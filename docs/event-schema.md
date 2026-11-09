# Project Sentinel — Event Schema & Record Contract
**Document Version:** 1.1.0  
**Target Sprint:** Sprint 2 (Ingestion) & Sprint 3 (Normalization)  

---

## 1. Overview

In Project Sentinel, incoming log events undergo a two-stage lifecycle:
1. **Stage 1 (Sprint 2 — Ingestion & Sanitization):** Strict parsing into pre-normalized `ParsedRecord` structures, scrubbing of cleartext secrets, and atomic persistence into the SQLite `parsed_records` table alongside line-level error tracking in `import_errors`.
2. **Stage 2 (Sprint 3 — Canonical Event Normalization):** Mapping of parsed records into the canonical `NormalizedEventContract` (`shared/contracts/event_contract.json`) with deterministic event IDs, UTC normalization, and provenance hashes.

---

## 2. Ingested Parsed Record Structure

Pre-normalized records persisted during Sprint 2 conform to the following schema within the `parsed_records` table:

| Column | Type | Description |
| :--- | :--- | :--- |
| `record_id` | TEXT PRIMARY KEY | Unique identifier for the parsed record (e.g., `rec_a1b2c3d4e5f6`). |
| `import_id` | TEXT NOT NULL | Foreign key referencing `import_jobs(import_id)` on cascade. |
| `record_number` | INTEGER NOT NULL | Physical 1-based line or row number in the source file. |
| `parser_id` | TEXT NOT NULL | Profile used to parse the record (`generic_jsonl`, `auth_csv`, `web_access_csv`). |
| `parser_version` | TEXT NOT NULL | Semantic version of the parser profile (e.g., `1.0.0`). |
| `record_json` | TEXT NOT NULL | Serialized JSON representation of the parsed and redacted event record. |
| `created_at` | TEXT NOT NULL | ISO-8601 UTC timestamp of database insertion. |

### 2.1 The `record_json` Payload Structure
```json
{
  "line_number": 42,
  "timestamp": "2026-11-09T08:00:15Z",
  "event_type": "user_authentication",
  "attributes": {
    "username": "secops_admin",
    "auth_result": "SUCCESS",
    "source_ip": "192.168.1.100",
    "session_id": "sess_a1b2c3",
    "password": "[REDACTED]"
  },
  "raw_payload": "2026-11-09T08:00:15Z,secops_admin,SUCCESS,192.168.1.100,sess_a1b2c3"
}
```

---

## 3. Parser Profiles & Ingestion Attribute Extraction

### 3.1 Profile: `generic_jsonl`
- **Source Format:** Line-delimited UTF-8 JSON objects.
- **Header:** None. Empty lines are skipped.
- **Validation Rules:**
  - Must be a valid JSON object (`{...}`). Arrays and primitives are rejected as `ParsingError`.
  - Line length must not exceed 1,048,576 characters (1MB).
  - Timestamp extracted from candidate keys (`timestamp`, `time`, `@timestamp`, `ts`, `datetime`, `event_time`, `logged_at`).
  - Event type extracted from candidate keys (`event_type`, `event`, `action`, `type`, `name`, `activity`); defaults to `"generic_event"`.
  - All parsed key-value pairs are stored in `attributes`.

### 3.2 Profile: `auth_csv`
- **Source Format:** Comma-separated values with header.
- **Required Columns:** `timestamp`, `username` (or `user_id`), `auth_result`.
- **Validation Rules:**
  - `auth_result` must be one of: `SUCCESS`, `FAILURE`, `CHALLENGE`, `LOCKED` (case-insensitive, normalized to uppercase).
  - Rejects missing required columns in the header.
  - Rejects rows with missing required fields or column count mismatches.
- **Attributes:**
  - `username`: String user identifier.
  - `auth_result`: Normalized uppercase string.
  - `source_ip`: Optional client IP address.
  - `session_id`: Optional session tracking token.
  - `event_type`: Defaults to `"user_authentication"`.

