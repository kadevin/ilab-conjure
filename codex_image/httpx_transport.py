from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Coroutine, Iterator, Mapping, TypeVar
from urllib.parse import urljoin, urlsplit
from urllib.request import getproxies, proxy_bypass

import httpx

from .asset_urls import resolve_asset_destination

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
    ) -> None:
        self.timeout = _request_timeout_seconds(timeout)
        self.proxy_map = None if proxy_map is None else dict(proxy_map)

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
        try:
            proxy = self._proxy_for_url(url)
            trust_env = self.proxy_map is None
            client_options = {}
            if asset_provider_base_url is not None and self.proxy_map is None:
                # NO_PROXY applies to the original hostname, before pinning.
                parsed = urlsplit(url)
                proxies = getproxies()
                proxy = None if proxy_bypass(parsed.hostname or "") else (proxies.get(parsed.scheme) or proxies.get("all"))
                trust_env = False
                client_options["verify"] = _https_ssl_context() or True
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                proxy=proxy,
                trust_env=trust_env,
                follow_redirects=not same_origin_redirects and asset_provider_base_url is None,
                **client_options,
            ) as client:
                current_method = method
                current_url = url
                current_headers = dict(headers)
                current_body = bytes(body)
                for redirect_count in range(client.max_redirects + 1):
                    request_urls = (current_url,)
                    request_headers = current_headers
                    extensions = {}
                    if asset_provider_base_url is not None:
                        destination = await asyncio.to_thread(resolve_asset_destination, current_url, asset_provider_base_url)
                        request_urls = destination.urls
                        request_headers = {**current_headers, "Host": destination.host_header}
                        extensions = {"sni_hostname": destination.server_hostname}
                    async with _stream_with_address_fallback(
                        client, current_method, request_urls,
                        headers=request_headers,
                        content=current_body,
                        extensions=extensions,
                    ) as response:
                        location = response.headers.get("location", "")
                        if (
                            (same_origin_redirects or asset_provider_base_url is not None)
                            and response.status_code in self._REDIRECT_STATUSES
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


@asynccontextmanager
async def _stream_with_address_fallback(client, method, urls, **kwargs):
    for index, url in enumerate(urls):
        opened = False
        try:
            async with client.stream(method, url, **kwargs) as response:
                opened = True
                yield response
                return
        except (httpx.ConnectError, httpx.ConnectTimeout):
            if opened or index == len(urls) - 1:
                raise


__all__ = (
    "HTTPRequestCancellationScope",
    "HttpxTransport",
    "cancellable_http_request_scope",
)
