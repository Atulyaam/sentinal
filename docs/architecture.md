# Project Sentinel Architecture Specification

**Version:** 0.1.0 (Phase 1 Foundation)  
**Author:** Lead Software Architect & Security Reviewer  
**Status:** Approved Baseline  

---

## 1. System Vision

Project Sentinel is a local-first defensive cybersecurity workbench. It bridges the gap between raw log streams and high-stakes human security decisions through **Proof-Carrying Investigation**.

Instead of relying on black-box enterprise SIEMs or unconstrained AI chatbots that hallucinate conclusions, Sentinel implements an end-to-end provenance pipeline:
1. **Source Provenance:** Every normalized event records the source file path, line number, and SHA-256 hash.
2. **Deterministic Rules:** Rule detections explicitly cite rule IDs, versions, parameter thresholds, and matched event IDs.
3. **Correlation Rationale:** Cases explain the grouping mechanism (e.g. matching IP, shared principal, or time window).
4. **Claim Guard:** A deterministic verifier that validates typed AI claim proposals against mathematical case evidence before any statement is rendered as a fact.

---

## 2. Phase 1 Repository Architecture

The repository enforces modularity and strict boundary separation:

```text
project-sentinel/
├── .kiro/                       # Kiro Development Configuration
│   ├── specs/                   # Subsystem specifications (01, 02)
│   ├── steering/                # Architecture, design, security, product, and testing directives
│   └── hooks/                   # Quality gate scripts
├── apps/
│   ├── crew-app/                # Canonical Kiro Crew app package
│   │   ├── app.json             # Official Kiro Crew manifest
│   │   ├── agents/              # Custom investigator agent definition
│   │   ├── skills/              # Custom evidence-led investigation skill
│   │   ├── assets/              # SVG icon assets
│   │   ├── src/                 # React UI application shell
│   │   └── dist/                # Production build (ESM library & standalone web app)
│   └── judge-demo/              # Hosted synthetic judge preview surface
├── backend/                     # Python Investigation Engine
│   ├── api/                     # HTTP server and request handlers (GET /health)
│   └── config/                  # Immutable settings and environment bounds
├── docs/                        # Architecture, audit reports, runbooks, and Kiro usage logs
├── shared/                      # Shared JSON schemas and synthetic fixtures
│   ├── contracts/               # Health, event, and claim contracts
│   └── fixtures/                # Synthetic test datasets
├── tests/                       # Automated test suites
│   ├── unit/                    # Config and health endpoint tests
│   └── contract/                # Schema parity tests between backend and frontend
├── scripts/                     # Operational scripts (validate_manifest, run_demo)
├── .env.example                 # Configuration template
├── .gitignore                   # Exclusion rules for credentials, caches, databases
├── LICENSE                      # Apache-2.0 open-source license
├── README.md                    # Quickstart and overview
└── CHANGELOG.md                 # Semantic versioning changelog
```

---

## 3. Component Details & Boundaries

### 3.1 Kiro Crew App Package (`apps/crew-app`)
- **Manifest:** Strictly conforms to Kiro Crew App Kit reference:
  - Registers entry `dist/index.mjs`.
  - Declares page `/apps/project-sentinel`.
  - Declares agent `agents/sentinel-investigator.json` and skill `skills/evidence-led-investigation`.
  - Declares least-privilege API permissions (`/health`, `/api/health`, `/api/status`, etc.).
- **Build System:** Vite library build externalizes host-provided dependencies (`react`, `react-dom`, `@kirocrew/app-sdk`, `lucide-react`) to output standard ESM for the Crew host, while providing a standalone browser preview for testing and the public judge demo.

### 3.2 Frontend Application Shell
- **Aesthetic:** High-density, restrained security interface using deep graphite (`#0B0D11`, `#11141B`), fine borders (`#21262D`), and controlled cobalt accent (`#388BFD`).
- **Iconography:** Purpose-built SVG line icons. Strict prohibition of emojis in interface controls.
- **Route Navigation:** Supports 8 routes: Overview, Investigations, Findings, Events, Replay Lab, Sources, Digests, Settings.
- **State Handling:** Implements Loading, Empty, Error, Backend Unavailable, and Connected states.
- **Zero AI Slop:** No fake metrics, fabricated threat counts, or placeholder graphs.

### 3.3 Backend Service (`backend/`)
- **Runtime:** Python 3.14 standard library (`http.server.ThreadingHTTPServer`, `sqlite3`, `urllib`).
- **Endpoints:** Full REST API spanning health, log import, canonical events, detection rules, findings, investigation cases, and Claim Guard verification.
- **Security Boundaries:** No arbitrary filesystem access, no remote code execution, no secret leakage, parameter sanitization via `html.escape()`.

### 3.4 Core Data Pipeline & Parsers (Phase 2)
- **Multi-Source Parsers:** Dedicated parsers for `auth_csv`, `generic_jsonl`, and `web_access_csv`.
- **Secret Sanitizer:** Automatic redaction of credentials, bearer tokens, API keys, and authorization headers during ingestion.
- **SQLite Database:** WAL mode, 5000ms busy timeout, foreign key enforcement (`PRAGMA foreign_keys = ON`), versioned migrations 001–006.

### 3.5 Canonical Event Normalization & Provenance (Phase 3)
- **Canonical Schema:** Normalizes timestamps to strict UTC ISO-8601, extracts `user_principal`, `source_ip`, `target_resource`, and canonical status.
- **Provenance Linkage:** Preserves immutable `source_sha256`, `source_file`, `source_line`, parser version, and normalization version.
- **Deterministic Identity:** `evt_` + SHA-256 over source coordinates.

### 3.6 Deterministic Detection Rules & Findings (Phase 4)
- **Sliding-Window Evaluator:** Evaluates 5 built-in security rules (`AUTH-001`, `AUTH-002`, `WEB-001`, `PRIV-001`, `INGEST-001`) chronologically without probabilistic guessing.
- **Relational Evidence:** `finding_events` junction table enforces `ON DELETE RESTRICT` foreign keys.
- **Deterministic Finding Identity:** `find_` + SHA-256 over rule ID, version, config hash, and dedupe key.

### 3.7 Investigation Cases & Correlation (Phase 5)
- **Deterministic Clustering:** Pure function grouping findings and supporting events by approved identity keys (`user_principal`, `session_id`, `request_id`) within time windows.
- **Anti-False-Clustering Guardrail:** IP-only identity grouping disabled by default (`enable_ip_correlation = False`).
- **Unified Timeline & State Machine:** Assembles events, findings, correlation rationale, and append-only operator review actions into a strict UTC chronological sequence with state machine validation (`Open`, `UnderReview`, `NeedsMoreEvidence`, `Resolved`, `Dismissed`).

### 3.8 Claim Guard & Safe Rendering (Phase 6)
- **Core Axiom:** *"AI proposes. Deterministic code verifies. The operator decides."*
- **Typed Claim Proposals:** LLMs propose structured JSON conforming to `shared/contracts/claim_contract.json` across 8 finite claim types.
- **9-Stage Verifier:** Python engine checks schema, templates, injection patterns, case containment, mathematical evidence matches, IP guardrails, and data quality.
- **Three Strict Outcomes:** `verified`, `qualified`, and `blocked`. Blocked claims are strictly quarantined in the audit panel with actionable remedies.
- **Safe Rendering:** Vetted parameter template substitution with mandatory `html.escape()` for untrusted log data.

