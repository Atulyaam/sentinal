"""Unit tests for Deterministic Correlation Engine (Phase 5)."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from backend.cases.engine import CorrelationEngine
from backend.cases.models import (
    ALLOWED_STATUSES,
    ALLOWED_TRANSITIONS,
    compute_case_id,
    derive_case_severity,
    validate_status_transition,
)
from backend.detection.models import Finding
from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository


def _make_event(
    event_id: str,
    event_type: str,
    timestamp: str,
    user_principal: str | None = None,
    source_ip: str = "192.168.1.100",
    attributes: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "event_id": event_id,
        "import_id": "imp_corr_test",
        "event_type": event_type,
        "timestamp": timestamp,
        "source_ip": source_ip,
        "user_principal": user_principal,
        "target_resource": "/login",
        "status": "FAILURE",
        "attributes": attributes or {},
        "source_file": "auth.log",
        "source_line": 1,
        "source_sha256": "f" * 64,
        "schema_version": "1.0.0",
        "parser_version": "1.0.0",
    }


def _make_finding(
    finding_id: str,
    rule_id: str,
    severity: str,
    first_obs: str,
    last_obs: str,
    matched_entity: str | None,
    supporting_event_ids: List[str],
    matched_conditions: Dict[str, Any] | None = None,
) -> Finding:
    return Finding(
        finding_id=finding_id,
        rule_id=rule_id,
        rule_version="1.0.0",
        rule_config_hash="a" * 64,
        severity=severity,
        status="open",
        title=f"Test Finding {finding_id}",
        description=f"Description for {finding_id}",
        first_observed_at=first_obs,
        last_observed_at=last_obs,
        matched_entity=matched_entity,
        matched_conditions=matched_conditions or {"user_principal": matched_entity},
        supporting_event_ids=supporting_event_ids,
        limitations="none",
        dedupe_key=f"{rule_id}:{matched_entity}:{first_obs}",
    )


class TestCorrelationEngine(unittest.TestCase):
    """Test suite for deterministic correlation, key extraction, and case derivation."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_corr.db"
        self.conn = get_connection(self.db_path)
        apply_migrations(self.conn)
        self.repo = IngestionRepository(self.conn)

        # Baseline source and import job to satisfy foreign keys
        self.repo.get_or_create_source("src_corr", "Corr Source", "auth_csv")
        self.repo.create_import_job(
            import_id="imp_corr_test",
            source_id="src_corr",
            filename="auth.log",
            sha256="c" * 64,
            file_size=1024,
            parser_id="auth_csv",
            parser_version="1.0.0",
            status="completed",
        )

        # Add parsed records so normalized events can reference them
        self.repo.persist_import_batch(
            import_id="imp_corr_test",
            status="completed",
            total_records=10,
            accepted_records=10,
            rejected_records=0,
            records=[
                {
                    "record_number": i,
                    "parser_id": "auth_csv",
                    "parser_version": "1.0.0",
                    "record": {
                        "line_number": i,
                        "timestamp": "2026-11-09T08:00:00Z",
                        "event_type": "user_authentication",
                        "attributes": {},
                        "raw_payload": "{}",
                    },
                }
                for i in range(1, 11)
            ],
            errors=[],
        )
        unnorm = self.repo.get_unnormalized_records(import_id="imp_corr_test")
        self.record_ids = [r["record_id"] for r in unnorm]

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    def test_derive_case_severity(self) -> None:
        """Case severity is derived strictly from maximum severity among linked findings."""
        # 1. Medium + Low -> Medium
        sev, rat = derive_case_severity(["Medium", "Low"])
        self.assertEqual(sev, "Medium")
        self.assertIn("1 Medium", rat)

        # 2. Medium + High + Info -> High
        sev, rat = derive_case_severity(["Medium", "High", "Info"])
        self.assertEqual(sev, "High")
        self.assertIn("High", rat)

        # 3. Critical + High -> Critical
        sev, rat = derive_case_severity(["Critical", "High"])
        self.assertEqual(sev, "Critical")

        # 4. Empty -> Info default
        sev, rat = derive_case_severity([])
        self.assertEqual(sev, "Info")

    def test_status_transitions_valid_and_invalid(self) -> None:
        """Allowed transitions succeed; invalid transitions and illegal statuses are rejected."""
        # Valid forward transitions
        validate_status_transition("Open", "UnderReview")
        validate_status_transition("UnderReview", "Resolved")
        validate_status_transition("UnderReview", "NeedsMoreEvidence")
        validate_status_transition("NeedsMoreEvidence", "UnderReview")
        validate_status_transition("Resolved", "UnderReview")  # Reopen
        validate_status_transition("Open", "Dismissed")

        # No-op transition
        validate_status_transition("Open", "Open")

        # Invalid target status
        with self.assertRaises(ValueError):
            validate_status_transition("Open", "FakeStatus")

        # Illegal skip: Open directly to Resolved
        with self.assertRaises(ValueError):
            validate_status_transition("Open", "Resolved")

        # Illegal skip: Resolved directly to NeedsMoreEvidence
        with self.assertRaises(ValueError):
            validate_status_transition("Resolved", "NeedsMoreEvidence")

    def test_same_user_within_window_correlates(self) -> None:
        """Findings for the same normalized user within time window are grouped into one case."""
        base_time = datetime(2026, 11, 9, 8, 0, 0, tzinfo=timezone.utc)
        # Create 2 canonical events
        evt1 = _make_event("evt_u1", "user_authentication", base_time.isoformat(), user_principal="alice")
        evt2 = _make_event("evt_u2", "user_authentication", (base_time + timedelta(minutes=15)).isoformat(), user_principal="alice")

        self.repo.persist_normalized_events_batch(
            events=[
                {
                    "event_id": e["event_id"],
                    "import_id": "imp_corr_test",
                    "record_id": self.record_ids[i],
                    "source_id": "src_corr",
                    "record_number": i + 1,
                    "timestamp": e["timestamp"],
                    "source_type": "auth_csv",
                    "source_file": "auth.log",
                    "source_line": i + 1,
                    "source_sha256": "c" * 64,
                    "event_type": e["event_type"],
                    "user_principal": e["user_principal"],
                    "source_ip": e["source_ip"],
                    "target_resource": e["target_resource"],
                    "status": e["status"],
                    "attributes_json": "{}",
                }
                for i, e in enumerate([evt1, evt2])
            ],
            errors=[],
        )

        # Create 2 findings for alice
        f1 = _make_finding("find_a1", "AUTH-001", "Medium", base_time.isoformat(), base_time.isoformat(), "alice", ["evt_u1"])
        f2 = _make_finding("find_a2", "AUTH-002", "High", (base_time + timedelta(minutes=15)).isoformat(), (base_time + timedelta(minutes=15)).isoformat(), "alice", ["evt_u2"])
        self.repo.persist_findings_batch([f1, f2])

        engine = CorrelationEngine(window_seconds=3600, enable_ip_correlation=False)
        result = engine.run_correlation(self.repo)

        self.assertEqual(result["findings_scanned"], 2)
        self.assertEqual(result["cases_created"], 1)

        cases, total = self.repo.list_cases()
        self.assertEqual(total, 1)
        c = cases[0]
        self.assertEqual(c["correlation_key_type"], "user_principal")
        self.assertEqual(c["correlation_key_value"], "alice")
        self.assertEqual(c["severity"], "High")  # Max(Medium, High) -> High
        self.assertEqual(c["finding_count"], 2)
        self.assertEqual(c["event_count"], 2)

    def test_different_users_remain_separate(self) -> None:
        """Findings for different users produce independent investigation cases."""
        base_time = datetime(2026, 11, 9, 8, 0, 0, tzinfo=timezone.utc)
        evt1 = _make_event("evt_alice", "user_authentication", base_time.isoformat(), user_principal="alice")
        evt2 = _make_event("evt_bob", "user_authentication", base_time.isoformat(), user_principal="bob")

        self.repo.persist_normalized_events_batch(
            events=[
                {
                    "event_id": e["event_id"],
                    "import_id": "imp_corr_test",
                    "record_id": self.record_ids[i],
                    "source_id": "src_corr",
                    "record_number": i + 1,
                    "timestamp": e["timestamp"],
                    "source_type": "auth_csv",
                    "source_file": "auth.log",
                    "source_line": i + 1,
                    "source_sha256": "c" * 64,
                    "event_type": e["event_type"],
                    "user_principal": e["user_principal"],
                    "source_ip": e["source_ip"],
                    "target_resource": e["target_resource"],
                    "status": e["status"],
                    "attributes_json": "{}",
                }
                for i, e in enumerate([evt1, evt2])
            ],
            errors=[],
        )

        f1 = _make_finding("find_alice", "AUTH-001", "Medium", base_time.isoformat(), base_time.isoformat(), "alice", ["evt_alice"])
        f2 = _make_finding("find_bob", "AUTH-001", "Medium", base_time.isoformat(), base_time.isoformat(), "bob", ["evt_bob"])
        self.repo.persist_findings_batch([f1, f2])

        engine = CorrelationEngine(window_seconds=3600, enable_ip_correlation=False)
        result = engine.run_correlation(self.repo)

        self.assertEqual(result["cases_created"], 2)
        cases, total = self.repo.list_cases()
        self.assertEqual(total, 2)
        users = {c["correlation_key_value"] for c in cases}
        self.assertEqual(users, {"alice", "bob"})

    def test_ip_only_correlation_disabled_by_default(self) -> None:
        """Shared IP address alone does NOT group findings from different anonymous sources."""
        base_time = datetime(2026, 11, 9, 8, 0, 0, tzinfo=timezone.utc)
        # Two web findings with same IP 203.0.113.99 but no user principal
        f1 = _make_finding("find_w1", "WEB-001", "Medium", base_time.isoformat(), base_time.isoformat(), None, [], matched_conditions={"source_ip": "203.0.113.99"})
        f2 = _make_finding("find_w2", "WEB-001", "Medium", (base_time + timedelta(minutes=5)).isoformat(), (base_time + timedelta(minutes=5)).isoformat(), None, [], matched_conditions={"source_ip": "203.0.113.99"})
        self.repo.persist_findings_batch([f1, f2])

        # By default enable_ip_correlation is False
        engine = CorrelationEngine(window_seconds=3600, enable_ip_correlation=False)
        result = engine.run_correlation(self.repo)

        # Because neither finding has an approved identity key (user, session, request),
        # they must NOT be combined under IP. They fall back to isolated single-finding cases!
        self.assertEqual(result["cases_created"], 2)
        cases, total = self.repo.list_cases()
        self.assertEqual(total, 2)
        for c in cases:
            self.assertNotEqual(c["correlation_key_type"], "source_ip")
            self.assertIn("ip_correlation_used", c["metadata"])
            self.assertFalse(c["metadata"]["ip_correlation_used"])

    def test_re_correlation_is_idempotent_and_preserves_notes(self) -> None:
        """Re-running correlation does not create duplicate cases and preserves operator notes and status."""
        base_time = datetime(2026, 11, 9, 8, 0, 0, tzinfo=timezone.utc)
        evt1 = _make_event("evt_idem", "user_authentication", base_time.isoformat(), user_principal="charlie")
        self.repo.persist_normalized_events_batch(
            events=[
                {
                    "event_id": evt1["event_id"],
                    "import_id": "imp_corr_test",
                    "record_id": self.record_ids[0],
                    "source_id": "src_corr",
                    "record_number": 1,
                    "timestamp": evt1["timestamp"],
                    "source_type": "auth_csv",
                    "source_file": "auth.log",
                    "source_line": 1,
                    "source_sha256": "c" * 64,
                    "event_type": evt1["event_type"],
                    "user_principal": evt1["user_principal"],
                    "source_ip": evt1["source_ip"],
                    "target_resource": evt1["target_resource"],
                    "status": evt1["status"],
                    "attributes_json": "{}",
                }
            ],
            errors=[],
        )
        f1 = _make_finding("find_idem", "AUTH-001", "Medium", base_time.isoformat(), base_time.isoformat(), "charlie", ["evt_idem"])
        self.repo.persist_findings_batch([f1])

        engine = CorrelationEngine(window_seconds=3600)
        res1 = engine.run_correlation(self.repo)
        self.assertEqual(res1["cases_created"], 1)

        cases, _ = self.repo.list_cases()
        case_id = cases[0]["case_id"]

        # Operator updates status to UnderReview and adds a note
        self.repo.update_case_status(case_id, "UnderReview", operator_note="Beginning triage")
        self.repo.add_case_note(case_id, "Checking server logs for Charlie")

        # Run correlation second time
        res2 = engine.run_correlation(self.repo)
        self.assertEqual(res2["cases_created"], 0)
        self.assertEqual(res2["cases_updated"], 1)

        # Verify case status and review history survive re-correlation
        updated_case = self.repo.get_case(case_id)
        self.assertIsNotNone(updated_case)
        self.assertEqual(updated_case["status"], "UnderReview")
        self.assertEqual(len(updated_case["review_actions"]), 2)
        notes = [ra["operator_note"] for ra in updated_case["review_actions"]]
        self.assertIn("Beginning triage", notes)
        self.assertIn("Checking server logs for Charlie", notes)


if __name__ == "__main__":
    unittest.main()

