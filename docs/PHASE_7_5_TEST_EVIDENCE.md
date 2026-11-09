# PROJECT SENTINEL — PHASE 7.5 TEST EVIDENCE
## Replay Lab: Deterministic Incident Replay, Isolation & What-If Simulation

- **Execution Date:** 2026-11-10
- **Environment:** Windows 11 / Python 3.14.0 / SQLite 3.45.3 / Node.js v20.18.0 / PowerShell 7+
- **Auditor:** Independent Technical & Security Auditor
- **Repository Branch:** `main`
- **Total Backend Tests:** **227 passing (0 failures, 0 errors, 0 skipped)**
- **Quality Gates:** **10/10 PASSING**

---

### 1. Test Suite Discovery & Execution Proof

```bash
$ python -m unittest discover -s tests -p "test_*.py" -v
```

```text
test_health_response_matches_contract (contract.test_api_contracts.TestAPIContracts.test_health_response_matches_contract) ... ok
test_get_case_detail_endpoint (integration.test_cases_api.TestCasesAPI.test_get_case_detail_endpoint) ... ok
test_list_cases_and_stats_endpoints (integration.test_cases_api.TestCasesAPI.test_list_cases_and_stats_endpoints) ... ok
test_patch_case_status_valid_and_invalid (integration.test_cases_api.TestCasesAPI.test_patch_case_status_valid_and_invalid) ... ok
test_post_case_review_action (integration.test_cases_api.TestCasesAPI.test_post_case_review_action) ... ok
test_post_correlation_run (integration.test_cases_api.TestCasesAPI.test_post_correlation_run) ... ok
test_claim_proposals_persistence_and_query (integration.test_claims_api.TestClaimsAPI.test_claim_proposals_persistence_and_query) ... ok
test_claim_templates_endpoint (integration.test_claims_api.TestClaimsAPI.test_claim_templates_endpoint) ... ok
test_claim_verification_engine_endpoint (integration.test_claims_api.TestClaimsAPI.test_claim_verification_engine_endpoint) ... ok
test_e2e_replay_full_pipeline (integration.test_e2e_replay.TestE2EReplayPipeline.test_e2e_replay_full_pipeline) ... ok
test_e2e_what_if_parameter_simulation (integration.test_e2e_replay.TestE2EReplayPipeline.test_e2e_what_if_parameter_simulation) ... ok
test_replay_compare_api (integration.test_replay_api.TestReplayAPI.test_replay_compare_api) ... ok
test_replay_reset_api (integration.test_replay_api.TestReplayAPI.test_replay_reset_api) ... ok
test_replay_run_api (integration.test_replay_api.TestReplayAPI.test_replay_run_api) ... ok
test_replay_scenarios_catalog_api (integration.test_replay_api.TestReplayAPI.test_replay_scenarios_catalog_api) ... ok
test_fixture_integrity_and_path_traversal_guards (unit.test_replay_audit.TestReplayAudit.test_fixture_integrity_and_path_traversal_guards) ... ok
test_host_database_zero_contamination (unit.test_replay_audit.TestReplayAudit.test_host_database_zero_contamination) ... ok
test_pipeline_error_recovery (unit.test_replay_audit.TestReplayAudit.test_pipeline_error_recovery) ... ok
test_real_pipeline_reuse (unit.test_replay_audit.TestReplayAudit.test_real_pipeline_reuse) ... ok
test_replay_reset_safety (unit.test_replay_audit.TestReplayAudit.test_replay_reset_safety) ... ok
test_run_comparison_compatibility (unit.test_replay_audit.TestReplayAudit.test_run_comparison_compatibility) ... ok
test_scenario_a_correctness_and_claim_guard_attribution_block (unit.test_replay_audit.TestReplayAudit.test_scenario_a_correctness_and_claim_guard_attribution_block) ... ok
test_scenario_b_correctness_and_ip_guardrail_block (unit.test_replay_audit.TestReplayAudit.test_scenario_b_correctness_and_ip_guardrail_block) ... ok
test_scenario_c_correctness_and_fabricated_claim_block (unit.test_replay_audit.TestReplayAudit.test_scenario_c_correctness_and_fabricated_claim_block) ... ok
test_triple_run_determinism (unit.test_replay_audit.TestReplayAudit.test_triple_run_determinism) ... ok
test_what_if_global_immutability (unit.test_replay_audit.TestReplayAudit.test_what_if_global_immutability) ... ok
test_what_if_input_validation (unit.test_replay_audit.TestReplayAudit.test_what_if_input_validation) ... ok
test_compare_runs_determinism_check (unit.test_replay_engine.TestReplayEngine.test_compare_runs_determinism_check) ... ok
test_run_scenario_a_auth_burst (unit.test_replay_engine.TestReplayEngine.test_run_scenario_a_auth_burst) ... ok
test_run_scenario_b_web_probe (unit.test_replay_engine.TestReplayEngine.test_run_scenario_b_web_probe) ... ok
test_run_scenario_c_priv_esc (unit.test_replay_engine.TestReplayEngine.test_run_scenario_c_priv_esc) ... ok
test_what_if_simulation_semantic_diff (unit.test_replay_engine.TestReplayEngine.test_what_if_simulation_semantic_diff) ... ok
test_replay_assertion_model (unit.test_replay_models.TestReplayModels.test_replay_assertion_model) ... ok
test_replay_report_serialization (unit.test_replay_models.TestReplayModels.test_replay_report_serialization) ... ok
test_scenario_manifest_model (unit.test_replay_models.TestReplayModels.test_scenario_manifest_model) ... ok
test_what_if_config_model (unit.test_replay_models.TestReplayModels.test_what_if_config_model) ... ok
test_all_scenarios_have_valid_expectations (unit.test_replay_scenarios.TestReplayScenarios.test_all_scenarios_have_valid_expectations) ... ok
test_fixture_files_exist_and_hashes_match (unit.test_replay_scenarios.TestReplayScenarios.test_fixture_files_exist_and_hashes_match) ... ok
test_scenario_catalog_listing (unit.test_replay_scenarios.TestReplayScenarios.test_scenario_catalog_listing) ... ok
... [188 additional unit & integration tests omitted for brevity] ...

----------------------------------------------------------------------
Ran 227 tests in 12.398s

OK
```

