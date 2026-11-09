# Project Sentinel — Phase 2.5 Test Execution Evidence
**Audit Date:** 2026-11-09  
**Auditor:** Independent Technical Lead & Security Reviewer  

This document contains raw execution logs and test outputs demonstrating 100% verification across all backend, database, security, frontend, and headless browser tests.

---

## 1. Backend Automated Test Suite (47/47 Passed)

```text
PS C:\Users\Atul2\OneDrive\Desktop\KiroHackethon\sentinal> python -m unittest discover -s tests -p "test_*.py" -v
test_health_response_matches_contract (contract.test_api_contracts.TestAPIContracts.test_health_response_matches_contract)
Verify the health response satisfies the BackendHealthResponse TypeScript schema. ... ok
test_filename_path_traversal_sanitized (integration.test_import_api.TestImportAPI.test_filename_path_traversal_sanitized)
Filenames with directory traversal sequences must be sanitized to safe basename. ... ok
test_get_parsers_endpoint (integration.test_import_api.TestImportAPI.test_get_parsers_endpoint)
GET /api/parsers must return all registered parser profiles. ... ok
test_get_sources_endpoint (integration.test_import_api.TestImportAPI.test_get_sources_endpoint)
GET /api/sources must return configured sources including default manual source. ... ok
test_import_invalid_parser_returns_422 (integration.test_import_api.TestImportAPI.test_import_invalid_parser_returns_422)
POST /api/import with invalid parser profile must return 422 rejected. ... ok
test_list_and_get_imports (integration.test_import_api.TestImportAPI.test_list_and_get_imports)
GET /api/imports and GET /api/imports/{id} must retrieve genuine persisted jobs. ... ok
test_malformed_multipart_returns_400 (integration.test_import_api.TestImportAPI.test_malformed_multipart_returns_400)
Malformed multipart body or missing boundary must return 400 Bad Request. ... ok
test_oversized_payload_returns_413 (integration.test_import_api.TestImportAPI.test_oversized_payload_returns_413)
Requests declaring size above max_import_size_bytes must return 413 Payload Too Large. ... ok
test_post_import_json_payload (integration.test_import_api.TestImportAPI.test_post_import_json_payload)
POST /api/import with JSON payload must ingest records and return completed status. ... ok
test_post_import_multipart_payload (integration.test_import_api.TestImportAPI.test_post_import_multipart_payload)
POST /api/import with multipart/form-data must successfully ingest CSV file. ... ok
test_default_settings (unit.test_config.TestSettings.test_default_settings)
Verify default configuration values. ... ok
test_env_override (unit.test_config.TestSettings.test_env_override)
Verify that environment variables cleanly override defaults. ... ok
test_allowed_origin_receives_exact_cors_header (unit.test_cors_security.TestCORSSecurity.test_allowed_origin_receives_exact_cors_header)
Allowed origin must receive exact matching Access-Control-Allow-Origin and Vary: Origin. ... ok
test_disallowed_origin_receives_no_cors_header (unit.test_cors_security.TestCORSSecurity.test_disallowed_origin_receives_no_cors_header)
Disallowed/untrusted origin must NEVER receive Access-Control-Allow-Origin header. ... ok
test_no_origin_header_receives_no_cors_headers (unit.test_cors_security.TestCORSSecurity.test_no_origin_header_receives_no_cors_headers)
Direct non-browser or same-origin requests receive no CORS headers. ... ok
test_options_preflight_allowed_origin (unit.test_cors_security.TestCORSSecurity.test_options_preflight_allowed_origin)
OPTIONS preflight from allowed origin returns 204 with correct CORS headers. ... ok
test_options_preflight_disallowed_origin_returns_403 (unit.test_cors_security.TestCORSSecurity.test_options_preflight_disallowed_origin_returns_403)
OPTIONS preflight from disallowed origin is rejected with 403 Forbidden. ... ok
test_foreign_key_enforcement (unit.test_database.TestDatabasePersistence.test_foreign_key_enforcement)
Foreign key constraint must prevent creating import job with non-existent source_id. ... ok
test_persistence_across_reconnect (unit.test_database.TestDatabasePersistence.test_persistence_across_reconnect)
Database state must persist reliably after connection close and reopening. ... ok
test_reconcile_pending_jobs_on_restart (unit.test_database.TestDatabasePersistence.test_reconcile_pending_jobs_on_restart)
Dangling 'pending' jobs from prior crashes must reconcile to 'failed'. ... ok
test_repeatable_migrations (unit.test_database.TestDatabasePersistence.test_repeatable_migrations)
Applying migrations multiple times must be completely idempotent. ... ok
test_transactional_batch_persistence (unit.test_database.TestDatabasePersistence.test_transactional_batch_persistence)
Verify atomic insertion of job metadata, parsed records, and error rows. ... ok
test_unique_hash_parser_constraint (unit.test_database.TestDatabasePersistence.test_unique_hash_parser_constraint)
Inserting identical (sha256, parser_id, parser_version) must violate unique constraint. ... ok
test_api_health_alias (unit.test_health.TestHealthEndpoint.test_api_health_alias)
Verify GET /api/health alias functions identically. ... ok
test_cors_options_preflight (unit.test_health.TestHealthEndpoint.test_cors_options_preflight)
Verify OPTIONS request returns 204 with exact CORS headers. ... ok
test_health_endpoint_ok (unit.test_health.TestHealthEndpoint.test_health_endpoint_ok)
Verify GET /health returns 200 OK and valid schema. ... ok
test_unknown_route_returns_404 (unit.test_health.TestHealthEndpoint.test_unknown_route_returns_404)
Verify unknown path returns structured 404 JSON response. ... ok
test_deduplication_skips_identical_file (unit.test_import_engine.TestImportEngine.test_deduplication_skips_identical_file)
Engine must skip duplicate import of identical file content and parser profile. ... ok
test_empty_file_rejection (unit.test_import_engine.TestImportEngine.test_empty_file_rejection)
Engine must reject empty files. ... ok
test_file_size_limit_rejection (unit.test_import_engine.TestImportEngine.test_file_size_limit_rejection)
Engine must reject files exceeding configured maximum size. ... ok
test_partial_ingestion_with_row_errors (unit.test_import_engine.TestImportEngine.test_partial_ingestion_with_row_errors)
Engine must record partial status and store row errors when some records fail. ... ok
test_sanitizer_scrubs_secrets (unit.test_import_engine.TestImportEngine.test_sanitizer_scrubs_secrets)
Sanitizer must redact passwords, tokens, cookies, session IDs, arrays, and headers. ... ok
test_successful_ingestion (unit.test_import_engine.TestImportEngine.test_successful_ingestion)
Engine must process valid JSONL and persist job and records in SQLite. ... ok
test_auth_csv_missing_header_columns (unit.test_parsers.TestParsers.test_auth_csv_missing_header_columns)
Auth CSV parser must reject CSV missing required headers. ... ok
test_auth_csv_parser_valid_and_errors (unit.test_parsers.TestParsers.test_auth_csv_parser_valid_and_errors)
Auth CSV parser must validate required columns, allowed results, and column counts. ... ok
test_generic_jsonl_parser_valid_and_errors (unit.test_parsers.TestParsers.test_generic_jsonl_parser_valid_and_errors)
JSONL parser must extract valid records and accurately attribute line errors. ... ok
test_generic_jsonl_utf8_bom_handling (unit.test_parsers.TestParsers.test_generic_jsonl_utf8_bom_handling)
JSONL parser must strip UTF-8 BOM if present at start. ... ok
test_max_line_length_protection (unit.test_parsers.TestParsers.test_max_line_length_protection)
Parser must reject excessively long lines exceeding safe memory limit. ... ok
test_parser_registry (unit.test_parsers.TestParsers.test_parser_registry)
Registry must resolve all required profiles and list metadata. ... ok
test_web_access_csv_valid_and_errors (unit.test_parsers.TestParsers.test_web_access_csv_valid_and_errors)
Web access CSV parser must validate HTTP verbs and status code ranges. ... ok
test_disabled_source_skips_scanning (unit.test_scanner.TestInboxScanner.test_disabled_source_skips_scanning)
Disabled source (enabled=0) must not ingest files. ... ok
test_explicit_parser_profile_used_never_inferred_from_filename (unit.test_scanner.TestInboxScanner.test_explicit_parser_profile_used_never_inferred_from_filename)
Scanner must strictly use the source's configured parser profile, never guessing from filename. ... ok
test_monitoring_disabled_by_default (unit.test_scanner.TestInboxScanner.test_monitoring_disabled_by_default)
Inbox scanner background monitoring must be disabled by default. ... ok
test_non_recursive_scanning (unit.test_scanner.TestInboxScanner.test_non_recursive_scanning)
Scanner must ignore nested subdirectories. ... ok
test_path_safety_validation (unit.test_scanner.TestInboxScanner.test_path_safety_validation)
Scanner must reject roots, user homes, and system directories. ... ok
test_pause_and_resume (unit.test_scanner.TestInboxScanner.test_pause_and_resume)
Scanner must not process files while paused. ... ok
test_scan_once_ingests_and_preserves_files (unit.test_scanner.TestInboxScanner.test_scan_once_ingests_and_preserves_files)
Scanner must ingest files without deleting or moving them. ... ok

----------------------------------------------------------------------
Ran 47 tests in 2.511s

OK
```

