# Project Sentinel — Phase 4 Detection Architecture & Design Specification
**Document Version:** 1.0.0  
**Status:** Approved for Implementation  
**Sprint:** Sprint 4 (Deterministic Detection Rules & Explainable Findings)  

---

## 1. Executive Summary & Purpose

Phase 2 established secure log ingestion and redaction into `parsed_records`. Phase 3 established deterministic canonical event normalization, timezone enforcement, and provenance tracking into `normalized_events`.

Phase 4 introduces the **Deterministic Detection Engine**:
An explainable, deterministic rule engine that evaluates canonical security events and generates evidence-backed security findings conforming to the master plan specification (`Project_Sentinel_Kiroween_2026_WINNING_MASTER_PLAN_v3.md`).

### Architectural Principles:
1. **Strict Determinism:** Rule evaluation is a pure function over canonical event records within bounded time windows. Given the same canonical events, rule definitions, and configurations, the engine always yields the exact same findings.
2. **Zero Hallucination / Zero Heuristics:** No machine learning, probabilistic models, or LLMs are used to generate findings. Every finding represents an exact match of deterministic criteria.
3. **Proof-Carrying Evidence Linkage:** Every generated finding explicitly links to the specific canonical `event_id`s that triggered it, stored in a relational junction table (`finding_events`).
4. **Stable Finding Identity & Deduplication:** Findings carry a deterministic `finding_id` derived via SHA-256 from the rule ID, rule version, configuration hash, and entity time-window dedupe key. Re-evaluating the same events prevents duplicate findings via SQLite unique constraints.
5. **Explainability & Documented Limitations:** Every finding records its matched conditions, threshold values, window boundaries, and explicit limitations (e.g., "Could be user error or misconfigured client").
6. **Defensive Boundaries:** The engine is purely analytical and read-only with respect to events and system state. It does not perform offensive actions, scanning, or autonomous remediation.

---

## 2. Canonical Event Input Contract

The detection engine reads strictly from `normalized_events` (and `normalization_errors` for data quality monitoring). It consumes records conforming to `shared/contracts/event_contract.json`:

```json
{
  "event_id": "evt_8f3a1b0c9e7d5f2a1b4c6e8d",
  "timestamp": "2026-11-09T08:00:15Z",
  "source_type": "auth_csv",
  "source_file": "auth_audit.csv",
  "source_line": 42,
  "source_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "event_type": "user_authentication",
  "user_principal": "alice",
  "source_ip": "192.168.1.100",
  "target_resource": null,
  "status": "FAILURE",
  "attributes": {}
}
```

Rules access canonical top-level fields directly (`event_type`, `user_principal`, `source_ip`, `target_resource`, `status`, `timestamp`) and nested attributes safely through dictionary lookups.

---

## 3. Rule Definition Model & Registry

### 3.1 Rule Schema
Rules are versioned, immutable definitions registered in the engine:

```json
{
  "rule_id": "AUTH-001",
  "version": "1.0.0",
  "name": "Repeated Authentication Failures",
  "description": "Detects 5 or more failed authentications for the same user within a 10-minute window.",
  "severity": "Medium",
  "enabled": true,
  "config": {
    "target_event_type": "user_authentication",
    "target_status": "FAILURE",
    "entity_field": "user_principal",
    "threshold_count": 5,
    "window_seconds": 600
  },
  "limitations": "Could be user error, forgotten password, or misconfigured client.",
  "config_hash": "a1b2c3d4..."
}
```

### 3.2 Configuration Hashing
To preserve historical provenance across rule updates, each rule computes a SHA-256 hash over its canonical configuration JSON:
$$\text{config\_hash} = \text{SHA256}(\text{json\_canonical}(\text{config}))[0:16]$$
If rule parameters (e.g. threshold count or window seconds) are modified, the version must increment and the configuration hash updates accordingly.

---

## 4. Initial Rule Catalogue (Sprint 4)

Conforming to Section 6.4 of the Master Plan:

### 4.1 `AUTH-001`: Repeated Authentication Failures
- **Default Severity:** `Medium`
- **Logic:** $\ge 5$ failed authentications (`status == 'FAILURE'`) for the same `user_principal` within a rolling 10-minute window (600 seconds).
- **Entity Key:** `user_principal` (non-null).
- **Evidence:** The $\ge 5$ failed authentication `event_id`s in chronological order.
- **Dedupe Key:** `auth_fail:{user_principal}:{window_bucket}`
- **Limitations:** "Could be user error or misconfigured client."

### 4.2 `AUTH-002`: Success After Authentication Failures
- **Default Severity:** `High`
- **Logic:** A successful authentication (`status == 'SUCCESS'`) occurring within 30 minutes (1800 seconds) after an `AUTH-001` failure burst for the same user.
- **Entity Key:** `user_principal` (non-null).
- **Evidence:** The preceding failure burst event IDs plus the subsequent successful login event ID.
- **Dedupe Key:** `auth_succ_after_fail:{user_principal}:{success_event_id}`
- **Limitations:** "Does not identify the human at the keyboard; credentials may have been guessed or legitimately recalled."

### 4.3 `WEB-001`: Sensitive Route Burst
- **Default Severity:** `Medium`
- **Logic:** $\ge 3$ requests to configured sensitive routes (`/admin/*`, `/api/v1/auth/*`, `/login`, `/wp-admin/*`, `/internal/*`) from the same `source_ip` within 15 minutes (900 seconds).
- **Entity Key:** `source_ip` (non-null).
- **Evidence:** The matching web request `event_id`s.
- **Dedupe Key:** `sensitive_route:{source_ip}:{window_bucket}`
- **Limitations:** "Route access may be legitimate administrative activity; inspect status codes (200 vs 403)."

