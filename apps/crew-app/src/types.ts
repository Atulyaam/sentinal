export type RouteId = 
  | 'overview'
  | 'investigations'
  | 'findings'
  | 'events'
  | 'replay'
  | 'sources'
  | 'digests'
  | 'settings';

export interface RouteMeta {
  id: RouteId;
  label: string;
  icon: string;
  planned?: boolean;
  sprint?: string;
  description: string;
}

export interface BackendHealthResponse {
  app: string;
  status: 'ok' | 'degraded' | 'error';
  version: string;
  timestamp?: string;
  environment?: string;
  demo_mode?: boolean;
}

export type ConnectionState = 'connected' | 'connecting' | 'disconnected';

export interface BackendHealthState {
  state: ConnectionState;
  data: BackendHealthResponse | null;
  lastChecked: Date | null;
  error: string | null;
}

export interface ImportJob {
  import_id: string;
  source_id: string;
  filename: string;
  sha256: string;
  file_size: number;
  parser_id: string;
  parser_version: string;
  status: 'pending' | 'completed' | 'partial' | 'failed' | 'skipped';
  total_records: number;
  accepted_records: number;
  rejected_records: number;
  started_at: string;
  completed_at?: string | null;
  error_summary?: string | null;
  errors?: ImportError[];
}

export interface ImportError {
  error_id: string;
  record_number: number;
  error_code: string;
  safe_error_message: string;
}

export interface EventSource {
  source_id: string;
  source_name: string;
  parser_profile: string;
  configured_path?: string | null;
  enabled: number;
  created_at: string;
  updated_at: string;
}

export interface ParserProfile {
  id: string;
  name: string;
  version: string;
  description: string;
}

export interface ImportResult {
  status: 'completed' | 'partial' | 'skipped' | 'failed' | 'rejected';
  duplicate: boolean;
  import_id?: string;
  source_id?: string;
  filename?: string;
  sha256?: string;
  file_size?: number;
  parser_id?: string;
  parser_version?: string;
  total_records?: number;
  accepted_records?: number;
  rejected_records?: number;
  completed_at?: string;
  error?: string;
  message?: string;
  errors?: ImportError[];
}

export interface NormalizedEvent {
  event_id: string;
  timestamp: string;
  source_type: string;
  source_file: string;
  source_line: number;
  source_sha256: string;
  event_type: string;
  user_principal?: string | null;
  source_ip?: string | null;
  target_resource?: string | null;
  status: 'SUCCESS' | 'FAILURE' | 'ERROR' | 'UNKNOWN';
  attributes: Record<string, any>;
  import_id?: string;
  record_id?: string;
  source_id?: string;
  record_number?: number;
  normalization_version?: string;
  created_at?: string;
}

export interface NormalizationStats {
  total_normalized_events: number;
  total_normalization_errors: number;
  pending_unnormalized_records: number;
  events_by_type: Record<string, number>;
}

export interface NormalizationRunResult {
  total_fetched: number;
  accepted: number;
  rejected: number;
  skipped: number;
}

export interface NormalizationError {
  error_id: string;
  record_id: string;
  import_id: string;
  record_number: number;
  error_code: string;
  safe_error_message: string;
  created_at: string;
}

export type FindingSeverity = 'Critical' | 'High' | 'Medium' | 'Low' | 'Info';
export type FindingStatus = 'open' | 'acknowledged' | 'resolved' | 'dismissed';

export interface Finding {
  finding_id: string;
  rule_id: string;
  rule_version: string;
  rule_config_hash: string;
  severity: FindingSeverity;
  status: FindingStatus;
  title: string;
  description: string;
  first_observed_at: string;
  last_observed_at: string;
  matched_entity: string | null;
  matched_conditions: Record<string, any>;
  supporting_event_ids: string[];
  supporting_events?: NormalizedEvent[];
  limitations: string;
  dedupe_key: string;
  created_at?: string;
  updated_at?: string;
}

export interface DetectionStats {
  total_findings: number;
  findings_by_severity: Record<string, number>;
  findings_by_status: Record<string, number>;
  last_evaluation?: {
    evaluation_id: string;
    evaluated_at: string;
    rule_count: number;
    events_scanned: number;
    findings_generated: number;
    findings_duplicate: number;
    duration_ms: number;
  } | null;
}

export interface DetectionRule {
  rule_id: string;
  version: string;
  name: string;
  description: string;
  severity: FindingSeverity;
  enabled: number | boolean;
  config_hash: string;
  config: Record<string, any>;
  limitations?: string;
  created_at?: string;
  updated_at?: string;
}

export type CaseStatus = 'Open' | 'UnderReview' | 'NeedsMoreEvidence' | 'Resolved' | 'Dismissed';
export type CaseSeverity = 'Critical' | 'High' | 'Medium' | 'Low' | 'Info';

export interface ReviewAction {
  action_id: string;
  case_id: string;
  action_type: string;
  previous_status?: string | null;
  new_status?: string | null;
  operator_note: string;
  author: string;
  created_at: string;
}

export interface TimelineItem {
  item_id: string;
  item_type: 'event' | 'finding' | 'correlation' | 'review_action' | 'status_change';
  timestamp: string;
  title: string;
  description: string;
  severity?: string | null;
  data?: Record<string, any>;
}

