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

## Phase 3 Capabilities (Sprint 3 Complete)

Project Sentinel v0.3.0 establishes the canonical normalization engine and immutable evidence provenance:
1. **Canonical Normalization Engine:** Transforms pre-normalized ingestion records (`parsed_records`) into canonical events conforming to `shared/contracts/event_contract.json`.
2. **Three Parser Mappers:**
   - `GenericJsonlMapper`: Resolves candidate timestamp, user principal, source IP, target resource, and outcome keys.
   - `AuthCsvMapper`: Normalizes authentication credentials and outcomes (`SUCCESS`, `FAILURE`, `LOCKED`, `CHALLENGE`).
   - `WebAccessCsvMapper`: Normalizes HTTP requests, mapping HTTP status codes (100–399 $\rightarrow$ `SUCCESS`, 400–499 $\rightarrow$ `FAILURE`, 500–599 $\rightarrow$ `ERROR`).
3. **Deterministic Event Identity:** Formula `evt_` + SHA-256(`source_sha256:record_number:parser_id:norm_version`)[0:24] providing reproducible, collision-resistant event IDs across re-runs.
4. **Strict Timestamp Normalization:** Mandatory UTC conversion, ISO-8601 UTC output, epoch handling, explicit naive timestamp metadata annotation (`"timezone_inferred": "UTC_ASSUMED"`), and rejection of invalid timestamps without silent `datetime.now()` fallback.
5. **Database Migration 002:** Added `normalized_events` table with unique constraint on `(record_id, normalization_version)`, indexes on timestamp/type/user/IP, and `normalization_errors` table for structured diagnostic capture of unmappable lines.
6. **Canonical Events Stream UI:** Interactive `EventsView` in `apps/crew-app` featuring aggregate normalization metrics, filter toolbar, interactive events stream table, and comprehensive Event Inspector drawer detailing immutable SHA-256 provenance and formatted attributes JSON.
7. **Comprehensive Test Suite:** 68 passing tests across unit, integration, contract, and headless browser runtime verification.

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
Run all 68 backend tests:
```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Run end-to-end quality gate hook (tests + manifest + build + headless browser):
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

