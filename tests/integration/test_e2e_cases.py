"""End-to-End Investigation Lifecycle Integration Test (Phase 5)."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from backend.api import handler
from backend.api.server import create_server
from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository


class TestE2ECases(unittest.TestCase):
    """
    End-to-end lifecycle test covering:
    Ingestion -> Normalization -> Detection -> Case Correlation ->
    Timeline Verification -> Review Actions -> Re-correlation Idempotency -> Benign Lookalike Isolation.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = str(Path(cls.temp_dir.name) / "test_e2e_cases.db")
        os.environ["SENTINEL_DB_PATH"] = cls.db_path
        os.environ["SENTINEL_ALLOWED_ORIGINS"] = "http://localhost:5173"

        handler._repo = None
        handler._norm_engine = None
        handler._engine = None
        handler._detection_engine = None
        handler._correlation_engine = None

        conn = get_connection(cls.db_path)
        apply_migrations(conn)

        cls.server = create_server(host="127.0.0.1", port=0)
        cls.host, cls.port = cls.server.server_address
        cls.base_url = f"http://{cls.host}:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2.0)
        if handler._repo and handler._repo.conn:
            try:
                handler._repo.conn.close()
            except Exception:
                pass
        handler._repo = None
        handler._engine = None
        handler._norm_engine = None
        handler._detection_engine = None
        handler._correlation_engine = None
        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def _post_multipart(self, filename: str, content: str, parser_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/import"
        boundary = "----SentinelE2ECasesBoundary"
        body_parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"parser_id\"\r\n\r\n{parser_id}\r\n",
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: text/plain\r\n\r\n{content}\r\n",
            f"--{boundary}--\r\n",
        ]
        body = "".join(body_parts).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _get_json(self, path: str) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_complete_investigation_lifecycle(self) -> None:
        """
        Step 1: Ingest authentication failure burst + success for target user 'mallory'.
        Step 2: Run canonical normalization.
        Step 3: Run deterministic detection engine -> emit AUTH-001 and AUTH-002 findings.
        Step 4: Run correlation engine -> assemble investigation case.
        Step 5: Verify case structure, derived severity, and evidence timeline.
        Step 6: Add operator note and update status to 'UnderReview'.
        Step 7: Re-run correlation -> confirm idempotency and zero duplicate cases.
        Step 8: Ingest benign dataset -> confirm no unrelated case is created.
        """
        # Step 1: Ingest authentication log for mallory (5 failures + 1 success within 10 minutes)
        auth_lines = [
            "timestamp,user,ip,status",
            "2026-11-09T08:00:00Z,mallory,198.51.100.20,FAILURE",
            "2026-11-09T08:01:00Z,mallory,198.51.100.20,FAILURE",
            "2026-11-09T08:02:00Z,mallory,198.51.100.20,FAILURE",
            "2026-11-09T08:03:00Z,mallory,198.51.100.20,FAILURE",
            "2026-11-09T08:04:00Z,mallory,198.51.100.20,FAILURE",
            "2026-11-09T08:06:00Z,mallory,198.51.100.20,SUCCESS",
        ]
        import_res = self._post_multipart("auth_mallory.csv", "\n".join(auth_lines), "auth_csv")
        self.assertEqual(import_res["status"], "completed")
        self.assertEqual(import_res["accepted_records"], 6)

        # Step 2: Run normalization
        norm_res = self._post_json("/api/normalization/run", {"limit": 500})
        self.assertEqual(norm_res["status"], "success")
        self.assertEqual(norm_res["result"]["accepted"], 6)

        # Step 3: Run detection engine
        det_res = self._post_json("/api/detection/run", {"limit_events": 500})
        self.assertEqual(det_res["status"], "success")
        # Both AUTH-001 (5 failures) and AUTH-002 (failures + success) must trigger
        self.assertEqual(det_res["result"]["findings_generated"], 2)

        # Step 4: Run correlation engine
        corr_res = self._post_json("/api/cases/correlate", {"limit_findings": 500})
        self.assertEqual(corr_res["status"], "success")
        self.assertEqual(corr_res["result"]["cases_created"], 1)

        # Step 5: Query case detail
        cases_list = self._get_json("/api/cases")
        self.assertEqual(cases_list["total"], 1)
        case_summary = cases_list["cases"][0]
        self.assertEqual(case_summary["correlation_key_type"], "user_principal")
        self.assertEqual(case_summary["correlation_key_value"], "mallory")
        self.assertEqual(case_summary["severity"], "High")  # Derived from AUTH-002 (High)
        self.assertEqual(case_summary["finding_count"], 2)
        self.assertEqual(case_summary["event_count"], 6)

        case_id = case_summary["case_id"]
        detail = self._get_json(f"/api/cases/{case_id}")
        self.assertEqual(detail["status"], "Open")

        # Verify timeline items
        timeline = detail["timeline"]
        item_types = [item["item_type"] for item in timeline]
        self.assertIn("event", item_types)
        self.assertIn("finding", item_types)
        self.assertIn("correlation", item_types)

        # Step 6: Operator triage - add note & update status
        review_res = self._post_json(f"/api/cases/{case_id}/review", {
            "note": "Credential burst confirmed from non-standard IP. Escalating to incident triage.",
            "status": "UnderReview",
            "author": "analyst_sarah",
        })
        self.assertEqual(review_res["status"], "success")
        self.assertEqual(review_res["case"]["status"], "UnderReview")
        self.assertEqual(len(review_res["case"]["review_actions"]), 1)

        # Step 7: Re-run correlation engine - verify idempotency
        corr_res_2 = self._post_json("/api/cases/correlate", {"limit_findings": 500})
        self.assertEqual(corr_res_2["status"], "success")
        self.assertEqual(corr_res_2["result"]["cases_created"], 0)
        self.assertEqual(corr_res_2["result"]["cases_updated"], 1)

        # Verify case status and review history were preserved
        detail_after = self._get_json(f"/api/cases/{case_id}")
        self.assertEqual(detail_after["status"], "UnderReview")
        self.assertEqual(len(detail_after["review_actions"]), 1)

        # Step 8: Ingest benign lookalike data (single isolated failure for benign user 'sam')
        benign_lines = [
            "timestamp,user,ip,status",
            "2026-11-09T09:00:00Z,sam,198.51.100.50,FAILURE",
            "2026-11-09T09:01:00Z,sam,198.51.100.50,SUCCESS",
        ]
        self._post_multipart("auth_benign.csv", "\n".join(benign_lines), "auth_csv")
        self._post_json("/api/normalization/run", {"limit": 500})
        det_res_benign = self._post_json("/api/detection/run", {"limit_events": 500})
        # Benign records do not meet 5 failures threshold, so 0 findings generated
        self.assertEqual(det_res_benign["result"]["findings_generated"], 0)

        # Re-running correlation does not create any case for sam
        corr_res_3 = self._post_json("/api/cases/correlate", {"limit_findings": 500})
        self.assertEqual(corr_res_3["result"]["cases_created"], 0)
        cases_list_final = self._get_json("/api/cases")
        self.assertEqual(cases_list_final["total"], 1)


if __name__ == "__main__":
    unittest.main()
