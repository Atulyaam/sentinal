"""Security regression tests for CORS policies and Origin validation."""

import json
import os
import threading
import unittest
import urllib.error
import urllib.request

from backend.api.server import create_server


class TestCORSSecurity(unittest.TestCase):
    """Rigorous security checks for Cross-Origin Resource Sharing."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = create_server(host="127.0.0.1", port=0)
        cls.host, cls.port = cls.server.server_address
        cls.base_url = f"http://{cls.host}:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2.0)

    def test_allowed_origin_receives_exact_cors_header(self) -> None:
        """Allowed origin must receive exact matching Access-Control-Allow-Origin and Vary: Origin."""
        allowed_origin = "http://127.0.0.1:5173"
        req = urllib.request.Request(
            f"{self.base_url}/health",
            headers={"Origin": allowed_origin}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), allowed_origin)
            self.assertNotEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertEqual(resp.headers.get("Vary"), "Origin")
            self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
            self.assertEqual(resp.headers.get("X-Frame-Options"), "DENY")

    def test_disallowed_origin_receives_no_cors_header(self) -> None:
        """Disallowed/untrusted origin must NEVER receive Access-Control-Allow-Origin header."""
        disallowed_origin = "http://malicious-site.example.com"
        req = urllib.request.Request(
            f"{self.base_url}/health",
            headers={"Origin": disallowed_origin}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            # Crucial check: NO Access-Control-Allow-Origin header sent
            self.assertIsNone(resp.headers.get("Access-Control-Allow-Origin"))

    def test_options_preflight_allowed_origin(self) -> None:
        """OPTIONS preflight from allowed origin returns 204 with correct CORS headers."""
        allowed_origin = "http://localhost:5173"
        req = urllib.request.Request(
            f"{self.base_url}/health",
            headers={"Origin": allowed_origin},
            method="OPTIONS"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), allowed_origin)
            self.assertIn("GET", resp.headers.get("Access-Control-Allow-Methods", ""))
            self.assertIn("OPTIONS", resp.headers.get("Access-Control-Allow-Methods", ""))

    def test_options_preflight_disallowed_origin_returns_403(self) -> None:
        """OPTIONS preflight from disallowed origin is rejected with 403 Forbidden."""
        disallowed_origin = "http://attacker.example.org"
        req = urllib.request.Request(
            f"{self.base_url}/health",
            headers={"Origin": disallowed_origin},
            method="OPTIONS"
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)

        self.assertEqual(ctx.exception.code, 403)
        with ctx.exception:
            self.assertIsNone(ctx.exception.headers.get("Access-Control-Allow-Origin"))
            body = json.loads(ctx.exception.read().decode("utf-8"))
            self.assertEqual(body.get("error"), "Forbidden")

    def test_no_origin_header_receives_no_cors_headers(self) -> None:
        """Direct non-browser or same-origin requests receive no CORS headers."""
        req = urllib.request.Request(f"{self.base_url}/health")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIsNone(resp.headers.get("Access-Control-Allow-Origin"))


if __name__ == "__main__":
    unittest.main()

