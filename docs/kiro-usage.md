# Kiro Usage Evidence Log
**Project:** Project Sentinel  
**Hackathon:** Kiroween 2026  
**Auditor:** Technical Lead  

Judges evaluate technological implementation based on genuine, thoughtful use of Kiro features (specs, steering, hooks, agents, skills, and App Kit conventions) rather than generic claims. This log documents real artifacts, decisions, and validations across Phase 1, Phase 1.5, and Phase 2.

---

## 1. Feature Usage Summary

| Date | Kiro Feature | Task / Purpose | What Was Implemented | Validation / Review |
|---|---|---|---|---|
| 2026-11-09 | **Environment Audit** | Phase 1 Pre-flight | Inspected host Kiro IDE (v1.4.86), App Kit docs, Node 24 LTS, Python 3.14. | Documented in `docs/PHASE_1_ENVIRONMENT_AUDIT.md`. |
| 2026-11-09 | **Steering Files** | System Directives | Authored 5 steering directives: `product.md`, `architecture.md`, `security.md`, `testing.md`, and `design.md`. | Enforced design constraints (no emojis, zero fake metrics) and security rules. |
| 2026-11-09 | **Specs** | Spec-Driven Dev | Authored specifications: `01-product-and-judge-experience.md`, `02-crew-app-shell.md`, and `PHASE_2_DATABASE_DESIGN.md`. | Verified requirements against acceptance criteria. |
| 2026-11-09 | **Crew Manifest** | App Kit Packaging | Authored `apps/crew-app/app.json` following official App Kit schema. | Validated via `scripts/validate_manifest.py` (0 errors). |
| 2026-11-09 | **Crew Agent** | AI Specialization | Defined `agents/sentinel-investigator.json` constrained to typed claim proposals. | Verified least privilege; disabled autonomous shell and remediation. |
| 2026-11-09 | **Crew Skill** | Domain Knowledge | Authored `skills/evidence-led-investigation/SKILL.md` defining evidence citations and forbidden claims. | Checked alignment with Claim Guard contract. |
| 2026-11-09 | **Hooks** | Quality Gate | Created and expanded `.kiro/hooks/validate-all.ps1` automating backend tests, manifest checks, frontend typecheck, builds, and browser runtime verification. | Executed and passed 100% cleanly across 36 tests and 12 browser steps. |
| 2026-11-09 | **App Kit Views** | Phase 2 UI | Implemented `SourcesView.tsx` with live ingestion controls, parser profiles, and SQLite-backed import history table. | Verified in headless Chrome with zero artificial metrics. |
| 2026-11-09 | **Specs & Engine** | Phase 3 Normalization | Authored `PHASE_3_NORMALIZATION_DESIGN.md` and deterministic canonical normalization engine with strict UTC timestamps. | Verified via `test_e2e_normalization.py` and `verify_real_normalization_workflow.py`. |
| 2026-11-09 | **Specs & Engine** | Phase 4 Detection | Authored `PHASE_4_DETECTION_DESIGN.md` and deterministic detection engine with 5 built-in rules, condition matching, and relational junction evidence. | Verified via `test_e2e_detection.py` and `verify_real_detection_workflow.py`. |
| 2026-11-09 | **Specs & Engine** | Phase 5 Cases & Correlation | Authored `PHASE_5_CASE_DESIGN.md`, deterministic correlation engine, derived severity calculation, append-only review actions, and unified evidence timeline in `CasesView.tsx`. | Verified via `test_e2e_cases.py`, `verify_real_case_workflow.py`, and `validate-all.ps1`. |
| 2026-11-09 | **Specs, Agent & Claim Guard** | Phase 6 Claim Guard | Authored `PHASE_6_CLAIM_GUARD_DESIGN.md`, `shared/contracts/claim_contract.json`, `backend/claims/`, updated `skills/evidence-led-investigation/SKILL.md`, and built the Claim Guard tab with signature demo moment in `CasesView.tsx`. | Verified via `test_e2e_claims.py`, `test_claim_security.py`, `verify_real_claim_guard_workflow.py`, and Gate 9 in `validate-all.ps1`. |

