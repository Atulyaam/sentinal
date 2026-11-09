# Project Sentinel — Phase 3 Normalization Architecture & Design Specification
**Document Version:** 1.0.0  
**Status:** Approved for Implementation  
**Sprint:** Sprint 3 (Canonical Event Normalization, Provenance & Data Integrity)  

---

## 1. Executive Summary & Purpose

Phase 2 established a secure, deterministic ingestion pipeline where raw logs are validated, scrubbed of cleartext credentials, and atomically persisted into SQLite `parsed_records`.

Phase 3 introduces the **Canonical Normalization Pipeline**:
A deterministic, auditable engine that transforms pre-normalized records from `parsed_records` into canonical security events conforming to `shared/contracts/event_contract.json`.

Key architectural principles:
1. **Deterministic Identity:** Every normalized event receives an `event_id` derived deterministically from source provenance. Reprocessing identical records produces the identical event ID.
2. **Strict UTC Normalization:** All timestamps are normalized to ISO-8601 UTC representation (`...Z`). Naive timestamps are handled under strict, explicit rules without guessing local machine time.
3. **No Silent Data Loss:** Records failing schema validation, timestamp parsing, or type constraints are recorded in `normalization_errors` with line-level diagnostics.
4. **End-to-End Provenance:** Normalized events retain complete bidirectional traceability back to the source file, SHA-256 hash, record number, parser profile, and import job.
5. **Idempotent Reprocessing:** Composite constraints on `(record_id, normalization_version)` guarantee that normalization passes can be re-run safely without producing duplicate events.

---

## 2. Canonical Event Contract

