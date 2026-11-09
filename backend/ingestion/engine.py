"""Core ingestion engine coordinating hashing, validation, parsing, and atomic persistence."""

import hashlib
import logging
import uuid
from typing import Any, Dict, Optional

from backend.config.settings import Settings
from backend.ingestion.sanitizer import sanitize_attributes, sanitize_string
from backend.parsers.base import BaseParser
from backend.parsers.registry import get_parser
from backend.persistence.repository import IngestionRepository

logger = logging.getLogger("sentinel.ingestion")


class ImportEngine:
    """Coordinates validation, parsing, deduplication, and atomic persistence of security logs."""

    def __init__(self, repository: IngestionRepository, settings: Settings) -> None:
        self.repo = repository
        self.settings = settings

    def ingest_file(
        self,
        source_id: str,
        filename: str,
        content_bytes: bytes,
        parser_id: str,
    ) -> Dict[str, Any]:
        """Process an uploaded or scanned log file deterministically."""

        # 1. Size validation
        file_size = len(content_bytes)
        if file_size > self.settings.max_import_size_bytes:
            return {
                "status": "rejected",
                "duplicate": False,
                "error": f"File size ({file_size} bytes) exceeds configured maximum limit of {self.settings.max_import_size_bytes} bytes.",
            }

        if file_size == 0:
            return {
                "status": "rejected",
                "duplicate": False,
                "error": "Cannot import empty file (0 bytes).",
            }

        # 2. SHA-256 calculation
        sha256_hash = hashlib.sha256(content_bytes).hexdigest()

        # 3. Resolve parser profile
        parser = get_parser(parser_id)
        if parser is None:
            return {
                "status": "rejected",
                "duplicate": False,
                "error": f"Unknown parser profile '{parser_id}'. Supported profiles: generic_jsonl, auth_csv, web_access_csv.",
            }

        # 4. Idempotency duplicate check
        existing_job = self.repo.find_import_by_hash(
            sha256=sha256_hash,
            parser_id=parser.parser_id,
            parser_version=parser.parser_version,
        )
        if existing_job and existing_job.get("status") in ("completed", "partial"):
            logger.info(
                "Skipping duplicate import for SHA-256 %s (existing import: %s)",
                sha256_hash,
                existing_job["import_id"],
            )
            return {
                "status": "skipped",
                "duplicate": True,
                "import_id": existing_job["import_id"],
                "source_id": existing_job["source_id"],
                "filename": existing_job["filename"],
                "sha256": sha256_hash,
                "file_size": existing_job["file_size"],
                "parser_id": parser.parser_id,
                "parser_version": parser.parser_version,
                "total_records": existing_job["total_records"],
                "accepted_records": existing_job["accepted_records"],
                "rejected_records": existing_job["rejected_records"],
                "message": "Duplicate file already imported with this parser profile; ingestion skipped.",
            }

        # 5. Verify source existence (fallback to manual source)
        source = self.repo.get_source(source_id)
        if not source:
            source = self.repo.get_or_create_source(
                source_id="src_manual_default",
                source_name="Manual Local File Upload",
                parser_profile="generic_jsonl",
            )
            source_id = source["source_id"]

        # 6. Decode bytes to UTF-8
        try:
            text_content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                # Try UTF-8 with BOM
                text_content = content_bytes.decode("utf-8-sig")
            except UnicodeDecodeError as err:
                return {
                    "status": "rejected",
                    "duplicate": False,
                    "error": f"File content is not valid UTF-8: {err}",
                }

        # 7. Execute parser
        parse_result = parser.parse(text_content)

        # 8. Bound check on record count
        if len(parse_result.records) > self.settings.max_records_per_file:
            return {
                "status": "rejected",
                "duplicate": False,
                "error": f"Record count ({len(parse_result.records)}) exceeds maximum permitted limit of {self.settings.max_records_per_file}.",
            }

        # 9. Pre-persistence sanitization & batch structuring
        records_to_insert = []
        for r in parse_result.records:
            sanitized_attrs = sanitize_attributes(r.attributes)
            sanitized_raw = sanitize_string(r.raw_payload)
            record_payload = {
                "line_number": r.line_number,
                "timestamp": r.timestamp,
                "event_type": r.event_type,
                "attributes": sanitized_attrs,
                "raw_payload": sanitized_raw,
            }
            records_to_insert.append(
                {
                    "record_number": r.line_number,
                    "parser_id": parser.parser_id,
                    "parser_version": parser.parser_version,
                    "record": record_payload,
                }
            )

        errors_to_insert = []
        for e in parse_result.errors:
            errors_to_insert.append(
                {
                    "record_number": e.line_number,
                    "error_code": "PARSE_ERROR",
                    "safe_error_message": e.error_reason[:500],
                }
            )

        accepted_count = len(records_to_insert)
        rejected_count = len(errors_to_insert)
        total_count = accepted_count + rejected_count

        if accepted_count > 0 and rejected_count == 0:
            final_status = "completed"
            error_summary = None
        elif accepted_count > 0 and rejected_count > 0:
            final_status = "partial"
            error_summary = f"{rejected_count} row(s) failed parsing validation"
        else:
            final_status = "failed"
            error_summary = f"All {rejected_count} row(s) failed parsing validation"

        # 10. Atomic persistence
        import_id = f"imp_{uuid.uuid4().hex[:12]}"
        self.repo.create_import_job(
            import_id=import_id,
            source_id=source_id,
            filename=filename,
            sha256=sha256_hash,
            file_size=file_size,
            parser_id=parser.parser_id,
            parser_version=parser.parser_version,
            status="pending",
        )

        persisted_job = self.repo.persist_import_batch(
            import_id=import_id,
            status=final_status,
            total_records=total_count,
            accepted_records=accepted_count,
            rejected_records=rejected_count,
            records=records_to_insert,
            errors=errors_to_insert,
            error_summary=error_summary,
        )

        return {
            "status": final_status,
            "duplicate": False,
            "import_id": import_id,
            "source_id": source_id,
            "filename": filename,
            "sha256": sha256_hash,
            "file_size": file_size,
            "parser_id": parser.parser_id,
            "parser_version": parser.parser_version,
            "total_records": total_count,
            "accepted_records": accepted_count,
            "rejected_records": rejected_count,
            "completed_at": persisted_job["completed_at"],
            "errors": persisted_job.get("errors", []),
        }

