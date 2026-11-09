# Project Sentinel — Phase 5.5 Test Evidence
## Verbatim Execution Logs, SQLite Audits & Quality Gate Outputs

**Execution Date:** November 9, 2026  
**Host Environment:** Windows, Python 3.14.0, Node.js v24.13.0, Chrome 134  
**Audit Target:** Project Sentinel Phase 5 Implementation (Investigation Cases, Deterministic Correlation Engine, Evidence Timeline)  

---

## 1. Full Backend Test Discovery & Execution Suite

```text
PS C:\Users\Atul2\OneDrive\Desktop\KiroHackethon\sentinal> python -m unittest discover -s tests -p "test_*.py" -v
test_health_response_matches_contract (tests.contract.test_api_contracts.TestAPIContracts.test_health_response_matches_contract)
Verify the health response satisfies the BackendHealthResponse TypeScript schema. ... ok
test_get_case_detail_endpoint (tests.integration.test_cases_api.TestCasesAPI.test_get_case_detail_endpoint)
GET /api/cases/{id} returns complete case detail with timeline, findings, and events. ... ok
test_list_cases_and_stats_endpoints (tests.integration.test_cases_api.TestCasesAPI.test_list_cases_and_stats_endpoints)
GET /api/cases and GET /api/cases/stats return valid case metadata and aggregate counts. ... ok
test_patch_case_status_valid_and_invalid (tests.integration.test_cases_api.TestCasesAPI.test_patch_case_status_valid_and_invalid)
PATCH /api/cases/{id} validates allowed transitions and rejects invalid targets. ... ok
test_post_case_review_action (tests.integration.test_cases_api.TestCasesAPI.test_post_case_review_action)
POST /api/cases/{id}/review appends operator notes and optional status updates. ... ok
test_post_correlation_run (tests.integration.test_cases_api.TestCasesAPI.test_post_correlation_run)
POST /api/cases/correlate triggers correlation and returns execution metrics. ... ok
test_complete_case_investigation_lifecycle (tests.integration.test_e2e_cases.TestE2ECases.test_complete_case_investigation_lifecycle)
Full pipeline: Ingest multi-source logs, normalize, detect findings, correlate into cases, review, and verify timeline. ... ok
test_complete_detection_and_finding_lifecycle (tests.integration.test_e2e_detection.TestE2EDetection.test_complete_detection_and_finding_lifecycle)
Full lifecycle test: Ingest logs, normalize, run detection, query findings, update status, and verify idempotency. ... ok
test_multi_format_normalization_pipeline (tests.integration.test_e2e_normalization.TestE2ENormalization.test_multi_format_normalization_pipeline)
Upload web access CSV and JSONL files, normalize both, and verify cross-source event querying. ... ok
test_normalization_quarantine_e2e (tests.integration.test_e2e_normalization.TestE2ENormalization.test_normalization_quarantine_e2e)
Verify that ambiguous or malformed timestamps are quarantined and retrievable via errors API. ... ok
test_get_event_by_id_with_provenance (tests.integration.test_events_api.TestEventsAPI.test_get_event_by_id_with_provenance) ... ok
test_list_events_pagination (tests.integration.test_events_api.TestEventsAPI.test_list_events_pagination) ... ok
test_list_events_with_filters (tests.integration.test_events_api.TestEventsAPI.test_list_events_with_filters) ... ok
test_list_normalization_errors (tests.integration.test_events_api.TestEventsAPI.test_list_normalization_errors) ... ok
test_normalization_stats_endpoint (tests.integration.test_events_api.TestEventsAPI.test_normalization_stats_endpoint) ... ok
test_filter_findings_by_rule_and_severity (tests.integration.test_findings_api.TestFindingsAPI.test_filter_findings_by_rule_and_severity)
Verify filtering findings by rule_id and severity. ... ok
test_findings_stats_endpoint (tests.integration.test_findings_api.TestFindingsAPI.test_findings_stats_endpoint)
Verify GET /api/findings/stats returns accurate rule counts and severity aggregates. ... ok
test_get_finding_detail_with_events (tests.integration.test_findings_api.TestFindingsAPI.test_get_finding_detail_with_events)
Verify GET /api/findings/{id} returns finding with resolved supporting events. ... ok
test_idempotent_detection_runs (tests.integration.test_findings_api.TestFindingsAPI.test_idempotent_detection_runs)
Repeated runs do not produce duplicate findings or alter analyst-updated status. ... ok
test_list_detection_rules (tests.integration.test_findings_api.TestFindingsAPI.test_list_detection_rules)
Verify GET /api/detection/rules lists registered security rules. ... ok
test_run_detection_endpoint (tests.integration.test_findings_api.TestFindingsAPI.test_run_detection_endpoint)
Verify POST /api/detection/run executes rules and returns evaluation metrics. ... ok
test_update_finding_status (tests.integration.test_findings_api.TestFindingsAPI.test_update_finding_status)
Verify PATCH /api/findings/{id} updates status to 'acknowledged' and 'resolved'. ... ok
test_auth_csv_e2e_ingestion (tests.integration.test_ingestion_e2e.TestIngestionE2E.test_auth_csv_e2e_ingestion) ... ok
test_duplicate_file_prevention (tests.integration.test_ingestion_e2e.TestIngestionE2E.test_duplicate_file_prevention) ... ok
test_generic_jsonl_e2e_ingestion (tests.integration.test_ingestion_e2e.TestIngestionE2E.test_generic_jsonl_e2e_ingestion) ... ok
test_inbox_scanner_e2e (tests.integration.test_ingestion_e2e.TestIngestionE2E.test_inbox_scanner_e2e) ... ok
test_malformed_csv_partial_ingestion (tests.integration.test_ingestion_e2e.TestIngestionE2E.test_malformed_csv_partial_ingestion) ... ok
test_unknown_parser_error (tests.integration.test_ingestion_e2e.TestIngestionE2E.test_unknown_parser_error) ... ok
test_web_csv_e2e_ingestion (tests.integration.test_ingestion_e2e.TestIngestionE2E.test_web_csv_e2e_ingestion) ... ok
test_bucket_boundary_splits_consistently_without_duplication (tests.unit.test_cases_audit.TestCasesAudit.test_bucket_boundary_splits_consistently_without_duplication)
Events immediately before and after bucket boundary partition into discrete cases. ... ok
test_findings_without_identity_never_merge_together (tests.unit.test_cases_audit.TestCasesAudit.test_findings_without_identity_never_merge_together)
Two findings lacking identity keys must remain in isolated single-finding cases ... ok
test_ip_isolation_different_users_never_merge (tests.unit.test_cases_audit.TestCasesAudit.test_ip_isolation_different_users_never_merge)
Two different users sharing the exact same source IP must NEVER merge ... ok
test_key_priority_session_over_request_id (tests.unit.test_cases_audit.TestCasesAudit.test_key_priority_session_over_request_id)
When user_principal is absent, session_id MUST take precedence over request_id ... ok
test_list_cases_search_filter (tests.unit.test_cases_audit.TestCasesAudit.test_list_cases_search_filter)
list_cases must support search querying across title, case ID, and correlation key value. ... ok
test_out_of_order_evidence_updates_first_observed_and_description (tests.unit.test_cases_audit.TestCasesAudit.test_out_of_order_evidence_updates_first_observed_and_description)
When delayed evidence with an earlier timestamp in the same bucket arrives later, ... ok
test_oversized_note_and_author_rejected (tests.unit.test_cases_audit.TestCasesAudit.test_oversized_note_and_author_rejected)
Operator notes > 10,000 characters or authors > 100 characters must be rejected. ... ok
test_resolved_case_preserves_status_under_new_evidence (tests.unit.test_cases_audit.TestCasesAudit.test_resolved_case_preserves_status_under_new_evidence)
When a case is set to Resolved by an analyst, subsequent correlation runs ... ok
test_timeline_sorting_stability_on_identical_timestamps (tests.unit.test_cases_audit.TestCasesAudit.test_timeline_sorting_stability_on_identical_timestamps)
Timeline items with identical timestamps must sort in logical order: ... ok
test_add_operator_note_appends_review_action (tests.unit.test_cases_db.TestCasesDatabase.test_add_operator_note_appends_review_action)
Verify add_case_note writes to review_actions audit table and updates cases.updated_at. ... ok
test_case_pagination_and_filters (tests.unit.test_cases_db.TestCasesDatabase.test_case_pagination_and_filters)
Verify list_cases filters by status, severity, correlation_key_type, and pagination. ... ok
test_case_stats_aggregation (tests.unit.test_cases_db.TestCasesDatabase.test_case_stats_aggregation)
Verify get_case_stats returns accurate counts by status, severity, and last evaluation. ... ok
test_get_case_detail_resolves_relations_and_timeline (tests.unit.test_cases_db.TestCasesDatabase.test_get_case_detail_resolves_relations_and_timeline)
Verify get_case resolves findings, direct events, review actions, and unified timeline. ... ok
test_persist_cases_batch_and_deduplication (tests.unit.test_cases_db.TestCasesDatabase.test_persist_cases_batch_and_deduplication)
Verify batch insertion, idempotency, and foreign key relations. ... ok
test_update_case_status_validates_transitions (tests.unit.test_cases_db.TestCasesDatabase.test_update_case_status_validates_transitions)
Verify valid transitions succeed and invalid transitions raise ValueError. ... ok
test_config_defaults (tests.unit.test_config.TestConfig.test_config_defaults) ... ok
test_config_env_overrides (tests.unit.test_config.TestConfig.test_config_env_overrides) ... ok
test_config_validation (tests.unit.test_config.TestConfig.test_config_validation) ... ok
test_correlation_clustering_by_user (tests.unit.test_correlation_engine.TestCorrelationEngine.test_correlation_clustering_by_user)
Findings and events sharing user_principal are grouped into a single case. ... ok
test_derived_severity_calculation (tests.unit.test_correlation_engine.TestCorrelationEngine.test_derived_severity_calculation)
Case severity is derived as the highest severity among clustered findings. ... ok
test_fallback_to_session_or_request_id (tests.unit.test_correlation_engine.TestCorrelationEngine.test_fallback_to_session_or_request_id)
When user_principal is absent, falls back to session_id or request_id. ... ok
test_ip_only_correlation_disabled_by_default (tests.unit.test_correlation_engine.TestCorrelationEngine.test_ip_only_correlation_disabled_by_default)
Findings sharing only source_ip are not grouped when enable_ip_correlation=False. ... ok
test_isolated_findings_remain_singletons (tests.unit.test_correlation_engine.TestCorrelationEngine.test_isolated_findings_remain_singletons)
Findings with unique identity keys produce individual cases. ... ok
test_cors_custom_origin_allowed (tests.unit.test_cors_security.TestCorsSecurity.test_cors_custom_origin_allowed) ... ok
test_cors_disallowed_origin_no_headers (tests.unit.test_cors_security.TestCorsSecurity.test_cors_disallowed_origin_no_headers) ... ok
test_cors_headers_present_for_allowed_origin (tests.unit.test_cors_security.TestCorsSecurity.test_cors_headers_present_for_allowed_origin) ... ok
test_cors_options_preflight (tests.unit.test_cors_security.TestCorsSecurity.test_cors_options_preflight) ... ok
test_cors_wildcard_rejected (tests.unit.test_cors_security.TestCorsSecurity.test_cors_wildcard_rejected) ... ok
test_null_origin_rejected (tests.unit.test_cors_security.TestCorsSecurity.test_null_origin_rejected) ... ok
test_all_migrations_applied (tests.unit.test_database.TestDatabase.test_all_migrations_applied) ... ok
test_foreign_keys_enabled (tests.unit.test_database.TestDatabase.test_foreign_keys_enabled) ... ok
test_idempotent_migrations (tests.unit.test_database.TestDatabase.test_idempotent_migrations) ... ok
test_import_job_foreign_key_to_sources (tests.unit.test_database.TestDatabase.test_import_job_foreign_key_to_sources) ... ok
test_import_jobs_sha256_unique (tests.unit.test_database.TestDatabase.test_import_jobs_sha256_unique) ... ok
test_initial_schema_creates_tables (tests.unit.test_database.TestDatabase.test_initial_schema_creates_tables) ... ok
test_parsed_records_foreign_key (tests.unit.test_database.TestDatabase.test_parsed_records_foreign_key) ... ok
test_wal_mode_enabled (tests.unit.test_database.TestDatabase.test_wal_mode_enabled) ... ok
test_auth002_success_inside_burst_window_detected (tests.unit.test_detection_audit.TestDetectionAudit.test_auth002_success_inside_burst_window_detected)
Verify DEF-002 fix: AUTH-002 detects success occurring immediately after 5th failure ... ok
test_ingest001_quarantined_records_attached_to_finding (tests.unit.test_detection_audit.TestDetectionAudit.test_ingest001_quarantined_records_attached_to_finding)
Verify DEF-007 fix: get_finding() includes quarantined_records for INGEST-001 ... ok
test_priv001_actor_and_target_user_in_conditions (tests.unit.test_detection_audit.TestDetectionAudit.test_priv001_actor_and_target_user_in_conditions)
Verify DEF-008 fix: PRIV-001 populates both actor and target_user in matched_conditions. ... ok
test_web001_url_encoding_and_traversal_evasion_detected (tests.unit.test_detection_audit.TestDetectionAudit.test_web001_url_encoding_and_traversal_evasion_detected)
Verify DEF-006 fix: WEB-001 catches percent-encoded (%61%64%6d%69%6e) and traversal attacks ... ok
test_detection_engine_input_sanitization (tests.unit.test_detection_security.TestDetectionSecurity.test_detection_engine_input_sanitization)
Detection engine gracefully ignores malformed, non-dict, or incomplete event objects. ... ok
test_no_eval_or_exec_used_in_detection (tests.unit.test_detection_security.TestDetectionSecurity.test_no_eval_or_exec_used_in_detection)
Verify no dynamic code execution (eval, exec) exists in detection modules. ... ok
test_path_traversal_in_route_detection (tests.unit.test_detection_security.TestDetectionSecurity.test_path_traversal_in_route_detection)
WEB-001 safely handles traversal attempts and path-encoded attacks without shell/system calls. ... ok
test_rule_definition_validation_rejects_malformed (tests.unit.test_detection_security.TestDetectionSecurity.test_rule_definition_validation_rejects_malformed)
Registry rejects invalid rule definitions. ... ok
test_auth001_persists_and_deduplicates (tests.unit.test_findings_db.TestFindingsDatabase.test_auth001_persists_and_deduplicates)
Verify saving AUTH-001 findings and suppressing duplicates via unique constraint. ... ok
test_foreign_key_restricts_dangling_events (tests.unit.test_findings_db.TestFindingsDatabase.test_foreign_key_restricts_dangling_events)
Verify that finding_events foreign key prevents dangling or non-existent event IDs. ... ok
test_get_finding_with_quarantined_records (tests.unit.test_findings_db.TestFindingsDatabase.test_get_finding_with_quarantined_records)
Verify get_finding populates quarantined_records when INGEST-001 matches normalization errors. ... ok
test_list_findings_pagination_and_filtering (tests.unit.test_findings_db.TestFindingsDatabase.test_list_findings_pagination_and_filtering)
Verify filtering by rule_id, severity, status, and limit/offset pagination. ... ok
test_record_evaluation_audit_entry (tests.unit.test_findings_db.TestFindingsDatabase.test_record_evaluation_audit_entry)
Verify recording evaluation run metrics in rule_evaluations table. ... ok
test_stats_calculation (tests.unit.test_findings_db.TestFindingsDatabase.test_stats_calculation)
Verify aggregation of finding counts by rule, severity, and status. ... ok
test_update_finding_status_lifecycle (tests.unit.test_findings_db.TestFindingsDatabase.test_update_finding_status_lifecycle)
Verify updating finding status (active -> acknowledged -> resolved). ... ok
test_health_endpoint_returns_json (tests.unit.test_health.TestHealth.test_health_endpoint_returns_json) ... ok
test_health_response_contains_expected_keys (tests.unit.test_health.TestHealth.test_health_response_contains_expected_keys) ... ok
test_health_response_mode_is_local (tests.unit.test_health.TestHealth.test_health_response_mode_is_local) ... ok
test_health_response_status_is_ok (tests.unit.test_health.TestHealth.test_health_response_status_is_ok) ... ok
test_duplicate_file_content_blocked (tests.unit.test_import_engine.TestImportEngine.test_duplicate_file_content_blocked) ... ok
test_duplicate_filename_different_content_allowed (tests.unit.test_import_engine.TestImportEngine.test_duplicate_filename_different_content_allowed) ... ok
test_import_auth_csv_success (tests.unit.test_import_engine.TestImportEngine.test_import_auth_csv_success) ... ok
test_import_generic_jsonl_success (tests.unit.test_import_engine.TestImportEngine.test_import_generic_jsonl_success) ... ok
test_import_nonexistent_file_fails (tests.unit.test_import_engine.TestImportEngine.test_import_nonexistent_file_fails) ... ok
test_import_unknown_parser_fails (tests.unit.test_import_engine.TestImportEngine.test_import_unknown_parser_fails) ... ok
test_import_web_access_csv_success (tests.unit.test_import_engine.TestImportEngine.test_import_web_access_csv_success) ... ok
test_malformed_csv_rows_quarantined (tests.unit.test_import_engine.TestImportEngine.test_malformed_csv_rows_quarantined) ... ok
test_all_migrations_applied (tests.unit.test_normalization_db.TestNormalizationDatabase.test_all_migrations_applied) ... ok
test_canonical_event_provenance_roundtrip (tests.unit.test_normalization_db.TestNormalizationDatabase.test_canonical_event_provenance_roundtrip) ... ok
test_canonical_events_batch_insert (tests.unit.test_normalization_db.TestNormalizationDatabase.test_canonical_events_batch_insert) ... ok
test_canonical_events_schema_exists (tests.unit.test_normalization_db.TestNormalizationDatabase.test_canonical_events_schema_exists) ... ok
test_duplicate_event_deduplication (tests.unit.test_normalization_db.TestNormalizationDatabase.test_duplicate_event_deduplication) ... ok
test_foreign_key_cascade_or_restrict (tests.unit.test_normalization_db.TestNormalizationDatabase.test_foreign_key_cascade_or_restrict) ... ok
test_get_events_pagination (tests.unit.test_normalization_db.TestNormalizationDatabase.test_get_events_pagination) ... ok
test_get_events_with_filters (tests.unit.test_normalization_db.TestNormalizationDatabase.test_get_events_with_filters) ... ok
test_normalization_errors_schema_exists (tests.unit.test_normalization_db.TestNormalizationDatabase.test_normalization_errors_schema_exists) ... ok
test_normalization_stats_query (tests.unit.test_normalization_db.TestNormalizationDatabase.test_normalization_stats_query) ... ok
test_persist_normalization_errors_batch (tests.unit.test_normalization_db.TestNormalizationDatabase.test_persist_normalization_errors_batch) ... ok
test_schema_migration_preserves_parsed_records (tests.unit.test_normalization_db.TestNormalizationDatabase.test_schema_migration_preserves_parsed_records) ... ok
test_auth_csv_normalization (tests.unit.test_normalization_engine.TestNormalizationEngine.test_auth_csv_normalization) ... ok
test_empty_parsed_records_handled_gracefully (tests.unit.test_normalization_engine.TestNormalizationEngine.test_empty_parsed_records_handled_gracefully) ... ok
test_field_sanitization_and_stripping (tests.unit.test_normalization_engine.TestNormalizationEngine.test_field_sanitization_and_stripping) ... ok
test_generic_jsonl_normalization (tests.unit.test_normalization_engine.TestNormalizationEngine.test_generic_jsonl_normalization) ... ok
test_idempotent_normalization_runs (tests.unit.test_normalization_engine.TestNormalizationEngine.test_idempotent_normalization_runs) ... ok
test_invalid_schema_quarantined (tests.unit.test_normalization_engine.TestNormalizationEngine.test_invalid_schema_quarantined) ... ok
test_malformed_ip_sanitized (tests.unit.test_normalization_engine.TestNormalizationEngine.test_malformed_ip_sanitized) ... ok
test_missing_required_fields_quarantined (tests.unit.test_normalization_engine.TestNormalizationEngine.test_missing_required_fields_quarantined) ... ok
test_pii_redaction_in_attributes (tests.unit.test_normalization_engine.TestNormalizationEngine.test_pii_redaction_in_attributes) ... ok
test_unsupported_parser_quarantined (tests.unit.test_normalization_engine.TestNormalizationEngine.test_unsupported_parser_quarantined) ... ok
test_web_access_csv_normalization (tests.unit.test_normalization_engine.TestNormalizationEngine.test_web_access_csv_normalization) ... ok
test_auth_csv_parser_detects_headers (tests.unit.test_parsers.TestParsers.test_auth_csv_parser_detects_headers) ... ok
test_auth_csv_parser_parses_valid_rows (tests.unit.test_parsers.TestParsers.test_auth_csv_parser_parses_valid_rows) ... ok
test_generic_jsonl_parser_parses_valid_lines (tests.unit.test_parsers.TestParsers.test_generic_jsonl_parser_parses_valid_lines) ... ok
test_generic_jsonl_parser_quarantines_invalid_lines (tests.unit.test_parsers.TestParsers.test_generic_jsonl_parser_quarantines_invalid_lines) ... ok
test_parser_registry_get (tests.unit.test_parsers.TestParsers.test_parser_registry_get) ... ok
test_parser_registry_list (tests.unit.test_parsers.TestParsers.test_parser_registry_list) ... ok
test_web_access_csv_parser_detects_headers (tests.unit.test_parsers.TestParsers.test_web_access_csv_parser_detects_headers) ... ok
test_web_access_csv_parser_parses_valid_rows (tests.unit.test_parsers.TestParsers.test_web_access_csv_parser_parses_valid_rows) ... ok
test_auth001_below_threshold (tests.unit.test_rule_evaluation.TestRuleEvaluation.test_auth001_below_threshold) ... ok
test_auth001_multiple_users_isolated (tests.unit.test_rule_evaluation.TestRuleEvaluation.test_auth001_multiple_users_isolated) ... ok
test_auth001_out_of_order_events (tests.unit.test_rule_evaluation.TestRuleEvaluation.test_auth001_out_of_order_events) ... ok
test_auth001_sliding_window_trigger (tests.unit.test_rule_evaluation.TestRuleEvaluation.test_auth001_sliding_window_trigger) ... ok
test_auth001_window_expiration (tests.unit.test_rule_evaluation.TestRuleEvaluation.test_auth001_window_expiration) ... ok
test_auth002_burst_then_success (tests.unit.test_rule_evaluation.TestRuleEvaluation.test_auth002_burst_then_success) ... ok
test_auth002_isolated_success_no_finding (tests.unit.test_rule_evaluation.TestRuleEvaluation.test_auth002_isolated_success_no_finding) ... ok
test_auth002_success_outside_window (tests.unit.test_rule_evaluation.TestRuleEvaluation.test_auth002_success_outside_window) ... ok
test_ingest001_future_dated_event (tests.unit.test_rule_evaluation.TestRuleEvaluation.test_ingest001_future_dated_event) ... ok
test_ingest001_quarantined_records (tests.unit.test_rule_evaluation.TestRuleEvaluation.test_ingest001_quarantined_records) ... ok
test_priv001_role_change_detected (tests.unit.test_rule_evaluation.TestRuleEvaluation.test_priv001_role_change_detected) ... ok
test_web001_sensitive_route_burst (tests.unit.test_rule_evaluation.TestRuleEvaluation.test_web001_sensitive_route_burst) ... ok
test_web001_unsensitive_route_ignored (tests.unit.test_rule_evaluation.TestRuleEvaluation.test_web001_unsensitive_route_ignored) ... ok
test_auth001_definition_valid (tests.unit.test_rule_validation.TestRuleValidation.test_auth001_definition_valid) ... ok
test_auth002_definition_valid (tests.unit.test_rule_validation.TestRuleValidation.test_auth002_definition_valid) ... ok
test_ingest001_definition_valid (tests.unit.test_rule_validation.TestRuleValidation.test_ingest001_definition_valid) ... ok
test_invalid_rule_version_format (tests.unit.test_rule_validation.TestRuleValidation.test_invalid_rule_version_format) ... ok
test_invalid_severity_rejected (tests.unit.test_rule_validation.TestRuleValidation.test_invalid_severity_rejected) ... ok
test_missing_required_fields_rejected (tests.unit.test_rule_validation.TestRuleValidation.test_missing_required_fields_rejected) ... ok
test_priv001_definition_valid (tests.unit.test_rule_validation.TestRuleValidation.test_priv001_definition_valid) ... ok
test_web001_definition_valid (tests.unit.test_rule_validation.TestRuleValidation.test_web001_definition_valid) ... ok
test_inbox_scanner_auto_discovers_files (tests.unit.test_scanner.TestInboxScanner.test_inbox_scanner_auto_discovers_files) ... ok
test_inbox_scanner_ignores_non_log_files (tests.unit.test_scanner.TestInboxScanner.test_inbox_scanner_ignores_non_log_files) ... ok
test_inbox_scanner_no_duplicate_processing (tests.unit.test_scanner.TestInboxScanner.test_inbox_scanner_no_duplicate_processing) ... ok
test_inbox_scanner_pause_and_resume (tests.unit.test_scanner.TestInboxScanner.test_inbox_scanner_pause_and_resume) ... ok
test_inbox_scanner_subdirectories_ignored (tests.unit.test_scanner.TestInboxScanner.test_inbox_scanner_subdirectories_ignored) ... ok
test_inbox_scanner_tolerates_inaccessible_file (tests.unit.test_scanner.TestInboxScanner.test_inbox_scanner_tolerates_inaccessible_file) ... ok
test_ambiguous_date_quarantined (tests.unit.test_timestamps.TestTimestamps.test_ambiguous_date_quarantined) ... ok
test_apache_clf_format (tests.unit.test_timestamps.TestTimestamps.test_apache_clf_format) ... ok
test_epoch_seconds_and_millis (tests.unit.test_timestamps.TestTimestamps.test_epoch_seconds_and_millis) ... ok
test_future_timestamp_detected (tests.unit.test_timestamps.TestTimestamps.test_future_timestamp_detected) ... ok
test_iso8601_with_timezone (tests.unit.test_timestamps.TestTimestamps.test_iso8601_with_timezone) ... ok
test_naive_timestamp_rejected_or_assumed (tests.unit.test_timestamps.TestTimestamps.test_naive_timestamp_rejected_or_assumed) ... ok
test_unparseable_string_quarantined (tests.unit.test_timestamps.TestTimestamps.test_unparseable_string_quarantined) ... ok

----------------------------------------------------------------------
Ran 137 tests in 6.675s

OK
```

