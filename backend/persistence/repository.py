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

        # If rule INGEST-001 or no supporting normalized events, check if matched_conditions has quarantined record_ids
        record_ids = finding_dict.get("matched_conditions", {}).get("record_ids", [])
        if record_ids:
            placeholders = ",".join("?" for _ in record_ids)
            cursor.execute(
                f"""
                SELECT error_id, record_id, import_id, record_number, error_code, safe_error_message, created_at
                FROM normalization_errors
                WHERE record_id IN ({placeholders})
                ORDER BY created_at ASC;
                """,
                tuple(record_ids),
            )
            finding_dict["quarantined_records"] = [dict(r) for r in cursor.fetchall()]
        else:
            finding_dict["quarantined_records"] = []

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

    # ---------------------------------------------------------
    # Investigation Cases & Deterministic Correlation (Phase 5)
    # ---------------------------------------------------------

    def persist_cases_batch(
        self,
        cases: List[Any],
        case_findings: List[Any],
        case_events: List[Any],
        relationships: Optional[List[Any]] = None,
    ) -> Dict[str, int]:
        """Atomically persist or update a batch of correlated investigation cases."""
        now = datetime.now(timezone.utc).isoformat()
        created = 0
        updated = 0

        self.conn.execute("BEGIN IMMEDIATE;")
        try:
            for c in cases:
                c_dict = c.to_dict() if hasattr(c, "to_dict") else dict(c)
                meta_json = json.dumps(c_dict.get("metadata", {}), ensure_ascii=False)

                # Check if case exists with matching dedupe_key
                cursor = self.conn.execute(
                    """
                    SELECT case_id, severity, status
                    FROM cases
                    WHERE correlation_key_type = ? AND correlation_key_value = ? AND dedupe_key = ?;
                    """,
                    (c_dict["correlation_key_type"], c_dict["correlation_key_value"], c_dict["dedupe_key"]),
                )
                existing = cursor.fetchone()

                if existing:
                    existing_case_id = existing[0]
                    existing_severity = existing[1]
                    from backend.cases.models import SEVERITY_RANK
                    target_sev = c_dict["severity"]
                    if SEVERITY_RANK.get(existing_severity, 0) > SEVERITY_RANK.get(target_sev, 0):
                        target_sev = existing_severity

                    # Update boundaries, metadata, updated_at, and severity (do not overwrite status!)
                    self.conn.execute(
                        """
                        UPDATE cases
                        SET first_observed_at = MIN(first_observed_at, ?),
                            last_observed_at = MAX(last_observed_at, ?),
                            description = ?,
                            updated_at = ?,
                            metadata_json = ?,
                            severity = ?
                        WHERE case_id = ?;
                        """,
                        (c_dict["first_observed_at"], c_dict["last_observed_at"], c_dict["description"], now, meta_json, target_sev, existing_case_id),
                    )
                    target_case_id = existing_case_id
                    updated += 1
                else:
                    self.conn.execute(
                        """
                        INSERT INTO cases (
                            case_id, title, description, status, severity,
                            correlation_key_type, correlation_key_value,
                            first_observed_at, last_observed_at, algorithm_version,
                            dedupe_key, metadata_json, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            c_dict["case_id"],
                            c_dict["title"],
                            c_dict["description"],
                            c_dict.get("status", "Open"),
                            c_dict["severity"],
                            c_dict["correlation_key_type"],
                            c_dict["correlation_key_value"],
                            c_dict["first_observed_at"],
                            c_dict["last_observed_at"],
                            c_dict.get("algorithm_version", "1.0.0"),
                            c_dict["dedupe_key"],
                            meta_json,
                            now,
                            now,
                        ),
                    )
                    target_case_id = c_dict["case_id"]
                    created += 1

                # Link findings
                for cf in case_findings:
                    cf_dict = cf.to_dict() if hasattr(cf, "to_dict") else dict(cf)
                    if cf_dict["case_id"] == c_dict["case_id"]:
                        self.conn.execute(
                            """
                            INSERT OR IGNORE INTO case_findings (case_id, finding_id, correlation_rationale, created_at)
                            VALUES (?, ?, ?, ?);
                            """,
                            (target_case_id, cf_dict["finding_id"], cf_dict["correlation_rationale"], now),
                        )

                # Link events
                for ce in case_events:
                    ce_dict = ce.to_dict() if hasattr(ce, "to_dict") else dict(ce)
                    if ce_dict["case_id"] == c_dict["case_id"]:
                        self.conn.execute(
                            """
                            INSERT OR IGNORE INTO case_events (case_id, event_id, relationship_type, correlation_rationale, created_at)
                            VALUES (?, ?, ?, ?, ?);
                            """,
                            (
                                target_case_id,
                                ce_dict["event_id"],
                                ce_dict.get("relationship_type", "correlated_evidence"),
                                ce_dict["correlation_rationale"],
                                now,
                            ),
                        )

            self.conn.execute("COMMIT;")
        except Exception:
            self.conn.execute("ROLLBACK;")
            raise

        return {"cases_created": created, "cases_updated": updated}

    def get_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a complete investigation case with findings, events, timeline, and review history."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT case_id, title, description, status, severity,
                   correlation_key_type, correlation_key_value,
                   first_observed_at, last_observed_at, algorithm_version,
                   dedupe_key, metadata_json, created_at, updated_at
            FROM cases
            WHERE case_id = ?;
            """,
            (case_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        case_dict = dict(row)
        meta_raw = case_dict.pop("metadata_json", "{}")
        try:
            case_dict["metadata"] = json.loads(meta_raw)
        except Exception:
            case_dict["metadata"] = {}
        case_dict["correlation_rationale"] = case_dict["metadata"].get("correlation_rationale", "")

        # 1. Fetch linked findings with full details and supporting events
        cursor.execute(
            """
            SELECT f.finding_id, f.rule_id, f.rule_version, f.rule_config_hash,
                   f.severity, f.status, f.title, f.description,
                   f.first_observed_at, f.last_observed_at, f.matched_entity,
                   f.matched_conditions_json, f.supporting_event_ids_json,
                   f.limitations, f.dedupe_key, cf.correlation_rationale
            FROM case_findings cf
            JOIN findings f ON cf.finding_id = f.finding_id
            WHERE cf.case_id = ?
            ORDER BY f.first_observed_at ASC;
            """,
            (case_id,),
        )
        findings = []
        for f_row in cursor.fetchall():
            f_item = dict(f_row)
            try:
                f_item["matched_conditions"] = json.loads(f_item.pop("matched_conditions_json", "{}"))
            except Exception:
                f_item["matched_conditions"] = {}
            try:
                f_item["supporting_event_ids"] = json.loads(f_item.pop("supporting_event_ids_json", "[]"))
            except Exception:
                f_item["supporting_event_ids"] = []
            findings.append(f_item)
        case_dict["findings"] = findings

        # 2. Fetch linked events with full canonical provenance
        cursor.execute(
            """
            SELECT ne.event_id, ne.timestamp, ne.source_type, ne.source_file,
                   ne.source_line, ne.source_sha256, ne.event_type,
                   ne.user_principal, ne.source_ip, ne.target_resource,
                   ne.status, ne.attributes_json, ce.relationship_type,
                   ce.correlation_rationale
            FROM case_events ce
            JOIN normalized_events ne ON ce.event_id = ne.event_id
            WHERE ce.case_id = ?
            ORDER BY ne.timestamp ASC;
            """,
            (case_id,),
        )
        events = []
        for e_row in cursor.fetchall():
            e_item = dict(e_row)
            try:
                e_item["attributes"] = json.loads(e_item.pop("attributes_json", "{}"))
            except Exception:
                e_item["attributes"] = {}
            events.append(e_item)
        case_dict["events"] = events

        # 3. Fetch review actions
        cursor.execute(
            """
            SELECT action_id, case_id, action_type, previous_status,
                   new_status, operator_note, author, created_at
            FROM review_actions
            WHERE case_id = ?
            ORDER BY created_at ASC;
            """,
            (case_id,),
        )
        reviews = [dict(r) for r in cursor.fetchall()]
        case_dict["review_actions"] = reviews

        # 4. Assemble chronological timeline
        timeline: List[Dict[str, Any]] = []

        # Add events to timeline
        for ev in events:
            timeline.append({
                "item_id": f"tl_evt_{ev['event_id']}",
                "item_type": "event",
                "timestamp": ev["timestamp"],
                "title": f"Canonical Event: {ev['event_type']} ({ev['status']})",
                "description": f"Source: {ev['source_file']}:{ev['source_line']} | User: {ev.get('user_principal') or 'none'} | IP: {ev.get('source_ip') or 'none'} | Target: {ev.get('target_resource') or 'none'}",
                "severity": None,
                "data": ev,
            })

        # Add findings to timeline
        for f in findings:
            timeline.append({
                "item_id": f"tl_find_{f['finding_id']}",
                "item_type": "finding",
                "timestamp": f["first_observed_at"],
                "title": f"Detection: [{f['rule_id']}] {f['title']}",
                "description": f"{f['description']} (Severity: {f['severity']}, Entity: {f.get('matched_entity') or 'none'})",
                "severity": f["severity"],
                "data": f,
            })

        # Add review actions & status changes to timeline
        for rev in reviews:
            if rev["action_type"] == "status_changed":
                t_title = f"Status Changed: {rev['previous_status']} -> {rev['new_status']}"
                t_desc = f"Operator: {rev['author']}"
                if rev["operator_note"]:
                    t_desc += f" — Note: {rev['operator_note']}"
                timeline.append({
                    "item_id": f"tl_act_{rev['action_id']}",
                    "item_type": "status_change",
                    "timestamp": rev["created_at"],
                    "title": t_title,
                    "description": t_desc,
                    "severity": None,
                    "data": rev,
                })
            else:
                timeline.append({
                    "item_id": f"tl_act_{rev['action_id']}",
                    "item_type": "review_action",
                    "timestamp": rev["created_at"],
                    "title": f"Operator Note by {rev['author']}",
                    "description": rev["operator_note"],
                    "severity": None,
                    "data": rev,
                })

        # Add correlation summary to timeline
        if case_dict.get("metadata", {}).get("correlation_rationale"):
            timeline.append({
                "item_id": f"tl_corr_{case_dict['case_id']}",
                "item_type": "correlation",
                "timestamp": case_dict["first_observed_at"],
                "title": f"Deterministic Correlation [{case_dict['correlation_key_type']}={case_dict['correlation_key_value']}]",
                "description": case_dict["metadata"]["correlation_rationale"],
                "severity": case_dict["severity"],
                "data": {
                    "key_type": case_dict["correlation_key_type"],
                    "key_value": case_dict["correlation_key_value"],
                    "window_seconds": case_dict["metadata"].get("window_seconds"),
                    "algorithm_version": case_dict["algorithm_version"],
                    "severity_derivation": case_dict["metadata"].get("severity_derivation"),
                },
            })

        # Sort timeline chronologically with deterministic logical tiebreaker
        timeline_type_order = {
            "event": 1,
            "finding": 2,
            "correlation": 3,
            "status_change": 4,
            "review_action": 5,
        }
        timeline.sort(
            key=lambda item: (
                item.get("timestamp") or "",
                timeline_type_order.get(item.get("item_type"), 99),
                item.get("item_id", ""),
            )
        )
        case_dict["timeline"] = timeline

        # 5. Fetch verified, qualified and blocked claims for case (Phase 6)
        try:
            case_dict["claims"] = self.list_case_claims(case_id)
        except Exception:
            case_dict["claims"] = []

        return case_dict

    def list_cases(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        correlation_key_type: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List cases with optional filtering, pagination, search, and evidence counts."""
        cursor = self.conn.cursor()
        where_clauses: List[str] = []
        params: List[Any] = []

        if status:
            where_clauses.append("c.status = ?")
            params.append(status)
        if severity:
            where_clauses.append("c.severity = ?")
            params.append(severity)
        if correlation_key_type:
            where_clauses.append("c.correlation_key_type = ?")
            params.append(correlation_key_type)
        if search and str(search).strip():
            s = f"%{str(search).strip()}%"
            where_clauses.append("(c.title LIKE ? OR c.case_id LIKE ? OR c.correlation_key_value LIKE ?)")
            params.extend([s, s, s])

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        # Total count query
        count_query = f"SELECT COUNT(*) FROM cases c {where_sql};"
        cursor.execute(count_query, tuple(params))
        total_count = cursor.fetchone()[0]

        # Data query with counts of linked findings and events
        data_query = f"""
            SELECT c.case_id, c.title, c.description, c.status, c.severity,
                   c.correlation_key_type, c.correlation_key_value,
                   c.first_observed_at, c.last_observed_at, c.algorithm_version,
                   c.dedupe_key, c.metadata_json, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM case_findings cf WHERE cf.case_id = c.case_id) AS finding_count,
                   (SELECT COUNT(*) FROM case_events ce WHERE ce.case_id = c.case_id) AS event_count,
                   (SELECT COUNT(*) FROM review_actions ra WHERE ra.case_id = c.case_id) AS review_count
            FROM cases c
            {where_sql}
            ORDER BY c.updated_at DESC
            LIMIT ? OFFSET ?;
        """
        data_params = list(params) + [limit, offset]
        cursor.execute(data_query, tuple(data_params))

        cases: List[Dict[str, Any]] = []
        for row in cursor.fetchall():
            item = dict(row)
            try:
                item["metadata"] = json.loads(item.pop("metadata_json", "{}"))
            except Exception:
                item["metadata"] = {}
            cases.append(item)

        return cases, total_count

    def update_case_status(
        self,
        case_id: str,
        new_status: str,
        operator_note: str = "",
        author: str = "secops_operator",
    ) -> Optional[Dict[str, Any]]:
        """Validate and apply a case status transition, appending an immutable review action."""
        if operator_note and len(str(operator_note)) > 10000:
            raise ValueError("Operator note exceeds maximum allowed length of 10,000 characters.")
        if author and len(str(author)) > 100:
            raise ValueError("Author exceeds maximum allowed length of 100 characters.")

        cursor = self.conn.cursor()
        cursor.execute("SELECT status FROM cases WHERE case_id = ?;", (case_id,))
        row = cursor.fetchone()
        if not row:
            return None

        current_status = row[0]
        from backend.cases.models import validate_status_transition
        validate_status_transition(current_status, new_status)

        now = datetime.now(timezone.utc).isoformat()
        act_id = f"act_{uuid.uuid4().hex[:16]}"

        self.conn.execute("BEGIN IMMEDIATE;")
        try:
            self.conn.execute(
                "UPDATE cases SET status = ?, updated_at = ? WHERE case_id = ?;",
                (new_status, now, case_id),
            )
            self.conn.execute(
                """
                INSERT INTO review_actions (
                    action_id, case_id, action_type, previous_status,
                    new_status, operator_note, author, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    act_id,
                    case_id,
                    "status_changed",
                    current_status,
                    new_status,
                    operator_note or f"Status transitioned from {current_status} to {new_status}",
                    author,
                    now,
                ),
            )
            self.conn.execute("COMMIT;")
        except Exception:
            self.conn.execute("ROLLBACK;")
            raise

        return self.get_case(case_id)

    def add_case_note(
        self,
        case_id: str,
        operator_note: str,
        author: str = "secops_operator",
    ) -> Optional[Dict[str, Any]]:
        """Append an operator note to a case without changing status."""
        if not operator_note or not str(operator_note).strip():
            raise ValueError("Operator note cannot be empty.")
        if len(str(operator_note)) > 10000:
            raise ValueError("Operator note exceeds maximum allowed length of 10,000 characters.")
        if author and len(str(author)) > 100:
            raise ValueError("Author exceeds maximum allowed length of 100 characters.")

        cursor = self.conn.cursor()
        cursor.execute("SELECT status FROM cases WHERE case_id = ?;", (case_id,))
        row = cursor.fetchone()
        if not row:
            return None

        current_status = row[0]
        now = datetime.now(timezone.utc).isoformat()
        act_id = f"act_{uuid.uuid4().hex[:16]}"

        self.conn.execute("BEGIN IMMEDIATE;")
        try:
            self.conn.execute(
                "UPDATE cases SET updated_at = ? WHERE case_id = ?;",
                (now, case_id),
            )
            self.conn.execute(
                """
                INSERT INTO review_actions (
                    action_id, case_id, action_type, previous_status,
                    new_status, operator_note, author, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (act_id, case_id, "note_added", current_status, current_status, operator_note.strip(), author, now),
            )
            self.conn.execute("COMMIT;")
        except Exception:
            self.conn.execute("ROLLBACK;")
            raise

        return self.get_case(case_id)

    def get_case_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics across investigation cases."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM cases;")
        total_cases = cursor.fetchone()[0]

        cursor.execute("SELECT status, COUNT(*) FROM cases GROUP BY status;")
        by_status = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute("SELECT severity, COUNT(*) FROM cases GROUP BY severity;")
        by_severity = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute(
            """
            SELECT evaluation_id, evaluated_at, findings_scanned, events_scanned,
                   cases_created, cases_updated, duration_ms
            FROM correlation_evaluations
            ORDER BY evaluated_at DESC
            LIMIT 1;
            """
        )
        last_eval_row = cursor.fetchone()
        last_eval = dict(last_eval_row) if last_eval_row else None

        return {
            "total_cases": total_cases,
            "total": total_cases,
            "cases_by_status": by_status,
            "by_status": by_status,
            "cases_by_severity": by_severity,
            "by_severity": by_severity,
            "last_evaluation": last_eval,
        }

    def record_correlation_evaluation(self, audit_record: Dict[str, Any]) -> None:
        """Record correlation engine execution metrics into audit table."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO correlation_evaluations (
                evaluation_id, evaluated_at, findings_scanned, events_scanned,
                cases_created, cases_updated, duration_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                audit_record["evaluation_id"],
                audit_record["evaluated_at"],
                audit_record["findings_scanned"],
                audit_record["events_scanned"],
                audit_record["cases_created"],
                audit_record["cases_updated"],
                audit_record["duration_ms"],
            ),
        )
        self.conn.commit()

    # ---------------------------------------------------------
    # Claim Guard Management (Phase 6)
    # ---------------------------------------------------------

    def persist_claim_proposal(self, proposal: Any) -> None:
        """Persist an agent claim proposal into claim_proposals table."""
        if hasattr(proposal, "to_dict"):
            p_data = proposal.to_dict()
        else:
            p_data = proposal

        self.conn.execute(
            """
            INSERT OR IGNORE INTO claim_proposals (
                claim_id, case_id, claim_type, predicate, value_json,
                evidence_refs_json, certainty, template_id, proposed_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                p_data["claim_id"],
                p_data["case_id"],
                p_data["claim_type"],
                p_data["predicate"],
                json.dumps(p_data.get("value", {})),
                json.dumps(p_data.get("evidence_refs", [])),
                p_data.get("certainty", "observed"),
                p_data.get("template_id", "case_event_count_v1"),
                p_data.get("proposed_by", "kiro_crew_agent"),
                p_data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()

    def persist_claim_verification(self, verification: Any) -> None:
        """Persist a claim verification result into claim_verifications table."""
        if hasattr(verification, "to_dict"):
            v_data = verification.to_dict()
        else:
            v_data = verification

        checks = v_data.get("checks", [])
        checks_serialized = [c.to_dict() if hasattr(c, "to_dict") else c for c in checks]

        self.conn.execute(
            """
            INSERT OR REPLACE INTO claim_verifications (
                verification_id, claim_id, case_id, status, verification_version,
                checks_json, rendered_text, qualification_notes_json,
                blocked_reasons_json, suggested_remedy, evidence_refs_json, verified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                v_data["verification_id"],
                v_data["claim_id"],
                v_data["case_id"],
                v_data["status"],
                v_data.get("verification_version", "1.0.0"),
                json.dumps(checks_serialized),
                v_data["rendered_text"],
                json.dumps(v_data.get("qualification_notes", [])),
                json.dumps(v_data.get("blocked_reasons", [])),
                v_data.get("suggested_remedy"),
                json.dumps(v_data.get("evidence_refs", [])),
                v_data.get("verified_at") or datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()

    def get_claim(self, claim_id: str) -> Optional[Dict[str, Any]]:
        """Fetch claim proposal and latest verification result by claim_id."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT p.claim_id, p.case_id, p.claim_type, p.predicate, p.value_json,
                   p.evidence_refs_json, p.certainty, p.template_id, p.proposed_by, p.created_at,
                   v.verification_id, v.status, v.verification_version, v.checks_json,
                   v.rendered_text, v.qualification_notes_json, v.blocked_reasons_json,
                   v.suggested_remedy, v.verified_at
            FROM claim_proposals p
            LEFT JOIN claim_verifications v ON p.claim_id = v.claim_id
            WHERE p.claim_id = ?
            ORDER BY v.verified_at DESC
            LIMIT 1;
            """,
            (claim_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._format_claim_row(row)

    def list_case_claims(
        self,
        case_id: str,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List all claims for a case with their latest verification results."""
        cursor = self.conn.cursor()
        query = """
            SELECT p.claim_id, p.case_id, p.claim_type, p.predicate, p.value_json,
                   p.evidence_refs_json, p.certainty, p.template_id, p.proposed_by, p.created_at,
                   v.verification_id, v.status, v.verification_version, v.checks_json,
                   v.rendered_text, v.qualification_notes_json, v.blocked_reasons_json,
                   v.suggested_remedy, v.verified_at
            FROM claim_proposals p
            LEFT JOIN claim_verifications v ON p.claim_id = v.claim_id
            WHERE p.case_id = ?
        """
        params: List[Any] = [case_id]
        if status:
            query += " AND v.status = ?"
            params.append(status)

        query += " ORDER BY p.created_at ASC, v.verified_at DESC;"
        cursor.execute(query, tuple(params))

        claims = []
        seen_claim_ids = set()
        for row in cursor.fetchall():
            c_dict = self._format_claim_row(row)
            if c_dict["claim_id"] not in seen_claim_ids:
                seen_claim_ids.add(c_dict["claim_id"])
                claims.append(c_dict)
        return claims

    def list_all_claims(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List claim verifications with pagination and optional status filter."""
        cursor = self.conn.cursor()
        where_clauses: List[str] = []
        params: List[Any] = []

        if status:
            where_clauses.append("v.status = ?")
            params.append(status)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        count_sql = f"""
            SELECT COUNT(DISTINCT p.claim_id)
            FROM claim_proposals p
            LEFT JOIN claim_verifications v ON p.claim_id = v.claim_id
            {where_sql};
        """
        cursor.execute(count_sql, tuple(params))
        total = cursor.fetchone()[0]

        query = f"""
            SELECT p.claim_id, p.case_id, p.claim_type, p.predicate, p.value_json,
                   p.evidence_refs_json, p.certainty, p.template_id, p.proposed_by, p.created_at,
                   v.verification_id, v.status, v.verification_version, v.checks_json,
                   v.rendered_text, v.qualification_notes_json, v.blocked_reasons_json,
                   v.suggested_remedy, v.verified_at
            FROM claim_proposals p
            LEFT JOIN claim_verifications v ON p.claim_id = v.claim_id
            {where_sql}
            GROUP BY p.claim_id
            ORDER BY v.verified_at DESC, p.created_at DESC
            LIMIT ? OFFSET ?;
        """
        params.extend([limit, offset])
        cursor.execute(query, tuple(params))

        claims = [self._format_claim_row(row) for row in cursor.fetchall()]
        return claims, total

    def _format_claim_row(self, row: Any) -> Dict[str, Any]:
        """Deserialize JSON fields from a claim query row."""
        r = dict(row)
        try:
            r["value"] = json.loads(r.pop("value_json", "{}"))
        except Exception:
            r["value"] = {}
        try:
            r["evidence_refs"] = json.loads(r.pop("evidence_refs_json", "[]"))
        except Exception:
            r["evidence_refs"] = []
        try:
            r["checks"] = json.loads(r.pop("checks_json", "[]"))
        except Exception:
            r["checks"] = []
        try:
            r["qualification_notes"] = json.loads(r.pop("qualification_notes_json", "[]"))
        except Exception:
            r["qualification_notes"] = []
        try:
            r["blocked_reasons"] = json.loads(r.pop("blocked_reasons_json", "[]"))
        except Exception:
            r["blocked_reasons"] = []
        return r

    # ---------------------------------------------------------
    # Replay Lab Management (Phase 7)
    # ---------------------------------------------------------

    def persist_replay_run(self, run_data: Dict[str, Any]) -> None:
        """Persist or update a replay run execution record."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO replay_runs (
                replay_id, scenario_id, scenario_version, status, mode,
                pipeline_versions_json, fixture_checksums_json, what_if_config_json,
                metrics_json, assertion_results_json, stages_json,
                cases_snapshot_json, claims_snapshot_json, error_summary,
                started_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                run_data["replay_id"],
                run_data["scenario_id"],
                run_data.get("scenario_version", "1.0.0"),
                run_data.get("status", "completed"),
                run_data.get("mode", "standard"),
                json.dumps(run_data.get("pipeline_versions", {})),
                json.dumps(run_data.get("fixture_checksums", {})),
                json.dumps(run_data.get("what_if_config", {})),
                json.dumps(run_data.get("metrics", {})),
                json.dumps(run_data.get("assertion_results", [])),
                json.dumps(run_data.get("stages", [])),
                json.dumps(run_data.get("cases_snapshot", [])),
                json.dumps(run_data.get("claims_snapshot", [])),
                run_data.get("error_summary"),
                run_data.get("started_at") or datetime.now(timezone.utc).isoformat(),
                run_data.get("completed_at"),
            ),
        )
        self.conn.commit()

    def get_replay_run(self, replay_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific replay run report by replay ID."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT replay_id, scenario_id, scenario_version, status, mode,
                   pipeline_versions_json, fixture_checksums_json, what_if_config_json,
                   metrics_json, assertion_results_json, stages_json,
                   cases_snapshot_json, claims_snapshot_json, error_summary,
                   started_at, completed_at
            FROM replay_runs
            WHERE replay_id = ?;
            """,
            (replay_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._format_replay_run_row(row)

    def list_replay_runs(
        self,
        scenario_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List past replay run summaries ordered by started_at descending."""
        cursor = self.conn.cursor()
        where_clauses = []
        params: List[Any] = []

        if scenario_id:
            where_clauses.append("scenario_id = ?")
            params.append(scenario_id)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        cursor.execute(f"SELECT count(*) FROM replay_runs {where_sql};", tuple(params))
        total = cursor.fetchone()[0]

        query = f"""
            SELECT replay_id, scenario_id, scenario_version, status, mode,
                   pipeline_versions_json, fixture_checksums_json, what_if_config_json,
                   metrics_json, assertion_results_json, stages_json,
                   cases_snapshot_json, claims_snapshot_json, error_summary,
                   started_at, completed_at
            FROM replay_runs
            {where_sql}
            ORDER BY started_at DESC
            LIMIT ? OFFSET ?;
        """
        params.extend([limit, offset])
        cursor.execute(query, tuple(params))

        runs = [self._format_replay_run_row(row) for row in cursor.fetchall()]
        return runs, total

    def reset_replay_runs(self, scenario_id: Optional[str] = None) -> int:
        """Reset replay history safely without touching core security tables."""
        cursor = self.conn.cursor()
        if scenario_id:
            cursor.execute("DELETE FROM replay_runs WHERE scenario_id = ?;", (scenario_id,))
        else:
            cursor.execute("DELETE FROM replay_runs;")
        deleted = cursor.rowcount
        self.conn.commit()
        return deleted

    def persist_replay_expectation(
        self,
        scenario_id: str,
        scenario_version: str,
        manifest: Dict[str, Any],
        checksums: Dict[str, str],
    ) -> None:
        """Persist or update committed baseline scenario expectations."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO replay_expectations (
                scenario_id, scenario_version, manifest_json, fixture_checksums_json, updated_at
            ) VALUES (?, ?, ?, ?, ?);
            """,
            (
                scenario_id,
                scenario_version,
                json.dumps(manifest),
                json.dumps(checksums),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()

    def get_replay_expectation(self, scenario_id: str, scenario_version: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored scenario expectation manifest."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT scenario_id, scenario_version, manifest_json, fixture_checksums_json, updated_at
            FROM replay_expectations
            WHERE scenario_id = ? AND scenario_version = ?;
            """,
            (scenario_id, scenario_version),
        )
        row = cursor.fetchone()
        if not row:
            return None
        r = dict(row)
        try:
            r["manifest"] = json.loads(r.pop("manifest_json", "{}"))
        except Exception:
            r["manifest"] = {}
        try:
            r["fixture_checksums"] = json.loads(r.pop("fixture_checksums_json", "{}"))
        except Exception:
            r["fixture_checksums"] = {}
        return r

    def _format_replay_run_row(self, row: Any) -> Dict[str, Any]:
        """Deserialize JSON fields from a replay run query row."""
        r = dict(row)
        for key in ("pipeline_versions", "fixture_checksums", "what_if_config", "metrics"):
            json_key = f"{key}_json"
            try:
                r[key] = json.loads(r.pop(json_key, "{}"))
            except Exception:
                r[key] = {}
        for key in ("assertion_results", "stages", "cases_snapshot", "claims_snapshot"):
            json_key = f"{key}_json"
            try:
                r[key] = json.loads(r.pop(json_key, "[]"))
            except Exception:
                r[key] = []
        return r