---

## 2. Authentic Engineering Insights & Trade-offs

### A. Dual Build Strategy for Kiro Crew App Kit
- **Challenge:** The Kiro Crew App Kit requires `ui.entry` to point to an ESM library bundle (`dist/index.mjs`) with host dependencies externalized (`@kirocrew/app-sdk`, `react`, `react-dom`). However, the standalone judge demo and local preview require a browser-executable single-page application (`dist/index.html`).
- **Solution:** Configured dual Vite targets: `vite.config.ts` builds the standalone web application with bundled React, while `vite.config.crew.ts` compiles the canonical library bundle `dist/index.mjs` for Kiro Crew. Both are generated during `npm run build`.

### B. Prevention of Artificial Metrics & Preserving Analyst Work
- **Decision:** Many hackathon submissions render impressive-looking charts with fictional threat percentages or hardcoded mock alerts. In accordance with Steering Directive `design.md` and Rule D (*No AI slop*), Sentinel's Overview, Sources, Findings, and Cases dashboards strictly avoid fake metrics. All import history, accepted/rejected record counts, detection findings, and investigation cases are queried live from SQLite.
- **Analyst State Preservation:** When the correlation engine is re-executed over expanded log archives, Sentinel automatically preserves any existing human analyst status (`UnderReview`, `Resolved`, `Dismissed`) and leaves all append-only operator review notes intact.

### C. The IP-Only Grouping Guardrail
- **Challenge:** Naive clustering tools frequently group all traffic originating from a shared IP address into a single mega-incident. In enterprise and cloud environments, IP addresses are often shared across thousands of users behind NAT gateways or corporate proxies.
- **Solution:** Sentinel strictly enforces `enable_ip_correlation = False` by default. Correlation requires explicit identity keys (`user_principal`, `session_id`, `request_id`). Source IP is preserved solely as contextual network evidence.

### D. Standard Library Architecture & Python 3.14 Compatibility
- **Challenge:** Python 3.14 completely removed the legacy `cgi` module (`cgi.FieldStorage`), which many tutorial upload scripts rely on.
- **Solution:** Built a zero-external-dependency multipart parser in `backend/api/upload.py` leveraging Python's modern standard library `email.parser` with `policy=default`, fully supporting both `multipart/form-data` and `application/json` payloads without adding heavy third-party framework dependencies.

### E. Non-Destructive Ingestion & SHA-256 Idempotency
- **Decision:** Traditional file watchers often delete or rename source logs after processing. Sentinel adheres strictly to security non-destructiveness: original files in the watched directory are **never altered or deleted**. Repeated scans identify already-processed files via `(sha256, parser_id, parser_version)` composite unique constraints in SQLite and safely skip them without duplicate database records.

### F. Zero-Trust Claim Guard: Preventing AI Hallucination in SecOps
- **Challenge:** LLM-powered security tools often generate misleading incident summaries, hallucinate non-existent event counts, attribute attacks to arbitrary users based on IP addresses, or invent connections between unrelated cases.
- **Solution:** Project Sentinel implements the core architectural axiom: *"AI proposes. Deterministic code verifies. The operator decides."*
  - The Kiro Crew agent (`agents/sentinel-investigator.json`) and investigation skill (`skills/evidence-led-investigation/SKILL.md`) are constrained to submit typed JSON proposals (`ClaimProposal`) across a finite set of 8 claim types and approved templates.
  - The deterministic `ClaimVerifier` performs 9 automated verification checks against actual SQLite evidence tables, mathematically verifying counts, cross-case containment, and injection resistance without LLM involvement.
  - Verified claims are rendered safely using approved parameter templates with `html.escape()`.
  - Blocked claims are quarantined in the dedicated Claim Guard audit panel with clear rejection reasons and actionable remediation advice.

