"""Integration tests for Detection Engine and Findings API Endpoints."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Tuple

from backend.api import handler
from backend.api.server import create_server


class TestFindingsAPI(unittest.TestCase):
    """Integration test suite for /api/rules, /api/findings, /api/detection/run, and /api/detection/stats."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = str(Path(cls.temp_dir.name) / "test_api_findings.db")

        os.environ["SENTINEL_DB_PATH"] = cls.db_path
        os.environ["SENTINEL_ALLOWED_ORIGINS"] = "http://localhost:5173"

        handler._repo = None
        handler._norm_engine = None
        handler._engine = None
        handler._detection_engine = None

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

        if handler._repo and handler._repo.conn:
            handler._repo.conn.close()
            handler._repo = None
            handler._engine = None
            handler._norm_engine = None
            handler._detection_engine = None

        cls.temp_dir.cleanup()
        os.environ.pop("SENTINEL_DB_PATH", None)
        os.environ.pop("SENTINEL_ALLOWED_ORIGINS", None)

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        headers: dict | None = None,
    ) -> Tuple[int, dict, dict]:
        url = f"{self.base_url}{path}"
        req_headers = {"Origin": "http://localhost:5173"}
        if headers:
            req_headers.update(headers)

        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                resp_body = resp.read().decode("utf-8")
                parsed = json.loads(resp_body) if resp_body else {}
                return resp.status, parsed, dict(resp.headers)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            parsed = json.loads(err_body) if err_body else {}
            return e.code, parsed, dict(e.headers)

    def test_get_detection_rules_list(self) -> None:
        """GET /api/rules returns all registered detection rules."""
        status, data, _ = self._request("GET", "/api/rules")
        self.assertEqual(status, 200)
        self.assertIn("rules", data)
        self.assertEqual(len(data["rules"]), 5)
        rule_ids = [r["rule_id"] for r in data["rules"]]
        self.assertIn("AUTH-001", rule_ids)
        self.assertIn("WEB-001", rule_ids)

    def test_get_single_rule_success_and_404(self) -> None:
        """GET /api/rules/{id} returns rule details or 404 for unknown rule."""
        status, data, _ = self._request("GET", "/api/rules/AUTH-001")
        self.assertEqual(status, 200)
        self.assertEqual(data["rule_id"], "AUTH-001")
        self.assertIn("threshold_count", data["config"])

        # Unknown rule returns 404
        status_404, err_data, _ = self._request("GET", "/api/rules/NONEXISTENT-999")
        self.assertEqual(status_404, 404)
        self.assertIn("error", err_data)

    def test_patch_rule_toggle_enabled(self) -> None:
        """PATCH /api/rules/{id} toggles rule enabled state."""
        # Disable AUTH-001
        status, data, _ = self._request("PATCH", "/api/rules/AUTH-001", body={"enabled": False})
        self.assertEqual(status, 200)
        self.assertEqual(data["rule_id"], "AUTH-001")
        self.assertFalse(data["enabled"])

        # Re-enable AUTH-001
        status, data, _ = self._request("PATCH", "/api/rules/AUTH-001", body={"enabled": True})
        self.assertEqual(status, 200)
        self.assertTrue(data["enabled"])

        # Non-existent rule returns 404
        status_404, _, _ = self._request("PATCH", "/api/rules/NONEXISTENT-999", body={"enabled": False})
        self.assertEqual(status_404, 404)

    def test_detection_run_and_stats(self) -> None:
        """POST /api/detection/run executes engine and GET /api/detection/stats returns metrics."""
        # Execute detection run
        status, run_data, _ = self._request("POST", "/api/detection/run")
        self.assertEqual(status, 200)
        self.assertEqual(run_data["status"], "success")
        self.assertIn("result", run_data)
        self.assertIn("evaluation_id", run_data["result"])
        self.assertEqual(run_data["result"]["rule_count"], 5)

        # Query detection stats
        status, stats, _ = self._request("GET", "/api/detection/stats")
        self.assertEqual(status, 200)
        self.assertIn("total_findings", stats)
        self.assertIn("findings_by_severity", stats)
        self.assertIn("findings_by_status", stats)
        self.assertIn("last_evaluation", stats)

    def test_findings_list_and_filter(self) -> None:
        """GET /api/findings returns paginated findings list."""
        status, data, _ = self._request("GET", "/api/findings?limit=10&offset=0")
        self.assertEqual(status, 200)
        self.assertIn("findings", data)
        self.assertIn("total", data)
        self.assertIn("limit", data)
        self.assertIn("offset", data)

    def test_patch_finding_status_and_validation(self) -> None:
        """PATCH /api/findings/{id} validates status updates and returns 400 on invalid status."""
        # First test invalid status validation on dummy ID
        status, data, _ = self._request("PATCH", "/api/findings/find_dummy_123", body={"status": "invalid_status"})
        self.assertEqual(status, 400)
        self.assertIn("error", data)

        # Test non-existent finding returns 404
        status, data, _ = self._request("PATCH", "/api/findings/find_nonexistent_999", body={"status": "acknowledged"})
        self.assertEqual(status, 404)
        self.assertIn("error", data)


if __name__ == "__main__":
    unittest.main()