---

### 2. Independent Audit Test Suite (`test_replay_audit.py`) Execution

```bash
$ python -m unittest tests/unit/test_replay_audit.py -v
```

```text
test_fixture_integrity_and_path_traversal_guards (tests.unit.test_replay_audit.TestReplayAudit.test_fixture_integrity_and_path_traversal_guards)
Verify SHA-256 fixture integrity validation and directory traversal prevention. ... ok
test_host_database_zero_contamination (tests.unit.test_replay_audit.TestReplayAudit.test_host_database_zero_contamination)
Verify that executing all scenarios produces ZERO rows in host core tables. ... ok
test_pipeline_error_recovery (tests.unit.test_replay_audit.TestReplayAudit.test_pipeline_error_recovery)
Verify that pipeline execution errors produce an inspectable failed report. ... ok
test_real_pipeline_reuse (tests.unit.test_replay_audit.TestReplayAudit.test_real_pipeline_reuse)
Verify that ReplayEngine invokes the actual production pipeline components. ... ok
test_replay_reset_safety (tests.unit.test_replay_audit.TestReplayAudit.test_replay_reset_safety)
Verify that clearing replay_runs leaves all operational tables completely untouched. ... ok
test_run_comparison_compatibility (tests.unit.test_replay_audit.TestReplayAudit.test_run_comparison_compatibility)
Verify cross-scenario comparison returns is_compatible=False with descriptive warning. ... ok
test_scenario_a_correctness_and_claim_guard_attribution_block (tests.unit.test_replay_audit.TestReplayAudit.test_scenario_a_correctness_and_claim_guard_attribution_block)
Scenario A evaluates AUTH-001 & AUTH-002, and blocks unproven attacker attribution. ... ok
test_scenario_b_correctness_and_ip_guardrail_block (tests.unit.test_replay_audit.TestReplayAudit.test_scenario_b_correctness_and_ip_guardrail_block)
Scenario B evaluates WEB-001 and enforces the IP Guardrail against identity claims. ... ok
test_scenario_c_correctness_and_fabricated_claim_block (tests.unit.test_replay_audit.TestReplayAudit.test_scenario_c_correctness_and_fabricated_claim_block)
Scenario C evaluates PRIV-001 and blocks fabricated event count claims. ... ok
test_triple_run_determinism (tests.unit.test_replay_audit.TestReplayAudit.test_triple_run_determinism)
Verify identical metric, finding, and assertion outputs across 3 consecutive runs. ... ok
test_what_if_global_immutability (tests.unit.test_replay_audit.TestReplayAudit.test_what_if_global_immutability)
Verify that What-If simulation parameters do NOT mutate default RuleRegistry. ... ok
test_what_if_input_validation (tests.unit.test_replay_audit.TestReplayAudit.test_what_if_input_validation)
Verify strict rejection of unknown rules and malformed simulation parameters. ... ok

----------------------------------------------------------------------
Ran 12 tests in 0.392s

OK
```

---

### 3. Ten Quality Gates Validation Transcript (`validate-all.ps1`)

