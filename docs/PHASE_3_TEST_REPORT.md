# Project Sentinel — Phase 3 Test Report
**Test Suite:** Unit, Contract, Integration, Persistence, Normalization, Security, and Headless Browser Verification  
**Sprint:** Sprint 3 (Canonical Event Normalization, Provenance & Data Integrity)  
**Date:** 2026-11-09  
**Result:** 100% PASS (68/68 Backend Tests, Dual Frontend Build, All Headless Browser Tests)  

---

## 1. Test Execution Overview

All test suites were executed sequentially and verified in clean test environments utilizing ephemeral databases and temporary directories.

| Test Category | Suite File | Total Tests | Passed | Failed | Duration |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **API Contracts** | `tests/contract/test_api_contracts.py` | 1 | 1 | 0 | 0.08s |
| **Configuration** | `tests/unit/test_config.py` | 2 | 2 | 0 | 0.01s |
| **CORS & Security** | `tests/unit/test_cors_security.py` | 5 | 5 | 0 | 0.09s |
| **Database & Persistence (Phase 2)** | `tests/unit/test_database.py` | 6 | 6 | 0 | 0.08s |
| **Database & Normalization (Phase 3)** | `tests/unit/test_normalization_db.py` | 6 | 6 | 0 | 0.10s |
| **Timestamp Parsing & UTC Normalization** | `tests/unit/test_timestamps.py` | 6 | 6 | 0 | 0.01s |
| **Normalization Engine & Mappers** | `tests/unit/test_normalization_engine.py` | 6 | 6 | 0 | 0.09s |
| **Health API** | `tests/unit/test_health.py` | 4 | 4 | 0 | 0.08s |
| **Strict Parsers** | `tests/unit/test_parsers.py` | 7 | 7 | 0 | 0.01s |
| **Import Engine & Sanitizer** | `tests/unit/test_import_engine.py` | 6 | 6 | 0 | 0.07s |
| **Approved Inbox Scanner** | `tests/unit/test_scanner.py` | 5 | 5 | 0 | 0.12s |
| **Import API Integration** | `tests/integration/test_import_api.py` | 6 | 6 | 0 | 0.61s |
| **Events API Integration** | `tests/integration/test_events_api.py` | 2 | 2 | 0 | 0.64s |
| **End-to-End Normalization Pipeline** | `tests/integration/test_e2e_normalization.py` | 1 | 1 | 0 | 0.61s |
| **Kiro Manifest Validation** | `scripts/validate_manifest.py` | 1 | 1 | 0 | 0.05s |
| **Frontend Typecheck** | `npm run typecheck` | 1 | 1 | 0 | 3.20s |
| **Dual Production Build (SPA + ESM)** | `npm run build` | 2 | 2 | 0 | 1.70s |
| **Headless Browser Runtime Verification**| `scripts/runtime_verification.py` | 5 | 5 | 0 | 16.20s |
| **Real Normalization & SQLite Audit** | `scripts/verify_real_normalization_workflow.py` | 6 | 6 | 0 | 1.80s |

---

## 2. Test Details & Assertions

### 2.1 Database & Normalization Persistence Tests (`test_normalization_db.py`)
- `test_migrations_applied`: Confirms migration 1 (`001_initial_schema`) and migration 2 (`002_canonical_events_and_provenance`) are tracked in `schema_migrations`.
- `test_get_unnormalized_records`: Asserts unnormalized records are correctly discovered and filtered when records are already processed or errored.
- `test_persist_and_query_normalized_events`: Persists batch of canonical events with unpacked attributes JSON; asserts fields and values match.
- `test_idempotency_prevents_duplicate_events`: Re-persisting identical events safely triggers `INSERT OR IGNORE` via `uq_record_norm_version`.
- `test_normalization_errors_persistence`: Stores structured normalization errors into `normalization_errors` table and verifies exclusion from pending record queue.
- `test_list_normalized_events_filtering`: Evaluates dynamic SQL filtering by `event_type`, `user_principal`, and verifies aggregate `get_normalization_stats()`.

