# Steering Directive — System Architecture & Component Boundaries
**Project Sentinel — Kiroween 2026**

## 1. System Philosophy: Modularity & Strict Separation
Project Sentinel divides responsibilities into clearly isolated subsystems. Data flows in a single direction from raw source logs to human decision.

```text
Approved Inbox / Synthetic Fixture
               │
               ▼
   [ Ingestion & Normalizer ] ──► Computes SHA-256 idempotency & redaction
               │
               ▼
   [ Normalized Event Store ] ──► Preserves source file & byte offset provenance
               │
               ▼
  [ Deterministic Rule Engine ] ──► Emits Findings with supporting Event IDs
               │
               ▼
   [ Case Correlator / Graph ] ──► Links findings into timeline with rationale
               │
               ▼
    [ Crew Agent Proposal ] ──► Generates typed Claim Objects (draft)
               │
               ▼
   [ Claim Guard Verifier ] ──► Recomputes facts; marks APPROVED or BLOCKED
               │
               ▼
    [ Operator Workbench ] ──► Human review & audit decision recording
```

## 2. Component Boundaries & Responsibilities

### A. Frontend (Kiro Crew App UI & Judge Demo)
- **Role:** Display investigation timeline, evidence relationships, findings, Claim Guard validation results, and operator triage controls.
- **Rules:**
  - Must connect to actual backend API or read-only synthetic scenario endpoints.
  - Must never fabricate incident counts, threat scores, or detection statistics.
  - Must implement complete UI states: loading, empty, error, backend unavailable, and connected.
  - Externalizes host-provided runtime dependencies (`react`, `react-dom`, `@kirocrew/app-sdk`, `lucide-react`) in Crew package mode.

### B. Backend (Python Investigation Engine)
- **Role:** Ingestion validation, path canonicalization, event normalization, deterministic rule evaluation, case assembly, and claim verification.
- **Rules:**
  - Standard library preferred where practical.
  - Stateless or durable SQLite storage with transactional consistency.
  - Exposes typed REST endpoints (`GET /health`, `/api/cases`, `/api/findings`, `/api/replay`, `/api/claims/verify`).
  - Strict input validation on all routes; untrusted data boundaries enforced.

### C. Shared Contracts
- Standard schemas for Canonical Events, Detection Rules, Findings, Cases, and Typed Claim Proposals located in `shared/contracts/`.
- Frontend and backend must conform to these shared schemas without divergence.

## 3. Data Flow Invariants
1. Raw source records are immutable.
2. Every normalized event retains source filename, line number, and SHA-256 provenance.
3. Every finding references at least one normalized event ID.
4. Every case references at least one finding and defines an explicit correlation key.
5. Every verified claim references existing event/finding IDs and passes numeric recomputation.
6. The UI separates verified facts from blocked or unverified hypotheses.

