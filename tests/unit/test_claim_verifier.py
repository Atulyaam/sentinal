"""Unit tests for Claim Guard deterministic verification engine and safe renderer."""

import unittest

from backend.claims.models import ClaimProposal
from backend.claims.renderer import SafeClaimRenderer
from backend.claims.verifier import ClaimVerifier


class TestClaimVerifier(unittest.TestCase):
    """Test suite for deterministic ClaimVerifier checks across all supported claim types."""

    def setUp(self) -> None:
        self.verifier = ClaimVerifier()
        # Synthetic Case Bundle for testing
        self.case_bundle = {
            "case_id": "case_alpha_001",
            "title": "Suspicious Authentication Failure Burst",
            "description": "Correlated activity for user analyst_bob",
            "status": "Open",
            "severity": "High",
            "correlation_key_type": "user_principal",
            "correlation_key_value": "analyst_bob",
            "first_observed_at": "2026-11-09T08:00:00Z",
            "last_observed_at": "2026-11-09T08:15:00Z",
            "events": [
                {
                    "event_id": f"evt_auth_{i}",
                    "timestamp": f"2026-11-09T08:0{i}:00Z",
                    "event_type": "authentication.failure",
                    "user_principal": "analyst_bob",
                    "source_ip": "198.51.100.10",
                    "status": "failure",
                    "attributes": {"attempt": i},
                }
                for i in range(5)
            ] + [
                {
                    "event_id": "evt_auth_succ",
                    "timestamp": "2026-11-09T08:10:00Z",
                    "event_type": "authentication.success",
                    "user_principal": "analyst_bob",
                    "source_ip": "198.51.100.10",
                    "status": "success",
                    "attributes": {"session": "sess_123"},
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
                    "supporting_event_ids": [f"evt_auth_{i}" for i in range(5)],
                },
                {
                    "finding_id": "find_auth_002",
                    "rule_id": "AUTH-002",
                    "rule_version": "1.0.0",
                    "severity": "High",
                    "title": "Successful Authentication After Failures",
                    "description": "Success following failure burst",
                    "first_observed_at": "2026-11-09T08:00:00Z",
                    "last_observed_at": "2026-11-09T08:10:00Z",
                    "matched_entity": "analyst_bob",
                    "matched_conditions": {"burst_count": 5, "latency_seconds": 360},
                    "supporting_event_ids": [f"evt_auth_{i}" for i in range(5)] + ["evt_auth_succ"],
                },
            ],
        }

    # 1. Event Count Claim
    def test_event_count_exact_match_verified(self) -> None:
        """Exact count of failure events matches referenced evidence -> verified."""
        proposal = ClaimProposal(
            claim_id="clm_evt_count_ok",
            case_id="case_alpha_001",
            claim_type="event_count",
            predicate="contains_events_of_type",
            value={"count": 5, "event_type": "authentication.failure"},
            evidence_refs=[f"evt_auth_{i}" for i in range(5)],
            certainty="observed",
            template_id="case_event_count_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        self.assertEqual(res.status, "verified")
        self.assertIn("Case contains 5 authentication.failure event(s).", res.rendered_text)

    def test_event_count_mismatch_blocked(self) -> None:
        """Hallucinated / incorrect count -> blocked with explicit reason."""
        proposal = ClaimProposal(
            claim_id="clm_evt_count_bad",
            case_id="case_alpha_001",
            claim_type="event_count",
            predicate="contains_events_of_type",
            value={"count": 14, "event_type": "authentication.failure"},  # Claims 14, but only 5 in evidence!
            evidence_refs=[f"evt_auth_{i}" for i in range(5)],
            certainty="observed",
            template_id="case_event_count_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        self.assertEqual(res.status, "blocked")
        self.assertTrue(any("Claimed count 14 does not match verified count 5" in r for r in res.blocked_reasons))
        self.assertIn("[BLOCKED CLAIM]", res.rendered_text)

    # 2. Finding Exists Claim
    def test_finding_exists_verified(self) -> None:
        """Existing rule and severity verified."""
        proposal = ClaimProposal(
            claim_id="clm_finding_ok",
            case_id="case_alpha_001",
            claim_type="finding_exists",
            predicate="contains_finding_for_rule",
            value={"rule_id": "AUTH-002", "severity": "High"},
            evidence_refs=["find_auth_002"],
            certainty="observed",
            template_id="case_finding_exists_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        self.assertEqual(res.status, "verified")
        self.assertIn("verified finding for rule 'AUTH-002'", res.rendered_text)

    def test_finding_exists_wrong_rule_blocked(self) -> None:
        """Citing a rule that never triggered in this case -> blocked."""
        proposal = ClaimProposal(
            claim_id="clm_finding_bad_rule",
            case_id="case_alpha_001",
            claim_type="finding_exists",
            predicate="contains_finding_for_rule",
            value={"rule_id": "WEB-001", "severity": "Medium"},
            evidence_refs=["find_auth_001"],
            certainty="observed",
            template_id="case_finding_exists_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        self.assertEqual(res.status, "blocked")
        self.assertTrue(any("No finding for rule 'WEB-001' exists" in r for r in res.blocked_reasons))

    # 3. Rule Match Condition Claim
    def test_rule_match_condition_verified(self) -> None:
        """Rule condition key matching finding -> verified."""
        proposal = ClaimProposal(
            claim_id="clm_rule_cond_ok",
            case_id="case_alpha_001",
            claim_type="rule_match",
            predicate="rule_matched_condition",
            value={"rule_id": "AUTH-001", "finding_id": "find_auth_001", "condition_key": "failure_count"},
            evidence_refs=["find_auth_001"],
            certainty="observed",
            template_id="case_rule_match_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        self.assertEqual(res.status, "verified")

    # 4. Time Window Claim
    def test_time_window_verified(self) -> None:
        """Claimed time bounds overlapping observed evidence -> verified."""
        proposal = ClaimProposal(
            claim_id="clm_time_ok",
            case_id="case_alpha_001",
            claim_type="time_window",
            predicate="spans_time_window",
            value={
                "start_time": "2026-11-09T08:00:00Z",
                "end_time": "2026-11-09T08:10:00Z",
                "duration_seconds": 600,
            },
            evidence_refs=["evt_auth_0", "evt_auth_succ"],
            certainty="observed",
            template_id="case_time_window_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        self.assertEqual(res.status, "verified")

    # 5. Entity Observed Claim
    def test_entity_observed_verified(self) -> None:
        """Observed user principal in evidence -> verified."""
        proposal = ClaimProposal(
            claim_id="clm_entity_ok",
            case_id="case_alpha_001",
            claim_type="entity_observed",
            predicate="identifies_entity",
            value={"entity_type": "user_principal", "entity_value": "analyst_bob"},
            evidence_refs=["evt_auth_0"],
            certainty="observed",
            template_id="case_entity_observed_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        self.assertEqual(res.status, "verified")

    def test_entity_observed_absent_blocked(self) -> None:
        """Asserting an entity not present in evidence -> blocked."""
        proposal = ClaimProposal(
            claim_id="clm_entity_bad",
            case_id="case_alpha_001",
            claim_type="entity_observed",
            predicate="identifies_entity",
            value={"entity_type": "user_principal", "entity_value": "attacker_eve"},
            evidence_refs=["evt_auth_0"],
            certainty="observed",
            template_id="case_entity_observed_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        self.assertEqual(res.status, "blocked")
        self.assertTrue(any("attacker_eve" in r for r in res.blocked_reasons))

    # 6. Case Status Claim
    def test_case_status_verified_and_mismatch_blocked(self) -> None:
        """Correct status verified; wrong status blocked."""
        prop_ok = ClaimProposal(
            claim_id="clm_status_ok",
            case_id="case_alpha_001",
            claim_type="case_status",
            predicate="has_case_status",
            value={"status": "Open", "severity": "High"},
            evidence_refs=["find_auth_002"],
            certainty="observed",
            template_id="case_status_v1",
        )
        self.assertEqual(self.verifier.verify_proposal(prop_ok, case_bundle=self.case_bundle).status, "verified")

        prop_bad = ClaimProposal(
            claim_id="clm_status_bad",
            case_id="case_alpha_001",
            claim_type="case_status",
            predicate="has_case_status",
            value={"status": "Resolved", "severity": "Low"},
            evidence_refs=["find_auth_002"],
            certainty="observed",
            template_id="case_status_v1",
        )
        self.assertEqual(self.verifier.verify_proposal(prop_bad, case_bundle=self.case_bundle).status, "blocked")

    # 7. Inferred Certainty Triggers Qualified Status
    def test_inferred_certainty_triggers_qualified(self) -> None:
        """When certainty is 'inferred', verified evidence yields 'qualified' status with caveats."""
        proposal = ClaimProposal(
            claim_id="clm_inferred_qual",
            case_id="case_alpha_001",
            claim_type="correlation_relationship",
            predicate="correlated_by_key",
            value={"key_type": "user_principal", "key_value": "analyst_bob"},
            evidence_refs=["evt_auth_0"],
            certainty="inferred",
            template_id="case_correlation_v1",
        )
        res = self.verifier.verify_proposal(proposal, case_bundle=self.case_bundle)
        self.assertEqual(res.status, "qualified")
        self.assertIn("[QUALIFIED]", res.rendered_text)
        self.assertTrue(any("marked as 'inferred'" in n for n in res.qualification_notes))

    # 8. Safe Template HTML Escaping
    def test_safe_template_renderer_escapes_html(self) -> None:
        """Renderer safely neutralizes HTML and script tags."""
        malicious_value = {"count": 1, "event_type": "<script>alert('xss')</script>"}
        rendered = SafeClaimRenderer.render(
            template_id="case_event_count_v1",
            value=malicious_value,
            status="verified",
        )
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)


if __name__ == "__main__":
    unittest.main()

