# Project Sentinel — Phase 4.5 Defect Log
## Independent Technical Audit & Quality Remediation

**Audit Date:** November 9, 2026  
**Auditor:** Independent Principal QA & Security Engineer  
**Scope:** Phase 4 Detection Engine, Rule Implementations, Database Persistence, and API Contracts  
**Target Master Plan:** `Project_Sentinel_Kiroween_2026_WINNING_MASTER_PLAN_v3.md`

---

## Defect Summary Matrix

| Defect ID | Severity | Component | Summary | Status |
| :--- | :--- | :--- | :--- | :--- |
| **DEF-001** | Low | `tests/unit/test_normalization_db.py` | Migration count assumption broken by Migration 004 | **Resolved** |
| **DEF-002** | High | `backend/detection/rules.py` | `AUTH-002` pointer skip caused missed burst success detections | **Resolved** |
| **DEF-003** | Low | `backend/detection/models.py` | Missing exported `compute_rule_config_hash()` utility | **Resolved** |
| **DEF-004** | Medium | `tests/integration/test_findings_api.py` | API run response payload unnesting mismatch | **Resolved** |
| **DEF-005** | Medium | `scripts/verify_real_*.py` | Workflow verification scripts lacked database isolation | **Resolved** |
| **DEF-006** | High | `backend/detection/rules.py` | `WEB-001` URL encoding evasion & query/prefix false positives | **Resolved** |
| **DEF-007** | Medium | `backend/persistence/repository.py` | `INGEST-001` quarantined records invisible in `get_finding()` | **Resolved** |
| **DEF-008** | Low | `backend/detection/rules.py` | `PRIV-001` actor vs target entity ambiguity in conditions | **Resolved** |

---

## Detailed Defect Records

### DEF-001: Migration count assumption broken by Migration 004
- **Severity:** Low
- **Category:** Test Hardening
- **Root Cause:** `test_normalization_db.py` had a brittle assertion `self.assertEqual(len(versions), 3)` that broke when Migration 004 was introduced.
- **Impact:** Legitimate database evolution failed regression testing.
- **Evidence:** `AssertionError: 4 != 3` in `test_all_migrations_applied`.
- **Resolution:** Replaced rigid count with `self.assertGreaterEqual(len(versions), 3)` and explicitly validated migrations `001`, `002`, `003`, and `004`.
- **Regression Verification:** Test passed cleanly across all test discovery suites.

---

### DEF-002: `AUTH-002` pointer increment skipped success events inside burst window
- **Severity:** High
- **Category:** Detection Engine Correctness
- **Root Cause:** In `Auth002SuccessAfterFailuresRule.evaluate()`, the inner loop scanned for a qualifying failure burst (`j`), and then set the success search pointer `k = j`. However, if the 5th failure completed at index 4, and a success event occurred at index 5 before the end of the failure window, advancing `k` improperly or resetting `i` caused the evaluator to miss the success event or skip evaluation windows.
- **Impact:** Failure to alert on credential stuffing or brute force followed by immediate successful login.
- **Evidence:** `AssertionError: 0 != 1` in targeted window boundary tests.
- **Resolution:** Explicitly tracked `last_fail_idx = fail_events[-1][2]` and initialized scan pointer `k = last_fail_idx + 1`. Success events within 1800s following the burst are deterministically captured.
- **Regression Verification:** Unit tests for exact window boundaries, out-of-order events, and multi-user bursts passed with 100% precision.

---

### DEF-003: Missing exported `compute_rule_config_hash()` utility
- **Severity:** Low
- **Category:** Architecture & Interfaces
- **Root Cause:** `RuleDefinition` calculated config hashes in inline logic, but `rules.py` and external callers imported `compute_rule_config_hash` directly from `backend.detection.models`.
- **Impact:** `ImportError` on dynamic rule re-registration or external rule definition creation.
- **Evidence:** `ImportError: cannot import name 'compute_rule_config_hash' from 'backend.detection.models'`.
- **Resolution:** Extracted deterministic canonical JSON hash calculation into public standalone function `compute_rule_config_hash(config: Dict[str, Any]) -> str` in `backend/detection/models.py`.
- **Regression Verification:** Unit tests and engine initialization verified.

---

### DEF-004: API detection run response wrapper mismatch in integration test
- **Severity:** Medium
- **Category:** Integration & Contracts
- **Root Cause:** `POST /api/detection/run` wrapped execution metrics in `{"status": "success", "result": {...}}`. Integration test accessed `data["evaluation_id"]` directly at top-level.
- **Impact:** API test failure and confusing client contract assumptions.
- **Evidence:** `KeyError: 'evaluation_id'` in `test_findings_api.py`.
- **Resolution:** Updated test to access `data["result"]["evaluation_id"]` conforming to the unified Sentinel API envelope contract.
- **Regression Verification:** `test_findings_api.py` passed with 0 errors.

---

