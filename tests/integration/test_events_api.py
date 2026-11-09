"""Integration tests for Canonical Events and Normalization API Endpoints."""

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


class TestEventsAPI(unittest.TestCase):
    """Integration test suite for /api/events, /api/events/{id}, and /api/normalization/run."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = str(Path(cls.temp_dir.name) / "test_api_events.db")

        os.environ["SENTINEL_DB_PATH"] = cls.db_path
        os.environ["SENTINEL_ALLOWED_ORIGINS"] = "http://localhost:5173"

        handler._repo = None
        handler._norm_engine = None
        handler._engine = None

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

        cls.temp_dir.cleanup()
        os.environ.pop("SENTINEL_DB_PATH", None)
        os.environ.pop("SENTINEL_ALLOWED_ORIGINS", None)

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        headers: dict | None = None,
    ) -> Tuple[int, dict]:
        req_headers = headers or {}
        data_bytes = None
        if body is not None:
            data_bytes = json.dumps(body).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")

        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data_bytes,
            headers=req_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as err:
            raw = err.read().decode("utf-8")
            return err.code, json.loads(raw) if raw else {}

    def test_events_empty_initially(self) -> None:
        """GET /api/events should return empty list and zero total initially."""
        status, data = self._request("GET", "/api/events")
        self.assertEqual(status, 200)
        self.assertEqual(data["events"], [])
        self.assertEqual(data["total"], 0)

    def test_import_and_normalize_workflow(self) -> None:
        """Upload log, trigger normalization run, query normalized event and detail."""
        # 1. Upload valid auth CSV
        csv_payload = (
            "timestamp,username,auth_result,source_ip\n"
            "2026-11-09T08:00:00Z,operator_1,SUCCESS,192.168.1.100\n"
            "2026-11-09T08:05:00Z,unknown_actor,FAILURE,198.51.100.22\n"
        )
        import_body = {
            "filename": "auth_test.csv",
            "content": csv_payload,
            "parser_id": "auth_csv",
            "source_id": "src_manual_default",
        }
        status, import_res = self._request("POST", "/api/import", body=import_body)
        self.assertEqual(status, 200)
        import_id = import_res["import_id"]
        self.assertEqual(import_res["accepted_records"], 2)

        # 2. Trigger normalization run
        status, norm_res = self._request(
            "POST",
            "/api/normalization/run",
            body={"import_id": import_id},
        )
        self.assertEqual(status, 200)
        self.assertEqual(norm_res["status"], "success")
        self.assertEqual(norm_res["result"]["accepted"], 2)
        self.assertEqual(norm_res["result"]["rejected"], 0)

        # 3. Query /api/events
        status, events_res = self._request("GET", "/api/events")
        self.assertEqual(status, 200)
        self.assertEqual(events_res["total"], 2)
        self.assertEqual(len(events_res["events"]), 2)

        event_0 = events_res["events"][0]
        self.assertTrue(event_0["event_id"].startswith("evt_"))
        self.assertIn(event_0["user_principal"], ["operator_1", "unknown_actor"])

        # 4. Filter by status=FAILURE
        status, fail_res = self._request("GET", "/api/events?status=FAILURE")
        self.assertEqual(status, 200)
        self.assertEqual(fail_res["total"], 1)
        self.assertEqual(fail_res["events"][0]["user_principal"], "unknown_actor")

        # 5. Query /api/events/{id}
        event_id = event_0["event_id"]
        status, single_res = self._request("GET", f"/api/events/{event_id}")
        self.assertEqual(status, 200)
        self.assertEqual(single_res["event_id"], event_id)
        self.assertEqual(single_res["source_file"], "auth_test.csv")
        self.assertEqual(single_res["source_type"], "auth_csv")

        # 6. Query nonexistent event
        status, not_found_res = self._request("GET", "/api/events/evt_nonexistent_999999")
        self.assertEqual(status, 404)

        # 7. Query /api/normalization/stats
        status, stats_res = self._request("GET", "/api/normalization/stats")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(stats_res["total_normalized_events"], 2)
        self.assertEqual(stats_res["pending_unnormalized_records"], 0)


if __name__ == "__main__":
    unittest.main()
