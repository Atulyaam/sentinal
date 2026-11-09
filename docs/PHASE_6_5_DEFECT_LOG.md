# Project Sentinel — Phase 6.5 Defect & Security Vulnerability Log
## Claim Guard: Typed Claims, Deterministic Verification & Safe Rendering

**Audit Date:** November 9, 2026  
**Auditor:** Principal Independent Application Security & Integrity Auditor  
**Scope:** Phase 6 Claim Guard Implementation (`backend/claims/`, `backend/persistence/`, `backend/api/`, and related contracts)  
**Status:** ALL DEFECTS REMEDIATED & REGRESSION TESTED  

---

### Defect Summary Table

| Defect ID | Severity | Component | Summary | Status | Regression Test |
| :--- | :---: | :--- | :--- | :---: | :--- |
| **DEF-CLAIM-001** | High | `backend/claims/verifier.py` | Inverted time windows, non-enclosing time windows, and bogus duration values verified without validation | FIXED | `test_def_claim_001_*` (3 tests) |
| **DEF-CLAIM-002** | High | `backend/claims/verifier.py` | `event_count` ignored `failed_event_count` predicate and status filter, verifying success events as failures | FIXED | `test_def_claim_002_*` (2 tests) |
| **DEF-CLAIM-003** | High | `backend/claims/verifier.py` | Verifier failed to validate presence of template required parameters before rendering | FIXED | `test_def_claim_003_missing_template_param_blocked` |
| **DEF-CLAIM-004** | High | `backend/claims/verifier.py` | Proof-carrying claims allowed empty `evidence_refs: []` or unverified finding references | FIXED | `test_def_claim_004_*` (2 tests) |
| **DEF-CLAIM-005** | Medium | `backend/claims/verifier.py` | `data_quality_issue` ignored `record_count` in claim value, permitting arbitrary record counts | FIXED | `test_def_claim_005_*` (2 tests) |
| **DEF-CLAIM-006** | Medium | `backend/claims/models.py` | `ClaimProposal.from_dict` converted `None` to `"None"` and permitted arbitrary unknown fields | FIXED | `test_def_claim_006_*` (2 tests) |
| **DEF-CLAIM-007** | Low | `backend/claims/verifier.py` | `event_count` matched `event_type` against arbitrary substring occurrences in attribute dictionary values | FIXED | `test_def_claim_007_event_type_strict_matching_no_attribute_leak` |
| **DEF-CLAIM-008** | Low | `backend/claims/verifier.py` | Verification checks audit trail omitted explicit `data_quality_clean` and `certainty_alignment` stages | FIXED | `test_def_claim_008_verification_checks_complete_audit_trail` |
| **DEF-CLAIM-009** | Medium | `backend/persistence/repository.py` | `persist_claim_proposal` used `INSERT OR REPLACE`, permitting historical proposal mutation/overwrite | FIXED | `test_claim_proposal_persistence_immutable` |

---

### Detailed Defect Analyses & Remediations

