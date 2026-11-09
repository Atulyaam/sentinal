"""Unit tests for Sentinel Health Endpoint and HTTP Request Handler."""

import json
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime

from backend.api.server import create_server


class TestHealthEndpoint(unittest.TestCase):
    """Test suite for /health, /api/health, CORS, and error handling."""

    @classmethod
    def setUpClass(cls) -> None:
        """Start an ephemeral test server on an OS-assigned port (port 0)."""
        cls.server = create_server(host="127.0.0.1", port=0)
        cls.host, cls.port = cls.server.server_address
        cls.base_url = f"http://{cls.host}:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        """Shutdown the test server cleanly."""
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2.0)

    def test_health_endpoint_ok(self) -> None:
        """Verify GET /health returns 200 OK and valid schema."""
        req = urllib.request.Request(
            f"{self.base_url}/health",
            headers={"Origin": "http://127.0.0.1:5173"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("application/json", resp.headers.get("Content-Type", ""))
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "http://127.0.0.1:5173")
            self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")

            body = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(body.get("app"), "Project Sentinel")
            self.assertEqual(body.get("status"), "ok")
            self.assertIn(body.get("version"), ("0.1.0", "0.2.0"))
            self.assertIn("timestamp", body)

            # Assert timestamp parses as valid ISO-8601
            parsed_time = datetime.fromisoformat(body["timestamp"])
            self.assertIsNotNone(parsed_time)

    def test_api_health_alias(self) -> None:
        """Verify GET /api/health alias functions identically."""
        req = urllib.request.Request(f"{self.base_url}/api/health")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(body.get("status"), "ok")
            self.assertEqual(body.get("app"), "Project Sentinel")

    def test_cors_options_preflight(self) -> None:
        """Verify OPTIONS request returns 204 with exact CORS headers."""
        allowed_origin = "http://127.0.0.1:5173"
        req = urllib.request.Request(
            f"{self.base_url}/health",
            headers={"Origin": allowed_origin},
            method="OPTIONS"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), allowed_origin)
            self.assertIn("GET", resp.headers.get("Access-Control-Allow-Methods", ""))

    def test_unknown_route_returns_404(self) -> None:
        """Verify unknown path returns structured 404 JSON response."""
        req = urllib.request.Request(f"{self.base_url}/nonexistent-path")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        
        self.assertEqual(ctx.exception.code, 404)
        with ctx.exception:
            error_body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertEqual(error_body.get("status"), 404)
        self.assertEqual(error_body.get("error"), "Not Found")
        self.assertEqual(error_body.get("path"), "/nonexistent-path")


if __name__ == "__main__":
    unittest.main()
