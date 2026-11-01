import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from urllib.request import proxy_bypass_environment

import httpx

from codex_image.asset_urls import AssetDestination, FakeIPAssetURLError
from codex_image.httpx_transport import HttpxTransport


class AssetRedirectRoutingTests(unittest.TestCase):
    def exercise(self, urls, *, proxy_map=None, fake_ip=False, headers=None):
        requests, resolutions, closed = [], [], []
        client_class = httpx.AsyncClient

        class RecordingTransport(httpx.MockTransport):
            async def aclose(self):
                closed.append(True)
                await super().aclose()

        def transport(route):
            def handle(request):
                requests.append((route, request))
                if len(requests) == 1:
                    return httpx.Response(302, headers={"Location": urls[1]})
                return httpx.Response(200, content=b"synthetic")
            return RecordingTransport(handle)

        def client(**options):
            if "transport" not in options:
                options["transport"] = transport(options.pop("proxy", None))
            return client_class(**options)

        def resolve(url, provider, *, resolved_addresses=None):
            parsed = httpx.URL(url)
            resolutions.append(parsed.host)
            if fake_ip and resolved_addresses is None:
                raise FakeIPAssetURLError(parsed.host)
            return AssetDestination((str(parsed.copy_with(host="8.8.8.8")),), parsed.host, parsed.host)

        with patch("codex_image.httpx_transport.httpx.AsyncClient", side_effect=client), \
             patch("codex_image.httpx_transport.AssetProxyTransport", side_effect=lambda **kwargs: transport(kwargs["proxy"])), \
             patch("codex_image.httpx_transport.getproxies", return_value={"http": "http://system-proxy:8080", "https": "http://system-proxy:8080"}), \
             patch("codex_image.httpx_transport.proxy_bypass", side_effect=lambda host: host.startswith("direct.example:")) as bypass, \
             patch("codex_image.httpx_transport.resolve_asset_destination", side_effect=resolve), \
             patch("codex_image.httpx_transport.resolve_fake_ip_hostname", new_callable=AsyncMock, return_value=("8.8.8.8",)) as independent:
            result = HttpxTransport(proxy_map=proxy_map, asset_fake_ip_dns_fallback=fake_ip).request_asset_bounded(
                url=urls[0], headers=headers or {}, max_response_bytes=100,
                provider_base_url=urls[0],
            )
        return result, requests, bypass.call_args_list, independent.call_args_list, closed

    def test_system_proxy_and_no_proxy_are_rechecked_on_each_redirect(self):
        for hosts, routes in (
            (("direct.example", "proxied.example"), (None, "http://system-proxy:8080")),
            (("proxied.example", "direct.example"), ("http://system-proxy:8080", None)),
        ):
            for fake_ip in (False, True):
                with self.subTest(hosts=hosts, fake_ip=fake_ip):
                    result, requests, bypass, independent, closed = self.exercise(
                        [f"https://{host}/image" for host in hosts], fake_ip=fake_ip,
                    )
                    self.assertEqual(result.body, b"synthetic")
                    self.assertEqual([route for route, _ in requests], list(routes))
                    self.assertEqual([call.args[0] for call in bypass], [f"{host}:443" for host in hosts])
                    self.assertEqual([request.headers["host"] for _, request in requests], list(hosts))
                    self.assertEqual([request.extensions["sni_hostname"] for _, request in requests], list(hosts))
                    self.assertTrue(all(request.url.host == "8.8.8.8" for _, request in requests))
                    if fake_ip:
                        self.assertEqual([call.kwargs["proxy"] for call in independent], list(routes))
                    self.assertEqual(len(closed), 2)

    def test_redirect_scheme_selects_its_configured_proxy(self):
        _, requests, _, _, _ = self.exercise(
            ["http://cdn.example/start", "https://cdn.example/image"],
            proxy_map={"http": "http://first-proxy:8080", "https": "http://second-proxy:8080"},
        )
        self.assertEqual([route for route, _ in requests], ["http://first-proxy:8080", "http://second-proxy:8080"])

    def test_no_proxy_matches_effective_ports_and_ipv6(self):
        for url, rule, bypassed in (
            ("https://cdn.example/image", "cdn.example:443", True),
            ("https://cdn.example:443/image", "cdn.example:443", True),
            ("https://cdn.example:8443/image", "cdn.example:443", False),
            ("https://cdn.example:8443/image", "cdn.example", True),
            ("http://cdn.example/image", "cdn.example:80", True),
            ("https://[2606:4700::1111]/image", "[2606:4700::1111]:443", True),
        ):
            proxies = {"http": "http://proxy.example:8080", "https": "http://proxy.example:8080", "no": rule}
            with self.subTest(url=url, rule=rule), \
                 patch("codex_image.httpx_transport.getproxies", return_value=proxies), \
                 patch("codex_image.httpx_transport.proxy_bypass", side_effect=lambda host: proxy_bypass_environment(host, proxies)):
                client, proxy = HttpxTransport()._new_request_client(url, asset=True)
                asyncio.run(client.aclose())
                self.assertEqual(proxy is None, bypassed)

    def test_authenticated_cross_origin_redirect_does_not_start_another_route(self):
        response, requests, bypass, _, closed = self.exercise(
            ["https://direct.example/start", "https://proxied.example/image"],
            headers={"Authorization": "Bearer synthetic"},
        )
        self.assertEqual(response.status, 302)
        self.assertEqual(len(requests), 1)
        self.assertEqual(len(bypass), 1)
        self.assertEqual(len(closed), 1)