#### 1. DEF-CLAIM-001: Time Window Inversion, Non-Enclosure, and Bogus Duration
- **Severity:** High
- **Component:** [`backend/claims/verifier.py`](file:///c:/Users/Atul2/OneDrive/Desktop/KiroHackethon/sentinal/backend/claims/verifier.py#L460-L510)
- **Description:**  
  The time window verification logic originally performed only a weak overlap check: `if claimed_start > evidence_end or claimed_end < evidence_start: ...`.
  This allowed three major security and factual integrity flaws:
  1. **Inverted Windows:** An adversary or buggy LLM could propose `start_time = "08:15:00"` and `end_time = "08:00:00"`, which passed if the strings were not chronologically validated.
  2. **Non-Enclosing Windows:** If evidence spanned `08:00:00` to `08:10:00`, a claim asserting the window was `08:02:00` to `08:05:00` would pass because it partially overlapped, even though evidence fell outside the claimed window.
  3. **Bogus Duration:** The template `case_time_window_v1` renders `duration_seconds`, but `verifier.py` never verified that `duration_seconds` matched the difference between `start_time` and `end_time`, allowing an LLM to state `duration_seconds: 999999` on a 10-minute window.
- **Root Cause:** Incomplete boundary and arithmetic validation on temporal parameters.
- **Remediation:**
  - Added strict chronological validation: `if claimed_start > claimed_end: return False, ...`
  - Enforced full containment: `if claimed_start > evidence_start or claimed_end < evidence_end: return False, ...`
  - Validated `duration_seconds` against computed window duration with 1.0s tolerance.
- **Verification Evidence:** `test_def_claim_001_inverted_time_window_blocked`, `test_def_claim_001_unenclosed_time_window_blocked`, and `test_def_claim_001_bogus_duration_seconds_blocked` all pass.

---

#### 2. DEF-CLAIM-002: Ignored `failed_event_count` Predicate and Status Filtering
- **Severity:** High
- **Component:** [`backend/claims/verifier.py`](file:///c:/Users/Atul2/OneDrive/Desktop/KiroHackethon/sentinal/backend/claims/verifier.py#L350-L380)
- **Description:**  
  In `_verify_claim_value` for `event_count`, the verifier only counted referenced events matching `event_type`. It completely ignored `proposal.predicate == "failed_event_count"` and any `status` specified in `proposal.value`.
  Consequently, a proposal asserting `failed_event_count` with 1 event was verified as a verified fact even when the single referenced event was a successful login (`status="SUCCESS"`).
- **Root Cause:** The event count evaluator did not inspect `proposal.predicate` or `val.get("status")`.
- **Remediation:**
  - When `proposal.predicate == "failed_event_count"`, strictly filtered `matching_events` to only those where `status.upper() in ("FAILURE", "LOCKED", "ERROR")`.
  - When `"status"` is provided in `val`, strictly filtered `matching_events` by matching status.
- **Verification Evidence:** `test_def_claim_002_failed_event_count_on_success_events_blocked` and `test_def_claim_002_failed_event_count_matches_failures_verified` pass.

---

#### 3. DEF-CLAIM-003: Missing Template Required Parameter Completeness Check
- **Severity:** High
- **Component:** [`backend/claims/verifier.py`](file:///c:/Users/Atul2/OneDrive/Desktop/KiroHackethon/sentinal/backend/claims/verifier.py#L74-L87)
- **Description:**  
  The verifier previously checked that `proposal.template_id` was in `APPROVED_TEMPLATES`, but never checked that `proposal.value` contained all parameters required by that template. When an LLM submitted a proposal for `case_status_v1` (which requires `status` and `severity`) omitting `status`, the safe renderer output:
  `"Case status is '[missing status]' with derived severity 'High'."` and marked it `verified`.
- **Root Cause:** Verification pipeline lacked a stage verifying value completeness against `tmpl["required_params"]`.
- **Remediation:**
  - Added Step 2 check `template_params_complete`:
    ```python
    missing_params = [p for p in tmpl.get("required_params", []) if p not in proposal.value or proposal.value[p] is None or proposal.value[p] == ""]
    if missing_params:
        is_blocked = True
        ...
    ```
- **Verification Evidence:** `test_def_claim_003_missing_template_param_blocked` passes.

---

#### 4. DEF-CLAIM-004: Empty Evidence References Allowed for Proof-Carrying Claims
- **Severity:** High
- **Component:** [`backend/claims/verifier.py`](file:///c:/Users/Atul2/OneDrive/Desktop/KiroHackethon/sentinal/backend/claims/verifier.py#L113-L120)
- **Description:**  
  Stage 5 of the verifier previously allowed empty `proposal.evidence_refs: []` for certain claim types such as `finding_exists` and `rule_match`, and only checked existence when refs were non-empty. This violated the core Master Plan requirement that all factual claims must be proof-carrying and cite specific evidence IDs.
- **Root Cause:** Guard check `if not proposal.evidence_refs:` was only implemented for `event_count` inside `_verify_claim_value`.
- **Remediation:**
  - Added global Stage 5 check requiring non-empty `evidence_refs` for all proof-carrying claim proposals:
    ```python
    if not proposal.evidence_refs:
        is_blocked = True
        msg = "Empty evidence references: Proof-carrying claims must cite at least one valid event or finding reference."
        checks.append(VerificationCheck(name="evidence_exists", passed=False, reason=msg))
    ```
  - For `finding_exists`, required that at least one of the referenced IDs matches a finding for the claimed rule.
- **Verification Evidence:** `test_def_claim_004_finding_exists_empty_evidence_refs_blocked` and `test_def_claim_004_finding_exists_without_finding_ref_blocked` pass.

---

#### 5. DEF-CLAIM-005: Unverified `record_count` in Data Quality Anomaly Claims
- **Severity:** Medium
- **Component:** [`backend/claims/verifier.py`](file:///c:/Users/Atul2/OneDrive/Desktop/KiroHackethon/sentinal/backend/claims/verifier.py#L600-L640)
- **Description:**  
  The handler for `claim_type == "data_quality_issue"` merely checked whether an `INGEST-001` finding existed in the case. It completely ignored the `record_count` field in `proposal.value`. An LLM could propose that 999,999 records were corrupted or quarantined when only 1 was quarantined, and Claim Guard would verify it.
- **Root Cause:** Absence of record count verification in `data_quality_issue` evaluation logic.
- **Remediation:**
  - Evaluated actual quarantined/anomalous record count from `finding["matched_conditions"]["record_ids"]` or `finding["supporting_event_ids"]` or event quality warning flags.
  - Enforced exact match: `if int(claimed_record_count) != actual_records: return False, ...`
- **Verification Evidence:** `test_def_claim_005_data_quality_hallucinated_record_count_blocked` and `test_def_claim_005_data_quality_accurate_record_count_verified` pass.

---

#### 6. DEF-CLAIM-006: Deserialization Coercion of `None` to String `"None"` & Unknown Field Tolerance
- **Severity:** Medium
- **Component:** [`backend/claims/models.py`](file:///c:/Users/Atul2/OneDrive/Desktop/KiroHackethon/sentinal/backend/claims/models.py#L90-L135)
- **Description:**  
  `ClaimProposal.from_dict` used `str(data.get("claim_id", ""))`. When an adversary or client sent `{"claim_id": None}`, Python evaluated `str(None)` to `"None"`, which is a non-empty string and passed schema validation. Additionally, `from_dict` ignored unknown keys, permitting payload injection or unvetted configuration options.
- **Root Cause:** Blind `str()` casting during dictionary parsing and lack of unexpected field validation.
- **Remediation:**
  - Enforced strict type checking: verified that `claim_id`, `case_id`, `claim_type`, `predicate`, and `template_id` are explicit `str` instances and not `None`.
  - Added unexpected key rejection: validated that all keys in `data` belong to recognized fields (`claim_id`, `case_id`, `subject_ref`, `claim_type`, `predicate`, `value`, `evidence_refs`, `certainty`, `template_id`, `proposed_by`, `created_at`).
- **Verification Evidence:** `test_def_claim_006_from_dict_rejects_none_and_non_strings` and `test_def_claim_006_from_dict_rejects_unknown_fields` pass.

---

#### 7. DEF-CLAIM-007: Event Matching Substring Leak in Attributes Dictionary
- **Severity:** Low
- **Component:** [`backend/claims/verifier.py`](file:///c:/Users/Atul2/OneDrive/Desktop/KiroHackethon/sentinal/backend/claims/verifier.py#L340-L355)
- **Description:**  
  When filtering events by `event_type`, the verifier used:
  `claimed_type in str(e.get("attributes", {}).values())`
  If an adversary claimed an event type of `"Windows"`, and an event carried `attributes={"user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}`, the verifier counted that event as a match.
- **Root Cause:** Overly permissive substring matching against serialized Python dictionaries.
- **Remediation:**
  - Replaced arbitrary dictionary substring search with strict field inspection:
    `e.get("event_type") == claimed_type or e.get("attributes", {}).get("action") == claimed_type or e.get("attributes", {}).get("event_name") == claimed_type`
- **Verification Evidence:** `test_def_claim_007_event_type_strict_matching_no_attribute_leak` passes.

---

#### 8. DEF-CLAIM-008: Incomplete 9-Stage Verification Checks Audit Trail
- **Severity:** Low
- **Component:** [`backend/claims/verifier.py`](file:///c:/Users/Atul2/OneDrive/Desktop/KiroHackethon/sentinal/backend/claims/verifier.py#L200-L225)
- **Description:**  
  The Claim Guard specification requires that every verification result contains an audit trail of checks representing all stages of the verification pipeline. Previously, `data_quality_clean` was only appended when a data quality issue was detected, and `certainty_alignment` was only appended when certainty was inferred, omitting entries when the evidence was clean.
- **Root Cause:** Conditional check generation rather than unconditional stage recording.
- **Remediation:**
  - Ensured both `data_quality_clean` and `certainty_alignment` append a `VerificationCheck` object whether the check passed or flagged an issue.
- **Verification Evidence:** `test_def_claim_008_verification_checks_complete_audit_trail` passes.

---

#### 9. DEF-CLAIM-009: Mutation of Historical Claim Proposals via `INSERT OR REPLACE`
- **Severity:** Medium
- **Component:** [`backend/persistence/repository.py`](file:///c:/Users/Atul2/OneDrive/Desktop/KiroHackethon/sentinal/backend/persistence/repository.py#L1480-L1500)
- **Description:**  
  In `persist_claim_proposal`, SQL `INSERT OR REPLACE` was used. In a forensic application, agent claim proposals represent historical claims proposed at a specific point in time. Allowing re-insertion with the same `claim_id` to overwrite existing proposals violates append-only integrity.
- **Root Cause:** Use of `INSERT OR REPLACE` instead of `INSERT OR IGNORE`.
- **Remediation:**
  - Changed `INSERT OR REPLACE INTO claim_proposals` to `INSERT OR IGNORE INTO claim_proposals`.
- **Verification Evidence:** `test_claim_proposal_persistence_immutable` passes.

