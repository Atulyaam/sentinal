"""Generic JSONL parser for Project Sentinel."""

import json
from typing import Any, Dict, Optional

from backend.parsers.base import (
    MAX_LINE_LENGTH,
    BaseParser,
    ParseResult,
    ParsedRecord,
    ParsingError,
)


TIMESTAMP_CANDIDATE_KEYS = (
    "timestamp",
    "time",
    "@timestamp",
    "ts",
    "datetime",
    "event_time",
    "logged_at",
)

EVENT_TYPE_CANDIDATE_KEYS = (
    "event_type",
    "event",
    "action",
    "type",
    "name",
    "activity",
)


class GenericJsonlParser(BaseParser):
    """Parses newline-delimited JSON (JSONL) records."""

    parser_id = "generic_jsonl"
    parser_version = "1.0.0"
    display_name = "Generic JSON Lines (JSONL)"
    description = "Parses line-by-line JSON objects with automatic timestamp and attribute detection."

    def parse(self, text_content: str) -> ParseResult:
        result = ParseResult()

        if not text_content:
            return result

        # Strip UTF-8 BOM if present at start of stream
        if text_content.startswith("\ufeff"):
            text_content = text_content[1:]

        lines = text_content.splitlines()
        result.total_lines_read = len(lines)

        for line_idx, raw_line in enumerate(lines, start=1):
            stripped = raw_line.strip()
            if not stripped:
                # Empty line is ignored gracefully
                continue

            if len(raw_line) > MAX_LINE_LENGTH:
                result.errors.append(
                    ParsingError(
                        line_number=line_idx,
                        raw_line=raw_line[:200] + "... [TRUNCATED]",
                        error_reason=f"Line exceeds maximum length limit of {MAX_LINE_LENGTH} characters.",
                    )
                )
                continue

            try:
                data = json.loads(stripped)
            except json.JSONDecodeError as err:
                result.errors.append(
                    ParsingError(
                        line_number=line_idx,
                        raw_line=stripped[:500],
                        error_reason=f"Invalid JSON syntax: {err.msg} (col {err.colno})",
                    )
                )
                continue

            if not isinstance(data, dict):
                result.errors.append(
                    ParsingError(
                        line_number=line_idx,
                        raw_line=stripped[:500],
                        error_reason=f"Record must be a JSON object, found {type(data).__name__}.",
                    )
                )
                continue

            # Extract timestamp candidate
            timestamp_val: Optional[str] = None
            for key in TIMESTAMP_CANDIDATE_KEYS:
                if key in data and data[key] is not None:
                    timestamp_val = str(data[key]).strip()
                    break

            # Extract event type candidate
            event_type_val = "generic_event"
            for key in EVENT_TYPE_CANDIDATE_KEYS:
                if key in data and data[key]:
                    event_type_val = str(data[key]).strip()
                    break

            result.records.append(
                ParsedRecord(
                    line_number=line_idx,
                    timestamp=timestamp_val,
                    event_type=event_type_val,
                    attributes=data,
                    raw_payload=stripped,
                )
            )

        return result