---

## 2. Kiro Crew Manifest Validation

```text
PS C:\Users\Atul2\OneDrive\Desktop\KiroHackethon\sentinal> python scripts/validate_manifest.py
[*] Validating Kiro Crew manifest at: C:\Users\Atul2\OneDrive\Desktop\KiroHackethon\sentinal\apps\crew-app\app.json
[+] Kiro Crew manifest is VALID and all resource references exist!
    - App Name: project-sentinel
    - Display Name: Project Sentinel
    - Version: 0.1.0
    - UI Entry: dist/index.mjs (verified present on disk)
    - Registered Agents: ['agents/sentinel-investigator.json'] (verified schema)
    - Registered Skills: ['skills/evidence-led-investigation'] (verified frontmatter)
```

---

## 3. Frontend Dual Production Build

```text
PS C:\Users\Atul2\OneDrive\Desktop\KiroHackethon\sentinal\apps\crew-app> npm run build
> project-sentinel-ui@0.1.0 build
> tsc --noEmit && vite build && vite build --config vite.config.crew.ts

vite v6.4.5 building for production...
transforming...
✓ 34 modules transformed.
rendering chunks...
computing gzip size...
dist/assets/icon-q7qYM4mz.svg     0.46 kB │ gzip:  0.28 kB
dist/index.html                   0.89 kB │ gzip:  0.51 kB
dist/assets/index-D97k4bAJ.css    3.67 kB │ gzip:  1.29 kB
dist/assets/index-KuI8Ckhu.js   182.02 kB │ gzip: 54.61 kB
✓ built in 701ms

vite v6.4.5 building for production...
transforming...
✓ 8 modules transformed.
rendering chunks...
computing gzip size...
dist/index.mjs  54.61 kB │ gzip: 10.00 kB
✓ built in 162ms
```

