"""Data models for Project Sentinel Replay Lab."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class ScenarioFixture:
    """Descriptor for a static synthetic fixture file associated with a scenario."""

    filename: str
    parser_id: str
    sha256: str
    size_bytes: int
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ScenarioFixture:
        return cls(
            filename=data["filename"],
            parser_id=data["parser_id"],
            sha256=data["sha256"],
            size_bytes=int(data["size_bytes"]),
            description=data.get("description", ""),
        )


@dataclass
class ScenarioExpectations:
    """Expected assertions defining deterministic correctness for a scenario."""

    expected_imported_records: int
    expected_normalized_events: int
    expected_rules: List[str]
    expected_findings_count: int
    expected_cases_count: int
    expected_claim_outcomes: Dict[str, str]  # claim_id -> status ('verified', 'qualified', 'blocked')
    expected_timeline_types: Optional[List[str]] = None
    custom_assertions: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ScenarioExpectations:
        return cls(
            expected_imported_records=int(data["expected_imported_records"]),
            expected_normalized_events=int(data["expected_normalized_events"]),
            expected_rules=list(data["expected_rules"]),
            expected_findings_count=int(data["expected_findings_count"]),
            expected_cases_count=int(data["expected_cases_count"]),
            expected_claim_outcomes=dict(data.get("expected_claim_outcomes", {})),
            expected_timeline_types=data.get("expected_timeline_types"),
            custom_assertions=data.get("custom_assertions"),
        )


@dataclass
class ScenarioManifest:
    """Versioned specification of a synthetic security scenario for Replay Lab."""

    scenario_id: str
    name: str
    version: str
    description: str
    learning_objective: str
    story: str
    category: str
    fixtures: List[ScenarioFixture]
    claim_proposals: List[Dict[str, Any]]
    expectations: ScenarioExpectations
    supported_what_ifs: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "learning_objective": self.learning_objective,
            "story": self.story,
            "category": self.category,
            "fixtures": [f.to_dict() for f in self.fixtures],
            "claim_proposals": self.claim_proposals,
            "expectations": self.expectations.to_dict(),
            "supported_what_ifs": self.supported_what_ifs,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ScenarioManifest:
        return cls(
            scenario_id=data["scenario_id"],
            name=data["name"],
            version=data.get("version", "1.0.0"),
            description=data["description"],
            learning_objective=data["learning_objective"],
            story=data.get("story", ""),
            category=data.get("category", "Investigation"),
            fixtures=[ScenarioFixture.from_dict(f) for f in data.get("fixtures", [])],
            claim_proposals=data.get("claim_proposals", []),
            expectations=ScenarioExpectations.from_dict(data["expectations"]),
            supported_what_ifs=data.get("supported_what_ifs", []),
        )


@dataclass
class ReplayAssertion:
    """Individual assertion comparing expected vs actual pipeline results."""

    assertion_id: str
    category: str  # 'ingestion', 'normalization', 'detection', 'cases', 'claims'
    description: str
    expected: Any
    actual: Any
    passed: bool
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReplayStage:
    """Execution status and duration of a single pipeline stage in the replay."""

    stage_id: str
    name: str
    status: str  # 'completed', 'failed', 'skipped'
    duration_ms: float
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReplayMetrics:
    """Summary execution statistics for a replay run."""

    imported_records: int = 0
    normalized_events: int = 0
    findings_count: int = 0
    cases_count: int = 0
    claims_total: int = 0
    claims_verified: int = 0
    claims_qualified: int = 0
    claims_blocked: int = 0
    assertions_total: int = 0
    assertions_passed: int = 0
    assertions_failed: int = 0
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WhatIfConfig:
    """Parameters for a hypothetical What-If simulation run."""

    what_if_id: str = "wif_custom"
    description: str = "Custom What-If Simulation"
    name: str = ""
    rule_overrides: Optional[Dict[str, Any]] = None  # e.g. {"AUTH-001": {"threshold_count": 10}}
    correlation_overrides: Optional[Dict[str, Any]] = None  # e.g. {"enable_ip_correlation": True}
    excluded_records: Optional[List[int]] = None  # 1-based line numbers to drop from fixture

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReplayRunReport:
    """Comprehensive replay execution report containing full proof-carrying results."""

    replay_id: str
    scenario_id: str
    scenario_name: str
    scenario_version: str
    status: str  # 'completed', 'failed'
    mode: str  # 'standard', 'what_if'
    pipeline_versions: Dict[str, str]
    fixture_checksums: Dict[str, str]
    what_if_config: Dict[str, Any]
    metrics: ReplayMetrics
    assertion_results: List[ReplayAssertion]
    stages: List[ReplayStage]
    cases_snapshot: List[Dict[str, Any]] = field(default_factory=list)
    claims_snapshot: List[Dict[str, Any]] = field(default_factory=list)
    what_if_diff: Optional[Dict[str, Any]] = None
    error_summary: Optional[str] = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "replay_id": self.replay_id,
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "scenario_version": self.scenario_version,
            "status": self.status,
            "mode": self.mode,
            "pipeline_versions": self.pipeline_versions,
            "fixture_checksums": self.fixture_checksums,
            "what_if_config": self.what_if_config,
            "metrics": self.metrics.to_dict() if hasattr(self.metrics, "to_dict") else self.metrics,
            "assertion_results": [a.to_dict() if hasattr(a, "to_dict") else a for a in self.assertion_results],
            "stages": [s.to_dict() if hasattr(s, "to_dict") else s for s in self.stages],
            "cases_snapshot": self.cases_snapshot,
            "claims_snapshot": self.claims_snapshot,
            "what_if_diff": self.what_if_diff,
            "error_summary": self.error_summary,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
