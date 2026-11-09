# Project Sentinel — Phase 3.5 Test Evidence & Runtime Verification Audit
**Audit Phase:** Phase 3.5 Independent Technical Audit  
**Target Sprint:** Sprint 3 (Canonical Event Normalization, Provenance & Data Integrity)  
**Execution Date:** 2026-11-09  
**Platform:** Windows, Python 3.14.0, Node.js v24.13.0, SQLite 3  
**Status:** 100% VERIFIED & PASSING  

---

## 1. Full Backend Test Suite Execution (69 Tests)

Command executed:
```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Execution Output:
```text
test_health_response_matches_contract (contract.test_api_contracts.TestAPIContracts.test_health_response_matches_contract)
Verify the health response satisfies the BackendHealthResponse TypeScript schema. ... ok
test_multi_format_normalization_pipeline (integration.test_e2e_normalization.TestE2ENormalization.test_multi_format_normalization_pipeline)
Upload web access CSV and JSONL files, normalize both, and verify cross-source event querying. ... ok
test_events_empty_initially (integration.test_events_api.TestEventsAPI.test_events_empty_initially)
GET /api/events should return empty list and zero total initially. ... ok
test_import_and_normalize_workflow (integration.test_events_api.TestEventsAPI.test_import_and_normalize_workflow)
Upload log, trigger normalization run, query normalized event and detail. ... ok
test_concurrent_duplicate_import_protection (integration.test_import_api.TestImportAPI.test_concurrent_duplicate_import_protection)
Concurrent imports of the same payload must not create duplicate jobs or records. ... ok
test_import_auth_csv_success (integration.test_import_api.TestImportAPI.test_import_auth_csv_success)
Import a valid auth CSV file and verify response. ... ok
test_import_content_type_validation (integration.test_import_api.TestImportAPI.test_import_content_type_validation)
Rejects non-JSON content types. ... ok
test_import_duplicate_sha256_detection (integration.test_import_api.TestImportAPI.test_import_duplicate_sha256_detection)
Importing identical content must be detected and return duplicate status. ... ok
test_import_empty_file_rejected (integration.test_import_api.TestImportAPI.test_import_empty_file_rejected)
Empty content must be rejected. ... ok
test_import_generic_jsonl_success (integration.test_import_api.TestImportAPI.test_import_generic_jsonl_success)
Import a valid generic JSONL file and verify response. ... ok
test_import_oversized_file_rejected (integration.test_import_api.TestImportAPI.test_import_oversized_file_rejected)
Files exceeding MAX_IMPORT_SIZE_BYTES must be rejected. ... ok
test_import_unknown_parser_rejected (integration.test_import_api.TestImportAPI.test_import_unknown_parser_rejected)
Specifying an unsupported parser_id must fail. ... ok
test_import_web_access_csv_success (integration.test_import_api.TestImportAPI.test_import_web_access_csv_success)
Import a valid web access CSV file and verify response. ... ok
test_config_custom_env_override (unit.test_config.TestConfig.test_config_custom_env_override)
Verify environment variables properly override default configurations. ... ok
test_config_defaults (unit.test_config.TestConfig.test_config_defaults)
Verify default configuration values meet production specification. ... ok
test_allowed_explicit_origin_accepted (unit.test_cors_security.TestCorsSecurity.test_allowed_explicit_origin_accepted)
Explicitly whitelisted origin must receive matching Access-Control-Allow-Origin header. ... ok
test_cors_headers_on_error_response (unit.test_cors_security.TestCorsSecurity.test_cors_headers_on_error_response)
Error responses must also include CORS headers for whitelisted origins. ... ok
test_disallowed_origin_rejected (unit.test_cors_security.TestCorsSecurity.test_disallowed_origin_rejected)
Unlisted or malicious origins must never receive an allow-origin header. ... ok
test_preflight_disallowed_origin_rejected (unit.test_cors_security.TestCorsSecurity.test_preflight_disallowed_origin_rejected)
Preflight OPTIONS from unlisted origins must not receive allow-origin header. ... ok
test_preflight_options_allowed_origin (unit.test_cors_security.TestCorsSecurity.test_preflight_options_allowed_origin)
Preflight OPTIONS from whitelisted origin must return 204 with correct security headers. ... ok
test_connection_creates_tables (unit.test_database.TestDatabasePersistence.test_connection_creates_tables)
Verify database initialization creates required tables. ... ok
test_foreign_key_enforcement (unit.test_database.TestDatabasePersistence.test_foreign_key_enforcement)
Foreign keys must be active and reject orphaned parsed records. ... ok
test_import_errors_persistence (unit.test_database.TestDatabasePersistence.test_import_errors_persistence)
Import errors must be recorded with line numbers and safe messages. ... ok
test_import_job_creation_and_retrieval (unit.test_database.TestDatabasePersistence.test_import_job_creation_and_retrieval)
Verify creating and retrieving an import job. ... ok
test_persist_import_batch_atomic (unit.test_database.TestDatabasePersistence.test_persist_import_batch_atomic)
Batch record and error persistence must be atomic. ... ok
test_reconcile_pending_jobs_on_startup (unit.test_database.TestDatabasePersistence.test_reconcile_pending_jobs_on_startup)
Interrupted 'pending' jobs must be marked as failed on startup. ... ok
test_health_endpoint_returns_json (unit.test_health.TestHealthEndpoint.test_health_endpoint_returns_json)
Test that /health returns application/json. ... ok
test_health_endpoint_returns_ok_status (unit.test_health.TestHealthEndpoint.test_health_endpoint_returns_ok_status)
Test that /health returns status 200 with ok. ... ok
test_health_includes_runtime_metadata (unit.test_health.TestHealthEndpoint.test_health_includes_runtime_metadata)
Test that runtime metadata (version, uptime, kiro_compatible) is present. ... ok
test_unknown_route_returns_404 (unit.test_health.TestHealthEndpoint.test_unknown_route_returns_404)
Test that unknown endpoints return 404 with standard error body. ... ok
test_duplicate_sha256_detection (unit.test_import_engine.TestImportEngine.test_duplicate_sha256_detection)
Engine must detect identical SHA-256 for the same parser profile. ... ok
test_import_from_string_success (unit.test_import_engine.TestImportEngine.test_import_from_string_success)
Verify end-to-end string import with valid records. ... ok
test_partial_failure_import (unit.test_import_engine.TestImportEngine.test_partial_failure_import)
Files with mixed valid and invalid lines must result in 'partial' status. ... ok
test_rejection_of_empty_content (unit.test_import_engine.TestImportEngine.test_rejection_of_empty_content)
Importing 0 bytes must raise ValidationError. ... ok
test_rejection_of_oversized_content (unit.test_import_engine.TestImportEngine.test_rejection_of_oversized_content)
Content exceeding MAX_IMPORT_SIZE_BYTES must raise ValidationError. ... ok
test_sensitive_secret_redaction (unit.test_import_engine.TestImportEngine.test_sensitive_secret_redaction)
Passwords and secrets must be scrubbed before database persistence. ... ok
test_get_unnormalized_records (unit.test_normalization_db.TestNormalizationDatabase.test_get_unnormalized_records)
Verify unnormalized records are discovered correctly. ... ok
test_idempotency_prevents_duplicate_events (unit.test_normalization_db.TestNormalizationDatabase.test_idempotency_prevents_duplicate_events)
Verify that persisting the same event/record again is safely ignored. ... ok
test_list_normalized_events_filtering (unit.test_normalization_db.TestNormalizationDatabase.test_list_normalized_events_filtering)
Verify filtering by event_type and user_principal. ... ok
test_migrations_applied (unit.test_normalization_db.TestNormalizationDatabase.test_migrations_applied)
Verify schema_migrations table tracks migration 1, 2, and 3. ... ok
test_normalization_errors_persistence (unit.test_normalization_db.TestNormalizationDatabase.test_normalization_errors_persistence)
Verify normalization errors are stored and queried. ... ok
test_persist_and_query_normalized_events (unit.test_normalization_db.TestNormalizationDatabase.test_persist_and_query_normalized_events)
Verify batch persisting of normalized events and querying. ... ok
test_auth_csv_mapper (unit.test_normalization_engine.TestNormalizationEngine.test_auth_csv_mapper)
Verify mapping of auth CSV record with success and failure status. ... ok
test_compute_event_id_deterministic (unit.test_normalization_engine.TestNormalizationEngine.test_compute_event_id_deterministic)
Verify compute_event_id is strictly deterministic and collision-resistant. ... ok
test_generic_jsonl_mapper (unit.test_normalization_engine.TestNormalizationEngine.test_generic_jsonl_mapper)
Verify mapping of generic JSONL record with candidate keys. ... ok
test_normalization_engine_error_handling (unit.test_normalization_engine.TestNormalizationEngine.test_normalization_engine_error_handling)
Verify malformed records generate structured normalization errors. ... ok
test_run_normalization_end_to_end (unit.test_normalization_engine.TestNormalizationEngine.test_run_normalization_end_to_end)
Verify end-to-end normalization run persists events and handles errors in repository. ... ok
test_web_access_csv_mapper (unit.test_normalization_engine.TestNormalizationEngine.test_web_access_csv_mapper)
Verify mapping of web access CSV record with HTTP status codes. ... ok
test_auth_csv_missing_columns (unit.test_parsers.TestParsers.test_auth_csv_missing_columns)
auth_csv parser rejects files missing required headers. ... ok
test_auth_csv_parser_valid (unit.test_parsers.TestParsers.test_auth_csv_parser_valid)
auth_csv parser parses valid CSV with required columns. ... ok
test_generic_jsonl_parser_invalid_json (unit.test_parsers.TestParsers.test_generic_jsonl_parser_invalid_json)
generic_jsonl parser flags malformed lines as ParsingError. ... ok
test_generic_jsonl_parser_valid (unit.test_parsers.TestParsers.test_generic_jsonl_parser_valid)
generic_jsonl parser yields valid records. ... ok
test_parser_registry_lookup (unit.test_parsers.TestParsers.test_parser_registry_lookup)
Parser registry must find registered parsers and reject unknown. ... ok
test_web_access_csv_invalid_status_code (unit.test_parsers.TestParsers.test_web_access_csv_invalid_status_code)
web_access_csv rejects non-numeric or out-of-range status codes. ... ok
test_web_access_csv_parser_valid (unit.test_parsers.TestParsers.test_web_access_csv_parser_valid)
web_access_csv parser parses valid HTTP log lines. ... ok
test_approved_inbox_path_normalization (unit.test_scanner.TestInboxScanner.test_approved_inbox_path_normalization)
Scanner must resolve and strictly validate the approved inbox directory. ... ok
test_disallowed_extension_ignored (unit.test_scanner.TestInboxScanner.test_disallowed_extension_ignored)
Files with unapproved extensions (.txt, .exe, .sh) must be skipped. ... ok
test_dot_prefixed_files_ignored (unit.test_scanner.TestInboxScanner.test_dot_prefixed_files_ignored)
Dot-prefixed and hidden files (.DS_Store, .tmp) must be skipped. ... ok
test_non_recursive_scanning (unit.test_scanner.TestInboxScanner.test_non_recursive_scanning)
Scanner must ignore nested subdirectories. ... ok
test_path_safety_validation (unit.test_scanner.TestInboxScanner.test_path_safety_validation)
Scanner must reject roots, user homes, and system directories. ... ok
test_pause_and_resume (unit.test_scanner.TestInboxScanner.test_pause_and_resume)
Scanner must not process files while paused. ... ok
test_scan_once_ingests_and_preserves_files (unit.test_scanner.TestInboxScanner.test_scan_once_ingests_and_preserves_files)
Scanner must ingest files without deleting or moving them. ... ok
test_day_boundary_crossing_with_offset (unit.test_timestamps.TestTimestamps.test_day_boundary_crossing_with_offset) ... ok
test_epoch_numeric_and_string (unit.test_timestamps.TestTimestamps.test_epoch_numeric_and_string) ... ok
test_invalid_timestamps_raise_value_error (unit.test_timestamps.TestTimestamps.test_invalid_timestamps_raise_value_error) ... ok
test_naive_timestamps_rejected_without_utc_assumption (unit.test_timestamps.TestTimestamps.test_naive_timestamps_rejected_without_utc_assumption) ... ok
test_offset_conversion_to_utc (unit.test_timestamps.TestTimestamps.test_offset_conversion_to_utc) ... ok
test_subsecond_precision_preserved (unit.test_timestamps.TestTimestamps.test_subsecond_precision_preserved) ... ok
test_utc_iso_string_with_z (unit.test_timestamps.TestTimestamps.test_utc_iso_string_with_z) ... ok

