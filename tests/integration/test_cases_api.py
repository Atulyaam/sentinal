"""Integration tests for Investigation Cases REST API Endpoints."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from backend.api import handler
from backend.api.server import create_server
from backend.cases.models import Case, CaseEvent, CaseFinding
from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository


class TestCasesAPI(unittest.TestCase):
    """Integration test suite for /api/cases endpoints."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = str(Path(cls.temp_dir.name) / "test_api_cases.db")
        os.environ["SENTINEL_DB_PATH"] = cls.db_path
        os.environ["SENTINEL_ALLOWED_ORIGINS"] = "http://localhost:5173"

        handler._repo = None
        handler._norm_engine = None
        handler._engine = None
        handler._detection_engine = None
        handler._correlation_engine = None

        conn = get_connection(cls.db_path)
        apply_migrations(conn)
        cls.repo = IngestionRepository(conn)

        # Baseline source and import
        cls.repo.get_or_create_source("src_api_cases", "API Case Source", "auth_csv")
        cls.repo.create_import_job(
            import_id="imp_api_cases",
            source_id="src_api_cases",
            filename="auth.log",
            sha256="e" * 64,
            file_size=1024,
            parser_id="auth_csv",
            parser_version="1.0.0",
            status="completed",
        )
        cls.repo.persist_import_batch(
            import_id="imp_api_cases",
            status="completed",
            total_records=1,
            accepted_records=1,
            rejected_records=0,
            records=[
                {
                    "record_number": 1,
                    "parser_id": "auth_csv",
                    "parser_version": "1.0.0",
                    "record": {"line_number": 1, "timestamp": "2026-11-09T08:00:00Z", "event_type": "user_authentication", "attributes": {}, "raw_payload": "{}"},
                }
            ],
            errors=[],
        )
        unnorm = cls.repo.get_unnormalized_records(import_id="imp_api_cases")
        rec_id = unnorm[0]["record_id"]

        cls.event_id = "evt_api_case_01"
        cls.repo.persist_normalized_events_batch(
            events=[
                {
                    "event_id": cls.event_id,
                    "import_id": "imp_api_cases",
                    "record_id": rec_id,
                    "source_id": "src_api_cases",
                    "record_number": 1,
                    "timestamp": "2026-11-09T08:00:00Z",
                    "source_type": "auth_csv",
                    "source_file": "auth.log",
                    "source_line": 1,
                    "source_sha256": "e" * 64,
                    "event_type": "user_authentication",
                    "user_principal": "eve",
                    "source_ip": "10.0.0.9",
                    "target_resource": "/login",
                    "status": "FAILURE",
                    "attributes_json": "{}",
                }
            ],
            errors=[],
        )

        cls.finding_id = "find_api_case_01"
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO findings (
                finding_id, rule_id, rule_version, rule_config_hash,
                severity, status, title, description,
                first_observed_at, last_observed_at, matched_entity,
                matched_conditions_json, supporting_event_ids_json,
                limitations, dedupe_key, created_at, updated_at
            ) VALUES (?, 'AUTH-001', '1.0.0', 'hash_api', 'High', 'open', 'API Test Finding', 'desc', ?, ?, 'eve', '{}', ?, 'none', 'key_api_1', ?, ?);
            """,
            (cls.finding_id, now, now, f'["{cls.event_id}"]', now, now),
        )
        conn.commit()

        # Seed 1 initial case
        c = Case(
            case_id="case_api_seed_01",
            title="Eve Investigation Case",
            description="Case for Eve",
            status="Open",
            severity="High",
            correlation_key_type="user_principal",
            correlation_key_value="eve",
            first_observed_at="2026-11-09T08:00:00Z",
            last_observed_at="2026-11-09T08:00:00Z",
            dedupe_key="user_principal:eve:500",
            metadata={"correlation_rationale": "Grouped under eve"},
        )
        cf = CaseFinding(case_id="case_api_seed_01", finding_id=cls.finding_id, correlation_rationale="Linked finding")
        ce = CaseEvent(case_id="case_api_seed_01", event_id=cls.event_id, relationship_type="evidence", correlation_rationale="Evt")
        cls.repo.persist_cases_batch([c], [cf], [ce])

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
        if hasattr(cls, "repo") and cls.repo and cls.repo.conn:
            cls.repo.conn.close()
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

    def _get(self, path: str) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _patch(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "Accept": "application/json"}, method="PATCH")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_list_cases_and_stats_endpoints(self) -> None:
        """GET /api/cases and GET /api/cases/stats return valid case metadata and aggregate counts."""
        # Stats
        stats = self._get("/api/cases/stats")
        self.assertIn("total_cases", stats)
        self.assertGreaterEqual(stats["total_cases"], 1)

        # List
        data = self._get("/api/cases?limit=10&offset=0")
        self.assertIn("cases", data)
        self.assertIn("total", data)
        self.assertGreaterEqual(len(data["cases"]), 1)
        c0 = data["cases"][0]
        self.assertEqual(c0["case_id"], "case_api_seed_01")
        self.assertEqual(c0["severity"], "High")

    def test_get_case_detail_endpoint(self) -> None:
        """GET /api/cases/{id} returns complete case detail with timeline, findings, and events."""
        case_data = self._get("/api/cases/case_api_seed_01")
        self.assertEqual(case_data["case_id"], "case_api_seed_01")
        self.assertEqual(case_data["status"], "Open")
        self.assertIn("timeline", case_data)
        self.assertIn("findings", case_data)
        self.assertIn("events", case_data)
        self.assertEqual(len(case_data["findings"]), 1)
        self.assertEqual(len(case_data["events"]), 1)

    def test_patch_case_status_valid_and_invalid(self) -> None:
        """PATCH /api/cases/{id} validates allowed transitions and rejects invalid targets."""
        # 1. Valid transition Open -> UnderReview
        res = self._patch("/api/cases/case_api_seed_01", {"status": "UnderReview", "note": "Analyst triage started"})
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["case"]["status"], "UnderReview")

        # 2. Invalid target status string returns 400
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._patch("/api/cases/case_api_seed_01", {"status": "FakeStatus"})
        self.assertEqual(ctx.exception.code, 400)

        # 3. Non-existent case ID returns 404
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._patch("/api/cases/case_nonexistent_999", {"status": "Resolved"})
        self.assertEqual(ctx.exception.code, 404)

    def test_post_case_review_action(self) -> None:
        """POST /api/cases/{id}/review appends operator notes and optional status updates."""
        res = self._post("/api/cases/case_api_seed_01/review", {
            "note": "Corroborated malicious activity with firewall team.",
            "author": "analyst_frank",
        })
        self.assertEqual(res["status"], "success")
        case_obj = res["case"]
        self.assertGreaterEqual(len(case_obj["review_actions"]), 1)
        last_action = case_obj["review_actions"][-1]
        self.assertEqual(last_action["operator_note"], "Corroborated malicious activity with firewall team.")
        self.assertEqual(last_action["author"], "analyst_frank")

    def test_post_correlation_run(self) -> None:
        """POST /api/cases/correlate triggers correlation and returns execution metrics."""
        res = self._post("/api/cases/correlate", {"limit_findings": 500})
        self.assertEqual(res["status"], "success")
        result = res["result"]
        self.assertIn("evaluation_id", result)
        self.assertIn("findings_scanned", result)
        self.assertIn("duration_ms", result)


if __name__ == "__main__":
    unittest.main()
