"""Data models and validation logic for Claim Guard typed claims and verification results."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

VERIFIER_VERSION = "1.0.0"

SUPPORTED_CLAIM_TYPES: Set[str] = {
    "event_count",
    "finding_exists",
    "rule_match",
    "time_window",
    "entity_observed",
    "case_status",
    "correlation_relationship",
    "data_quality_issue",
}

SUPPORTED_PREDICATES: Dict[str, Set[str]] = {
    "event_count": {"contains_events_of_type", "total_event_count", "failed_event_count"},
    "finding_exists": {"contains_finding_for_rule", "has_detection"},
    "rule_match": {"rule_matched_condition", "rule_condition_satisfied"},
    "time_window": {"spans_time_window", "activity_observed_between"},
    "entity_observed": {"identifies_entity", "actor_identified", "target_identified"},
    "case_status": {"has_case_status", "case_severity_is"},
    "correlation_relationship": {"correlated_by_key", "shares_identity_dimension"},
    "data_quality_issue": {"contains_data_anomaly", "quarantined_record_present"},
}

VALID_STATUSES: Set[str] = {"verified", "qualified", "blocked"}
VALID_CERTAINTIES: Set[str] = {"observed", "inferred", "hypothesis"}


@dataclass
class ClaimProposal:
    """A structured, typed investigative statement proposed by an AI agent or workflow."""

    claim_id: str
    case_id: str
    claim_type: str
    predicate: str
    value: Dict[str, Any]
    evidence_refs: List[str]
    certainty: str = "observed"
    template_id: str = "case_event_count_v1"
    proposed_by: str = "kiro_crew_agent"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def validate(self) -> None:
        """Enforce strict schema validation on the claim proposal."""
        if not isinstance(self.claim_id, str) or not self.claim_id.strip():
            raise ValueError("ClaimProposal 'claim_id' must be a non-empty string.")
        if len(self.claim_id) > 64:
            raise ValueError("ClaimProposal 'claim_id' exceeds maximum length of 64 characters.")

        if not isinstance(self.case_id, str) or not self.case_id.strip():
            raise ValueError("ClaimProposal 'case_id' must be a non-empty string.")
        if len(self.case_id) > 64:
            raise ValueError("ClaimProposal 'case_id' exceeds maximum length of 64 characters.")

        if not isinstance(self.claim_type, str) or self.claim_type not in SUPPORTED_CLAIM_TYPES:
            raise ValueError(
                f"Unsupported claim_type '{self.claim_type}'. Allowed types: {sorted(list(SUPPORTED_CLAIM_TYPES))}"
            )

        allowed_preds = SUPPORTED_PREDICATES.get(self.claim_type, set())
        if not isinstance(self.predicate, str) or self.predicate not in allowed_preds:
            raise ValueError(
                f"Predicate '{self.predicate}' is not supported for claim_type '{self.claim_type}'. "
                f"Allowed predicates: {sorted(list(allowed_preds))}"
            )

        if not isinstance(self.value, dict):
            raise ValueError("ClaimProposal 'value' must be a JSON dictionary.")
        try:
            val_json = json.dumps(self.value)
            if len(val_json) > 10000:
                raise ValueError("ClaimProposal 'value' JSON exceeds maximum size limit of 10,000 characters.")
        except (TypeError, OverflowError) as e:
            raise ValueError(f"ClaimProposal 'value' must be JSON-serializable: {e}")

        if not isinstance(self.evidence_refs, list):
            raise ValueError("ClaimProposal 'evidence_refs' must be a list of evidence IDs.")
        if len(self.evidence_refs) > 500:
            raise ValueError("ClaimProposal 'evidence_refs' exceeds maximum limit of 500 references.")
        for ref in self.evidence_refs:
            if not isinstance(ref, str) or not ref.strip():
                raise ValueError("Every item in 'evidence_refs' must be a non-empty string.")
            if len(ref) > 64:
                raise ValueError(f"Evidence reference ID '{ref}' exceeds 64 characters.")

        if self.certainty not in VALID_CERTAINTIES:
            raise ValueError(
                f"Invalid certainty '{self.certainty}'. Allowed certainties: {sorted(list(VALID_CERTAINTIES))}"
            )

        if not isinstance(self.template_id, str) or not self.template_id.strip():
            raise ValueError("ClaimProposal 'template_id' must be a non-empty string.")

    def to_dict(self) -> Dict[str, Any]:
        """Convert dataclass to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ClaimProposal:
        """Construct ClaimProposal from dictionary and validate."""
        if not isinstance(data, dict):
            raise ValueError("ClaimProposal input must be a dictionary.")

        allowed_fields = {
            "claim_id",
            "case_id",
            "subject_ref",
            "claim_type",
            "predicate",
            "value",
            "evidence_refs",
            "certainty",
            "template_id",
            "proposed_by",
            "created_at",
            "status",
        }
        unknown_fields = set(data.keys()) - allowed_fields
        if unknown_fields:
            raise ValueError(f"Unknown field(s) in claim proposal: {sorted(list(unknown_fields))}")

        for str_field in ("claim_id", "claim_type", "predicate", "template_id"):
            val = data.get(str_field)
            if val is None or not isinstance(val, str) or not val.strip():
                raise ValueError(f"ClaimProposal '{str_field}' must be a non-empty string.")

        case_id = data.get("case_id") or data.get("subject_ref")
        if case_id is None or not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("ClaimProposal 'case_id' must be a non-empty string.")

        raw_val = data.get("value")
        if raw_val is None or not isinstance(raw_val, dict):
            raise ValueError("ClaimProposal 'value' must be a dictionary.")

        raw_refs = data.get("evidence_refs")
        if raw_refs is None or not isinstance(raw_refs, list):
            raise ValueError("ClaimProposal 'evidence_refs' must be a list.")

        certainty = data.get("certainty", "observed")
        if certainty is not None and not isinstance(certainty, str):
            raise ValueError("ClaimProposal 'certainty' must be a string.")

        proposed_by = data.get("proposed_by", "kiro_crew_agent")
        if proposed_by is not None and not isinstance(proposed_by, str):
            raise ValueError("ClaimProposal 'proposed_by' must be a string.")

        created_at = data.get("created_at")
        if created_at is not None and not isinstance(created_at, str):
            raise ValueError("ClaimProposal 'created_at' must be a string.")

        proposal = cls(
            claim_id=str(data["claim_id"]).strip(),
            case_id=str(case_id).strip(),
            claim_type=str(data["claim_type"]).strip(),
            predicate=str(data["predicate"]).strip(),
            value=data["value"],
            evidence_refs=list(data["evidence_refs"]),
            certainty=str(certainty).strip(),
            template_id=str(data["template_id"]).strip(),
            proposed_by=str(proposed_by).strip(),
            created_at=str(created_at or datetime.now(timezone.utc).isoformat()),
        )
        proposal.validate()
        return proposal