---

## 4. Headless Browser Runtime Verification (12/12 Steps)

```text
======================================================================
 PROJECT SENTINEL — Phase 2 Runtime Verification
======================================================================
[+] Found Browser for Runtime Verification: C:\Program Files\Google\Chrome\Application\chrome.exe
[*] Starting production preview server on 127.0.0.1:4173...
[+] Production preview server is ACTIVE on http://127.0.0.1:4173
[*] Starting Backend service on 127.0.0.1:8000...
[+] Backend service is ACTIVE on http://127.0.0.1:8000

--> [Test 1/4] Verifying Initial UI Render and Backend Connectivity...
    [PASS] DOM rendered successfully with active 'Backend Connected' state!

--> [Test 2/4] Testing all 8 navigation routes in browser runtime...
    [PASS] Route 'overview' rendered: 'Welcome to Project Sentinel' verified.
    [PASS] Route 'investigations' rendered: 'Investigations Module' verified.
    [PASS] Route 'findings' rendered: 'Findings Module' verified.
    [PASS] Route 'events' rendered: 'Events Module' verified.
    [PASS] Route 'replay' rendered: 'Replay Lab Module' verified.
    [PASS] Route 'sources' rendered: 'Data Ingestion' verified.
    [PASS] Route 'digests' rendered: 'Digests Module' verified.
    [PASS] Route 'settings' rendered: 'Settings Module' verified.

--> [Test 2b/4] Verifying Sources view interactive controls and genuine history...
    [PASS] Sources view verified: controls, event sources, and history table present.

--> [Test 3/4] Testing Backend Disconnect and Offline Error State...
    [*] Stopping backend service...
    [PASS] Offline state correctly displayed with 'Backend Unavailable' and recovery guidance!

--> [Test 4/4] Testing Backend Restart and UI Recovery...
    [*] Restarting backend service...
    [PASS] Backend recovery confirmed: UI resumed 'Backend Connected' operational state!

[*] Shutting down test processes cleanly...
[+] All test servers stopped cleanly. Zero background processes remaining.

======================================================================
 ALL 12 RUNTIME VERIFICATION STEPS PASSED SUCCESSFULLY!
======================================================================
```

