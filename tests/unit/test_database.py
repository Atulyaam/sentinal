"""Unit tests for SQLite database persistence, migrations, and transactional repository."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository


class TestDatabasePersistence(unittest.TestCase):
    """Test suite for SQLite schema, foreign keys, unique constraints, and transactions."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_sentinel.db"
        self.conn = get_connection(self.db_path)
        apply_migrations(self.conn)
        self.repo = IngestionRepository(self.conn)

    def tearDown(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_repeatable_migrations(self) -> None:
        """Applying migrations multiple times must be completely idempotent."""
        apply_migrations(self.conn)
        cursor = self.conn.cursor()
        cursor.execute("SELECT count(*) FROM schema_migrations WHERE version = 1;")
        self.assertEqual(cursor.fetchone()[0], 1)

    def test_foreign_key_enforcement(self) -> None:
        """Foreign key constraint must prevent creating import job with non-existent source_id."""
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.create_import_job(
                import_id="imp_invalid_fk",
                source_id="src_non_existent",
                filename="test.log",
                sha256="a" * 64,
                file_size=100,
                parser_id="generic_jsonl",
                parser_version="1.0.0",
            )

    def test_unique_hash_parser_constraint(self) -> None:
        """Inserting identical (sha256, parser_id, parser_version) must violate unique constraint."""
        # Valid source
        self.repo.get_or_create_source("src_test", "Test Source", "generic_jsonl")

        # First import job
        self.repo.create_import_job(
            import_id="imp_001",
            source_id="src_test",
            filename="auth.jsonl",
            sha256="b" * 64,
            file_size=250,
            parser_id="generic_jsonl",
            parser_version="1.0.0",
        )

        # Attempt duplicate import with identical sha256 + parser + version
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.create_import_job(
                import_id="imp_002",
                source_id="src_test",
                filename="auth_copy.jsonl",
                sha256="b" * 64,
                file_size=250,
                parser_id="generic_jsonl",
                parser_version="1.0.0",
            )

    def test_transactional_batch_persistence(self) -> None:
        """Verify atomic insertion of job metadata, parsed records, and error rows."""
        self.repo.get_or_create_source("src_test", "Test Source", "generic_jsonl")
        self.repo.create_import_job(
            import_id="imp_batch",
            source_id="src_test",
            filename="data.jsonl",
            sha256="c" * 64,
            file_size=500,
            parser_id="generic_jsonl",
            parser_version="1.0.0",
        )

        records = [
            {"record_number": 1, "parser_id": "generic_jsonl", "parser_version": "1.0.0", "record": {"user": "alice"}},
            {"record_number": 2, "parser_id": "generic_jsonl", "parser_version": "1.0.0", "record": {"user": "bob"}},
        ]
        errors = [
            {"record_number": 3, "error_code": "MALFORMED_JSON", "safe_error_message": "Invalid JSON syntax on line 3"},
        ]

        result = self.repo.persist_import_batch(
            import_id="imp_batch",
            status="completed_with_errors",
            total_records=3,
            accepted_records=2,
            rejected_records=1,
            records=records,
            errors=errors,
        )

        self.assertEqual(result["status"], "completed_with_errors")
        self.assertEqual(result["total_records"], 3)
        self.assertEqual(result["accepted_records"], 2)
        self.assertEqual(result["rejected_records"], 1)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["record_number"], 3)

    def test_persistence_across_reconnect(self) -> None:
        """Database state must persist reliably after connection close and reopening."""
        self.repo.get_or_create_source("src_persist", "Persist Source", "auth_csv")
        self.repo.create_import_job(
            import_id="imp_persist",
            source_id="src_persist",
            filename="auth.csv",
            sha256="d" * 64,
            file_size=1024,
            parser_id="auth_csv",
            parser_version="1.0.0",
            status="completed",
        )
        self.conn.close()

        # Reopen connection
        new_conn = get_connection(self.db_path)
        try:
            new_repo = IngestionRepository(new_conn)
            job = new_repo.get_import_job("imp_persist")
            self.assertIsNotNone(job)
            self.assertEqual(job["filename"], "auth.csv")
            self.assertEqual(job["status"], "completed")
        finally:
            new_conn.close()
            # Reopen connection for tearDown cleanup
            self.conn = get_connection(self.db_path)

    def test_reconcile_pending_jobs_on_restart(self) -> None:
        """Dangling 'pending' jobs from prior crashes must reconcile to 'failed'."""
        self.repo.get_or_create_source("src_test", "Test Source", "generic_jsonl")
        self.repo.create_import_job(
            import_id="imp_dangling",
            source_id="src_test",
            filename="dangling.log",
            sha256="e" * 64,
            file_size=300,
            parser_id="generic_jsonl",
            parser_version="1.0.0",
            status="pending",
        )

        reconciled_count = self.repo.reconcile_pending_jobs()
        self.assertEqual(reconciled_count, 1)

        job = self.repo.get_import_job("imp_dangling")
        self.assertEqual(job["status"], "failed")
        self.assertIn("Server restarted", job["error_summary"])


if __name__ == "__main__":
    unittest.main()