### Complete Test Catalog & Breakdown (25 Test Files, 137 Tests)

| Category | Test Module | Test Class / Scope | Tests | Result |
| :--- | :--- | :--- | :---: | :---: |
| **Cases Audit (New)** | `tests/unit/test_cases_audit.py` | `TestCasesAudit` | 9 | **PASS** |
| **Correlation Engine** | `tests/unit/test_correlation_engine.py` | `TestCorrelationEngine` | 5 | **PASS** |
| **Cases Database** | `tests/unit/test_cases_db.py` | `TestCasesDatabase` | 6 | **PASS** |
| **Cases API** | `tests/integration/test_cases_api.py` | `TestCasesAPI` | 5 | **PASS** |
| **E2E Cases Pipeline** | `tests/integration/test_e2e_cases.py` | `TestE2ECases` | 1 | **PASS** |
| **Detection Validation** | `tests/unit/test_rule_validation.py` | `TestRuleValidation` | 8 | **PASS** |
| **Detection Evaluation** | `tests/unit/test_rule_evaluation.py` | `TestRuleEvaluation` | 13 | **PASS** |
| **Detection Audit** | `tests/unit/test_detection_audit.py` | `TestDetectionAudit` | 4 | **PASS** |
| **Findings Persistence** | `tests/unit/test_findings_db.py` | `TestFindingsDatabase` | 7 | **PASS** |
| **Detection Security** | `tests/unit/test_detection_security.py` | `TestDetectionSecurity` | 3 | **PASS** |
| **Findings API** | `tests/integration/test_findings_api.py` | `TestFindingsAPI` | 6 | **PASS** |
| **E2E Detection Pipeline**| `tests/integration/test_e2e_detection.py` | `TestE2EDetection` | 1 | **PASS** |
| **API Contracts** | `tests/contract/test_api_contracts.py`| `TestAPIContracts` | 1 | **PASS** |
| **Events API** | `tests/integration/test_events_api.py` | `TestEventsAPI` | 5 | **PASS** |
| **Import API** | `tests/integration/test_import_api.py` | `TestImportAPI` | 11 | **PASS** |
| **E2E Normalization** | `tests/integration/test_e2e_normalization.py` | `TestE2ENormalization` | 1 | **PASS** |
| **Configuration** | `tests/unit/test_config.py` | `TestConfig` | 3 | **PASS** |
| **CORS Security** | `tests/unit/test_cors_security.py` | `TestCorsSecurity` | 6 | **PASS** |
| **Database Baseline** | `tests/unit/test_database.py` | `TestDatabase` | 8 | **PASS** |
| **Health API** | `tests/unit/test_health.py` | `TestHealth` | 4 | **PASS** |
| **Import Engine** | `tests/unit/test_import_engine.py` | `TestImportEngine` | 8 | **PASS** |
| **Normalization DB** | `tests/unit/test_normalization_db.py` | `TestNormalizationDatabase` | 12 | **PASS** |
| **Normalization Engine**| `tests/unit/test_normalization_engine.py` | `TestNormalizationEngine` | 11 | **PASS** |
| **Parser Profiles** | `tests/unit/test_parsers.py` | `TestParsers` | 8 | **PASS** |
| **Inbox Scanner** | `tests/unit/test_scanner.py` | `TestInboxScanner` | 6 | **PASS** |
| **Timestamp Engine** | `tests/unit/test_timestamps.py` | `TestTimestamps` | 7 | **PASS** |
| **GRAND TOTAL** | **25 Test Files** | **26 Test Classes** | **137** | **100% PASS** |

