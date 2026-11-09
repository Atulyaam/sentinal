# Project Sentinel — Findings Schema & API Reference

## 1. Finding Architectural Model

A **Finding** in Project Sentinel represents an evidence-backed security anomaly produced by a deterministic detection rule.

Every finding is permanently linked to the concrete canonical events that generated it. A finding cannot exist without supporting evidence, and cannot make assertions beyond what the underlying canonical events prove.

```
+---------------------------------------------------------------------------------+
|                                     FINDING                                     |
+---------------------------------------------------------------------------------+
| finding_id          : find_3b12c87e1223b649cb2d2528                             |
| rule_id             : AUTH-001 (Repeated Authentication Failures)               |
| rule_version        : 1.0.0                                                     |
| rule_config_hash    : 9f82d1c68a412b10                                          |
| severity            : Medium                                                    |
| status              : open | acknowledged | resolved | dismissed                |
| title               : Repeated Authentication Failures for victim_user          |
| description         : Detected 5 failed attempts in 240 seconds                 |
| first_observed_at   : 2026-11-09T08:00:00Z                                      |
| last_observed_at    : 2026-11-09T08:04:00Z                                      |
| matched_entity      : victim_user                                               |
| matched_conditions  : {"failure_count": 5, "threshold": 5, "window_sec": 600}  |
| limitations         : Could be user error, forgotten password, or backup script |
| dedupe_key          : auth_fail:victim_user:2991093                             |
+---------------------------------------------------------------------------------+
          │
          │ Junction: finding_events (foreign key ON DELETE RESTRICT)
          ▼
+---------------------------------------------------------------------------------+
|                              SUPPORTING EVIDENCE                                |
+---------------------------------------------------------------------------------+
| evt_001 (2026-11-09T08:00:00Z | user_authentication | FAILURE | 198.51.100.22)  |
| evt_002 (2026-11-09T08:01:00Z | user_authentication | FAILURE | 198.51.100.22)  |
| evt_003 (2026-11-09T08:02:00Z | user_authentication | FAILURE | 198.51.100.22)  |
| evt_004 (2026-11-09T08:03:00Z | user_authentication | FAILURE | 198.51.100.22)  |
| evt_005 (2026-11-09T08:04:00Z | user_authentication | FAILURE | 198.51.100.22)  |
+---------------------------------------------------------------------------------+
```

---

## 2. Database Schema (Migration 004)

```sql
-- Detection rules catalogue table
CREATE TABLE IF NOT EXISTS detection_rules (
    rule_id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    config_hash TEXT NOT NULL,
    rule_definition_json TEXT NOT NULL,
    limitations TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Evidence-backed findings table
CREATE TABLE IF NOT EXISTS findings (
    finding_id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    rule_config_hash TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('Critical', 'High', 'Medium', 'Low', 'Info')),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'acknowledged', 'resolved', 'dismissed')),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    matched_entity TEXT,
    matched_conditions_json TEXT NOT NULL DEFAULT '{}',
    supporting_event_ids_json TEXT NOT NULL DEFAULT '[]',
    limitations TEXT NOT NULL,
    dedupe_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CONSTRAINT uq_finding_dedupe UNIQUE (rule_id, rule_version, dedupe_key),
    FOREIGN KEY (rule_id) REFERENCES detection_rules(rule_id) ON DELETE RESTRICT
);

-- Relational junction table linking findings to normalized evidence events
CREATE TABLE IF NOT EXISTS finding_events (
    finding_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (finding_id, event_id),
    FOREIGN KEY (finding_id) REFERENCES findings(finding_id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES normalized_events(event_id) ON DELETE RESTRICT
);

-- Audit table tracking rule evaluation execution runs
CREATE TABLE IF NOT EXISTS rule_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    evaluated_at TEXT NOT NULL,
    rule_count INTEGER NOT NULL,
    events_scanned INTEGER NOT NULL,
    findings_generated INTEGER NOT NULL,
    findings_duplicate INTEGER NOT NULL,
    duration_ms REAL NOT NULL
);
```

---

## 3. Finding Lifecycle & Status Transitions

Findings traverse four deterministic states:

```
                  ┌───────────────┐
                  │     open      │ (Initial state on creation)
                  └───────┬───────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
   ┌──────────────┐┌──────────────┐┌──────────────┐
   │ acknowledged ││   resolved   ││  dismissed   │
   └──────┬───────┘└──────────────┘└──────────────┘
          │               ▲
          └───────────────┘
```

1. **`open`**: Default initial state when a finding is produced.
2. **`acknowledged`**: The analyst has reviewed the finding and confirmed investigation is required.
3. **`resolved`**: Root cause addressed, credentials rotated, or firewall rule applied.
4. **`dismissed`**: Verified as benign activity, scheduled maintenance, or authorized testing.

### Idempotency & Re-evaluation Guarantee
When the detection engine executes repeatedly:
- If a finding with the same `(rule_id, rule_version, dedupe_key)` already exists, `INSERT OR IGNORE` suppresses duplication.
- An analyst's status transition (e.g., to `acknowledged` or `resolved`) is **preserved** and **never overwritten** back to `open` during re-evaluation.

