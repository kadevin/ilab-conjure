from __future__ import annotations

import ipaddress
from typing import Final
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .resource_limits import MAX_HTTP_REQUEST_BYTES
from .lan_access import LanAccessRuntime


_SAFE_METHODS: Final = frozenset({"GET", "HEAD"})
_CONTENT_SECURITY_POLICY: Final = (
    "default-src 'self'; "
    "base-uri 'none'; "
    "connect-src 'self'; "
    "font-src 'self' data:; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "img-src 'self' data: blob: https:; "
    "media-src 'self' blob:; "
    "object-src 'none'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "worker-src 'self' blob:"
)
_SECURITY_HEADERS: Final = {
    "Content-Security-Policy": _CONTENT_SECURITY_POLICY,
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


class _RequestBodyTooLarge(Exception):
    pass


def _parse_authority(authority: str) -> tuple[str, int | None] | None:
    raw = str(authority or "").strip()
    if not raw or any(character in raw for character in ("/", "\\", "@", ",", "\x00")):
        return None
    hostname: str
    port_text: str | None = None
    if raw.startswith("["):
        closing = raw.find("]")
        if closing <= 1:
            return None
        hostname = raw[1:closing]
        remainder = raw[closing + 1 :]
        if remainder:
            if not remainder.startswith(":"):
                return None
            port_text = remainder[1:]
    else:
        if raw.count(":") > 1:
            return None
        if ":" in raw:
            hostname, port_text = raw.rsplit(":", 1)
        else:
            hostname = raw
    hostname = hostname.rstrip(".").lower()
    if not hostname or "%" in hostname:
        return None
    port: int | None = None
    if port_text is not None:
        if not port_text.isdigit():
            return None
        port = int(port_text)
        if not 1 <= port <= 65535:
            return None
    return hostname, port


def _is_loopback_name(hostname: str) -> bool:
    if hostname == "localhost":
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    if address.is_loopback:
        return True
    mapped = getattr(address, "ipv4_mapped", None)
    return bool(mapped is not None and mapped.is_loopback)


def _client_is_loopback(scope: Scope) -> bool:
    client = scope.get("client")
    if not client:
        return False
    hostname = str(client[0] or "").strip().lower()
    return hostname == "testclient" or _is_loopback_name(hostname)


def _host_is_allowed(scope: Scope, host_header: str) -> bool:
    parsed = _parse_authority(host_header)
    if parsed is None:
        return False
    hostname, _ = parsed
    client = scope.get("client")
    client_hostname = str(client[0] or "").strip().lower() if client else ""
    if hostname == "testserver":
        return client_hostname == "testclient"
    return _is_loopback_name(hostname)


def _effective_port(scheme: str, explicit_port: int | None) -> int | None:
    if explicit_port is not None:
        return explicit_port
    if scheme == "http":
        return 80
    if scheme == "https":
        return 443
    return None


def _origin_matches_request(scope: Scope, origin: str, host_header: str) -> bool:
    if not origin or any(character in origin for character in (",", "\x00")):
        return False
    try:
        parsed_origin = urlsplit(origin)
        origin_port = parsed_origin.port
    except ValueError:
        return False
    if (
        parsed_origin.scheme not in {"http", "https"}
        or parsed_origin.username is not None
        or parsed_origin.password is not None
        or parsed_origin.hostname is None
        or parsed_origin.path not in {"", "/"}
        or parsed_origin.query
        or parsed_origin.fragment
    ):
        return False
    parsed_host = _parse_authority(host_header)
    if parsed_host is None:
        return False
    request_host, request_port = parsed_host
    scheme = str(scope.get("scheme") or "http").lower()
    return (
        parsed_origin.scheme == scheme
        and parsed_origin.hostname.rstrip(".").lower() == request_host
        and _effective_port(parsed_origin.scheme, origin_port)
        == _effective_port(scheme, request_port)
    )


class LocalWebUISecurityMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        max_request_bytes: int = MAX_HTTP_REQUEST_BYTES,
        lan_access: LanAccessRuntime | None = None,
    ) -> None:
        if max_request_bytes <= 0:
            raise ValueError("max_request_bytes must be positive")
        self.app = app
        self.max_request_bytes = int(max_request_bytes)
        self.lan_access = lan_access or LanAccessRuntime()

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        host_header = headers.get("host", "")
        rejection: tuple[int, str] | None = None
        if not _parse_authority(host_header) or (
            not self.lan_access.active and not _host_is_allowed(scope, host_header)
        ):
            rejection = (400, "Invalid local WebUI host")
        elif not self.lan_access.active and not _client_is_loopback(scope):
            rejection = (403, "WebUI access is limited to this device")
        elif scope["type"] == "http" and str(scope.get("method") or "").upper() not in _SAFE_METHODS:
            fetch_site = headers.get("sec-fetch-site", "").strip().lower()
            origin = headers.get("origin", "").strip()
            if fetch_site == "cross-site":
                rejection = (403, "Cross-site WebUI request rejected")
            elif origin and not _origin_matches_request(scope, origin, host_header):
                rejection = (403, "Cross-origin WebUI request rejected")

        declared_length = headers.get("content-length", "").strip()
        if (
            rejection is None
            and scope["type"] == "http"
            and declared_length.isdigit()
            and int(declared_length) > self.max_request_bytes
        ):
            rejection = (413, "request_body_too_large")

        if scope["type"] == "websocket":
            if rejection is not None:
                await send({"type": "websocket.close", "code": 1008})
                return
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                for name, value in _SECURITY_HEADERS.items():
                    response_headers[name] = value
            await send(message)

        if rejection is not None:
            status_code, detail = rejection
            payload: dict[str, object]
            if status_code == 413:
                payload = {
                    "detail": {
                        "code": detail,
                        "message": "The request body is too large.",
                    }
                }
            else:
                payload = {"detail": detail}
            await JSONResponse(
                payload,
                status_code=status_code,
            )(scope, receive, send_with_security_headers)
            return

        received_bytes = 0
        response_started = False

        async def receive_with_limit() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_request_bytes:
                    raise _RequestBodyTooLarge
            return message

        async def send_with_state(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send_with_security_headers(message)

        try:
            await self.app(scope, receive_with_limit, send_with_state)
        except _RequestBodyTooLarge:
            if response_started:
                raise
            await JSONResponse(
                {
                    "detail": {
                        "code": "request_body_too_large",
                        "message": "The request body is too large.",
                    }
                },
                status_code=413,
            )(scope, receive, send_with_security_headers)
