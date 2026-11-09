# Project Sentinel — Phase 5 Implementation Report
**Sprint 5: Investigation Cases, Deterministic Correlation & Timeline**  
**Execution Timestamp:** 2026-11-09T21:40:00Z  
**Implementation Lead:** Principal Software Architect, Detection Engineer & QA Lead  
**Overall Status:** **COMPLETED & VERIFIED (PASS)**

---

## 1. Architectural Objectives & Executive Summary

Sprint 5 delivers the core **Investigation Cases**, **Deterministic Correlation Engine**, and **Evidence Timeline** capabilities for Project Sentinel.

Sentinel's data pipeline now forms an unbroken, verifiable security architecture:
1. **Phase 1 & 1.5**: Secure foundation shell, offline resilience, and frontend navigation.
2. **Phase 2 & 2.5**: Multi-source log ingestion, parser profiles, SHA-256 deduplication, and SQLite persistence.
3. **Phase 3 & 3.5**: Canonical event normalization, timezone enforcement, provenance tracking, and quarantine.
4. **Phase 4 & 4.5**: Deterministic detection rules, sliding-window evaluators, and explainable findings.
5. **Phase 5**: Deterministic correlation clustering, collision-resistant case IDs, derived severity, chronological timelines, append-only operator review notes, and state-machine-validated case lifecycle.

### Core Deliverables Completed:
1. **Case & Correlation Models (`backend/cases/models.py`)**: Dataclasses for `Case`, `CaseFinding`, `CaseEvent`, `ReviewAction`, `TimelineItem`, and `CorrelationRelationship`. Includes severity derivation and strict state machine validation.
2. **Deterministic Correlation Engine (`backend/cases/engine.py`)**: Pure deterministic clustering grouping findings and supporting events by approved identity keys within configurable time windows (default 3600 seconds). IP-only grouping disabled by default.
3. **Database Migration 005 (`backend/persistence/migrations.py`)**: Created tables `cases`, `case_findings`, `case_events`, `review_actions`, `correlation_evaluations`, and query indexes.
4. **Repository Implementation (`backend/persistence/repository.py`)**: Added `persist_cases_batch`, `get_case`, `list_cases`, `update_case_status`, `add_case_note`, `get_case_stats`, and `record_correlation_evaluation`.
5. **API Handlers (`backend/api/handler.py`)**: Exposed REST endpoints for `/api/cases`, `/api/cases/stats`, `/api/cases/{id}`, `/api/cases/correlate`, and `/api/cases/{id}/review`.
6. **Shared Contract & Frontend Types (`shared/contracts/case_contract.json`, `apps/crew-app/src/types.ts`)**: Type-safe contracts shared between backend and React UI.
7. **Analyst Workspace UI (`apps/crew-app/src/components/Views/CasesView.tsx`)**: Full dark graphite interface featuring metrics bar, engine execution triggers, search/filter controls, cases table, and deep-dive drawer with unified evidence timeline and review action logging.
8. **Automated Test Suite**: 17 new unit and integration tests added, bringing total platform test count to **128 passing tests** (0 failures, 0 errors, 0 skipped).
9. **End-to-End Workflow Verification Script (`scripts/verify_real_case_workflow.py`)**: Real workflow script testing multi-stage log import, canonical normalization, detection, correlation, analyst triage review, database foreign keys, and idempotency.

---

## 2. Detailed Technical Implementation

### 2.1 Correlation Core Architecture (`backend/cases/`)

- **`CorrelationEngine`**:
  - Extracts approved correlation keys (`user_principal`, `session_id`, `request_id`).
  - Strict guardrail: `enable_ip_correlation=False` by default. Source IP is never treated as human or host identity unless explicitly enabled.
  - Groups findings by `(key_type, safe_key_value, window_bucket)` where `window_bucket = int(epoch // window_seconds)`.
  - Derives case severity as the maximum severity of linked findings.
  - Generates clear, human-readable correlation rationale explaining why records were grouped.
- **Deterministic Case ID Derivation**:
  $$\text{case\_id} = \text{"case\_"} + \text{SHA256}(\text{key\_type} : \text{key\_value} : \text{window\_bucket})[0:20]$$
