# Project Sentinel — Phase 5.5 Defect Log
## Independent Technical Audit & Quality Remediation

**Audit Date:** November 9, 2026  
**Auditor:** Independent Principal QA, Security Engineer & Kiro Integration Specialist  
**Scope:** Phase 5 Investigation Cases, Deterministic Correlation Engine, Evidence Timeline, Database Persistence, and Case Management APIs  
**Target Master Plan:** `Project_Sentinel_Kiroween_2026_WINNING_MASTER_PLAN_v3.md`

---

## Defect Summary Matrix

| Defect ID | Severity | Component | Summary | Status |
| :--- | :--- | :--- | :--- | :--- |
| **DEF-CASE-001** | Medium | `backend/persistence/repository.py` | Out-of-order evidence arrival caused stale `first_observed_at` and description in existing cases | **Resolved** |
| **DEF-CASE-002** | Low | `backend/cases/engine.py` | Inverted correlation key priority between `session_id` and `request_id` due to alphabetical ordering | **Resolved** |
| **DEF-CASE-003** | Low | `backend/persistence/repository.py` | Non-deterministic timeline order when items shared identical millisecond timestamps | **Resolved** |
| **DEF-CASE-004** | Low | `backend/persistence/repository.py` | Unbounded operator note and author string lengths permitted oversized payload insertions | **Resolved** |
| **DEF-CASE-005** | Low | `backend/persistence/repository.py` & `backend/api/handler.py` | Missing backend `search` parameter in `list_cases` API and database repository | **Resolved** |

---

## Detailed Defect Records

### DEF-CASE-001: Out-of-order evidence arrival caused stale `first_observed_at` and description in existing cases
- **Severity:** Medium
- **Category:** Data Integrity & Timeline Accuracy
- **Root Cause:** In `IngestionRepository.persist_cases_batch()`, the `UPDATE cases` query updated `last_observed_at = MAX(last_observed_at, ?)` and bumped `updated_at`. However, it omitted `first_observed_at = MIN(first_observed_at, ?)` and did not update `description` to reflect expanded evidence counts. If a delayed log arrived with an earlier timestamp in the same time bucket, the case's `first_observed_at` remained pinned to the later timestamp of the initial log.
- **Impact:** Misleading case boundaries on out-of-order log ingestion; stale description summary stating outdated counts.
- **Evidence:** Inserting an initial finding with timestamp `10:30:00` followed by a delayed finding with timestamp `10:05:00` resulted in `first_observed_at` remaining `10:30:00`.
- **Resolution:** Modified the SQL `UPDATE cases` statement in `backend/persistence/repository.py`:
  ```sql
  UPDATE cases
  SET last_observed_at = MAX(last_observed_at, ?),
      first_observed_at = MIN(first_observed_at, ?),
      description = ?,
      severity = CASE
          WHEN ? = 'Critical' OR severity = 'Critical' THEN 'Critical'
          WHEN ? = 'High' OR severity = 'High' THEN 'High'
          WHEN ? = 'Medium' OR severity = 'Medium' THEN 'Medium'
          WHEN ? = 'Low' OR severity = 'Low' THEN 'Low'
          ELSE severity
      END,
      updated_at = ?
  WHERE case_id = ?;
  ```
- **Regression Verification:** Added `test_out_of_order_evidence_updates_first_observed_and_description` in `tests/unit/test_cases_audit.py`. Confirmed `first_observed_at` updates to `10:05:00` and description reflects the aggregated finding count.

---

### DEF-CASE-002: Inverted correlation key priority between `session_id` and `request_id` due to alphabetical ordering
- **Severity:** Low
- **Category:** Correlation Clustering Precision
- **Root Cause:** In `CorrelationEngine._select_correlation_key()`, candidates were selected using `sorted(candidates, key=lambda c: c[0])` where `c[0]` was the key type string (`"request_id"`, `"session_id"`, `"user_principal"`). Because `"request_id" < "session_id"` alphabetically, when a user principal was absent, the engine favored `request_id` over `session_id`. However, according to Section 6.5 of the Master Plan, a session represents a broader and more meaningful identity boundary than an individual HTTP request.
- **Impact:** Related events belonging to the same user session were fragmented into multiple isolated request-level cases rather than clustered under the unified session.
- **Evidence:** An event with both `session_id="sess_xyz"` and `request_id="req_123"` was clustered under `request_id` instead of `session_id`.
- **Resolution:** Introduced an explicit integer priority mapping in `backend/cases/engine.py`:
  ```python
  key_priority = {
      "user_principal": 1,
      "session_id": 2,
      "request_id": 3,
      "source_ip": 4,
  }
  best_candidate = min(candidates, key=lambda c: key_priority.get(c[0], 99))
  ```
