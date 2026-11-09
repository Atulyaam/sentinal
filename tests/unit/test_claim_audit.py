"""Independent audit regression test suite for Project Sentinel Phase 6 (Claim Guard).

Verifies fixes and security guardrails for DEF-CLAIM-001 through DEF-CLAIM-008,
the 9-stage verification pipeline, and deterministic fact verification.
"""

import json
import sqlite3
import unittest
from datetime import datetime, timezone

from backend.claims.models import ClaimProposal, ClaimVerificationResult
from backend.claims.verifier import ClaimVerifier
from backend.claims.renderer import SafeClaimRenderer
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository


class TestClaimAudit(unittest.TestCase):
    """Independent audit test suite verifying Claim Guard security and integrity guarantees."""

    def setUp(self) -> None:
        self.verifier = ClaimVerifier()
        # Synthetic Case Bundle for audit tests
        self.case_bundle = {
            "case_id": "case_audit_001",
            "title": "Audit Investigation Case",
            "description": "Synthetic case bundle for audit verification",
            "status": "Open",
            "severity": "High",
            "correlation_key_type": "user_principal",
            "correlation_key_value": "analyst_bob",
            "first_observed_at": "2026-11-09T08:00:00Z",
            "last_observed_at": "2026-11-09T08:15:00Z",
            "events": [
                {
                    "event_id": f"evt_fail_{i}",
                    "timestamp": f"2026-11-09T08:0{i}:00Z",
                    "event_type": "user_authentication",
                    "user_principal": "analyst_bob",
                    "source_ip": "198.51.100.10",
                    "status": "FAILURE",
                    "attributes": {"attempt": i, "action": "login"},
                }
                for i in range(5)
            ]
            + [
                {
                    "event_id": "evt_succ_0",
                    "timestamp": "2026-11-09T08:10:00Z",
                    "event_type": "user_authentication",
                    "user_principal": "analyst_bob",
                    "source_ip": "198.51.100.10",
                    "status": "SUCCESS",
                    "attributes": {"session": "sess_123", "action": "login", "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                }
            ],
            "findings": [
                {
                    "finding_id": "find_auth_001",
                    "rule_id": "AUTH-001",
                    "rule_version": "1.0.0",
                    "severity": "Medium",
                    "title": "Repeated Authentication Failures",
                    "description": "5 failures within window",
                    "first_observed_at": "2026-11-09T08:00:00Z",
                    "last_observed_at": "2026-11-09T08:04:00Z",
                    "matched_entity": "analyst_bob",
                    "matched_conditions": {"failure_count": 5, "window_seconds": 600},
                    "supporting_event_ids": [f"evt_fail_{i}" for i in range(5)],
                },
                {
                    "finding_id": "find_ingest_001",
                    "rule_id": "INGEST-001",
                    "rule_version": "1.0.0",
                    "severity": "Info",
                    "title": "Data Quality Anomaly",
                    "description": "Quarantined record detected",
                    "first_observed_at": "2026-11-09T08:00:00Z",
                    "last_observed_at": "2026-11-09T08:00:00Z",
                    "matched_entity": "imp_001",
                    "matched_conditions": {"record_ids": ["rec_quar_01"], "import_id": "imp_001"},
                    "supporting_event_ids": [],
                },
            ],
        }

    # -------------------------------------------------------------------------
    # DEF-CLAIM-001: Time Window Validation Tests
    # -------------------------------------------------------------------------

    def test_def_claim_001_inverted_time_window_blocked(self) -> None:
        """Inverted time window (start_time > end_time) must be blocked."""
        proposal = ClaimProposal(
            claim_id="clm_time_inverted",
            case_id="case_audit_001",
            claim_type="time_window",
            predicate="spans_time_window",
            value={
                "start_time": "2026-11-09T08:15:00Z",
                "end_time": "2026-11-09T08:00:00Z",  # Inverted!
                "duration_seconds": 900,
            },
            evidence_refs=["evt_fail_0", "evt_succ_0"],
            certainty="observed",
            template_id="case_time_window_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        self.assertEqual(res.status, "blocked")
        self.assertTrue(any("Inverted time window" in r for r in res.blocked_reasons))

    def test_def_claim_001_unenclosed_time_window_blocked(self) -> None:
        """Claimed time window narrower than observed evidence window must be blocked."""
        # Evidence spans 08:00:00 to 08:10:00, but claim says window is 08:02:00 to 08:05:00
        proposal = ClaimProposal(
            claim_id="clm_time_narrow",
            case_id="case_audit_001",
            claim_type="time_window",
            predicate="spans_time_window",
            value={
                "start_time": "2026-11-09T08:02:00Z",
                "end_time": "2026-11-09T08:05:00Z",
                "duration_seconds": 180,
            },
            evidence_refs=["evt_fail_0", "evt_succ_0"],
            certainty="observed",
            template_id="case_time_window_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        self.assertEqual(res.status, "blocked")
        self.assertTrue(any("does not encompass referenced evidence window" in r for r in res.blocked_reasons))

    def test_def_claim_001_bogus_duration_seconds_blocked(self) -> None:
        """Claimed duration_seconds inconsistent with start/end bounds must be blocked."""
        # Window is 10 minutes (600s), but claim asserts duration_seconds = 999999
        proposal = ClaimProposal(
            claim_id="clm_time_bogus_dur",
            case_id="case_audit_001",
            claim_type="time_window",
            predicate="spans_time_window",
            value={
                "start_time": "2026-11-09T08:00:00Z",
                "end_time": "2026-11-09T08:10:00Z",
                "duration_seconds": 999999,  # Bogus duration!
            },
            evidence_refs=["evt_fail_0", "evt_succ_0"],
            certainty="observed",
            template_id="case_time_window_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        self.assertEqual(res.status, "blocked")
        self.assertTrue(any("does not match window duration" in r for r in res.blocked_reasons))

    # -------------------------------------------------------------------------
    # DEF-CLAIM-002: failed_event_count Predicate & Status Filter Tests
    # -------------------------------------------------------------------------

    def test_def_claim_002_failed_event_count_on_success_events_blocked(self) -> None:
        """Claiming failed_event_count when evidence only contains SUCCESS events must be blocked."""
        proposal = ClaimProposal(
            claim_id="clm_fail_count_bad",
            case_id="case_audit_001",
            claim_type="event_count",
            predicate="failed_event_count",
            value={"count": 1, "event_type": "user_authentication"},
            evidence_refs=["evt_succ_0"],  # Only 1 SUCCESS event in evidence!
            certainty="observed",
            template_id="case_event_count_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        self.assertEqual(res.status, "blocked")
        self.assertTrue(any("Claimed count 1 does not match verified count 0" in r for r in res.blocked_reasons))

    def test_def_claim_002_failed_event_count_matches_failures_verified(self) -> None:
        """Claiming failed_event_count matching actual FAILURE events must be verified."""
        proposal = ClaimProposal(
            claim_id="clm_fail_count_good",
            case_id="case_audit_001",
            claim_type="event_count",
            predicate="failed_event_count",
            value={"count": 5, "event_type": "user_authentication"},
            evidence_refs=[f"evt_fail_{i}" for i in range(5)] + ["evt_succ_0"],
            certainty="observed",
            template_id="case_event_count_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        self.assertEqual(res.status, "verified")
        self.assertIn("Case contains 5 user_authentication event(s).", res.rendered_text)

    # -------------------------------------------------------------------------
    # DEF-CLAIM-003: Template Required Parameter Completeness Tests
    # -------------------------------------------------------------------------

    def test_def_claim_003_missing_template_param_blocked(self) -> None:
        """Proposal omitting required template parameters must be blocked before rendering."""
        # case_status_v1 requires both 'status' and 'severity'
        proposal = ClaimProposal(
            claim_id="clm_missing_param",
            case_id="case_audit_001",
            claim_type="case_status",
            predicate="has_case_status",
            value={"severity": "High"},  # Missing 'status'!
            evidence_refs=["find_auth_001"],
            certainty="observed",
            template_id="case_status_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        self.assertEqual(res.status, "blocked")
        self.assertTrue(any("Missing required parameter(s)" in r and "status" in r for r in res.blocked_reasons))
        check = next((c for c in res.checks if c.name == "template_params_complete"), None)
        self.assertIsNotNone(check)
        self.assertFalse(check.passed)

    # -------------------------------------------------------------------------
    # DEF-CLAIM-004: Empty Evidence Refs & Finding Citation Tests
    # -------------------------------------------------------------------------

    def test_def_claim_004_finding_exists_empty_evidence_refs_blocked(self) -> None:
        """Claiming finding_exists with empty evidence_refs must be blocked."""
        proposal = ClaimProposal(
            claim_id="clm_finding_empty_refs",
            case_id="case_audit_001",
            claim_type="finding_exists",
            predicate="contains_finding_for_rule",
            value={"rule_id": "AUTH-001", "severity": "Medium"},
            evidence_refs=[],  # Empty!
            certainty="observed",
            template_id="case_finding_exists_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        self.assertEqual(res.status, "blocked")
        self.assertTrue(any("Empty evidence references" in r for r in res.blocked_reasons))

    def test_def_claim_004_finding_exists_without_finding_ref_blocked(self) -> None:
        """Claiming finding_exists but referencing only events and not the finding must be blocked."""
        proposal = ClaimProposal(
            claim_id="clm_finding_no_find_ref",
            case_id="case_audit_001",
            claim_type="finding_exists",
            predicate="contains_finding_for_rule",
            value={"rule_id": "AUTH-001", "severity": "Medium"},
            evidence_refs=["evt_fail_0"],  # Event referenced, but NOT finding!
            certainty="observed",
            template_id="case_finding_exists_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        self.assertEqual(res.status, "blocked")
        self.assertTrue(any("does not contain finding for rule 'AUTH-001'" in r for r in res.blocked_reasons))

    # -------------------------------------------------------------------------
    # DEF-CLAIM-005: Data Quality Anomaly record_count Verification Tests
    # -------------------------------------------------------------------------

    def test_def_claim_005_data_quality_hallucinated_record_count_blocked(self) -> None:
        """Claiming hallucinated record_count (e.g. 999999) for data_quality_issue must be blocked."""
        proposal = ClaimProposal(
            claim_id="clm_dq_hallucinated_count",
            case_id="case_audit_001",
            claim_type="data_quality_issue",
            predicate="contains_data_anomaly",
            value={"anomaly_type": "QuarantinedNormalizationRecords", "record_count": 999999},
            evidence_refs=["find_ingest_001"],
            certainty="observed",
            template_id="case_data_quality_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        self.assertEqual(res.status, "blocked")
        self.assertTrue(any("Claimed record_count (999999) does not match actual count" in r for r in res.blocked_reasons))

    def test_def_claim_005_data_quality_accurate_record_count_verified(self) -> None:
        """Accurate record_count (1) matching INGEST-001 finding is verified/qualified."""
        proposal = ClaimProposal(
            claim_id="clm_dq_accurate_count",
            case_id="case_audit_001",
            claim_type="data_quality_issue",
            predicate="contains_data_anomaly",
            value={"anomaly_type": "QuarantinedNormalizationRecords", "record_count": 1},
            evidence_refs=["find_ingest_001"],
            certainty="observed",
            template_id="case_data_quality_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        # Qualified due to data quality finding referenced
        self.assertEqual(res.status, "qualified")
        self.assertIn("detected across 1 record(s)", res.rendered_text)

    # -------------------------------------------------------------------------
    # DEF-CLAIM-006: Model Deserialization & Unknown Field Strictness Tests
    # -------------------------------------------------------------------------

    def test_def_claim_006_from_dict_rejects_none_and_non_strings(self) -> None:
        """ClaimProposal.from_dict rejects None or non-string values for required string fields."""
        bad_payload = {
            "claim_id": None,
            "case_id": "case_01",
            "claim_type": "event_count",
            "predicate": "contains_events_of_type",
            "value": {"count": 1},
            "evidence_refs": ["evt_1"],
            "template_id": "case_event_count_v1",
        }
        with self.assertRaises(ValueError) as ctx:
            ClaimProposal.from_dict(bad_payload)
        self.assertIn("ClaimProposal 'claim_id' must be a non-empty string.", str(ctx.exception))

    def test_def_claim_006_from_dict_rejects_unknown_fields(self) -> None:
        """ClaimProposal.from_dict rejects unexpected unrecognized fields."""
        bad_payload = {
            "claim_id": "clm_1",
            "case_id": "case_01",
            "claim_type": "event_count",
            "predicate": "contains_events_of_type",
            "value": {"count": 1},
            "evidence_refs": ["evt_1"],
            "template_id": "case_event_count_v1",
            "malicious_extra_field": "exploit",
        }
        with self.assertRaises(ValueError) as ctx:
            ClaimProposal.from_dict(bad_payload)
        self.assertIn("Unknown field(s) in claim proposal", str(ctx.exception))

    # -------------------------------------------------------------------------
    # DEF-CLAIM-007: Event Matching Substring Ambiguity Tests
    # -------------------------------------------------------------------------

    def test_def_claim_007_event_type_strict_matching_no_attribute_leak(self) -> None:
        """event_type cannot match arbitrary text buried inside unrelated attributes."""
        # In evidence, evt_succ_0 has user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        # An adversary asserts event_type is "Windows" - this must NOT match!
        proposal = ClaimProposal(
            claim_id="clm_evt_leak_test",
            case_id="case_audit_001",
            claim_type="event_count",
            predicate="contains_events_of_type",
            value={"count": 1, "event_type": "Windows"},
            evidence_refs=["evt_succ_0"],
            certainty="observed",
            template_id="case_event_count_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        self.assertEqual(res.status, "blocked")
        self.assertTrue(any("Claimed count 1 does not match verified count 0" in r for r in res.blocked_reasons))

    # -------------------------------------------------------------------------
    # DEF-CLAIM-008: 9-Stage Verification Audit Trail Completeness Tests
    # -------------------------------------------------------------------------

    def test_def_claim_008_verification_checks_complete_audit_trail(self) -> None:
        """Verification result checks array must contain all standard stages including data_quality and certainty."""
        proposal = ClaimProposal(
            claim_id="clm_checks_audit",
            case_id="case_audit_001",
            claim_type="event_count",
            predicate="contains_events_of_type",
            value={"count": 5, "event_type": "user_authentication"},
            evidence_refs=[f"evt_fail_{i}" for i in range(5)],
            certainty="observed",
            template_id="case_event_count_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        check_names = {c.name for c in res.checks}
        expected_checks = {
            "injection_safety",
            "template_params_complete",
            "case_exists",
            "case_containment",
            "evidence_exists",
            "value_matches_evidence",
            "data_quality_clean",
            "certainty_alignment",
        }
        for ec in expected_checks:
            self.assertIn(ec, check_names, f"Missing required verification check: {ec}")

    # -------------------------------------------------------------------------
    # Immutable Persistence Tests
    # -------------------------------------------------------------------------

    def test_claim_proposal_persistence_immutable(self) -> None:
        """Claim proposals table must be append-only / immutable once proposed (INSERT OR IGNORE)."""
        conn = sqlite3.connect(":memory:")
        apply_migrations(conn)
        repo = IngestionRepository(conn)

        proposal_initial = ClaimProposal(
            claim_id="clm_immutable_001",
            case_id="case_audit_001",
            claim_type="case_status",
            predicate="has_case_status",
            value={"status": "Open", "severity": "High"},
            evidence_refs=["find_auth_001"],
            certainty="observed",
            template_id="case_status_v1",
        )
        repo.persist_claim_proposal(proposal_initial)

        # Attempt to tamper proposal with altered value
        proposal_tampered = ClaimProposal(
            claim_id="clm_immutable_001",
            case_id="case_audit_001",
            claim_type="case_status",
            predicate="has_case_status",
            value={"status": "Resolved", "severity": "Low"},  # Tampered!
            evidence_refs=["find_auth_001"],
            certainty="observed",
            template_id="case_status_v1",
        )
        repo.persist_claim_proposal(proposal_tampered)

        cursor = conn.cursor()
        cursor.execute("SELECT value_json FROM claim_proposals WHERE claim_id = ?", ("clm_immutable_001",))
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        val = json.loads(row[0])
        self.assertEqual(val["status"], "Open", "Original claim proposal was mutated/overwritten!")
        conn.close()


if __name__ == "__main__":
    unittest.main()
