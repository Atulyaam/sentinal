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
                        status, attributes_json, normalization_version, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                   status, attributes_json, normalization_version, created_at
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
                   status, attributes_json, normalization_version, created_at
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