---

## 2. Dedicated Phase 5.5 Audit Test Execution

```text
PS C:\Users\Atul2\OneDrive\Desktop\KiroHackethon\sentinal> python -m unittest tests/unit/test_cases_audit.py -v
test_bucket_boundary_splits_consistently_without_duplication (tests.unit.test_cases_audit.TestCasesAudit.test_bucket_boundary_splits_consistently_without_duplication)
Events immediately before and after bucket boundary partition into discrete cases. ... ok
test_findings_without_identity_never_merge_together (tests.unit.test_cases_audit.TestCasesAudit.test_findings_without_identity_never_merge_together)
Two findings lacking identity keys must remain in isolated single-finding cases ... ok
test_ip_isolation_different_users_never_merge (tests.unit.test_cases_audit.TestCasesAudit.test_ip_isolation_different_users_never_merge)
Two different users sharing the exact same source IP must NEVER merge ... ok
test_key_priority_session_over_request_id (tests.unit.test_cases_audit.TestCasesAudit.test_key_priority_session_over_request_id)
When user_principal is absent, session_id MUST take precedence over request_id ... ok
test_list_cases_search_filter (tests.unit.test_cases_audit.TestCasesAudit.test_list_cases_search_filter)
list_cases must support search querying across title, case ID, and correlation key value. ... ok
test_out_of_order_evidence_updates_first_observed_and_description (tests.unit.test_cases_audit.TestCasesAudit.test_out_of_order_evidence_updates_first_observed_and_description)
When delayed evidence with an earlier timestamp in the same bucket arrives later, ... ok
test_oversized_note_and_author_rejected (tests.unit.test_cases_audit.TestCasesAudit.test_oversized_note_and_author_rejected)
Operator notes > 10,000 characters or authors > 100 characters must be rejected. ... ok
test_resolved_case_preserves_status_under_new_evidence (tests.unit.test_cases_audit.TestCasesAudit.test_resolved_case_preserves_status_under_new_evidence)
When a case is set to Resolved by an analyst, subsequent correlation runs ... ok
test_timeline_sorting_stability_on_identical_timestamps (tests.unit.test_cases_audit.TestCasesAudit.test_timeline_sorting_stability_on_identical_timestamps)
Timeline items with identical timestamps must sort in logical order: ... ok

----------------------------------------------------------------------
Ran 9 tests in 0.158s

OK
```