- **State Machine Transitions**:
  Enforces `ALLOWED_TRANSITIONS` across `Open`, `UnderReview`, `NeedsMoreEvidence`, `Resolved`, and `Dismissed`. Illegal transitions raise immediate `ValueError`.

### 2.2 Database Schema (Migration 005)

- **`cases` Table**: Stores case entities with unique constraint `uq_case_dedupe (correlation_key_type, correlation_key_value, dedupe_key)`.
- **`case_findings` Table**: Relational junction table linking cases to findings with foreign keys.
- **`case_events` Table**: Relational junction table linking cases to canonical events with full provenance.
- **`review_actions` Table**: Append-only audit log capturing every analyst note, status transition, previous status, new status, author, and timestamp.
- **`correlation_evaluations` Table**: Execution audit metrics recording scanned counts, cases created/updated, and execution latency.

### 2.3 Idempotency & Analyst State Preservation

When the correlation engine is triggered repeatedly:
1. `persist_cases_batch()` checks for existing cases by `(correlation_key_type, correlation_key_value, dedupe_key)`.
2. Existing cases update `last_observed_at`, metadata, and severity (if newly correlated findings have higher severity).
3. The analyst's `status` (e.g. `UnderReview` or `Resolved`) is **strictly preserved** and never reset to `Open`.
4. Existing review actions and operator notes are completely untouched.

### 2.4 Evidence Timeline Assembly

`get_case(case_id)` dynamically aggregates:
1. **Canonical Events**: Linked supporting events ordered by UTC timestamp.
2. **Triggered Findings**: Rule-matched security findings.
3. **Correlation Rationale**: Explanation of the identity key and time window.
4. **Operator Review Actions**: Historical record of triage decisions and notes.
All items are sorted chronologically by UTC timestamp to provide analysts with a comprehensive, transparent evidence reconstruction.

---

## 3. Real Workflow Verification (`scripts/verify_real_case_workflow.py`)

A standalone automated test was created and integrated into `.kiro/hooks/validate-all.ps1`:
1. Launches Sentinel backend with an isolated temporary SQLite database.
2. Ingests authentication burst logs (5 failures + 1 success) for user `analyst_bob`.
3. Ingests privilege escalation event for user `analyst_bob`.
4. Ingests unrelated web reconnaissance logs from IP `203.0.113.77` with no user.
5. Runs canonical normalization $\rightarrow$ 10 canonical events accepted.
6. Runs detection engine $\rightarrow$ 4 findings generated (`AUTH-001`, `AUTH-002`, `PRIV-001`, `WEB-001`).
7. Runs correlation engine $\rightarrow$ 2 cases created.
8. Verifies case for user `analyst_bob`:
   - Correlated findings: 3 (`AUTH-001`, `AUTH-002`, `PRIV-001`).
   - Derived severity: `High`.
   - IP-only grouping guardrail verified: 0 `source_ip` cases created.
9. Performs analyst triage:
   - Transition `Open` $\rightarrow$ `UnderReview` with note.
   - Appends standalone analyst note.
   - Transition `UnderReview` $\rightarrow$ `Resolved`.
10. Directly queries SQLite:
    - Verifies `cases`, `case_findings`, `case_events`, `review_actions` tables.
    - Runs `PRAGMA foreign_key_check;` $\rightarrow$ 0 violations!
11. Verifies idempotency:
    - Re-evaluates correlation $\rightarrow$ 0 new cases created, 2 cases updated.
    - Verified case status remains `Resolved` and all 3 review actions are preserved.
12. Clean teardown and process exit.

---

## 4. Phase 5.5 Independent Audit & Hardening Addendum

Phase 5 was independently audited during Phase 5.5 (`docs/PHASE_5_5_INDEPENDENT_AUDIT.md`).
- **Defects Identified & Remediated:** 5 defects (`DEF-CASE-001` to `DEF-CASE-005`, detailed in `docs/PHASE_5_5_DEFECT_LOG.md`).
- **New Audit Regression Tests:** 9 tests added in `tests/unit/test_cases_audit.py`.
- **Updated Platform Test Count:** **137 / 137 tests passing (100%)** across 25 test files.
- **Independent Audit Verdict:** **PASS**. Phase 5 is fully verified and hardened.


