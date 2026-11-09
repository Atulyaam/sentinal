"""Unit tests for Detection and Findings Database Persistence (Migration 004)."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backend.detection.models import Finding
from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository


class TestFindingsDatabase(unittest.TestCase):
    """Test suite for findings and detection persistence."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_sentinel.db"
        self.conn = get_connection(self.db_path)
        apply_migrations(self.conn)
        self.repo = IngestionRepository(self.conn)

        # Baseline source and import job to support foreign keys
        self.source = self.repo.get_or_create_source(
            source_id="src_findings",
            source_name="Findings Test Source",
            parser_profile="auth_csv",
        )
        self.job = self.repo.create_import_job(
            import_id="imp_findings_001",
            source_id="src_findings",
            filename="auth.log",
            sha256="b" * 64,
            file_size=1024,
            parser_id="auth_csv",
            parser_version="1.0.0",
            status="completed",
        )

        # Create parsed records
        self.repo.persist_import_batch(
            import_id="imp_findings_001",
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
                        "attributes": {"user": "admin_user", "ip": "10.0.0.1"},
                        "raw_payload": '{"user":"admin_user"}',
                    },
                },
                {
                    "record_number": 2,
                    "parser_id": "auth_csv",
                    "parser_version": "1.0.0",
                    "record": {
                        "line_number": 2,
                        "timestamp": "2026-11-09T08:01:00Z",
                        "event_type": "user_authentication",
                        "attributes": {"user": "admin_user", "ip": "10.0.0.1"},
                        "raw_payload": '{"user":"admin_user"}',
                    },
                },
            ],
            errors=[],
        )

        unnorm = self.repo.get_unnormalized_records(import_id="imp_findings_001")
        self.assertEqual(len(unnorm), 2)
        rec1 = unnorm[0]
        rec2 = unnorm[1]

        self.event_id_1 = "evt_000000000000000000000001"
        self.event_id_2 = "evt_000000000000000000000002"
        events = [
            {
                "event_id": self.event_id_1,
                "import_id": "imp_findings_001",
                "record_id": rec1["record_id"],
                "source_id": rec1["source_id"],
                "record_number": rec1["record_number"],
                "timestamp": "2026-11-09T08:00:00Z",
                "source_type": "auth_csv",
                "source_file": rec1["filename"],
                "source_line": rec1["record_number"],
                "source_sha256": rec1["sha256"],
                "event_type": "user_authentication",
                "user_principal": "admin_user",
                "source_ip": "10.0.0.1",
                "target_resource": "/login",
                "status": "FAILURE",
                "attributes": {},
                "parser_version": "1.0.0",
                "normalization_version": "1.0.0",
            },
            {
                "event_id": self.event_id_2,
                "import_id": "imp_findings_001",
                "record_id": rec2["record_id"],
                "source_id": rec2["source_id"],
                "record_number": rec2["record_number"],
                "timestamp": "2026-11-09T08:01:00Z",
                "source_type": "auth_csv",
                "source_file": rec2["filename"],
                "source_line": rec2["record_number"],
                "source_sha256": rec2["sha256"],
                "event_type": "user_authentication",
                "user_principal": "admin_user",
                "source_ip": "10.0.0.1",
                "target_resource": "/login",
                "status": "SUCCESS",
                "attributes": {},
                "parser_version": "1.0.0",
                "normalization_version": "1.0.0",
            },
        ]
        self.repo.persist_normalized_events_batch(events=events, errors=[])

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    def test_migration_004_applied(self) -> None:
        """Verify Migration 004 is applied and tables exist."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT version, name FROM schema_migrations WHERE version = 4;")
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 4)
        self.assertEqual(row[1], "004_detection_rules_and_findings")

        # Verify required tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {r[0] for r in cursor.fetchall()}
        self.assertIn("detection_rules", tables)
        self.assertIn("findings", tables)
        self.assertIn("finding_events", tables)
        self.assertIn("rule_evaluations", tables)

    def test_default_rules_seeded(self) -> None:
        """Verify the 5 default rules are seeded into detection_rules table."""
        rules = self.repo.list_detection_rules()
        self.assertEqual(len(rules), 5)
        rule_ids = {r["rule_id"] for r in rules}
        self.assertSetEqual(rule_ids, {"AUTH-001", "AUTH-002", "WEB-001", "PRIV-001", "INGEST-001"})

    def test_persist_findings_and_deduplication(self) -> None:
        """Verify atomic batch persistence and duplicate suppression via uq_finding_dedupe."""
        finding1 = Finding(
            finding_id="find_test_001",
            rule_id="AUTH-001",
            rule_version="1.0.0",
            rule_config_hash="abc1234567890123",
            severity="Medium",
            status="open",
            title="Repeated Authentication Failures",
            description="Test finding description",
            first_observed_at="2026-11-09T10:00:00Z",
            last_observed_at="2026-11-09T10:05:00Z",
            matched_entity="admin_user",
            matched_conditions={"failure_count": 5},
            supporting_event_ids=[self.event_id_1, self.event_id_2],
            limitations="Could be user error.",
            dedupe_key="auth_fail:admin_user:12345",
        )

        res = self.repo.persist_findings_batch([finding1])
        self.assertEqual(res["persisted_findings"], 1)
        self.assertEqual(res["duplicate_findings"], 0)

        # Attempt to insert identical finding again -> dedupe suppresses it
        res_again = self.repo.persist_findings_batch([finding1])
        self.assertEqual(res_again["persisted_findings"], 0)
        self.assertEqual(res_again["duplicate_findings"], 1)

        # Verify finding exists in database
        retrieved = self.repo.get_finding("find_test_001")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["finding_id"], "find_test_001")
        self.assertEqual(retrieved["rule_id"], "AUTH-001")
        self.assertEqual(retrieved["status"], "open")
        self.assertEqual(retrieved["matched_conditions"]["failure_count"], 5)
        self.assertEqual(len(retrieved["supporting_events"]), 2)

    def test_list_findings_filtering_and_pagination(self) -> None:
        """Verify list_findings filters by severity, status, and rule_id with pagination."""
        f1 = Finding(
            finding_id="find_f1",
            rule_id="AUTH-001",
            rule_version="1.0.0",
            rule_config_hash="hash1",
            severity="Medium",
            status="open",
            title="Finding 1",
            description="desc",
            first_observed_at="2026-11-09T10:00:00Z",
            last_observed_at="2026-11-09T10:05:00Z",
            matched_entity="alice",
            matched_conditions={},
            supporting_event_ids=[self.event_id_1],
            limitations="none",
            dedupe_key="f1_dedupe",
        )
        f2 = Finding(
            finding_id="find_f2",
            rule_id="AUTH-002",
            rule_version="1.0.0",
            rule_config_hash="hash2",
            severity="High",
            status="acknowledged",
            title="Finding 2",
            description="desc",
            first_observed_at="2026-11-09T11:00:00Z",
            last_observed_at="2026-11-09T11:05:00Z",
            matched_entity="bob",
            matched_conditions={},
            supporting_event_ids=[self.event_id_2],
            limitations="none",
            dedupe_key="f2_dedupe",
        )
        self.repo.persist_findings_batch([f1, f2])

        # Filter by severity
        high_results, total = self.repo.list_findings(severity="High")
        self.assertEqual(total, 1)
        self.assertEqual(high_results[0]["finding_id"], "find_f2")

        # Filter by status
        open_results, total = self.repo.list_findings(status="open")
        self.assertEqual(total, 1)
        self.assertEqual(open_results[0]["finding_id"], "find_f1")

        # Filter by rule_id
        auth001_results, total = self.repo.list_findings(rule_id="AUTH-001")
        self.assertEqual(total, 1)
        self.assertEqual(auth001_results[0]["finding_id"], "find_f1")

        # Pagination: limit 1, offset 0
        page1, total = self.repo.list_findings(limit=1, offset=0)
        self.assertEqual(total, 2)
        self.assertEqual(len(page1), 1)

    def test_update_finding_status(self) -> None:
        """Verify finding status update validates inputs and updates timestamps."""
        f = Finding(
            finding_id="find_status_test",
            rule_id="AUTH-001",
            rule_version="1.0.0",
            rule_config_hash="hash",
            severity="Medium",
            status="open",
            title="Status Test",
            description="desc",
            first_observed_at="2026-11-09T10:00:00Z",
            last_observed_at="2026-11-09T10:05:00Z",
            matched_entity="user",
            matched_conditions={},
            supporting_event_ids=[self.event_id_1],
            limitations="none",
            dedupe_key="status_test_dedupe",
        )
        self.repo.persist_findings_batch([f])

        # Valid update
        updated = self.repo.update_finding_status("find_status_test", "resolved")
        self.assertIsNotNone(updated)
        self.assertEqual(updated["status"], "resolved")

        # Invalid status raises ValueError
        with self.assertRaises(ValueError):
            self.repo.update_finding_status("find_status_test", "not_a_valid_status")

        # Non-existent finding returns None
        not_found = self.repo.update_finding_status("find_nonexistent_999", "resolved")
        self.assertIsNone(not_found)

    def test_toggle_detection_rule_enabled(self) -> None:
        """Verify updating detection rule enabled state in database."""
        rule_before = self.repo.get_detection_rule("AUTH-001")
        self.assertIsNotNone(rule_before)
        self.assertEqual(rule_before["enabled"], 1)

        # Disable
        success = self.repo.update_detection_rule_enabled("AUTH-001", False)
        self.assertTrue(success)
        rule_after = self.repo.get_detection_rule("AUTH-001")
        self.assertEqual(rule_after["enabled"], 0)

        # Non-existent rule returns False
        missing = self.repo.update_detection_rule_enabled("FAKE-999", True)
        self.assertFalse(missing)

    def test_record_audit_and_stats(self) -> None:
        """Verify recording rule evaluation audit and calculating detection statistics."""
        audit_payload = {
            "evaluation_id": "eval_test_001",
            "evaluated_at": "2026-11-09T10:00:00Z",
            "rule_count": 5,
            "events_scanned": 2,
            "findings_generated": 1,
            "findings_duplicate": 0,
            "duration_ms": 12.5,
        }
        self.repo.record_evaluation_audit(audit_payload)

        stats = self.repo.get_detection_stats()
        self.assertEqual(stats["total_findings"], 0)
        self.assertIsNotNone(stats["last_evaluation"])
        self.assertEqual(stats["last_evaluation"]["evaluation_id"], "eval_test_001")
        self.assertEqual(stats["last_evaluation"]["rule_count"], 5)

    def test_get_finding_with_quarantined_records(self) -> None:
        """Verify get_finding populates quarantined_records when INGEST-001 matches normalization errors."""
        # 1. Insert a parsed record to satisfy foreign key constraint on normalization_errors(record_id)
        self.repo.persist_import_batch(
            import_id="imp_findings_001",
            status="completed",
            total_records=1,
            accepted_records=1,
            rejected_records=0,
            records=[
                {
                    "record_number": 99,
                    "parser_id": "auth_csv",
                    "parser_version": "1.0.0",
                    "record": {
                        "line_number": 99,
                        "timestamp": "2026-11-09T08:00:00",
                        "event_type": "user_authentication",
                        "attributes": {},
                        "raw_payload": "{}",
                    },
                }
            ],
            errors=[],
        )
        unnorm = self.repo.get_unnormalized_records(import_id="imp_findings_001")
        target_rec_id = unnorm[-1]["record_id"]

        # 2. Insert a normalization error referencing the parsed record
        self.repo.persist_normalized_events_batch(
            events=[],
            errors=[
                {
                    "error_id": "nerr_quarantine_01",
                    "record_id": target_rec_id,
                    "import_id": "imp_findings_001",
                    "record_number": 99,
                    "error_code": "NORM_TIMEZONE_UNKNOWN",
                    "safe_error_message": "Timestamp lacks timezone",
                }
            ],
        )

        f = Finding(
            finding_id="find_ingest_quarantine_test",
            rule_id="INGEST-001",
            rule_version="1.0.0",
            rule_config_hash="a" * 64,
            severity="Info",
            status="open",
            title="Quarantined records anomaly",
            description="Quarantined records detected",
            first_observed_at="2026-11-09T10:00:00Z",
            last_observed_at="2026-11-09T10:00:00Z",
            matched_entity="imp_findings_001",
            matched_conditions={"record_ids": [target_rec_id], "import_id": "imp_findings_001"},
            supporting_event_ids=[],
            limitations="none",
            dedupe_key="ingest_quarantine_dedupe",
        )
        self.repo.persist_findings_batch([f])

        fetched = self.repo.get_finding("find_ingest_quarantine_test")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["supporting_events"], [])
        self.assertEqual(len(fetched["quarantined_records"]), 1)
        self.assertEqual(fetched["quarantined_records"][0]["error_id"], "nerr_quarantine_01")
        self.assertEqual(fetched["quarantined_records"][0]["error_code"], "NORM_TIMEZONE_UNKNOWN")


if __name__ == "__main__":
    unittest.main()
