# Project Sentinel — Phase 6 Claim Guard Architecture & Verification Design Specification
**Document Version:** 1.0.0  
**Status:** Approved & Implemented  
**Sprint:** Sprint 6 (Claim Guard: Typed AI Claims, Deterministic Verification & Safe Rendering)  

---

## 1. Executive Summary & Purpose

Phase 1 through 5 established the deterministic forensic foundation of Project Sentinel:
- **Phase 1 & 1.5:** Secure foundation shell, offline resilience, and frontend navigation.
- **Phase 2 & 2.5:** Multi-source log ingestion, parser profiles, SHA-256 deduplication, and SQLite persistence.
- **Phase 3 & 3.5:** Canonical event normalization, timezone enforcement, provenance tracking, and quarantine.
- **Phase 4 & 4.5:** Deterministic detection rules, sliding-window evaluators, and explainable findings.
- **Phase 5 & 5.5:** Deterministic correlation clustering, collision-resistant case IDs, derived severity, chronological timelines, append-only operator review notes, and state-machine-validated case lifecycle.

Phase 6 introduces **Claim Guard**:
A zero-trust verification boundary for AI-assisted security analysis conforming to the master plan specification (`Project_Sentinel_Kiroween_2026_WINNING_MASTER_PLAN_v3.md`, Sections 7, 10, 11, 12, 19).

### Core Architectural Axiom:
> **"AI proposes. Deterministic code verifies. The operator decides."**

### Core Architectural Principles:
1. **Never Render Raw LLM Prose as Fact:** Unverified AI-generated text is strictly prevented from appearing as verified factual statements in the investigation workspace.
2. **Finite Typed Claim Vocabulary:** LLM agents do not generate free-form text for factual assertions; they submit structured, strongly-typed JSON proposals adhering to an immutable JSON Schema (`shared/contracts/claim_contract.json`).
3. **Deterministic Multi-Stage Verifier:** A pure Python verification engine (`ClaimVerifier`) checks claims against SQLite evidence tables using mathematical and relational checks. The LLM has zero involvement in evaluating or scoring its own claims.
4. **Three Strict Verification Outcomes:**
   - `verified`: Evidence exists within the case, matches claimed values/predicates exactly, and satisfies all 9 deterministic verification checks.
   - `qualified`: Structurally valid and supported by evidence, but carries explicit caveats (e.g. certainty is `inferred` or `hypothesis`, or data quality warnings exist).
   - `blocked`: Evidence is missing, refers to evidence outside the case (cross-case tampering), contains conflicting values, attempts prompt/script injection, or infers user identity from IP alone. Blocked claims are strictly quarantined in the audit panel and never rendered in the factual narrative.
5. **Approved Template Catalog with Mandatory HTML Escaping:** Verified and qualified claims are rendered exclusively through vetted parameter substitution templates (`backend/claims/templates.py`). All parameters undergo strict `html.escape()` sanitization to block XSS attacks.
6. **Strict Evidence Containment & Cross-Case Reference Detection:** Claims may only reference evidence IDs associated with the target case (`case_events` and `case_findings`). Referencing IDs from other cases or non-existent records triggers an immediate `blocked` outcome.
7. **Anti-Hallucination Guardrails:** Claims asserting a human identity (`user_principal`) based solely on IP address evidence without explicit user attribution are categorically rejected.
8. **Client-Status Tampering Immunity:** The backend verifier completely ignores any client-supplied `status` field in the proposal payload; verification status is calculated strictly server-side.

---

## 2. Typed Claim Schema & Approved Vocabulary

### 2.1 The Finite Set of Claim Types
Claim Guard supports exactly 8 finite claim types:

