"""Timestamp parsing and UTC normalization for Project Sentinel."""

import re
from datetime import datetime, timezone
from typing import Any, Tuple


EPOCH_REGEX = re.compile(r"^-?\d+(\.\d+)?$")


class NaiveTimestampError(ValueError):
    """Raised when an ingested timestamp lacks an explicit timezone offset and UTC cannot be assumed."""

    def __init__(self, raw_val: str):
        super().__init__(f"Record timestamp '{raw_val}' lacks explicit timezone offset; cannot assume UTC.")
        self.raw_val = raw_val


def parse_and_normalize_timestamp(raw_val: Any) -> Tuple[str, str]:
    """
    Parse an input timestamp and convert it into a strict ISO-8601 UTC string.

    Only timezone-aware timestamps (with explicit offset like 'Z', '+02:00', '-05:00')
    or unambiguous POSIX Unix epoch timestamps are accepted. Naive timestamps without
    timezone information are rejected with NaiveTimestampError to prevent silent clock skew.

    Returns:
        Tuple[str, str]: (normalized_utc_iso_string, original_raw_string)

    Raises:
        NaiveTimestampError: If raw_val lacks an explicit timezone offset.
        ValueError: If raw_val is None, empty, or unparseable.
    """
    if raw_val is None:
        raise ValueError("Timestamp value is null or missing.")

    if isinstance(raw_val, (int, float)):
        ts_num = float(raw_val)
        if ts_num > 1e11:  # Milliseconds
            ts_num /= 1000.0
        dt = datetime.fromtimestamp(ts_num, tz=timezone.utc)
        return format_utc_iso(dt), str(raw_val)

    val_str = str(raw_val).strip()
    if not val_str:
        raise ValueError("Timestamp string is empty.")

    # Check if string is a numeric Unix epoch
    if EPOCH_REGEX.match(val_str):
        try:
            ts_num = float(val_str)
            if ts_num > 1e11:  # Milliseconds
                ts_num /= 1000.0
            dt = datetime.fromtimestamp(ts_num, tz=timezone.utc)
            return format_utc_iso(dt), val_str
        except (ValueError, OverflowError, OSError) as err:
            raise ValueError(f"Invalid epoch timestamp '{val_str}': {err}")

    # ISO-8601 parsing
    try:
        dt = datetime.fromisoformat(val_str)
    except ValueError:
        # Check if slash-separated with offset or naive
        if "/" in val_str:
            # If someone gave '2026/11/09 08:00:15', it's naive
            try:
                datetime.strptime(val_str, "%Y/%m/%d %H:%M:%S")
                raise NaiveTimestampError(val_str)
            except ValueError as sub_err:
                if isinstance(sub_err, NaiveTimestampError):
                    raise
                pass

        raise ValueError(f"Unable to parse timestamp '{val_str}' into ISO-8601 date-time.")

    # Determine whether the parsed datetime was naive
    is_naive = dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None
    if is_naive:
        raise NaiveTimestampError(val_str)

    dt_utc = dt.astimezone(timezone.utc)
    return format_utc_iso(dt_utc), val_str


def format_utc_iso(dt: datetime) -> str:
    """Format a timezone-aware UTC datetime into strict ISO-8601 with Z."""
    if dt.microsecond > 0:
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
