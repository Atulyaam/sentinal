"""Unit tests for Sentinel Approved Inbox Scanner."""

import tempfile
import time
import unittest
from pathlib import Path

from backend.config.settings import Settings
from backend.ingestion.engine import ImportEngine
from backend.ingestion.scanner import (
    InboxScanner,
    is_safe_inbox_path,
    is_symlink_or_junction,
)
from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository


class TestInboxScanner(unittest.TestCase):
    """Test suite covering inbox scanning, path security, idempotency, and pause control."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.inbox_path = Path(self.temp_dir.name) / "inbox"
        self.inbox_path.mkdir(parents=True, exist_ok=True)
        self.db_path = str(Path(self.temp_dir.name) / "test_scanner.db")

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
            approved_inbox=str(self.inbox_path),
            allowed_origins=("http://127.0.0.1:5173",),
            db_path=self.db_path,
            max_import_size_bytes=1024 * 1024,
            max_records_per_file=500,
        )

        self.engine = ImportEngine(repository=self.repo, settings=self.settings)
        self.scanner = InboxScanner(
            engine=self.engine,
            repository=self.repo,
            settings=self.settings,
            poll_interval_seconds=0.1,
            stability_wait_seconds=0.01,
        )

    def tearDown(self):
        self.scanner.stop_background_scanning()
        self.conn.close()
        self.temp_dir.cleanup()

    def test_monitoring_disabled_by_default(self):
        """Inbox scanner background monitoring must be disabled by default."""
        self.assertFalse(self.scanner.is_running)

    def test_path_safety_validation(self):
        """Scanner must reject roots, user homes, and system directories."""
        self.assertTrue(is_safe_inbox_path(self.inbox_path))
        self.assertFalse(is_safe_inbox_path("C:\\"))
        self.assertFalse(is_safe_inbox_path("/"))
        self.assertFalse(is_safe_inbox_path(Path.home()))
        self.assertFalse(is_safe_inbox_path("C:\\Windows\\System32"))

    def test_explicit_parser_profile_used_never_inferred_from_filename(self):
        """Scanner must strictly use the source's configured parser profile, never guessing from filename."""
        # Configure source with auth_csv profile
        self.repo.get_or_create_source(
            source_id="src_inbox_approved",
            source_name="Approved Local Inbox",
            parser_profile="auth_csv",
            configured_path=str(self.inbox_path),
            enabled=1,
        )

        # Place file with arbitrary name (e.g., custom_export.log) but valid auth_csv content
        test_file = self.inbox_path / "custom_export.log"
        test_file.write_text("timestamp,username,auth_result\n2026-11-09T09:30:00Z,operator_1,SUCCESS\n", encoding="utf-8")

        results = self.scanner.scan_once()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "completed")
        # Ensure parser_id used is the explicitly configured auth_csv, NOT generic_jsonl despite .log extension
        self.assertEqual(results[0]["parser_id"], "auth_csv")

    def test_disabled_source_skips_scanning(self):
        """Disabled source (enabled=0) must not ingest files."""
        self.repo.get_or_create_source(
            source_id="src_inbox_approved",
            source_name="Approved Local Inbox",
            parser_profile="generic_jsonl",
            configured_path=str(self.inbox_path),
            enabled=0,  # Explicitly disabled
        )
        test_file = self.inbox_path / "disabled_test.jsonl"
        test_file.write_text('{"event": "should_not_ingest"}\n', encoding="utf-8")

        results = self.scanner.scan_once()
        self.assertEqual(len(results), 0)

    def test_scan_once_ingests_and_preserves_files(self):
        """Scanner must ingest files without deleting or moving them."""
        test_file = self.inbox_path / "events.jsonl"
        test_file.write_text('{"timestamp": "2026-11-09T09:30:00Z", "event": "scanner_test"}\n', encoding="utf-8")

        results = self.scanner.scan_once()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "completed")
        self.assertFalse(results[0]["duplicate"])

        # Crucial check: original file MUST still exist untouched
        self.assertTrue(test_file.exists())

        # Second scan cycle: file is still there, but deduplication skips it
        results2 = self.scanner.scan_once()
        self.assertEqual(len(results2), 1)
        self.assertEqual(results2[0]["status"], "skipped")
        self.assertTrue(results2[0]["duplicate"])

    def test_non_recursive_scanning(self):
        """Scanner must ignore nested subdirectories."""
        subdir = self.inbox_path / "nested_subdir"
        subdir.mkdir()
        nested_file = subdir / "nested_events.jsonl"
        nested_file.write_text('{"event": "nested"}\n', encoding="utf-8")

        results = self.scanner.scan_once()
        self.assertEqual(len(results), 0)

    def test_pause_and_resume(self):
        """Scanner must not process files while paused."""
        self.scanner.pause()
        self.assertTrue(self.scanner.is_paused)

        test_file = self.inbox_path / "paused_test.jsonl"
        test_file.write_text('{"event": "paused_event"}\n', encoding="utf-8")

        results = self.scanner.scan_once()
        self.assertEqual(len(results), 0)

        # Resume scanner
        self.scanner.resume()
        self.assertFalse(self.scanner.is_paused)

        results_resumed = self.scanner.scan_once()
        self.assertEqual(len(results_resumed), 1)
        self.assertEqual(results_resumed[0]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