### DEF-005: Workflow verification scripts lacked per-run database isolation
- **Severity:** Medium
- **Category:** Test Harness & CI/CD
- **Root Cause:** Scripts `verify_real_normalization_workflow.py` and `verify_real_detection_workflow.py` defaulted to shared local database `sentinel.db`. Repeated runs encountered duplicate SHA-256 hash prevention and accumulated findings.
- **Impact:** Verification scripts were flaky when re-run consecutively.
- **Evidence:** `AssertionError: Expected at least 1 rejected, got 0` due to duplicate payload skipping.
- **Resolution:** Updated verification scripts to provision an isolated `tempfile.TemporaryDirectory()` database via `SENTINEL_DB_PATH` and inject unique timestamps per execution, cleaning up on exit.
- **Regression Verification:** Both scripts run repeatedly and deterministically without cross-run state pollution.

---

### DEF-006: `WEB-001` route matching susceptible to evasion and false positives
- **Severity:** High
- **Category:** Security & Detection Accuracy
- **Root Cause:** `Web001SensitiveRouteBurstRule` evaluated routes with naive lowercase substring containment: `any(resource.startswith(prefix) or prefix in resource for prefix in sensitive_prefixes)`. This produced:
  1. *Evasion:* An attacker requesting `/%61%64%6d%69%6e` bypassed `/admin`.
  2. *Evasion:* Traversal sequences such as `/foo/../admin` or redundant slashes `//admin` bypassed prefix matching.
  3. *False Positive:* Legitimate searches like `/search?q=/admin` triggered the rule because `/admin` appeared in the query parameter.
  4. *False Positive:* Benign endpoints with common prefixes like `/administrator` triggered `/admin`.
  5. *Grouping defect:* Anonymous requests lacking both IP and user identity were lumped into `"unknown_source"`, falsely triggering burst alerts across unrelated clients.
- **Impact:** Evasion of sensitive route surveillance and alert fatigue from false positives.
- **Evidence:** Unit tests demonstrated `/search?q=/admin` triggering false bursts and `/%61%64%6d%69%6e` evading detection.
- **Resolution:**
  - Implemented RFC-compliant `normalize_web_route(raw: str) -> str`: strips query strings and fragments, collapses redundant leading slashes, decodes percent-encoding via `urllib.parse.unquote`, and resolves relative traversals via `posixpath.normpath`.
  - Implemented `is_sensitive_route(target: str, sensitive_routes: List[str]) -> bool`: performs exact matching, directory-prefix matching (`/admin/...`), and dotfile matching (`/.env`).
  - Required explicit `source_ip` or `user_principal`, skipping unidentifiable anonymous records rather than lumping them together.
- **Regression Verification:** Added unit tests `test_web001_percent_encoded_and_traversal`, `test_web001_false_positive_query_and_prefix`, and `test_web001_anonymous_missing_identity`. All passed.

---

### DEF-007: `INGEST-001` quarantined records invisible in finding evidence query
- **Severity:** Medium
- **Category:** Data Model & Analyst Visibility
- **Root Cause:** Relational table `finding_events` strictly links `finding_id` to `normalized_events(event_id)`. However, quarantined records produced by normalization failures only exist in `normalization_errors` and `parsed_records`, meaning `supporting_event_ids` was empty (`[]`). Consequently, when an analyst inspected a finding via `GET /api/findings/{id}`, the API returned `supporting_events: []` with zero visibility into the quarantined error details.
- **Impact:** Analysts could not review which quarantined records triggered the anomaly alert without writing raw SQLite queries.
- **Evidence:** `get_finding()` returned empty supporting events for `INGEST-001` findings.
- **Resolution:** Enhanced `get_finding()` in `IngestionRepository` to check if `matched_conditions["record_ids"]` exists when `supporting_event_ids` is empty, querying `normalization_errors` and populating `finding_dict["quarantined_records"]`.
- **Regression Verification:** Added unit test `test_get_finding_with_quarantined_records` in `tests/unit/test_findings_db.py`. Passed.

---

### DEF-008: `PRIV-001` actor vs target entity ambiguity in condition evidence
- **Severity:** Low
- **Category:** Audit Trail & Explainability
- **Root Cause:** `Priv001PrivilegeChangeRule` populated `matched_conditions` with a single `target_entity` field, which made it ambiguous whether the user recorded was the administrative actor who granted the permission or the target user whose privileges were modified.
- **Impact:** Potential confusion in incident response triaging.
- **Evidence:** Findings for `grant_role` listed `secops_admin` as entity even when modifying user `bob`.
- **Resolution:** Enhanced `Priv001PrivilegeChangeRule.evaluate()` to extract both `actor` (`evt["user_principal"]`) and `target_user` (`attrs["target_user"]` or `attrs["target"]`), assigning `entity = target_user or actor` and storing both fields in `matched_conditions`.
- **Regression Verification:** Added assertion in `test_priv001_positive` verifying both `actor` and `target_user` are present and distinct. Passed.

