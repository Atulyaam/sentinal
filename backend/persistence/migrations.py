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

MIGRATIONS: List[Tuple[int, str, str]] = [
    (1, "001_initial_schema", MIGRATION_001_SQL),
    (2, "002_canonical_events_and_provenance", MIGRATION_002_SQL),
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