### 2.2 Timestamp Parsing & UTC Normalization Tests (`test_timestamps.py`)
- `test_utc_iso_string_with_z`: Preserves valid UTC date-time string terminating in `Z`; flags `is_naive = False`.
- `test_offset_conversion_to_utc`: Correctly converts positive (`+02:00`) and negative (`-05:00`) timezone offsets into absolute UTC `YYYY-MM-DDTHH:MM:SSZ`.
- `test_naive_timestamp_flagged`: Correctly detects naive strings (e.g. `2026-11-09 08:00:15`) and flags `is_naive = True`.
- `test_subsecond_precision_preserved`: Retains microsecond fractional seconds.
- `test_epoch_numeric_and_string`: Converts Unix epoch seconds and milliseconds into UTC datetime.
- `test_invalid_timestamps_raise_value_error`: Asserts that `None`, empty string, and unparseable dates raise `ValueError` (guaranteeing no silent fallback to `datetime.now()`).

### 2.3 Normalization Engine & Mappers Tests (`test_normalization_engine.py`)
- `test_compute_event_id_deterministic`: Confirms deterministic SHA-256 derivation `evt_...`; same inputs produce identical IDs, different inputs produce distinct IDs.
- `test_generic_jsonl_mapper`: Maps candidate keys for user, IP, target resource, outcome (`SUCCESS`/`FAILURE`/`ERROR`), and preserves attributes.
- `test_auth_csv_mapper`: Validates mapping of authentication outcomes (`SUCCESS` $\rightarrow$ `SUCCESS`, `FAILURE`/`LOCKED` $\rightarrow$ `FAILURE`, `CHALLENGE` $\rightarrow$ `UNKNOWN`).
- `test_web_access_csv_mapper`: Validates HTTP status code mapping (200 $\rightarrow$ `SUCCESS`, 401 $\rightarrow$ `FAILURE`, 500 $\rightarrow$ `ERROR`).
- `test_normalization_engine_error_handling`: Verifies quarantine into `normalization_errors` for invalid timestamps (`NORM_INVALID_TIMESTAMP`), malformed JSON (`NORM_INVALID_PAYLOAD`), and unknown parsers (`NORM_UNKNOWN_PARSER`).
- `test_run_normalization_end_to_end`: Tests full repository-backed normalization run, error recording, and verified 0 unnormalized remaining.

### 2.4 Events API Integration Tests (`test_events_api.py`)
- `test_events_empty_initially`: `GET /api/events` returns empty array and total 0 on fresh database.
- `test_import_and_normalize_workflow`: Ingests auth CSV via `POST /api/import`, triggers `POST /api/normalization/run`, queries `GET /api/events` with filter `status=FAILURE`, queries single event `GET /api/events/{id}`, asserts 404 on nonexistent event ID, and checks `GET /api/normalization/stats`.

### 2.5 End-to-End Multi-Format Normalization Test (`test_e2e_normalization.py`)
- `test_multi_format_normalization_pipeline`: Uploads both Web Access CSV and JSONL files, verifies pending count = 5, executes normalization, queries cross-source events, asserts naive timestamp annotation in attributes (`"timezone_inferred": "UTC_ASSUMED"`), verifies status classification across HTTP status codes, and asserts idempotency across re-runs.

### 2.6 Headless Chrome Runtime Verification (`scripts/runtime_verification.py`)
- Verified all 8 routes in real headless Chromium: `overview`, `investigations`, `findings`, `events`, `replay`, `sources`, `digests`, `settings`.
- Verified `EventsView` interactive elements rendered in DOM: title header, aggregate metrics bar ("Total Normalized Events"), "Run Normalization" action button, and canonical events table headers.
- Verified backend disconnect and reconnect lifecycle.

### 2.7 Real Browser & SQLite Audit Workflow (`scripts/verify_real_normalization_workflow.py`)
- Multi-format ingestion $\rightarrow$ Normalization execution $\rightarrow$ Filtered event queries $\rightarrow$ Single event inspection $\rightarrow$ Direct SQLite database file inspection on disk (`%LOCALAPPDATA%\ProjectSentinel\sentinel.db`).
- Verified foreign key linkage between `normalized_events.record_id` and `parsed_records.record_id`.
- Verified indexes `idx_norm_events_ts` and unique constraint `uq_record_norm_version`.

---

## 3. Conclusion & Sprint 4 Sign-Off

Phase 3 is **100% COMPLETE AND PASSING**.
Zero test failures, zero test skips, zero invented data, and zero regressions across all Phase 1, Phase 1.5, Phase 2, and Phase 3 deliverables.
The repository is fully ready for **Phase 4: Deterministic Rules & Findings Generation**.

