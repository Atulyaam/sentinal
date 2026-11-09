# Kiro Specification: 01-product-and-judge-experience
**Status:** In Progress (Phase 1 Baseline)  
**Parent Plan:** `Project_Sentinel_Kiroween_2026_WINNING_MASTER_PLAN_v3.md`  
**Owner:** Product Architect & QA Lead  

---

## 1. Overview & Objective
Project Sentinel provides a defensible, evidence-linked cybersecurity investigation experience. This spec defines the complete product workflow, the judge evaluation journey, and the core proof points that distinguish Sentinel during competition evaluation.

The goal is to deliver an intuitive 2-minute 40-second demonstration that moves from raw synthetic logs to deterministic detection, case correlation, AI-assisted proposal, and deterministic **Claim Guard** verification where an unsupported claim is visibly blocked.

---

## 2. Target Personas & User Journeys

### Persona A: Independent Developer / Small Team Lead (Primary Operator)
- Needs to investigate suspicious access patterns without deploying complex enterprise infrastructure.
- Ingests structured logs from an approved inbox folder.
- Inspects findings with exact rule versions and supporting event IDs.
- Reviews AI summaries with full trust that claims are backed by verified evidence.

### Persona B: Kiroween Hackathon Judge (Evaluator)
- Evaluates Potential Impact (20%), Technological Implementation (20%), Design (20%), Innovation (20%), and Presentation (20%).
- Accesses a hosted, synthetic-data demo URL with zero setup and zero secrets required.
- Launches a pre-packaged scenario (e.g. Credential Storm or Privilege Jump).
- Witnesses Claim Guard block a hallucinated AI claim.
- Verifies that the Kiro Crew app is installable and adheres to official App Kit standards.

---

## 3. Key Requirements

### 3.1 Dual-Surface Experience
- **Surface 1: Kiro Crew Native App (`apps/crew-app`):** Installable into the Kiro Crew workspace, packaging custom agent `sentinel-investigator`, skill `evidence-led-investigation`, and an integrated dashboard view.
- **Surface 2: Hosted Judge Demo (`apps/judge-demo`):** Publicly accessible web application pre-loaded with synthetic test scenarios, read-only guarantees, and deterministic replay capabilities.

### 3.2 Proof-Carrying Investigation Requirements
1. **Provenance Chain:** Every event record must preserve source file path, line number, and cryptographic content hash.
2. **Deterministic Rules:** Findings must clearly display condition parameters (e.g., threshold > 5 failures in 5m window).
3. **Correlation Rationale:** Cases must explain why disparate events were grouped (e.g. shared source IP or matching user principal).
4. **Claim Guard:** Structured claims must be mathematically validated against case evidence; mismatched numbers or entities are marked `BLOCKED` with an explanation.

---

## 4. Design Decisions & Trade-offs
- **Synthetic Data Exclusively for Demos:** No live production logs or operator telemetry are permitted in the public repository or demo environment.
- **No Uncontrolled Chatbot:** The AI agent does not converse in free-form markdown; it returns typed JSON claims conforming to the Claim Guard schema.
- **Zero Fake Metrics:** The dashboard presents real status indicators and empty states rather than decorative, fabricated graphs.

---

## 5. Implementation Tasks

- [x] Establish product steering directives and boundaries.
- [x] Document judge demo script and 2:40 timing constraints.
- [x] Scaffold dual-target architecture (Crew app + standalone judge preview).
- [ ] Implement synthetic scenario fixtures (`shared/fixtures/credential_storm.jsonl`).
- [ ] Implement Claim Guard deterministic verification engine.
- [ ] Build judge demo scenario runner and reset controls.

