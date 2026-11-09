"""Base parser interfaces and data structures for Project Sentinel."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


MAX_LINE_LENGTH = 1_048_576  # 1 MB maximum length per record/line to protect against DoS


@dataclass(frozen=True)
class ParsedRecord:
    """Represents a validated parsed event record prior to normalization."""
    line_number: int
    timestamp: Optional[str]
    event_type: str
    attributes: Dict[str, Any]
    raw_payload: str


@dataclass(frozen=True)
class ParsingError:
    """Represents an unparsable or invalid line encountered during parsing."""
    line_number: int
    raw_line: str
    error_reason: str


@dataclass
class ParseResult:
    """Aggregated result of a file parsing run."""
    records: List[ParsedRecord] = field(default_factory=list)
    errors: List[ParsingError] = field(default_factory=list)
    total_lines_read: int = 0


class BaseParser:
    """Abstract base class for all Sentinel source log parsers."""

    parser_id: str = ""
    parser_version: str = "1.0.0"
    display_name: str = ""
    description: str = ""

    def parse(self, text_content: str) -> ParseResult:
        """Parse raw text content into structured records and error entries."""
        raise NotImplementedError("Subclasses must implement parse()")