----------------------------------------------------------------------
Ran 69 tests in 4.142s

OK
```

---

## 2. Test Discovery Breakdown by Module

Programmatic discovery via `unittest.TestLoader().discover('tests', pattern='test_*.py')`:

| Module Path | Discovered Tests | Status | Description |
| :--- | :---: | :---: | :--- |
| `contract.test_api_contracts` | 1 | PASS | Health JSON Schema contract compliance |
| `integration.test_e2e_normalization` | 1 | PASS | Cross-format end-to-end ingestion and normalization pipeline |
| `integration.test_events_api` | 2 | PASS | `/api/events`, `/api/events/{id}`, `/api/normalization/*` REST API |
| `integration.test_import_api` | 9 | PASS | Ingestion HTTP endpoints, idempotency, size checks, concurrency |
| `unit.test_config` | 2 | PASS | Configuration initialization and environment variable overrides |
| `unit.test_cors_security` | 5 | PASS | Origin filtering, preflight handling, error headers |
| `unit.test_database` | 6 | PASS | Persistence engine, FK enforcement, batch transactions, recovery |
| `unit.test_health` | 4 | PASS | `/health` route, JSON metadata, 404 handler |
| `unit.test_import_engine` | 6 | PASS | Ingestion engine, SHA-256 deduplication, secret redaction |
| `unit.test_normalization_db` | 6 | PASS | Normalization persistence, queries, migrations 001-003, deduplication |
| `unit.test_normalization_engine` | 6 | PASS | Mappers (auth, web, generic), error quarantine, deterministic identity |
| `unit.test_parsers` | 7 | PASS | CSV and JSONL syntax, required headers, status codes |
| `unit.test_scanner` | 7 | PASS | Inbox directory safety, pause/resume, non-destructive polling |
| `unit.test_timestamps` | 7 | PASS | UTC normalization, offset day boundaries, naive timestamp rejection |
| **TOTAL** | **69** | **PASS** | **Zero failures, zero skips, zero errors** |

---

## 3. SQLite Database Schema & Migration Verification

Direct inspection of SQLite database at `%LOCALAPPDATA%\ProjectSentinel\sentinel.db`:

```text
MIGRATION: (1, '001_initial_schema', '2026-11-09 04:02:42')
MIGRATION: (2, '002_canonical_events_and_provenance', '2026-11-09 04:39:55')
MIGRATION: (3, '003_event_parser_version', '2026-11-09 14:39:12')

Table `normalized_events` PRAGMA table_info:
(0, 'event_id', 'TEXT', 0, None, 1)
(1, 'import_id', 'TEXT', 1, None, 0)
(2, 'record_id', 'TEXT', 1, None, 0)
(3, 'source_id', 'TEXT', 1, None, 0)
(4, 'record_number', 'INTEGER', 1, None, 0)
(5, 'timestamp', 'TEXT', 1, None, 0)
(6, 'source_type', 'TEXT', 1, None, 0)
(7, 'source_file', 'TEXT', 1, None, 0)
(8, 'source_line', 'INTEGER', 1, None, 0)
(9, 'source_sha256', 'TEXT', 1, None, 0)
(10, 'event_type', 'TEXT', 1, None, 0)
(11, 'user_principal', 'TEXT', 0, None, 0)
(12, 'source_ip', 'TEXT', 0, None, 0)
(13, 'target_resource', 'TEXT', 0, None, 0)
(14, 'status', 'TEXT', 1, None, 0)
(15, 'attributes_json', 'TEXT', 1, None, 0)
(16, 'normalization_version', 'TEXT', 1, None, 0)
(17, 'created_at', 'TEXT', 1, "datetime('now', 'utc')", 0)
(18, 'parser_version', 'TEXT', 1, "'1.0.0'", 0)

Quarantine Verification:
TOTAL_NORM_EVENTS: 12
TOTAL_NORM_ERRORS: 1
ERROR_SUMMARY: ('NORM_TIMEZONE_UNKNOWN', "Record timestamp '2026-11-09 08:30:00' lacks explicit timezone offset; cannot assume UTC.", 1)
```

---

## 4. Headless Chrome DOM Verification Output

Command executed:
```powershell
python scripts/runtime_verification.py
```

Execution Output:
```text
======================================================================
 PROJECT SENTINEL — Phase 3 Runtime Verification
======================================================================
[+] Found Browser for Runtime Verification: C:\Program Files\Google\Chrome\Application\chrome.exe
[*] Starting production preview server on 127.0.0.1:4173...
[+] Production preview server is ACTIVE on http://127.0.0.1:4173
[*] Starting Backend service on 127.0.0.1:8000...
[+] Backend service is ACTIVE on http://127.0.0.1:8000

--> [Test 1/5] Verifying Initial UI Render and Backend Connectivity...
    [PASS] DOM rendered successfully with active 'Backend Connected' state!

--> [Test 2/5] Testing all 8 navigation routes in browser runtime...
    [PASS] Route 'overview' rendered: 'Welcome to Project Sentinel' verified.
    [PASS] Route 'investigations' rendered: 'Investigations Module' verified.
    [PASS] Route 'findings' rendered: 'Findings Module' verified.
    [PASS] Route 'events' rendered: 'Canonical Events' verified.
    [PASS] Route 'replay' rendered: 'Replay Lab Module' verified.
    [PASS] Route 'sources' rendered: 'Data Ingestion' verified.
    [PASS] Route 'digests' rendered: 'Digests Module' verified.
    [PASS] Route 'settings' rendered: 'Settings Module' verified.

--> [Test 3/5] Verifying Events view interactive controls and canonical metrics...
    [PASS] Events view verified: controls, metrics bar, and canonical table present.

--> [Test 3b/5] Verifying Sources view interactive controls and genuine history...
    [PASS] Sources view verified: controls, event sources, and history table present.

--> [Test 4/5] Testing Backend Disconnect and Offline Error State...
    [*] Stopping backend service...
    [PASS] Offline state correctly displayed with 'Backend Unavailable' and recovery guidance!

--> [Test 5/5] Testing Backend Restart and UI Recovery...
    [*] Restarting backend service...
    [PASS] Backend recovery confirmed: UI resumed 'Backend Connected' operational state!

[*] Shutting down test processes cleanly...
[+] All test servers stopped cleanly. Zero background processes remaining.

======================================================================
 ALL RUNTIME VERIFICATION STEPS PASSED SUCCESSFULLY!
======================================================================
```

---

## 5. End-to-End Multi-Format Normalization & Quarantine Workflow

Command executed:
```powershell
python scripts/verify_real_normalization_workflow.py
```

Execution Output:
```text
======================================================================
 PROJECT SENTINEL — Phase 3 Real Normalization & Provenance Audit
======================================================================

[*] Starting Sentinel backend on 127.0.0.1:8000...
[+] Backend active and responding to /health.

--> [Step 1] Verifying /api/normalization/stats baseline...
    [PASS] Current stats: 8 normalized, 0 pending.

--> [Step 2] Ingesting multi-format logs for canonical normalization test...
    [PASS] Auth CSV ingested: import_id=imp_3cd2da46e5ea, accepted=2
    [PASS] Web CSV ingested: import_id=imp_9754077ece2c, accepted=2
    [PASS] Naive JSONL ingested: import_id=imp_9d699799712a, accepted=1

--> [Step 3] Triggering POST /api/normalization/run...
    [PASS] Normalization executed: 4 accepted, 1 rejected, 0 skipped.

--> [Step 4] Querying GET /api/events with dynamic filters...
    [PASS] /api/events returned total=12 events.
    [PASS] Filter status=FAILURE returned 6 events.

--> [Step 5] Inspecting specific event detail via GET /api/events/{id}...
    [PASS] Event evt_02467ba9eac11c88cad52610 verified: timestamp=2026-11-09T08:12:00Z, source=web_audit_1794199302.csv:3

--> [Step 6] Auditing SQLite database tables on disk...
    [*] Database path: C:\Users\Atul2\AppData\Local\ProjectSentinel\sentinel.db
    [PASS] SQLite normalized_events table contains 12 rows.
    [PASS] Verified FK integrity and parser_version column across 5 sampled normalized events.
    [PASS] Verified naive timestamp quarantine in SQLite: 1 error(s) with code NORM_TIMEZONE_UNKNOWN.
    [PASS] Indexes idx_norm_events_ts and uq_record_norm_version verified.

[*] Stopping backend service...
[+] Backend service stopped.

======================================================================
 ALL 6 PHASE 3 NORMALIZATION & AUDIT STEPS PASSED SUCCESSFULLY!
======================================================================
```

---

## 6. Pre-Commit Validation Hook Summary

Command executed:
```powershell
powershell -ExecutionPolicy Bypass -File .kiro/hooks/validate-all.ps1
```

Validation Result:
- Backend Unittests (69 discovered): 100% PASS
- Kiro Crew Manifest (`app.json`): VALID (all referenced agents, skills, UI bundles exist)
- Frontend TypeScript Typecheck (`tsc --noEmit`): 100% PASS (0 type errors)
- Frontend Production Dual Build (Vite SPA + Kiro ESM): 100% PASS (dist/index.html & dist/index.mjs built cleanly)
- Headless Browser Verification (`scripts/runtime_verification.py`): 100% PASS (all 8 routes verified)
- Real Workflow & SQLite Verification (`scripts/verify_real_workflow.py`): 100% PASS (all 13 steps verified)
- Result: **==> [Hook] All Quality Gates Passed Cleanly!**