| Claim Type | Predicates | Description |
| :--- | :--- | :--- |
| `event_count` | `contains_events_of_type`, `total_event_count`, `failed_event_count` | Asserts exact count of events of a specific type or status. |
| `finding_exists` | `contains_finding_for_rule`, `has_detection` | Asserts that a finding for an approved rule ID exists in the case. |
| `rule_match` | `rule_matched_condition`, `rule_condition_satisfied` | Asserts that a specific detection rule condition was satisfied. |
| `time_window` | `spans_time_window`, `activity_observed_between` | Asserts the temporal boundary across referenced evidence. |
| `entity_observed` | `identifies_entity`, `actor_identified`, `target_identified` | Asserts an observed actor, target, or entity attribute. |
| `case_status` | `has_case_status`, `case_severity_is` | Asserts current case triage status or derived severity. |
| `correlation_relationship` | `correlated_by_key`, `shares_identity_dimension` | Asserts a correlation relationship across case entities. |
| `data_quality_issue` | `contains_data_anomaly`, `quarantined_record_present` | Asserts presence of quarantined records or data quality warnings. |

### 2.2 Claim Proposal Contract (`shared/contracts/claim_contract.json`)
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ClaimProposal",
  "type": "object",
  "required": ["claim_id", "case_id", "claim_type", "predicate", "value", "evidence_refs", "certainty", "template_id"],
  "properties": {
    "claim_id": { "type": "string", "maxLength": 64 },
    "case_id": { "type": "string", "maxLength": 64 },
    "claim_type": { "type": "string", "enum": ["event_count", "finding_exists", "rule_match", "time_window", "entity_observed", "case_status", "correlation_relationship", "data_quality_issue"] },
    "predicate": { "type": "string", "maxLength": 64 },
    "value": { "type": "object" },
    "evidence_refs": { "type": "array", "items": { "type": "string" } },
    "certainty": { "type": "string", "enum": ["observed", "inferred", "hypothesis"] },
    "template_id": { "type": "string", "maxLength": 64 },
    "proposed_by": { "type": "string", "default": "kiro_crew_agent" },
    "created_at": { "type": "string" }
  }
}
```

---

## 3. The 9 Deterministic Verifier Checks

The `ClaimVerifier` pipeline executes 9 sequential deterministic checks for every proposal:

```
[Claim Proposal]
       │
       ▼
 1. Schema Conformance Check ────(Fail)───► [BLOCKED: Malformed Schema]
       │ (Pass)
       ▼
 2. Approved Template Check ─────(Fail)───► [BLOCKED: Unapproved Template]
       │ (Pass)
       ▼
 3. Injection Scan Check ────────(Fail)───► [BLOCKED: Injection Detected]
       │ (Pass)
       ▼
 4. Case Containment Check ──────(Fail)───► [BLOCKED: Cross-Case / Missing Evidence]
       │ (Pass)
       ▼
 5. Value & Predicate Check ─────(Fail)───► [BLOCKED: Value Mismatch]
       │ (Pass)
       ▼
 6. IP Identity Guardrail ───────(Fail)───► [BLOCKED: IP-Only Attribution Rejected]
       │ (Pass)
       ▼
 7. Data Quality Audit ──────────(Warning)─► [FLAG: Qualification Warning]
       │
       ▼
 8. Certainty Evaluation ────────(Inferred/Hypothesis)─► [QUALIFIED]
       │ (Observed & No Warnings)
       ▼
 9. Safe Rendering Check ────────► [VERIFIED] (Render template with html.escape)
