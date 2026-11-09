"""Domain models and data structures for Project Sentinel Detection Engine."""

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any, Dict, List, Optional


@dataclass
class RuleDefinition:
    """Represents a validated, versioned detection rule."""
    rule_id: str
    version: str
    name: str
    description: str
    severity: str  # 'Critical', 'High', 'Medium', 'Low', 'Info'
    enabled: bool
    config: Dict[str, Any]
    limitations: str
    config_hash: str = field(default="")

    def __post_init__(self) -> None:
        if not self.config_hash:
            self.config_hash = compute_rule_config_hash(self.config)[:16]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_rule_config_hash(config: Dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash of rule configuration dictionary."""
    canonical_json = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


@dataclass
class Finding:
    """Represents an evidence-backed security finding produced by a detection rule."""
    finding_id: str
    rule_id: str
    rule_version: str
    rule_config_hash: str
    severity: str
    status: str  # 'open', 'acknowledged', 'resolved', 'dismissed'
    title: str
    description: str
    first_observed_at: str
    last_observed_at: str
    matched_entity: Optional[str]
    matched_conditions: Dict[str, Any]
    supporting_event_ids: List[str]
    limitations: str
    dedupe_key: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvaluationStats:
    """Execution statistics for a rule evaluation run."""
    evaluation_id: str
    evaluated_at: str
    rule_count: int
    events_scanned: int
    findings_generated: int
    findings_duplicate: int
    duration_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
