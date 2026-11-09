# Phase 2 Database & Data Pipeline Design Specification
**Project:** Project Sentinel  
**Sprint:** 2 — Core Data Pipeline, SQLite, Parsers & Secure Ingestion  
**Author:** Principal Backend Engineer & Database Architect  
**Status:** Approved Architectural Specification  

---

## 1. System Overview & Objective

Sprint 2 establishes the core ingestion engine for Project Sentinel. The objective is to provide a local-first, tamper-evident, deterministic pipeline that imports security logs from explicitly approved sources, executes strict parsing across three distinct profiles (`generic_jsonl`, `auth_csv`, `web_access_csv`), redacts credentials, enforces SHA-256 idempotency, and records import lifecycle history and parsed records in a persistent SQLite database.

```text
Local Inbox File / Browser Upload
               │
               ▼
   [ Ingestion Engine Pre-flight ]
   - Path containment verification (os.path.realpath)
   - Size limit check (max 20 MB)
   - Read-only SHA-256 calculation
               │
               ▼
   [ Idempotency Check (DB) ] ── (Duplicate found) ──► Mark "duplicate_skipped" (no-op)
               │ (New Hash)
               ▼
   [ Selected Strict Parser ] ── (Row syntax error) ──► Record in import_errors
               │ (Valid rows)
               ▼
   [ Sanitizer / Redactor ] ──► Mask credentials, tokens, authorization headers
               │
               ▼
  [ SQLite Atomic Transaction ]
   ├── BEGIN IMMEDIATE
   ├── INSERT INTO import_jobs
   ├── INSERT INTO import_errors (if any)
   ├── INSERT INTO parsed_records
   └── COMMIT (Status: completed / completed_with_errors)
```

---

## 2. SQLite Database Architecture

### 2.1 Storage Location & Separation
To prevent repository pollution and accidental leakage of operator logs:
- **Default Database Path:** The database is stored outside the repository and outside the watched inbox in the standard OS user local data directory:
  - Windows: `%LOCALAPPDATA%\ProjectSentinel\sentinel.db`
  - POSIX / Linux / macOS: `~/.local/share/project-sentinel/sentinel.db`
  - Fallback / Test override: Configurable via environment variable `SENTINEL_DB_PATH`.
- SQLite Pragmas enforced on every connection:
  - `PRAGMA foreign_keys = ON;` (Strict referential integrity)
  - `PRAGMA journal_mode = WAL;` (Write-Ahead Logging for concurrency and crash-durability)
  - `PRAGMA synchronous = NORMAL;` (Optimal durability balance in WAL mode)
  - `PRAGMA busy_timeout = 5000;` (Wait up to 5s for lock acquisition)

