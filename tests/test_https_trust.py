import os
import ssl
import socket
import subprocess
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import certifi

from codex_image.http import _https_ssl_context


class HTTPSTrustTests(TestCase):
    def tearDown(self):
        _https_ssl_context.cache_clear()

    def test_default_context_verifies_certificates_and_hostnames(self):
        _https_ssl_context.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            context = _https_ssl_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertGreater(context.cert_store_stats()["x509_ca"], 0)

    def test_explicit_ca_file_is_still_honored(self):
        _https_ssl_context.cache_clear()
        with patch.dict(os.environ, {"SSL_CERT_FILE": certifi.where()}, clear=True), \
                patch("ssl.create_default_context", wraps=ssl.create_default_context) as create:
            context = _https_ssl_context()
        create.assert_called_once_with()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_local_tls_rejects_untrusted_and_wrong_hostname_but_accepts_explicit_ca(self):
        with TemporaryDirectory() as directory:
            cert, key = Path(directory) / "cert.pem", Path(directory) / "key.pem"
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                            "-keyout", str(key), "-out", str(cert), "-days", "1",
                            "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost"],
                           check=True, capture_output=True)
            server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_context.load_cert_chain(cert, key)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen()
                listener.settimeout(10)

                def serve():
                    for _ in range(3):
                        connection, _ = listener.accept()
                        try:
                            with server_context.wrap_socket(connection, server_side=True):
                                pass
                        except ssl.SSLError:
                            connection.close()

                thread = threading.Thread(target=serve, daemon=True)
                thread.start()
                for ca, hostname, succeeds in ((None, "localhost", False),
                                               (str(cert), "localhost", True),
                                               (str(cert), "wrong.invalid", False)):
                    _https_ssl_context.cache_clear()
                    with patch.dict(os.environ, {"SSL_CERT_FILE": ca} if ca else {}, clear=True):
                        context = _https_ssl_context()
                    with socket.create_connection(listener.getsockname(), timeout=5) as connection:
                        if succeeds:
                            with context.wrap_socket(connection, server_hostname=hostname):
                                pass
                        else:
                            with self.assertRaises(ssl.SSLCertVerificationError):
                                context.wrap_socket(connection, server_hostname=hostname)
                thread.join(timeout=10)
                self.assertFalse(thread.is_alive())