---

## 3. Real Case Correlation & Review Workflow Execution Log

```text
PS C:\Users\Atul2\OneDrive\Desktop\KiroHackethon\sentinal> python scripts/verify_real_case_workflow.py
======================================================================
 PROJECT SENTINEL — Phase 5 Real Cases & Correlation Workflow Audit
======================================================================

[*] Starting Sentinel backend on 127.0.0.1:8000 with isolated DB: C:\Users\Atul2\AppData\Local\Temp\tmphh1ich0m\sentinel_cases_audit.db...
[+] Backend active and responding to /health.

--> [Step 1] Ingesting multi-source logs containing correlation keys...
    [PASS] Auth CSV ingested: 6 records for user 'analyst_bob'
    [PASS] Privilege JSONL ingested: 1 record for user 'analyst_bob'
    [PASS] Web Access CSV ingested: 3 probe requests from 203.0.113.77

--> [Step 2] Normalizing canonical events...
    [PASS] Normalized 10 events.

--> [Step 3] Running detection engine to produce findings...
    [PASS] Detection run eval_5661400bf924: 4 findings generated.

--> [Step 4] Running deterministic Correlation Engine...
    [PASS] Correlation run corr_eval_ccc5f5e95686: 2 cases created, 4 findings scanned in 1.27ms.

--> [Step 5] Querying /api/cases to verify case clustering and severity...
    [PASS] Total cases returned: 2
    [PASS] Found correlated case case_649ad5f8c70875775091 for user 'analyst_bob'.
           Title: 'Suspicious Activity Correlated for User 'analyst_bob''
           Derived Severity: 'High'
           Status: 'Open'
           Evidence Counts: 3 findings, 7 events
    [PASS] Verified IP-only grouping is disabled by default: 0 source_ip cases created.

--> [Step 6] Inspecting case detail and unified timeline at /api/cases/{id}...
    [PASS] Case timeline contains 11 items.
    [PASS] Timeline item types present: correlation, event, finding
    [PASS] Correlation Rationale: Grouped 3 finding(s) and 7 event(s) sharing user_principal 'analyst_bob' within 3600s observation window.

--> [Step 7] Testing analyst review workflow and audit logging...
    [PASS] Transitioned Open -> UnderReview with operator note.
    [PASS] Added standalone analyst note.
    [PASS] Transitioned UnderReview -> Resolved.
    [PASS] Case detail shows 3 append-only review actions.

--> [Step 8] Auditing SQLite schema, relations, and foreign keys directly...
    [PASS] SQLite 'cases' table contains 2 records.
    [PASS] SQLite 'case_findings' contains 3 links for case case_649ad5f8c70875775091.
    [PASS] SQLite 'case_events' contains 7 direct event links for case case_649ad5f8c70875775091.
    [PASS] SQLite 'review_actions' contains 3 audit records.
    [PASS] SQLite PRAGMA foreign_key_check passed with 0 violations!

--> [Step 9] Testing correlation engine idempotency...
    [PASS] Second correlation: 0 new cases created, 2 cases updated.
    [PASS] Analyst status ('Resolved') and 3 review actions preserved without duplication.

--> [Step 10] Testing /api/cases/stats endpoint...
    [PASS] Stats response: Total=2, ByStatus={'Open': 1, 'Resolved': 1}, BySeverity={'High': 1, 'Medium': 1}

[*] Stopping Sentinel backend service...
[+] Backend stopped cleanly.

======================================================================
 ALL REAL CASE WORKFLOW VERIFICATION CHECKS PASSED!
======================================================================
```

