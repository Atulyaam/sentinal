"""End-to-End Integration Test for Project Sentinel Detection and Findings Pipeline."""
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


class TestE2EDetection(unittest.TestCase):
    """Verifies end-to-end ingestion, normalization, detection rule evaluation, findings, and lifecycle management."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = str(Path(cls.temp_dir.name) / "test_e2e_detection.db")

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

    def _post(self, path: str, body: dict) -> Tuple[int, dict]:
        data_bytes = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data_bytes,
            headers={"Content-Type": "application/json", "Origin": "http://localhost:5173"},
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
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            headers={"Origin": "http://localhost:5173"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as err:
            raw = err.read().decode("utf-8")
            return err.code, json.loads(raw) if raw else {}

    def _patch(self, path: str, body: dict) -> Tuple[int, dict]:
        data_bytes = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data_bytes,
            headers={"Content-Type": "application/json", "Origin": "http://localhost:5173"},
            method="PATCH",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as err:
            raw = err.read().decode("utf-8")
            return err.code, json.loads(raw) if raw else {}

    def test_complete_detection_and_finding_lifecycle(self) -> None:
        """
        Full lifecycle test:
        1. Ingest auth CSV with 5 failures + 1 success for victim_user.
        2. Normalize records to canonical events.
        3. Run detection engine -> produces AUTH-001 and AUTH-002.
        4. Inspect findings and supporting events.
        5. Update status of AUTH-001 to 'acknowledged'.
        6. Re-run detection -> deduplication suppresses redundant findings.
        """
        # 1. Ingest Auth CSV
        auth_csv = (
            "timestamp,username,auth_result,source_ip,session_id\n"
            "2026-11-09T08:00:00Z,victim_user,FAILURE,198.51.100.22,sess_01\n"
            "2026-11-09T08:01:00Z,victim_user,FAILURE,198.51.100.22,sess_02\n"
            "2026-11-09T08:02:00Z,victim_user,FAILURE,198.51.100.22,sess_03\n"
            "2026-11-09T08:03:00Z,victim_user,FAILURE,198.51.100.22,sess_04\n"
            "2026-11-09T08:04:00Z,victim_user,FAILURE,198.51.100.22,sess_05\n"
            "2026-11-09T08:06:00Z,victim_user,SUCCESS,198.51.100.22,sess_06\n"
        )
        status, import_res = self._post("/api/import", {
            "filename": "auth_bruteforce.csv",
            "content": auth_csv,
            "parser_id": "auth_csv",
            "source_id": "src_manual_default",
        })
        self.assertEqual(status, 200)
        self.assertEqual(import_res["accepted_records"], 6)

        # 2. Normalize records
        status, norm_res = self._post("/api/normalization/run", {})
        self.assertEqual(status, 200)
        self.assertEqual(norm_res["result"]["accepted"], 6)

        # 3. Run Detection Engine
        status, det_res = self._post("/api/detection/run", {})
        self.assertEqual(status, 200)
        self.assertEqual(det_res["status"], "success")
        stats = det_res["result"]
        self.assertEqual(stats["rule_count"], 5)
        self.assertGreaterEqual(stats["events_scanned"], 6)
        self.assertEqual(stats["findings_generated"], 2)  # AUTH-001 and AUTH-002
        self.assertEqual(stats["findings_duplicate"], 0)

        # 4. Query Findings
        status, findings_data = self._get("/api/findings")
        self.assertEqual(status, 200)
        self.assertEqual(findings_data["total"], 2)
        findings = findings_data["findings"]
        rule_map = {f["rule_id"]: f for f in findings}

        # Check AUTH-001
        self.assertIn("AUTH-001", rule_map)
        f_auth001 = rule_map["AUTH-001"]
        self.assertEqual(f_auth001["severity"], "Medium")
        self.assertEqual(f_auth001["status"], "open")
        self.assertEqual(f_auth001["matched_entity"], "victim_user")
        self.assertEqual(len(f_auth001["supporting_event_ids"]), 5)

        # Check AUTH-002
        self.assertIn("AUTH-002", rule_map)
        f_auth002 = rule_map["AUTH-002"]
        self.assertEqual(f_auth002["severity"], "High")
        self.assertEqual(f_auth002["status"], "open")
        self.assertEqual(f_auth002["matched_entity"], "victim_user")
        self.assertEqual(len(f_auth002["supporting_event_ids"]), 6)

        # 5. Fetch Finding Detail with joined supporting events
        auth001_id = f_auth001["finding_id"]
        status, detail = self._get(f"/api/findings/{auth001_id}")
        self.assertEqual(status, 200)
        self.assertEqual(detail["finding_id"], auth001_id)
        self.assertEqual(len(detail["supporting_events"]), 5)
        for ev in detail["supporting_events"]:
            self.assertEqual(ev["user_principal"], "victim_user")
            self.assertEqual(ev["status"], "FAILURE")

        # 6. Update Status to 'acknowledged'
        status, patch_res = self._patch(f"/api/findings/{auth001_id}", {"status": "acknowledged"})
        self.assertEqual(status, 200)
        self.assertEqual(patch_res["status"], "acknowledged")

        # Verify update persisted
        status, detail_after = self._get(f"/api/findings/{auth001_id}")
        self.assertEqual(status, 200)
        self.assertEqual(detail_after["status"], "acknowledged")

        # 7. Re-run Detection Engine to test deduplication
        status, det_res2 = self._post("/api/detection/run", {})
        self.assertEqual(status, 200)
        stats2 = det_res2["result"]
        self.assertEqual(stats2["findings_generated"], 0)
        self.assertEqual(stats2["findings_duplicate"], 2)

        # Status of acknowledged finding was NOT overwritten
        status, detail_final = self._get(f"/api/findings/{auth001_id}")
        self.assertEqual(status, 200)
        self.assertEqual(detail_final["status"], "acknowledged")


if __name__ == "__main__":
    unittest.main()
