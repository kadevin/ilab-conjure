"""Keep checked asset IPs and the original TLS hostname through HTTP proxies."""
from __future__ import annotations

from contextvars import ContextVar
import ssl
from urllib.parse import urlsplit

import httpx


_ASSET_HOSTNAME: ContextVar[str | None] = ContextVar("asset_tls_hostname", default=None)


class _AssetProxyStream:
    def __init__(self, stream, context: ssl.SSLContext, hostname: str | None, proxy_hostname: str) -> None:
        self._stream = stream
        self._context = context
        self._hostname = hostname
        self._proxy_hostname = proxy_hostname

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return await self._stream.read(max_bytes, timeout)

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        await self._stream.write(buffer, timeout)

    async def aclose(self) -> None:
        await self._stream.aclose()

    def get_extra_info(self, info: str):
        return self._stream.get_extra_info(info)

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        # Use the asset hostname only for destination TLS. An HTTPS proxy's
        # outer TLS connection must still verify the proxy's own hostname.
        if ssl_context is self._context and self._hostname:
            server_hostname = self._hostname
        elif ssl_context is not self._context:
            # httpcore forwards request extensions to CONNECT too, so its
            # direct connection may incorrectly pick the asset's SNI here.
            server_hostname = self._proxy_hostname
        stream = await self._stream.start_tls(ssl_context, server_hostname, timeout)
        return _AssetProxyStream(stream, self._context, self._hostname, self._proxy_hostname)


class _AssetProxyBackend:
    def __init__(self, backend, context: ssl.SSLContext, proxy_hostname: str) -> None:
        self._backend = backend
        self._context = context
        self._proxy_hostname = proxy_hostname

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        stream = await self._backend.connect_tcp(
            host=host, port=port, timeout=timeout,
            local_address=local_address, socket_options=socket_options,
        )
        return _AssetProxyStream(stream, self._context, _ASSET_HOSTNAME.get(), self._proxy_hostname)

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        stream = await self._backend.connect_unix_socket(
            path=path, timeout=timeout, socket_options=socket_options,
        )
        return _AssetProxyStream(stream, self._context, _ASSET_HOSTNAME.get(), self._proxy_hostname)

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class AssetProxyTransport(httpx.AsyncHTTPTransport):
    def __init__(self, *, proxy: str, verify: ssl.SSLContext) -> None:
        super().__init__(
            proxy=proxy, verify=verify, trust_env=False,
            # Different redirect hostnames may share a pinned IP. Never reuse
            # a tunnel authenticated for the previous hostname.
            limits=httpx.Limits(max_keepalive_connections=0),
        )
        # HTTPX 0.28.1/httpcore 1.0.9 have no HTTP-proxy SNI hook: the latter
        # ignores the sni_hostname extension on CONNECT tunnels. Keep this
        # compatibility adapter isolated and covered by a real TLS proxy test.
        self._pool._network_backend = _AssetProxyBackend(
            self._pool._network_backend, verify, urlsplit(proxy).hostname or "",
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        token = _ASSET_HOSTNAME.set(request.extensions.get("sni_hostname"))
        try:
            return await super().handle_async_request(request)
        finally:
            _ASSET_HOSTNAME.reset(token)
