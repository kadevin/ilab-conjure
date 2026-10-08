import asyncio
import json
import socket
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from codex_image.asset_dns import resolve_fake_ip_hostname
from codex_image.asset_urls import FakeIPAssetURLError, UnsafeAssetURLError, resolve_asset_destination
from codex_image.httpx_transport import HttpxTransport
from codex_image.http_connection import HTTPTransportFailure


def dns_entries(*addresses):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in addresses]


class AssetDNSResolverTests(unittest.IsolatedAsyncioTestCase):
    def mock_client(self, handler):
        client_class = httpx.AsyncClient
        self.options = []

        def create(**options):
            self.options.append(dict(options))
            options.pop("proxy", None)
            return client_class(transport=httpx.MockTransport(handler), **options)

        return patch("codex_image.asset_dns.httpx.AsyncClient", side_effect=create)

    async def test_queries_only_hostname_and_deduplicates_addresses(self):
        requests = []

        def handler(request):
            requests.append(request)
            number = 1 if request.url.params["type"] == "A" else 28
            address = "8.8.8.8" if number == 1 else "2001:4860:4860::8888"
            return httpx.Response(200, json={
                "Status": 0, "Question": [{"name": "cdn.example.", "type": number}],
                "Answer": [{"type": number, "data": address}] * 2,
            })

        with self.mock_client(handler):
            self.assertEqual(await resolve_fake_ip_hostname("cdn.example", proxy="http://proxy.example:8080"),
                             ("8.8.8.8", "2001:4860:4860::8888"))
        self.assertEqual(len(requests), 2)
        self.assertEqual(self.options[0]["proxy"], "http://proxy.example:8080")
        self.assertFalse(self.options[0]["follow_redirects"])
        for request in requests:
            self.assertEqual(request.url.host, "cloudflare-dns.com")
            self.assertEqual(set(request.url.params), {"name", "type"})
            self.assertNotIn("authorization", request.headers)
            self.assertEqual(request.content, b"")

    async def test_rejects_bad_status_malformed_mismatched_and_oversized_answers(self):
        responses = [
            httpx.Response(302, headers={"Location": "http://127.0.0.1/private"}),
            httpx.Response(200, content=b"invalid json"),
            httpx.Response(200, json={"Status": 0, "Question": [{"name": "other.example", "type": 1}]}),
            httpx.Response(200, content=b"x" * 65537),
            httpx.Response(200, json={"Status": 3, "Question": []}),
        ]
        for response in responses:
            with self.subTest(status=response.status_code), self.mock_client(lambda request: response):
                with self.assertRaises(UnsafeAssetURLError):
                    await resolve_fake_ip_hostname("cdn.example")

    async def test_cancellation_stops_both_queries(self):
        started = asyncio.Event()
        active = 0

        async def handler(request):
            nonlocal active
            active += 1
            if active == 2:
                started.set()
            try:
                await asyncio.Event().wait()
            finally:
                active -= 1

        with self.mock_client(handler):
            task = asyncio.create_task(resolve_fake_ip_hostname("cdn.example"))
            await asyncio.wait_for(started.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(active, 0)

    async def test_connection_retries_are_per_query_and_exhaustion_keeps_dns_stage(self):
        for failures in (1, 10):
            calls = {"A": 0, "AAAA": 0}

            def handler(request):
                record = request.url.params["type"]
                calls[record] += 1
                if calls[record] <= failures:
                    raise httpx.ConnectError("private-host secret-token")
                number, address = (1, "8.8.8.8") if record == "A" else (28, "2001:4860:4860::8888")
                return httpx.Response(200, json={
                    "Status": 0, "Question": [{"name": "cdn.example.", "type": number}],
                    "Answer": [{"type": number, "data": address}],
                })

            with self.subTest(failures=failures), self.mock_client(handler), \
                 patch("codex_image.http_connection.connection_retry_delay", return_value=0):
                if failures == 1:
                    self.assertEqual(await resolve_fake_ip_hostname("cdn.example", connect_retry_count=2),
                                     ("8.8.8.8", "2001:4860:4860::8888"))
                    self.assertEqual(calls, {"A": 2, "AAAA": 2})
                else:
                    with self.assertRaises(HTTPTransportFailure) as caught:
                        await resolve_fake_ip_hostname("cdn.example", connect_retry_count=2)
                    self.assertIn("stage=image_dns_lookup", str(caught.exception))
                    self.assertIn("host=cloudflare-dns.com", str(caught.exception))
                    self.assertIn("attempts=3", str(caught.exception))
                    self.assertNotIn("secret-token", str(caught.exception))
                    self.assertTrue(all(value <= 3 for value in calls.values()))

    async def test_cancellation_during_connection_backoff_stops_both_queries(self):
        calls = []
        backoff_started = asyncio.Event()

        def handler(request):
            calls.append(request)
            raise httpx.ConnectError("synthetic")

        def delay(_round):
            if len(calls) == 2:
                backoff_started.set()
            return 60

        with self.mock_client(handler), patch("codex_image.http_connection.connection_retry_delay", side_effect=delay):
            task = asyncio.create_task(resolve_fake_ip_hostname("cdn.example", connect_retry_count=2))
            await asyncio.wait_for(backoff_started.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(len(calls), 2)


class FakeIPDownloadTests(unittest.TestCase):
    def test_connection_retries_preserve_validated_address_order_host_and_tls_name(self):
        client_class = httpx.AsyncClient
        requests = []

        def handler(request):
            requests.append(request)
            if len(requests) < 3:
                raise httpx.ConnectError("synthetic")
            return httpx.Response(200, content=b"synthetic")

        with patch("socket.getaddrinfo", return_value=dns_entries("8.8.8.8", "1.1.1.1")), \
             patch("codex_image.httpx_transport.httpx.AsyncClient", side_effect=lambda **options:
                   client_class(transport=httpx.MockTransport(handler), **options)), \
             patch("codex_image.http_connection.connection_retry_delay", return_value=0):
            result = HttpxTransport(proxy_map={}, connect_retry_count=2).request_asset_bounded(
                url="https://cdn.example/image", headers={}, max_response_bytes=100,
                provider_base_url="https://provider.example",
            )
        self.assertEqual(result.body, b"synthetic")
        self.assertEqual([request.url.host for request in requests], ["8.8.8.8", "1.1.1.1", "8.8.8.8"])
        for request in requests:
            self.assertEqual(request.headers["host"], "cdn.example")
            self.assertEqual(request.extensions["sni_hostname"], "cdn.example")
            self.assertNotIn("authorization", request.headers)

    def test_only_domain_answers_entirely_in_fake_ip_range_trigger_fallback_signal(self):
        with patch("socket.getaddrinfo", return_value=dns_entries("198.18.1.2", "198.19.1.2")):
            with self.assertRaises(FakeIPAssetURLError) as caught:
                resolve_asset_destination("https://cdn.example/image", "https://provider.example")
            self.assertEqual(caught.exception.hostname, "cdn.example")
            with self.assertRaises(UnsafeAssetURLError) as literal:
                resolve_asset_destination("https://198.18.1.2/image", "https://provider.example")
            self.assertNotIsInstance(literal.exception, FakeIPAssetURLError)
        for addresses in (("10.0.0.1",), ("8.8.8.8", "198.18.1.2")):
            with patch("socket.getaddrinfo", return_value=dns_entries(*addresses)):
                with self.assertRaises(UnsafeAssetURLError) as caught:
                    resolve_asset_destination("https://cdn.example/image", "https://provider.example")
                self.assertNotIsInstance(caught.exception, FakeIPAssetURLError)

    def test_enabled_transport_pins_real_address_and_keeps_hostname_and_no_credentials(self):
        client_class = httpx.AsyncClient
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, content=b"synthetic asset")

        def create(**options):
            return client_class(transport=httpx.MockTransport(handler), **options)

        with patch("socket.getaddrinfo", return_value=dns_entries("198.18.1.2")), \
             patch("codex_image.httpx_transport.httpx.AsyncClient", side_effect=create), \
             patch("codex_image.httpx_transport.resolve_fake_ip_hostname", new_callable=AsyncMock,
                   return_value=("8.8.8.8",)) as independent:
            transport = HttpxTransport(proxy_map={}, asset_fake_ip_dns_fallback=True)
            result = transport.request_asset_bounded(
                url="https://cdn.example/image?signature=private", headers={"Accept": "image/*"},
                max_response_bytes=100, provider_base_url="https://provider.example/v1",
            )
        self.assertEqual(result.status, 200)
        independent.assert_awaited_once_with("cdn.example", proxy=None, connect_retry_count=0)
        self.assertEqual(requests[0].url.host, "8.8.8.8")
        self.assertEqual(requests[0].headers["host"], "cdn.example")
        self.assertEqual(requests[0].extensions["sni_hostname"], "cdn.example")
        self.assertNotIn("authorization", requests[0].headers)

    def test_disabled_transport_and_unsafe_independent_answers_never_download(self):
        for enabled, addresses in ((False, ("8.8.8.8",)), (True, ("10.0.0.1",)),
                                   (True, ("8.8.8.8", "127.0.0.1"))):
            with self.subTest(enabled=enabled, addresses=addresses), \
                 patch("socket.getaddrinfo", return_value=dns_entries("198.18.1.2")), \
                 patch("codex_image.httpx_transport.resolve_fake_ip_hostname", new_callable=AsyncMock,
                       return_value=addresses) as independent:
                transport = HttpxTransport(proxy_map={}, asset_fake_ip_dns_fallback=enabled)
                with self.assertRaises(UnsafeAssetURLError):
                    transport.request_asset_bounded(
                        url="https://cdn.example/image", headers={}, max_response_bytes=100,
                        provider_base_url="https://provider.example",
                    )
                self.assertEqual(independent.await_count, int(enabled))

    def test_enabled_fallback_revalidates_redirect_before_second_download(self):
        client_class = httpx.AsyncClient
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})

        original_lookup = socket.getaddrinfo

        def lookup(host, port, *args, **kwargs):
            return dns_entries("198.18.1.2") if host == "cdn.example" else original_lookup(host, port, *args, **kwargs)

        with patch("socket.getaddrinfo", side_effect=lookup), \
             patch("codex_image.httpx_transport.httpx.AsyncClient",
                   side_effect=lambda **options: client_class(transport=httpx.MockTransport(handler), **options)), \
             patch("codex_image.httpx_transport.resolve_fake_ip_hostname", new_callable=AsyncMock,
                   return_value=("8.8.8.8",)):
            with self.assertRaises(UnsafeAssetURLError):
                HttpxTransport(proxy_map={}, asset_fake_ip_dns_fallback=True).request_asset_bounded(
                    url="https://cdn.example/image", headers={}, max_response_bytes=100,
                    provider_base_url="https://provider.example",
                )
        self.assertEqual(len(requests), 1)
