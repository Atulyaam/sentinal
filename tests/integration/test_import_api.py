"""Integration tests for Sentinel Manual Import API endpoints."""

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from backend.api import handler
from backend.api.server import create_server
from backend.config.settings import Settings


class TestImportAPI(unittest.TestCase):
    """Integration test suite for /api/import, /api/imports, /api/parsers, and /api/sources."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = str(Path(cls.temp_dir.name) / "test_api.db")

        # Point environment to test database and inbox
        os.environ["SENTINEL_DB_PATH"] = cls.db_path
        os.environ["SENTINEL_ALLOWED_ORIGINS"] = "http://127.0.0.1:5173"

        # Reset handler globals to ensure clean test state
        handler._repo = None
        handler._engine = None

        cls.server = create_server(host="127.0.0.1", port=0)
        cls.host, cls.port = cls.server.server_address
        cls.base_url = f"http://{cls.host}:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2.0)

        # Close active connection before directory cleanup
        if handler._repo and handler._repo.conn:
            handler._repo.conn.close()
            handler._repo = None
            handler._engine = None

        cls.temp_dir.cleanup()
        os.environ.pop("SENTINEL_DB_PATH", None)
        os.environ.pop("SENTINEL_ALLOWED_ORIGINS", None)

    def test_get_parsers_endpoint(self):
        """GET /api/parsers must return all registered parser profiles."""
        req = urllib.request.Request(f"{self.base_url}/api/parsers")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("parsers", data)
            parser_ids = [p["id"] for p in data["parsers"]]
            self.assertIn("generic_jsonl", parser_ids)
            self.assertIn("auth_csv", parser_ids)
            self.assertIn("web_access_csv", parser_ids)

    def test_get_sources_endpoint(self):
        """GET /api/sources must return configured sources including default manual source."""
        req = urllib.request.Request(f"{self.base_url}/api/sources")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("sources", data)
            source_ids = [s["source_id"] for s in data["sources"]]
            self.assertIn("src_manual_default", source_ids)

    def test_post_import_json_payload(self):
        """POST /api/import with JSON payload must ingest records and return completed status."""
        payload = {
            "filename": "test_events.jsonl",
            "parser_id": "generic_jsonl",
            "content_text": '{"timestamp": "2026-11-09T09:00:00Z", "event_type": "user_action", "actor": "bob"}\n',
        }
        body_bytes = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/api/import",
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "Origin": "http://127.0.0.1:5173",
            },
            method="POST",
        )

        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "http://127.0.0.1:5173")
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "completed")
            self.assertFalse(data.get("duplicate"))
            self.assertEqual(data.get("total_records"), 1)
            self.assertEqual(data.get("accepted_records"), 1)
            import_id = data.get("import_id")
            self.assertIsNotNone(import_id)

        # Test deduplication on re-upload
        req_dup = urllib.request.Request(
            f"{self.base_url}/api/import",
            data=body_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_dup) as resp:
            self.assertEqual(resp.status, 200)
            dup_data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(dup_data.get("status"), "skipped")
            self.assertTrue(dup_data.get("duplicate"))
            self.assertEqual(dup_data.get("import_id"), import_id)

    def test_post_import_multipart_payload(self):
        """POST /api/import with multipart/form-data must successfully ingest CSV file."""
        boundary = "---------------------------974767299852498929531610575"
        csv_data = "timestamp,username,auth_result\n2026-11-09T09:01:00Z,charlie,SUCCESS\n"
        
        multipart_body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="parser_id"\r\n\r\n'
            f"auth_csv\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="auth_test.csv"\r\n'
            f"Content-Type: text/csv\r\n\r\n"
            f"{csv_data}\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/api/import",
            data=multipart_body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Origin": "http://127.0.0.1:5173",
            },
            method="POST",
        )

        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "completed")
            self.assertEqual(data.get("accepted_records"), 1)
            self.assertEqual(data.get("filename"), "auth_test.csv")

    def test_list_and_get_imports(self):
        """GET /api/imports and GET /api/imports/{id} must retrieve genuine persisted jobs."""
        # 1. First import a test record to ensure data exists independently of test ordering
        payload = {
            "filename": "history_test.jsonl",
            "parser_id": "generic_jsonl",
            "content_text": '{"timestamp": "2026-11-09T09:05:00Z", "event": "audit_entry"}\n',
        }
        post_req = urllib.request.Request(
            f"{self.base_url}/api/import",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(post_req) as post_resp:
            self.assertEqual(post_resp.status, 200)

        # 2. List imports
        req = urllib.request.Request(f"{self.base_url}/api/imports")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("imports", data)
            self.assertGreaterEqual(len(data["imports"]), 1)
            first_job = data["imports"][0]
            job_id = first_job["import_id"]

        # 3. Fetch detail of first job
        detail_req = urllib.request.Request(f"{self.base_url}/api/imports/{job_id}")
        with urllib.request.urlopen(detail_req) as resp:
            self.assertEqual(resp.status, 200)
            detail = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(detail["import_id"], job_id)
            self.assertIn("errors", detail)

    def test_import_invalid_parser_returns_422(self):
        """POST /api/import with invalid parser profile must return 422 rejected."""
        payload = {
            "filename": "invalid.log",
            "parser_id": "nonexistent_parser",
            "content_text": "hello",
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/import",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)

        self.assertEqual(ctx.exception.code, 422)
        with ctx.exception:
            data = json.loads(ctx.exception.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "rejected")

    def test_filename_path_traversal_sanitized(self):
        """Filenames with directory traversal sequences must be sanitized to safe basename."""
        payload = {
            "filename": "../../etc/shadow",
            "parser_id": "generic_jsonl",
            "content_text": '{"timestamp": "2026-11-09T09:10:00Z", "event": "safe_log"}\n',
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/import",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("filename"), "shadow")
            self.assertNotIn("..", data.get("filename", ""))

    def test_malformed_multipart_returns_400(self):
        """Malformed multipart body or missing boundary must return 400 Bad Request."""
        malformed_body = b"not_a_valid_multipart_payload"
        req = urllib.request.Request(
            f"{self.base_url}/api/import",
            data=malformed_body,
            headers={"Content-Type": "multipart/form-data; boundary=missing_parts"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)
        with ctx.exception:
            _ = ctx.exception.read()

    def test_oversized_payload_returns_413(self):
        """Requests declaring size above max_import_size_bytes must return 413 Payload Too Large."""
        req = urllib.request.Request(
            f"{self.base_url}/api/import",
            data=b"",
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(25 * 1024 * 1024),  # 25 MB exceeds 20 MB limit
            },
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 413)
        with ctx.exception:
            _ = ctx.exception.read()


if __name__ == "__main__":
    unittest.main()
