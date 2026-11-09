# Project Sentinel — Phase 7 Implementation Report
## Replay Lab: Deterministic Incident Replay & What-If Simulation

**Sprint:** Phase 7  
**Status:** PASS  
**Date:** November 10, 2026  
**Author:** Principal Detection, Data & Security Architect  

---

## 1. Primary Objectives Achieved

Phase 7 of Project Sentinel establishes the **Replay Lab**, a proof-carrying runtime environment that executes the real production security pipeline—from ingestion to normalization, deterministic detection, correlation, timeline synthesis, and Claim Guard verification—against synthetic incident scenarios.

### Core Requirements Met:
1. **Real Pipeline Execution (Zero Mocks):** Every replay processes authentic fixture files through real engine classes (`ImportEngine`, `NormalizationEngine`, `DetectionEngine`, `CorrelationEngine`, `ClaimGuardEngine`). No hardcoded findings or synthetic shortcuts exist.
2. **Complete SQLite Data Isolation:** Every replay executes inside an isolated in-memory SQLite database (`:memory:`) with complete schema migrations (001 through 007 applied). Core host security tables (`sources`, `raw_records`, `normalized_events`, `findings`, `cases`, `case_claims`) are 100% untouched.
3. **Approved Incident Scenarios:**
   - **`SCN-AUTH-BURST` (Authentication Burst):** 5 failures and 1 success for `operator_dave`. Detects `AUTH-001`, `AUTH-002`, correlates High-severity case, and Claim Guard blocks unproven attacker attribution.
   - **`SCN-WEB-PROBE` (Sensitive Endpoint Probing):** Route probing across `/admin`, `/api/v1/auth`, `/config` receiving HTTP 403 Forbidden. Detects `WEB-001` and enforces Sentinel's IP Guardrail.
   - **`SCN-PRIV-ESC` (Privilege Escalation):** Role grant audit event (`role_changed`). Detects `PRIV-001`, traces SHA-256 provenance hashes, and blocks exaggerated record counts.
4. **Proof-Carrying Assertions:** Evaluates 100% of committed expectations against runtime outputs (expected vs actual comparison table).
5. **What-If Simulation & Semantic Diffs:** Evaluates counterfactuals (e.g. higher failure thresholds, excluded lines) and computes exact structural diffs (`findings_added`, `findings_removed`, `metric_deltas`).
6. **Frontend Workbench (`ReplayView.tsx`):** Interactive React workbench featuring scenario cards, 7-stage execution stepper, proof assertions table, chronological case timeline, Claim Guard audit cards, and side-by-side run comparison.

---

## 2. Components Implemented

### 2.1 Database Migration 007 (`backend/persistence/migrations.py`)
- Created `replay_runs` and `replay_expectations` tables.
- Applied indexes `idx_replay_runs_scenario` and `idx_replay_runs_status`.
- Integrated safely into `MIGRATIONS` sequence.

### 2.2 Replay Persistence Repository (`backend/persistence/repository.py`)
- `persist_replay_run(run_data)`: Stores full JSON snapshots of execution metrics, stages, assertions, and cases.
- `get_replay_run(replay_id)`: Fetches individual replay run reports.
- `list_replay_runs(scenario_id, limit, offset)`: Paginated run history.
- `reset_replay_runs(scenario_id)`: Safely purges replay history without touching security data.

### 2.3 Replay Engine & Scenarios (`backend/replay/`)
- `backend/replay/models.py`: Data models for `ScenarioFixture`, `ScenarioExpectations`, `ScenarioManifest`, `ReplayAssertion`, `ReplayStage`, `ReplayMetrics`, `WhatIfConfig`, and `ReplayRunReport`.
- `backend/replay/scenarios.py`: Canonical manifests for `SCN-AUTH-BURST`, `SCN-WEB-PROBE`, and `SCN-PRIV-ESC`.
- `backend/replay/engine.py`: `ReplayEngine` coordinating real engines on isolated `:memory:` connections, evaluating assertions, comparing runs, and computing what-if semantic diffs.

### 2.4 Synthetic Scenario Fixtures (`fixtures/scenarios/`)
- `fixtures/scenarios/scenario_a_auth_burst.csv` (SHA-256: `45e53eda48ed3e2b683f3ce99bc25732de7e733e0b3a0f0fc323464283c13618`, 383 B)
- `fixtures/scenarios/scenario_b_web_probe.csv` (SHA-256: `c76e17ccf0b6e21a779a55d4414982f799a2b8b15603c568bc48c743b74be463`, 448 B)
- `fixtures/scenarios/scenario_c_priv_esc.jsonl` (SHA-256: `f4ffffdb030c764bf938464bba8748ad62fbf8e825ce59f7fb2972ab98163066`, 580 B)

### 2.5 REST API Endpoints (`backend/api/handler.py`)
- `GET /api/replay/scenarios`: Returns catalog of all approved scenarios.
- `GET /api/replay/scenarios/{id}`: Returns scenario manifest details.
- `POST /api/replay/run`: Executes scenario or What-If simulation.
- `GET /api/replay/runs`: Lists historical replay audit runs.
- `GET /api/replay/runs/{id}`: Returns single execution report.
- `POST /api/replay/compare`: Compares two runs side-by-side.
- `POST /api/replay/reset`: Resets replay run history.

### 2.6 Frontend Replay Lab Workbench (`apps/crew-app/`)
- `apps/crew-app/src/components/Views/ReplayView.tsx`: Full interactive workbench matching Sentinel design tokens.
- `apps/crew-app/src/types.ts`: Replay TypeScript interfaces.
- `apps/crew-app/src/App.tsx`: Route binding for live Replay Lab.
- `apps/crew-app/src/components/Navigation.tsx`: Activated Replay Lab navigation.

---

## 3. Test Evidence & Quality Gates

- **Total Backend Tests:** 215 tests (215 passed, 0 failed, 0 errors).
- **Phase 7 Tests Added:** 31 tests.
  - `tests/unit/test_replay_models.py` (4 tests)
  - `tests/unit/test_replay_scenarios.py` (6 tests)
  - `tests/unit/test_replay_engine.py` (7 tests)
  - `tests/integration/test_replay_api.py` (9 tests)
  - `tests/integration/test_e2e_replay.py` (5 tests)
- **Quality Gates:** 10/10 PASS in `.kiro/hooks/validate-all.ps1`.

