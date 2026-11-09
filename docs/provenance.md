# Project Sentinel — Data Provenance, Auditability & Evidence Integrity
**Document Version:** 1.1.0 (Audited & Hardened in Phase 3.5)  
**Status:** Canonical Reference  
**Target Sprints:** Sprint 2 (Ingestion), Sprint 3 (Normalization), Sprint 4+ (Findings & Cases)  

---

## 1. Core Philosophy: Proof-Carrying Evidence

Project Sentinel operates on the fundamental principle that **no security conclusion or AI-assisted synthesis should exist without a cryptographic chain of custody pointing back to physical evidence**.

In traditional SIEM and modern "AI SOC" architectures, events are frequently parsed, mutated, summarized, or aggregated in ways that destroy original formatting, drop raw line numbers, or obscure provenance. Sentinel treats raw data as an unalterable artifact:

1. **Source Preservation:** Original log files on disk are opened read-only and never modified or deleted.
2. **Cryptographic Identity:** Every imported file is identified by its SHA-256 hash calculated over raw bytes before parsing.
3. **Record-Level Lineage:** Every parsed record and every normalized canonical event preserves its 1-based physical row or line number in the source file.
4. **Deterministic Event Generation:** Normalized event identifiers (`event_id`) are mathematical derivations of file hash, line number, parser ID, parser version, and normalizer version. Reprocessing identical raw logs always yields identical event IDs.
5. **No Hallucinated Evidence:** AI summaries and automated detections (Claim Guard) must cite verifiable `event_id` and `finding_id` identifiers backed by SQLite records.

---

## 2. Provenance Architecture & Data Flow

The Sentinel data pipeline maintains complete bidirectional traceability across three persistence tiers:

```
+---------------------------------------------------------------+
|  1. Physical Source Log (Read-Only on Local Filesystem)       |
|     - Filename: auth_audit_20261109.csv                       |
|     - SHA-256: 065290f761cd1c58b8343cecbc575de604b21208...   |
+---------------------------------------------------------------+
                               |
                               v (Pre-persistence Secret Redaction)
+---------------------------------------------------------------+
|  2. Ingestion Tier: parsed_records (SQLite)                   |
|     - record_id: rec_3a9f0e1c2b5d                             |
|     - import_id: imp_f5b3c3fe880a                             |
|     - record_number: 42 (Physical 1-based line)               |
|     - parser_id: auth_csv                                     |
|     - parser_version: 1.0.0                                   |
|     - record_json: Sanitized pre-normalized payload           |
+---------------------------------------------------------------+
                               |
                               v (Canonical Normalization Engine)
+---------------------------------------------------------------+
|  3. Canonical Tier: normalized_events (SQLite)                |
|     - event_id: evt_86ab2363d929604a63e01e52 (Deterministic)  |
|     - timestamp: 2026-11-09T08:00:15Z (Strict UTC)            |
|     - source_type: auth_csv                                   |
|     - source_file: auth_audit_20261109.csv                    |
|     - source_line: 42                                         |
|     - source_sha256: 065290f761cd1c58b8343cecbc575de604b2... |
|     - parser_version: 1.0.0 (Self-contained parser version)   |
|     - normalization_version: 1.0.0                            |
|     - attributes: Typed key-values + provenance metadata      |
+---------------------------------------------------------------+
```

---

## 3. Deterministic Identity Formula

Every canonical event receives an `event_id` computed deterministically using the following formula:

$$\text{Seed} = \text{source\_sha256} \,\|\, \text{record\_number} \,\|\, \text{parser\_id} \,\|\, \text{parser\_version} \,\|\, \text{normalization\_version}$$

$$\text{event\_id} = \text{"evt\_"} + \text{SHA256}(\text{Seed})[0:24]$$

### Properties:
- **Reproducible:** Running normalization across identical ingested files reproduces the exact same `event_id`.
- **Deduplicated & Idempotent:** A unique constraint on `(record_id, normalization_version)` in SQLite prevents redundant inserts when normalization is triggered multiple times.
- **Traceable:** A security analyst inspecting `evt_86ab2363d929604a63e01e52` can immediately query its `source_file`, `source_line`, and `source_sha256` to examine the physical source line on disk.
- **Algorithm Version Sensitive:** Upgrading either the parser (`parser_version`) or the normalization schema (`normalization_version`) deterministically alters the identifier seed, preventing collision between differing semantic interpretations of the same raw byte offset.

---

## 4. Timestamp Normalization & Quarantine Policy

Security timelines depend entirely on consistent temporal alignment. Sentinel enforces strict timestamp normalization:

### 4.1 Timezone-Aware Sources
- Input strings specifying explicit timezone offsets (e.g. `2026-11-09T10:00:15+02:00` or `Z`) are converted to standard UTC `YYYY-MM-DDTHH:MM:SSZ`.
- For records whose original timestamp differed from the standard UTC format, the original string is preserved in `attributes["__provenance"]["original_timestamp"]`.

### 4.2 Naive Timestamps (No Timezone Offset Provided)
- When a log source provides timestamps lacking timezone information (e.g. `2026-11-09 08:00:15`), Sentinel **does not assume UTC or guess local machine time**. Assuming UTC for local timestamps introduces severe chronology errors into cross-source timeline reconstruction.
- The record is quarantined into `normalization_errors` under `error_code = "NORM_TIMEZONE_UNKNOWN"`.
- The raw record in `parsed_records` remains intact and queryable for manual inspection or future timezone-parameterized normalization passes.

### 4.3 Invalid or Missing Timestamps
- If a timestamp cannot be parsed into a valid date-time, Sentinel **never falls back to `datetime.now()`**.
- The record is rejected from `normalized_events` and logged in `normalization_errors` with code `NORM_INVALID_TIMESTAMP`.

---

## 5. Security & Threat Model Considerations

1. **Local Administrator Boundaries:**
   - Sentinel's SQLite database lives in the per-user application directory (`%LOCALAPPDATA%\ProjectSentinel\sentinel.db`).
   - SQLite is an embedded database; a root or administrative user with local filesystem access can modify or delete SQLite tables.
   - Sentinel claims **auditability, determinism, and evidence linkage**, not hardware tamper-proofing or cryptographic immutability against malicious local root.
2. **Path Traversal Protection:**
   - Filenames received via manual import or inbox scans are stripped of directory paths, POSIX slashes, and Windows backslashes (`sanitize_filename()`).
3. **Secret Redaction Integrity:**
   - Passwords, authorization headers, API keys, and bearer tokens are scrubbed prior to persistence in `parsed_records` and carried through to `normalized_events`.
