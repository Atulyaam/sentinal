"""Database Migrations Manager for Project Sentinel."""

import logging
import sqlite3
from typing import List, Tuple

logger = logging.getLogger("sentinel.migrations")

MIGRATION_001_SQL = """
-- 1. Event Sources (Approved inboxes and manual sources)
CREATE TABLE IF NOT EXISTS event_sources (
    source_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    parser_profile TEXT NOT NULL,
    configured_path TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- 2. Import Jobs (Lifecycle, counts, SHA-256 idempotency)
CREATE TABLE IF NOT EXISTS import_jobs (
    import_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES event_sources(source_id) ON DELETE RESTRICT,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    parser_id TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    status TEXT NOT NULL,
    total_records INTEGER NOT NULL DEFAULT 0,
    accepted_records INTEGER NOT NULL DEFAULT 0,
    rejected_records INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    completed_at TEXT,
    error_summary TEXT,
    CONSTRAINT uq_import_hash_parser UNIQUE (sha256, parser_id, parser_version)
);

-- 3. Import Errors (Fine-grained diagnostic records for malformed lines)
CREATE TABLE IF NOT EXISTS import_errors (
    error_id TEXT PRIMARY KEY,
    import_id TEXT NOT NULL REFERENCES import_jobs(import_id) ON DELETE CASCADE,
    record_number INTEGER NOT NULL,
    error_code TEXT NOT NULL,
    safe_error_message TEXT NOT NULL
);

-- 4. Parsed Records (Pre-normalized records with redaction applied)
CREATE TABLE IF NOT EXISTS parsed_records (
    record_id TEXT PRIMARY KEY,
    import_id TEXT NOT NULL REFERENCES import_jobs(import_id) ON DELETE CASCADE,
    record_number INTEGER NOT NULL,
    parser_id TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- Indexes for performance and query integrity
CREATE INDEX IF NOT EXISTS idx_import_jobs_sha256 ON import_jobs(sha256);
CREATE INDEX IF NOT EXISTS idx_import_jobs_created ON import_jobs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_import_jobs_source ON import_jobs(source_id);
CREATE INDEX IF NOT EXISTS idx_parsed_records_import ON parsed_records(import_id);
CREATE INDEX IF NOT EXISTS idx_import_errors_import ON import_errors(import_id);

-- Default Source for Manual Ingestion
INSERT OR IGNORE INTO event_sources (source_id, source_name, parser_profile, configured_path, enabled)
VALUES ('src_manual_default', 'Manual Browser Upload', 'generic_jsonl', NULL, 1);
"""

MIGRATION_002_SQL = """
-- 5. Normalized Events (Canonical security events with full provenance)
CREATE TABLE IF NOT EXISTS normalized_events (
    event_id TEXT PRIMARY KEY,
    import_id TEXT NOT NULL REFERENCES import_jobs(import_id) ON DELETE CASCADE,
    record_id TEXT NOT NULL REFERENCES parsed_records(record_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES event_sources(source_id) ON DELETE RESTRICT,
    record_number INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_line INTEGER NOT NULL,
    source_sha256 TEXT NOT NULL,
    event_type TEXT NOT NULL,
    user_principal TEXT,
    source_ip TEXT,
    target_resource TEXT,
    status TEXT NOT NULL,
    attributes_json TEXT NOT NULL,
    normalization_version TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    CONSTRAINT uq_record_norm_version UNIQUE (record_id, normalization_version)
);

-- 6. Normalization Errors (Fine-grained diagnostic records for unmappable records)
CREATE TABLE IF NOT EXISTS normalization_errors (
    error_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES parsed_records(record_id) ON DELETE CASCADE,
    import_id TEXT NOT NULL REFERENCES import_jobs(import_id) ON DELETE CASCADE,
    record_number INTEGER NOT NULL,
    error_code TEXT NOT NULL,
    safe_error_message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- Performance and Query Integrity Indexes for Canonical Events
CREATE INDEX IF NOT EXISTS idx_norm_events_ts ON normalized_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_norm_events_type ON normalized_events(event_type);
CREATE INDEX IF NOT EXISTS idx_norm_events_user ON normalized_events(user_principal);
CREATE INDEX IF NOT EXISTS idx_norm_events_ip ON normalized_events(source_ip);
CREATE INDEX IF NOT EXISTS idx_norm_events_import ON normalized_events(import_id);
CREATE INDEX IF NOT EXISTS idx_norm_events_record ON normalized_events(record_id);
CREATE INDEX IF NOT EXISTS idx_norm_errors_import ON normalization_errors(import_id);
CREATE INDEX IF NOT EXISTS idx_norm_errors_record ON normalization_errors(record_id);
"""

MIGRATION_003_SQL = """
-- 7. Add parser_version to normalized_events for self-contained parser provenance
ALTER TABLE normalized_events ADD COLUMN parser_version TEXT NOT NULL DEFAULT '1.0.0';
"""