### 3.3 Profile: `web_access_csv`
- **Source Format:** Comma-separated values with header.
- **Required Columns:** `timestamp`, `http_method`, `request_path`, `status_code`.
- **Validation Rules:**
  - `http_method` must be a valid HTTP verb: `GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `HEAD`, `OPTIONS`, `CONNECT`, `TRACE`.
  - `status_code` must parse as an integer between 100 and 599.
  - Rejects missing required columns or column count mismatches.
- **Attributes:**
  - `http_method`: Normalized uppercase HTTP verb.
  - `request_path`: Request URI/endpoint string.
  - `status_code`: Integer HTTP status code (e.g. `200`, `401`, `500`).
  - `source_ip`: Optional client IP address.
  - `user_agent`: Optional client user-agent string.
  - `event_type`: Defaults to `"web_request"`.

---

## 4. Pre-Persistence Redaction Rules

Prior to database insertion, all parsed attributes and raw payloads pass through `backend.ingestion.sanitizer`:
1. **Dictionary Key Match:** Any attribute key containing substrings such as `password`, `passwd`, `token`, `secret`, `authorization`, `auth_token`, `api_key`, `apikey`, `private_key`, `cookie`, or `session_token` has its value overwritten with `"[REDACTED]"`.
2. **Raw Text Regex Match:**
   - Bearer tokens: `Bearer\s+[A-Za-z0-9_\-\.]{8,}` is scrubbed to `Bearer [REDACTED]`.
   - Inline passwords: `(?i)(?:password|passwd|secret)\s*[:=]\s*[^\s,;\"]+` is scrubbed to `password=[REDACTED]`.
   - Inline API keys: `(?i)(?:api[_-]?key)\s*[:=]\s*[^\s,;\"]+` is scrubbed to `api_key=[REDACTED]`.

---

## 5. Canonical Event Schema (`NormalizedEventContract`)

In Sprint 3, canonical normalization maps `ParsedRecord` into `NormalizedEventContract`:

### 5.1 Canonical Event Fields

| Field Name | Type | Requirement | Description | Validation Rule | Example Value |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `event_id` | String | **Required** | Deterministic unique event identifier. | Derived via SHA-256 hash of `(source_sha256, record_number, parser_id, normalization_version)`. Prefixed with `evt_` and 24 hex characters. | `evt_8f3a1b0c9e7d5f2a1b4c6e8d` |
| `timestamp` | String | **Required** | Canonical event occurrence time in UTC. | Valid ISO-8601 date-time string terminating in `Z` (or UTC offset). Naive timestamps parsed as UTC with metadata annotation. Invalid timestamps cause normalization rejection. | `2026-11-09T08:00:15Z` |
| `source_type` | String | **Required** | Originating parser profile / format family. | Non-empty string matching one of the supported parser IDs: `generic_jsonl`, `auth_csv`, `web_access_csv`. | `auth_csv` |
| `source_file` | String | **Required** | Safe filename of the ingested source file. | Basename of original imported file, sanitized of path traversals. | `auth_audit_20261109.csv` |
| `source_line` | Integer | **Required** | Physical line or row number in the source file. | 1-based positive integer ($\ge 1$). | `42` |
| `source_sha256` | String | **Required** | Cryptographic SHA-256 hash of original file. | 64-character lowercase hexadecimal string matching `^[a-f0-9]{64}$`. | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `event_type` | String | **Required** | Normalized security event classification. | Non-empty string identifying the semantic event type. | `user_authentication`, `web_request` |
| `user_principal` | String \| null | *Optional* | User or principal identifier associated with event. | Non-empty string or `null` if unauthenticated/unspecified. | `secops_admin` |
| `source_ip` | String \| null | *Optional* | Client IP address originating the event. | Valid IPv4/IPv6 string or `null` if absent. | `192.168.1.100` |
| `target_resource` | String \| null | *Optional* | Target URI, host, file, or resource. | Non-empty string or `null` if absent. | `/api/v1/auth/login` |
| `status` | String | **Required** | High-level outcome of the observed event. | Strict enum: `SUCCESS`, `FAILURE`, `ERROR`, `UNKNOWN`. | `SUCCESS` |
| `attributes` | Object | **Required** | Structured event-specific payload. | Key-value dictionary containing sanitized event attributes and provenance metadata. | `{"session_id": "sess_123", "http_method": "POST"}` |

---

## 6. Field Mapping Specification by Parser

| Canonical Field | `generic_jsonl` Source | `auth_csv` Source | `web_access_csv` Source |
| :--- | :--- | :--- | :--- |
| `event_id` | Deterministic SHA-256 hash | Deterministic SHA-256 hash | Deterministic SHA-256 hash |
| `timestamp` | Normalized candidate timestamp | Normalized `timestamp` column | Normalized `timestamp` column |
| `source_type` | `"generic_jsonl"` | `"auth_csv"` | `"web_access_csv"` |
| `source_file` | `import_jobs.filename` | `import_jobs.filename` | `import_jobs.filename` |
| `source_line` | `parsed_records.record_number` | `parsed_records.record_number` | `parsed_records.record_number` |
| `source_sha256` | `import_jobs.sha256` | `import_jobs.sha256` | `import_jobs.sha256` |
| `event_type` | Candidate keys or `"generic_event"` | `"user_authentication"` | `"web_request"` |
| `user_principal` | Candidate keys (`user`, `username`, etc.) or `null` | `username` / `user_id` column | Candidate column or `null` |
| `source_ip` | Candidate keys (`ip`, `client_ip`, etc.) or `null` | `source_ip` / `ip` column or `null` | `source_ip` / `client_ip` column or `null` |
| `target_resource` | Candidate keys (`resource`, `path`, etc.) or `null` | `target_resource` / `domain` or `null` | `request_path` column |
| `status` | Mapped from `status`/`result` candidate | Mapped from `auth_result` (`SUCCESS`/`FAILURE`/`UNKNOWN`) | Mapped from HTTP `status_code` |
| `attributes` | Sanitized dictionary | Sanitized dictionary | Sanitized dictionary |

---

## 7. Normalization Error Taxonomy

When a record fails normalization, it is inserted into `normalization_errors` rather than silently dropped:

| Error Code | Trigger Condition | Example Safe Message |
| :--- | :--- | :--- |
| `NORM_INVALID_TIMESTAMP` | Timestamp is missing, empty, or unparseable | "Unable to parse timestamp 'invalid-date' into UTC ISO-8601" |
| `NORM_INVALID_PAYLOAD` | Record JSON is corrupted or not a valid dictionary | "Record JSON payload is malformed or not an object" |
| `NORM_UNKNOWN_PARSER` | Parser profile is not supported by normalization engine | "No normalization mapper registered for parser 'unsupported'" |
| `NORM_SCHEMA_VIOLATION` | Normalized output fails schema contract constraints | "Missing required field 'event_type' in normalized output" |
