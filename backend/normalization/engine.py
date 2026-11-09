"""Canonical Normalization Engine for Project Sentinel."""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from backend.normalization.mappers import (
    AuthCsvMapper,
    BaseMapper,
    GenericJsonlMapper,
    WebAccessCsvMapper,
)
from backend.persistence.repository import IngestionRepository

logger = logging.getLogger("sentinel.normalization.engine")

CURRENT_NORMALIZATION_VERSION = "1.0.0"


class NormalizationEngine:
    """Orchestrates normalization of pre-normalized parsed records into canonical events."""

    def __init__(self) -> None:
        self.mappers: Dict[str, BaseMapper] = {
            "generic_jsonl": GenericJsonlMapper(),
            "auth_csv": AuthCsvMapper(),
            "web_access_csv": WebAccessCsvMapper(),
        }

    def register_mapper(self, mapper: BaseMapper) -> None:
        """Register a custom or additional parser mapper."""
        self.mappers[mapper.parser_id] = mapper

    def normalize_single_record(
        self,
        record_row: Dict[str, Any],
        normalization_version: str = CURRENT_NORMALIZATION_VERSION,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Normalize a single record row fetched from parsed_records.

        Returns:
            Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
            (normalized_event, None) on success, or (None, normalization_error) on failure.
        """
        rec_id = record_row["record_id"]
        import_id = record_row["import_id"]
        rec_num = record_row["record_number"]
        parser_id = record_row["parser_id"]

        # 1. Parse JSON record payload
        try:
            raw_record = json.loads(record_row["record_json"])
            if not isinstance(raw_record, dict):
                raise ValueError("Record JSON payload is not a valid dictionary.")
        except Exception as err:
            logger.warning("Failed to parse record_json for record %s: %s", rec_id, err)
            return None, {
                "error_id": f"nerr_{uuid.uuid4().hex[:12]}",
                "record_id": rec_id,
                "import_id": import_id,
                "record_number": rec_num,
                "error_code": "NORM_INVALID_PAYLOAD",
                "safe_error_message": f"Malformed record payload: {err}",
            }

        # 2. Identify mapper
        mapper = self.mappers.get(parser_id)
        if not mapper:
            logger.warning("No mapper registered for parser_id '%s'", parser_id)
            return None, {
                "error_id": f"nerr_{uuid.uuid4().hex[:12]}",
                "record_id": rec_id,
                "import_id": import_id,
                "record_number": rec_num,
                "error_code": "NORM_UNKNOWN_PARSER",
                "safe_error_message": f"No normalization mapper registered for parser '{parser_id}'.",
            }

        # 3. Build provenance context
        context = {
            "source_id": record_row["source_id"],
            "filename": record_row["filename"],
            "sha256": record_row["sha256"],
            "record_number": rec_num,
            "import_id": import_id,
            "record_id": rec_id,
        }

        # 4. Map record
        try:
            event = mapper.map_record(
                raw_record=raw_record,
                context=context,
                normalization_version=normalization_version,
            )
            # Contract verification: ensure required keys are present
            required_keys = (
                "event_id",
                "timestamp",
                "source_type",
                "source_file",
                "source_line",
                "source_sha256",
                "event_type",
                "status",
                "attributes",
            )
            for req in required_keys:
                if req not in event or event[req] is None:
                    raise ValueError(f"Normalized event missing required contract field '{req}'")

            return event, None

        except ValueError as err:
            err_msg = str(err)
            error_code = "NORM_INVALID_TIMESTAMP" if "timestamp" in err_msg.lower() else "NORM_SCHEMA_VIOLATION"
            logger.info("Normalization rejected for record %s: %s", rec_id, err_msg)
            return None, {
                "error_id": f"nerr_{uuid.uuid4().hex[:12]}",
                "record_id": rec_id,
                "import_id": import_id,
                "record_number": rec_num,
                "error_code": error_code,
                "safe_error_message": err_msg,
            }
        except Exception as err:
            logger.exception("Unexpected error during normalization of record %s: %s", rec_id, err)
            return None, {
                "error_id": f"nerr_{uuid.uuid4().hex[:12]}",
                "record_id": rec_id,
                "import_id": import_id,
                "record_number": rec_num,
                "error_code": "NORM_UNEXPECTED_ERROR",
                "safe_error_message": f"Unexpected normalization error: {err}",
            }

    def run_normalization(
        self,
        repo: IngestionRepository,
        import_id: Optional[str] = None,
        limit: int = 500,
        normalization_version: str = CURRENT_NORMALIZATION_VERSION,
    ) -> Dict[str, Any]:
        """
        Execute normalization over unnormalized records in the database.

        Returns:
            Dict containing batch execution statistics:
            total_fetched, accepted, rejected, skipped
        """
        unnorm = repo.get_unnormalized_records(
            import_id=import_id,
            normalization_version=normalization_version,
            limit=limit,
        )

        if not unnorm:
            return {
                "total_fetched": 0,
                "accepted": 0,
                "rejected": 0,
                "skipped": 0,
            }

        events_to_persist: List[Dict[str, Any]] = []
        errors_to_persist: List[Dict[str, Any]] = []

        for row in unnorm:
            evt, err = self.normalize_single_record(row, normalization_version=normalization_version)
            if evt:
                events_to_persist.append(evt)
            elif err:
                errors_to_persist.append(err)

        persist_res = repo.persist_normalized_events_batch(
            events=events_to_persist,
            errors=errors_to_persist,
        )

        accepted = persist_res["persisted_events"]
        rejected = persist_res["persisted_errors"]
        skipped = len(events_to_persist) - accepted

        logger.info(
            "Normalization run completed: %d fetched, %d accepted, %d rejected, %d skipped.",
            len(unnorm),
            accepted,
            rejected,
            skipped,
        )

        return {
            "total_fetched": len(unnorm),
            "accepted": accepted,
            "rejected": rejected,
            "skipped": skipped,
        }