Normalized events conform strictly to `shared/contracts/event_contract.json`:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "NormalizedEventContract",
  "type": "object",
  "required": [
    "event_id",
    "timestamp",
    "source_type",
    "source_file",
    "source_line",
    "source_sha256",
    "event_type",
    "attributes"
  ],
  "properties": {
    "event_id": { "type": "string" },
    "timestamp": { "type": "string", "format": "date-time" },
    "source_type": { "type": "string" },
    "source_file": { "type": "string" },
    "source_line": { "type": "integer", "minimum": 1 },
    "source_sha256": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
    "event_type": { "type": "string" },
    "user_principal": { "type": ["string", "null"] },
    "source_ip": { "type": ["string", "null"] },
    "target_resource": { "type": ["string", "null"] },
    "status": { "type": "string", "enum": ["SUCCESS", "FAILURE", "ERROR", "UNKNOWN"] },
    "attributes": { "type": "object" }
  }
}
```

---

## 3. Parser-Specific Mapping Rules

### 3.1 Profile: `generic_jsonl`
- **Source Type:** `generic_jsonl`
- **Candidate Timestamp Keys:** `timestamp`, `time`, `@timestamp`, `ts`, `datetime`, `event_time`, `logged_at`
- **Candidate Event Type Keys:** `event_type`, `event`, `action`, `type`, `name`, `activity` (fallback: `"generic_event"`)
- **Candidate User Keys:** `user_principal`, `user`, `username`, `principal`, `user_id`, `actor`, `account`
- **Candidate Source IP Keys:** `source_ip`, `src_ip`, `client_ip`, `ip`, `remote_addr`
- **Candidate Target Resource Keys:** `target_resource`, `resource`, `target`, `uri`, `path`, `endpoint`, `destination`
- **Status Mapping:**
  - Evaluates `status`, `result`, or `outcome` if present:
    - `SUCCESS`, `OK`, `PASS`, `ALLOWED`, `200` $\rightarrow$ `"SUCCESS"`
    - `FAIL`, `FAILURE`, `DENIED`, `BLOCKED`, `REJECTED`, `401`, `403` $\rightarrow$ `"FAILURE"`
    - `ERR`, `ERROR`, `CRASH`, `500` $\rightarrow$ `"ERROR"`
    - Unmatched or missing $\rightarrow$ `"UNKNOWN"`

### 3.2 Profile: `auth_csv`
- **Source Type:** `auth_csv`
- **Event Type:** `parsed_record.event_type` (default `"user_authentication"`)
- **User Principal:** `attributes["username"]`
- **Source IP:** `attributes.get("source_ip")` or `attributes.get("ip")`
- **Target Resource:** `attributes.get("target_resource")` or `attributes.get("domain")`
- **Status Mapping:**
  - `SUCCESS` $\rightarrow$ `"SUCCESS"`
  - `FAILURE`, `LOCKED` $\rightarrow$ `"FAILURE"`
  - `CHALLENGE` $\rightarrow$ `"UNKNOWN"` (transitional MFA/challenge state)
  - Default $\rightarrow$ `"UNKNOWN"`

### 3.3 Profile: `web_access_csv`
- **Source Type:** `web_access_csv`
- **Event Type:** `parsed_record.event_type` (default `"web_request"`)
- **User Principal:** `attributes.get("username")` or `attributes.get("user")`
- **Source IP:** `attributes.get("source_ip")` or `attributes.get("client_ip")`
- **Target Resource:** `attributes.get("request_path")`
- **Status Mapping (HTTP Status Code):**
  - `100 <= status_code < 400` $\rightarrow$ `"SUCCESS"`
  - `400 <= status_code < 500` $\rightarrow$ `"FAILURE"` (client errors: 401 Unauthorized, 403 Forbidden, 404 Not Found)
  - `500 <= status_code <= 599` $\rightarrow$ `"ERROR"` (server errors: 500 Internal, 502 Bad Gateway)
  - Otherwise $\rightarrow$ `"UNKNOWN"`

---

## 4. Deterministic Identity Formula

Event IDs must be deterministic, collision-resistant, and verifiable across re-runs.

$$\text{Seed} = \text{source\_sha256} \,\|\, \text{record\_number} \,\|\, \text{parser\_id} \,\|\, \text{normalization\_version}$$

$$\text{event\_id} = \text{"evt\_"} + \text{SHA256}(\text{Seed})[0:24]$$

Example:
Given file hash `e3b0c44...`, line `12`, parser `auth_csv`, and normalizer `1.0.0`:
`event_id = "evt_a94a8fe5ccb19ba61c4c0873"`

---

## 5. Timestamp Normalization Protocol

### 5.1 Supported Formats
1. **ISO-8601 with Timezone:** `2026-11-09T08:00:15Z`, `2026-11-09T10:00:15+02:00`.
   - Converted to UTC and formatted as `YYYY-MM-DDTHH:MM:SSZ` (or microseconds if subsecond precision is provided).
2. **ISO-8601 Naive (No Timezone):** `2026-11-09T08:00:15` or `2026-11-09 08:00:15`.
   - Sentinel does NOT guess the local machine timezone.
   - Treated as UTC, and normalization records metadata in `attributes["__provenance"]`: `{"timezone_inferred": "UTC_ASSUMED"}`.
3. **Unix Epoch Timestamp:** Numeric string or number (e.g., `1762675215` or `1762675215000`).
   - Parsed as UTC datetime.

### 5.2 Invalid Timestamps
- If timestamp cannot be parsed into a valid UTC datetime, or if the source timestamp is missing/empty:
  - Normalization engine **NEVER** falls back to `datetime.now()`.
  - Normalization engine **REJECTS** the record and inserts an error into `normalization_errors` with code `NORM_INVALID_TIMESTAMP`.

---

## 6. Database Schema Expansion (Migration 002)

### 6.1 `normalized_events` Table
```sql
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
```

### 6.2 `normalization_errors` Table
```sql
CREATE TABLE IF NOT EXISTS normalization_errors (
    error_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES parsed_records(record_id) ON DELETE CASCADE,
    import_id TEXT NOT NULL REFERENCES import_jobs(import_id) ON DELETE CASCADE,
    record_number INTEGER NOT NULL,
    error_code TEXT NOT NULL,
    safe_error_message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);
```

### 6.3 Performance Indexes
```sql
CREATE INDEX IF NOT EXISTS idx_norm_events_ts ON normalized_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_norm_events_type ON normalized_events(event_type);
CREATE INDEX IF NOT EXISTS idx_norm_events_user ON normalized_events(user_principal);
CREATE INDEX IF NOT EXISTS idx_norm_events_ip ON normalized_events(source_ip);
CREATE INDEX IF NOT EXISTS idx_norm_events_import ON normalized_events(import_id);
CREATE INDEX IF NOT EXISTS idx_norm_errors_import ON normalization_errors(import_id);
```

---

## 7. Reprocessing, Idempotency & Error Handling

- **Idempotency Guarantee:** The unique constraint `(record_id, normalization_version)` ensures re-running normalization on an already normalized import will cleanly skip previously generated events without inserting duplicates.
- **Batch Processing:** Normalization runs in atomic database transactions (`BEGIN IMMEDIATE ... COMMIT`). If a fatal unexpected database crash occurs, no partial batches remain.
- **Read-Only Ingestion Safety:** `parsed_records` and original source files are strictly read-only and never modified during normalization.