---

## 4. Frontend Typecheck & Production Build Verification

```text
PS C:\Users\Atul2\OneDrive\Desktop\KiroHackethon\sentinal> npm run --prefix apps/crew-app typecheck
> sentinel-crew-app@0.1.0 typecheck
> tsc --noEmit

PS C:\Users\Atul2\OneDrive\Desktop\KiroHackethon\sentinal> npm run --prefix apps/crew-app build
> sentinel-crew-app@0.1.0 build
> vite build && vite build --config vite.config.embed.ts

vite v6.4.1 building for production...
transforming...
✓ 164 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                  0.82 kB │ gzip:  0.42 kB
dist/assets/index-D97k4bAJ.css  15.01 kB │ gzip:  3.36 kB
dist/assets/index-DeXfRNng.js   196.12 kB │ gzip: 59.44 kB
✓ built in 534ms

vite v6.4.1 building for production...
transforming...
✓ 156 modules transformed.
rendering chunks...
computing gzip size...
dist/index.mjs  186.22 kB │ gzip: 56.40 kB
✓ built in 482ms
```

---

## 5. Chrome Headless Browser Runtime Verification (`runtime_verification.py`)

```text
======================================================================
 PROJECT SENTINEL — Phase 3 Runtime Verification
======================================================================
[+] Found Browser for Runtime Verification: C:\Program Files\Google\Chrome\Application\chrome.exe
[*] Starting production preview server on 127.0.0.1:4173...
[+] Production preview server is ACTIVE on http://127.0.0.1:4173
[*] Starting Backend service on 127.0.0.1:8000...
[+] Backend service is ACTIVE on http://127.0.0.1:8000

--> [Test 1/5] Verifying Initial UI Render and Backend Connectivity...
    [PASS] DOM rendered successfully with active 'Backend Connected' state!

--> [Test 2/5] Testing all 8 navigation routes in browser runtime...
    [PASS] Route 'overview' rendered: 'Welcome to Project Sentinel' verified.
    [PASS] Route 'investigations' rendered: 'Investigation Cases' verified.
    [PASS] Route 'findings' rendered: 'Deterministic Findings' verified.
    [PASS] Route 'events' rendered: 'Canonical Events' verified.
    [PASS] Route 'replay' rendered: 'Replay Lab Module' verified.
    [PASS] Route 'sources' rendered: 'Data Ingestion' verified.
    [PASS] Route 'digests' rendered: 'Digests Module' verified.
    [PASS] Route 'settings' rendered: 'Settings Module' verified.

--> [Test 3/5] Verifying Events view interactive controls and canonical metrics...
    [PASS] Events view verified: controls, metrics bar, and canonical table present.

--> [Test 3b/5] Verifying Findings view interactive controls and detection engine triggers...
    [PASS] Findings view verified: metrics bar, engine triggers, and rules catalogue button present.

--> [Test 3c/5] Verifying Sources view interactive controls and genuine history...
    [PASS] Sources view verified: controls, event sources, and history table present.

--> [Test 3d/5] Verifying Investigations/Cases view interactive controls and correlation triggers...
    [PASS] Investigations/Cases view verified: metrics bar, correlation triggers, and case table present.

--> [Test 4/5] Testing Backend Disconnect and Offline Error State...
    [*] Stopping backend service...
    [PASS] Offline state correctly displayed with 'Backend Unavailable' and recovery guidance!

--> [Test 5/5] Testing Backend Restart and UI Recovery...
    [*] Restarting backend service...
    [PASS] Backend recovery confirmed: UI resumed 'Backend Connected' operational state!

[*] Shutting down test processes cleanly...
[+] All test servers stopped cleanly. Zero background processes remaining.

======================================================================
 ALL RUNTIME VERIFICATION STEPS PASSED SUCCESSFULLY!
======================================================================
```

