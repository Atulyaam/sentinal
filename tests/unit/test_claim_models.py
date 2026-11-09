"""Unit tests for Claim Guard data models, serialization, and schema validation."""

import json
import unittest

from backend.claims.models import (
    SUPPORTED_CLAIM_TYPES,
    SUPPORTED_PREDICATES,
    VERIFIER_VERSION,
    ClaimProposal,
    ClaimVerificationResult,
    VerificationCheck,
)


class TestClaimModels(unittest.TestCase):
    """Test suite for ClaimProposal and ClaimVerificationResult models."""

    def test_valid_proposal_construction(self) -> None:
        """Valid proposal creates and serializes cleanly."""
        proposal = ClaimProposal(
            claim_id="clm_valid_01",
            case_id="case_test_01",
            claim_type="event_count",
            predicate="contains_events_of_type",
            value={"count": 5, "event_type": "authentication.failure"},
            evidence_refs=["evt_001", "evt_002"],
            certainty="observed",
            template_id="case_event_count_v1",
            proposed_by="kiro_crew_agent",
        )
        proposal.validate()
        d = proposal.to_dict()
        self.assertEqual(d["claim_id"], "clm_valid_01")
        self.assertEqual(d["claim_type"], "event_count")
        self.assertEqual(d["certainty"], "observed")

    def test_from_dict_and_subject_ref_alias(self) -> None:
        """from_dict accepts subject_ref as alias for case_id as per Master Plan 7.2."""
        raw = {
            "claim_id": "clm_alias_01",
            "subject_ref": "case_test_alias",
            "claim_type": "finding_exists",
            "predicate": "contains_finding_for_rule",
            "value": {"rule_id": "AUTH-001", "severity": "Medium"},
            "evidence_refs": ["find_001"],
            "certainty": "observed",
            "template_id": "case_finding_exists_v1",
        }
        prop = ClaimProposal.from_dict(raw)
        self.assertEqual(prop.case_id, "case_test_alias")
        self.assertEqual(prop.claim_type, "finding_exists")

    def test_reject_unsupported_claim_type(self) -> None:
        """Reject arbitrary unsupported claim types."""
        with self.assertRaises(ValueError) as ctx:
            ClaimProposal(
                claim_id="clm_bad_type",
                case_id="case_01",
                claim_type="arbitrary_unsupported_type",
                predicate="contains_events_of_type",
                value={"foo": "bar"},
                evidence_refs=["evt_01"],
            ).validate()
        self.assertIn("Unsupported claim_type", str(ctx.exception))

    def test_reject_unsupported_predicate_for_type(self) -> None:
        """Predicate must be supported for the specific claim type."""
        with self.assertRaises(ValueError) as ctx:
            ClaimProposal(
                claim_id="clm_bad_pred",
                case_id="case_01",
                claim_type="event_count",
                predicate="contains_finding_for_rule",  # Invalid predicate for event_count
                value={"count": 5},
                evidence_refs=["evt_01"],
            ).validate()
        self.assertIn("Predicate 'contains_finding_for_rule' is not supported", str(ctx.exception))

    def test_reject_invalid_certainty(self) -> None:
        """Reject unapproved certainty values."""
        with self.assertRaises(ValueError) as ctx:
            ClaimProposal(
                claim_id="clm_bad_cert",
                case_id="case_01",
                claim_type="event_count",
                predicate="contains_events_of_type",
                value={"count": 5},
                evidence_refs=["evt_01"],
                certainty="absolutely_guaranteed",
            ).validate()
        self.assertIn("Invalid certainty", str(ctx.exception))

    def test_reject_oversized_value_json(self) -> None:
        """Values exceeding size limits must be rejected."""
        huge_value = {"junk": "x" * 15000}
        with self.assertRaises(ValueError) as ctx:
            ClaimProposal(
                claim_id="clm_huge_val",
                case_id="case_01",
                claim_type="event_count",
                predicate="contains_events_of_type",
                value=huge_value,
                evidence_refs=["evt_01"],
            ).validate()
        self.assertIn("exceeds maximum size limit", str(ctx.exception))

    def test_reject_oversized_evidence_refs(self) -> None:
        """More than 500 evidence refs must be rejected."""
        many_refs = [f"evt_{i}" for i in range(501)]
        with self.assertRaises(ValueError) as ctx:
            ClaimProposal(
                claim_id="clm_many_refs",
                case_id="case_01",
                claim_type="event_count",
                predicate="contains_events_of_type",
                value={"count": 501},
                evidence_refs=many_refs,
            ).validate()
        self.assertIn("exceeds maximum limit of 500", str(ctx.exception))

    def test_verification_result_serialization(self) -> None:
        """ClaimVerificationResult serializes and deserializes accurately."""
        check = VerificationCheck(name="evidence_exists", passed=True, reason="All events found.")
        res = ClaimVerificationResult(
            verification_id="vchk_001",
            claim_id="clm_001",
            case_id="case_001",
            status="verified",
            verification_version=VERIFIER_VERSION,
            checks=[check],
            rendered_text="Case contains 5 failed events.",
            evidence_refs=["evt_01"],
        )
        res.validate()
        d = res.to_dict()
        self.assertEqual(d["status"], "verified")
        self.assertEqual(len(d["checks"]), 1)
        self.assertTrue(d["checks"][0]["passed"])

        roundtrip = ClaimVerificationResult.from_dict(d)
        self.assertEqual(roundtrip.verification_id, "vchk_001")
        self.assertEqual(roundtrip.checks[0].name, "evidence_exists")


if __name__ == "__main__":
    unittest.main()

