# Changelog

All notable changes to Project Sentinel will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-11-09 (Phase 6: Claim Guard: Typed AI Claims, Deterministic Verification & Safe Rendering)
### Added
- **Typed AI Claims Schema & Contract:** Created `shared/contracts/claim_contract.json` specifying a finite vocabulary of 8 claim types (`event_count`, `finding_exists`, `rule_match`, `time_window`, `entity_observed`, `case_status`, `correlation_relationship`, `data_quality_issue`) and strict predicates.
- **Core Claim Models:** Implemented `ClaimProposal`, `VerificationCheck`, and `ClaimVerificationResult` dataclasses (`backend/claims/models.py`) with strict schema validation and string length enforcement.
- **Approved Template Catalog:** Defined `APPROVED_TEMPLATES` (`backend/claims/templates.py`) providing 8 vetted templates with required parameters for rendering factual and qualified statements.
- **Safe Claim Renderer:** Implemented `SafeClaimRenderer` (`backend/claims/renderer.py`) enforcing HTML entity escaping via `html.escape()`, prefixing `[QUALIFIED]` caveats, and strictly quarantining blocked claims (`[BLOCKED CLAIM]`) with failure reasons and remedies.
- **Deterministic 9-Stage Verifier:** Implemented `ClaimVerifier` (`backend/claims/verifier.py`) executing schema check, template vetting, injection scanning, case containment, mathematical value validation, IP-only identity guardrails, data quality checks, certainty alignment, and safe rendering without LLM self-evaluation.
- **Claim Guard Orchestration Engine:** Implemented `ClaimGuardEngine` (`backend/claims/engine.py`) orchestrating batch claim processing, SQLite persistence, and the signature "Claim Guard Demo Moment" (`generate_demo_claims`).
- **Database Migration 006:** Added `claim_proposals` and `claim_verifications` tables with cascading foreign keys to `cases(case_id)` and fast query indexes (`backend/persistence/migrations.py`).
- **Repository Integration:** Added `persist_claim_proposal`, `persist_claim_verification`, `get_claim`, `list_case_claims`, and `list_all_claims` (`backend/persistence/repository.py`). Updated `get_case(case_id)` to embed verified claims.
- **REST API Endpoints:** Added `POST /api/claims/verify`, `POST /api/cases/{id}/claims/demo`, `POST /api/cases/{id}/claims/propose`, `GET /api/claims/templates`, `GET /api/cases/{id}/claims`, and `GET /api/claims/{id}` (`backend/api/handler.py`).
- **Analyst Workspace UI:** Built a dedicated Claim Guard tab in `CasesView.tsx` with real-time metrics cards, verified/qualified/blocked panels, clickable evidence chips, and the interactive demo trigger.
- **Kiro Skill Update:** Updated `apps/crew-app/skills/evidence-led-investigation/SKILL.md` with Claim Guard JSON schema, approved templates, and operational guardrails.
- **Automated Test Suites:** Added `test_claim_models.py`, `test_claim_verifier.py`, `test_claim_security.py`, `test_claims_api.py`, and `test_e2e_claims.py`, expanding test suite to 169 passing tests (0 failures, 0 errors, 0 skipped).
- **Real Workflow Verification Script:** Added `scripts/verify_real_claim_guard_workflow.py` testing multi-source log import, normalization, detection, correlation, demo execution, adversarial injection tests, and direct SQLite foreign-key auditing.
- **Documentation:** Created `docs/PHASE_6_CLAIM_GUARD_DESIGN.md`, `docs/PHASE_6_IMPLEMENTATION_REPORT.md`, `docs/PHASE_6_TEST_REPORT.md`, and updated `docs/threat-model.md` and `docs/kiro-usage.md`.

