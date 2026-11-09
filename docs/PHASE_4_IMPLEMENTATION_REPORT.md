# Project Sentinel — Phase 4 Implementation Report
**Sprint 4: Deterministic Detection Rules & Explainable Findings**  
**Execution Timestamp:** 2026-11-09T20:51:00Z  
**Implementation Lead:** Principal Software Architect, Detection Engineer & QA Lead  
**Overall Status:** **COMPLETED & VERIFIED (PASS)**

---

## 1. Architectural Objectives & Executive Summary

Sprint 4 introduces Project Sentinel's **Deterministic Detection Engine** and **Evidence-Backed Findings** capability.

Prior to Sprint 4, Sentinel successfully established:
- Phase 1 & 1.5: Foundation shell, Kiro development setup, offline resilience, and frontend routing.
- Phase 2 & 2.5: Secure multi-format log ingestion, parser profiles, SHA-256 deduplication, and SQLite persistence.
- Phase 3 & 3.5: Canonical event normalization, timezone-aware conversion, provenance tracking, and data integrity quarantine.

Sprint 4 builds directly upon the canonical event foundation by evaluating normalized events through deterministic sliding windows and state transitions to produce explainable, relational security findings.

### Core Deliverables Completed:
1. **Detection Models & Configuration Hashing:** Dataclasses for versioned rule definitions, findings, and evaluation metrics with SHA-256 configuration hashing (`backend/detection/models.py`).
2. **Deterministic Rules Suite:** 5 security rules with explicit sliding windows, thresholding, deduplication keys, and analyst limitations (`backend/detection/rules.py`).
3. **Detection Engine & Rule Registry:** Engine orchestrating batch retrieval of canonical events, chronological sliding-window evaluation, atomic persistence, duplicate tracking, and audit logging (`backend/detection/engine.py`).
4. **Database Schema (Migration 004):** Migration adding `detection_rules`, `findings`, `finding_events` junction table, `rule_evaluations`, and performance indexes (`backend/persistence/migrations.py`).
5. **Relational Findings Repository:** High-performance persistence methods supporting atomic batch inserts (`INSERT OR IGNORE`), duplicate suppression via `uq_finding_dedupe`, foreign-key junction records, dynamic filtering, pagination, and status transitions (`backend/persistence/repository.py`).
6. **REST API Endpoints:** Complete API suite for listing rules, toggling rules, executing detection runs, retrieving detection statistics, paginating findings, and updating finding status (`backend/api/handler.py`).
7. **Frontend Findings Interface:** Full dark graphite UI in `FindingsView.tsx` with metrics bar, execution triggers, dynamic filters, finding details drawer with full supporting event inspection, and rules catalogue modal with toggle switches.
8. **Automated Test Suite & Verification:** 38 new automated unit and integration tests (bringing the complete platform suite to 107 passing tests) and automated verification scripts.

---

## 2. Detailed Technical Implementation

### 2.1 Detection Core Architecture (`backend/detection/`)

- **`RuleDefinition`**: Versioned detection rule model containing `rule_id`, `version`, `name`, `description`, `severity`, `enabled`, `config`, `limitations`, and automatic SHA-256 `config_hash`.
- **`Finding`**: Relational finding entity containing `finding_id`, `rule_id`, `rule_version`, `rule_config_hash`, `severity`, `status`, `title`, `description`, `first_observed_at`, `last_observed_at`, `matched_entity`, `matched_conditions`, `supporting_event_ids`, `limitations`, and `dedupe_key`.
- **`compute_finding_id()`**: Collision-resistant deterministic identifier derivation:
  $$\text{Seed} = \text{rule\_id} : \text{rule\_version} : \text{rule\_config\_hash} : \text{dedupe\_key}$$
  $$\text{finding\_id} = \text{"find\_"} + \text{SHA256}(\text{Seed})[0:24]$$
- **`RuleRegistry`**: In-memory registry with strict schema validation (`validate_rule_definition()`), holding built-in rules and synchronizing with SQLite `detection_rules` table.
- **`DetectionEngine`**: Orchestrator executing the evaluation cycle:
  1. Synchronizes rule enabled states from SQLite.
  2. Queries canonical `normalized_events` ordered chronologically by `timestamp ASC`.
  3. Queries quarantined `normalization_errors` for ingestion anomaly analysis.
  4. Evaluates each enabled rule evaluator against the event stream.
  5. Atomically persists generated findings via `persist_findings_batch()`.
  6. Records audit metrics in `rule_evaluations`.

### 2.2 Built-in Detection Rules

1. **`AUTH-001` (Repeated Authentication Failures):**
   - *Logic:* $\ge 5$ failures for the same `user_principal` within a 10-minute sliding window (600 seconds).
   - *Severity:* `Medium`
   - *Dedupe Key:* `auth_fail:{user_principal}:{epoch // 600}`
   - *Limitations:* Explicitly cites user error, forgotten password, or misconfigured backup script.
