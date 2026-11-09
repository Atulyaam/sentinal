"""Web access CSV parser for Project Sentinel."""

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


ALLOWED_HTTP_METHODS: Set[str] = {
    "GET",
    "POST",
    "PUT",
    "DELETE",
    "PATCH",
    "HEAD",
    "OPTIONS",
    "CONNECT",
    "TRACE",
}

TIMESTAMP_HEADER_ALIASES = ("timestamp", "time", "datetime", "logged_at", "event_time")
METHOD_HEADER_ALIASES = ("http_method", "method", "verb", "request_method")
PATH_HEADER_ALIASES = ("request_path", "path", "uri", "url", "endpoint")
STATUS_HEADER_ALIASES = ("status_code", "status", "http_status", "code")


class WebAccessCsvParser(BaseParser):
    """Parses HTTP web access logs from comma-separated values."""

    parser_id = "web_access_csv"
    parser_version = "1.0.0"
    display_name = "Web Access Logs (CSV)"
    description = "Parses HTTP web server access logs (method, path, status, IP, user-agent) from CSV logs."

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

        raw_headers = [h.strip() for h in header_row]
        norm_headers = [h.lower() for h in raw_headers]

        method_col = next((i for i, h in enumerate(norm_headers) if h in METHOD_HEADER_ALIASES), None)
        path_col = next((i for i, h in enumerate(norm_headers) if h in PATH_HEADER_ALIASES), None)
        status_col = next((i for i, h in enumerate(norm_headers) if h in STATUS_HEADER_ALIASES), None)
        timestamp_col = next((i for i, h in enumerate(norm_headers) if h in TIMESTAMP_HEADER_ALIASES), None)

        missing_fields: List[str] = []
        if timestamp_col is None:
            missing_fields.append("timestamp")
        if method_col is None:
            missing_fields.append("http_method")
        if path_col is None:
            missing_fields.append("request_path")
        if status_col is None:
            missing_fields.append("status_code")

        if missing_fields:
            result.errors.append(
                ParsingError(
                    line_number=1,
                    raw_line=",".join(raw_headers),
                    error_reason=f"Missing required CSV header columns: {', '.join(missing_fields)}",
                )
            )
            return result

        for row in reader:
            current_line = reader.line_num
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

            row_dict: Dict[str, str] = {
                raw_headers[i]: row[i].strip() for i in range(len(norm_headers))
            }

            timestamp_val = row[timestamp_col].strip()
            method_raw = row[method_col].strip().upper()
            path_val = row[path_col].strip()
            status_raw = row[status_col].strip()

            if not timestamp_val:
                result.errors.append(
                    ParsingError(
                        line_number=current_line,
                        raw_line=raw_line_text[:500],
                        error_reason="Missing required timestamp value.",
                    )
                )
                continue

            if method_raw not in ALLOWED_HTTP_METHODS:
                result.errors.append(
                    ParsingError(
                        line_number=current_line,
                        raw_line=raw_line_text[:500],
                        error_reason=f"Invalid HTTP method '{method_raw}'. Must be standard HTTP verb.",
                    )
                )
                continue

            if not path_val:
                result.errors.append(
                    ParsingError(
                        line_number=current_line,
                        raw_line=raw_line_text[:500],
                        error_reason="Missing required request_path value.",
                    )
                )
                continue

            try:
                status_int = int(status_raw)
                if not (100 <= status_int <= 599):
                    raise ValueError(f"Status code {status_int} out of valid range (100-599).")
            except ValueError as err:
                result.errors.append(
                    ParsingError(
                        line_number=current_line,
                        raw_line=raw_line_text[:500],
                        error_reason=f"Invalid HTTP status code '{status_raw}': {err}",
                    )
                )
                continue

            attributes = dict(row_dict)
            attributes["http_method"] = method_raw
            attributes["request_path"] = path_val
            attributes["status_code"] = status_int

            result.records.append(
                ParsedRecord(
                    line_number=current_line,
                    timestamp=timestamp_val,
                    event_type="web_request",
                    attributes=attributes,
                    raw_payload=raw_line_text.strip(),
                )
            )

        return result

