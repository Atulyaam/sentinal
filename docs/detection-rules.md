# Project Sentinel — Detection Rules Specification

## 1. Architectural Philosophy

Project Sentinel adheres to a **deterministic, evidence-backed detection architecture**. Unlike probabilistic or opaque machine learning models that generate unexplainable risk scores, Sentinel's detection rules evaluate canonical events through deterministic sliding windows and state transitions.

### Non-Negotiable Detection Principles:
1. **Zero Black-Box Scoring:** Every finding cites the specific rule ID, rule version, configuration hash, and concrete canonical event IDs that triggered it.
2. **Deterministic Finding IDs:** Finding identifiers are computed via a collision-resistant SHA-256 seed incorporating `rule_id`, `rule_version`, `config_hash`, and a window-bucketed `dedupe_key`:
   $$\text{Seed} = \text{rule\_id} : \text{rule\_version} : \text{rule\_config\_hash} : \text{dedupe\_key}$$
   $$\text{finding\_id} = \text{"find\_"} + \text{SHA256}(\text{Seed})[0:24]$$
3. **Explicit Analyst Limitations:** Every rule explicitly includes analyst limitations and alternative hypotheses directly in the generated finding to prevent premature conclusions and confirmation bias.
4. **Relational Evidence Integrity:** Findings are relational entities linked via foreign keys to `normalized_events` in SQLite (`ON DELETE RESTRICT`). Evidence events cannot be deleted while linked to an active finding.
5. **Idempotent Re-evaluation:** Re-running the detection engine across previously evaluated events updates audit logs but suppresses duplicate findings via `uq_finding_dedupe UNIQUE (rule_id, rule_version, dedupe_key)`.

---

## 2. Detection Rule Schema