2. **`AUTH-002` (Success After Failures):**
   - *Logic:* Successful authentication within 30 minutes (1800 seconds) following an `AUTH-001` failure burst for the same user.
   - *Severity:* `High`
   - *Dedupe Key:* `auth_succ_after_fail:{user_principal}:{success_event_id}`
   - *Limitations:* Highlights that log data cannot identify the human at the keyboard.
3. **`WEB-001` (Sensitive Route Burst):**
   - *Logic:* $\ge 3$ requests to sensitive administrative routes (`/admin`, `/api/v1/auth`, `/login`, `/wp-admin`, `/.env`, etc.) from the same source IP/entity within 15 minutes (900 seconds).
   - *Severity:* `Medium`
   - *Dedupe Key:* `sensitive_route:{entity}:{epoch // 900}`
   - *Limitations:* Contextualizes between successful breach (HTTP 200) vs denied reconnaissance (HTTP 401/403/404).
4. **`PRIV-001` (Explicit Privilege Change):**
   - *Logic:* Immediate detection of administrative role alterations, grants, or privilege escalations (`role_changed`, `grant_role`, `sudo`).
   - *Severity:* `High`
   - *Dedupe Key:* `priv_change:{event_id}`
   - *Limitations:* Cites legitimate administrative onboarding and scheduled maintenance.
5. **`INGEST-001` (Ingestion & Timestamp Data Quality Anomaly):**
   - *Logic:* Detection of events dated $> 24$ hours into the future, clock skew, or quarantined naive timestamps in `normalization_errors`.
   - *Severity:* `Info`
   - *Dedupe Key:* `future_date:{event_id}` or `ingest_errors:{import_id}:{error_code}`
   - *Limitations:* Explicitly clarifies that this represents telemetry format failure, not direct attack evidence.

### 2.3 Database Schema Migration 004 (`backend/persistence/migrations.py`)

- **`detection_rules` table:** Stores rule definitions and enabled toggles. Seeded with all 5 default rules.
- **`findings` table:** Stores finding records with constraint `CONSTRAINT uq_finding_dedupe UNIQUE (rule_id, rule_version, dedupe_key)` and `FOREIGN KEY (rule_id) REFERENCES detection_rules(rule_id) ON DELETE RESTRICT`.
- **`finding_events` junction table:** Relational junction table linking findings to evidence events with `FOREIGN KEY (finding_id) REFERENCES findings(finding_id) ON DELETE CASCADE` and `FOREIGN KEY (event_id) REFERENCES normalized_events(event_id) ON DELETE RESTRICT`.
- **`rule_evaluations` audit table:** Tracks execution runs (`evaluation_id`, `evaluated_at`, `rule_count`, `events_scanned`, `findings_generated`, `findings_duplicate`, `duration_ms`).
- **Indexes:** `idx_findings_rule_id`, `idx_findings_severity`, `idx_findings_status`, `idx_findings_observed`, `idx_finding_events_event`, `idx_rule_eval_time`.

### 2.4 Repository Persistence Operations (`backend/persistence/repository.py`)

- `persist_findings_batch()`: Atomic batch insertion using `INSERT OR IGNORE` and junction record population.
- `get_finding()`: Fetches finding by ID, deserializes matched conditions and supporting event IDs, and joins detailed `normalized_events` records.
- `list_findings()`: Dynamic parameterized filtering by `severity`, `status`, `rule_id`, with limit/offset pagination and total match count.
- `update_finding_status()`: Transactionally updates status to `open`, `acknowledged`, `resolved`, or `dismissed`, updating `updated_at`.
- `record_evaluation_audit()`: Writes audit log entry to `rule_evaluations`.
- `get_detection_stats()`: Aggregates counts by severity, status, and retrieves the most recent evaluation run.
- `list_detection_rules()`, `get_detection_rule()`, `update_detection_rule_enabled()`: Rules management.

### 2.5 REST API Endpoints (`backend/api/handler.py`)

- `GET /api/rules`: Returns all registered detection rules.
- `GET /api/rules/{id}`: Returns single rule definition and config.
- `PATCH /api/rules/{id}`: Toggles rule `enabled` state.
- `POST /api/detection/run`: Triggers detection run and returns execution statistics.
- `GET /api/detection/stats`: Returns findings summary by severity, status, and last evaluation.
- `GET /api/findings`: Returns paginated findings with dynamic filtering.
- `GET /api/findings/{id}`: Returns finding details and joined supporting events.
- `PATCH /api/findings/{id}`: Updates finding status (`acknowledged`, `resolved`, etc.).
- Updated CORS handler to allow `PATCH` method.

### 2.6 Frontend Findings View (`apps/crew-app/src/components/Views/FindingsView.tsx`)

