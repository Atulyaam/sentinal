# Project Sentinel
> **Kiroween 2026** — Proof-Carrying Defensive Security Investigation Workbench

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Kiro](https://img.shields.io/badge/Kiro-1.4.86-purple.svg)](https://kiro.dev)
[![Node](https://img.shields.io/badge/Node-24_LTS-green.svg)](https://nodejs.org)
[![Python](https://img.shields.io/badge/Python-3.14-blue.svg)](https://python.org)

Project Sentinel turns approved security logs into an evidence-linked investigation that a human can understand, replay, challenge and review. It detects explainable patterns, shows exactly which records support each finding, and refuses to present an AI-generated claim unless its structured evidence checks pass (**Claim Guard**).

---

## Architecture Overview

```text
project-sentinel/
├── .kiro/                       # Kiro specifications, steering, and quality hooks
│   ├── specs/                   # Subsystem specs (01-product, 02-shell, database design)
│   ├── steering/                # Architecture, design, security, product, and testing directives
│   └── hooks/                   # Pre-commit & CI validation scripts (validate-all.ps1)
├── apps/
│   ├── crew-app/                # Canonical Kiro Crew app package (app.json, UI bundle, Agent, Skill)
│   └── judge-demo/              # Hosted browser demo & standalone preview wrapper
├── backend/                     # Python investigation & verification engine
│   ├── api/                     # HTTP endpoints (health, sources, parsers, import)
│   ├── config/                  # Settings, origin whitelist, storage paths
│   ├── ingestion/               # Engine, approved inbox scanner, secret sanitizer
│   ├── parsers/                 # Strict parsers (generic_jsonl, auth_csv, web_access_csv)
│   └── persistence/             # SQLite connection, WAL pragmas, migrations, repository
├── docs/                        # Specifications, database design, threat model, runbooks
├── shared/                      # Contracts and synthetic test fixtures (JSONL, CSV)
├── tests/                       # Unit, integration, contract, and security test suites
└── scripts/                     # Runtime verification, manifest validation, helpers
```

---

## Phase 8 Capabilities (Sprint 8 Complete — Hosted Judge Demo & Production Deployment)

Project Sentinel v0.8.0 delivers the **Hosted Synthetic Judge Demo & Production Deployment** architecture, providing an immediate, zero-installation, publicly accessible demonstration of Sentinel's end-to-end security investigation pipeline for Kiroween 2026:
1. **Unified Single-Container Architecture:** Serves both the compiled React Single Page Application (SPA) and the Python HTTP API from a single lightweight container with client-side SPA routing fallback and security headers.
2. **Zero Third-Party Python Runtime Dependencies:** Built 100% on the Python 3.12+ standard library (`sqlite3`, `http.server`, `hashlib`, `json`, `dataclasses`, `pathlib`, `urllib`). Zero supply-chain attack surface, <45ms startup time, and <100MB container footprint.
3. **Public Demo Mode (`SENTINEL_DEMO_MODE=true`):** Restricts arbitrary file imports (`POST /api/import` returns `403 Forbidden`) while keeping Replay Lab synthetic scenarios 100% functional on isolated in-memory databases.
4. **Automated Baseline Demo Seeder:** Automatically populates `SCN-AUTH-BURST` on container startup so visiting judges land on an immediately active investigation dashboard.
5. **Rolling-Window Rate Limiter:** Protects heavy and simulation endpoints (`/api/replay/*`, `/api/cases/correlate`) against abuse with a 60-second rolling window per client IP.
6. **Health & Readiness Probes:** Dedicated `/health` and `/ready` probes for Kubernetes, Render, Railway, and Fly.io.
7. **Judge Onboarding UI:** Public Demo status badge in header and a 2-Minute Judge Walkthrough card in `OverviewView.tsx`.
8. **Multi-Stage Container & Blueprints:** Ready-to-deploy `Dockerfile`, `docker-compose.yml`, `render.yaml`, and `railway.toml`.
9. **Automated 17-Step Judge Verification:** `scripts/verify_hosted_demo.py` validates the entire end-to-end judge evaluation workflow against any target URL with 100% compliance.
10. **235 Automated Tests & 10 Quality Gates:** Complete passing test suite across unit, contract, integration, security, E2E, and headless browser runtime verification.

---

## Phase 7 Capabilities (Sprint 7 Complete — Replay Lab & What-If Simulation)

Project Sentinel v0.7.0 introduces the **Replay Lab**: a deterministic incident replay and what-if simulation environment executing the real live security pipeline with zero mocked outcomes (*"Every replay executes the real pipeline. No mocked results."*):
1. **Real Pipeline Execution (Zero Mocks):** Authentic execution through `ImportEngine` -> `NormalizationEngine` -> `DetectionEngine` -> `CorrelationEngine` -> `ClaimGuardEngine` on isolated in-memory SQLite databases (`:memory:`).
2. **Three Canonical Synthetic Scenarios:**
   - **`SCN-AUTH-BURST` (Authentication Burst):** 5 failures and 1 success for `operator_dave`. Detects `AUTH-001`, `AUTH-002`, groups into High-severity case, and Claim Guard blocks unproven attacker attribution.
   - **`SCN-WEB-PROBE` (Sensitive Endpoint Probing):** Probing across `/admin`, `/api/v1/auth`, `/config` receiving HTTP 403 Forbidden. Detects `WEB-001` and strictly enforces Sentinel's IP Guardrail (cannot infer identity from IP alone).
   - **`SCN-PRIV-ESC` (Privilege Escalation Investigation):** Administrative role change event (`role_changed`) for `analyst_bob`. Detects `PRIV-001`, verifies SHA-256 provenance hashes, and blocks exaggerated record counts.
3. **Committed Fixtures & SHA-256 Integrity:** Authentic fixture files stored in `fixtures/scenarios/` with cryptographically verified checksums.
4. **What-If Counterfactual Simulation & Semantic Diffs:** Evaluates parameter variations (elevated failure thresholds, line exclusions) and calculates exact mathematical differences (`findings_added`, `findings_removed`, `metric_deltas`).
5. **Deterministic Repeatability & Comparison Engine:** `compare_runs` verifies 100% identical outputs and 0 metric deltas between repeated runs.
6. **Strict Host Data Isolation:** Core security tables (`sources`, `raw_records`, `normalized_events`, `findings`, `cases`, `case_claims`) in the primary database remain 100% untouched.
7. **Interactive Replay Workbench UI:** Live `ReplayView` in `apps/crew-app` featuring scenario cards, 7-stage execution stepper, proof assertions table, chronological case timeline, Claim Guard audit cards, what-if diff cards, and side-by-side run comparison.
8. **215 Automated Tests & 10 Quality Gates:** Complete passing suite across unit, contract, integration, security, E2E, and headless browser runtime verification.

### Quickstart

#### 1. Start Backend Service
```powershell
python -m backend.api.server
```
Runs on `http://127.0.0.1:8000`. Endpoints:
- `GET /health`: Health status.
- `GET /api/parsers`: Registered parser profiles.
- `GET /api/sources`: Configured event sources.
- `GET /api/imports`: Historical import jobs audit log.
- `GET /api/imports/{id}`: Detailed job diagnostics with row-level error entries.
- `POST /api/import`: Manual file upload endpoint (multipart or JSON).
- `POST /api/normalization/run`: Execute normalization over pending ingestion records.
- `GET /api/events`: Query canonical normalized events with dynamic filters.
- `GET /api/events/{id}`: Inspect single canonical event with full source provenance.
- `GET /api/normalization/stats`: Pipeline normalization metrics.
- `GET /api/rules`: Registered detection rules catalogue.
- `GET /api/rules/{id}`: Single detection rule definition.
- `PATCH /api/rules/{id}`: Toggle rule enabled state.
- `POST /api/detection/run`: Execute detection engine evaluation.
- `GET /api/detection/stats`: Aggregate detection metrics.
- `GET /api/findings`: Query paginated findings with dynamic filters.
- `GET /api/findings/{id}`: Inspect single finding with joined supporting evidence events.
- `PATCH /api/findings/{id}`: Update finding lifecycle status.
- `GET /api/cases`: Query paginated investigation cases with dynamic filters.
- `GET /api/cases/stats`: Aggregate case metrics by status and severity.
- `GET /api/cases/{id}`: Inspect single case with assembled timeline, findings, and events.
- `POST /api/cases/correlate`: Execute correlation engine run.
- `POST /api/cases/{id}/review`: Append operator note or execute status transition.
- `PATCH /api/cases/{id}`: Direct status update validating state machine.
- `GET /api/claims/templates`: Catalogue of approved Claim Guard templates and claim types.
- `GET /api/cases/{id}/claims`: List verified, qualified, and blocked claims for a case.
- `GET /api/claims/{id}`: Inspect single claim detail and verification checks.
- `POST /api/claims/verify`: Verify and persist custom claim proposals.
- `POST /api/cases/{id}/claims/demo`: Execute signature Claim Guard demo bundle on a case.
- `POST /api/cases/{id}/claims/propose`: Propose and verify case-specific claims.
- `GET /api/replay/scenarios`: List approved Replay Lab scenario manifests.
- `GET /api/replay/scenarios/{id}`: Inspect single scenario manifest and expectations.
- `POST /api/replay/run`: Execute deterministic replay or What-If simulation.
- `GET /api/replay/runs`: Query historical replay run audit records.
- `GET /api/replay/runs/{id}`: Inspect single replay run report snapshot.
- `POST /api/replay/compare`: Compare two historical runs side-by-side.
- `POST /api/replay/reset`: Safely reset replay history without touching security data.

#### 2. Kiro Crew Application UI
```powershell
cd apps/crew-app
npm install
npm run build
```
Starts development server:
```powershell
npm run dev
```

#### 3. Run Production Server (Unified Single-Container Runner)
To run the unified server (serving both frontend and backend on port 8000 with demo mode):
```powershell
python scripts/run_production_server.py --port 8000
```

#### 4. Run Quality Gates & Tests
Run all 235 backend tests:
```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Run end-to-end quality gate hook (tests + manifest + build + headless browser + 6 real workflow verification scripts across all 10 gates):
```powershell
powershell -ExecutionPolicy Bypass -File .kiro/hooks/validate-all.ps1
```

Run 17-step hosted judge verification against any local or deployed URL:
```powershell
python scripts/verify_hosted_demo.py --url http://127.0.0.1:8000
```
Builds the canonical Kiro Crew package into `dist/index.mjs` matching the Kiro Crew App Kit manifest (`app.json`).

For standalone browser preview:
```powershell
npm run dev
```

---

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.