### 2.2 Schema Versioning & Repeatable Migrations
Schema changes are managed through a dedicated `schema_migrations` table and versioned Python migration scripts (`001_initial_schema.sql`, etc.):

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);
```

---

## 3. Table Definitions & Responsibilities

### 3.1 `event_sources`
Represents an explicitly approved log source (manual upload or inbox directory).
- `source_id` (TEXT PRIMARY KEY): Unique identifier (e.g. `src_manual_default`, UUID).
- `source_name` (TEXT NOT NULL): Human-readable label (e.g. `Primary Inbox`, `Manual Upload`).
- `parser_profile` (TEXT NOT NULL): Default parser profile (`generic_jsonl`, `auth_csv`, `web_access_csv`).
- `configured_path` (TEXT): Canonical absolute directory path if an inbox directory is configured.
- `enabled` (INTEGER NOT NULL DEFAULT 1): 1 for active monitoring, 0 for paused.
- `created_at` (TEXT NOT NULL DEFAULT (datetime('now', 'utc'))): ISO-8601 UTC timestamp.
- `updated_at` (TEXT NOT NULL DEFAULT (datetime('now', 'utc'))): ISO-8601 UTC timestamp.

### 3.2 `import_jobs`
Tracks the complete lifecycle, metadata, and cryptographic identity of each ingested file.
- `import_id` (TEXT PRIMARY KEY): Unique job identifier (e.g. `imp_<uuid>`).
- `source_id` (TEXT NOT NULL REFERENCES event_sources(source_id) ON DELETE RESTRICT): Associated source.
- `filename` (TEXT NOT NULL): Basename of the file (sanitized; no path components).
- `sha256` (TEXT NOT NULL): 64-character lowercase hexadecimal hash of the file bytes.
- `file_size` (INTEGER NOT NULL): File size in bytes.
- `parser_id` (TEXT NOT NULL): Explicitly selected parser profile (`generic_jsonl`, `auth_csv`, `web_access_csv`).
- `parser_version` (TEXT NOT NULL): Semantic version of the parser (e.g. `1.0.0`).
- `status` (TEXT NOT NULL): State transition indicator:
  - `pending`: Registered, processing starting.
  - `completed`: All records parsed successfully without errors.
  - `completed_with_errors`: Completed, but one or more records failed validation.
  - `duplicate_skipped`: Byte-for-byte duplicate of an existing import; no records re-inserted.
  - `failed`: Fatal file-level failure (e.g. encoding corruption, unexpected schema mismatch).
- `total_records` (INTEGER NOT NULL DEFAULT 0): Total lines/rows encountered.
- `accepted_records` (INTEGER NOT NULL DEFAULT 0): Successfully parsed and persisted records.
- `rejected_records` (INTEGER NOT NULL DEFAULT 0): Malformed records rejected and logged in `import_errors`.
- `started_at` (TEXT NOT NULL): ISO-8601 UTC timestamp when ingestion started.
- `completed_at` (TEXT): ISO-8601 UTC timestamp when transaction committed.
- `error_summary` (TEXT): High-level failure reason if job failed.

**Unique Constraint & Idempotency Key:**
```sql
UNIQUE(sha256, parser_id, parser_version)
```
Enforces at the database layer that identical file bytes evaluated with the same parser profile and parser version cannot be duplicated.

### 3.3 `import_errors`
Preserves fine-grained diagnostic records for each malformed row while allowing valid records in the same file to proceed.
- `error_id` (TEXT PRIMARY KEY): Unique error identifier (e.g. `err_<uuid>`).
- `import_id` (TEXT NOT NULL REFERENCES import_jobs(import_id) ON DELETE CASCADE): Linked import job.
- `record_number` (INTEGER NOT NULL): 1-based line or row number in the source file.
- `error_code` (TEXT NOT NULL): Machine-readable classification (e.g. `MALFORMED_JSON`, `MISSING_TIMESTAMP`, `INVALID_STATUS_CODE`, `UNEXPECTED_COLUMN_COUNT`).
- `safe_error_message` (TEXT NOT NULL): Sanitized diagnostic explanation safe for operator review (secrets redacted).

### 3.4 `parsed_records`
Stores ingestion-stage structured records pending canonical normalization (Phase 3).
- `record_id` (TEXT PRIMARY KEY): Unique record identifier (e.g. `rec_<uuid>`).
- `import_id` (TEXT NOT NULL REFERENCES import_jobs(import_id) ON DELETE CASCADE): Linked import job.
- `record_number` (INTEGER NOT NULL): 1-based source line or row number.
- `parser_id` (TEXT NOT NULL): Parser profile used.
- `parser_version` (TEXT NOT NULL): Parser version used.
- `record_json` (TEXT NOT NULL): JSON-serialized structured dictionary with pre-persistence redaction applied.
- `created_at` (TEXT NOT NULL DEFAULT (datetime('now', 'utc'))): Ingestion timestamp.

**Indexes:**
```sql
CREATE INDEX idx_import_jobs_sha256 ON import_jobs(sha256);
CREATE INDEX idx_import_jobs_created ON import_jobs(started_at DESC);
CREATE INDEX idx_parsed_records_import ON parsed_records(import_id);
CREATE INDEX idx_import_errors_import ON import_errors(import_id);
```

---

## 4. Transaction Boundaries & Recovery Strategy

1. **Atomic Import Transactions:** All records and error logs for an import job are inserted within a single SQLite transaction:
   ```python
   with connection:
       # Inserts to import_jobs, parsed_records, import_errors
   ```
2. **Crash & Restart Recovery:**
   - If the backend crashes mid-import, SQLite's WAL journal automatically rolls back uncommitted changes upon reconnection.
   - On startup, the persistence engine runs a reconciliation query:
     ```sql
     UPDATE import_jobs SET status = 'failed', error_summary = 'Server restarted during processing'
     WHERE status = 'pending';
     ```
   - This prevents zombie jobs and guarantees that retrying an import does not violate unique constraints.

---

## 5. Parser Architecture & Profiles

All parsers inherit from `BaseParser` and implement the generator contract:
`parse(stream: Iterable[str]) -> Tuple[List[ParsedRecord], List[ParsingError]]`

### 5.1 `generic_jsonl`
- UTF-8 and UTF-8 BOM (`\ufeff`) decoding.
- Evaluates line-by-line.
- Rejects JSON scalars (strings, numbers, booleans) and arrays; requires top-level JSON objects.
- Malformed lines append an `import_errors` entry with exact line number; parsing continues.

### 5.2 `auth_csv`
- Header validation: Requires `timestamp`, `username` (or `user_id`), `auth_result` (or `status`). Optional: `source_ip`, `session_id`, `event_type`.
- Validates explicit authentication outcomes (`SUCCESS`, `FAILURE`, `CHALLENGE`, `LOCKED`).
- Handles CSV escaping and RFC 4180 quoting. Missing optional fields remain `null`.

### 5.3 `web_access_csv`
- Header validation: Requires `timestamp`, `http_method`, `request_path`, `status_code`. Optional: `source_ip`, `user_agent`.
- Validates HTTP methods (`GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `HEAD`, `OPTIONS`) and integer status codes (100–599).

---

## 6. Security Boundaries

1. **Path Traversal Defense:** Configured inbox paths are resolved via `os.path.realpath`. Traversal sequences (`..`), root paths (`C:\`, `/`), user homes (`~`), and OS system paths are rejected.
2. **Pre-Persistence Redaction:** Before storing parsed records into `parsed_records.record_json`, sensitive fields (passwords, tokens, bearer authorizations, cookies) are masked to prevent plaintext credential exposure in the database.
3. **No Code Execution:** Parsers use strict standard-library `json` and `csv` modules. No `eval()`, no dynamic imports, no shell invocation.

