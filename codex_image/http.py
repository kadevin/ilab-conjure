from __future__ import annotations

import os
import http.client
import socket
import ssl
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Protocol
from urllib import error, request
from urllib.parse import urljoin, urlsplit

from .asset_urls import resolve_asset_destination

DEFAULT_REQUEST_TIMEOUT_SECONDS = 600.0
MAX_HTTP_RESPONSE_BYTES = 320 * 1024 * 1024
MAX_HTTP_ERROR_BODY_BYTES = 2 * 1024 * 1024
_CREDENTIAL_HEADER_NAMES = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "x-goog-api-key",
        "x-api-key",
        "api-key",
    }
)


class HTTPResponseTooLarge(RuntimeError):
    pass


def _request_timeout_seconds(value: float | None = None) -> float:
    if value is not None:
        return float(value)
    raw = os.getenv("CODEX_IMAGE_REQUEST_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_REQUEST_TIMEOUT_SECONDS
    try:
        parsed = float(raw)
    except ValueError:
        return DEFAULT_REQUEST_TIMEOUT_SECONDS
    return parsed if parsed > 0 else DEFAULT_REQUEST_TIMEOUT_SECONDS


def _format_elapsed_seconds(seconds: float) -> str:
    return f"{max(0.0, seconds):.2f}".rstrip("0").rstrip(".")


@lru_cache(maxsize=1)
def _https_ssl_context() -> ssl.SSLContext | None:
    if os.getenv("SSL_CERT_FILE") or os.getenv("SSL_CERT_DIR"):
        return ssl.create_default_context()

    try:
        import certifi  # type: ignore[import-not-found]
    except Exception:
        return None

    ca_file = Path(certifi.where())
    if not ca_file.is_file():
        return None
    return ssl.create_default_context(cafile=str(ca_file))


@dataclass
class HTTPResponse:
    status: int
    body: bytes
    headers: dict[str, str]


class Transport(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
    ) -> HTTPResponse: ...


def _response_header(headers: object, name: str) -> str:
    getter = getattr(headers, "get", None)
    if callable(getter):
        value = getter(name)
        if value is None:
            value = getter(name.lower())
        return str(value or "")
    return ""


def _read_response_body(
    response: object,
    *,
    status: int,
    max_response_bytes: int,
) -> bytes:
    if max_response_bytes <= 0:
        raise ValueError("max_response_bytes must be positive")
    is_success = 200 <= status < 300
    limit = max_response_bytes if is_success else MAX_HTTP_ERROR_BODY_BYTES
    headers = getattr(response, "headers", {})
    declared_length = _response_header(headers, "Content-Length").strip()
    if is_success and declared_length.isdigit() and int(declared_length) > limit:
        raise HTTPResponseTooLarge(
            f"HTTP response exceeded the {limit}-byte limit"
        )
    payload = response.read(limit + 1)
    if len(payload) <= limit:
        return payload
    if is_success:
        raise HTTPResponseTooLarge(
            f"HTTP response exceeded the {limit}-byte limit"
        )
    return payload[:limit]


def _same_origin(left: str, right: str) -> bool:
    left_url = urlsplit(left)
    right_url = urlsplit(right)
    return (
        left_url.scheme.lower(),
        (left_url.hostname or "").lower(),
        left_url.port or (443 if left_url.scheme.lower() == "https" else 80),
    ) == (
        right_url.scheme.lower(),
        (right_url.hostname or "").lower(),
        right_url.port or (443 if right_url.scheme.lower() == "https" else 80),
    )


class _SameOriginRedirectHandler(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        if not _same_origin(req.full_url, newurl):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _NoRedirectHandler(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _AssetHTTPSHandler(request.HTTPSHandler):
    def __init__(self, server_hostname: str) -> None:
        super().__init__(context=_https_ssl_context())
        self.server_hostname = server_hostname

    def https_open(self, req):
        hostname = self.server_hostname

        class AssetHTTPSConnection(http.client.HTTPSConnection):
            def connect(self):
                # The URL (including a proxy CONNECT target) is pinned to the
                # checked IP. TLS still verifies the original hostname.
                http.client.HTTPConnection.connect(self)
                self.sock = self._context.wrap_socket(self.sock, server_hostname=hostname)

        return self.do_open(AssetHTTPSConnection, req, context=self._context)


class UrllibTransport:
    def __init__(
        self,
        *,
        timeout: float | None = None,
        proxy_map: Mapping[str, str] | None = None,
    ) -> None:
        self.timeout = _request_timeout_seconds(timeout)
        self.proxy_map = None if proxy_map is None else dict(proxy_map)

    def request_asset_bounded(
        self, *, url: str, headers: dict[str, str], max_response_bytes: int,
        provider_base_url: str,
    ) -> HTTPResponse:
        authenticated = any(name.lower() in _CREDENTIAL_HEADER_NAMES for name in headers)
        current_url = url
        for _ in range(21):
            destination = resolve_asset_destination(current_url, provider_base_url)
            proxies = self.proxy_map
            if proxies is None and request.proxy_bypass(destination.server_hostname):
                proxies = {}
            opener = request.build_opener(
                request.ProxyHandler(proxies), _NoRedirectHandler(),
                _AssetHTTPSHandler(destination.server_hostname),
            )
            for index, pinned_url in enumerate(destination.urls):
                req = request.Request(pinned_url, headers={**headers, "Host": destination.host_header}, method="GET")
                try:
                    response = opener.open(req, timeout=self.timeout)
                except error.HTTPError as exc:
                    response = exc
                except (error.URLError, ConnectionError, TimeoutError):
                    if index == len(destination.urls) - 1:
                        raise
                    continue
                break
            with response:
                status = response.code
                location = _response_header(response.headers, "Location")
                if status in {301, 302, 303, 307, 308} and location:
                    redirect = urljoin(current_url, location)
                    if not authenticated or _same_origin(url, redirect):
                        current_url = redirect
                        continue
                return HTTPResponse(status, _read_response_body(response, status=status, max_response_bytes=max_response_bytes), dict(response.headers.items()))
        raise RuntimeError("Too many generated asset redirects")

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
        if any(str(name).lower() in _CREDENTIAL_HEADER_NAMES for name in headers):
            return self.request_same_origin_redirects_bounded(
                method=method,
                url=url,
                headers=headers,
                body=body,
                max_response_bytes=max_response_bytes,
            )
        req = request.Request(url=url, data=body, headers=headers, method=method)
        started_at = time.monotonic()
        try:
            context = _https_ssl_context() if url.lower().startswith("https://") else None
            if self.proxy_map is None:
                response_context = request.urlopen(req, timeout=self.timeout, context=context)
            else:
                handlers: list[object] = [request.ProxyHandler(self.proxy_map)]
                if context is not None:
                    handlers.append(request.HTTPSHandler(context=context))
                response_context = request.build_opener(*handlers).open(req, timeout=self.timeout)
            with response_context as response:
                status = getattr(response, "status", response.getcode())
                return HTTPResponse(
                    status=status,
                    body=_read_response_body(
                        response,
                        status=status,
                        max_response_bytes=max_response_bytes,
                    ),
                    headers=dict(response.headers.items()),
                )
        except error.HTTPError as exc:
            return HTTPResponse(
                status=exc.code,
                body=_read_response_body(
                    exc,
                    status=exc.code,
                    max_response_bytes=max_response_bytes,
                ),
                headers=dict(exc.headers.items()),
            )
        except socket.timeout as exc:
            elapsed = _format_elapsed_seconds(time.monotonic() - started_at)
            raise TimeoutError(f"HTTP request timed out after {elapsed}s (timeout limit {self.timeout:g}s)") from exc
        except error.URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                elapsed = _format_elapsed_seconds(time.monotonic() - started_at)
                raise TimeoutError(
                    f"HTTP request timed out after {elapsed}s (timeout limit {self.timeout:g}s): {exc.reason}"
                ) from exc
            raise

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

    def request_same_origin_redirects_bounded(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        max_response_bytes: int,
    ) -> HTTPResponse:
        req = request.Request(url=url, data=body, headers=headers, method=method)
        handlers: list[object] = []
        if self.proxy_map is not None:
            handlers.append(request.ProxyHandler(self.proxy_map))
        handlers.append(_SameOriginRedirectHandler())
        context = _https_ssl_context() if url.lower().startswith("https://") else None
        if context is not None:
            handlers.append(request.HTTPSHandler(context=context))
        opener = request.build_opener(*handlers)
        started_at = time.monotonic()
        try:
            with opener.open(req, timeout=self.timeout) as response:
                status = getattr(response, "status", response.getcode())
                return HTTPResponse(
                    status=status,
                    body=_read_response_body(
                        response,
                        status=status,
                        max_response_bytes=max_response_bytes,
                    ),
                    headers=dict(response.headers.items()),
                )
        except error.HTTPError as exc:
            return HTTPResponse(
                status=exc.code,
                body=_read_response_body(
                    exc,
                    status=exc.code,
                    max_response_bytes=max_response_bytes,
                ),
                headers=dict(exc.headers.items()),
            )
        except socket.timeout as exc:
            elapsed = _format_elapsed_seconds(time.monotonic() - started_at)
            raise TimeoutError(
                f"HTTP request timed out after {elapsed}s (timeout limit {self.timeout:g}s)"
            ) from exc
        except error.URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                elapsed = _format_elapsed_seconds(time.monotonic() - started_at)
                raise TimeoutError(
                    f"HTTP request timed out after {elapsed}s (timeout limit {self.timeout:g}s): {exc.reason}"
                ) from exc
            raise
