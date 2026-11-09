"""Data models and validation logic for Investigation Cases and Correlation."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

ALLOWED_STATUSES: Set[str] = {
    "Open",
    "UnderReview",
    "NeedsMoreEvidence",
    "Resolved",
    "Dismissed",
}

CaseStatus = str
CaseSeverity = str

ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    "Open": {"UnderReview", "Dismissed"},
    "UnderReview": {"NeedsMoreEvidence", "Resolved", "Dismissed", "Open"},
    "NeedsMoreEvidence": {"UnderReview", "Dismissed"},
    "Resolved": {"UnderReview"},
    "Dismissed": {"UnderReview"},
}

SEVERITY_ORDER: List[str] = ["Critical", "High", "Medium", "Low", "Info"]
SEVERITY_RANK: Dict[str, int] = {
    "Critical": 5,
    "High": 4,
    "Medium": 3,
    "Low": 2,
    "Info": 1,
}


def validate_status_transition(current_status: str, new_status: str) -> None:
    """
    Validate that transitioning from current_status to new_status is permitted.
    Raises ValueError on invalid status or illegal transition.
    """
    if current_status not in ALLOWED_STATUSES:
        raise ValueError(f"Current status '{current_status}' is not a recognized case status.")
    if new_status not in ALLOWED_STATUSES:
        raise ValueError(
            f"Target status '{new_status}' is invalid. Allowed statuses: {sorted(list(ALLOWED_STATUSES))}"
        )
    if current_status == new_status:
        return  # No-op transition is allowed

    allowed = ALLOWED_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise ValueError(
            f"Illegal case status transition from '{current_status}' to '{new_status}'. "
            f"Allowed transitions from '{current_status}' are: {sorted(list(allowed))}"
        )


def derive_case_severity(finding_severities: List[str]) -> Tuple[str, str]:
    """
    Derive the overall case severity from the maximum severity of its linked findings.
    Returns (severity_string, visible_derivation_rationale).
    """
    if not finding_severities:
        return "Info", "Default severity 'Info' assigned (no linked findings)."

    highest_rank = 0
    highest_severity = "Info"
    counts: Dict[str, int] = {}

    for sev in finding_severities:
        cleaned = str(sev).capitalize()
        counts[cleaned] = counts.get(cleaned, 0) + 1
        rank = SEVERITY_RANK.get(cleaned, 1)
        if rank > highest_rank:
            highest_rank = rank
            highest_severity = cleaned

    count_breakdown = ", ".join(f"{cnt} {s}" for s, cnt in sorted(counts.items(), key=lambda x: -SEVERITY_RANK.get(x[0], 0)))
    rationale = (
        f"Derived as '{highest_severity}' from the maximum severity of {len(finding_severities)} linked finding(s) "
        f"({count_breakdown})."
    )
    return highest_severity, rationale


def compute_case_id(key_type: str, key_value: str, window_bucket: int) -> str:
    """Generate a collision-resistant, deterministic case identifier."""
    seed = f"{key_type}:{key_value}:{window_bucket}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()[:20]
    return f"case_{digest}"


@dataclass
class ReviewAction:
    """Append-only record of an operator review decision or investigative note."""

    action_id: str
    case_id: str
    action_type: str
    previous_status: Optional[str]
    new_status: Optional[str]
    operator_note: str
    author: str = "secops_operator"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "case_id": self.case_id,
            "action_type": self.action_type,
            "previous_status": self.previous_status,
            "new_status": self.new_status,
            "operator_note": self.operator_note,
            "author": self.author,
            "created_at": self.created_at,
        }


@dataclass
class CorrelationRelationship:
    """Metadata describing a specific correlation link between findings and events."""

    relationship_id: str
    case_id: str
    relationship_type: str
    key_type: str
    key_value: str
    time_window_start: str
    time_window_end: str
    related_finding_ids: List[str]
    related_event_ids: List[str]
    rationale: str
    algorithm_version: str = "1.0.0"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relationship_id": self.relationship_id,
            "case_id": self.case_id,
            "relationship_type": self.relationship_type,
            "key_type": self.key_type,
            "key_value": self.key_value,
            "time_window_start": self.time_window_start,
            "time_window_end": self.time_window_end,
            "related_finding_ids": self.related_finding_ids,
            "related_event_ids": self.related_event_ids,
            "rationale": self.rationale,
            "algorithm_version": self.algorithm_version,
            "created_at": self.created_at,
        }


@dataclass
class CaseFinding:
    """Relational link between a case and a finding."""

    case_id: str
    finding_id: str
    correlation_rationale: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "finding_id": self.finding_id,
            "correlation_rationale": self.correlation_rationale,
            "created_at": self.created_at,
        }


@dataclass
class CaseEvent:
    """Relational link between a case and a canonical event."""

    case_id: str
    event_id: str
    relationship_type: str
    correlation_rationale: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "event_id": self.event_id,
            "relationship_type": self.relationship_type,
            "correlation_rationale": self.correlation_rationale,
            "created_at": self.created_at,
        }


@dataclass
class TimelineItem:
    """Chronological evidence item for the unified investigation case timeline."""

    item_id: str
    item_type: str  # 'event', 'finding', 'correlation', 'review_action', 'status_change'
    timestamp: str
    title: str
    description: str
    severity: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "item_type": self.item_type,
            "timestamp": self.timestamp,
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "data": self.data,
        }


@dataclass
class Case:
    """Investigation Case entity assembled via deterministic correlation."""

    case_id: str
    title: str
    description: str
    status: str
    severity: str
    correlation_key_type: str
    correlation_key_value: str
    first_observed_at: str
    last_observed_at: str
    dedupe_key: str
    algorithm_version: str = "1.0.0"
    metadata: Dict[str, Any] = field(default_factory=dict)
    linked_finding_ids: List[str] = field(default_factory=list)
    linked_event_ids: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "severity": self.severity,
            "correlation_key_type": self.correlation_key_type,
            "correlation_key_value": self.correlation_key_value,
            "first_observed_at": self.first_observed_at,
            "last_observed_at": self.last_observed_at,
            "algorithm_version": self.algorithm_version,
            "dedupe_key": self.dedupe_key,
            "metadata": self.metadata,
            "linked_finding_ids": self.linked_finding_ids,
            "linked_event_ids": self.linked_event_ids,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