## [0.5.0] - 2026-11-09 (Phase 5: Investigation Cases, Deterministic Correlation & Timeline)
### Added
- **Deterministic Correlation Engine:** Implemented `CorrelationEngine` (`backend/cases/engine.py`) that clusters related security findings and canonical events into unified cases using approved identity keys (`user_principal`, `session_id`, `request_id`) and temporal observation windows (default 3600 seconds).
- **IP-Only Correlation Guardrail:** Disabled IP-only grouping by default (`enable_ip_correlation = False`) to prevent catastrophic false clustering across shared NAT, proxies, and mobile cellular networks. Source IP is preserved as contextual network evidence only.
- **Deterministic Case Identity Derivation:** Collision-resistant case ID derivation `case_` + SHA256(`key_type:key_value:window_bucket`)[0:20].
- **Transparent Severity Derivation:** Transparent derivation of case severity as the maximum severity of linked findings, recording an explicit rationale.
- **Unified Chronological Evidence Timeline:** Dynamically merges canonical events, detection findings, correlation summaries, and operator review actions into a strict UTC chronological sequence (`backend/persistence/repository.py`).
- **Database Migration 005:** Added `cases` table with unique constraint `uq_case_dedupe (correlation_key_type, correlation_key_value, dedupe_key)`, `case_findings` junction table, `case_events` junction table, `review_actions` append-only audit log table, and `correlation_evaluations` performance table (`backend/persistence/migrations.py`).
- **Append-Only Analyst Review Log:** Capture of operator triage notes, decisions, and status transitions in `review_actions` without mutating original evidence.
- **Strict State Machine Lifecycle Validation:** Enforced transitions across `Open`, `UnderReview`, `NeedsMoreEvidence`, `Resolved`, and `Dismissed` (`backend/cases/models.py`). Illegal transitions raise immediate validation errors.
- **REST API Endpoints:** Added `GET /api/cases`, `GET /api/cases/stats`, `GET /api/cases/{id}`, `POST /api/cases/correlate`, `POST /api/cases/{id}/review`, and `PATCH /api/cases/{id}` (`backend/api/handler.py`).
- **Interactive Cases UI:** Activated `CasesView` in `apps/crew-app` featuring summary metrics bar, correlation execution button, dynamic search and filters, cases table, and deep-dive drawer with unified timeline, finding condition inspect modal, and review action submission.
- **Automated Test Suites:** Added `test_correlation_engine.py`, `test_cases_db.py`, `test_cases_api.py`, and `test_e2e_cases.py`, bringing total platform tests to 128 passing tests.
- **Real Workflow Verification Script:** Added `scripts/verify_real_case_workflow.py` testing multi-source log import, normalization, detection, correlation, analyst review, direct SQLite verification, and re-evaluation idempotency.
- **Documentation:** Created `docs/PHASE_5_CASE_DESIGN.md`, `docs/PHASE_5_IMPLEMENTATION_REPORT.md`, `docs/PHASE_5_TEST_REPORT.md`, `docs/cases.md`, and `docs/correlation.md`.

## [0.4.0] - 2026-11-09 (Phase 4: Deterministic Detection Rules & Explainable Findings)
### Added
- **Deterministic Detection Engine:** Implemented chronological sliding-window detection orchestrator (`backend/detection/engine.py`) evaluating canonical events against versioned rules without machine learning or probabilistic guessing.
- **5 Built-in Detection Rules:**
  - `AUTH-001` (Repeated Authentication Failures): 5 failures within 10 minutes.
  - `AUTH-002` (Success After Failures): Successful login within 30 minutes following an `AUTH-001` burst.
  - `WEB-001` (Sensitive Route Burst): 3 requests to sensitive endpoints within 15 minutes.
  - `PRIV-001` (Explicit Privilege Escalation): Direct detection of administrative role alterations and grants.
  - `INGEST-001` (Data Quality Anomaly): Detection of future-dated events and quarantined normalization records.
- **Deterministic Finding Identity:** Collision-resistant SHA-256 derivation `find_` + SHA256(`rule_id:version:config_hash:dedupe_key`)[0:24].
- **Database Migration 004:** Added `detection_rules` table (seeded with all 5 default rules), `findings` table with `uq_finding_dedupe UNIQUE (rule_id, rule_version, dedupe_key)`, `finding_events` junction table with `FOREIGN KEY (event_id) REFERENCES normalized_events(event_id) ON DELETE RESTRICT`, `rule_evaluations` audit table, and performance indexes (`backend/persistence/migrations.py`).
- **Relational Findings Repository:** High-performance persistence methods (`backend/persistence/repository.py`) supporting atomic batch persistence (`INSERT OR IGNORE`), duplicate tracking, foreign-key evidence joining, dynamic filtering, pagination, and status management.
- **REST API Endpoints:** Added `GET /api/rules`, `GET /api/rules/{id}`, `PATCH /api/rules/{id}`, `POST /api/detection/run`, `GET /api/detection/stats`, `GET /api/findings`, `GET /api/findings/{id}`, and `PATCH /api/findings/{id}` (`backend/api/handler.py`).
- **Interactive Findings UI:** Activated `FindingsView` in `apps/crew-app` featuring summary metrics bar, detection engine trigger, severity/status filters, detailed inspection drawer with joined evidence events, and rules catalogue modal with toggle switches.
- **Automated Test Suites:** Added `test_rule_validation.py`, `test_rule_evaluation.py`, `test_findings_db.py`, `test_findings_api.py`, `test_detection_security.py`, and `test_e2e_detection.py`, bringing total platform tests to 107 passing tests.
- **Specifications & Documentation:** Created `docs/PHASE_4_DETECTION_DESIGN.md`, `docs/PHASE_4_IMPLEMENTATION_REPORT.md`, `docs/PHASE_4_TEST_REPORT.md`, `docs/detection-rules.md`, `docs/findings.md`, and updated `docs/threat-model.md`.

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
