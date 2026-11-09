"""Repository providing structured data access for ingestion and persistence."""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("sentinel.repository")


class IngestionRepository:
    """Manages transactional persistence for sources, import jobs, and parsed records."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ---------------------------------------------------------
    # Sources Management
    # ---------------------------------------------------------

    def get_or_create_source(
        self,
        source_id: str,
        source_name: str,
        parser_profile: str,
        configured_path: Optional[str] = None,
        enabled: int = 1,
    ) -> Dict[str, Any]:
        """Fetch an existing source or insert a new one."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM event_sources WHERE source_id = ?;", (source_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)

        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute("BEGIN IMMEDIATE;")
        try:
            self.conn.execute(
                """
                INSERT INTO event_sources (source_id, source_name, parser_profile, configured_path, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (source_id, source_name, parser_profile, configured_path, enabled, now, now),
            )
            self.conn.execute("COMMIT;")
        except Exception:
            self.conn.execute("ROLLBACK;")
            raise

        cursor.execute("SELECT * FROM event_sources WHERE source_id = ?;", (source_id,))
        return dict(cursor.fetchone())

    def list_sources(self) -> List[Dict[str, Any]]:
        """List all configured event sources."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM event_sources ORDER BY created_at ASC;")
        return [dict(row) for row in cursor.fetchall()]

    def get_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific source by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM event_sources WHERE source_id = ?;", (source_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_source(
        self,
        source_id: str,
        enabled: Optional[int] = None,
        configured_path: Optional[str] = None,
        parser_profile: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update source configuration."""
        source = self.get_source(source_id)
        if not source:
            return None

        updates = []
        params = []
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(enabled)
        if configured_path is not None:
            updates.append("configured_path = ?")
            params.append(configured_path)
        if parser_profile is not None:
            updates.append("parser_profile = ?")
            params.append(parser_profile)

        if not updates:
            return source

        updates.append("updated_at = ?")
        params.append(datetime.now(timezone.utc).isoformat())
        params.append(source_id)

        self.conn.execute("BEGIN IMMEDIATE;")
        try:
            self.conn.execute(
                f"UPDATE event_sources SET {', '.join(updates)} WHERE source_id = ?;",
                tuple(params),
            )
            self.conn.execute("COMMIT;")
        except Exception:
            self.conn.execute("ROLLBACK;")
            raise

        return self.get_source(source_id)

    # ---------------------------------------------------------
    # Import Jobs Management
    # ---------------------------------------------------------

    def find_import_by_hash(
        self, sha256: str, parser_id: str, parser_version: str
    ) -> Optional[Dict[str, Any]]:
        """Check if an identical file was already successfully imported with this parser profile."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM import_jobs 
            WHERE sha256 = ? AND parser_id = ? AND parser_version = ?
            ORDER BY started_at DESC LIMIT 1;
            """,
            (sha256, parser_id, parser_version),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def create_import_job(
        self,
        import_id: str,
        source_id: str,
        filename: str,
        sha256: str,
        file_size: int,
        parser_id: str,
        parser_version: str,
        status: str = "pending",
    ) -> Dict[str, Any]:
        """Record the initial registration of an import job."""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute("BEGIN IMMEDIATE;")
        try:
            self.conn.execute(
                """
                INSERT INTO import_jobs (
                    import_id, source_id, filename, sha256, file_size,
                    parser_id, parser_version, status, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    import_id, source_id, filename, sha256, file_size,
                    parser_id, parser_version, status, now
                ),
            )
            self.conn.execute("COMMIT;")
        except Exception:
            self.conn.execute("ROLLBACK;")
            raise

        return self.get_import_job(import_id)  # type: ignore

    def get_import_job(self, import_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve import job details including row errors."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM import_jobs WHERE import_id = ?;", (import_id,))
        row = cursor.fetchone()
        if not row:
            return None

        job = dict(row)
        cursor.execute(
            """
            SELECT error_id, record_number, error_code, safe_error_message
            FROM import_errors WHERE import_id = ? ORDER BY record_number ASC;
            """,
            (import_id,),
        )
        job["errors"] = [dict(r) for r in cursor.fetchall()]
        return job

    def list_import_jobs(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """List historical import jobs in reverse chronological order."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT import_id, source_id, filename, sha256, file_size, parser_id,
                   parser_version, status, total_records, accepted_records,
                   rejected_records, started_at, completed_at, error_summary
            FROM import_jobs
            ORDER BY started_at DESC
            LIMIT ? OFFSET ?;
            """,
            (limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]

    def persist_import_batch(
        self,
        import_id: str,
        status: str,
        total_records: int,
        accepted_records: int,
        rejected_records: int,
        records: List[Dict[str, Any]],
        errors: List[Dict[str, Any]],
        error_summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Atomically persist parsed records, parsing errors, and update job status."""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute("BEGIN IMMEDIATE;")
        try:
            # 1. Insert parsed records
            for rec in records:
                rec_id = f"rec_{uuid.uuid4().hex[:12]}"
                rec_json = json.dumps(rec.get("record", {}), ensure_ascii=False)
                self.conn.execute(
                    """
                    INSERT INTO parsed_records (record_id, import_id, record_number, parser_id, parser_version, record_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        rec_id,
                        import_id,
                        rec["record_number"],
                        rec["parser_id"],
                        rec["parser_version"],
                        rec_json,
                        now,
                    ),
                )

            # 2. Insert error entries
            for err in errors:
                err_id = f"err_{uuid.uuid4().hex[:12]}"
                self.conn.execute(
                    """
                    INSERT INTO import_errors (error_id, import_id, record_number, error_code, safe_error_message)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (
                        err_id,
                        import_id,
                        err["record_number"],
                        err["error_code"],
                        err["safe_error_message"],
                    ),
                )

            # 3. Update import job status
            self.conn.execute(
                """
                UPDATE import_jobs
                SET status = ?, total_records = ?, accepted_records = ?, rejected_records = ?,
                    completed_at = ?, error_summary = ?
                WHERE import_id = ?;
                """,
                (
                    status,
                    total_records,
                    accepted_records,
                    rejected_records,
                    now,
                    error_summary,
                    import_id,
                ),
            )
            self.conn.execute("COMMIT;")
        except Exception:
            self.conn.execute("ROLLBACK;")
            raise

        return self.get_import_job(import_id)  # type: ignore

    def reconcile_pending_jobs(self) -> int:
        """Mark any dangling 'pending' jobs as failed after server restart."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT count(*) FROM import_jobs WHERE status = 'pending';")
        count = cursor.fetchone()[0]
        if count > 0:
            now = datetime.now(timezone.utc).isoformat()
            self.conn.execute("BEGIN IMMEDIATE;")
            try:
                self.conn.execute(
                    """
                    UPDATE import_jobs
                    SET status = 'failed', completed_at = ?, error_summary = 'Server restarted during processing'
                    WHERE status = 'pending';
                    """,
                    (now,),
                )
                self.conn.execute("COMMIT;")
                logger.warning("Reconciled %d dangling pending import job(s) as failed.", count)
            except Exception:
                self.conn.execute("ROLLBACK;")
                raise
        return count

    # ---------------------------------------------------------
    # Canonical Normalization & Events Management (Phase 3)
    # ---------------------------------------------------------

    def get_unnormalized_records(
        self,
        import_id: Optional[str] = None,
        normalization_version: str = "1.0.0",
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Fetch parsed records that have not yet been normalized for the specified version."""
        cursor = self.conn.cursor()
        query = """
            SELECT pr.record_id, pr.import_id, pr.record_number, pr.parser_id, pr.parser_version,
                   pr.record_json, pr.created_at,
                   ij.source_id, ij.filename, ij.sha256
            FROM parsed_records pr
            JOIN import_jobs ij ON pr.import_id = ij.import_id
            LEFT JOIN normalized_events ne ON pr.record_id = ne.record_id AND ne.normalization_version = ?
            LEFT JOIN normalization_errors nerr ON pr.record_id = nerr.record_id
            WHERE ne.event_id IS NULL AND nerr.error_id IS NULL
        """
        params: List[Any] = [normalization_version]
        if import_id:
            query += " AND pr.import_id = ?"
            params.append(import_id)

        query += " ORDER BY pr.created_at ASC, pr.record_number ASC LIMIT ?;"
        params.append(limit)

        cursor.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]

    def persist_normalized_events_batch(
        self,
        events: List[Dict[str, Any]],
        errors: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        """Atomically persist a batch of normalized events and normalization errors."""
        now = datetime.now(timezone.utc).isoformat()
        persisted_events = 0
        persisted_errors = 0

        self.conn.execute("BEGIN IMMEDIATE;")
        try:
            # 1. Insert normalized events
            for evt in events:
                attrs_json = json.dumps(evt.get("attributes", {}), ensure_ascii=False)
                cursor = self.conn.execute(
                    """
                    INSERT OR IGNORE INTO normalized_events (
                        event_id, import_id, record_id, source_id, record_number,
                        timestamp, source_type, source_file, source_line, source_sha256,
                        event_type, user_principal, source_ip, target_resource,
                        status, attributes_json, parser_version, normalization_version, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        evt["event_id"],
                        evt["import_id"],
                        evt["record_id"],
                        evt["source_id"],
                        evt["record_number"],
                        evt["timestamp"],
                        evt["source_type"],
                        evt["source_file"],
                        evt["source_line"],
                        evt["source_sha256"],
                        evt["event_type"],
                        evt.get("user_principal"),
                        evt.get("source_ip"),
                        evt.get("target_resource"),
                        evt.get("status", "UNKNOWN"),
                        attrs_json,
                        evt.get("parser_version", "1.0.0"),
                        evt.get("normalization_version", "1.0.0"),
                        now,
                    ),
                )
                if cursor.rowcount > 0:
                    persisted_events += 1

            # 2. Insert normalization errors
            for err in errors:
                err_id = err.get("error_id") or f"nerr_{uuid.uuid4().hex[:12]}"
                cursor = self.conn.execute(
                    """
                    INSERT INTO normalization_errors (
                        error_id, record_id, import_id, record_number,
                        error_code, safe_error_message, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        err_id,
                        err["record_id"],
                        err["import_id"],
                        err["record_number"],
                        err["error_code"],
                        err["safe_error_message"],
                        now,
                    ),
                )
                if cursor.rowcount > 0:
                    persisted_errors += 1

            self.conn.execute("COMMIT;")
        except Exception:
            self.conn.execute("ROLLBACK;")
            raise

        return {"persisted_events": persisted_events, "persisted_errors": persisted_errors}

    def get_normalized_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single canonical normalized event with deserialized attributes."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT event_id, import_id, record_id, source_id, record_number,
                   timestamp, source_type, source_file, source_line, source_sha256,
                   event_type, user_principal, source_ip, target_resource,
                   status, attributes_json, parser_version, normalization_version, created_at
            FROM normalized_events
            WHERE event_id = ?;
            """,
            (event_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        event_dict = dict(row)
        attrs_raw = event_dict.pop("attributes_json", "{}")
        try:
            event_dict["attributes"] = json.loads(attrs_raw)
        except Exception:
            event_dict["attributes"] = {}
        return event_dict

    def list_normalized_events(
        self,
        limit: int = 50,
        offset: int = 0,
        event_type: Optional[str] = None,
        source_id: Optional[str] = None,
        user_principal: Optional[str] = None,
        status: Optional[str] = None,
        import_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List canonical normalized events with dynamic filtering and total match count."""
        cursor = self.conn.cursor()
        where_clauses: List[str] = []
        params: List[Any] = []

        if event_type:
            where_clauses.append("event_type = ?")
            params.append(event_type)
        if source_id:
            where_clauses.append("source_id = ?")
            params.append(source_id)
        if user_principal:
            where_clauses.append("user_principal = ?")
            params.append(user_principal)
        if status:
            where_clauses.append("status = ?")
            params.append(status)
        if import_id:
            where_clauses.append("import_id = ?")
            params.append(import_id)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Total count query
        count_query = f"SELECT COUNT(*) FROM normalized_events {where_sql};"
        cursor.execute(count_query, tuple(params))
        total_count = cursor.fetchone()[0]

        # Results query
        data_query = f"""
            SELECT event_id, import_id, record_id, source_id, record_number,
                   timestamp, source_type, source_file, source_line, source_sha256,
                   event_type, user_principal, source_ip, target_resource,
                   status, attributes_json, parser_version, normalization_version, created_at
            FROM normalized_events
            {where_sql}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?;
        """
        data_params = list(params) + [limit, offset]
        cursor.execute(data_query, tuple(data_params))

        results: List[Dict[str, Any]] = []
        for row in cursor.fetchall():
            row_dict = dict(row)
            attrs_raw = row_dict.pop("attributes_json", "{}")
            try:
                row_dict["attributes"] = json.loads(attrs_raw)
            except Exception:
                row_dict["attributes"] = {}
            results.append(row_dict)

        return results, total_count

    def list_normalization_errors(
        self, limit: int = 50, offset: int = 0, import_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List normalization errors."""
        cursor = self.conn.cursor()
        if import_id:
            cursor.execute(
                """
                SELECT error_id, record_id, import_id, record_number,
                       error_code, safe_error_message, created_at
                FROM normalization_errors
                WHERE import_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?;
                """,
                (import_id, limit, offset),
            )
        else:
            cursor.execute(
                """
                SELECT error_id, record_id, import_id, record_number,
                       error_code, safe_error_message, created_at
                FROM normalization_errors
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?;
                """,
                (limit, offset),
            )
        return [dict(row) for row in cursor.fetchall()]

    def get_normalization_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics about normalized events and pending records."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM normalized_events;")
        total_events = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM normalization_errors;")
        total_errors = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM parsed_records pr
            LEFT JOIN normalized_events ne ON pr.record_id = ne.record_id
            LEFT JOIN normalization_errors nerr ON pr.record_id = nerr.record_id
            WHERE ne.event_id IS NULL AND nerr.error_id IS NULL;
            """
        )
        pending_records = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT event_type, COUNT(*) as count
            FROM normalized_events
            GROUP BY event_type
            ORDER BY count DESC;
            """
        )
        by_type = {row["event_type"]: row["count"] for row in cursor.fetchall()}

        return {
            "total_normalized_events": total_events,
            "total_normalization_errors": total_errors,
            "pending_unnormalized_records": pending_records,
            "events_by_type": by_type,
        }

    # ---------------------------------------------------------
    # Detection Rules & Findings Management (Phase 4)
    # ---------------------------------------------------------

    def persist_findings_batch(self, findings: List[Any]) -> Dict[str, int]:
        """Atomically persist a batch of findings and evidence links in SQLite."""
        now = datetime.now(timezone.utc).isoformat()
        persisted = 0
        duplicates = 0

        self.conn.execute("BEGIN IMMEDIATE;")
        try:
            for f in findings:
                f_dict = f.to_dict() if hasattr(f, "to_dict") else dict(f)
                matched_conds_json = json.dumps(f_dict.get("matched_conditions", {}), ensure_ascii=False)
                supp_events = f_dict.get("supporting_event_ids", [])
                supp_events_json = json.dumps(supp_events, ensure_ascii=False)

                cursor = self.conn.execute(
                    """
                    INSERT OR IGNORE INTO findings (
                        finding_id, rule_id, rule_version, rule_config_hash,
                        severity, status, title, description,
                        first_observed_at, last_observed_at, matched_entity,
                        matched_conditions_json, supporting_event_ids_json,
                        limitations, dedupe_key, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        f_dict["finding_id"],
                        f_dict["rule_id"],
                        f_dict["rule_version"],
                        f_dict["rule_config_hash"],
                        f_dict.get("severity", "Medium"),
                        f_dict.get("status", "open"),
                        f_dict["title"],
                        f_dict["description"],
                        f_dict["first_observed_at"],
                        f_dict["last_observed_at"],
                        f_dict.get("matched_entity"),
                        matched_conds_json,
                        supp_events_json,
                        f_dict.get("limitations", ""),
                        f_dict["dedupe_key"],
                        now,
                        now,
                    ),
                )
                if cursor.rowcount > 0:
                    persisted += 1
                    # Insert junction rows for supporting events
                    for evt_id in supp_events:
                        self.conn.execute(
                            """
                            INSERT OR IGNORE INTO finding_events (finding_id, event_id)
                            VALUES (?, ?);
                            """,
                            (f_dict["finding_id"], evt_id),
                        )
                else:
                    duplicates += 1

            self.conn.execute("COMMIT;")
        except Exception:
            self.conn.execute("ROLLBACK;")
            raise

        return {"persisted_findings": persisted, "duplicate_findings": duplicates}

    def get_finding(self, finding_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single finding with deserialized conditions and supporting events."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT finding_id, rule_id, rule_version, rule_config_hash,
                   severity, status, title, description,
                   first_observed_at, last_observed_at, matched_entity,
                   matched_conditions_json, supporting_event_ids_json,
                   limitations, dedupe_key, created_at, updated_at
            FROM findings
            WHERE finding_id = ?;
            """,
            (finding_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        finding_dict = dict(row)
        conds_raw = finding_dict.pop("matched_conditions_json", "{}")
        try:
            finding_dict["matched_conditions"] = json.loads(conds_raw)
        except Exception:
            finding_dict["matched_conditions"] = {}

        events_raw = finding_dict.pop("supporting_event_ids_json", "[]")
        try:
            finding_dict["supporting_event_ids"] = json.loads(events_raw)
        except Exception:
            finding_dict["supporting_event_ids"] = []

        # Fetch detailed supporting events from normalized_events
        if finding_dict["supporting_event_ids"]:
            placeholders = ",".join("?" for _ in finding_dict["supporting_event_ids"])
            cursor.execute(
                f"""
                SELECT event_id, timestamp, source_type, source_file, source_line,
                       source_sha256, event_type, user_principal, source_ip,
                       target_resource, status, attributes_json
                FROM normalized_events
                WHERE event_id IN ({placeholders})
                ORDER BY timestamp ASC;
                """,
                tuple(finding_dict["supporting_event_ids"]),
            )
            supporting_events = []
            for ev_row in cursor.fetchall():
                ev_dict = dict(ev_row)
                attr_raw = ev_dict.pop("attributes_json", "{}")
                try:
                    ev_dict["attributes"] = json.loads(attr_raw)
                except Exception:
                    ev_dict["attributes"] = {}
                supporting_events.append(ev_dict)
            finding_dict["supporting_events"] = supporting_events
        else:
            finding_dict["supporting_events"] = []

        return finding_dict

    def list_findings(
        self,
        limit: int = 50,
        offset: int = 0,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        rule_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List findings with optional filtering and pagination."""
        cursor = self.conn.cursor()
        where_clauses: List[str] = []
        params: List[Any] = []

        if severity:
            where_clauses.append("severity = ?")
            params.append(severity)
        if status:
            where_clauses.append("status = ?")
            params.append(status)
        if rule_id:
            where_clauses.append("rule_id = ?")
            params.append(rule_id)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Total count query
        count_query = f"SELECT COUNT(*) FROM findings {where_sql};"
        cursor.execute(count_query, tuple(params))
        total_count = cursor.fetchone()[0]

        # Results query
        data_query = f"""
            SELECT finding_id, rule_id, rule_version, rule_config_hash,
                   severity, status, title, description,
                   first_observed_at, last_observed_at, matched_entity,
                   matched_conditions_json, supporting_event_ids_json,
                   limitations, dedupe_key, created_at, updated_at
            FROM findings
            {where_sql}
            ORDER BY last_observed_at DESC, created_at DESC
            LIMIT ? OFFSET ?;
        """
        data_params = list(params) + [limit, offset]
        cursor.execute(data_query, tuple(data_params))

        results: List[Dict[str, Any]] = []
        for row in cursor.fetchall():
            item = dict(row)
            conds_raw = item.pop("matched_conditions_json", "{}")
            try:
                item["matched_conditions"] = json.loads(conds_raw)
            except Exception:
                item["matched_conditions"] = {}

            events_raw = item.pop("supporting_event_ids_json", "[]")
            try:
                item["supporting_event_ids"] = json.loads(events_raw)
            except Exception:
                item["supporting_event_ids"] = []

            results.append(item)

        return results, total_count

    def update_finding_status(self, finding_id: str, new_status: str) -> Optional[Dict[str, Any]]:
        """Update finding status with validation and transactional persistence."""
        valid_statuses = {"open", "acknowledged", "resolved", "dismissed"}
        status_clean = new_status.strip().lower()
        if status_clean not in valid_statuses:
            raise ValueError(f"Invalid finding status '{new_status}'. Must be one of {sorted(valid_statuses)}")

        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute("BEGIN IMMEDIATE;")
        try:
            cursor = self.conn.execute(
                """
                UPDATE findings
                SET status = ?, updated_at = ?
                WHERE finding_id = ?;
                """,
                (status_clean, now, finding_id),
            )
            if cursor.rowcount == 0:
                self.conn.execute("ROLLBACK;")
                return None
            self.conn.execute("COMMIT;")
        except Exception:
            self.conn.execute("ROLLBACK;")
            raise

        return self.get_finding(finding_id)

    def record_evaluation_audit(self, stats: Any) -> None:
        """Record rule evaluation statistics in audit log."""
        s = stats.to_dict() if hasattr(stats, "to_dict") else dict(stats)
        self.conn.execute(
            """
            INSERT INTO rule_evaluations (
                evaluation_id, evaluated_at, rule_count, events_scanned,
                findings_generated, findings_duplicate, duration_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                s["evaluation_id"],
                s["evaluated_at"],
                s["rule_count"],
                s["events_scanned"],
                s["findings_generated"],
                s["findings_duplicate"],
                s["duration_ms"],
            ),
        )

    def get_detection_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics about findings by severity and status."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM findings;")
        total_findings = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT severity, COUNT(*) as count
            FROM findings
            GROUP BY severity;
            """
        )
        by_severity = {row["severity"]: row["count"] for row in cursor.fetchall()}

        cursor.execute(
            """
            SELECT status, COUNT(*) as count
            FROM findings
            GROUP BY status;
            """
        )
        by_status = {row["status"]: row["count"] for row in cursor.fetchall()}

        cursor.execute(
            """
            SELECT evaluation_id, evaluated_at, rule_count, events_scanned,
                   findings_generated, findings_duplicate, duration_ms
            FROM rule_evaluations
            ORDER BY evaluated_at DESC
            LIMIT 1;
            """
        )
        last_eval_row = cursor.fetchone()
        last_eval = dict(last_eval_row) if last_eval_row else None

        return {
            "total_findings": total_findings,
            "findings_by_severity": by_severity,
            "findings_by_status": by_status,
            "last_evaluation": last_eval,
        }

    def list_detection_rules(self) -> List[Dict[str, Any]]:
        """List all rules stored in detection_rules table."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT rule_id, version, name, description, severity, enabled,
                   config_hash, rule_definition_json, created_at, updated_at
            FROM detection_rules
            ORDER BY rule_id ASC;
            """
        )
        rules: List[Dict[str, Any]] = []
        for row in cursor.fetchall():
            item = dict(row)
            cfg_raw = item.pop("rule_definition_json", "{}")
            try:
                item["config"] = json.loads(cfg_raw)
            except Exception:
                item["config"] = {}
            rules.append(item)
        return rules

    def get_detection_rule(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single rule definition from detection_rules table."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT rule_id, version, name, description, severity, enabled,
                   config_hash, rule_definition_json, created_at, updated_at
            FROM detection_rules
            WHERE rule_id = ?;
            """,
            (rule_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        item = dict(row)
        cfg_raw = item.pop("rule_definition_json", "{}")
        try:
            item["config"] = json.loads(cfg_raw)
        except Exception:
            item["config"] = {}
        return item

    def update_detection_rule_enabled(self, rule_id: str, enabled: bool) -> bool:
        """Toggle rule enabled status in detection_rules table."""
        now = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.execute(
            """
            UPDATE detection_rules
            SET enabled = ?, updated_at = ?
            WHERE rule_id = ?;
            """,
            (1 if enabled else 0, now, rule_id),
        )
        return cursor.rowcount > 0