MIGRATION_004_SQL = """
-- 8. Detection Rules (Versioned detection definitions)
CREATE TABLE IF NOT EXISTS detection_rules (
    rule_id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    config_hash TEXT NOT NULL,
    rule_definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- 9. Findings (Evidence-backed security detections)
CREATE TABLE IF NOT EXISTS findings (
    finding_id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL REFERENCES detection_rules(rule_id) ON DELETE RESTRICT,
    rule_version TEXT NOT NULL,
    rule_config_hash TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    matched_entity TEXT,
    matched_conditions_json TEXT NOT NULL,
    supporting_event_ids_json TEXT NOT NULL,
    limitations TEXT NOT NULL,
    dedupe_key TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    CONSTRAINT uq_finding_dedupe UNIQUE (rule_id, rule_version, dedupe_key)
);

-- 10. Finding Events (Relational evidence junction)
CREATE TABLE IF NOT EXISTS finding_events (
    finding_id TEXT NOT NULL REFERENCES findings(finding_id) ON DELETE CASCADE,
    event_id TEXT NOT NULL REFERENCES normalized_events(event_id) ON DELETE RESTRICT,
    PRIMARY KEY (finding_id, event_id)
);

-- 11. Rule Evaluations (Audit history of detection engine executions)
CREATE TABLE IF NOT EXISTS rule_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    evaluated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    rule_count INTEGER NOT NULL,
    events_scanned INTEGER NOT NULL,
    findings_generated INTEGER NOT NULL,
    findings_duplicate INTEGER NOT NULL,
    duration_ms REAL NOT NULL
);

-- Indexes for performance and query integrity
CREATE INDEX IF NOT EXISTS idx_findings_rule_id ON findings(rule_id);
CREATE INDEX IF NOT EXISTS idx_findings_severity ON findings(severity);
CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status);
CREATE INDEX IF NOT EXISTS idx_findings_observed ON findings(last_observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_finding_events_event ON finding_events(event_id);
CREATE INDEX IF NOT EXISTS idx_rule_evaluations_date ON rule_evaluations(evaluated_at DESC);

-- Seed default detection rules
INSERT OR IGNORE INTO detection_rules (rule_id, version, name, description, severity, enabled, config_hash, rule_definition_json)
VALUES 
('AUTH-001', '1.0.0', 'Repeated Authentication Failures', 'Detects 5 or more failed authentications for the same user within a 10-minute window.', 'Medium', 1, 'cce9a85113c5427f', '{"target_event_type":"user_authentication","target_status":"FAILURE","threshold_count":5,"window_seconds":600}'),
('AUTH-002', '1.0.0', 'Success After Authentication Failures', 'Detects successful authentication within 30 minutes following an authentication failure burst for the same user.', 'High', 1, '4aba64844021f317', '{"failure_threshold":5,"failure_window_seconds":600,"success_window_seconds":1800}'),
('WEB-001', '1.0.0', 'Sensitive Route Burst', 'Detects 3 or more requests to sensitive administrative endpoints from the same source within 15 minutes.', 'Medium', 1, '6a4edb386c9a9c3a', '{"sensitive_routes":["/admin","/api/v1/auth","/login","/wp-admin","/internal","/.env","/config"],"threshold_count":3,"window_seconds":900}'),
('PRIV-001', '1.0.0', 'Explicit Privilege Escalation / Role Change', 'Detects explicit administrative privilege alteration, role modification, or permission grants.', 'High', 1, '8180deeb2e9fdcae', '{"privilege_event_types":["role_changed","privilege_granted","admin_escalation","group_add","role_assigned"],"privilege_actions":["grant_role","assign_admin","sudo","privilege_escalation"]}'),
('INGEST-001', '1.0.0', 'Ingestion & Timestamp Data Quality Anomaly', 'Detects data-quality anomalies including quarantined timestamps, clock skew, or future-dated events.', 'Info', 1, '598a7581f1108d23', '{"max_future_seconds":86400}');
"""

MIGRATIONS: List[Tuple[int, str, str]] = [
    (1, "001_initial_schema", MIGRATION_001_SQL),
    (2, "002_canonical_events_and_provenance", MIGRATION_002_SQL),
    (3, "003_event_parser_version", MIGRATION_003_SQL),
    (4, "004_detection_rules_and_findings", MIGRATION_004_SQL),
]


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Ensure database schema is up-to-date and track applied versions."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
        );
    """)

    cursor = conn.cursor()
    cursor.execute("SELECT version FROM schema_migrations;")
    applied_versions = {row[0] for row in cursor.fetchall()}

    for version, name, sql in MIGRATIONS:
        if version not in applied_versions:
            logger.info("Applying database migration %d: %s", version, name)
            # executescript executes all statements transactionally
            full_script = f"""
                {sql}
                INSERT INTO schema_migrations (version, name) VALUES ({version}, '{name}');
            """
            conn.executescript(full_script)
            logger.info("Migration %d (%s) applied successfully.", version, name)
