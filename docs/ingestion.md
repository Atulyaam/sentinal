# Project Sentinel — Data Ingestion Pipeline Guide
**Document Version:** 1.0.0  
**Sprint:** Sprint 2  

---

## 1. Architecture Overview

Project Sentinel's ingestion pipeline is designed around five non-negotiable architectural principles:
1. **Local-First & Isolated:** Ingestion processes files locally without external network dependencies. Database records are stored securely in user application data (`%LOCALAPPDATA%\ProjectSentinel\sentinel.db` on Windows).
2. **Deterministic & Strict:** Files are validated against explicit parser profiles (`generic_jsonl`, `auth_csv`, `web_access_csv`). Syntax errors are attributed to exact line numbers and persisted in `import_errors`.
3. **Idempotent by Design:** Files are hashed using SHA-256 before parsing. Re-importing an identical file with the same parser profile results in an automatic no-op (`skipped`, `duplicate=True`), preventing duplicated database records.
4. **Non-Destructive:** The ingestion pipeline **never deletes, moves, or alters original source log files**.
5. **Crash-Resilient:** Database operations occur in atomic transactions (`BEGIN IMMEDIATE`/`COMMIT`). Unfinished jobs from unexpected shutdowns reconcile automatically from `pending` to `failed` upon startup.

```text
       Manual Web Upload                     Approved Local Inbox
     (POST /api/import)                      (./inbox Polling)
              │                                      │
              └───────────────┬──────────────────────┘
                              ▼
                 [ Ingestion Pre-flight ]
                 ├── Path safety & symlink containment
                 ├── Size validation (max 20 MB)
                 └── Read-only SHA-256 hash calculation
                              │
                              ▼
                 [ Idempotency Query ]
                 ├── Query import_jobs by (sha256, parser_id, parser_version)
                 └── If exists: return status="skipped", duplicate=True
                              │
                              ▼ (New File)
                 [ Selected Parser Profile ]
                 ├── generic_jsonl: JSON objects, UTF-8 BOM strip
                 ├── auth_csv: SUCCESS, FAILURE, CHALLENGE, LOCKED
                 └── web_access_csv: HTTP verbs, status 100-599
                              │
                              ▼
                 [ Pre-Persistence Sanitizer ]
                 └── Scrub passwords, tokens, API keys, Bearer headers
                              │
                              ▼
                 [ Atomic SQLite Transaction ]
                 ├── INSERT INTO import_jobs (status: pending)
                 ├── INSERT INTO parsed_records (valid rows)
                 ├── INSERT INTO import_errors (invalid rows)
                 └── UPDATE import_jobs (status: completed / partial / failed)
```

---

## 2. Ingestion Methods

### 2.1 Manual Browser Upload (`POST /api/import`)
Operators can upload local files directly via the Sentinel Sources UI or HTTP clients.

#### Request Format A: Multipart Form Data
```http
POST /api/import HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary...

------WebKitFormBoundary...
Content-Disposition: form-data; name="parser_id"

generic_jsonl
------WebKitFormBoundary...
Content-Disposition: form-data; name="file"; filename="auth_audit.log"
Content-Type: text/plain

{"timestamp": "2026-11-09T08:00:00Z", "event_type": "login", "user": "alice"}
------WebKitFormBoundary...--
```

#### Request Format B: JSON Payload
```http
POST /api/import HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json

{
  "filename": "auth_audit.log",
  "parser_id": "generic_jsonl",
  "content_text": "{\"timestamp\": \"2026-11-09T08:00:00Z\", \"event_type\": \"login\", \"user\": \"alice\"}\n"
}
```

#### Response (Success - 200 OK)
```json
{
  "status": "completed",
  "duplicate": false,
  "import_id": "imp_7a8b9c0d1e2f",
  "source_id": "src_manual_default",
  "filename": "auth_audit.log",
  "sha256": "4fd49fe45b6ce638c52458d707298eaaddb6c2535ae840b8175737f976c455f1",
  "file_size": 81,
  "parser_id": "generic_jsonl",
  "parser_version": "1.0.0",
  "total_records": 1,
  "accepted_records": 1,
  "rejected_records": 0,
  "completed_at": "2026-11-09T08:00:01.123456+00:00",
  "errors": []
}
```

#### Response (Duplicate Skipped - 200 OK)
```json
{
  "status": "skipped",
  "duplicate": true,
  "import_id": "imp_7a8b9c0d1e2f",
  "source_id": "src_manual_default",
  "filename": "auth_audit.log",
  "sha256": "4fd49fe45b6ce638c52458d707298eaaddb6c2535ae840b8175737f976c455f1",
  "file_size": 81,
  "parser_id": "generic_jsonl",
  "parser_version": "1.0.0",
  "total_records": 1,
  "accepted_records": 1,
  "rejected_records": 0,
  "message": "Duplicate file already imported with this parser profile; ingestion skipped."
}
```

---

### 2.2 Approved Local Inbox Scanner
The background inbox scanner polls a single operator-approved local folder (configured via `SENTINEL_APPROVED_INBOX`, defaulting to `./inbox`).

#### Safety & Containment Rules:
1. **Path Safety:** Rejects filesystem roots (`/`, `C:\`), system folders (`C:\Windows`, `/etc`), and user home roots (`~`).
2. **Symlink Escape Defense:** Canonical resolution ensures files cannot point to targets outside the approved folder.
3. **Non-Recursive:** Subdirectories inside the inbox are completely ignored.
4. **Stability Check:** Files must maintain stable size across a polling interval before ingestion begins, preventing partial reads of in-flight writes.
5. **Non-Destructive:** Files remain in the inbox; subsequent polling cycles skip them via the SHA-256 idempotency check.
6. **Pause / Resume:** Can be paused programmatically without dropping state.

---

## 3. Query Endpoints

- `GET /api/parsers`: Returns all registered parser profiles (`generic_jsonl`, `auth_csv`, `web_access_csv`) and their descriptions.
- `GET /api/sources`: Returns registered sources (`src_manual_default`, `src_inbox_approved`).
- `GET /api/imports?limit=50&offset=0`: Returns paginated historical import jobs in reverse chronological order.
- `GET /api/imports/{import_id}`: Returns detailed job record along with its associated line error entries from `import_errors`.

---

## 4. Stage 2: Canonical Normalization Pipeline (Sprint 3)

Following successful ingestion into `parsed_records`, raw log events are converted into canonical security events conforming to `shared/contracts/event_contract.json`:

1. **Triggering Normalization:**
   - Endpoint: `POST /api/normalization/run`
   - Payload (optional): `{"import_id": "imp_...", "limit": 500}`
   - Result: `{"status": "success", "result": {"total_fetched": N, "accepted": N, "rejected": N, "skipped": N}}`
2. **Canonical Event Queries:**
   - `GET /api/events`: Paginated event stream supporting dynamic filters (`status`, `event_type`, `user_principal`, `source_id`, `import_id`).
   - `GET /api/events/{event_id}`: Full single event payload with provenance and deserialized attributes.
   - `GET /api/normalization/stats`: Pipeline summary metrics (total normalized events, pending unnormalized records, error count, and event breakdown).
   - `GET /api/normalization/errors`: Line-level diagnostic errors for unmappable records.
3. **Idempotency & Safe Reprocessing:**
   - Database constraint `(record_id, normalization_version)` ensures re-running normalization over historical imports never inserts duplicate canonical events.


