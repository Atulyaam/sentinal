"""Deterministic verification engine for Claim Guard."""
from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.claims.models import (
    SUPPORTED_CLAIM_TYPES,
    SUPPORTED_PREDICATES,
    VERIFIER_VERSION,
    ClaimProposal,
    ClaimVerificationResult,
    VerificationCheck,
)
from backend.claims.renderer import SafeClaimRenderer
from backend.claims.templates import APPROVED_TEMPLATES

INJECTION_PATTERNS = [
    re.compile(r"<\s*script\b", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
]


class ClaimVerifier:
    """
    Deterministic verifier for AI-generated investigative claims.
    Verifies existence, relational case containment, value accuracy, IP guardrails,
    and returns verified, qualified, or blocked results.
    """

    def __init__(self, conn: Optional[sqlite3.Connection] = None) -> None:
        self.conn = conn

    def verify_proposal(
        self,
        proposal: ClaimProposal,
        case_bundle: Optional[Dict[str, Any]] = None,
    ) -> ClaimVerificationResult:
        """Execute deterministic verification on a single claim proposal."""
        checks: List[VerificationCheck] = []
        blocked_reasons: List[str] = []
        qualification_notes: List[str] = []
        suggested_remedy: Optional[str] = None
        is_blocked = False
        is_qualified = False

        # 1. Schema & Predicate Check
        try:
            proposal.validate()
            checks.append(VerificationCheck(name="claim_schema_valid", passed=True, reason="Claim schema is valid."))
        except Exception as e:
            is_blocked = True
            msg = f"Schema validation error: {str(e)}"
            checks.append(VerificationCheck(name="claim_schema_valid", passed=False, reason=msg))
            blocked_reasons.append(msg)
            suggested_remedy = "Correct the claim proposal fields to match the Claim Guard contract."

        # 2. Template Approved Check & Required Parameters Completeness
        tmpl = APPROVED_TEMPLATES.get(proposal.template_id)
        if not tmpl:
            is_blocked = True
            msg = f"Template '{proposal.template_id}' is not an approved Claim Guard template."
            checks.append(VerificationCheck(name="template_approved", passed=False, reason=msg))
            blocked_reasons.append(msg)
            suggested_remedy = f"Use one of the approved templates: {sorted(list(APPROVED_TEMPLATES.keys()))}"
        else:
            checks.append(VerificationCheck(name="template_approved", passed=True, reason="Template is approved."))
            # Check required parameters for the template
            missing_params = [
                p for p in tmpl.get("required_params", [])
                if p not in proposal.value or proposal.value[p] is None or proposal.value[p] == ""
            ]
            if missing_params:
                is_blocked = True
                msg = f"Missing required parameter(s) {missing_params} for template '{proposal.template_id}'."
                checks.append(VerificationCheck(name="template_params_complete", passed=False, reason=msg))
                blocked_reasons.append(msg)
                suggested_remedy = f"Provide all required template parameters: {tmpl.get('required_params', [])}."
            else:
                checks.append(VerificationCheck(name="template_params_complete", passed=True, reason="All required template parameters present."))

        # 3. Injection and Malicious Content Check
        has_injection, injection_msg = self._check_injection_patterns(proposal)
        if has_injection:
            is_blocked = True
            checks.append(VerificationCheck(name="injection_safety", passed=False, reason=injection_msg))
            blocked_reasons.append(injection_msg)
            suggested_remedy = "Remove unescaped tags or prompt injection directives from claim text."
        else:
            checks.append(VerificationCheck(name="injection_safety", passed=True, reason="Zero injection patterns detected."))

        # 4. Resolve Case Bundle
        case_data = case_bundle
        if case_data is None and self.conn is not None:
            case_data = self._load_case_bundle_from_db(proposal.case_id)

        if not case_data:
            is_blocked = True
            msg = f"Referenced case '{proposal.case_id}' does not exist or has no data."
            checks.append(VerificationCheck(name="case_exists", passed=False, reason=msg))
            blocked_reasons.append(msg)
            suggested_remedy = "Verify the case ID or ensure the investigation case has been generated."
        else:
            checks.append(VerificationCheck(name="case_exists", passed=True, reason=f"Case '{proposal.case_id}' exists."))

        # 5. Evidence References Existence and Case Containment
        if case_data and not is_blocked:
            if not proposal.evidence_refs:
                is_blocked = True
                msg = "Empty evidence references: Proof-carrying claims must cite at least one valid event or finding reference."
                checks.append(VerificationCheck(name="evidence_exists", passed=False, reason=msg))
                blocked_reasons.append(msg)
                suggested_remedy = "Cite specific event or finding IDs supporting this claim."
            else:
                case_event_ids: Set[str] = {e["event_id"] for e in case_data.get("events", [])}
                case_finding_ids: Set[str] = {f["finding_id"] for f in case_data.get("findings", [])}

                # Also include events referenced by the findings in the case
                for f in case_data.get("findings", []):
                    for supp_id in f.get("supporting_event_ids", []):
                        case_event_ids.add(supp_id)

                missing_refs: List[str] = []
                cross_case_refs: List[str] = []

                for ref in proposal.evidence_refs:
                    if ref not in case_event_ids and ref not in case_finding_ids:
                        # Check whether it exists globally in another case / DB
                        if self._check_ref_exists_globally(ref):
                            cross_case_refs.append(ref)
                        else:
                            missing_refs.append(ref)

                if missing_refs or cross_case_refs:
                    is_blocked = True
                    if cross_case_refs:
                        msg = (
                            f"Cross-case evidence reference: Evidence ID(s) {cross_case_refs} "
                            f"belong to a different case or are not associated with case '{proposal.case_id}'."
                        )
                        checks.append(VerificationCheck(name="case_containment", passed=False, reason=msg))
                        blocked_reasons.append(msg)
                        suggested_remedy = "Remove cross-case references. Only cite evidence linked to this investigation case."

                    if missing_refs:
                        msg = f"Nonexistent evidence references: Evidence ID(s) {missing_refs} do not exist in the database."
                        checks.append(VerificationCheck(name="evidence_exists", passed=False, reason=msg))
                        blocked_reasons.append(msg)
                        suggested_remedy = "Verify that all cited event and finding IDs exist."
                else:
                    checks.append(
                        VerificationCheck(
                            name="evidence_exists",
                            passed=True,
                            reason=f"All {len(proposal.evidence_refs)} cited evidence references verified in case bundle.",
                        )
                    )
                    checks.append(
                        VerificationCheck(
                            name="case_containment",
                            passed=True,
                            reason="All evidence references are strictly contained within the referenced case.",
                        )
                    )

        # 6. Type-Specific Value Verification & IP Guardrail
        if case_data and not is_blocked:
            val_ok, val_msg, val_remedy, qual_note = self._verify_claim_value(proposal, case_data)
            if not val_ok:
                is_blocked = True
                checks.append(VerificationCheck(name="value_matches_evidence", passed=False, reason=val_msg))
                blocked_reasons.append(val_msg)
                if val_remedy:
                    suggested_remedy = val_remedy
            else:
                checks.append(VerificationCheck(name="value_matches_evidence", passed=True, reason=val_msg))
                if qual_note:
                    qualification_notes.append(qual_note)

        # 7. Data Quality Audit
        if case_data and not is_blocked:
            has_dq_issue = False
            dq_notes: List[str] = []

            for f in case_data.get("findings", []):
                if f.get("rule_id") == "INGEST-001" and f.get("finding_id") in proposal.evidence_refs:
                    has_dq_issue = True
                    dq_notes.append("Referenced evidence contains an INGEST-001 data quality anomaly finding.")

            for e in case_data.get("events", []):
                if e.get("event_id") in proposal.evidence_refs:
                    attrs = e.get("attributes", {})
                    if attrs.get("timezone_inferred") or attrs.get("data_quality_warning"):
                        has_dq_issue = True
                        dq_notes.append(f"Event '{e.get('event_id')}' carries data quality warning: timezone inferred or sanitized.")

            if has_dq_issue:
                is_qualified = True
                checks.append(VerificationCheck(name="data_quality_clean", passed=False, reason="; ".join(dq_notes)))
                qualification_notes.extend(dq_notes)
            else:
                checks.append(VerificationCheck(name="data_quality_clean", passed=True, reason="Referenced evidence is clean with zero data quality anomalies."))

        # 8. Certainty Alignment Check
        if not is_blocked:
            if proposal.certainty in ("inferred", "hypothesis"):
                is_qualified = True
                msg = f"Claim marked as '{proposal.certainty}' rather than observed factual certainty."
                checks.append(VerificationCheck(name="certainty_alignment", passed=True, reason=msg))
                qualification_notes.append(msg)
            else:
                checks.append(VerificationCheck(name="certainty_alignment", passed=True, reason="Claim certainty aligns with directly observed facts."))

        # 8. Determine Final Status
        if is_blocked:
            final_status = "blocked"
        elif is_qualified:
            final_status = "qualified"
        else:
            final_status = "verified"

        # 9. Safe Template Rendering
        rendered_text = SafeClaimRenderer.render(
            template_id=proposal.template_id,
            value=proposal.value,
            status=final_status,
            qualification_notes=qualification_notes,
            blocked_reasons=blocked_reasons,
        )

        verification_id = f"vchk_{uuid.uuid4().hex[:16]}"
        result = ClaimVerificationResult(
            verification_id=verification_id,
            claim_id=proposal.claim_id,
            case_id=proposal.case_id,
            status=final_status,
            verification_version=VERIFIER_VERSION,
            checks=checks,
            rendered_text=rendered_text,
            qualification_notes=qualification_notes,
            blocked_reasons=blocked_reasons,
            suggested_remedy=suggested_remedy,
            evidence_refs=proposal.evidence_refs,
            verified_at=datetime.now(timezone.utc).isoformat(),
        )
        return result

    def verify_batch(
        self,
        proposals: List[ClaimProposal],
        case_bundle: Optional[Dict[str, Any]] = None,
    ) -> List[ClaimVerificationResult]:
        """Execute verification across a list of claim proposals."""
        return [self.verify_proposal(p, case_bundle=case_bundle) for p in proposals]

    # -------------------------------------------------------------------------
    # Internal Verification Helpers
    # -------------------------------------------------------------------------

    def _check_injection_patterns(self, proposal: ClaimProposal) -> Tuple[bool, str]:
        """Scan claim predicate and string values for script or prompt injection."""
        text_samples = [proposal.predicate, proposal.template_id, proposal.certainty]
        for v in proposal.value.values():
            if isinstance(v, str):
                text_samples.append(v)

        for text in text_samples:
            for pat in INJECTION_PATTERNS:
                if pat.search(text):
                    return True, f"Prohibited injection pattern detected: '{pat.pattern}'."
        return False, ""

    def _load_case_bundle_from_db(self, case_id: str) -> Optional[Dict[str, Any]]:
        """Fetch case details and all linked findings/events from database connection."""
        if not self.conn:
            return None
        from backend.persistence.repository import IngestionRepository

        repo = IngestionRepository(self.conn)
        return repo.get_case(case_id)

    def _check_ref_exists_globally(self, ref_id: str) -> bool:
        """Check whether an evidence ID exists in the global database."""
        if not self.conn:
            return False
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM normalized_events WHERE event_id = ? LIMIT 1;", (ref_id,))
        if cursor.fetchone():
            return True
        cursor.execute("SELECT 1 FROM findings WHERE finding_id = ? LIMIT 1;", (ref_id,))
        if cursor.fetchone():
            return True
        return False

    def _verify_claim_value(
        self,
        proposal: ClaimProposal,
        case: Dict[str, Any],
    ) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """
        Verify that evidence actually supports the claimed type and value parameters.
        Returns: (passed: bool, reason: str, suggested_remedy: Optional[str], qualification_note: Optional[str])
        """
        claim_type = proposal.claim_type
        val = proposal.value
        events = case.get("events", [])
        findings = case.get("findings", [])

        # Create lookup maps for referenced evidence
        ref_set = set(proposal.evidence_refs)
        ref_events = [e for e in events if e["event_id"] in ref_set]
        ref_findings = [f for f in findings if f["finding_id"] in ref_set]

        # Also pull supporting events from referenced findings
        for f in ref_findings:
            for e in events:
                if e["event_id"] in f.get("supporting_event_ids", []) and e not in ref_events:
                    ref_events.append(e)

        # ---------------------------------------------------------------------
        # 1. Event Count Claim
        # ---------------------------------------------------------------------
        if claim_type == "event_count":
            if not proposal.evidence_refs:
                return False, "Evidence references cannot be empty for an event_count claim.", "Cite specific event IDs.", None

            claimed_count = val.get("count")
            if claimed_count is None or not isinstance(claimed_count, (int, float)):
                return False, "Missing or non-numeric 'count' in claim value.", "Provide integer 'count'.", None

            claimed_type = val.get("event_type")
            if claimed_type:
                # Strictly match against event_type or action attribute (DEF-CLAIM-007)
                matching_events = [
                    e for e in ref_events
                    if e.get("event_type") == claimed_type
                    or e.get("attributes", {}).get("action") == claimed_type
                    or e.get("attributes", {}).get("event_name") == claimed_type
                ]
            else:
                matching_events = list(ref_events)

            # DEF-CLAIM-002: Check predicate or status filter
            if proposal.predicate == "failed_event_count":
                matching_events = [
                    e for e in matching_events
                    if str(e.get("status", "")).upper() in ("FAILURE", "LOCKED", "ERROR")
                ]
            elif "status" in val and val["status"]:
                req_status = str(val["status"]).upper()
                matching_events = [
                    e for e in matching_events
                    if str(e.get("status", "")).upper() == req_status
                ]

            actual_count = len(matching_events)
            if actual_count != int(claimed_count):
                return (
                    False,
                    f"Claimed count {int(claimed_count)} does not match verified count {actual_count} of referenced events.",
                    f"Update claimed count to {actual_count} to reflect the referenced evidence.",
                    None,
                )
            return True, f"Verified: Exactly {actual_count} matching event(s) found in evidence.", None, None

        # ---------------------------------------------------------------------
        # 2. Finding Exists Claim
        # ---------------------------------------------------------------------
        if claim_type == "finding_exists":
            if not proposal.evidence_refs:
                return False, "Evidence references cannot be empty for a finding_exists claim.", "Cite the finding ID as evidence.", None

            rule_id = val.get("rule_id")
            if not rule_id:
                return False, "Missing 'rule_id' in claim value.", "Specify the rule_id for the finding.", None

            matched_findings = [f for f in findings if f.get("rule_id") == rule_id]
            if not matched_findings:
                return False, f"No finding for rule '{rule_id}' exists in case.", f"Rule '{rule_id}' has not triggered in this case.", None

            # DEF-CLAIM-004: Ensure at least one finding matching rule_id is cited in evidence_refs
            ref_matched = [f for f in matched_findings if f.get("finding_id") in ref_set]
            if not ref_matched:
                return (
                    False,
                    f"Referenced evidence does not contain finding for rule '{rule_id}'.",
                    f"Include finding ID (e.g. {matched_findings[0].get('finding_id')}) in evidence_refs.",
                    None,
                )

            claimed_severity = val.get("severity")
            if claimed_severity:
                sev_match = any(f.get("severity") == claimed_severity for f in ref_matched)
                if not sev_match:
                    actual_sev = ref_matched[0].get("severity")
                    return (
                        False,
                        f"Claimed severity '{claimed_severity}' does not match actual finding severity '{actual_sev}'.",
                        f"Update claimed severity to '{actual_sev}'.",
                        None,
                    )

            return True, f"Verified: Finding for rule '{rule_id}' exists in case.", None, None

        # ---------------------------------------------------------------------
        # 3. Rule Match Condition Claim
        # ---------------------------------------------------------------------
        if claim_type == "rule_match":
            if not proposal.evidence_refs:
                return False, "Evidence references cannot be empty for a rule_match claim.", "Cite the finding ID as evidence.", None

            rule_id = val.get("rule_id")
            finding_id = val.get("finding_id")
            condition_key = val.get("condition_key")

            if finding_id and finding_id not in ref_set:
                return False, f"Finding '{finding_id}' is not cited in proposal evidence references.", "Include finding_id in evidence_refs.", None

            matched_finding = next((f for f in findings if f.get("finding_id") == finding_id), None)
            if not matched_finding:
                return False, f"Referenced finding '{finding_id}' does not exist in case.", "Provide a valid finding_id.", None

            if rule_id and matched_finding.get("rule_id") != rule_id:
                return False, f"Finding '{finding_id}' is for rule '{matched_finding.get('rule_id')}', not '{rule_id}'.", None, None

            if condition_key and condition_key not in matched_finding.get("matched_conditions", {}):
                return (
                    False,
                    f"Condition key '{condition_key}' not present in finding's matched conditions.",
                    f"Available condition keys: {list(matched_finding.get('matched_conditions', {}).keys())}",
                    None,
                )

            return True, f"Verified: Rule condition matches finding '{finding_id}'.", None, None

        # ---------------------------------------------------------------------
        # 4. Time Window Claim
        # ---------------------------------------------------------------------
        if claim_type == "time_window":
            if not proposal.evidence_refs:
                return False, "Evidence references cannot be empty for a time_window claim.", "Cite supporting event or finding IDs.", None

            claimed_start = val.get("start_time")
            claimed_end = val.get("end_time")
            if not claimed_start or not claimed_end:
                return False, "Missing 'start_time' or 'end_time' in claim value.", "Provide start_time and end_time.", None

            # DEF-CLAIM-001: Check start <= end
            if claimed_start > claimed_end:
                return (
                    False,
                    f"Inverted time window: start_time '{claimed_start}' is after end_time '{claimed_end}'.",
                    "Ensure start_time is chronologically before or equal to end_time.",
                    None,
                )

            timestamps: List[str] = []
            for e in ref_events:
                if e.get("timestamp"):
                    timestamps.append(e["timestamp"])
            for f in ref_findings:
                if f.get("first_observed_at"):
                    timestamps.append(f["first_observed_at"])
                if f.get("last_observed_at"):
                    timestamps.append(f["last_observed_at"])

            if not timestamps:
                return False, "No timestamps available in referenced evidence to verify time window.", None, None

            timestamps.sort()
            evidence_start = timestamps[0]
            evidence_end = timestamps[-1]

            # DEF-CLAIM-001: Ensure claimed window covers the evidence (claimed_start <= evidence_start and claimed_end >= evidence_end)
            if claimed_start > evidence_start or claimed_end < evidence_end:
                return (
                    False,
                    f"Claimed window ({claimed_start} to {claimed_end}) does not encompass referenced evidence window ({evidence_start} to {evidence_end}).",
                    f"Expand time window to cover observed evidence: {evidence_start} to {evidence_end}.",
                    None,
                )

            # DEF-CLAIM-001: If duration_seconds provided, verify it matches claimed start/end
            if "duration_seconds" in val and val["duration_seconds"] is not None:
                try:
                    dt_start = datetime.fromisoformat(claimed_start.replace("Z", "+00:00"))
                    dt_end = datetime.fromisoformat(claimed_end.replace("Z", "+00:00"))
                    expected_duration = (dt_end - dt_start).total_seconds()
                    claimed_duration = float(val["duration_seconds"])
                    if abs(claimed_duration - expected_duration) > 1.0:
                        return (
                            False,
                            f"Claimed duration_seconds ({claimed_duration}) does not match window duration ({expected_duration} seconds).",
                            f"Set duration_seconds to {int(expected_duration)}.",
                            None,
                        )
                except Exception as ex:
                    return False, f"Invalid datetime format or duration: {str(ex)}.", "Use ISO 8601 UTC timestamps.", None

            return True, f"Verified: Time window matches evidence bounds ({evidence_start} to {evidence_end}).", None, None

        # ---------------------------------------------------------------------
        # 5. Entity Observed Claim & IP Guardrail
        # ---------------------------------------------------------------------
        if claim_type == "entity_observed":
            if not proposal.evidence_refs:
                return False, "Evidence references cannot be empty for an entity_observed claim.", "Cite supporting event or finding IDs.", None

            entity_type = val.get("entity_type")
            entity_val = val.get("entity_value")
            if not entity_type or not entity_val:
                return False, "Missing 'entity_type' or 'entity_value'.", "Specify entity_type and entity_value.", None

            # CRITICAL IP GUARDRAIL: Reject claims inferring user identity from source IP alone
            if entity_type == "user_principal":
                users_in_evidence = {
                    e.get("user_principal") for e in ref_events if e.get("user_principal")
                }
                if not users_in_evidence:
                    # Check if evidence only has IP addresses
                    ips_in_evidence = {e.get("source_ip") for e in ref_events if e.get("source_ip")}
                    if ips_in_evidence:
                        return (
                            False,
                            f"IP-only identity inference rejected: Cannot infer user identity '{entity_val}' from IP address(es) {sorted(list(ips_in_evidence))} alone.",
                            "Attribute network activity to source IP, not unverified user principal.",
                            None,
                        )

            # Check if entity_val is present in referenced evidence
            found = False
            for e in ref_events:
                if entity_type == "user_principal" and e.get("user_principal") == entity_val:
                    found = True
                    break
                if entity_type == "source_ip" and e.get("source_ip") == entity_val:
                    found = True
                    break
                if entity_val in str(e.get("attributes", {}).values()):
                    found = True
                    break

            for f in ref_findings:
                if f.get("matched_entity") == entity_val:
                    found = True
                    break

            if not found:
                return (
                    False,
                    f"Entity '{entity_val}' of type '{entity_type}' is not present in referenced evidence.",
                    "Verify entity spelling or reference evidence containing the entity.",
                    None,
                )

            return True, f"Verified: Entity '{entity_val}' confirmed in evidence.", None, None

        # ---------------------------------------------------------------------
        # 6. Case Status Claim
        # ---------------------------------------------------------------------
        if claim_type == "case_status":
            claimed_status = val.get("status")
            claimed_severity = val.get("severity")

            actual_status = case.get("status")
            actual_severity = case.get("severity")

            if claimed_status and claimed_status != actual_status:
                return (
                    False,
                    f"Claimed status '{claimed_status}' does not match case status '{actual_status}'.",
                    f"Update status to '{actual_status}'.",
                    None,
                )

            if claimed_severity and claimed_severity != actual_severity:
                return (
                    False,
                    f"Claimed severity '{claimed_severity}' does not match case severity '{actual_severity}'.",
                    f"Update severity to '{actual_severity}'.",
                    None,
                )

            return True, f"Verified: Case status '{actual_status}' and severity '{actual_severity}' confirmed.", None, None

        # ---------------------------------------------------------------------
        # 7. Correlation Relationship Claim
        # ---------------------------------------------------------------------
        if claim_type == "correlation_relationship":
            key_type = val.get("key_type")
            key_val = val.get("key_value")

            actual_key_type = case.get("correlation_key_type")
            actual_key_val = case.get("correlation_key_value")

            if key_type != actual_key_type or key_val != actual_key_val:
                return (
                    False,
                    f"Claimed correlation ({key_type}='{key_val}') does not match actual case correlation ({actual_key_type}='{actual_key_val}').",
                    f"Update correlation key to {actual_key_type}='{actual_key_val}'.",
                    None,
                )

            return True, f"Verified: Correlation on {actual_key_type}='{actual_key_val}' confirmed.", None, None

        # ---------------------------------------------------------------------
        # 8. Data Quality Anomaly Claim
        # ---------------------------------------------------------------------
        if claim_type == "data_quality_issue":
            if not proposal.evidence_refs:
                return (
                    False,
                    "Evidence references cannot be empty for a data_quality_issue claim.",
                    "Cite the INGEST-001 finding ID or affected event/record IDs.",
                    None,
                )

            anomaly_type = val.get("anomaly_type")
            claimed_record_count = val.get("record_count")

            ingest_findings = [f for f in findings if f.get("rule_id") == "INGEST-001"]
            if not ingest_findings:
                return (
                    False,
                    "No data quality finding (INGEST-001) is associated with this case.",
                    "Verify whether data quality issues were reported during ingestion or normalization.",
                    None,
                )

            actual_records = 0
            for f in ingest_findings:
                rec_ids = f.get("matched_conditions", {}).get("record_ids", [])
                if rec_ids:
                    actual_records += len(rec_ids)
                elif f.get("supporting_event_ids"):
                    actual_records += len(f["supporting_event_ids"])

            if actual_records == 0:
                actual_records = sum(
                    1 for e in events
                    if e.get("attributes", {}).get("data_quality_warning")
                    or e.get("attributes", {}).get("timezone_inferred")
                )

            if claimed_record_count is not None:
                try:
                    if int(claimed_record_count) != actual_records:
                        return (
                            False,
                            f"Claimed record_count ({claimed_record_count}) does not match actual count of data quality anomalies ({actual_records}).",
                            f"Update record_count to {actual_records}.",
                            None,
                        )
                except (ValueError, TypeError):
                    return False, f"Invalid non-integer record_count: '{claimed_record_count}'.", "Provide integer record_count.", None

            return True, f"Verified: Data quality anomaly '{anomaly_type}' supported by INGEST-001 finding.", None, "Normalization anomaly present"

        return False, f"Unhandled claim type '{claim_type}'.", None, None