- **Regression Verification:** Added `test_key_priority_session_over_request_id` in `tests/unit/test_cases_audit.py`. Confirmed `session_id` is selected when `user_principal` is absent.

---

### DEF-CASE-003: Non-deterministic timeline order when items shared identical millisecond timestamps
- **Severity:** Low
- **Category:** Evidence Presentation & Reproducibility
- **Root Cause:** In `IngestionRepository.get_case()`, timeline items from multiple sources (`events`, `findings`, `correlation_created`, `review_actions`) were merged into a single array and sorted solely by `lambda x: x["timestamp"]`. When a correlated event, finding, and correlation action occurred at the exact same millisecond, Python's Timsort preserved arbitrary insertion order, producing variable timeline ordering between test runs or across different database read passes.
- **Impact:** Inconsistent timeline rendering across UI reloads when evidence possessed identical timestamps.
- **Evidence:** Event items and finding items swapped order depending on dictionary iteration order.
- **Resolution:** Established a strict secondary logical tiebreaker in `backend/persistence/repository.py`:
  ```python
  timeline_type_order = {
      "event": 1,
      "finding": 2,
      "correlation": 3,
      "status_change": 4,
      "review_action": 5,
  }
  timeline.sort(key=lambda x: (x.get("timestamp") or "", timeline_type_order.get(x.get("type", ""), 99), x.get("id") or ""))
  ```
- **Regression Verification:** Added `test_timeline_sorting_stability_on_identical_timestamps` in `tests/unit/test_cases_audit.py`. Verified exact deterministic order: `event` $\to$ `finding` $\to$ `correlation` $\to$ `review_action`.

---

### DEF-CASE-004: Unbounded operator note and author string lengths permitted oversized payload insertions
- **Severity:** Low
- **Category:** Input Validation & Database Protection
- **Root Cause:** `update_case_status()` and `add_case_note()` validated that `operator_note` was not empty, but enforced no maximum string length constraint on either `operator_note` or `author`. A client could inadvertently or maliciously submit an arbitrary multi-megabyte string into `review_actions`.
- **Impact:** Potential SQLite database bloat and memory pressure in timeline retrieval.
- **Evidence:** Notes of 500,000 characters were inserted without validation rejection.
- **Resolution:** Enforced strict length limits in `backend/persistence/repository.py`:
  - `operator_note`: maximum 10,000 characters.
  - `author`: maximum 100 characters.
  Calls exceeding these limits immediately raise `ValueError` (which maps to HTTP 400 Bad Request at the API layer).
- **Regression Verification:** Added `test_oversized_note_and_author_rejected` in `tests/unit/test_cases_audit.py`. Rejections verified for notes $> 10,000$ characters and authors $> 100$ characters.

---

### DEF-CASE-005: Missing backend `search` parameter in `list_cases` API and database repository
- **Severity:** Low
- **Category:** API Completeness & Analyst Usability
- **Root Cause:** The frontend `CasesView.tsx` provided a search bar allowing analysts to filter by title, case ID, or correlation key. While client-side filtering functioned, the backend `list_cases()` API and repository only accepted `status`, `severity`, and `correlation_key_type`, ignoring the `search` query parameter.
- **Impact:** Inability to perform server-side paginated search across large case volumes.
- **Evidence:** `GET /api/cases?search=bob` returned all cases without server-side filtering.
- **Resolution:** Added `search: Optional[str] = None` to `IngestionRepository.list_cases()` using parameterized SQL:
  ```python
  if search and search.strip():
      like_term = f"%{search.strip()}%"
      where_clauses.append("(title LIKE ? OR case_id LIKE ? OR correlation_key_value LIKE ?)")
      params.extend([like_term, like_term, like_term])
  ```
  Updated `SentinelRequestHandler.do_GET()` to extract and pass `search` from query parameters.
- **Regression Verification:** Added `test_list_cases_search_filter` in `tests/unit/test_cases_audit.py`. Confirmed exact matching across title, case ID, and correlation key value.

---

## Audit Defect Summary
- **Total Defects Identified:** 5
- **Critical:** 0
- **High:** 0
- **Medium:** 1 (`DEF-CASE-001`)
- **Low:** 4 (`DEF-CASE-002`, `DEF-CASE-003`, `DEF-CASE-004`, `DEF-CASE-005`)
- **Total Resolved:** 5 (100%)
- **Targeted Audit Tests Added:** 9 (`tests/unit/test_cases_audit.py`)
- **Total Backend Regression Tests:** 137 / 137 Passing (100%)