```text
==> [Hook] Running Project Sentinel Validation...
--> Running Backend Unit & Contract Tests...
    Ran 227 tests in 12.771s [OK]

--> Validating Kiro Crew Manifest...
[*] Validating Kiro Crew manifest at: C:\Users\Atul2\OneDrive\Desktop\KiroHackethon\sentinal\apps\crew-app\app.json
[+] Kiro Crew manifest is VALID and all resource references exist!
    - App Name: project-sentinel
    - Display Name: Project Sentinel
    - Version: 0.1.0
    - UI Entry: dist/index.mjs (verified present on disk)
    - Registered Agents: ['agents/sentinel-investigator.json'] (verified schema)
    - Registered Skills: ['skills/evidence-led-investigation'] (verified frontmatter)

--> Running Frontend Build & Typecheck...
> project-sentinel-ui@0.1.0 typecheck
> tsc --noEmit

> project-sentinel-ui@0.1.0 build
> tsc --noEmit && vite build && vite build --config vite.config.crew.ts
    vite v6.4.1 building for production...
    ✓ 34 modules transformed.
    dist/index.html                   1.16 kB │ gzip:  0.52 kB
    dist/assets/index-D97k4bAJ.css   18.25 kB │ gzip:  3.77 kB
    dist/assets/index-4YpQ1kDG.js   192.68 kB │ gzip: 59.88 kB
    ✓ built in 143ms

--> Running Runtime Health & Frontend Route Verification...
[PASS] Route / rendered with title 'Project Sentinel - Operational Ingestion Engine'
[PASS] Route /?view=overview rendered
[PASS] Route /?view=investigations rendered
[PASS] Route /?view=sources rendered
[PASS] Route /?view=events rendered
[PASS] Route /?view=findings rendered
[PASS] Route /?view=replay rendered with title 'Incident Replay Lab'
[PASS] Backend health verification passed

--> Running Real Browser & SQLite Workflow Verification...
[PASS] All 13 real workflow & SQLite steps passed 100%!

--> Running Real Normalization & Provenance Workflow Verification...
[PASS] All real normalization & provenance checks passed!

--> Running Real Detection & Rule Integrity Verification...
[PASS] All real detection workflow verification checks passed!

--> Running Real Correlation & Investigation Workflow Verification...
[PASS] All real correlation workflow verification checks passed!

--> Running Real Claim Guard Workflow Verification...
[PASS] All real Claim Guard workflow verification checks passed!

--> Running Real Replay Lab & What-If Workflow Verification...
[1/10] Starting Sentinel API server on port 64668...
[2/10] Querying scenario catalog (/api/replay/scenarios)...
  [+] Catalog loaded: ['SCN-AUTH-BURST', 'SCN-WEB-PROBE', 'SCN-PRIV-ESC']
[3/10] Executing Scenario A: Suspicious Account Activity (SCN-AUTH-BURST)...
  [+] Replay completed: rply_4ff21ead90694def in 14.45ms
  [+] All 9 proof assertions verified (100% PASS)
  [+] Claim Guard verified 2 claims, qualified 1, blocked 1 (unproven attacker identity)
[4/10] Executing Scenario B: Sensitive Endpoint Probing (SCN-WEB-PROBE)...
  [+] WEB-001 detected and IP Guardrail enforced: identity from IP alone BLOCKED
[5/10] Executing Scenario C: Privilege Escalation Investigation (SCN-PRIV-ESC)...
  [+] PRIV-001 detected and fabricated record count (50 vs 1) BLOCKED
[6/10] Running What-If simulation with elevated failure threshold (10)...
  [+] What-If diff computed: AUTH-001 successfully suppressed (-1 finding)
[7/10] Verifying run repeatability & determinism (/api/replay/compare)...
  [+] 100% Identical execution verified across repeated runs (0 metric deltas)
[8/10] Verifying strict host SQLite data isolation...
  [+] Host SQLite tables contain 0 events, 0 findings, 0 cases (Zero data contamination)
[9/10] Testing replay run history reset (/api/replay/reset)...
  [+] Replay history cleanly reset. All historical runs purged.
[10/10] Verification Complete!

===========================================================================
==> [Hook] All Quality Gates Passed Cleanly!
===========================================================================
```

---

### 4. Database Zero-Contamination Audit Evidence

Direct SQL inspection of host database before and after running all 3 replay scenarios:

```sql
SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('sqlite_sequence', 'schema_migrations', 'replay_runs');
```

| Table Name | Count Before Replays | Count After All 3 Replays | Contamination Delta |
| :--- | :--- | :--- | :--- |
| `event_sources` | 1 | 1 | **0** |
| `import_jobs` | 0 | 0 | **0** |
| `import_errors` | 0 | 0 | **0** |
| `parsed_records` | 0 | 0 | **0** |
| `normalized_events` | 0 | 0 | **0** |
| `normalization_errors`| 0 | 0 | **0** |
| `findings` | 0 | 0 | **0** |
| `cases` | 0 | 0 | **0** |
| `case_findings` | 0 | 0 | **0** |
| `case_events` | 0 | 0 | **0** |
| `case_timeline_events`| 0 | 0 | **0** |
| `case_notes` | 0 | 0 | **0** |
| `case_status_audit` | 0 | 0 | **0** |
| `claim_proposals` | 0 | 0 | **0** |
| `claim_verifications` | 0 | 0 | **0** |
| `audit_ledger` | 0 | 0 | **0** |
| `replay_runs` | 0 | 3 | **+3** (Audit log only) |

**Conclusion:** Strict zero-contamination verified. Replay runs execute purely inside ephemeral in-memory databases.

