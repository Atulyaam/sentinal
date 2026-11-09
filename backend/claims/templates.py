"""Catalog of approved claim templates for Claim Guard."""
from __future__ import annotations

from typing import Any, Dict

APPROVED_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "case_event_count_v1": {
        "template_id": "case_event_count_v1",
        "claim_type": "event_count",
        "description": "Render statement regarding count of observed canonical events.",
        "format": "Case contains {count} {event_type} event(s).",
        "required_params": ["count", "event_type"],
    },
    "case_finding_exists_v1": {
        "template_id": "case_finding_exists_v1",
        "claim_type": "finding_exists",
        "description": "Render statement regarding presence of a verified security finding.",
        "format": "Case includes verified finding for rule '{rule_id}' with severity '{severity}'.",
        "required_params": ["rule_id", "severity"],
    },
    "case_rule_match_v1": {
        "template_id": "case_rule_match_v1",
        "claim_type": "rule_match",
        "description": "Render statement regarding specific rule match conditions.",
        "format": "Rule '{rule_id}' matched condition '{condition_key}' for finding '{finding_id}'.",
        "required_params": ["rule_id", "condition_key", "finding_id"],
    },
    "case_time_window_v1": {
        "template_id": "case_time_window_v1",
        "claim_type": "time_window",
        "description": "Render statement regarding the observed time boundary of the case.",
        "format": "Observed activity spans {duration_seconds}s from {start_time} to {end_time}.",
        "required_params": ["start_time", "end_time", "duration_seconds"],
    },
    "case_entity_observed_v1": {
        "template_id": "case_entity_observed_v1",
        "claim_type": "entity_observed",
        "description": "Render statement identifying an observed actor, target, or entity.",
        "format": "Entity '{entity_type}' observed with value '{entity_value}'.",
        "required_params": ["entity_type", "entity_value"],
    },
    "case_status_v1": {
        "template_id": "case_status_v1",
        "claim_type": "case_status",
        "description": "Render statement regarding current case status and severity.",
        "format": "Case status is '{status}' with derived severity '{severity}'.",
        "required_params": ["status", "severity"],
    },
    "case_correlation_v1": {
        "template_id": "case_correlation_v1",
        "claim_type": "correlation_relationship",
        "description": "Render statement regarding deterministic correlation key and grouping.",
        "format": "Evidence correlated on {key_type} '{key_value}' within observation window.",
        "required_params": ["key_type", "key_value"],
    },
    "case_data_quality_v1": {
        "template_id": "case_data_quality_v1",
        "claim_type": "data_quality_issue",
        "description": "Render statement regarding data quality anomalies or quarantined records.",
        "format": "Data quality alert: {anomaly_type} detected across {record_count} record(s).",
        "required_params": ["anomaly_type", "record_count"],
    },
}

