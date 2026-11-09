"""Committed scenario catalog and manifests for Project Sentinel Replay Lab."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

from backend.replay.models import (
    ScenarioExpectations,
    ScenarioFixture,
    ScenarioManifest,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "scenarios"


# -----------------------------------------------------------------------------
# Scenario A: Suspicious Account Activity
# -----------------------------------------------------------------------------
SCENARIO_A = ScenarioManifest(
    scenario_id="SCN-AUTH-BURST",
    name="Suspicious Account Activity & Authentication Burst",
    version="1.0.0",
    category="Authentication Security",
    description="Rapid succession of authentication failures followed by a successful login for user 'operator_dave'.",
    story=(
        "Synthetic identity 'operator_dave' incurs 5 rapid authentication failures from IP 198.51.100.10 "
        "within 4 minutes, followed 6 minutes later by a successful login. The scenario tests burst detection, "
        "success-after-failure correlation, and verifies that the system does not prematurely assert the successful "
        "login was performed by an adversary without direct cryptographic or behavioral proof."
    ),
    learning_objective=(
        "Understand how deterministic sliding-window rules detect brute-force bursts (AUTH-001) and subsequent "
        "successful access (AUTH-002), how cases group on user_principal, and how Claim Guard blocks unproven attacker attributions."
    ),
    fixtures=[
        ScenarioFixture(
            filename="scenario_a_auth_burst.csv",
            parser_id="auth_csv",
            sha256="45e53eda48ed3e2b683f3ce99bc25732de7e733e0b3a0f0fc323464283c13618",
            size_bytes=383,
            description="6 authentication records (5 failures, 1 success) for user 'operator_dave'.",
        )
    ],
    claim_proposals=[
        {
            "claim_id": "clm_scn_a_01",
            "claim_type": "event_count",
            "predicate": "failed_event_count",
            "value": {"count": 5, "event_type": "user_authentication"},
            "certainty": "observed",
            "template_id": "case_event_count_v1",
        },
        {
            "claim_id": "clm_scn_a_02",
            "claim_type": "finding_exists",
            "predicate": "contains_finding_for_rule",
            "value": {"rule_id": "AUTH-002", "severity": "High"},
            "certainty": "observed",
            "template_id": "case_finding_exists_v1",
        },
        {
            "claim_id": "clm_scn_a_03",
            "claim_type": "entity_observed",
            "predicate": "identifies_entity",
            "value": {"entity_type": "user_principal", "entity_value": "attacker_eve"},
            "certainty": "observed",
            "template_id": "case_entity_observed_v1",
        },
        {
            "claim_id": "clm_scn_a_04",
            "claim_type": "correlation_relationship",
            "predicate": "correlated_by_key",
            "value": {"key_type": "user_principal", "key_value": "operator_dave"},
            "certainty": "inferred",
            "template_id": "case_correlation_v1",
        },
    ],
    expectations=ScenarioExpectations(
        expected_imported_records=6,
        expected_normalized_events=6,
        expected_rules=["AUTH-001", "AUTH-002"],
        expected_findings_count=2,
        expected_cases_count=1,
        expected_claim_outcomes={
            "clm_scn_a_01": "verified",
            "clm_scn_a_02": "verified",
            "clm_scn_a_03": "blocked",
            "clm_scn_a_04": "qualified",
        },
        expected_timeline_types=["event", "finding", "correlation"],
    ),
    supported_what_ifs=[
        {
            "what_if_id": "WIF-THRESHOLD-10",
            "name": "Higher Failure Threshold (10)",
            "description": "Increase AUTH-001 threshold from 5 to 10 failures. Evaluates threshold sensitivity.",
            "rule_overrides": {"AUTH-001": {"threshold_count": 10}},
        },
        {
            "what_if_id": "WIF-DISABLE-AUTH-002",
            "name": "Disable Success Follow-Up Rule",
            "description": "Disable rule AUTH-002. Only AUTH-001 evaluates, yielding Medium severity case.",
            "rule_overrides": {"AUTH-002": {"enabled": False}},
        },
    ],
)


# -----------------------------------------------------------------------------
# Scenario B: Sensitive Endpoint Probing
# -----------------------------------------------------------------------------
SCENARIO_B = ScenarioManifest(
    scenario_id="SCN-WEB-PROBE",
    name="Sensitive Endpoint Probing & Route Reconnaissance",
    version="1.0.0",
    category="Web Application Security",
    description="Systematic probing of administrative web endpoints with HTTP 403 Forbidden responses.",
    story=(
        "Synthetic client from IP 203.0.113.88 attempts to access /admin, /api/v1/auth, and /config, "
        "receiving HTTP 403 Forbidden status codes, interspersed with legitimate HTTP 200 OK requests to public routes. "
        "The scenario demonstrates path-based sensitive route detection (WEB-001), distinguishing HTTP status codes, "
        "and enforces the IP Guardrail refusing to treat raw source IP as proof of user identity."
    ),
    learning_objective=(
        "Understand web application route normalization, status code differentiation (200 OK vs 403 Forbidden), "
        "how WEB-001 triggers, and why Sentinel prohibits inferring user identities from IP addresses alone."
    ),
    fixtures=[
        ScenarioFixture(
            filename="scenario_b_web_probe.csv",
            parser_id="web_access_csv",
            sha256="c76e17ccf0b6e21a779a55d4414982f799a2b8b15603c568bc48c743b74be463",
            size_bytes=448,
            description="5 web access records (3 forbidden administrative probes, 2 benign public requests).",
        )
    ],
    claim_proposals=[
        {
            "claim_id": "clm_scn_b_01",
            "claim_type": "finding_exists",
            "predicate": "contains_finding_for_rule",
            "value": {"rule_id": "WEB-001", "severity": "Medium"},
            "certainty": "observed",
            "template_id": "case_finding_exists_v1",
        },
        {
            "claim_id": "clm_scn_b_02",
            "claim_type": "entity_observed",
            "predicate": "identifies_entity",
            "value": {"entity_type": "source_ip", "entity_value": "203.0.113.88"},
            "certainty": "observed",
            "template_id": "case_entity_observed_v1",
        },
        {
            "claim_id": "clm_scn_b_03",
            "claim_type": "entity_observed",
            "predicate": "identifies_entity",
            "value": {"entity_type": "user_principal", "entity_value": "suspect_ip_user"},
            "certainty": "observed",
            "template_id": "case_entity_observed_v1",
        },
    ],
    expectations=ScenarioExpectations(
        expected_imported_records=5,
        expected_normalized_events=5,
        expected_rules=["WEB-001"],
        expected_findings_count=1,
        expected_cases_count=1,
        expected_claim_outcomes={
            "clm_scn_b_01": "verified",
            "clm_scn_b_02": "verified",
            "clm_scn_b_03": "blocked",  # IP guardrail block: cannot infer user identity from IP alone
        },
        expected_timeline_types=["event", "finding", "correlation"],
    ),
    supported_what_ifs=[
        {
            "what_if_id": "WIF-ENABLE-IP-CORRELATION",
            "name": "Enable Network IP Correlation",
            "description": "Enable enable_ip_correlation=True. Findings with matching source IP form a network investigation case.",
            "correlation_overrides": {"enable_ip_correlation": True},
        },
    ],
)


# -----------------------------------------------------------------------------
# Scenario C: Privilege Escalation Investigation
# -----------------------------------------------------------------------------
SCENARIO_C = ScenarioManifest(
    scenario_id="SCN-PRIV-ESC",
    name="Privilege Escalation & Unauthorized Role Assignment",
    version="1.0.0",
    category="Identity & Access Governance",
    description="Explicit administrative privilege grant audit event elevating user permissions.",
    story=(
        "In a synthetic audit stream, user 'audit_alice' executes a 'role_changed' action granting administrative "
        "role to 'analyst_bob' ('grant_role', target: 'analyst_bob', role: 'admin', previous_role: 'analyst'). "
        "The scenario demonstrates high-severity policy detection (PRIV-001), provenance linking to raw audit payloads, "
        "and shows how Claim Guard verifies the exact role change while blocking exaggerated claim proposals."
    ),
    learning_objective=(
        "Understand explicit privilege alteration detection (PRIV-001), severity derivation to High, "
        "audit payload provenance tracing, and Claim Guard's mathematical verification of record counts."
    ),
    fixtures=[
        ScenarioFixture(
            filename="scenario_c_priv_esc.jsonl",
            parser_id="generic_jsonl",
            sha256="f4ffffdb030c764bf938464bba8748ad62fbf8e825ce59f7fb2972ab98163066",
            size_bytes=580,
            description="3 audit records in JSONL including 1 explicit role change event for 'analyst_bob'.",
        )
    ],
    claim_proposals=[
        {
            "claim_id": "clm_scn_c_01",
            "claim_type": "finding_exists",
            "predicate": "contains_finding_for_rule",
            "value": {"rule_id": "PRIV-001", "severity": "High"},
            "certainty": "observed",
            "template_id": "case_finding_exists_v1",
        },
        {
            "claim_id": "clm_scn_c_02",
            "claim_type": "entity_observed",
            "predicate": "identifies_entity",
            "value": {"entity_type": "user_principal", "entity_value": "analyst_bob"},
            "certainty": "observed",
            "template_id": "case_entity_observed_v1",
        },
        {
            "claim_id": "clm_scn_c_03",
            "claim_type": "event_count",
            "predicate": "contains_events_of_type",
            "value": {"count": 50, "event_type": "role_changed"},
            "certainty": "observed",
            "template_id": "case_event_count_v1",
        },
        {
            "claim_id": "clm_scn_c_04",
            "claim_type": "time_window",
            "predicate": "spans_time_window",
            "value": {
                "start_time": "2026-11-09T08:00:00Z",
                "end_time": "2026-11-09T08:15:00Z",
                "duration_seconds": 900,
            },
            "certainty": "inferred",
            "template_id": "case_time_window_v1",
        },
    ],
    expectations=ScenarioExpectations(
        expected_imported_records=3,
        expected_normalized_events=3,
        expected_rules=["PRIV-001"],
        expected_findings_count=1,
        expected_cases_count=1,
        expected_claim_outcomes={
            "clm_scn_c_01": "verified",
            "clm_scn_c_02": "verified",
            "clm_scn_c_03": "blocked",  # Hallucinated count (50 vs 1)
            "clm_scn_c_04": "qualified",  # Inferred certainty
        },
        expected_timeline_types=["event", "finding", "correlation"],
    ),
    supported_what_ifs=[
        {
            "what_if_id": "WIF-EXCLUDE-ROLE-CHANGE",
            "name": "Exclude Role-Change Event",
            "description": "Exclude line 2 (the role_changed event). Evaluates exact causal dependency on the privilege event.",
            "excluded_records": [2],
        },
    ],
)


SCENARIO_CATALOG: Dict[str, ScenarioManifest] = {
    SCENARIO_A.scenario_id: SCENARIO_A,
    SCENARIO_B.scenario_id: SCENARIO_B,
    SCENARIO_C.scenario_id: SCENARIO_C,
}


def list_scenario_manifests() -> List[ScenarioManifest]:
    """Return all approved scenario manifests."""
    return list(SCENARIO_CATALOG.values())


def list_scenarios() -> List[ScenarioManifest]:
    """Alias for list_scenario_manifests."""
    return list_scenario_manifests()


def get_scenario_manifest(scenario_id: str) -> Optional[ScenarioManifest]:
    """Look up a scenario manifest by ID."""
    return SCENARIO_CATALOG.get(scenario_id)


def get_scenario(scenario_id: str) -> ScenarioManifest:
    """Look up a scenario manifest by ID or raise KeyError."""
    manifest = SCENARIO_CATALOG.get(scenario_id)
    if not manifest:
        raise KeyError(f"Unknown scenario ID: {scenario_id}")
    return manifest


def get_fixture_path(filename: str) -> Path:
    """Resolve absolute path to a scenario fixture file, preventing directory traversal."""
    resolved_fixtures_dir = FIXTURES_DIR.resolve()
    p = (resolved_fixtures_dir / filename).resolve()
    if not str(p).startswith(str(resolved_fixtures_dir)):
        raise ValueError(f"Path traversal detected in fixture path: {filename}")
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"Scenario fixture '{filename}' not found at {p}")
    return p