### 4.4 `PRIV-001`: Explicit Privilege Escalation / Change
- **Default Severity:** `High`
- **Logic:** Any event indicating role alteration, administrative privilege grant, or sudo/privilege escalation (`event_type` in `('role_changed', 'privilege_granted', 'admin_escalation', 'group_add')` or attributes action `grant_role`).
- **Entity Key:** `user_principal` (or `target_resource`).
- **Evidence:** The privilege alteration `event_id`.
- **Dedupe Key:** `priv_change:{event_id}`
- **Limitations:** "Depends on source event quality; may be authorized administrator assignment."

### 4.5 `INGEST-001`: Timestamp & Ingestion Data Quality Anomaly
- **Default Severity:** `Info`
- **Logic:** Ingested records exhibiting date-time anomalies:
  - Records quarantined in `normalization_errors` (e.g. `NORM_TIMEZONE_UNKNOWN`, `NORM_INVALID_TIMESTAMP`).
  - Events with timestamps dated $> 24\text{ hours}$ in the future.
- **Entity Key:** `source_file` (or `source_id`).
- **Evidence:** Associated `record_id`s or `event_id`s.
- **Dedupe Key:** `ingest_anomaly:{source_file}:{import_id}`
- **Limitations:** "Data-quality issue, clock skew, or log export error, not attack evidence."

---

## 5. Finding Data Model & Database Persistence

### 5.1 Tables (Migration 004)

```sql
-- 1. Detection Rules Registry
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

-- 2. Findings (Core Security Detections)
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

-- 3. Finding-to-Event Evidence Junction
CREATE TABLE IF NOT EXISTS finding_events (
    finding_id TEXT NOT NULL REFERENCES findings(finding_id) ON DELETE CASCADE,
    event_id TEXT NOT NULL REFERENCES normalized_events(event_id) ON DELETE RESTRICT,
    PRIMARY KEY (finding_id, event_id)
);

-- 4. Rule Evaluation Audit Log
CREATE TABLE IF NOT EXISTS rule_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    evaluated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    rule_count INTEGER NOT NULL,
    events_scanned INTEGER NOT NULL,
    findings_generated INTEGER NOT NULL,
    findings_duplicate INTEGER NOT NULL,
    duration_ms REAL NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_findings_rule_id ON findings(rule_id);
CREATE INDEX IF NOT EXISTS idx_findings_severity ON findings(severity);
CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status);
CREATE INDEX IF NOT EXISTS idx_findings_observed ON findings(last_observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_finding_events_event ON finding_events(event_id);
```

### 5.2 Deterministic Finding Identity Formula
To prevent duplication across re-runs while preserving rule version history:
$$\text{Seed} = \text{rule\_id} \,\|\, \text{rule\_version} \,\|\, \text{rule\_config\_hash} \,\|\, \text{dedupe\_key}$$
$$\text{finding\_id} = \text{"find\_"} + \text{SHA256}(\text{Seed})[0:24]$$

---

## 6. Evaluation Lifecycle & Re-Evaluation Policy

1. **Triggering:** Operator-initiated via `POST /api/detection/run` or automated post-normalization.
2. **Event Selection:** Queries eligible `normalized_events` ordered chronologically by `timestamp ASC`.
3. **Execution:** Evaluates each enabled rule independently against its event filter criteria.
4. **Windowing:** Timestamps parsed into UTC epoch timestamps. Events grouped by entity and evaluated in rolling time windows.
5. **Persistence:** Transactional commit (`BEGIN IMMEDIATE ... COMMIT`). If a finding with the same `(rule_id, rule_version, dedupe_key)` exists:
   - `INSERT OR IGNORE` safely ignores duplicates, preserving initial status (`open`, `acknowledged`, etc.).
   - `last_observed_at` can be updated if new supporting events extend the window.
6. **Provenance Preservation:** Historical findings generated under older rule versions are never silently mutated or deleted when rules are updated.

---

## 7. Backend API Routes

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/rules` | List all registered rules, versions, and enabled states |
| `GET` | `/api/rules/{id}` | Inspect a single rule definition and parameters |
| `PATCH` | `/api/rules/{id}` | Enable or disable a rule |
| `POST` | `/api/detection/run` | Execute rule evaluation and return findings generation metrics |
| `GET` | `/api/detection/stats` | Summary metrics: total findings by severity and status |
| `GET` | `/api/findings` | Paginated findings list with severity, status, and rule filters |
| `GET` | `/api/findings/{id}` | Finding detail, explanation, matched conditions, limitations, evidence events |
| `PATCH` | `/api/findings/{id}` | Update finding status (`open`, `acknowledged`, `resolved`, `dismissed`) |

---

## 8. Frontend Integration (`FindingsView`)

- **Location:** Mounted at route `findings` in `apps/crew-app`.
- **Metrics Bar:** Real-time counts for Total Findings, Critical/High Findings, Open Findings, and Resolved Findings.
- **Action Bar:** "Run Detection" button triggering `POST /api/detection/run` with real progress indicator and result notification.
- **Filters:** Interactive dropdowns for Severity, Status, and Rule ID; search input across finding titles and entities.
- **Findings Table:** Columns for Title, Severity, Rule ID & Version, Matched Entity, Status, Observed Window, Supporting Events Count.
- **Detail Drawer / Modal:** Explains triggering rationale, matched conditions, rule limitations, and provides interactive links to view the supporting canonical events.
- **Rules Drawer:** Displays available detection rules and allows toggling enabled status.
