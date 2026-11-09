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
