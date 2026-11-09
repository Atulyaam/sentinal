"""Authentication CSV parser for Project Sentinel."""

import csv
import io
from typing import Dict, List, Optional, Set

from backend.parsers.base import (
    MAX_LINE_LENGTH,
    BaseParser,
    ParseResult,
    ParsedRecord,
    ParsingError,
)


ALLOWED_AUTH_RESULTS: Set[str] = {"SUCCESS", "FAILURE", "CHALLENGE", "LOCKED"}

TIMESTAMP_HEADER_ALIASES = ("timestamp", "time", "datetime", "logged_at", "event_time")
USER_HEADER_ALIASES = ("username", "user_id", "user", "principal", "user_principal")
RESULT_HEADER_ALIASES = ("auth_result", "result", "status", "outcome")


class AuthCsvParser(BaseParser):
    """Parses authentication event logs from comma-separated values."""

    parser_id = "auth_csv"
    parser_version = "1.0.0"
    display_name = "Authentication Logs (CSV)"
    description = "Parses user authentication events (SUCCESS, FAILURE, CHALLENGE, LOCKED) from CSV logs."

    def parse(self, text_content: str) -> ParseResult:
        result = ParseResult()

        if not text_content:
            return result

        # Strip UTF-8 BOM if present
        if text_content.startswith("\ufeff"):
            text_content = text_content[1:]

        lines = text_content.splitlines()
        result.total_lines_read = len(lines)

        if not lines:
            return result

        reader = csv.reader(io.StringIO(text_content))

        # Read header row
        try:
            header_row = next(reader)
        except StopIteration:
            return result
        except csv.Error as err:
            result.errors.append(
                ParsingError(
                    line_number=1,
                    raw_line=lines[0][:200] if lines else "",
                    error_reason=f"Failed to read CSV header: {err}",
                )
            )
            return result

        # Normalize header column names (lower-cased and stripped)
        raw_headers = [h.strip() for h in header_row]
        norm_headers = [h.lower() for h in raw_headers]

        # Identify required column positions
        timestamp_col = next((i for i, h in enumerate(norm_headers) if h in TIMESTAMP_HEADER_ALIASES), None)
        user_col = next((i for i, h in enumerate(norm_headers) if h in USER_HEADER_ALIASES), None)
        result_col = next((i for i, h in enumerate(norm_headers) if h in RESULT_HEADER_ALIASES), None)

        missing_fields: List[str] = []
        if timestamp_col is None:
            missing_fields.append("timestamp")
        if user_col is None:
            missing_fields.append("username/user_id")
        if result_col is None:
            missing_fields.append("auth_result/status")

        if missing_fields:
            result.errors.append(
                ParsingError(
                    line_number=1,
                    raw_line=",".join(raw_headers),
                    error_reason=f"Missing required CSV header columns: {', '.join(missing_fields)}",
                )
            )
            return result

        # Parse subsequent rows
        for row in reader:
            current_line = reader.line_num

            # Determine the raw line text if available
            raw_line_text = lines[current_line - 1] if 0 <= current_line - 1 < len(lines) else ",".join(row)

            if len(raw_line_text) > MAX_LINE_LENGTH:
                result.errors.append(
                    ParsingError(
                        line_number=current_line,
                        raw_line=raw_line_text[:200] + "... [TRUNCATED]",
                        error_reason=f"Line exceeds maximum length limit of {MAX_LINE_LENGTH} characters.",
                    )
                )
                continue

            # Skip empty lines
            if not row or (len(row) == 1 and not row[0].strip()):
                continue

            if len(row) != len(norm_headers):
                result.errors.append(
                    ParsingError(
                        line_number=current_line,
                        raw_line=raw_line_text[:500],
                        error_reason=f"Column count mismatch: expected {len(norm_headers)}, got {len(row)}",
                    )
                )
                continue

            # Build row dict
            row_dict: Dict[str, str] = {
                raw_headers[i]: row[i].strip() for i in range(len(norm_headers))
            }

            # Validate required values
            timestamp_val = row[timestamp_col].strip()
            user_val = row[user_col].strip()
            result_raw = row[result_col].strip().upper()

            if not timestamp_val:
                result.errors.append(
                    ParsingError(
                        line_number=current_line,
                        raw_line=raw_line_text[:500],
                        error_reason="Missing required timestamp value.",
                    )
                )
                continue

            if not user_val:
                result.errors.append(
                    ParsingError(
                        line_number=current_line,
                        raw_line=raw_line_text[:500],
                        error_reason="Missing required username/user_id value.",
                    )
                )
                continue

            if result_raw not in ALLOWED_AUTH_RESULTS:
                result.errors.append(
                    ParsingError(
                        line_number=current_line,
                        raw_line=raw_line_text[:500],
                        error_reason=f"Invalid auth_result '{result_raw}'. Must be one of: {', '.join(sorted(ALLOWED_AUTH_RESULTS))}",
                    )
                )
                continue

            # Standardized event type
            event_type = row_dict.get("event_type") or row_dict.get("action") or "user_authentication"

            # Normalized attributes
            attributes = dict(row_dict)
            attributes["auth_result"] = result_raw
            attributes["username"] = user_val

            result.records.append(
                ParsedRecord(
                    line_number=current_line,
                    timestamp=timestamp_val,
                    event_type=event_type,
                    attributes=attributes,
                    raw_payload=raw_line_text.strip(),
                )
            )

        return result

