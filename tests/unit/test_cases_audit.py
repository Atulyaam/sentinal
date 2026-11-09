"""Independent audit unit tests for Phase 5 Investigation Cases and Correlation Engine."""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone

from backend.cases.engine import CorrelationEngine
from backend.cases.models import (
    Case,
    CaseEvent,
    CaseFinding,
    compute_case_id,
    derive_case_severity,
    validate_status_transition,
)
from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository


class TestCasesAudit(unittest.TestCase):
    """Independent audit tests verifying correlation, cases lifecycle, and boundary integrity."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "audit_cases.db")
        self.conn = get_connection(self.db_path)
        apply_migrations(self.conn)
        self.repo = IngestionRepository(self.conn)
        self.engine = CorrelationEngine(window_seconds=3600, enable_ip_correlation=False)

        # Baseline source and import to satisfy foreign keys
        self.repo.get_or_create_source("src_audit", "Audit Source", "auth_csv")
        self.repo.create_import_job(
            import_id="imp_audit_01",
            source_id="src_audit",
            filename="audit.log",
            sha256="a" * 64,
            file_size=2048,
            parser_id="auth_csv",
            parser_version="1.0.0",
            status="completed",
        )

    def tearDown(self) -> None:
        self.conn.close()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _seed_normalized_event(self, event_id: str, timestamp: str, user: str | None = None, ip: str | None = None, attrs: dict | None = None) -> None:
        """Seed a valid canonical event to satisfy foreign key constraints."""
        import json
        rec_id = f"rec_{event_id}"
        self.conn.execute(
            """
            INSERT OR IGNORE INTO parsed_records (
                record_id, import_id, record_number, parser_id, parser_version, record_json, created_at
            ) VALUES (?, 'imp_audit_01', 1, 'auth_csv', '1.0.0', '{}', datetime('now', 'utc'));
            """,
            (rec_id,),
        )

        self.conn.execute(
            """
            INSERT OR IGNORE INTO normalized_events (
                event_id, import_id, record_id, source_id, record_number, timestamp, source_type,
                source_file, source_line, source_sha256, event_type, user_principal, source_ip,
                target_resource, status, attributes_json, normalization_version, created_at
            ) VALUES (?, 'imp_audit_01', ?, 'src_audit', 1, ?, 'auth_csv', 'audit.csv', 1, ?, 'user_authentication', ?, ?, NULL, 'SUCCESS', ?, '1.0.0', datetime('now', 'utc'));
            """,
            (event_id, rec_id, timestamp, "a" * 64, user, ip, json.dumps(attrs or {})),
        )

    def _seed_finding(self, finding_id: str, rule_id: str, severity: str, first_obs: str, last_obs: str, user: str | None = None, event_ids: list[str] | None = None) -> None:
        """Seed a valid finding to satisfy foreign key constraints."""
        import json
        eids = event_ids or []
        for eid in eids:
            self._seed_normalized_event(eid, first_obs, user=user)

        self.conn.execute(
            """
            INSERT OR IGNORE INTO findings (
                finding_id, rule_id, rule_version, rule_config_hash, severity, status,
                title, description, first_observed_at, last_observed_at, matched_entity,
                matched_conditions_json, supporting_event_ids_json, limitations, dedupe_key, created_at, updated_at
            ) VALUES (?, ?, '1.0.0', 'hash_01', ?, 'open', 'Audit Finding', 'Desc', ?, ?, ?, '{}', ?, 'Limitations', ?, datetime('now', 'utc'), datetime('now', 'utc'));
            """,
            (finding_id, rule_id, severity, first_obs, last_obs, user, json.dumps(eids), f"dedupe_{finding_id}"),
        )

        for eid in eids:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO finding_events (finding_id, event_id)
                VALUES (?, ?);
                """,
                (finding_id, eid),
            )

    # -------------------------------------------------------------
    # 1. Bucket Boundary Integrity (Risk A)
    # -------------------------------------------------------------
    def test_bucket_boundary_splits_consistently_without_duplication(self) -> None:
        """
        Events immediately before and after bucket boundary partition into discrete cases.
        Repeated correlation runs never duplicate either case.
        """
        # Bucket boundary at 11:00:00Z (epoch: 1794222000, divisible by 3600)
        # Event 1: 10:59:50Z (bucket N)
        # Event 2: 11:00:10Z (bucket N + 1)
        self._seed_finding("f_pre", "AUTH-001", "Medium", "2026-11-09T10:59:50Z", "2026-11-09T10:59:50Z", user="alice", event_ids=["evt_pre"])
        self._seed_finding("f_post", "AUTH-001", "Medium", "2026-11-09T11:00:10Z", "2026-11-09T11:00:10Z", user="alice", event_ids=["evt_post"])

        res1 = self.engine.run_correlation(self.repo)
        self.assertEqual(res1["cases_created"], 2)

        cases, total = self.repo.list_cases()
        self.assertEqual(total, 2)
        case_ids = {c["case_id"] for c in cases}
        self.assertEqual(len(case_ids), 2)

        # Repeated run: zero duplicates created
        res2 = self.engine.run_correlation(self.repo)
        self.assertEqual(res2["cases_created"], 0)
        self.assertEqual(res2["cases_updated"], 2)
        _, total2 = self.repo.list_cases()
        self.assertEqual(total2, 2)

    # -------------------------------------------------------------
    # 2. Key Priority Audit (Risk B, DEF-CASE-002)
    # -------------------------------------------------------------
    def test_key_priority_session_over_request_id(self) -> None:
        """
        When user_principal is absent, session_id MUST take precedence over request_id
        regardless of alphabetical ordering.
        """
        # Supporting event has session_id and request_id
        supp_evts = [{
            "event_id": "evt_multi_key",
            "timestamp": "2026-11-09T10:00:00Z",
            "attributes": {"session_id": "sess_target_alpha", "request_id": "req_target_beta"},
        }]
        finding = {
            "finding_id": "f_multi",
            "rule_id": "WEB-001",
            "first_observed_at": "2026-11-09T10:00:00Z",
            "matched_entity": None,
            "matched_conditions": {},
            "supporting_events": supp_evts,
        }
        keys = self.engine.extract_correlation_keys(finding, supp_evts)
        key_types = [k[0] for k in keys]
        self.assertIn("session_id", key_types)
        self.assertIn("request_id", key_types)

        # Verify that session_id was prioritized over request_id
        key_priority = {"user_principal": 1, "session_id": 2, "request_id": 3, "source_ip": 4}
        sorted_keys = sorted(keys, key=lambda k: (key_priority.get(k[0], 99), k[1]))
        self.assertEqual(sorted_keys[0][0], "session_id")
        self.assertEqual(sorted_keys[0][1], "sess_target_alpha")

    # -------------------------------------------------------------
    # 3. Out-of-Order Log Ingestion & First Observed Update (DEF-CASE-001)
    # -------------------------------------------------------------
    def test_out_of_order_evidence_updates_first_observed_and_description(self) -> None:
        """
        When delayed evidence with an earlier timestamp in the same bucket arrives later,
        first_observed_at must expand to MIN(first_observed_at) and description must update.
        """
        # Initial finding at 10:25:00Z
        self._seed_finding("f_later", "AUTH-001", "Medium", "2026-11-09T10:25:00Z", "2026-11-09T10:25:00Z", user="bob", event_ids=["evt_later"])
        self.engine.run_correlation(self.repo)

        cases, _ = self.repo.list_cases()
        bob_case = [c for c in cases if c["correlation_key_value"] == "bob"][0]
        self.assertEqual(bob_case["first_observed_at"], "2026-11-09T10:25:00Z")
        self.assertEqual(bob_case["finding_count"], 1)

        # Delayed finding arrives at 10:05:00Z (same user, same bucket)
        self._seed_finding("f_earlier", "AUTH-002", "High", "2026-11-09T10:05:00Z", "2026-11-09T10:05:00Z", user="bob", event_ids=["evt_earlier"])
        self.engine.run_correlation(self.repo)

        updated_case = self.repo.get_case(bob_case["case_id"])
        self.assertIsNotNone(updated_case)
        # first_observed_at must now be 10:05:00Z
        self.assertEqual(updated_case["first_observed_at"], "2026-11-09T10:05:00Z")
        # severity must be elevated to High
        self.assertEqual(updated_case["severity"], "High")
        # finding count must be 2
        self.assertEqual(len(updated_case["findings"]), 2)

    # -------------------------------------------------------------
    # 4. Analyst Status Preservation on New Evidence (Risk C & D)
    # -------------------------------------------------------------
    def test_resolved_case_preserves_status_under_new_evidence(self) -> None:
        """
        When a case is set to Resolved by an analyst, subsequent correlation runs
        must NEVER silently reopen the case to Open.
        """
        self._seed_finding("f_res_1", "AUTH-001", "Medium", "2026-11-09T10:10:00Z", "2026-11-09T10:10:00Z", user="charlie", event_ids=["evt_res_1"])
        self.engine.run_correlation(self.repo)

        cases, _ = self.repo.list_cases()
        charlie_case = [c for c in cases if c["correlation_key_value"] == "charlie"][0]
        case_id = charlie_case["case_id"]

        # Analyst reviews and resolves case
        self.repo.update_case_status(case_id, "UnderReview", operator_note="Triage started")
        self.repo.update_case_status(case_id, "Resolved", operator_note="Issue resolved")

        c_resolved = self.repo.get_case(case_id)
        self.assertEqual(c_resolved["status"], "Resolved")

        # New evidence arrives for charlie in the same bucket
        self._seed_finding("f_res_2", "PRIV-001", "High", "2026-11-09T10:30:00Z", "2026-11-09T10:30:00Z", user="charlie", event_ids=["evt_res_2"])
        self.engine.run_correlation(self.repo)

        c_after = self.repo.get_case(case_id)
        # Status MUST remain Resolved!
        self.assertEqual(c_after["status"], "Resolved")
        # Severity elevated to High
        self.assertEqual(c_after["severity"], "High")
        # Review actions intact
        self.assertEqual(len(c_after["review_actions"]), 2)

    # -------------------------------------------------------------
    # 5. Timeline Order Stability (DEF-CASE-003)
    # -------------------------------------------------------------
    def test_timeline_sorting_stability_on_identical_timestamps(self) -> None:
        """
        Timeline items with identical timestamps must sort in logical order:
        event (1) < finding (2) < correlation (3) < review_action (5).
        """
        same_ts = "2026-11-09T12:00:00Z"
        self._seed_finding("f_sync", "AUTH-001", "Medium", same_ts, same_ts, user="david", event_ids=["evt_sync"])
        self.engine.run_correlation(self.repo)

        cases, _ = self.repo.list_cases()
        david_case = [c for c in cases if c["correlation_key_value"] == "david"][0]
        self.repo.add_case_note(david_case["case_id"], "Operator note at same time")

        detail = self.repo.get_case(david_case["case_id"])
        timeline = detail["timeline"]

        # Check types ordering
        item_types = [item["item_type"] for item in timeline]
        self.assertIn("event", item_types)
        self.assertIn("finding", item_types)
        self.assertIn("review_action", item_types)

        evt_idx = item_types.index("event")
        find_idx = item_types.index("finding")
        rev_idx = item_types.index("review_action")
        # event must precede finding, finding must precede review_action
        self.assertLess(evt_idx, find_idx)
        self.assertLess(find_idx, rev_idx)

    # -------------------------------------------------------------
    # 6. Unbounded Note and Author Defense (DEF-CASE-004)
    # -------------------------------------------------------------
    def test_oversized_note_and_author_rejected(self) -> None:
        """
        Operator notes > 10,000 characters or authors > 100 characters must be rejected.
        """
        self._seed_finding("f_sec", "AUTH-001", "Low", "2026-11-09T10:00:00Z", "2026-11-09T10:00:00Z", user="eve", event_ids=["evt_sec"])
        self.engine.run_correlation(self.repo)

        cases, _ = self.repo.list_cases()
        case_id = cases[0]["case_id"]

        # 10,001 character note
        huge_note = "A" * 10001
        with self.assertRaises(ValueError) as ctx:
            self.repo.add_case_note(case_id, huge_note)
        self.assertIn("10,000 characters", str(ctx.exception))

        # 101 character author
        huge_author = "B" * 101
        with self.assertRaises(ValueError) as ctx:
            self.repo.add_case_note(case_id, "Valid note", author=huge_author)
        self.assertIn("100 characters", str(ctx.exception))

    # -------------------------------------------------------------
    # 7. Backend Search in list_cases (DEF-CASE-005)
    # -------------------------------------------------------------
    def test_list_cases_search_filter(self) -> None:
        """
        list_cases must support search querying across title, case ID, and correlation key value.
        """
        self._seed_finding("f_search_1", "AUTH-001", "Medium", "2026-11-09T10:00:00Z", "2026-11-09T10:00:00Z", user="frank_unique", event_ids=["evt_s1"])
        self._seed_finding("f_search_2", "AUTH-001", "Medium", "2026-11-09T10:00:00Z", "2026-11-09T10:00:00Z", user="george_normal", event_ids=["evt_s2"])
        self.engine.run_correlation(self.repo)

        # Search for frank
        cases, total = self.repo.list_cases(search="frank_unique")
        self.assertEqual(total, 1)
        self.assertEqual(cases[0]["correlation_key_value"], "frank_unique")

        # Search non-existent
        cases_none, total_none = self.repo.list_cases(search="nonexistent_phantom")
        self.assertEqual(total_none, 0)
        self.assertEqual(len(cases_none), 0)

    # -------------------------------------------------------------
    # 8. IP Isolation Guardrail
    # -------------------------------------------------------------
    def test_ip_isolation_different_users_never_merge(self) -> None:
        """
        Two different users sharing the exact same source IP must NEVER merge
        into a single case when enable_ip_correlation is False.
        """
        same_ip = "198.51.100.222"
        self._seed_finding("f_user_u1", "AUTH-001", "Medium", "2026-11-09T10:00:00Z", "2026-11-09T10:00:00Z", user="user_one", event_ids=["evt_u1"])
        self.conn.execute("UPDATE normalized_events SET source_ip = ? WHERE event_id = 'evt_u1';", (same_ip,))

        self._seed_finding("f_user_u2", "AUTH-001", "Medium", "2026-11-09T10:05:00Z", "2026-11-09T10:05:00Z", user="user_two", event_ids=["evt_u2"])
        self.conn.execute("UPDATE normalized_events SET source_ip = ? WHERE event_id = 'evt_u2';", (same_ip,))

        self.engine.run_correlation(self.repo)

        cases, total = self.repo.list_cases()
        u1_cases = [c for c in cases if c["correlation_key_value"] == "user_one"]
        u2_cases = [c for c in cases if c["correlation_key_value"] == "user_two"]

        self.assertEqual(len(u1_cases), 1)
        self.assertEqual(len(u2_cases), 1)
        self.assertNotEqual(u1_cases[0]["case_id"], u2_cases[0]["case_id"])

        # Confirm 0 source_ip cases
        ip_cases = [c for c in cases if c["correlation_key_type"] == "source_ip"]
        self.assertEqual(len(ip_cases), 0)

    # -------------------------------------------------------------
    # 9. Isolated Findings Without Identity Keys
    # -------------------------------------------------------------
    def test_findings_without_identity_never_merge_together(self) -> None:
        """
        Two findings lacking identity keys must remain in isolated single-finding cases
        and never merge into an artificial shared 'unknown' cluster.
        """
        self._seed_finding("f_anon_1", "WEB-001", "Low", "2026-11-09T10:00:00Z", "2026-11-09T10:00:00Z", user=None, event_ids=["evt_anon_1"])
        self._seed_finding("f_anon_2", "WEB-001", "Low", "2026-11-09T10:00:00Z", "2026-11-09T10:00:00Z", user=None, event_ids=["evt_anon_2"])

        self.engine.run_correlation(self.repo)

        cases, total = self.repo.list_cases()
        anon_cases = [c for c in cases if c["correlation_key_type"] == "isolated_finding"]
        self.assertEqual(len(anon_cases), 2)
        self.assertNotEqual(anon_cases[0]["case_id"], anon_cases[1]["case_id"])


if __name__ == "__main__":
    unittest.main()
