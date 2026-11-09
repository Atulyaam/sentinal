"""Integration tests for Claim Guard REST API endpoints."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
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


class TestClaimsAPI(unittest.TestCase):
    """Integration test suite for /api/claims/* endpoints."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = str(Path(cls.temp_dir.name) / "test_api_claims.db")
        os.environ["SENTINEL_DB_PATH"] = cls.db_path
        os.environ["SENTINEL_ALLOWED_ORIGINS"] = "http://localhost:5173"

        handler._repo = None
        handler._norm_engine = None
        handler._engine = None
        handler._detection_engine = None
        handler._correlation_engine = None
        handler._claim_engine = None

        conn = get_connection(cls.db_path)
        apply_migrations(conn)
        cls.repo = IngestionRepository(conn)

        # 1. Setup Source & Import Job
        cls.repo.get_or_create_source("src_api_claims", "API Claims Source", "auth_csv")
        cls.repo.create_import_job(
            import_id="imp_api_claims",
            source_id="src_api_claims",
            filename="auth.log",
            sha256="f" * 64,
            file_size=1024,
            parser_id="auth_csv",
            parser_version="1.0.0",
            status="completed",
        )
        cls.repo.persist_import_batch(
            import_id="imp_api_claims",
            status="completed",
            total_records=3,
            accepted_records=3,
            rejected_records=0,
            records=[
                {"record_number": 1, "parser_id": "auth_csv", "parser_version": "1.0.0", "record": {}},
                {"record_number": 2, "parser_id": "auth_csv", "parser_version": "1.0.0", "record": {}},
                {"record_number": 3, "parser_id": "auth_csv", "parser_version": "1.0.0", "record": {}},
            ],
            errors=[],
        )
        unnorm = cls.repo.get_unnormalized_records(import_id="imp_api_claims")
        rec_ids = [u["record_id"] for u in unnorm]

        # 2. Seed Normalized Events
        cls.event_ids = [f"evt_claim_{i}" for i in range(3)]
        events = [
            {
                "event_id": cls.event_ids[i],
                "import_id": "imp_api_claims",
                "record_id": rec_ids[i],
                "source_id": "src_api_claims",
                "record_number": i + 1,
                "timestamp": f"2026-11-09T08:0{i}:00Z",
                "source_type": "auth_csv",
                "source_file": "auth.log",
                "source_line": i + 1,
                "source_sha256": "f" * 64,
                "event_type": "authentication.failure",
                "user_principal": "analyst_bob",
                "source_ip": "10.0.0.5",
                "target_resource": "/login",
                "status": "failure",
                "attributes": {},
            }
            for i in range(3)
        ]
        cls.repo.persist_normalized_events_batch(events=events, errors=[])

        # 3. Seed Finding
        cls.finding_id = "find_claim_01"
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO findings (
                finding_id, rule_id, rule_version, rule_config_hash,
                severity, status, title, description,
                first_observed_at, last_observed_at, matched_entity,
                matched_conditions_json, supporting_event_ids_json,
                limitations, dedupe_key, created_at, updated_at
            ) VALUES (?, 'AUTH-001', '1.0.0', 'hash_claim', 'Medium', 'open', 'Failure Burst', 'Desc', ?, ?, 'analyst_bob', '{}', ?, 'none', 'key_clm_1', ?, ?);
            """,
            (cls.finding_id, now, now, json.dumps(cls.event_ids), now, now),
        )
        conn.commit()

        # 4. Seed Investigation Case
        cls.case_id = "case_claim_test_01"
        c = Case(
            case_id=cls.case_id,
            title="Claim Test Investigation Case",
            description="Testing Claim Guard API",
            status="Open",
            severity="Medium",
            correlation_key_type="user_principal",
            correlation_key_value="analyst_bob",
            first_observed_at="2026-11-09T08:00:00Z",
            last_observed_at="2026-11-09T08:02:00Z",
            dedupe_key="user_principal:analyst_bob:100",
            metadata={"correlation_rationale": "Grouped under analyst_bob"},
        )
        cf = CaseFinding(case_id=cls.case_id, finding_id=cls.finding_id, correlation_rationale="Linked finding")
        ces = [CaseEvent(case_id=cls.case_id, event_id=eid, relationship_type="evidence", correlation_rationale="Evt") for eid in cls.event_ids]
        cls.repo.persist_cases_batch([c], [cf], ces)

        # 5. Start Test HTTP Server
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
        cls.temp_dir.cleanup()

    def _request(self, method: str, path: str, body: Any = None) -> Tuple[int, Dict[str, Any]]:
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Origin": "http://localhost:5173", "Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                status = resp.status
                resp_data = json.loads(resp.read().decode("utf-8"))
                return status, resp_data
        except urllib.error.HTTPError as err:
            err_data = json.loads(err.read().decode("utf-8"))
            return err.code, err_data

    def test_get_templates_catalog(self) -> None:
        """GET /api/claims/templates returns approved templates and supported claim types."""
        status, data = self._request("GET", "/api/claims/templates")
        self.assertEqual(status, 200)
        self.assertIn("templates", data)
        self.assertIn("case_event_count_v1", data["templates"])
        self.assertIn("supported_claim_types", data)
        self.assertIn("event_count", data["supported_claim_types"])

    def test_verify_claims_endpoint_success(self) -> None:
        """POST /api/claims/verify with valid claim returns 200 and 'verified' status."""
        payload = {
            "case_id": self.case_id,
            "claims": [
                {
                    "claim_id": "clm_api_test_01",
                    "case_id": self.case_id,
                    "claim_type": "event_count",
                    "predicate": "contains_events_of_type",
                    "value": {"count": 3, "event_type": "authentication.failure"},
                    "evidence_refs": self.event_ids,
                    "certainty": "observed",
                    "template_id": "case_event_count_v1",
                }
            ],
        }
        status, data = self._request("POST", "/api/claims/verify", body=payload)
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "success")
        report = data["report"]
        self.assertEqual(report["verified_count"], 1)
        self.assertEqual(report["blocked_count"], 0)
        self.assertEqual(report["results"][0]["status"], "verified")
        self.assertIn("Case contains 3 authentication.failure event(s).", report["results"][0]["rendered_text"])

    def test_verify_claims_endpoint_blocks_adversarial_claim(self) -> None:
        """POST /api/claims/verify with hallucinated count returns 200 with status 'blocked'."""
        payload = {
            "case_id": self.case_id,
            "claims": [
                {
                    "claim_id": "clm_api_bad_count",
                    "case_id": self.case_id,
                    "claim_type": "event_count",
                    "predicate": "contains_events_of_type",
                    "value": {"count": 99, "event_type": "authentication.failure"},  # Claims 99, only 3 exist!
                    "evidence_refs": self.event_ids,
                    "certainty": "observed",
                    "template_id": "case_event_count_v1",
                }
            ],
        }
        status, data = self._request("POST", "/api/claims/verify", body=payload)
        self.assertEqual(status, 200)
        report = data["report"]
        self.assertEqual(report["verified_count"], 0)
        self.assertEqual(report["blocked_count"], 1)
        self.assertEqual(report["results"][0]["status"], "blocked")
        self.assertIn("[BLOCKED CLAIM]", report["results"][0]["rendered_text"])

    def test_get_case_claims_endpoint(self) -> None:
        """GET /api/cases/{case_id}/claims returns all verified and blocked claims for case."""
        status, data = self._request("GET", f"/api/cases/{self.case_id}/claims")
        self.assertEqual(status, 200)
        self.assertEqual(data["case_id"], self.case_id)
        self.assertGreaterEqual(len(data["claims"]), 2)

    def test_demo_claims_generation_endpoint(self) -> None:
        """POST /api/cases/{case_id}/claims/demo runs the Claim Guard Demo Moment."""
        status, data = self._request("POST", f"/api/cases/{self.case_id}/claims/demo")
        self.assertEqual(status, 200)
        report = data["report"]
        # Must contain both verified claims and blocked adversarial claims
        self.assertGreaterEqual(report["verified_count"], 1)
        self.assertGreaterEqual(report["blocked_count"], 1)

    def test_verify_claims_rejects_malformed_payload(self) -> None:
        """POST /api/claims/verify with unsupported claim type returns 400 Bad Request."""
        payload = {
            "case_id": self.case_id,
            "claims": [
                {
                    "claim_id": "clm_malformed",
                    "case_id": self.case_id,
                    "claim_type": "hallucinated_arbitrary_type",
                    "predicate": "invalid_pred",
                    "value": {},
                    "evidence_refs": [],
                    "template_id": "invalid_tmpl",
                }
            ],
        }
        status, data = self._request("POST", "/api/claims/verify", body=payload)
        self.assertEqual(status, 400)
        self.assertIn("Unsupported claim_type", data["message"])


if __name__ == "__main__":
    unittest.main()