---

## 4. REST API Specification

### 4.1 GET `/api/rules`
Returns all registered detection rules.

**Response (200 OK):**
```json
{
  "rules": [
    {
      "rule_id": "AUTH-001",
      "version": "1.0.0",
      "name": "Repeated Authentication Failures",
      "description": "Detects 5 or more failed authentications...",
      "severity": "Medium",
      "enabled": true,
      "config": {
        "target_event_type": "user_authentication",
        "target_status": "FAILURE",
        "threshold_count": 5,
        "window_seconds": 600
      },
      "limitations": "Could be user error..."
    }
  ],
  "total": 5
}
```

### 4.2 GET `/api/rules/{rule_id}`
Returns definition and configuration of a single rule.

**Response (200 OK):**
```json
{
  "rule_id": "AUTH-001",
  "version": "1.0.0",
  "name": "Repeated Authentication Failures",
  "severity": "Medium",
  "enabled": true,
  "config": { ... },
  "limitations": "..."
}
```

### 4.3 PATCH `/api/rules/{rule_id}`
Toggles rule enabled status.

**Request:**
```json
{
  "enabled": false
}
```

**Response (200 OK):**
```json
{
  "rule_id": "AUTH-001",
  "enabled": false,
  "status": "updated"
}
```

### 4.4 POST `/api/detection/run`
Triggers an immediate evaluation run of all enabled detection rules against normalized events.

**Response (200 OK):**
```json
{
  "status": "success",
  "result": {
    "evaluation_id": "eval_4c3fc7a0fce1",
    "evaluated_at": "2026-11-09T15:10:00Z",
    "rule_count": 5,
    "events_scanned": 120,
    "findings_generated": 2,
    "findings_duplicate": 0,
    "duration_ms": 1.45
  }
}
```

### 4.5 GET `/api/detection/stats`
Retrieves summary metrics across findings and the latest evaluation run.

**Response (200 OK):**
```json
{
  "total_findings": 14,
  "findings_by_severity": {
    "High": 3,
    "Medium": 8,
    "Info": 3
  },
  "findings_by_status": {
    "open": 9,
    "acknowledged": 3,
    "resolved": 2
  },
  "last_evaluation": {
    "evaluation_id": "eval_4c3fc7a0fce1",
    "evaluated_at": "2026-11-09T15:10:00Z",
    "rule_count": 5,
    "events_scanned": 120,
    "findings_generated": 2,
    "findings_duplicate": 0,
    "duration_ms": 1.45
  }
}
```

### 4.6 GET `/api/findings`
Lists findings with optional filtering and pagination.

**Query Parameters:**
- `severity`: Filter by `Critical`, `High`, `Medium`, `Low`, `Info`.
- `status`: Filter by `open`, `acknowledged`, `resolved`, `dismissed`.
- `rule_id`: Filter by rule (e.g., `AUTH-001`).
- `limit`: Number of records (default 50, max 500).
- `offset`: Pagination offset (default 0).

**Response (200 OK):**
```json
{
  "findings": [
    {
      "finding_id": "find_3b12c87e1223b649cb2d2528",
      "rule_id": "AUTH-001",
      "rule_version": "1.0.0",
      "severity": "Medium",
      "status": "open",
      "title": "Repeated Authentication Failures for victim_user",
      "description": "Detected 5 failed authentication attempts...",
      "first_observed_at": "2026-11-09T08:00:00Z",
      "last_observed_at": "2026-11-09T08:04:00Z",
      "matched_entity": "victim_user",
      "matched_conditions": {
        "failure_count": 5,
        "threshold": 5,
        "window_seconds": 600
      },
      "supporting_event_ids": [
        "evt_001",
        "evt_002",
        "evt_003",
        "evt_004",
        "evt_005"
      ],
      "limitations": "Could be user error...",
      "created_at": "2026-11-09T08:05:00Z",
      "updated_at": "2026-11-09T08:05:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### 4.7 GET `/api/findings/{finding_id}`
Retrieves a single finding by ID, joined with its full supporting canonical events.

**Response (200 OK):**
```json
{
  "finding_id": "find_3b12c87e1223b649cb2d2528",
  "rule_id": "AUTH-001",
  "severity": "Medium",
  "status": "open",
  "title": "Repeated Authentication Failures for victim_user",
  "matched_conditions": { ... },
  "supporting_events": [
    {
      "event_id": "evt_001",
      "timestamp": "2026-11-09T08:00:00Z",
      "event_type": "user_authentication",
      "user_principal": "victim_user",
      "source_ip": "198.51.100.22",
      "status": "FAILURE",
      "source_file": "auth.csv",
      "source_line": 2,
      "attributes": { ... }
    }
  ],
  "limitations": "..."
}
```

### 4.8 PATCH `/api/findings/{finding_id}`
Updates finding status.

**Request:**
```json
{
  "status": "acknowledged"
}
```

**Response (200 OK):**
```json
{
  "finding_id": "find_3b12c87e1223b649cb2d2528",
  "status": "acknowledged",
  "updated_at": "2026-11-09T15:15:00Z"
}
```

