# PROJECT SENTINEL — PHASE 7.5 DEFECT LOG
## Replay Lab: Deterministic Incident Replay, Isolation & What-If Simulation

- **Audit Date:** 2026-11-10
- **Auditor:** Independent Principal Security Architect & QA Auditor
- **Target Phase:** Phase 7 (Replay Lab)
- **Status:** REMEDIATED & VERIFIED

---

### Defect Summary Table

| Defect ID | Title | Severity | Impact | Status | Remediation File |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **DEFECT-7.5-01** | Windows CRLF Line Ending Fixture Hash Mismatch | **High** | Pre-execution SHA-256 fixture integrity check fails on Windows checkout due to Git `autocrlf` conversion | **RESOLVED** | `.gitattributes`, `fixtures/scenarios/scenario_c_priv_esc.jsonl` |
| **DEFECT-7.5-02** | Unvalidated What-If Overrides & Incompatibility Flags | **Medium** | Unknown rule IDs accepted silently, negative/non-integer thresholds unvalidated, cross-scenario comparisons lacked explicit compatibility flags | **RESOLVED** | `backend/replay/engine.py` |
| **DEFECT-7.5-03** | Missing Path Traversal Guard in `get_fixture_path` | **Medium** | Path concatenation allowed potential directory traversal outside `fixtures/scenarios` | **RESOLVED** | `backend/replay/scenarios.py` |

---

### Detailed Defect Reports

#### DEFECT-7.5-01: Windows CRLF Line Ending Fixture Hash Mismatch
- **Severity:** High
- **Component:** Fixture Storage & Checksum Verification (`fixtures/scenarios/`, `backend/replay/engine.py`)
- **Discovery Method:** Initial execution of Scenario C pre-flight integrity check on Windows test environment.
- **Root Cause:**
  When checking out repository files on Windows with Git default `core.autocrlf = true`, line endings in `fixtures/scenarios/scenario_c_priv_esc.jsonl` were automatically transformed from LF (`\n`) to CRLF (`\r\n`). This increased file size from 580 to 583 bytes and altered the SHA-256 hash from `f4ffffdb030c764bf938464bba8748ad62fbf8e825ce59f7fb2972ab98163066` to `76beba...`, causing `ReplayEngine.run_scenario()` to abort with `ValueError: Integrity check failed for fixture 'scenario_c_priv_esc.jsonl'`.
- **Reproduction:**
  Clone repository on Windows without `.gitattributes`. Run `python -c "from backend.replay.engine import ReplayEngine; ReplayEngine().run_scenario('SCN-PRIV-ESC')"`.
- **Remediation:**
  1. Created repository `.gitattributes` enforcing explicit LF line endings:
     ```gitattributes
     fixtures/scenarios/* text eol=lf
     ```
  2. Restored `scenario_c_priv_esc.jsonl` to exact 580-byte binary LF format matching hash `f4ffffdb030c764bf938464bba8748ad62fbf8e825ce59f7fb2972ab98163066`.
- **Verification:** Verified that `ReplayEngine.run_scenario("SCN-PRIV-ESC")` passes fixture integrity validation cleanly across environments.

---

#### DEFECT-7.5-02: Unvalidated What-If Overrides & Missing Incompatibility Flag
- **Severity:** Medium
- **Component:** What-If Simulation Engine (`backend/replay/engine.py`)
- **Discovery Method:** Code audit and adversarial testing of `run_what_if` and `compare_runs`.
- **Root Cause:**
  1. In `ReplayEngine.run_scenario`, when `what_if.rule_overrides` was passed, unknown rule IDs (e.g. `INVALID-999`) were silently ignored instead of raising a clear validation error.
  2. Rule threshold overrides did not validate types or bounds, permitting negative counts (e.g. `threshold_count: -5`) or non-integer values.
  3. `excluded_records` accepted arbitrary indices without checking that lines were positive 1-based integers.
  4. In `compare_runs`, comparing two runs from differing scenarios (e.g. `SCN-AUTH-BURST` vs `SCN-WEB-PROBE`) returned metric deltas without an explicit `is_compatible: false` boolean and `compatibility_warning`.
- **Reproduction:**
  Pass `WhatIfConfig(rule_overrides={"UNKNOWN-RULE": {"threshold_count": 10}})` or compare run A and run B of different scenarios.
- **Remediation:**
  1. Implemented `ReplayEngine._validate_what_if_config(what_if)` validating:
     - Rule IDs against the approved registry set `{"AUTH-001", "AUTH-002", "WEB-001", "PRIV-001", "INGEST-001"}`.
     - `threshold_count` must be integer $\ge 1$.
     - `window_seconds` must be integer $\ge 1$.
     - `excluded_records` must be positive integers $\ge 1$ (deduplicated).
     - `correlation_overrides` window seconds must be integer $\ge 1$.
  2. In `compare_runs`, added:
     - `"is_compatible": is_compatible`
     - `"compatibility_warning": compatibility_warning`
- **Verification:**
  Covered by `tests/unit/test_replay_audit.py` (`test_what_if_input_validation` and `test_run_comparison_compatibility`).

---

#### DEFECT-7.5-03: Missing Path Traversal Guard in `get_fixture_path`
- **Severity:** Medium
- **Component:** Fixture Resolution Utility (`backend/replay/scenarios.py`)
- **Discovery Method:** Security audit of input path handling.
- **Root Cause:**
  `get_fixture_path(filename)` concatenated `FIXTURES_DIR / filename` directly. If an untrusted caller passed `../../secret.txt`, the path resolved outside `fixtures/scenarios/`.
- **Reproduction:**
  Call `get_fixture_path("../../requirements.txt")`. Prior to fix, resolved to repository root `requirements.txt`.
- **Remediation:**
  Added directory containment assertion using `Path.resolve()`:
  ```python
  def get_fixture_path(filename: str) -> Path:
      resolved_fixtures_dir = FIXTURES_DIR.resolve()
      p = (resolved_fixtures_dir / filename).resolve()
      if not str(p).startswith(str(resolved_fixtures_dir)):
          raise ValueError(f"Path traversal detected in fixture path: {filename}")
      if not p.exists() or not p.is_file():
          raise FileNotFoundError(f"Scenario fixture '{filename}' not found at {p}")
      return p
  ```
- **Verification:**
  Covered by `test_fixture_integrity_and_path_traversal_guards` in `tests/unit/test_replay_audit.py`.

---

### Audit Conclusion on Defects
All 3 identified defects have been remediated with production-grade fixes and verified by automated unit tests. Zero unresolved defects remain in Phase 7.

