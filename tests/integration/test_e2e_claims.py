"""End-to-end integration test for Claim Guard: Full pipeline from logs to verified and blocked claims."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from backend.api import handler
from backend.api.server import create_server
from backend.claims.engine import ClaimGuardEngine
from backend.claims.models import ClaimProposal
from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository


class TestE2EClaims(unittest.TestCase):
    """End-to-end pipeline test for Claim Guard."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_e2e_claims.db")
        os.environ["SENTINEL_DB_PATH"] = self.db_path
        os.environ["SENTINEL_ALLOWED_ORIGINS"] = "http://localhost:5173"

        handler._repo = None
        handler._norm_engine = None
        handler._engine = None
        handler._detection_engine = None
        handler._correlation_engine = None
        handler._claim_engine = None

        self.conn = get_connection(self.db_path)
        apply_migrations(self.conn)
        self.repo = IngestionRepository(self.conn)

        self.server = create_server(host="127.0.0.1", port=0)
        self.host, self.port = self.server.server_address
        self.base_url = f"http://{self.host}:{self.port}"

        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        time.sleep(0.1)

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2.0)
        try:
            self.conn.close()
        except Exception:
            pass
        if handler._repo and handler._repo.conn:
            try:
                handler._repo.conn.close()
            except Exception:
                pass
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _post_multipart(self, filename: str, content: str, parser_id: str) -> dict:
        url = f"{self.base_url}/api/import"
        boundary = "----SentinelE2EClaimsBoundary"
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

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8")
        headers = {"Origin": "http://localhost:5173", "Content-Type": "application/json", "Accept": "application/json"}
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _get(self, path: str) -> dict:
        url = f"{self.base_url}{path}"
        headers = {"Origin": "http://localhost:5173", "Accept": "application/json"}
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_complete_claim_guard_lifecycle(self) -> None:
        """
        Full lifecycle test:
        1. Ingest auth CSV logs for user 'charlie'.
        2. Normalize into canonical events.
        3. Run detection engine to produce findings.
        4. Correlate into investigation case.
        5. AI proposes valid and adversarial claims.
        6. Claim Guard verifies and blocks appropriately.
        7. Verify SQLite schema, foreign keys, and persistence.
        """
        # Step 1: Ingest Auth CSV (5 failures + 1 success)
        auth_csv_content = (
            "timestamp,user,ip,status\n"
            "2026-11-09T08:00:00Z,charlie,198.51.100.55,FAILURE\n"
            "2026-11-09T08:01:00Z,charlie,198.51.100.55,FAILURE\n"
            "2026-11-09T08:02:00Z,charlie,198.51.100.55,FAILURE\n"
            "2026-11-09T08:03:00Z,charlie,198.51.100.55,FAILURE\n"
            "2026-11-09T08:04:00Z,charlie,198.51.100.55,FAILURE\n"
            "2026-11-09T08:06:00Z,charlie,198.51.100.55,SUCCESS\n"
        )
        import_res = self._post_multipart("auth_charlie.csv", auth_csv_content, "auth_csv")
        self.assertEqual(import_res["status"], "completed")

        # Step 2: Normalize
        norm_res = self._post("/api/normalization/run", {"limit": 100})
        self.assertEqual(norm_res["status"], "success")
        self.assertEqual(norm_res["result"]["accepted"], 6)

        # Step 3: Run Detection Engine
        det_res = self._post("/api/detection/run", {"limit_events": 100})
        self.assertEqual(det_res["status"], "success")
        self.assertGreaterEqual(det_res["result"]["findings_generated"], 1)

        # Step 4: Run Correlation Engine
        corr_res = self._post("/api/cases/correlate", {"limit_findings": 100})
        self.assertEqual(corr_res["status"], "success")
        self.assertGreaterEqual(corr_res["result"]["cases_created"], 1)

        cases_res = self._get("/api/cases?limit=10")
        cases = cases_res["cases"]
        self.assertGreaterEqual(len(cases), 1)
        case_id = cases[0]["case_id"]

        # Fetch case details
        case_detail = self._get(f"/api/cases/{case_id}")
        self.assertEqual(case_detail["correlation_key_value"], "charlie")
        evidence_events = case_detail["events"]
        failure_events = [e for e in evidence_events if str(e.get("status", "")).upper() == "FAILURE"]
        self.assertGreater(len(failure_events), 0)
        failure_ids = [e["event_id"] for e in failure_events]

        # Step 5: Propose Claims (Factual, Inferred, and Adversarial)
        proposals = [
            # Proposal 1: Valid event count (5 failures)
            {
                "claim_id": "clm_charlie_01",
                "case_id": case_id,
                "claim_type": "event_count",
                "predicate": "contains_events_of_type",
                "value": {"count": len(failure_ids), "event_type": "user_authentication"},
                "evidence_refs": failure_ids,
                "certainty": "observed",
                "template_id": "case_event_count_v1",
            },
            # Proposal 2: Valid finding existence
            {
                "claim_id": "clm_charlie_02",
                "case_id": case_id,
                "claim_type": "finding_exists",
                "predicate": "contains_finding_for_rule",
                "value": {"rule_id": "AUTH-001", "severity": "Medium"},
                "evidence_refs": [case_detail["findings"][0]["finding_id"]],
                "certainty": "observed",
                "template_id": "case_finding_exists_v1",
            },
            # Proposal 3: Qualified claim (inferred correlation)
            {
                "claim_id": "clm_charlie_03",
                "case_id": case_id,
                "claim_type": "correlation_relationship",
                "predicate": "correlated_by_key",
                "value": {"key_type": "user_principal", "key_value": "charlie"},
                "evidence_refs": [failure_ids[0]],
                "certainty": "inferred",
                "template_id": "case_correlation_v1",
            },
            # Proposal 4: Adversarial Claim (Hallucinated count of 25)
            {
                "claim_id": "clm_charlie_adv_01",
                "case_id": case_id,
                "claim_type": "event_count",
                "predicate": "contains_events_of_type",
                "value": {"count": 25, "event_type": "authentication.failure"},
                "evidence_refs": failure_ids,
                "certainty": "observed",
                "template_id": "case_event_count_v1",
            },
            # Proposal 5: Adversarial Claim (Fabricated nonexistent evidence ID)
            {
                "claim_id": "clm_charlie_adv_02",
                "case_id": case_id,
                "claim_type": "finding_exists",
                "predicate": "contains_finding_for_rule",
                "value": {"rule_id": "AUTH-001"},
                "evidence_refs": ["evt_hallucinated_ghost_record"],
                "certainty": "observed",
                "template_id": "case_finding_exists_v1",
            },
        ]

        # Step 6: Verify via POST /api/claims/verify
        verify_res = self._post("/api/claims/verify", {
            "case_id": case_id,
            "claims": proposals,
        })
        self.assertEqual(verify_res["status"], "success")
        rep = verify_res["report"]
        self.assertEqual(rep["verified_count"], 2)
        self.assertEqual(rep["qualified_count"], 1)
        self.assertEqual(rep["blocked_count"], 2)

        # Step 7: Verify SQLite schema, foreign keys, and persistence
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA foreign_key_check;")
        fk_violations = cursor.fetchall()
        self.assertEqual(len(fk_violations), 0, f"Foreign key violations found: {fk_violations}")

        cursor.execute("SELECT count(*) FROM claim_proposals WHERE case_id = ?;", (case_id,))
        self.assertEqual(cursor.fetchone()[0], 5)

        cursor.execute("SELECT count(*) FROM claim_verifications WHERE case_id = ?;", (case_id,))
        self.assertEqual(cursor.fetchone()[0], 5)

        cursor.execute("SELECT status, count(*) FROM claim_verifications WHERE case_id = ? GROUP BY status;", (case_id,))
        status_counts = dict(cursor.fetchall())
        self.assertEqual(status_counts["verified"], 2)
        self.assertEqual(status_counts["qualified"], 1)
        self.assertEqual(status_counts["blocked"], 2)

        # Step 8: Verify case detail endpoint includes the verified claims
        refreshed_case = self._get(f"/api/cases/{case_id}")
        claims_in_case = refreshed_case.get("claims", [])
        self.assertEqual(len(claims_in_case), 5)


if __name__ == "__main__":
    unittest.main()