Every detection rule satisfies the strict schema validated by `validate_rule_definition()`:

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
    "threshold_count": 5,
    "window_seconds": 600
  },
  "limitations": "Could be user error, forgotten password, or misconfigured automated client script."
}
```

### Configuration Hashing
To track rule configuration changes across evaluations, each rule configuration dictionary is serialized to canonical JSON (`separators=(',', ':')`, `sort_keys=True`) and hashed using SHA-256. A modification to any parameter (e.g., threshold from 5 to 3) alters the configuration hash, ensuring findings generated under distinct criteria remain distinguishable in audit logs.

---

## 3. Built-in Detection Rules Catalogue

### 3.1 AUTH-001: Repeated Authentication Failures

- **Rule ID:** `AUTH-001`
- **Version:** `1.0.0`
- **Default Severity:** `Medium`
- **Category:** Authentication / Credential Access
- **MITRE ATT&CK Mapping:** T1110.001 (Brute Force: Password Guessing), T1110.003 (Password Spraying)
- **Description:** Detects repeated failed authentications for the same user identity within a sliding window.
- **Trigger Condition:**
  $$\sum \text{events where } \text{type} = \text{"user\_authentication"} \land \text{status} = \text{"FAILURE"} \ge 5 \text{ within } 600\text{s}$$
- **Default Config:**
  ```json
  {
    "target_event_type": "user_authentication",
    "target_status": "FAILURE",
    "threshold_count": 5,
    "window_seconds": 600
  }
  ```
- **Deduplication Strategy:** `auth_fail:{user_principal}:{epoch // window_seconds}`
- **Limitations:** User may have forgotten password, caps lock engaged, or an automated workstation backup/credential script may have expired credentials.

---

### 3.2 AUTH-002: Success After Authentication Failures

- **Rule ID:** `AUTH-002`
- **Version:** `1.0.0`
- **Default Severity:** `High`
- **Category:** Authentication / Initial Access
- **MITRE ATT&CK Mapping:** T1078 (Valid Accounts), T1110 (Brute Force)
- **Description:** Detects a successful authentication occurring within 30 minutes following an `AUTH-001` burst for the same user principal.
- **Trigger Condition:**
  A `SUCCESS` authentication event where timestamp $t_{\text{success}}$ satisfies:
  $$0 < (t_{\text{success}} - t_{\text{last\_fail}}) \le 1800\text{s}$$
  following a sequence of $\ge 5$ failures within 600s.
- **Default Config:**
  ```json
  {
    "failure_threshold": 5,
    "failure_window_seconds": 600,
    "success_window_seconds": 1800
  }
  ```
- **Deduplication Strategy:** `auth_succ_after_fail:{user_principal}:{success_event_id}`
- **Limitations:** Does not identify the human at the keyboard; credentials may have been legitimately remembered, password reset performed through secondary channel, or attacker successfully guessed password.

---

### 3.3 WEB-001: Sensitive Route Burst

- **Rule ID:** `WEB-001`
- **Version:** `1.0.0`
- **Default Severity:** `Medium`
- **Category:** Reconnaissance / Web Attack
- **MITRE ATT&CK Mapping:** T1190 (Exploit Public-Facing Application), T1595.002 (Vulnerability Scanning)
- **Description:** Detects rapid requests directed at sensitive administrative, configuration, or authentication endpoints from the same source IP or entity within 15 minutes.
- **Trigger Condition:**
  $$\sum \text{web requests to sensitive prefixes from source } S \ge 3 \text{ within } 900\text{s}$$
- **Default Config:**
  ```json
  {
    "sensitive_routes": [
      "/admin",
      "/api/v1/auth",
      "/login",
      "/wp-admin",
      "/internal",
      "/.env",
      "/config"
    ],
    "threshold_count": 3,
    "window_seconds": 900
  }
  ```
- **Deduplication Strategy:** `sensitive_route:{entity}:{epoch // window_seconds}`
- **Limitations:** May represent legitimate administrator activity; analysts must distinguish between successful access (HTTP 200) indicating breach and blocked attempts (HTTP 401/403/404) indicating scanning.

---

### 3.4 PRIV-001: Explicit Privilege Escalation / Role Change

- **Rule ID:** `PRIV-001`
- **Version:** `1.0.0`
- **Default Severity:** `High`
- **Category:** Privilege Escalation / Persistence
- **MITRE ATT&CK Mapping:** T1078.004 (Cloud Administration Accounts), T1098 (Account Manipulation)
- **Description:** Detects explicit security alterations involving administrative role assignment, permission grants, or privilege escalation.
- **Trigger Condition:**
  Any event where `event_type` is in `privilege_event_types` OR attributes include an action in `privilege_actions`.
- **Default Config:**
  ```json
  {
    "privilege_event_types": [
      "role_changed",
      "privilege_granted",
      "admin_escalation",
      "group_add",
      "role_assigned"
    ],
    "privilege_actions": [
      "grant_role",
      "assign_admin",
      "sudo",
      "privilege_escalation"
    ]
  }
  ```
- **Deduplication Strategy:** `priv_change:{event_id}`
- **Limitations:** Depends on source event quality; may represent authorized IT change management or administrative onboarding.

---

### 3.5 INGEST-001: Ingestion & Timestamp Data Quality Anomaly

- **Rule ID:** `INGEST-001`
- **Version:** `1.0.0`
- **Default Severity:** `Info`
- **Category:** Data Integrity / Defense Evasion / Telemetry Failure
- **MITRE ATT&CK Mapping:** T1070.006 (Timestomp), T1562.001 (Disable or Modify Tools)
- **Description:** Detects anomalous event timestamps (future-dated events $> 24$ hours) or quarantined records in `normalization_errors` (e.g., naive timestamps lacking explicit timezone offset).
- **Trigger Condition:**
  Event timestamp $t > t_{\text{current}} + 86400\text{s}$ OR occurrence of quarantined records in `normalization_errors`.
- **Default Config:**
  ```json
  {
    "max_future_seconds": 86400
  }
  ```
- **Deduplication Strategy:**
  - Future dates: `future_date:{event_id}`
  - Ingestion errors: `ingest_errors:{import_id}:{error_code}`
- **Limitations:** Data-quality defect, time-synchronization (NTP) failure, clock skew, or log export format misconfiguration; not direct proof of an attack.

---

## 4. Rule Evaluation Lifecycle

```
[Normalized Events (SQLite)] ───► [Detection Engine] ───► [Rule Registry]
                                        │                      │
                                        ▼                      ▼
                            [Sliding-Window Eval]     [AUTH/WEB/PRIV/INGEST]
                                        │
                                        ▼
                             [Dedupe Check: uq_finding_dedupe]
                                ├── Match Found ──► Suppress (Audit duplicate)
                                └── New Finding ──► Insert into `findings`
                                                    Insert FK into `finding_events`
                                                    Record in `rule_evaluations`
```

