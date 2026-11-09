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

## Phase 6 Capabilities (Sprint 6 Complete)

Project Sentinel v0.6.0 introduces **Claim Guard**: a zero-trust verification boundary for AI-assisted security investigations (*"AI proposes. Deterministic code verifies. The operator decides."*):
1. **Typed Claim Schema & Vocabulary:** LLMs and automated workflows propose structured JSON claims adhering to a finite set of 8 claim types and approved predicates (`shared/contracts/claim_contract.json`).
2. **Deterministic 9-Stage Verifier:** Pure Python engine checks claims against SQLite evidence tables: schema validity, template vetting, injection scanning, case containment, mathematical value validation, IP-only identity guardrails, data quality checks, certainty alignment, and safe rendering. Zero LLM self-evaluation.
3. **Three Explicit Verification Outcomes:**
   - **`verified`:** Evidence exists in the case and matches claimed values and predicates exactly.
   - **`qualified`:** Supported by evidence, but carries explicit caveats (e.g. certainty is `inferred` or `hypothesis`, or data quality warnings exist).
   - **`blocked`:** Evidence is missing, refers to foreign cases (cross-case tampering), contains conflicting values, attempts prompt/script injection, or infers user identity from IP alone. Strictly quarantined in the audit panel and never rendered in the factual narrative.
4. **Approved Template Catalog with Mandatory HTML Escaping:** Verified and qualified claims render exclusively through vetted parameter substitution templates (`backend/claims/templates.py`) with `html.escape()` applied to all dynamic values.
5. **Anti-Hallucination & Containment Guardrails:** Categorically blocks claims asserting human identity from IP alone, or referencing evidence outside the target case.
6. **Signature Demo Moment:** Interactive trigger in the UI (`POST /api/cases/{id}/claims/demo`) generating verified, qualified, and adversarial blocked claims with clear remediation advice.
7. **SQLite Persistence:** Migration 006 adds `claim_proposals` and `claim_verifications` with cascading foreign keys to `cases(case_id)`.
8. **Analyst Workspace UI:** Dedicated Claim Guard tab in `CasesView` with real-time metrics, color-coded verified/qualified/blocked panels, clickable evidence chips, and demo trigger.
9. **169 Automated Tests:** Complete passing suite across unit, contract, integration, security, and headless browser runtime verification.

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

#### 3. Run Quality Gates & Tests
Run all 169 backend tests:
```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Run end-to-end quality gate hook (tests + manifest + build + headless browser + 5 real workflow verification scripts across all 9 gates):
```powershell
powershell -ExecutionPolicy Bypass -File .kiro/hooks/validate-all.ps1
```
Builds the canonical Kiro Crew package into `dist/index.mjs` matching the Kiro Crew App Kit manifest (`app.json`).

For standalone browser preview:
```powershell
npm run dev
```

---

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.

