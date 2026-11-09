"""Detection package for Project Sentinel."""

from backend.detection.engine import DetectionEngine
from backend.detection.models import EvaluationStats, Finding, RuleDefinition
from backend.detection.rules import (
    Auth001RepeatedFailuresRule,
    Auth002SuccessAfterFailuresRule,
    BaseRuleEvaluator,
    Ingest001DataQualityRule,
    Priv001PrivilegeChangeRule,
    RuleRegistry,
    Web001SensitiveRouteBurstRule,
    compute_finding_id,
    validate_rule_definition,
)

__all__ = [
    "DetectionEngine",
    "RuleDefinition",
    "Finding",
    "EvaluationStats",
    "RuleRegistry",
    "BaseRuleEvaluator",
    "Auth001RepeatedFailuresRule",
    "Auth002SuccessAfterFailuresRule",
    "Web001SensitiveRouteBurstRule",
    "Priv001PrivilegeChangeRule",
    "Ingest001DataQualityRule",
    "compute_finding_id",
    "validate_rule_definition",
]

