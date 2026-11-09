"""Integration tests for Replay Lab REST API endpoints."""
from __future__ import annotations

import gc
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Dict, Optional
import unittest
import urllib.error
import urllib.request

from backend.api import handler
from backend.api.server import create_server
from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository


class TestReplayAPI(unittest.TestCase):
    """Integration test suite for /api/replay/* endpoints."""

    saved_run_a1: str = ""
    saved_what_if_run: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = str(Path(cls.temp_dir.name) / "test_api_replay.db")
        os.environ["SENTINEL_DB_PATH"] = cls.db_path
        os.environ["SENTINEL_ALLOWED_ORIGINS"] = "http://localhost:5173"

        # Reset handler singletons
        handler._repo = None
        handler._norm_engine = None
        handler._engine = None
        handler._detection_engine = None
        handler._correlation_engine = None
        handler._claim_engine = None
        handler._replay_engine = None

        cls.conn = get_connection(cls.db_path)
        apply_migrations(cls.conn)
        cls.repo = IngestionRepository(cls.conn)

        # Start Test HTTP Server
        cls.server = create_server(host="127.0.0.1", port=0)
        cls.host, cls.port = cls.server.server_address
        cls.base_url = f"http://{cls.host}:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2.0)

        # Close all SQLite connections to allow clean directory removal on Windows
        if hasattr(cls, "conn"):
            cls.conn.close()
        if hasattr(cls, "repo") and hasattr(cls.repo, "conn"):
            try:
                cls.repo.conn.close()
            except Exception:
                pass

        handler._repo = None
        handler._replay_engine = None
        gc.collect()

        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
    ) -> tuple[int, Dict[str, Any]]:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_data = resp.read().decode("utf-8")
                return resp.status, json.loads(resp_data) if resp_data else {}
        except urllib.error.HTTPError as e:
            resp_data = e.read().decode("utf-8")
            try:
                err_json = json.loads(resp_data)
            except Exception:
                err_json = {"raw": resp_data}
            return e.code, err_json

    def test_01_list_scenarios(self) -> None:
        """GET /api/replay/scenarios returns all 3 approved scenario manifests."""
        status, body = self._request("GET", "/api/replay/scenarios")
        self.assertEqual(status, 200)
        self.assertIn("scenarios", body)
        self.assertEqual(len(body["scenarios"]), 3)

        ids = [s["scenario_id"] for s in body["scenarios"]]
        self.assertIn("SCN-AUTH-BURST", ids)
        self.assertIn("SCN-WEB-PROBE", ids)
        self.assertIn("SCN-PRIV-ESC", ids)

    def test_02_get_scenario_details(self) -> None:
        """GET /api/replay/scenarios/{id} retrieves specific scenario manifests."""
        # 1. Existing scenario
        status, body = self._request("GET", "/api/replay/scenarios/SCN-AUTH-BURST")
        self.assertEqual(status, 200)
        scenario = body.get("scenario", {})
        self.assertEqual(scenario["scenario_id"], "SCN-AUTH-BURST")
        self.assertEqual(scenario["category"], "Authentication Security")
        self.assertGreater(len(scenario["fixtures"]), 0)
        self.assertGreater(len(scenario["supported_what_ifs"]), 0)

        # 2. Non-existent scenario
        status_404, body_404 = self._request("GET", "/api/replay/scenarios/SCN-UNKNOWN")
        self.assertEqual(status_404, 404)
        self.assertIn("error", body_404)

    def test_03_run_scenario_success(self) -> None:
        """POST /api/replay/run executes Scenario A and returns complete report."""
        payload = {"scenario_id": "SCN-AUTH-BURST"}
        status, body = self._request("POST", "/api/replay/run", payload)
        self.assertEqual(status, 200)
        run = body.get("run", {})
        self.assertTrue(run["replay_id"].startswith("rply_"))
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["scenario_id"], "SCN-AUTH-BURST")
        self.assertEqual(run["mode"], "standard")

        # Verify metrics
        m = run["metrics"]
        self.assertEqual(m["imported_records"], 6)
        self.assertEqual(m["findings_count"], 2)
        self.assertEqual(m["cases_count"], 1)
        self.assertEqual(m["assertions_failed"], 0)

        # Save replay_id for later retrieval/comparison tests
        TestReplayAPI.saved_run_a1 = run["replay_id"]

    def test_04_run_what_if_scenario(self) -> None:
        """POST /api/replay/run with what-if config returns simulation with diff."""
        payload = {
            "scenario_id": "SCN-AUTH-BURST",
            "what_if": {
                "what_if_id": "WIF-THRESHOLD-10",
                "name": "Higher Threshold",
                "description": "Increase threshold to 10 failures",
                "rule_overrides": {"AUTH-001": {"threshold_count": 10}},
            },
        }
        status, body = self._request("POST", "/api/replay/run", payload)
        self.assertEqual(status, 200)
        run = body.get("run", {})
        self.assertEqual(run["mode"], "what_if")
        self.assertIn("what_if_diff", run)
        self.assertIsNotNone(run["what_if_diff"])

        diff = run["what_if_diff"]
        self.assertIn("AUTH-001", diff["findings_removed"])
        self.assertEqual(diff["metric_deltas"]["findings_count"], -1)

        TestReplayAPI.saved_what_if_run = run["replay_id"]

    def test_05_run_invalid_requests(self) -> None:
        """POST /api/replay/run validates payload and handles errors cleanly."""
        # 1. Missing scenario_id
        status, body = self._request("POST", "/api/replay/run", {})
        self.assertEqual(status, 400)
        self.assertIn("error", body)

        # 2. Non-existent scenario
        status_404, body_404 = self._request("POST", "/api/replay/run", {"scenario_id": "SCN-DOES-NOT-EXIST"})
        self.assertEqual(status_404, 404)

    def test_06_list_runs(self) -> None:
        """GET /api/replay/runs lists historical runs stored in the repository."""
        status, body = self._request("GET", "/api/replay/runs")
        self.assertEqual(status, 200)
        self.assertIn("runs", body)
        self.assertGreaterEqual(len(body["runs"]), 2)

        run_ids = [r["replay_id"] for r in body["runs"]]
        self.assertIn(self.saved_run_a1, run_ids)
        self.assertIn(self.saved_what_if_run, run_ids)

    def test_07_get_run_by_id(self) -> None:
        """GET /api/replay/runs/{id} returns the full run report or 404."""
        # 1. Existing run
        status, body = self._request("GET", f"/api/replay/runs/{self.saved_run_a1}")
        self.assertEqual(status, 200)
        run = body.get("run", {})
        self.assertEqual(run["replay_id"], self.saved_run_a1)
        self.assertIn("assertion_results", run)
        self.assertIn("stages", run)
        self.assertIn("cases_snapshot", run)

        # 2. Non-existent run
        status_404, _ = self._request("GET", "/api/replay/runs/rply_nonexistent_999")
        self.assertEqual(status_404, 404)

    def test_08_compare_runs(self) -> None:
        """POST /api/replay/compare computes semantic comparison between two runs."""
        # Run a second baseline identical to run_a1
        _, body_a2 = self._request("POST", "/api/replay/run", {"scenario_id": "SCN-AUTH-BURST"})
        run_a2_id = body_a2["run"]["replay_id"]

        # 1. Compare identical runs
        status, resp_identical = self._request(
            "POST",
            "/api/replay/compare",
            {"run_a_id": self.saved_run_a1, "run_b_id": run_a2_id},
        )
        self.assertEqual(status, 200)
        diff_identical = resp_identical.get("comparison", {})
        self.assertTrue(diff_identical["is_identical"])
        for val in diff_identical["metric_deltas"].values():
            self.assertEqual(val, 0)

        # 2. Compare baseline with what-if run
        status_diff, resp_whatif = self._request(
            "POST",
            "/api/replay/compare",
            {"run_a_id": self.saved_run_a1, "run_b_id": self.saved_what_if_run},
        )
        self.assertEqual(status_diff, 200)
        diff_whatif = resp_whatif.get("comparison", {})
        self.assertFalse(diff_whatif["is_identical"])
        self.assertEqual(diff_whatif["metric_deltas"]["findings_count"], -1)

    def test_09_reset_runs(self) -> None:
        """POST /api/replay/reset safely cleans up historical replay run records."""
        status, body = self._request("POST", "/api/replay/reset")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "success")
        self.assertGreater(body["deleted_count"], 0)

        # Verify subsequent list is empty
        status_list, body_list = self._request("GET", "/api/replay/runs")
        self.assertEqual(status_list, 200)
        self.assertEqual(len(body_list["runs"]), 0)


if __name__ == "__main__":
    unittest.main()
