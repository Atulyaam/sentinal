"""Claim Guard orchestration engine for Project Sentinel."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.claims.models import (
    VERIFIER_VERSION,
    ClaimProposal,
    ClaimVerificationResult,
)
from backend.claims.verifier import ClaimVerifier

logger = logging.getLogger("sentinel.claims.engine")


class ClaimGuardEngine:
    """Orchestrates deterministic verification, persistence, and safe demo generation."""

    def __init__(self, verifier: Optional[ClaimVerifier] = None) -> None:
        self.verifier = verifier or ClaimVerifier()

    def process_claims(
        self,
        proposals: List[ClaimProposal],
        case_id: str,
        repo: Any,
    ) -> Dict[str, Any]:
        """
        Verify a batch of claim proposals against an investigation case and persist results.
        """
        case_data = repo.get_case(case_id)
        if not case_data:
            raise ValueError(f"Investigation case '{case_id}' does not exist.")

        # Attach database connection to verifier if available
        self.verifier.conn = repo.conn

        # Execute deterministic verification
        results: List[ClaimVerificationResult] = self.verifier.verify_batch(
            proposals, case_bundle=case_data
        )

        # Persist proposals and verifications transactionally
        for prop, res in zip(proposals, results):
            try:
                repo.persist_claim_proposal(prop)
                repo.persist_claim_verification(res)
            except Exception as e:
                logger.error("Failed to persist claim proposal/verification %s: %s", prop.claim_id, e)

        verified_count = sum(1 for r in results if r.status == "verified")
        qualified_count = sum(1 for r in results if r.status == "qualified")
        blocked_count = sum(1 for r in results if r.status == "blocked")

        logger.info(
            "Claim Guard run for case %s: %d verified, %d qualified, %d blocked",
            case_id,
            verified_count,
            qualified_count,
            blocked_count,
        )

        return {
            "case_id": case_id,
            "verification_version": VERIFIER_VERSION,
            "total_claims": len(results),
            "verified_count": verified_count,
            "qualified_count": qualified_count,
            "blocked_count": blocked_count,
            "results": [r.to_dict() for r in results],
        }

    def generate_demo_claims(self, case_id: str, repo: Any) -> List[ClaimProposal]:
        """
        Generate a curated bundle of valid and adversarial claims to demonstrate Claim Guard.
        Matches Section 7.5 of the Master Plan ("The Claim Guard Demo Moment").
        """
        case_data = repo.get_case(case_id)
        if not case_data:
            return []

        events = case_data.get("events", [])
        findings = case_data.get("findings", [])
        demo_proposals: List[ClaimProposal] = []

        # 1. Valid Claim: Observed event count
        if events:
            evt_type = events[0].get("event_type", "authentication.failure")
            matching_evts = [e for e in events if e.get("event_type") == evt_type]
            event_ids = [e["event_id"] for e in matching_evts]
            demo_proposals.append(
                ClaimProposal(
                    claim_id=f"clm_demo_valid_{case_id[:8]}_count",
                    case_id=case_id,
                    claim_type="event_count",
                    predicate="contains_events_of_type",
                    value={"count": len(matching_evts), "event_type": evt_type},
                    evidence_refs=event_ids,
                    certainty="observed",
                    template_id="case_event_count_v1",
                    proposed_by="kiro_crew_agent",
                )
            )

        # 2. Valid Claim: Finding existence
        if findings:
            first_finding = findings[0]
            demo_proposals.append(
                ClaimProposal(
                    claim_id=f"clm_demo_valid_{case_id[:8]}_finding",
                    case_id=case_id,
                    claim_type="finding_exists",
                    predicate="contains_finding_for_rule",
                    value={
                        "rule_id": first_finding.get("rule_id"),
                        "severity": first_finding.get("severity"),
                    },
                    evidence_refs=[first_finding.get("finding_id")],
                    certainty="observed",
                    template_id="case_finding_exists_v1",
                    proposed_by="kiro_crew_agent",
                )
            )

        # 3. Qualified Claim: Inferred correlation rationale
        demo_proposals.append(
            ClaimProposal(
                claim_id=f"clm_demo_qual_{case_id[:8]}_corr",
                case_id=case_id,
                claim_type="correlation_relationship",
                predicate="correlated_by_key",
                value={
                    "key_type": case_data.get("correlation_key_type", "user_principal"),
                    "key_value": case_data.get("correlation_key_value", "unknown"),
                },
                evidence_refs=[e["event_id"] for e in events[:2]],
                certainty="inferred",
                template_id="case_correlation_v1",
                proposed_by="kiro_crew_agent",
            )
        )

        # 4. Adversarial Claim: Hallucinated / Incorrect Event Count (Master Plan Demo Climax)
        if events:
            actual_count = len(events)
            hallucinated_count = actual_count + 13  # Hallucinated count
            demo_proposals.append(
                ClaimProposal(
                    claim_id=f"clm_demo_adv_{case_id[:8]}_bad_count",
                    case_id=case_id,
                    claim_type="event_count",
                    predicate="contains_events_of_type",
                    value={
                        "count": hallucinated_count,
                        "event_type": events[0].get("event_type", "authentication.failure"),
                    },
                    evidence_refs=[e["event_id"] for e in events],
                    certainty="observed",
                    template_id="case_event_count_v1",
                    proposed_by="kiro_crew_agent",
                )
            )

        # 5. Adversarial Claim: Cross-Case / Nonexistent Evidence Reference
        demo_proposals.append(
            ClaimProposal(
                claim_id=f"clm_demo_adv_{case_id[:8]}_cross_case",
                case_id=case_id,
                claim_type="finding_exists",
                predicate="contains_finding_for_rule",
                value={"rule_id": "AUTH-001", "severity": "High"},
                evidence_refs=["evt_hallucinated_9999", "find_unrelated_foreign_case"],
                certainty="observed",
                template_id="case_finding_exists_v1",
                proposed_by="kiro_crew_agent",
            )
        )

        # 6. Adversarial Claim: IP-only identity attribution guardrail test
        if events:
            src_ip = events[0].get("source_ip") or "203.0.113.77"
            demo_proposals.append(
                ClaimProposal(
                    claim_id=f"clm_demo_adv_{case_id[:8]}_ip_infer",
                    case_id=case_id,
                    claim_type="entity_observed",
                    predicate="identifies_entity",
                    value={
                        "entity_type": "user_principal",
                        "entity_value": "unconfirmed_external_actor",
                    },
                    evidence_refs=[events[0]["event_id"]],
                    certainty="observed",
                    template_id="case_entity_observed_v1",
                    proposed_by="kiro_crew_agent",
                )
            )

        return demo_proposals