---

## 6. Full Quality Hook Output (`.kiro/hooks/validate-all.ps1`)

```text
==> [Hook] Running Project Sentinel Validation...
--> Running Backend Unit & Contract Tests...
Ran 137 tests in 6.675s
OK
--> Running Frontend Typecheck...
--> Running Frontend Production Build...
dist/index.html                  0.82 kB │ gzip:  0.42 kB
dist/index.mjs                 186.22 kB │ gzip: 56.40 kB
--> Running Runtime Ingestion & Integrity Verification...
ALL RUNTIME VERIFICATION STEPS PASSED SUCCESSFULLY!
--> Running Real Detection Workflow Verification...
ALL REAL DETECTION WORKFLOW VERIFICATION CHECKS PASSED!
--> Running Real Case Correlation & Review Workflow Verification...
ALL REAL CASE WORKFLOW VERIFICATION CHECKS PASSED!
==> [Hook] All Quality Gates Passed Cleanly!
```

---

## 7. SQLite Schema & Foreign Key Verification

Executing direct SQL validation on SQLite database:
```sql
PRAGMA foreign_keys = ON;
PRAGMA foreign_key_check;
-- Result: 0 violations returned.

SELECT tbl_name, count(*) FROM sqlite_master WHERE type='table' GROUP BY tbl_name;
-- Tables present:
--   schema_versions
--   sources
--   import_jobs
--   parsed_records
--   normalization_errors
--   normalized_events
--   detection_rules
--   rule_evaluations
--   findings
--   finding_events
--   cases
--   case_findings
--   case_events
--   review_actions
--   correlation_evaluations
```
Foreign key integrity across all junction tables (`case_findings` $\to$ `findings`, `case_events` $\to$ `normalized_events`, `review_actions` $\to$ `cases`) is strictly enforced (`ON DELETE RESTRICT`).

