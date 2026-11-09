"""Unit tests for the Canonical Normalization Engine and Mappers."""

import json
import tempfile
import unittest
from pathlib import Path

from backend.normalization.engine import NormalizationEngine
from backend.normalization.mappers import (
    AuthCsvMapper,
    GenericJsonlMapper,
    WebAccessCsvMapper,
    compute_event_id,
)
from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository


class TestNormalizationEngine(unittest.TestCase):
    """Test suite for the Normalization Engine and all parser mappers."""

    def setUp(self) -> None:
        self.engine = NormalizationEngine()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_norm_engine.db"
        self.conn = get_connection(self.db_path)
        apply_migrations(self.conn)
        self.repo = IngestionRepository(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    def test_compute_event_id_deterministic(self) -> None:
        """Verify compute_event_id is strictly deterministic and collision-resistant."""
        sha = "a" * 64
        id1 = compute_event_id(sha, 10, "auth_csv", "1.0.0", "1.0.0")
        id2 = compute_event_id(sha, 10, "auth_csv", "1.0.0", "1.0.0")
        id3 = compute_event_id(sha, 11, "auth_csv", "1.0.0", "1.0.0")
        id_different_parser_ver = compute_event_id(sha, 10, "auth_csv", "1.0.1", "1.0.0")

        self.assertTrue(id1.startswith("evt_"))
        self.assertEqual(id1, id2)
        self.assertNotEqual(id1, id3)
        self.assertNotEqual(id1, id_different_parser_ver)

    def test_generic_jsonl_mapper(self) -> None:
        """Verify mapping of generic JSONL record with candidate keys."""
        mapper = GenericJsonlMapper()
        raw_rec = {
            "timestamp": "2026-11-09T08:00:00Z",
            "event_type": "api_request",
            "attributes": {
                "user": "secops_lead",
                "ip": "192.168.1.50",
                "resource": "/api/v1/telemetry",
                "status": "SUCCESS",
                "custom_metric": 42,
            },
        }
        context = {
            "source_id": "src_1",
            "filename": "logs.jsonl",
            "sha256": "b" * 64,
            "record_number": 5,
            "import_id": "imp_1",
            "record_id": "rec_1",
            "parser_version": "1.0.0",
        }
        event = mapper.map_record(raw_rec, context)

        self.assertEqual(event["event_type"], "api_request")
        self.assertEqual(event["user_principal"], "secops_lead")
        self.assertEqual(event["source_ip"], "192.168.1.50")
        self.assertEqual(event["target_resource"], "/api/v1/telemetry")
        self.assertEqual(event["status"], "SUCCESS")
        self.assertEqual(event["source_file"], "logs.jsonl")
        self.assertEqual(event["source_line"], 5)
        self.assertEqual(event["parser_version"], "1.0.0")
        self.assertEqual(event["attributes"]["custom_metric"], 42)

    def test_auth_csv_mapper(self) -> None:
        """Verify mapping of auth CSV record with success and failure status."""
        mapper = AuthCsvMapper()
        context = {
            "source_id": "src_auth",
            "filename": "auth.csv",
            "sha256": "c" * 64,
            "record_number": 2,
            "import_id": "imp_auth",
            "record_id": "rec_auth",
            "parser_version": "1.0.0",
        }

        # Success case
        raw_rec_success = {
            "timestamp": "2026-11-09 10:00:00+02:00",
            "event_type": "user_authentication",
            "attributes": {
                "username": "admin",
                "auth_result": "SUCCESS",
                "source_ip": "10.0.0.5",
            },
        }
        evt_success = mapper.map_record(raw_rec_success, context)
        self.assertEqual(evt_success["status"], "SUCCESS")
        self.assertEqual(evt_success["timestamp"], "2026-11-09T08:00:00Z")  # 10:00+02:00 -> 08:00Z
        self.assertEqual(evt_success["user_principal"], "admin")
        self.assertEqual(evt_success["source_ip"], "10.0.0.5")
        self.assertEqual(evt_success["parser_version"], "1.0.0")

        # Failure / locked case
        raw_rec_failure = {
            "timestamp": "2026-11-09T08:05:00Z",
            "event_type": "user_authentication",
            "attributes": {
                "username": "hacker",
                "auth_result": "LOCKED",
                "source_ip": "185.220.101.5",
            },
        }
        evt_failure = mapper.map_record(raw_rec_failure, context)
        self.assertEqual(evt_failure["status"], "FAILURE")

    def test_web_access_csv_mapper(self) -> None:
        """Verify mapping of web access CSV record with HTTP status codes."""
        mapper = WebAccessCsvMapper()
        context = {
            "source_id": "src_web",
            "filename": "access.csv",
            "sha256": "d" * 64,
            "record_number": 12,
            "import_id": "imp_web",
            "record_id": "rec_web",
            "parser_version": "1.0.0",
        }

        # 200 OK -> SUCCESS
        raw_200 = {
            "timestamp": "2026-11-09T08:10:00Z",
            "event_type": "web_request",
            "attributes": {
                "http_method": "GET",
                "request_path": "/dashboard",
                "status_code": "200",
                "source_ip": "192.168.1.10",
            },
        }
        evt_200 = mapper.map_record(raw_200, context)
        self.assertEqual(evt_200["status"], "SUCCESS")
        self.assertEqual(evt_200["target_resource"], "/dashboard")

        # 302 Found & 304 Not Modified -> UNKNOWN (not SUCCESS!)
        raw_302 = {
            "timestamp": "2026-11-09T08:10:30Z",
            "event_type": "web_request",
            "attributes": {
                "http_method": "GET",
                "request_path": "/old-page",
                "status_code": "302",
                "source_ip": "192.168.1.10",
            },
        }
        evt_302 = mapper.map_record(raw_302, context)
        self.assertEqual(evt_302["status"], "UNKNOWN")

        # 401 Unauthorized -> FAILURE
        raw_401 = {
            "timestamp": "2026-11-09T08:11:00Z",
            "event_type": "web_request",
            "attributes": {
                "http_method": "POST",
                "request_path": "/login",
                "status_code": "401",
                "source_ip": "192.168.1.10",
            },
        }
        evt_401 = mapper.map_record(raw_401, context)
        self.assertEqual(evt_401["status"], "FAILURE")

        # 500 Server Error -> ERROR
        raw_500 = {
            "timestamp": "2026-11-09T08:12:00Z",
            "event_type": "web_request",
            "attributes": {
                "http_method": "GET",
                "request_path": "/crash",
                "status_code": "500",
                "source_ip": "192.168.1.10",
            },
        }
        evt_500 = mapper.map_record(raw_500, context)
        self.assertEqual(evt_500["status"], "ERROR")

    def test_normalization_engine_error_handling(self) -> None:
        """Verify malformed records generate structured normalization errors."""
        # 1. Invalid timestamp (unparseable)
        bad_ts_row = {
            "record_id": "rec_bad_ts",
            "import_id": "imp_test",
            "record_number": 1,
            "parser_id": "generic_jsonl",
            "parser_version": "1.0.0",
            "record_json": json.dumps({"timestamp": "garbage-date", "attributes": {}}),
            "source_id": "src_1",
            "filename": "bad.jsonl",
            "sha256": "e" * 64,
        }
        evt, err = self.engine.normalize_single_record(bad_ts_row)
        self.assertIsNone(evt)
        self.assertIsNotNone(err)
        self.assertEqual(err["error_code"], "NORM_INVALID_TIMESTAMP")

        # 1b. Naive timestamp without timezone offset -> NORM_TIMEZONE_UNKNOWN
        naive_ts_row = {
            "record_id": "rec_naive_ts",
            "import_id": "imp_test",
            "record_number": 15,
            "parser_id": "generic_jsonl",
            "parser_version": "1.0.0",
            "record_json": json.dumps({"timestamp": "2026-11-09 08:00:15", "attributes": {}}),
            "source_id": "src_1",
            "filename": "naive.jsonl",
            "sha256": "e" * 64,
        }
        evt_naive, err_naive = self.engine.normalize_single_record(naive_ts_row)
        self.assertIsNone(evt_naive)
        self.assertIsNotNone(err_naive)
        self.assertEqual(err_naive["error_code"], "NORM_TIMEZONE_UNKNOWN")
        self.assertIn("cannot assume UTC", err_naive["safe_error_message"])

        # 2. Corrupted JSON payload
        bad_json_row = {
            "record_id": "rec_bad_json",
            "import_id": "imp_test",
            "record_number": 2,
            "parser_id": "generic_jsonl",
            "parser_version": "1.0.0",
            "record_json": "{not-valid-json",
            "source_id": "src_1",
            "filename": "bad.jsonl",
            "sha256": "e" * 64,
        }
        evt, err = self.engine.normalize_single_record(bad_json_row)
        self.assertIsNone(evt)
        self.assertIsNotNone(err)
        self.assertEqual(err["error_code"], "NORM_INVALID_PAYLOAD")

        # 3. Unknown parser profile
        unknown_parser_row = {
            "record_id": "rec_unknown",
            "import_id": "imp_test",
            "record_number": 3,
            "parser_id": "unsupported_profile",
            "parser_version": "1.0.0",
            "record_json": json.dumps({"timestamp": "2026-11-09T08:00:00Z"}),
            "source_id": "src_1",
            "filename": "unknown.log",
            "sha256": "e" * 64,
        }
        evt, err = self.engine.normalize_single_record(unknown_parser_row)
        self.assertIsNone(evt)
        self.assertIsNotNone(err)
        self.assertEqual(err["error_code"], "NORM_UNKNOWN_PARSER")

    def test_run_normalization_end_to_end(self) -> None:
        """Verify end-to-end normalization run persists events and handles errors in repository."""
        self.repo.get_or_create_source(
            source_id="src_e2e",
            source_name="E2E Source",
            parser_profile="auth_csv",
        )
        self.repo.create_import_job(
            import_id="imp_e2e",
            source_id="src_e2e",
            filename="auth.csv",
            sha256="f" * 64,
            file_size=2048,
            parser_id="auth_csv",
            parser_version="1.0.0",
            status="completed",
        )
        # Persist 1 valid and 1 invalid record
        self.repo.persist_import_batch(
            import_id="imp_e2e",
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
                        "timestamp": "2026-11-09T09:00:00Z",
                        "event_type": "user_authentication",
                        "attributes": {
                            "username": "valid_user",
                            "auth_result": "SUCCESS",
                            "source_ip": "172.16.0.1",
                        },
                        "raw_payload": "2026-11-09T09:00:00Z,valid_user,SUCCESS,172.16.0.1",
                    },
                },
                {
                    "record_number": 2,
                    "parser_id": "auth_csv",
                    "parser_version": "1.0.0",
                    "record": {
                        "line_number": 2,
                        "timestamp": "",  # Missing timestamp
                        "event_type": "user_authentication",
                        "attributes": {
                            "username": "bad_user",
                            "auth_result": "FAILURE",
                        },
                        "raw_payload": ",bad_user,FAILURE",
                    },
                },
            ],
            errors=[],
        )

        res = self.engine.run_normalization(self.repo, import_id="imp_e2e")
        self.assertEqual(res["total_fetched"], 2)
        self.assertEqual(res["accepted"], 1)
        self.assertEqual(res["rejected"], 1)

        # Query normalized events
        events, total = self.repo.list_normalized_events(import_id="imp_e2e")
        self.assertEqual(total, 1)
        self.assertEqual(events[0]["user_principal"], "valid_user")

        # Query normalization errors
        errors = self.repo.list_normalization_errors(import_id="imp_e2e")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["error_code"], "NORM_INVALID_TIMESTAMP")

        # Re-running normalization should find zero unnormalized records
        res_repeat = self.engine.run_normalization(self.repo, import_id="imp_e2e")
        self.assertEqual(res_repeat["total_fetched"], 0)


if __name__ == "__main__":
    unittest.main()

