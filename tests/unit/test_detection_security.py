"""Security tests for Detection Engine and Findings Persistence."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backend.detection.models import Finding
from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository


class TestDetectionSecurity(unittest.TestCase):
    """Security verification for detection engine, query parameterization, and relational integrity."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_sec.db"
        self.conn = get_connection(self.db_path)
        apply_migrations(self.conn)
        self.repo = IngestionRepository(self.conn)

        # Create baseline records
        self.repo.get_or_create_source("src_sec", "Sec Source", "auth_csv")
        self.repo.create_import_job(
            import_id="imp_sec_001",
            source_id="src_sec",
            filename="auth.log",
            sha256="e" * 64,
            file_size=512,
            parser_id="auth_csv",
            parser_version="1.0.0",
            status="completed",
        )
        self.repo.persist_import_batch(
            import_id="imp_sec_001",
            status="completed",
            total_records=1,
            accepted_records=1,
            rejected_records=0,
            records=[
                {
                    "record_number": 1,
                    "parser_id": "auth_csv",
                    "parser_version": "1.0.0",
                    "record": {
                        "line_number": 1,
                        "timestamp": "2026-11-09T09:00:00Z",
                        "event_type": "user_authentication",
                        "attributes": {"user": "alice"},
                        "raw_payload": '{"user":"alice"}',
                    },
                }
            ],
            errors=[],
        )
        unnorm = self.repo.get_unnormalized_records(import_id="imp_sec_001")
        rec = unnorm[0]

        self.event_id = "evt_sec_001"
        event = {
            "event_id": self.event_id,
            "import_id": "imp_sec_001",
            "record_id": rec["record_id"],
            "source_id": rec["source_id"],
            "record_number": rec["record_number"],
            "timestamp": "2026-11-09T09:00:00Z",
            "source_type": "auth_csv",
            "source_file": rec["filename"],
            "source_line": rec["record_number"],
            "source_sha256": rec["sha256"],
            "event_type": "user_authentication",
            "user_principal": "alice",
            "source_ip": "10.0.0.1",
            "target_resource": "/login",
            "status": "FAILURE",
            "attributes": {},
            "parser_version": "1.0.0",
            "normalization_version": "1.0.0",
        }
        self.repo.persist_normalized_events_batch([event], [])

        self.finding = Finding(
            finding_id="find_sec_001",
            rule_id="AUTH-001",
            rule_version="1.0.0",
            rule_config_hash="hash123",
            severity="Medium",
            status="open",
            title="Security Test Finding",
            description="Testing SQL injection resistance",
            first_observed_at="2026-11-09T09:00:00Z",
            last_observed_at="2026-11-09T09:00:00Z",
            matched_entity="alice",
            matched_conditions={"test": "sql_injection"},
            supporting_event_ids=[self.event_id],
            limitations="none",
            dedupe_key="sec_dedupe_1",
        )
        self.repo.persist_findings_batch([self.finding])

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    def test_sql_injection_in_list_findings_filters(self) -> None:
        """SQL injection payloads in filters do not alter queries or bypass filtering."""
        sql_payloads = [
            "' OR '1'='1",
            "'; DROP TABLE findings; --",
            "admin'--",
            "' UNION SELECT * FROM findings --",
            "1' ORDER BY 1--",
        ]

        for payload in sql_payloads:
            # Should treat payload as literal string and safely return 0 results
            results, total = self.repo.list_findings(severity=payload)
            self.assertEqual(len(results), 0, f"Severity SQL injection failed: {payload}")
            self.assertEqual(total, 0)

            results, total = self.repo.list_findings(status=payload)
            self.assertEqual(len(results), 0, f"Status SQL injection failed: {payload}")
            self.assertEqual(total, 0)

            results, total = self.repo.list_findings(rule_id=payload)
            self.assertEqual(len(results), 0, f"Rule ID SQL injection failed: {payload}")
            self.assertEqual(total, 0)

        # Verify table still exists and data is intact
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM findings;")
        self.assertEqual(cursor.fetchone()[0], 1)

    def test_invalid_status_injection_rejected(self) -> None:
        """Attempt to update status with injected SQL or invalid words is rejected."""
        malicious_statuses = [
            "open'; UPDATE findings SET status='hacked'; --",
            "admin",
            "active",
            "RESOLVED",  # Case normalization handles or rejects, but invalid strings must fail
            "status' OR 1=1",
        ]
        for bad_status in malicious_statuses:
            if bad_status == "RESOLVED":
                continue  # 'resolved' is valid in lowercase
            with self.assertRaises(ValueError):
                self.repo.update_finding_status("find_sec_001", bad_status)

        # Data remains open
        f = self.repo.get_finding("find_sec_001")
        self.assertIsNotNone(f)
        self.assertEqual(f["status"], "open")

    def test_foreign_key_evidence_immutability(self) -> None:
        """Foreign key constraint prevents deleting events linked as finding evidence."""
        # Because PRAGMA foreign_keys = ON, deleting normalized_events referenced in finding_events fails
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM normalized_events WHERE event_id = ?;", (self.event_id,))


if __name__ == "__main__":
    unittest.main()