export interface Case {
  case_id: string;
  title: string;
  description: string;
  status: CaseStatus;
  severity: CaseSeverity;
  correlation_key_type: string;
  correlation_key_value: string;
  first_observed_at: string;
  last_observed_at: string;
  algorithm_version: string;
  dedupe_key: string;
  metadata?: Record<string, any>;
  finding_count?: number;
  event_count?: number;
  review_count?: number;
  findings?: Finding[];
  events?: NormalizedEvent[];
  timeline?: TimelineItem[];
  review_actions?: ReviewAction[];
  claims?: ClaimVerificationResult[];
  created_at?: string;
  updated_at?: string;
}

export interface CaseStats {
  total_cases: number;
  cases_by_status: Record<string, number>;
  cases_by_severity: Record<string, number>;
  last_evaluation?: {
    evaluation_id: string;
    evaluated_at: string;
    findings_scanned: number;
    events_scanned: number;
    cases_created: number;
    cases_updated: number;
    duration_ms: number;
  } | null;
}

export type ClaimType =
  | 'event_count'
  | 'finding_exists'
  | 'rule_match'
  | 'time_window'
  | 'entity_observed'
  | 'case_status'
  | 'correlation_relationship'
  | 'data_quality_issue';

export type VerificationStatus = 'verified' | 'qualified' | 'blocked';
export type ClaimCertainty = 'observed' | 'inferred' | 'hypothesis';

export interface VerificationCheck {
  name: string;
  passed: boolean;
  reason: string;
}

export interface ClaimProposal {
  claim_id: string;
  case_id: string;
  claim_type: ClaimType;
  predicate: string;
  value: Record<string, any>;
  evidence_refs: string[];
  certainty?: ClaimCertainty;
  template_id: string;
  proposed_by?: string;
  created_at?: string;
}

export interface ClaimVerificationResult {
  verification_id: string;
  claim_id: string;
  case_id: string;
  status: VerificationStatus;
  verification_version: string;
  checks: VerificationCheck[];
  rendered_text: string;
  qualification_notes?: string[];
  blocked_reasons?: string[];
  suggested_remedy?: string | null;
  evidence_refs: string[];
  verified_at: string;
  claim_type?: ClaimType;
  predicate?: string;
  value?: Record<string, any>;
  certainty?: ClaimCertainty;
  template_id?: string;
  proposed_by?: string;
}

export interface ClaimVerificationReport {
  case_id: string;
  verification_version: string;
  total_claims: number;
  verified_count: number;
  qualified_count: number;
  blocked_count: number;
  results: ClaimVerificationResult[];
}

export interface ClaimTemplate {
  template_id: string;
  claim_type: string;
  description: string;
  format: string;
  required_params: string[];
}

// ----------------------------------------------------------------------------
// Phase 7: Replay Lab Types
// ----------------------------------------------------------------------------

export interface ScenarioFixtureMeta {
  filename: string;
  parser_id: string;
  sha256: string;
  size_bytes: number;
  description: string;
}

export interface ScenarioExpectationsMeta {
  expected_imported_records: number;
  expected_normalized_events: number;
  expected_rules: string[];
  expected_findings_count: number;
  expected_cases_count: number;
  expected_claim_outcomes: Record<string, string>;
  expected_timeline_types: string[];
}

export interface SupportedWhatIf {
  what_if_id: string;
  name: string;
  description: string;
  rule_overrides?: Record<string, any>;
  correlation_overrides?: Record<string, any>;
  excluded_records?: number[];
}

export interface ScenarioManifestMeta {
  scenario_id: string;
  name: string;
  version: string;
  category: string;
  description: string;
  story: string;
  learning_objective: string;
  fixtures: ScenarioFixtureMeta[];
  claim_proposals: Record<string, any>[];
  expectations: ScenarioExpectationsMeta;
  supported_what_ifs: SupportedWhatIf[];
}

export interface ReplayAssertionItem {
  assertion_id: string;
  category: string;
  description: string;
  expected: any;
  actual: any;
  passed: boolean;
  message: string;
}

export interface ReplayStageItem {
  stage_id: string;
  name: string;
  status: 'completed' | 'failed' | 'skipped';
  duration_ms: number;
  summary: string;
}

export interface ReplayMetricsMeta {
  imported_records: number;
  normalized_events: number;
  findings_count: number;
  cases_count: number;
  claims_total: number;
  claims_verified: number;
  claims_qualified: number;
  claims_blocked: number;
  assertions_total: number;
  assertions_passed: number;
  assertions_failed: number;
  duration_ms: number;
}

export interface ReplayRunReportMeta {
  replay_id: string;
  scenario_id: string;
  scenario_name: string;
  scenario_version: string;
  status: 'completed' | 'failed';
  mode: 'standard' | 'what_if';
  pipeline_versions: Record<string, string>;
  fixture_checksums: Record<string, string>;
  what_if_config: Record<string, any>;
  metrics: ReplayMetricsMeta;
  assertion_results: ReplayAssertionItem[];
  stages: ReplayStageItem[];
  cases_snapshot: any[];
  claims_snapshot: any[];
  what_if_diff?: Record<string, any> | null;
  error_summary?: string | null;
  started_at: string;
  completed_at?: string | null;
}

export interface ReplayComparisonMeta {
  run_a_id: string;
  run_b_id: string;
  scenario_id: string;
  scenario_version: string;
  is_identical: boolean;
  metric_deltas: Record<string, number>;
  metrics_delta?: Record<string, number>;
  findings_added: string[];
  findings_removed: string[];
  cases_added: number;
  cases_removed: number;
  assertion_mismatches: string[];
  run_a_duration_ms: number;
  run_b_duration_ms: number;
  pipeline_versions_match: boolean;
  fixture_checksums_match: boolean;
}


