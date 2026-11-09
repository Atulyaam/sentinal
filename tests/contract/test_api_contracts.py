"""Contract tests validating schema parity between backend responses and frontend types."""

import json
import threading
import unittest
import urllib.request
from datetime import datetime

from backend.api.server import create_server


class TestAPIContracts(unittest.TestCase):
    """Assert backend endpoints conform to the shared frontend contract definitions."""

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

    def test_health_response_matches_contract(self) -> None:
        """Verify the health response satisfies the BackendHealthResponse TypeScript schema."""
        req = urllib.request.Request(f"{self.base_url}/health")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # Verify required fields
        self.assertIn("app", data)
        self.assertIsInstance(data["app"], str)
        self.assertTrue(len(data["app"]) > 0)

        self.assertIn("status", data)
        self.assertIn(data["status"], ("ok", "degraded", "error"))

        self.assertIn("version", data)
        self.assertIsInstance(data["version"], str)

        # Verify optional fields
        if "timestamp" in data:
            self.assertIsInstance(data["timestamp"], str)
            # Verify ISO-8601 parsing
            datetime.fromisoformat(data["timestamp"])

        if "environment" in data:
            self.assertIsInstance(data["environment"], str)


if __name__ == "__main__":
    unittest.main()
