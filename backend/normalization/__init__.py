"""Canonical Normalization Package for Project Sentinel."""

from backend.normalization.engine import (
    CURRENT_NORMALIZATION_VERSION,
    NormalizationEngine,
)
from backend.normalization.mappers import (
    AuthCsvMapper,
    BaseMapper,
    GenericJsonlMapper,
    WebAccessCsvMapper,
    compute_event_id,
)
from backend.normalization.timestamps import (
    format_utc_iso,
    parse_and_normalize_timestamp,
)

__all__ = [
    "NormalizationEngine",
    "CURRENT_NORMALIZATION_VERSION",
    "BaseMapper",
    "GenericJsonlMapper",
    "AuthCsvMapper",
    "WebAccessCsvMapper",
    "compute_event_id",
    "parse_and_normalize_timestamp",
    "format_utc_iso",
]

