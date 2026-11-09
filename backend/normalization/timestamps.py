"""Timestamp parsing and UTC normalization for Project Sentinel."""

import re
from datetime import datetime, timezone
from typing import Any, Tuple


EPOCH_REGEX = re.compile(r"^-?\d+(\.\d+)?$")


def parse_and_normalize_timestamp(raw_val: Any) -> Tuple[str, bool]:
    """
    Parse an input timestamp and convert it into a strict ISO-8601 UTC string.

    Returns:
        Tuple[str, bool]: (normalized_utc_iso_string, is_naive)
        where is_naive is True if the original source provided no timezone offset.

    Raises:
        ValueError: If raw_val is None, empty, or unparseable.
    """
    if raw_val is None:
        raise ValueError("Timestamp value is null or missing.")

    if isinstance(raw_val, (int, float)):
        ts_num = float(raw_val)
        if ts_num > 1e11:  # Milliseconds
            ts_num /= 1000.0
        dt = datetime.fromtimestamp(ts_num, tz=timezone.utc)
        return format_utc_iso(dt), False

    val_str = str(raw_val).strip()
    if not val_str:
        raise ValueError("Timestamp string is empty.")

    # Check if string is a numeric epoch
    if EPOCH_REGEX.match(val_str):
        try:
            ts_num = float(val_str)
            if ts_num > 1e11:  # Milliseconds
                ts_num /= 1000.0
            dt = datetime.fromtimestamp(ts_num, tz=timezone.utc)
            return format_utc_iso(dt), False
        except (ValueError, OverflowError, OSError) as err:
            raise ValueError(f"Invalid epoch timestamp '{val_str}': {err}")

    # ISO-8601 parsing
    try:
        dt = datetime.fromisoformat(val_str)
    except ValueError:
        # Try common fallback with RFC 2822 or common log formats if needed
        # e.g., '2026/11/09 08:00:15'
        if "/" in val_str:
            try:
                dt = datetime.strptime(val_str, "%Y/%m/%d %H:%M:%S")
            except ValueError:
                pass
            else:
                return format_utc_iso(dt.replace(tzinfo=timezone.utc)), True

        raise ValueError(f"Unable to parse timestamp '{val_str}' into ISO-8601 date-time.")

    # Determine whether the parsed datetime was naive
    is_naive = dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None
    if is_naive:
        dt_utc = dt.replace(tzinfo=timezone.utc)
    else:
        dt_utc = dt.astimezone(timezone.utc)

    return format_utc_iso(dt_utc), is_naive


def format_utc_iso(dt: datetime) -> str:
    """Format a timezone-aware UTC datetime into strict ISO-8601 with Z."""
    if dt.microsecond > 0:
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