@dataclass
class VerificationCheck:
    """Individual deterministic check result in a verification pipeline."""

    name: str
    passed: bool
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimVerificationResult:
    """Deterministic verification outcome for a proposed claim."""

    verification_id: str
    claim_id: str
    case_id: str
    status: str  # "verified", "qualified", "blocked"
    verification_version: str  # "1.0.0"
    checks: List[VerificationCheck]
    rendered_text: str
    qualification_notes: List[str] = field(default_factory=list)
    blocked_reasons: List[str] = field(default_factory=list)
    suggested_remedy: Optional[str] = None
    evidence_refs: List[str] = field(default_factory=list)
    verified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def validate(self) -> None:
        """Validate result properties."""
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Invalid verification status '{self.status}'. Must be one of {VALID_STATUSES}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verification_id": self.verification_id,
            "claim_id": self.claim_id,
            "case_id": self.case_id,
            "status": self.status,
            "verification_version": self.verification_version,
            "checks": [c.to_dict() if hasattr(c, "to_dict") else c for c in self.checks],
            "rendered_text": self.rendered_text,
            "qualification_notes": self.qualification_notes,
            "blocked_reasons": self.blocked_reasons,
            "suggested_remedy": self.suggested_remedy,
            "evidence_refs": self.evidence_refs,
            "verified_at": self.verified_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ClaimVerificationResult:
        raw_checks = data.get("checks", [])
        checks: List[VerificationCheck] = []
        for c in raw_checks:
            if isinstance(c, VerificationCheck):
                checks.append(c)
            elif isinstance(c, dict):
                checks.append(
                    VerificationCheck(
                        name=str(c.get("name", "")),
                        passed=bool(c.get("passed", False)),
                        reason=str(c.get("reason", "")),
                    )
                )

        result = cls(
            verification_id=str(data.get("verification_id", "")),
            claim_id=str(data.get("claim_id", "")),
            case_id=str(data.get("case_id", "")),
            status=str(data.get("status", "blocked")),
            verification_version=str(data.get("verification_version", VERIFIER_VERSION)),
            checks=checks,
            rendered_text=str(data.get("rendered_text", "")),
            qualification_notes=list(data.get("qualification_notes", [])),
            blocked_reasons=list(data.get("blocked_reasons", [])),
            suggested_remedy=data.get("suggested_remedy"),
            evidence_refs=list(data.get("evidence_refs", [])),
            verified_at=str(data.get("verified_at") or datetime.now(timezone.utc).isoformat()),
        )
        result.validate()
        return result

