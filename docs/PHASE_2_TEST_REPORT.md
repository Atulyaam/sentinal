# Project Sentinel — Phase 2 Test Report
**Test Suite:** Unit, Contract, Integration, Persistence, Security, and Headless Browser Verification  
**Sprint:** Sprint 2 (Core Data Pipeline, SQLite, Parsers & Secure Ingestion)  
**Date:** 2026-11-09  
**Result:** 100% PASS (36/36 Backend Tests, Dual Frontend Build, 12/12 Browser Steps)  

---

## 1. Test Execution Overview

All test suites were executed sequentially and verified in clean test environments utilizing ephemeral databases and temporary directories.

| Test Category | Suite File | Total Tests | Passed | Failed | Duration |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **API Contracts** | `tests/contract/test_api_contracts.py` | 1 | 1 | 0 | 0.08s |
| **Configuration** | `tests/unit/test_config.py` | 2 | 2 | 0 | 0.01s |
| **CORS & Security** | `tests/unit/test_cors_security.py` | 5 | 5 | 0 | 0.09s |
| **Database & Persistence** | `tests/unit/test_database.py` | 6 | 6 | 0 | 0.08s |
| **Health API** | `tests/unit/test_health.py` | 4 | 4 | 0 | 0.08s |
| **Strict Parsers** | `tests/unit/test_parsers.py` | 7 | 7 | 0 | 0.01s |
| **Import Engine** | `tests/unit/test_import_engine.py` | 6 | 6 | 0 | 0.07s |
| **Inbox Scanner** | `tests/unit/test_scanner.py` | 5 | 5 | 0 | 0.12s |
| **Import API Integration** | `tests/integration/test_import_api.py` | 6 | 6 | 0 | 0.61s |
| **Kiro Manifest** | `scripts/validate_manifest.py` | 1 | 1 | 0 | 0.05s |
| **Frontend Typecheck** | `npm run typecheck` | 1 | 1 | 0 | 3.50s |
| **Dual Production Build** | `npm run build` | 2 | 2 | 0 | 1.80s |
| **Headless Browser Suite** | `scripts/runtime_verification.py` | 12 | 12 | 0 | 14.50s |

---

## 2. Test Details & Assertions

### 2.1 Database & Persistence Tests (`test_database.py`)
- `test_repeatable_migrations`: Applies migration 001 repeatedly; verifies idempotency in `schema_migrations`.
- `test_foreign_key_enforcement`: Asserts `sqlite3.IntegrityError` when referencing a non-existent `source_id`.
- `test_unique_hash_parser_constraint`: Asserts `sqlite3.IntegrityError` when inserting identical `(sha256, parser_id, parser_version)`.
- `test_transactional_batch_persistence`: Verifies atomic insertion of job metadata, parsed records, and error rows across a single `BEGIN IMMEDIATE`/`COMMIT` boundary.
- `test_persistence_across_reconnect`: Verifies database state persists across connection close and re-open.
- `test_reconcile_pending_jobs_on_restart`: Confirms dangling `pending` jobs from simulated server crashes reconcile to `failed`.

### 2.2 Strict Parsers Tests (`test_parsers.py`)
- `test_parser_registry`: Validates registry discovery for `generic_jsonl`, `auth_csv`, `web_access_csv`.
- `test_generic_jsonl_parser_valid_and_errors`: Evaluates JSON syntax errors, non-object JSON arrays, line error attribution, and inert handling of prompt injection text.
- `test_generic_jsonl_utf8_bom_handling`: Confirms UTF-8 BOM (`\ufeff`) is cleanly stripped without corrupting first line.
- `test_auth_csv_parser_valid_and_errors`: Tests allowed outcome set (`SUCCESS`, `FAILURE`, `CHALLENGE`, `LOCKED`), missing columns, and column count mismatches.
- `test_auth_csv_missing_header_columns`: Tests rejection of CSV missing required columns.
- `test_web_access_csv_valid_and_errors`: Tests HTTP verb validation, status code bounds (100–599), and type conversions.
- `test_max_line_length_protection`: Verifies lines exceeding 1MB limit are rejected before memory exhaustion.

### 2.3 Import Engine & Ingestion Tests (`test_import_engine.py`)
- `test_sanitizer_scrubs_secrets`: Verifies passwords, API keys, tokens, session IDs, and inline bearer headers are replaced with `[REDACTED]`.
- `test_successful_ingestion`: Verifies full ingestion cycle, hash calculation, and record persistence.
- `test_deduplication_skips_identical_file`: Verifies identical file and parser returns `status="skipped"`, `duplicate=True`, and creates 0 new database rows.
- `test_partial_ingestion_with_row_errors`: Verifies partial status and error row attribution in `import_errors`.
- `test_file_size_limit_rejection`: Confirms files > 20MB are rejected immediately.
- `test_empty_file_rejection`: Confirms empty 0-byte files are rejected.

### 2.4 Inbox Scanner Tests (`test_scanner.py`)
- `test_path_safety_validation`: Rejects root directories, system directories (`C:\Windows`), and home directories.
- `test_parser_inference`: Correctly maps filename extensions to parser profiles.
- `test_scan_once_ingests_and_preserves_files`: Ingests file, confirms original file is **never deleted or moved**, and second scan cycle skips it via SHA-256 deduplication.
- `test_non_recursive_scanning`: Ignores files placed inside nested subdirectories.
- `test_pause_and_resume`: Halts file processing while paused; resumes cleanly.

### 2.5 API Integration Tests (`test_import_api.py`)
- `test_get_parsers_endpoint`: Returns list of registered parsers.
- `test_get_sources_endpoint`: Returns list of registered sources.
- `test_post_import_json_payload`: Tests `POST /api/import` with JSON body.
- `test_post_import_multipart_payload`: Tests `POST /api/import` with `multipart/form-data`.
- `test_list_and_get_imports`: Tests `GET /api/imports` and `GET /api/imports/{id}`.
- `test_import_invalid_parser_returns_422`: Returns HTTP 422 for unknown parser profile.

### 2.6 Headless Chrome Runtime Verification (`runtime_verification.py`)
- Full browser runtime execution against standalone production build (`http://127.0.0.1:4173`) and live backend (`http://127.0.0.1:8000`):
  1. Initial UI render and `Backend Connected` operational pill.
  2. All 8 routes rendered in browser: `overview`, `investigations`, `findings`, `events`, `replay`, `sources`, `digests`, `settings`.
  3. Sources view verified with configured event sources, manual file import form, and genuine import history table.
  4. Backend termination triggers `Backend Unavailable` offline banner and recovery instructions.
  5. Backend restart triggers immediate automatic recovery to `Backend Connected`.
  6. Clean teardown with zero orphaned processes.

---

## 3. Quality Gate Hook Verification

Execution of `.kiro/hooks/validate-all.ps1`:
```text
==> [Hook] Running Project Sentinel Validation...
--> Running Backend Unit & Contract Tests...
Ran 36 tests in 1.882s
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
==> [Hook] All Quality Gates Passed Cleanly!
```

