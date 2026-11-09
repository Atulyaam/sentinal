"""Unit tests for Normalization Database Migration 002 and Repository operations."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository


class TestNormalizationDatabase(unittest.TestCase):
    """Test suite for Migration 002 and normalization persistence methods."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_norm.db"
        self.conn = get_connection(self.db_path)
        apply_migrations(self.conn)
        self.repo = IngestionRepository(self.conn)

        # Setup baseline source and import job for testing FK relationships
        self.source = self.repo.get_or_create_source(
            source_id="src_test",
            source_name="Test Source",
            parser_profile="generic_jsonl",
        )
        self.job = self.repo.create_import_job(
            import_id="imp_test_001",
            source_id="src_test",
            filename="audit.jsonl",
            sha256="a" * 64,
            file_size=1024,
            parser_id="generic_jsonl",
            parser_version="1.0.0",
            status="completed",
        )

        # Create sample parsed records
        self.repo.persist_import_batch(
            import_id="imp_test_001",
            status="completed",
            total_records=2,
            accepted_records=2,
            rejected_records=0,
            records=[
                {
                    "record_number": 1,
                    "parser_id": "generic_jsonl",
                    "parser_version": "1.0.0",
                    "record": {
                        "line_number": 1,
                        "timestamp": "2026-11-09T08:00:00Z",
                        "event_type": "user_login",
                        "attributes": {"user": "alice", "ip": "10.0.0.1"},
                        "raw_payload": '{"user":"alice"}',
                    },
                },
                {
                    "record_number": 2,
                    "parser_id": "generic_jsonl",
                    "parser_version": "1.0.0",
                    "record": {
                        "line_number": 2,
                        "timestamp": "2026-11-09T08:01:00Z",
                        "event_type": "user_logout",
                        "attributes": {"user": "bob", "ip": "10.0.0.2"},
                        "raw_payload": '{"user":"bob"}',
                    },
                },
            ],
            errors=[],
        )

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    def test_migrations_applied(self) -> None:
        """Verify schema_migrations table tracks migration 1 and 2."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT version, name FROM schema_migrations ORDER BY version ASC;")
        versions = cursor.fetchall()
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0][0], 1)
        self.assertEqual(versions[1][0], 2)
        self.assertEqual(versions[1][1], "002_canonical_events_and_provenance")

    def test_get_unnormalized_records(self) -> None:
        """Verify unnormalized records are discovered correctly."""
        records = self.repo.get_unnormalized_records(import_id="imp_test_001")
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["record_number"], 1)
        self.assertEqual(records[1]["record_number"], 2)

    def test_persist_and_query_normalized_events(self) -> None:
        """Verify batch persisting of normalized events and querying."""
        unnorm = self.repo.get_unnormalized_records(import_id="imp_test_001")
        rec1 = unnorm[0]

        event_payload = {
            "event_id": "evt_test_001",
            "import_id": rec1["import_id"],
            "record_id": rec1["record_id"],
            "source_id": rec1["source_id"],
            "record_number": rec1["record_number"],
            "timestamp": "2026-11-09T08:00:00Z",
            "source_type": "generic_jsonl",
            "source_file": rec1["filename"],
            "source_line": rec1["record_number"],
            "source_sha256": rec1["sha256"],
            "event_type": "user_login",
            "user_principal": "alice",
            "source_ip": "10.0.0.1",
            "target_resource": "/app",
            "status": "SUCCESS",
            "attributes": {"extra": "data"},
            "normalization_version": "1.0.0",
        }

        res = self.repo.persist_normalized_events_batch(events=[event_payload], errors=[])
        self.assertEqual(res["persisted_events"], 1)
        self.assertEqual(res["persisted_errors"], 0)

        # Query single event
        evt = self.repo.get_normalized_event("evt_test_001")
        self.assertIsNotNone(evt)
        self.assertEqual(evt["event_id"], "evt_test_001")
        self.assertEqual(evt["user_principal"], "alice")
        self.assertEqual(evt["attributes"], {"extra": "data"})

        # Now only 1 record should be unnormalized
        remaining = self.repo.get_unnormalized_records(import_id="imp_test_001")
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["record_number"], 2)

    def test_idempotency_prevents_duplicate_events(self) -> None:
        """Verify that persisting the same event/record again is safely ignored."""
        unnorm = self.repo.get_unnormalized_records(import_id="imp_test_001")
        rec1 = unnorm[0]

        event_payload = {
            "event_id": "evt_test_001",
            "import_id": rec1["import_id"],
            "record_id": rec1["record_id"],
            "source_id": rec1["source_id"],
            "record_number": rec1["record_number"],
            "timestamp": "2026-11-09T08:00:00Z",
            "source_type": "generic_jsonl",
            "source_file": rec1["filename"],
            "source_line": rec1["record_number"],
            "source_sha256": rec1["sha256"],
            "event_type": "user_login",
            "user_principal": "alice",
            "source_ip": "10.0.0.1",
            "target_resource": "/app",
            "status": "SUCCESS",
            "attributes": {},
            "normalization_version": "1.0.0",
        }

        # First persistence
        res1 = self.repo.persist_normalized_events_batch(events=[event_payload], errors=[])
        self.assertEqual(res1["persisted_events"], 1)

        # Second persistence of same event
        res2 = self.repo.persist_normalized_events_batch(events=[event_payload], errors=[])
        self.assertEqual(res2["persisted_events"], 0)  # Ignored due to unique constraint

        events, total = self.repo.list_normalized_events()
        self.assertEqual(total, 1)

    def test_normalization_errors_persistence(self) -> None:
        """Verify normalization errors are stored and queried."""
        unnorm = self.repo.get_unnormalized_records(import_id="imp_test_001")
        rec2 = unnorm[1]

        error_payload = {
            "error_id": "nerr_001",
            "record_id": rec2["record_id"],
            "import_id": rec2["import_id"],
            "record_number": rec2["record_number"],
            "error_code": "NORM_INVALID_TIMESTAMP",
            "safe_error_message": "Invalid timestamp format",
        }

        res = self.repo.persist_normalized_events_batch(events=[], errors=[error_payload])
        self.assertEqual(res["persisted_errors"], 1)

        errs = self.repo.list_normalization_errors(import_id="imp_test_001")
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0]["error_code"], "NORM_INVALID_TIMESTAMP")

        # Record with error should no longer be fetched by get_unnormalized_records
        remaining = self.repo.get_unnormalized_records(import_id="imp_test_001")
        self.assertEqual(len(remaining), 1)  # Only rec1 remains unnormalized

    def test_list_normalized_events_filtering(self) -> None:
        """Verify filtering by event_type and user_principal."""
        unnorm = self.repo.get_unnormalized_records(import_id="imp_test_001")
        rec1, rec2 = unnorm[0], unnorm[1]

        events = [
            {
                "event_id": "evt_1",
                "import_id": rec1["import_id"],
                "record_id": rec1["record_id"],
                "source_id": rec1["source_id"],
                "record_number": 1,
                "timestamp": "2026-11-09T08:00:00Z",
                "source_type": "generic_jsonl",
                "source_file": "audit.jsonl",
                "source_line": 1,
                "source_sha256": "a" * 64,
                "event_type": "user_login",
                "user_principal": "alice",
                "source_ip": "10.0.0.1",
                "target_resource": "/app",
                "status": "SUCCESS",
                "attributes": {},
                "normalization_version": "1.0.0",
            },
            {
                "event_id": "evt_2",
                "import_id": rec2["import_id"],
                "record_id": rec2["record_id"],
                "source_id": rec2["source_id"],
                "record_number": 2,
                "timestamp": "2026-11-09T08:01:00Z",
                "source_type": "generic_jsonl",
                "source_file": "audit.jsonl",
                "source_line": 2,
                "source_sha256": "a" * 64,
                "event_type": "user_logout",
                "user_principal": "bob",
                "source_ip": "10.0.0.2",
                "target_resource": "/app",
                "status": "SUCCESS",
                "attributes": {},
                "normalization_version": "1.0.0",
            },
        ]
        self.repo.persist_normalized_events_batch(events=events, errors=[])

        # Filter by event_type
        evts_login, total = self.repo.list_normalized_events(event_type="user_login")
        self.assertEqual(total, 1)
        self.assertEqual(evts_login[0]["event_id"], "evt_1")

        # Filter by user_principal
        evts_bob, total = self.repo.list_normalized_events(user_principal="bob")
        self.assertEqual(total, 1)
        self.assertEqual(evts_bob[0]["event_id"], "evt_2")

        # Stats
        stats = self.repo.get_normalization_stats()
        self.assertEqual(stats["total_normalized_events"], 2)
        self.assertEqual(stats["events_by_type"], {"user_login": 1, "user_logout": 1})
        self.assertEqual(stats["pending_unnormalized_records"], 0)


if __name__ == "__main__":
    unittest.main()

