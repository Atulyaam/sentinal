"""End-to-End Integration Test for Project Sentinel Normalization Pipeline."""

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


class TestE2ENormalization(unittest.TestCase):
    """Verifies complete end-to-end multi-format ingestion, normalization, and provenance cycle."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = str(Path(cls.temp_dir.name) / "test_e2e_norm.db")

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

    def _post(self, path: str, body: dict) -> Tuple[int, dict]:
        data_bytes = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as err:
            raw = err.read().decode("utf-8")
            return err.code, json.loads(raw) if raw else {}

    def _get(self, path: str) -> Tuple[int, dict]:
        req = urllib.request.Request(f"{self.base_url}{path}", method="GET")
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as err:
            raw = err.read().decode("utf-8")
            return err.code, json.loads(raw) if raw else {}

    def test_multi_format_normalization_pipeline(self) -> None:
        """Upload web access CSV and JSONL files, normalize both, and verify cross-source event querying."""
        # 1. Ingest Web Access CSV
        web_csv = (
            "timestamp,http_method,request_path,status_code,source_ip\n"
            "2026-11-09T08:00:00Z,GET,/api/v1/health,200,10.0.0.1\n"
            "2026-11-09T08:00:05Z,POST,/api/v1/auth,401,10.0.0.2\n"
            "2026-11-09T08:00:10Z,GET,/api/v1/crash,500,10.0.0.3\n"
        )
        status, web_res = self._post("/api/import", {
            "filename": "web_audit.csv",
            "content": web_csv,
            "parser_id": "web_access_csv",
            "source_id": "src_manual_default",
        })
        self.assertEqual(status, 200)
        web_import_id = web_res["import_id"]

        # 2. Ingest JSONL with 1 valid and 1 naive timestamp record
        jsonl_content = (
            '{"timestamp": "2026-11-09T08:05:00Z", "event_type": "vpn_login", "user": "alice", "ip": "172.16.0.5"}\n'
            '{"timestamp": "2026-11-09 08:06:00", "event_type": "vpn_disconnect", "user": "alice", "ip": "172.16.0.5"}\n'
        )
        status, jsonl_res = self._post("/api/import", {
            "filename": "vpn.jsonl",
            "content": jsonl_content,
            "parser_id": "generic_jsonl",
            "source_id": "src_manual_default",
        })
        self.assertEqual(status, 200)
        jsonl_import_id = jsonl_res["import_id"]

        # 3. Check unnormalized stats prior to running normalization
        status, stats_before = self._get("/api/normalization/stats")
        self.assertEqual(status, 200)
        self.assertEqual(stats_before["pending_unnormalized_records"], 5)
        self.assertEqual(stats_before["total_normalized_events"], 0)

        # 4. Run Normalization
        status, run_res = self._post("/api/normalization/run", {})
        self.assertEqual(status, 200)
        self.assertEqual(run_res["result"]["accepted"], 5)
        self.assertEqual(run_res["result"]["rejected"], 0)

        # 5. Check stats after normalization
        status, stats_after = self._get("/api/normalization/stats")
        self.assertEqual(status, 200)
        self.assertEqual(stats_after["pending_unnormalized_records"], 0)
        self.assertEqual(stats_after["total_normalized_events"], 5)
        self.assertEqual(stats_after["events_by_type"]["web_request"], 3)
        self.assertEqual(stats_after["events_by_type"]["vpn_login"], 1)
        self.assertEqual(stats_after["events_by_type"]["vpn_disconnect"], 1)

        # 6. Verify Naive timestamp annotation in event attributes
        status, evts = self._get("/api/events?event_type=vpn_disconnect")
        self.assertEqual(status, 200)
        self.assertEqual(evts["total"], 1)
        vpn_evt = evts["events"][0]
        self.assertEqual(vpn_evt["timestamp"], "2026-11-09T08:06:00Z")
        self.assertEqual(vpn_evt["attributes"]["__provenance"]["timezone_inferred"], "UTC_ASSUMED")

        # 7. Verify Web status classification (SUCCESS, FAILURE, ERROR)
        status, web_evts = self._get(f"/api/events?import_id={web_import_id}")
        self.assertEqual(status, 200)
        self.assertEqual(web_evts["total"], 3)
        statuses = {e["target_resource"]: e["status"] for e in web_evts["events"]}
        self.assertEqual(statuses["/api/v1/health"], "SUCCESS")
        self.assertEqual(statuses["/api/v1/auth"], "FAILURE")
        self.assertEqual(statuses["/api/v1/crash"], "ERROR")

        # 8. Reprocessing idempotency test: running normalization again accepts 0 and creates no duplicates
        status, rerun_res = self._post("/api/normalization/run", {})
        self.assertEqual(status, 200)
        self.assertEqual(rerun_res["result"]["total_fetched"], 0)

        status, final_evts = self._get("/api/events")
        self.assertEqual(status, 200)
        self.assertEqual(final_evts["total"], 5)


if __name__ == "__main__":
    unittest.main()

