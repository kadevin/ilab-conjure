from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import socket
import ssl
import shutil
import subprocess
import tempfile
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from PIL import Image

from codex_image.asset_urls import UnsafeAssetURLError, resolve_asset_destination
from codex_image.http import UrllibTransport
from codex_image.httpx_transport import HttpxTransport
from codex_image.providers.result_assets import AssetLoadError, download_asset_url


class AssetURLSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        image = BytesIO()
        Image.new("RGB", (2, 2), "red").save(image, format="PNG")
        png = image.getvalue()
        self.requests = []
        requests = self.requests

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append((self.path, self.headers.get("Host"), self.headers.get("Authorization")))
                if self.path.startswith("/auth") and not self.headers.get("Authorization"):
                    self.send_response(401)
                    self.end_headers()
                elif self.path in {"/redirect", "/auth-redirect"}:
                    self.send_response(302)
                    self.send_header("Location", f"http://localhost:{self.server.server_port}/private")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(png)))
                    self.end_headers()
                    self.wfile.write(png)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def test_production_transports_reject_indirect_loopback_without_a_request(self):
        for transport in (UrllibTransport(proxy_map={}), HttpxTransport(proxy_map={})):
            for host in ("127.0.0.1", "localhost", "[::1]", "2130706433"):
                with self.subTest(transport=type(transport).__name__, host=host):
                    with self.assertRaises(AssetLoadError):
                        download_asset_url(f"http://{host}:{self.server.server_port}/image", transport=transport,
                                           provider_base_url="https://provider.example/v1", authorization="Bearer synthetic")
        self.assertEqual(self.requests, [])

    def test_explicit_local_provider_works_but_cross_origin_redirect_is_blocked(self):
        for transport in (UrllibTransport(proxy_map={}), HttpxTransport(proxy_map={})):
            with self.subTest(transport=type(transport).__name__):
                self.requests.clear()
                result = download_asset_url(self.base + "/image", transport=transport,
                                            provider_base_url=self.base + "/v1", authorization="Bearer synthetic")
                self.assertEqual((result.width, result.height), (2, 2))
                with self.assertRaises(AssetLoadError):
                    download_asset_url(self.base + "/redirect", transport=transport,
                                       provider_base_url=self.base + "/v1", authorization=None)
                self.assertEqual([item[0] for item in self.requests], ["/image", "/redirect"])
                self.assertTrue(all(item[2] is None for item in self.requests))

    def test_hostname_is_resolved_once_and_request_uses_checked_ip_and_original_host(self):
        original = socket.getaddrinfo
        for transport in (UrllibTransport(proxy_map={}), HttpxTransport(proxy_map={})):
            lookups = []

            def resolve(host, port, *args, **kwargs):
                if host in ("provider.example", b"provider.example"):
                    lookups.append(host)
                    if len(lookups) > 1:
                        raise AssertionError("hostname was resolved again after validation")
                    host = "127.0.0.1"
                return original(host, port, *args, **kwargs)

            url = f"http://provider.example:{self.server.server_port}/image"
            with patch("socket.getaddrinfo", side_effect=resolve):
                download_asset_url(url, transport=transport, provider_base_url=url, authorization=None)
            self.assertEqual(len(lookups), 1)
            self.assertEqual(self.requests[-1][1], f"provider.example:{self.server.server_port}")

    def test_private_special_and_mixed_dns_answers_are_rejected(self):
        for ip in ("10.0.0.1", "169.254.169.254", "0.0.0.0", "100.64.0.1", "224.0.0.1",
                   "::1", "fc00::1", "fe80::1", "::ffff:127.0.0.1", "fec0::1", "64:ff9b::7f00:1"):
            with self.subTest(ip=ip), patch("socket.getaddrinfo", return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 80)),
                (socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 80)),
            ]):
                with self.assertRaises(UnsafeAssetURLError):
                    resolve_asset_destination("http://cdn.example/image", "https://provider.example")

    def test_authenticated_retry_remains_on_provider_origin(self):
        for transport in (UrllibTransport(proxy_map={}), HttpxTransport(proxy_map={})):
            self.requests.clear()
            result = download_asset_url(self.base + "/auth", transport=transport,
                                        provider_base_url=self.base, authorization="Bearer synthetic")
            self.assertEqual(result.width, 2)
            self.assertEqual([item[2] for item in self.requests], [None, "Bearer synthetic"])
            with self.assertRaises(AssetLoadError):
                download_asset_url(self.base + "/auth-redirect", transport=transport,
                                   provider_base_url=self.base, authorization="Bearer synthetic")
            self.assertEqual([item[0] for item in self.requests], ["/auth", "/auth", "/auth-redirect", "/auth-redirect"])

    def test_connection_failure_falls_back_only_to_already_checked_addresses(self):
        original = socket.getaddrinfo
        for transport in (UrllibTransport(timeout=2, proxy_map={}), HttpxTransport(timeout=2, proxy_map={})):
            lookups = []

            def resolve(host, port, *args, **kwargs):
                if host == "provider.example":
                    lookups.append(host)
                    return [*original("127.0.0.2", port, *args, **kwargs), *original("127.0.0.1", port, *args, **kwargs)]
                return original(host, port, *args, **kwargs)

            url = f"http://provider.example:{self.server.server_port}/image"
            with patch("socket.getaddrinfo", side_effect=resolve):
                self.assertEqual(download_asset_url(url, transport=transport, provider_base_url=url, authorization=None).width, 2)
            self.assertEqual(len(lookups), 1)

    def test_http_proxy_receives_pinned_destination_and_original_host(self):
        for transport_class in (UrllibTransport, HttpxTransport):
            transport = transport_class(proxy_map={"http": self.base})
            # No external connection: the synthetic proxy returns the image.
            download_asset_url("http://8.8.8.8:8080/image", transport=transport,
                               provider_base_url="https://provider.example", authorization=None)
            self.assertEqual(self.requests[-1], ("http://8.8.8.8:8080/image", "8.8.8.8:8080", None))

    @unittest.skipUnless(shutil.which("openssl"), "TLS fixture requires openssl")
    def test_pinned_https_keeps_hostname_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "cert.conf"
            config.write_text("[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n[dn]\nCN=asset.test\n[ext]\nsubjectAltName=DNS:asset.test\nbasicConstraints=CA:TRUE\n")
            cert, key = root / "cert.pem", root / "key.pem"
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                            "-config", str(config), "-keyout", str(key), "-out", str(cert)],
                           capture_output=True, check=True, timeout=20)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            server = ThreadingHTTPServer(("127.0.0.1", 0), self.server.RequestHandlerClass)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            original = socket.getaddrinfo

            def resolve(host, port, *args, **kwargs):
                if host in ("asset.test", "wrong.test"):
                    host = "127.0.0.1"
                return original(host, port, *args, **kwargs)

            try:
                with patch("socket.getaddrinfo", side_effect=resolve), patch(
                    "codex_image.http._https_ssl_context", return_value=ssl.create_default_context(cafile=str(cert))
                ), patch("certifi.where", return_value=str(cert)):
                    for transport in (UrllibTransport(proxy_map={}), HttpxTransport(proxy_map={})):
                        url = f"https://asset.test:{server.server_port}/image"
                        self.assertEqual(download_asset_url(url, transport=transport, provider_base_url=url, authorization=None).width, 2)
                        wrong = f"https://wrong.test:{server.server_port}/image"
                        with self.assertRaises(Exception) as caught:
                            download_asset_url(wrong, transport=transport, provider_base_url=wrong, authorization=None)
                        self.assertIn("certificate", str(caught.exception).lower())
            finally:
                server.shutdown()
                server.server_close()
                thread.join(5)
