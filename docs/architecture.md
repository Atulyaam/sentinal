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
- **Runtime:** Python 3.14 standard library (`http.server.ThreadingHTTPServer`, `urllib`).
- **Endpoints:**
  - `GET /health` and `GET /api/health`: Returns application name, status, version, and ISO-8601 timestamp.
  - `OPTIONS /health`: CORS preflight response (204).
  - Unknown routes: Structured 404 JSON response.
- **Security Boundaries:** No arbitrary filesystem access, no remote code execution, no secret leakage.
