"""Unit tests for Cases Database Persistence and Schema Migration 005."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backend.cases.models import Case, CaseEvent, CaseFinding, ReviewAction
from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository


class TestCasesDatabase(unittest.TestCase):
    """Test suite for cases, case relationships, review actions, and foreign keys."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_cases_db.db"
        self.conn = get_connection(self.db_path)
        apply_migrations(self.conn)
        self.repo = IngestionRepository(self.conn)

        # Baseline source and import
        self.repo.get_or_create_source("src_test_cases", "Test Source", "auth_csv")
        self.repo.create_import_job(
            import_id="imp_cases_01",
            source_id="src_test_cases",
            filename="auth.log",
            sha256="d" * 64,
            file_size=2048,
            parser_id="auth_csv",
            parser_version="1.0.0",
            status="completed",
        )

        # Add parsed records
        self.repo.persist_import_batch(
            import_id="imp_cases_01",
            status="completed",
            total_records=2,
            accepted_records=2,
            rejected_records=0,
            records=[
                {
                    "record_number": 1,
                    "parser_id": "auth_csv",
                    "parser_version": "1.0.0",
                    "record": {
                        "line_number": 1,
                        "timestamp": "2026-11-09T08:00:00Z",
                        "event_type": "user_authentication",
                        "attributes": {},
                        "raw_payload": "{}",
                    },
                },
                {
                    "record_number": 2,
                    "parser_id": "auth_csv",
                    "parser_version": "1.0.0",
                    "record": {
                        "line_number": 2,
                        "timestamp": "2026-11-09T08:05:00Z",
                        "event_type": "user_authentication",
                        "attributes": {},
                        "raw_payload": "{}",
                    },
                },
            ],
            errors=[],
        )
        unnorm = self.repo.get_unnormalized_records(import_id="imp_cases_01")
        self.record_ids = [r["record_id"] for r in unnorm]

        # Add normalized events
        self.event_id_1 = "evt_case_000000000001"
        self.event_id_2 = "evt_case_000000000002"
        self.repo.persist_normalized_events_batch(
            events=[
                {
                    "event_id": self.event_id_1,
                    "import_id": "imp_cases_01",
                    "record_id": self.record_ids[0],
                    "source_id": "src_test_cases",
                    "record_number": 1,
                    "timestamp": "2026-11-09T08:00:00Z",
                    "source_type": "auth_csv",
                    "source_file": "auth.log",
                    "source_line": 1,
                    "source_sha256": "d" * 64,
                    "event_type": "user_authentication",
                    "user_principal": "dave",
                    "source_ip": "10.0.0.5",
                    "target_resource": "/login",
                    "status": "FAILURE",
                    "attributes_json": '{"session":"sess_100"}',
                },
                {
                    "event_id": self.event_id_2,
                    "import_id": "imp_cases_01",
                    "record_id": self.record_ids[1],
                    "source_id": "src_test_cases",
                    "record_number": 2,
                    "timestamp": "2026-11-09T08:05:00Z",
                    "source_type": "auth_csv",
                    "source_file": "auth.log",
                    "source_line": 2,
                    "source_sha256": "d" * 64,
                    "event_type": "user_authentication",
                    "user_principal": "dave",
                    "source_ip": "10.0.0.5",
                    "target_resource": "/login",
                    "status": "SUCCESS",
                    "attributes_json": '{"session":"sess_100"}',
                },
            ],
            errors=[],
        )

        # Add detection finding
        self.finding_id = "find_case_test_01"
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO findings (
                finding_id, rule_id, rule_version, rule_config_hash,
                severity, status, title, description,
                first_observed_at, last_observed_at, matched_entity,
                matched_conditions_json, supporting_event_ids_json,
                limitations, dedupe_key, created_at, updated_at
            ) VALUES (?, 'AUTH-001', '1.0.0', 'hash123', 'High', 'open', 'Test Auth Finding', 'desc', ?, ?, 'dave', '{}', ?, 'none', 'key123', ?, ?);
            """,
            (self.finding_id, now, now, f'["{self.event_id_1}"]', now, now),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    def test_schema_migration_005_tables_and_fk_check(self) -> None:
        """Verify Migration 005 tables exist and PRAGMA foreign_key_check passes with 0 violations."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        expected = {"cases", "case_findings", "case_events", "review_actions", "correlation_evaluations"}
        for t in expected:
            self.assertIn(t, tables, f"Expected table '{t}' in database.")

        cursor.execute("PRAGMA foreign_key_check;")
        violations = cursor.fetchall()
        self.assertEqual(len(violations), 0, f"Expected 0 FK violations, got: {violations}")

    def test_case_persistence_and_relationships(self) -> None:
        """Create a case with linked findings and events, verifying retrieval."""
        now = "2026-11-09T08:10:00Z"
        c = Case(
            case_id="case_dave_01",
            title="Dave Investigation Case",
            description="Case for Dave",
            status="Open",
            severity="High",
            correlation_key_type="user_principal",
            correlation_key_value="dave",
            first_observed_at="2026-11-09T08:00:00Z",
            last_observed_at="2026-11-09T08:05:00Z",
            dedupe_key="user_principal:dave:100",
            metadata={"correlation_rationale": "Grouped under user dave"},
        )
        cf = CaseFinding(case_id="case_dave_01", finding_id=self.finding_id, correlation_rationale="Linked finding")
        ce1 = CaseEvent(case_id="case_dave_01", event_id=self.event_id_1, relationship_type="evidence", correlation_rationale="Evt 1")
        ce2 = CaseEvent(case_id="case_dave_01", event_id=self.event_id_2, relationship_type="evidence", correlation_rationale="Evt 2")

        stats = self.repo.persist_cases_batch([c], [cf], [ce1, ce2])
        self.assertEqual(stats["cases_created"], 1)

        fetched = self.repo.get_case("case_dave_01")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["title"], "Dave Investigation Case")
        self.assertEqual(fetched["severity"], "High")
        self.assertEqual(len(fetched["findings"]), 1)
        self.assertEqual(fetched["findings"][0]["finding_id"], self.finding_id)
        self.assertEqual(len(fetched["events"]), 2)

    def test_foreign_key_restricts_event_deletion(self) -> None:
        """Deleting an event referenced in case_events is prohibited by ON DELETE RESTRICT."""
        c = Case(
            case_id="case_fk_test",
            title="FK Test Case",
            description="desc",
            status="Open",
            severity="Medium",
            correlation_key_type="user_principal",
            correlation_key_value="dave",
            first_observed_at="2026-11-09T08:00:00Z",
            last_observed_at="2026-11-09T08:05:00Z",
            dedupe_key="fk_test_key",
        )
        ce = CaseEvent(case_id="case_fk_test", event_id=self.event_id_1, relationship_type="evidence", correlation_rationale="FK test")
        self.repo.persist_cases_batch([c], [], [ce])

        # Attempting to delete the normalized event must fail
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM normalized_events WHERE event_id = ?;", (self.event_id_1,))

    def test_review_action_append_only(self) -> None:
        """Review actions and status transitions are recorded immutably."""
        c = Case(
            case_id="case_review_test",
            title="Review Test Case",
            description="desc",
            status="Open",
            severity="Medium",
            correlation_key_type="user_principal",
            correlation_key_value="dave",
            first_observed_at="2026-11-09T08:00:00Z",
            last_observed_at="2026-11-09T08:05:00Z",
            dedupe_key="review_test_key",
        )
        self.repo.persist_cases_batch([c], [], [])

        # 1. Update status
        updated = self.repo.update_case_status("case_review_test", "UnderReview", operator_note="Assigned to SecOps Analyst")
        self.assertIsNotNone(updated)
        self.assertEqual(updated["status"], "UnderReview")

        # 2. Add an operator note
        updated2 = self.repo.add_case_note("case_review_test", "Corroborated with firewall alert")
        self.assertIsNotNone(updated2)
        self.assertEqual(len(updated2["review_actions"]), 2)
        self.assertEqual(updated2["review_actions"][0]["action_type"], "status_changed")
        self.assertEqual(updated2["review_actions"][1]["action_type"], "note_added")

    def test_case_timeline_assembly(self) -> None:
        """get_case() produces a chronological unified timeline with events, findings, and review actions."""
        c = Case(
            case_id="case_timeline_test",
            title="Timeline Test Case",
            description="desc",
            status="Open",
            severity="High",
            correlation_key_type="user_principal",
            correlation_key_value="dave",
            first_observed_at="2026-11-09T08:00:00Z",
            last_observed_at="2026-11-09T08:05:00Z",
            dedupe_key="timeline_test_key",
            metadata={"correlation_rationale": "Timeline rationale"},
        )
        cf = CaseFinding(case_id="case_timeline_test", finding_id=self.finding_id, correlation_rationale="Linked finding")
        ce = CaseEvent(case_id="case_timeline_test", event_id=self.event_id_1, relationship_type="evidence", correlation_rationale="Evt 1")
        self.repo.persist_cases_batch([c], [cf], [ce])

        self.repo.update_case_status("case_timeline_test", "UnderReview", operator_note="Analyst review")

        case_obj = self.repo.get_case("case_timeline_test")
        self.assertIsNotNone(case_obj)
        timeline = case_obj["timeline"]
        self.assertGreaterEqual(len(timeline), 3)

        types = [item["item_type"] for item in timeline]
        self.assertIn("event", types)
        self.assertIn("finding", types)
        self.assertIn("status_change", types)


if __name__ == "__main__":
    unittest.main()

