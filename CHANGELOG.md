# Changelog

All notable changes to Project Sentinel will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-11-09 (Phase 3: Canonical Event Normalization, Provenance & Data Integrity)
### Added
- **Canonical Event Normalization Engine:** Implemented deterministic transformation engine (`backend/normalization/engine.py`) converting pre-normalized records into canonical `NormalizedEventContract` instances.
- **Parser-Specific Mappers:** Built dedicated mappers for all three supported formats (`backend/normalization/mappers.py`):
  - `GenericJsonlMapper`: Resolves candidate timestamp, user principal, source IP, target resource, and outcome keys.
  - `AuthCsvMapper`: Normalizes authentication credentials and outcomes (`SUCCESS`, `FAILURE`, `LOCKED`, `CHALLENGE`).
  - `WebAccessCsvMapper`: Normalizes HTTP requests, mapping HTTP status codes (100–399 $\rightarrow$ `SUCCESS`, 400–499 $\rightarrow$ `FAILURE`, 500–599 $\rightarrow$ `ERROR`).
- **Strict Timestamp Normalization:** Built robust UTC parsing (`backend/normalization/timestamps.py`) with timezone offset preservation, ISO-8601 UTC output, epoch handling, explicit naive timestamp metadata annotation (`"timezone_inferred": "UTC_ASSUMED"`), and rejection of invalid timestamps without silent `datetime.now()` fallback.
- **Deterministic Event Identity:** Formula `evt_` + SHA-256(`source_sha256:record_number:parser_id:norm_version`)[0:24] providing reproducible, collision-resistant event IDs across re-runs.
- **Database Migration 002:** Added `normalized_events` table with unique constraint on `(record_id, normalization_version)`, indexes on timestamp/type/user/IP, and `normalization_errors` table for structured diagnostic capture of unmappable lines (`backend/persistence/migrations.py`).
- **Normalization API Endpoints:** Added `POST /api/normalization/run`, `GET /api/events` (with dynamic filtering by status, event type, user, source, import), `GET /api/events/{id}` (with complete provenance), `GET /api/normalization/stats`, and `GET /api/normalization/errors` (`backend/api/handler.py`).
- **Interactive Events UI:** Activated `EventsView` in `apps/crew-app` featuring aggregate normalization metrics, filter toolbar, interactive events stream table, and comprehensive Event Inspector drawer detailing immutable SHA-256 provenance and formatted attributes JSON.
- **Comprehensive Automated Test Suites:** Added `test_normalization_db.py`, `test_timestamps.py`, `test_normalization_engine.py`, `test_events_api.py`, and `test_e2e_normalization.py` bringing total backend tests to 68 passing tests.
- **Provenance & Architecture Documentation:** Created `docs/PHASE_3_NORMALIZATION_DESIGN.md`, `docs/provenance.md`, and updated `docs/event-schema.md`, `docs/ingestion.md`, and `docs/threat-model.md`.

## [0.2.0] - 2026-11-09 (Phase 2: Core Data Pipeline, SQLite, Parsers & Secure Ingestion)
### Added
- **SQLite Persistence Foundation:** Created persistent SQLite storage outside repository (`%LOCALAPPDATA%\ProjectSentinel\sentinel.db`) with WAL mode, foreign key enforcement, 5000ms busy timeout, and versioned migration runner (`backend/persistence/`).
- **Strict Log Parsers:** Implemented three distinct parser profiles (`backend/parsers/`):
  - `generic_jsonl`: Line-by-line JSON objects, UTF-8 BOM stripping, timestamp/event type extraction.
  - `auth_csv`: Authentication log parser with outcome validation (`SUCCESS`, `FAILURE`, `CHALLENGE`, `LOCKED`).
  - `web_access_csv`: HTTP access log parser validating standard verbs and status code bounds (100–599).
  - Parser registry (`backend/parsers/registry.py`) providing dynamic discovery and metadata.
- **Pre-Persistence Sanitizer:** Scrubbing of cleartext passwords, tokens, API keys, and Authorization Bearer headers prior to storage (`backend/ingestion/sanitizer.py`).
- **Core Ingestion Engine:** `ImportEngine` coordinating SHA-256 calculation, duplicate check, 20MB file limits, 100,000 record bounds, and atomic database transactions (`backend/ingestion/engine.py`).
- **Approved Inbox Scanner:** Background polling scanner for approved directory with path traversal defense, symlink escape checks, file stability validation, and non-destructive processing (`backend/ingestion/scanner.py`).
- **Manual Import API:** Endpoints `POST /api/import` (supporting multipart and JSON payloads without deprecated `cgi`), `GET /api/imports`, `GET /api/imports/{id}`, `GET /api/sources`, and `GET /api/parsers` (`backend/api/`).
- **Interactive Sources UI:** Activated `SourcesView` in `apps/crew-app` displaying configured event sources, manual file ingestion controls with immediate diagnostics, and genuine historical import table from SQLite.
- **Comprehensive Test Suites:** Added database unit tests (`test_database.py`), parser unit tests (`test_parsers.py`), ingestion engine tests (`test_import_engine.py`), scanner tests (`test_scanner.py`), and import API integration tests (`test_import_api.py`).
- **Comprehensive Documentation:** Created `docs/PHASE_2_DATABASE_DESIGN.md`, `docs/PHASE_2_IMPLEMENTATION_REPORT.md`, `docs/PHASE_2_TEST_REPORT.md`, `docs/event-schema.md`, `docs/ingestion.md`, and `docs/threat-model.md`.

## [0.1.1] - 2026-11-09 (Phase 1.5 Hardening)
### Security
- Eliminated wildcard CORS (`*`). Implemented strict origin validation (`backend/config/settings.py`) with `Vary: Origin`.
- Added 403 Forbidden rejection for unauthorized OPTIONS preflight requests.
- Added `X-Content-Type-Options: nosniff` and `X-Frame-Options: DENY` HTTP security headers.
- Hardened exception handling to prevent traceback leakage on 500 errors.

### Fixed
- Fixed fetch fallback bug in `App.tsx` where static server HTTP 404 responses bypassed catch blocks.
- Fixed missing Vite client type declarations in `src/vite-env.d.ts`.
- Fixed Kiro Crew agent schema in `agents/sentinel-investigator.json` by adding `model` and `tools` fields.

### Added
- Automated headless browser runtime verification script (`scripts/runtime_verification.py`) validating all 8 routes and disconnect/reconnect lifecycle in Google Chrome headless.
- CORS security unit test suite (`tests/unit/test_cors_security.py`).
- Phase 1.5 verification report (`docs/PHASE_1_5_VERIFICATION_REPORT.md`).

## [0.1.0] - 2026-11-09
### Added
- Phase 1 execution: repository structure and engineering foundation established.
- Kiro development configuration: `.kiro/steering` (`product.md`, `architecture.md`, `security.md`, `testing.md`, `design.md`) and `.kiro/specs` (`01-product-and-judge-experience.md`, `02-crew-app-shell.md`).
- Kiro Crew App package definition (`apps/crew-app/app.json`, agent definition, skill definition).
- Application shell with restrained cybersecurity design system, 8-route navigation, Overview dashboard, and live backend connectivity status.
- Zero fake metrics or placeholder hallucinations: real empty states, loading states, and error handling.
- Lightweight standard Python backend with `GET /health` and `GET /api/health` endpoints.
- Backend automated unit test suite.
- Architecture and Phase 1 audit and runbook documentation.