- Dark graphite styling conforming to design tokens (`#0f172a`, `#161b22`, `#21262d`, `#30363d`).
- Summary metrics bar: Total Findings, High/Critical count, Medium count, Open count, and Last Evaluation status.
- Primary interactive triggers: "Run Detection Engine" (with loading state and success feedback) and "Rules Catalogue" button.
- Filtering controls: Severity dropdown, Status dropdown, Rule dropdown, and text search input.
- Findings table: Columns for Severity badge, Rule ID, Title & Matched Entity, Observed Time, Supporting Events count, Status, and Action.
- Finding details drawer: Slides out on row selection to display complete matched conditions JSON, explicit analyst limitations alert box, status update buttons (`Acknowledge`, `Resolve`, `Dismiss`, `Reopen`), and expandable list of supporting evidence events.
- Rules Catalogue modal: Displays all 5 rules with descriptions, MITRE ATT&CK badges, tunables, and toggle switches to enable/disable rules.

---

## 3. Strict Boundary Compliance

As specified in the Sprint 4 Master Plan:
- **No Case Management (Sprint 5):** Findings are relational entities but are NOT correlated into Cases or Case Timelines.
- **No Claim Guard (Sprint 6):** Findings do NOT produce typed agent claims or automated LLM summaries.
- **No Replay Lab (Sprint 7):** Replay Lab runner remains unmounted and planned for Sprint 7.
- **Zero Mocking / Fabricated Data:** All tests run against genuine SQLite tables with foreign keys enabled (`PRAGMA foreign_keys = ON;`).

---

## 4. Defect Log & Resolutions

| Issue ID | Component | Symptom | Root Cause | Resolution |
| :--- | :--- | :--- | :--- | :--- |
| **DEF-001** | `test_normalization_db.py` | `AssertionError: 4 != 3` | Adding Migration 004 increased applied migrations to 4, failing hardcoded assertion `len(versions) == 3`. | Updated test to assert `len(versions) >= 3` and verified migrations 1, 2, 3, and 4 are tracked. |
| **DEF-002** | `rules.py` (`AUTH-002`) | `AssertionError: 0 != 1` | In `AUTH-002`, `k = j` started scanning for success events past `j`, which skipped success events that occurred within `fail_window_sec` after the 5th failure. | Tracked the exact index of the last failure in the failure burst `last_fail_idx` and set `k = last_fail_idx + 1`. |
| **DEF-003** | `models.py` | `ImportError: cannot import name 'compute_rule_config_hash'` | Config hash was inlined in `RuleDefinition.__post_init__` rather than exported as a helper function. | Extracted `compute_rule_config_hash(config)` as a top-level function in `models.py` and aliased in `rules.py`. |
| **DEF-004** | `test_findings_api.py` | `KeyError: 'evaluation_id'` | `POST /api/detection/run` wraps result inside `{"status": "success", "result": {...}}`. Test checked top level. | Updated test to assert `run_data["result"]["evaluation_id"]`. |
| **DEF-005** | `verify_real_normalization_workflow.py` | `AssertionError: Expected at least 1 rejected, got 0` | Script ran against shared dev DB where identical file hash had already been processed in a previous session. | Updated script to use an isolated temporary database via `SENTINEL_DB_PATH` and unique record timestamps. |

---

## 5. Quality Verification Summary

| Gate | Target | Result | Status |
| :--- | :--- | :--- | :---: |
| Backend Automated Tests | 100% pass | 107/107 pass (0 fail, 0 error, 0 skip) | **PASS** |
| Kiro Crew Manifest Validation | Valid app.json | Schema valid, all entry points and skills exist | **PASS** |
| Frontend Typecheck | TypeScript compiler | 0 errors (`npm run typecheck`) | **PASS** |
| Frontend Production Bundles | Vite + Kiro Crew ESM | `dist/index.html` + `dist/index.mjs` built | **PASS** |
| Headless Browser DOM Verification | All 8 navigation routes | Verified in Chrome DOM with live engine triggers | **PASS** |
| Real Import & SQLite Workflow | 13-step sequence | 100% pass | **PASS** |
| Real Normalization & Provenance | 6-step sequence | 100% pass | **PASS** |
| Real Detection & Findings Workflow | 8-step sequence | 100% pass | **PASS** |
| Kiro Hook (`validate-all.ps1`) | Full quality hook | Exit code 0 | **PASS** |

---

## 6. Readiness for Phase 5

Sprint 4 is complete and verified. The platform now possesses:
1. Validated canonical events with strict timezone normalization and provenance.
2. Deterministic detection rules evaluating sliding-window temporal criteria.
3. Deduplicated, evidence-backed findings linked via foreign keys to canonical events.
4. Complete REST API endpoints and a functional, responsive Findings UI view.

**Project Sentinel is 100% READY for Sprint 5 (Correlation, Cases & Incident Investigation).**  
**Execution has halted per protocol. Awaiting user authorization to proceed to Sprint 5.**

