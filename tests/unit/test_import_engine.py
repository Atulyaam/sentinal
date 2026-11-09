"""Unit tests for Sentinel Import Engine, deduplication, and sanitization."""

import json
import tempfile
import unittest
from pathlib import Path

from backend.config.settings import Settings
from backend.ingestion.engine import ImportEngine
from backend.ingestion.sanitizer import sanitize_attributes, sanitize_string
from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository


class TestImportEngine(unittest.TestCase):
    """Test suite covering ingestion engine execution, deduplication, and redaction."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_import.db")
        self.conn = get_connection(self.db_path)
        apply_migrations(self.conn)
        self.repo = IngestionRepository(self.conn)

        self.settings = Settings(
            app_name="Test Sentinel",
            version="0.2.0",
            host="127.0.0.1",
            port=8000,
            environment="test",
            log_level="DEBUG",
            approved_inbox="./inbox",
            allowed_origins=("http://127.0.0.1:5173",),
            db_path=self.db_path,
            max_import_size_bytes=1024 * 1024,  # 1 MB for testing
            max_records_per_file=500,
        )
        self.engine = ImportEngine(repository=self.repo, settings=self.settings)

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_sanitizer_scrubs_secrets(self):
        """Sanitizer must redact passwords, tokens, cookies, session IDs, arrays, and headers."""
        raw_attrs = {
            "username": "admin_user",
            "password": "SuperSecretPassword123!",
            "api_key": "sec_live_9876543210abcdef",
            "session_id": "sess_secret_active_token_99",
            "cookie": "sessionid=xyz123; tracking=abc",
            "metadata": {
                "auth_token": "jwt_secret_token_value",
                "safe_field": "visible_info",
                "token_list": ["token_val_1", "safe_val"],
            },
            "array_of_dicts": [
                {"secret_key": "nested_secret_1", "item_name": "device_1"},
                {"session_token": "sess_token_2", "item_name": "device_2"},
            ],
        }
        sanitized = sanitize_attributes(raw_attrs)
        self.assertEqual(sanitized["username"], "admin_user")
        self.assertEqual(sanitized["password"], "[REDACTED]")
        self.assertEqual(sanitized["api_key"], "[REDACTED]")
        self.assertEqual(sanitized["session_id"], "[REDACTED]")
        self.assertEqual(sanitized["cookie"], "[REDACTED]")
        self.assertEqual(sanitized["metadata"]["auth_token"], "[REDACTED]")
        self.assertEqual(sanitized["metadata"]["safe_field"], "visible_info")
        self.assertEqual(sanitized["array_of_dicts"][0]["secret_key"], "[REDACTED]")
        self.assertEqual(sanitized["array_of_dicts"][0]["item_name"], "device_1")
        self.assertEqual(sanitized["array_of_dicts"][1]["session_token"], "[REDACTED]")

        raw_str = (
            "Authorization: Bearer my_secret_token_123456789 and password=SuperSecretPassword123! "
            "Cookie: sessionid=1234567890abcdef and api_key=xyz987654321"
        )
        sanitized_str = sanitize_string(raw_str)
        self.assertNotIn("my_secret_token_123456789", sanitized_str)
        self.assertNotIn("SuperSecretPassword123!", sanitized_str)
        self.assertNotIn("sessionid=1234567890abcdef", sanitized_str)
        self.assertNotIn("xyz987654321", sanitized_str)
        self.assertIn("Bearer [REDACTED]", sanitized_str)
        self.assertIn("password=[REDACTED]", sanitized_str)
        self.assertIn("Cookie: [REDACTED]", sanitized_str)
        self.assertIn("api_key=[REDACTED]", sanitized_str)

    def test_successful_ingestion(self):
        """Engine must process valid JSONL and persist job and records in SQLite."""
        log_bytes = (
            b'{"timestamp": "2026-11-09T08:00:00Z", "event_type": "login", "user": "alice"}\n'
            b'{"timestamp": "2026-11-09T08:01:00Z", "event_type": "logout", "user": "alice"}\n'
        )

        result = self.engine.ingest_file(
            source_id="src_manual_default",
            filename="auth.jsonl",
            content_bytes=log_bytes,
            parser_id="generic_jsonl",
        )

        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["duplicate"])
        self.assertEqual(result["total_records"], 2)
        self.assertEqual(result["accepted_records"], 2)
        self.assertEqual(result["rejected_records"], 0)

        # Verify database records
        job = self.repo.get_import_job(result["import_id"])
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "completed")

        cursor = self.conn.cursor()
        cursor.execute("SELECT count(*) FROM parsed_records WHERE import_id = ?;", (result["import_id"],))
        self.assertEqual(cursor.fetchone()[0], 2)

    def test_deduplication_skips_identical_file(self):
        """Engine must skip duplicate import of identical file content and parser profile."""
        log_bytes = b'{"timestamp": "2026-11-09T08:00:00Z", "event": "test"}\n'

        res1 = self.engine.ingest_file(
            source_id="src_manual_default",
            filename="events.jsonl",
            content_bytes=log_bytes,
            parser_id="generic_jsonl",
        )
        self.assertEqual(res1["status"], "completed")
        self.assertFalse(res1["duplicate"])

        # Second import with identical content and parser
        res2 = self.engine.ingest_file(
            source_id="src_manual_default",
            filename="events_copy.jsonl",
            content_bytes=log_bytes,
            parser_id="generic_jsonl",
        )
        self.assertEqual(res2["status"], "skipped")
        self.assertTrue(res2["duplicate"])
        self.assertEqual(res2["import_id"], res1["import_id"])

        # Verify no duplicate records were inserted
        cursor = self.conn.cursor()
        cursor.execute("SELECT count(*) FROM parsed_records;")
        self.assertEqual(cursor.fetchone()[0], 1)

    def test_partial_ingestion_with_row_errors(self):
        """Engine must record partial status and store row errors when some records fail."""
        csv_bytes = (
            b"timestamp,username,auth_result\n"
            b"2026-11-09T08:00:00Z,valid_user,SUCCESS\n"
            b"2026-11-09T08:01:00Z,invalid_user,UNKNOWN_STATUS\n"
        )

        result = self.engine.ingest_file(
            source_id="src_manual_default",
            filename="auth.csv",
            content_bytes=csv_bytes,
            parser_id="auth_csv",
        )

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["total_records"], 2)
        self.assertEqual(result["accepted_records"], 1)
        self.assertEqual(result["rejected_records"], 1)

        job = self.repo.get_import_job(result["import_id"])
        self.assertEqual(job["status"], "partial")
        self.assertEqual(len(job["errors"]), 1)
        self.assertEqual(job["errors"][0]["record_number"], 3)  # line 3 is row 2
        self.assertIn("Invalid auth_result", job["errors"][0]["safe_error_message"])

    def test_file_size_limit_rejection(self):
        """Engine must reject files exceeding configured maximum size."""
        huge_bytes = b"X" * (self.settings.max_import_size_bytes + 10)
        result = self.engine.ingest_file(
            source_id="src_manual_default",
            filename="oversized.log",
            content_bytes=huge_bytes,
            parser_id="generic_jsonl",
        )
        self.assertEqual(result["status"], "rejected")
        self.assertIn("exceeds configured maximum limit", result["error"])

    def test_empty_file_rejection(self):
        """Engine must reject empty files."""
        result = self.engine.ingest_file(
            source_id="src_manual_default",
            filename="empty.log",
            content_bytes=b"",
            parser_id="generic_jsonl",
        )
        self.assertEqual(result["status"], "rejected")
        self.assertIn("empty file", result["error"])


if __name__ == "__main__":
    unittest.main()