```

1. **`schema_conformance`:** Validates required fields, maximum string lengths, and non-empty IDs.
2. **`template_vetting`:** Confirms `template_id` exists in `APPROVED_TEMPLATES` and supports `claim_type`.
3. **`injection_safety`:** Scans all string values and predicates against prompt injection and script tag patterns (`<script>`, `javascript:`, `eval\(`, `ignore previous instructions`, etc.).
4. **`evidence_containment`:** Verifies all referenced evidence IDs exist within the target case (`case_events` or `case_findings`). Distinguishes nonexistent IDs from IDs belonging to a foreign case (cross-case tampering).
5. **`value_matches_evidence`:** Performs type-specific mathematical validation (e.g. counting exact matching events, finding rule matching, time window bounding).
6. **`ip_identity_guardrail`:** Prevents attributing user identity based solely on an IP address without an explicit `user_principal`.
7. **`data_quality_clean`:** Audits whether any referenced evidence contains normalization warnings or anomalies.
8. **`certainty_alignment`:** If certainty is `inferred` or `hypothesis`, the status is categorized as `qualified` rather than `verified`.
9. **`safe_rendering`:** Vetted template substitution using `html.escape()` on all parameter values.

---

## 4. Safe Rendering Architecture (`SafeClaimRenderer`)

- **Strict Affirmation Quarantine:** Blocked claims are NEVER rendered with affirmative template text. Instead, they render a standardized quarantine message:
  ```
  [BLOCKED CLAIM] Rejected: <reasons>. Suggested remedy: <remedy>
  ```
- **Qualified Caveat Tagging:** Qualified claims prepend `[QUALIFIED]` and append explicit qualification caveats.
- **XSS Immunity:** Every dynamic parameter formatted into templates passes through `html.escape()`. Untrusted log data (such as attack payloads in usernames or URIs) cannot execute HTML/JS in analyst browsers.

---

## 5. SQLite Data Model (Migration 006)

### 5.1 `claim_proposals` Table
```sql
CREATE TABLE IF NOT EXISTS claim_proposals (
    claim_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    claim_type TEXT NOT NULL,
    predicate TEXT NOT NULL,
    value_json TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    certainty TEXT NOT NULL,
    template_id TEXT NOT NULL,
    proposed_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);
```

### 5.2 `claim_verifications` Table
```sql
CREATE TABLE IF NOT EXISTS claim_verifications (
    verification_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    status TEXT NOT NULL,
    verification_version TEXT NOT NULL,
    checks_json TEXT NOT NULL,
    rendered_text TEXT NOT NULL,
    qualification_notes_json TEXT NOT NULL,
    blocked_reasons_json TEXT NOT NULL,
    suggested_remedy TEXT,
    evidence_refs_json TEXT NOT NULL,
    verified_at TEXT NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES claim_proposals(claim_id) ON DELETE CASCADE,
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);
```

---

## 6. Signature Demo Moment Specification (Master Plan Section 7.5)

To decisively demonstrate the power of Claim Guard to operators and hackathon judges, Sentinel implements the **Claim Guard Demo Moment**:
When an analyst opens an investigation case and navigates to the **Claim Guard** tab, they can click **"Run Claim Guard Verification"** (`POST /api/cases/{case_id}/claims/demo`).
The engine automatically generates and evaluates a curated bundle of claims:
1. **Verified Claim 1:** Exact observed event count (e.g. 5 failed authentication attempts).
2. **Verified Claim 2:** Verified finding existence (e.g. `AUTH-001` brute force detection).
3. **Qualified Claim:** Inferred correlation relationship (e.g. user `analyst_bob` linked across events, certainty: `inferred`).
4. **Adversarial Claim 1 (Hallucination Blocked):** AI asserts an exaggerated count (e.g. 25 failures instead of 5). Blocked with remedy: *"Update claimed count to 5"*.
5. **Adversarial Claim 2 (Cross-Case Tampering Blocked):** AI references evidence from an unrelated case or non-existent record. Blocked with remedy: *"Remove invalid references"*.
6. **Adversarial Claim 3 (IP-Only Attribution Blocked):** AI claims user identity based solely on a network IP address. Blocked with remedy: *"Cannot infer user identity from IP address alone"*.

The analyst immediately observes the three distinct visual sections:
- **Green Cards:** Verified factual claims with clickable evidence chips.
- **Amber Cards:** Qualified claims with clear inference caveats.
- **Red Audit Panel:** Blocked claims quarantined with transparent failure reasons and actionable remedies.

