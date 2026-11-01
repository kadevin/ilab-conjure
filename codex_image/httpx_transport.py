from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import socket
import ssl
import threading
import time
from contextlib import AsyncExitStack, contextmanager
from typing import Any, Coroutine, Iterator, Mapping, TypeVar
from urllib.parse import urljoin, urlsplit
from urllib.request import getproxies, proxy_bypass

import httpx

from .asset_urls import AssetDestination, FakeIPAssetURLError, UnsafeAssetURLError, resolve_asset_destination
from .asset_dns import resolve_fake_ip_hostname
from .asset_proxy_transport import AssetProxyTransport
from .http_connection import HTTPTransportFailure, connection_retry_delay, exception_chain, stream_with_connection_retries

from .http import (
    HTTPResponse,
    HTTPResponseTooLarge,
    MAX_HTTP_ERROR_BODY_BYTES,
    MAX_HTTP_RESPONSE_BYTES,
    _CREDENTIAL_HEADER_NAMES,
    _format_elapsed_seconds,
    _request_timeout_seconds,
    _same_origin,
    _https_ssl_context,
)


_T = TypeVar("_T")


class HTTPRequestCancellationScope:
    """Bridge synchronous client calls to cancellable I/O on their owner loop."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._lock = threading.Lock()
        self._cancelled = False
        self._active: set[asyncio.Task[Any]] = set()
        self._cleanup: list[concurrent.futures.Future[None]] = []

    def run(self, operation: Coroutine[Any, Any, _T]) -> _T:
        cleanup: concurrent.futures.Future[None] = concurrent.futures.Future()

        async def tracked_operation() -> _T:
            task = asyncio.current_task()
            if task is None:
                operation.close()
                raise RuntimeError("HTTP request did not start in an asyncio task")
            with self._lock:
                self._active.add(task)
                cancelled = self._cancelled
            try:
                if cancelled:
                    operation.close()
                    raise asyncio.CancelledError()
                return await operation
            finally:
                with self._lock:
                    self._active.discard(task)
                if not cleanup.done():
                    cleanup.set_result(None)

        with self._lock:
            if self._cancelled:
                operation.close()
                raise concurrent.futures.CancelledError()
            future = asyncio.run_coroutine_threadsafe(tracked_operation(), self._loop)
            self._cleanup.append(cleanup)
        return future.result()

    def cancel(self) -> bool:
        with self._lock:
            self._cancelled = True
            active = tuple(self._active)
        for task in active:
            self._loop.call_soon_threadsafe(task.cancel)
        return bool(active)

    async def wait_closed(self) -> None:
        with self._lock:
            cleanup = tuple(self._cleanup)
        if cleanup:
            await asyncio.gather(
                *(asyncio.wrap_future(item) for item in cleanup),
                return_exceptions=True,
            )


_CURRENT_HTTP_REQUEST_SCOPE: contextvars.ContextVar[HTTPRequestCancellationScope | None] = (
    contextvars.ContextVar("codex_image_http_request_scope", default=None)
)


@contextmanager
def cancellable_http_request_scope(
    loop: asyncio.AbstractEventLoop,
) -> Iterator[HTTPRequestCancellationScope]:
    scope = HTTPRequestCancellationScope(loop)
    token = _CURRENT_HTTP_REQUEST_SCOPE.set(scope)
    try:
        yield scope
    finally:
        _CURRENT_HTTP_REQUEST_SCOPE.reset(token)


class HttpxTransport:
    """Synchronous client facade backed by cancellable ``httpx`` async I/O.

    WebUI image clients still expose synchronous methods. When the executor
    installs a cancellation scope, this facade submits network work to that
    scope's event loop and blocks only the worker thread. Cancelling the scope
    therefore cancels and closes the actual response connection before the
    worker and provider slot are released.
    """

    _REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

    def __init__(
        self,
        *,
        timeout: float | None = None,
        proxy_map: Mapping[str, str] | None = None,
        asset_fake_ip_dns_fallback: bool = False,
        connect_retry_count: int = 0,
    ) -> None:
        self.timeout = _request_timeout_seconds(timeout)
        self.proxy_map = None if proxy_map is None else dict(proxy_map)
        self.asset_fake_ip_dns_fallback = asset_fake_ip_dns_fallback
        self.connect_retry_count = max(0, min(5, int(connect_retry_count)))

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
    ) -> HTTPResponse:
        return self.request_bounded(
            method=method,
            url=url,
            headers=headers,
            body=body,
            max_response_bytes=MAX_HTTP_RESPONSE_BYTES,
        )

    def request_bounded(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        max_response_bytes: int,
    ) -> HTTPResponse:
        return self._run(
            self._request_bounded(
                method=method,
                url=url,
                headers=headers,
                body=body,
                max_response_bytes=max_response_bytes,
                same_origin_redirects=any(
                    str(name).lower() in _CREDENTIAL_HEADER_NAMES for name in headers
                ),
            )
        )

    def request_same_origin_redirects(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
    ) -> HTTPResponse:
        return self.request_same_origin_redirects_bounded(
            method=method,
            url=url,
            headers=headers,
            body=body,
            max_response_bytes=MAX_HTTP_RESPONSE_BYTES,
        )

    def request_asset_bounded(
        self, *, url: str, headers: dict[str, str], max_response_bytes: int,
        provider_base_url: str,
    ) -> HTTPResponse:
        return self._run(self._request_bounded(
            method="GET", url=url, headers=headers, body=b"",
            max_response_bytes=max_response_bytes,
            same_origin_redirects=any(name.lower() in _CREDENTIAL_HEADER_NAMES for name in headers),
            asset_provider_base_url=provider_base_url,
        ))

    def request_same_origin_redirects_bounded(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        max_response_bytes: int,
    ) -> HTTPResponse:
        return self._run(
            self._request_bounded(
                method=method,
                url=url,
                headers=headers,
                body=body,
                max_response_bytes=max_response_bytes,
                same_origin_redirects=True,
            )
        )

    @staticmethod
    def _run(operation: Coroutine[Any, Any, _T]) -> _T:
        scope = _CURRENT_HTTP_REQUEST_SCOPE.get()
        if scope is not None:
            return scope.run(operation)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(operation)
        operation.close()
        raise RuntimeError(
            "HttpxTransport.request must run in a worker thread when an event loop is active"
        )

    def _proxy_for_url(self, url: str) -> str | None:
        if self.proxy_map is None:
            return None
        scheme = urlsplit(url).scheme.lower()
        return self.proxy_map.get(scheme) or self.proxy_map.get("all")

    def _new_request_client(self, url: str, *, asset: bool) -> tuple[httpx.AsyncClient, str | None]:
        proxy = self._proxy_for_url(url)
        trust_env = self.proxy_map is None
        options: dict[str, Any] = {}
        if asset and self.proxy_map is None:
            # Match NO_PROXY against each original redirect hostname, not its pinned IP.
            parsed = urlsplit(url)
            proxies = getproxies()
            hostname = parsed.hostname or ""
            authority = f"[{hostname}]" if ":" in hostname else hostname
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            proxy = None if proxy_bypass(f"{authority}:{port}") else (proxies.get(parsed.scheme) or proxies.get("all"))
            trust_env = False
            options["verify"] = _https_ssl_context() or True
        if asset and proxy and urlsplit(proxy).scheme.lower() in {"http", "https"}:
            options["transport"] = AssetProxyTransport(
                proxy=proxy, verify=_https_ssl_context() or ssl.create_default_context(),
            )
            # An AsyncClient proxy mount would bypass the custom transport.
            proxy_for_client = None
        else:
            proxy_for_client = proxy
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout), proxy=proxy_for_client,
            trust_env=trust_env, follow_redirects=False, **options,
        ), proxy

    async def _resolve_asset_destination(
        self, url: str, provider_base_url: str, *, proxy: str | None, route: str,
    ) -> AssetDestination:
        for attempt in range(1, self.connect_retry_count + 2):
            try:
                try:
                    return await asyncio.to_thread(resolve_asset_destination, url, provider_base_url)
                except FakeIPAssetURLError as exc:
                    if not self.asset_fake_ip_dns_fallback:
                        raise
                    addresses = await resolve_fake_ip_hostname(
                        exc.hostname, proxy=proxy, connect_retry_count=self.connect_retry_count,
                    )
                    return resolve_asset_destination(url, provider_base_url, resolved_addresses=addresses)
            except UnsafeAssetURLError as exc:
                dns_error = next((item for item in exception_chain(exc) if isinstance(item, socket.gaierror)), None)
                if dns_error is None:
                    raise
                if dns_error.errno != socket.EAI_AGAIN or attempt > self.connect_retry_count:
                    raise HTTPTransportFailure(
                        phase="image_dns_lookup", hostname=urlsplit(url).hostname or "",
                        route=route, attempts=attempt, error=exc,
                    ) from exc
                # Only a transient lookup is repeated. Once resolved, all
                # download attempts use the same validated address set.
                await asyncio.sleep(connection_retry_delay(attempt - 1))
        raise RuntimeError("Asset resolution ended without a result")

    async def _request_bounded(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        max_response_bytes: int,
        same_origin_redirects: bool,
        asset_provider_base_url: str | None = None,
    ) -> HTTPResponse:
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        started_at = time.monotonic()
        phase = "image_download" if asset_provider_base_url is not None else "upstream_request"
        try:
            async with AsyncExitStack() as client_stack:
                client, proxy = self._new_request_client(url, asset=asset_provider_base_url is not None)
                await client_stack.enter_async_context(client)
                current_method = method
                current_url = url
                current_headers = dict(headers)
                current_body = bytes(body)
                for redirect_count in range(client.max_redirects + 1):
                    if redirect_count and asset_provider_base_url is not None:
                        # Retire the previous hop before selecting the next route
                        # and TLS hostname; no tunnel is shared across asset hosts.
                        await client_stack.aclose()
                        client, proxy = self._new_request_client(current_url, asset=True)
                        await client_stack.enter_async_context(client)
                    route = "system" if self.proxy_map is None else "proxy" if proxy else "direct"
                    request_urls = (current_url,)
                    request_headers = current_headers
                    extensions = {}
                    if asset_provider_base_url is not None:
                        destination = await self._resolve_asset_destination(
                            current_url, asset_provider_base_url, proxy=proxy, route=route,
                        )
                        request_urls = destination.urls
                        request_headers = {**current_headers, "Host": destination.host_header}
                        extensions = {"sni_hostname": destination.server_hostname}
                    async with stream_with_connection_retries(
                        client, current_method, request_urls,
                        retry_count=self.connect_retry_count, phase=phase,
                        hostname=urlsplit(current_url).hostname or "", route=route,
                        headers=request_headers,
                        content=current_body,
                        extensions=extensions,
                    ) as response:
                        location = response.headers.get("location", "")
                        if (
                            response.status_code in self._REDIRECT_STATUSES
                            and location
                        ):
                            redirected_url = urljoin(current_url, location)
                            if same_origin_redirects and not _same_origin(url, redirected_url):
                                return HTTPResponse(
                                    status=response.status_code,
                                    body=await self._read_body(
                                        response,
                                        max_response_bytes=max_response_bytes,
                                    ),
                                    headers=dict(response.headers.items()),
                                )
                            if redirect_count >= client.max_redirects:
                                raise httpx.TooManyRedirects(
                                    "Exceeded maximum allowed redirects",
                                    request=response.request,
                                )
                            if not same_origin_redirects and asset_provider_base_url is None:
                                redirected_request = response.next_request
                                current_url = str(redirected_request.url)
                                current_method = redirected_request.method
                                current_headers = dict(redirected_request.headers)
                                current_body = await redirected_request.aread()
                                continue
                            current_url = redirected_url
                            if response.status_code == 303 or (
                                response.status_code in {301, 302}
                                and current_method.upper() == "POST"
                            ):
                                current_method = "GET"
                                current_body = b""
                                current_headers = {
                                    name: value
                                    for name, value in current_headers.items()
                                    if name.lower() not in {"content-length", "content-type"}
                                }
                            continue
                        return HTTPResponse(
                            status=response.status_code,
                            body=await self._read_body(
                                response,
                                max_response_bytes=max_response_bytes,
                            ),
                            headers=dict(response.headers.items()),
                        )
        except HTTPResponseTooLarge as exc:
            # Preserve the bounded-response API while recording that this
            # failure occurred after a response, so outer loops cannot replay it.
            failure = HTTPTransportFailure(phase=phase, hostname=urlsplit(current_url).hostname or "",
                                           route=route, attempts=1, error=exc)
            raise exc from failure
        except httpx.TimeoutException as exc:
            elapsed = _format_elapsed_seconds(time.monotonic() - started_at)
            raise TimeoutError(
                f"HTTP request timed out after {elapsed}s (timeout limit {self.timeout:g}s): {exc}"
            ) from exc
        raise RuntimeError("HTTP redirect loop completed without a response")

    @staticmethod
    async def _read_body(
        response: httpx.Response,
        *,
        max_response_bytes: int,
    ) -> bytes:
        is_success = 200 <= response.status_code < 300
        limit = max_response_bytes if is_success else MAX_HTTP_ERROR_BODY_BYTES
        declared_length = response.headers.get("content-length", "").strip()
        if is_success and declared_length.isdigit() and int(declared_length) > limit:
            raise HTTPResponseTooLarge(
                f"HTTP response exceeded the {limit}-byte limit"
            )
        payload = bytearray()
        async for chunk in response.aiter_bytes():
            remaining = limit + 1 - len(payload)
            if remaining <= 0:
                break
            payload.extend(chunk[:remaining])
            if len(payload) > limit:
                break
        if len(payload) <= limit:
            return bytes(payload)
        if is_success:
            raise HTTPResponseTooLarge(
                f"HTTP response exceeded the {limit}-byte limit"
            )
        return bytes(payload[:limit])


__all__ = (
    "HTTPRequestCancellationScope",
    "HttpxTransport",
    "cancellable_http_request_scope",
)