---

## 5. Real Browser & SQLite Workflow Verification (13/13 Steps)

```text
===========================================================================
 PROJECT SENTINEL — Phase 2.5 Real Browser & SQLite Verification
===========================================================================
[+] Found Browser: C:\Program Files\Google\Chrome\Application\chrome.exe

--> [Step 1/13] Starting Frontend Preview (127.0.0.1:4173) and Backend (127.0.0.1:8000)...
    [PASS] Both servers are ACTIVE and reachable.

--> [Step 2-3/13] Preparing valid authentication CSV with parser 'auth_csv'...
    Payload size: 180 bytes (2 records).

--> [Step 4-5/13] Importing file via POST /api/import and verifying response...
    API Response: status=completed, duplicate=False, accepted=2
    [PASS] API response verified: import_id=imp_12ddb2f0095a, sha256=bae1628a9744...

--> [Step 6/13] Querying SQLite database directly to verify persisted records...
    [PASS] SQLite verified: 1 import_job ('completed') and 2 parsed_records confirmed!

--> [Step 7/13] Verifying frontend Sources view in Headless Chrome DOM...
    [PASS] Chrome rendered history row with 'auth_valid_audit.csv', 'bae1628a9744...', and 'auth_csv'!

--> [Step 8-9/13] Re-importing identical file to test SHA-256 deduplication...
    [PASS] Duplicate skipped: SQLite records strictly unchanged (1 job, 2 records).

--> [Step 10-11/13] Ingesting CSV with malformed rows to verify error diagnostics...
    [PASS] Partial import verified: 1 accepted, 2 rejected rows with line attribution in SQLite!

--> [Step 12-13/13] Restarting backend service and verifying history retention...
    [PASS] Restart verified: both jobs persisted and rendered in Chrome DOM!

[*] Shutting down test processes cleanly...
[+] Teardown complete. All test processes terminated.

===========================================================================
 ALL 13 REAL WORKFLOW & SQLITE VERIFICATION STEPS PASSED 100%!
===========================================================================
```

---

## 6. Full Kiro Quality Gate Hook Execution

```text
PS C:\Users\Atul2\OneDrive\Desktop\KiroHackethon\sentinal> powershell -ExecutionPolicy Bypass -File .kiro/hooks/validate-all.ps1
==> [Hook] Running Project Sentinel Validation...
--> Running Backend Unit & Contract Tests...
Ran 47 tests in 2.511s
OK
--> Validating Kiro Crew Manifest...
[+] Kiro Crew manifest is VALID and all resource references exist!
--> Running Frontend Build & Typecheck...
dist/index.html                   0.89 kB │ gzip:  0.51 kB
dist/assets/index-D97k4bAJ.css    3.67 kB │ gzip:  1.29 kB
dist/assets/index-KuI8Ckhu.js   182.02 kB │ gzip: 54.61 kB
dist/index.mjs  54.61 kB │ gzip: 10.00 kB
--> Running Headless Browser Runtime Verification...
ALL 12 RUNTIME VERIFICATION STEPS PASSED SUCCESSFULLY!
--> Running Real Browser & SQLite Workflow Verification...
ALL 13 REAL WORKFLOW & SQLITE VERIFICATION STEPS PASSED 100%!
==> [Hook] All Quality Gates Passed Cleanly!
```

