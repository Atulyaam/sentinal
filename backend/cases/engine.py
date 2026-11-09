"""Deterministic and Explainable Correlation Engine for Project Sentinel."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.cases.models import (
    Case,
    CaseEvent,
    CaseFinding,
    CorrelationRelationship,
    compute_case_id,
    derive_case_severity,
)
from backend.persistence.repository import IngestionRepository

logger = logging.getLogger("sentinel.cases.engine")


def parse_utc_epoch(iso_ts: str) -> Optional[float]:
    """Parse an ISO-8601 UTC timestamp string to a unix epoch float."""
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return None


class CorrelationEngine:
    """
    Deterministic correlation engine that groups related security findings and canonical events
    into coherent investigation cases using approved correlation keys and explicit time windows.
    """

    ALGORITHM_VERSION = "1.0.0"

    def __init__(
        self,
        window_seconds: int = 3600,
        enable_ip_correlation: bool = False,  # MUST be False by default per master plan
    ) -> None:
        self.window_seconds = window_seconds
        self.enable_ip_correlation = enable_ip_correlation

    def extract_correlation_keys(
        self, finding: Dict[str, Any], supporting_events: List[Dict[str, Any]]
    ) -> List[Tuple[str, str]]:
        """
        Extract approved correlation keys from a finding and its supporting events.
        Approved keys: (key_type, safe_key_value)
        - 'user_principal': normalized user ID
        - 'session_id': explicit session ID from attributes
        - 'request_id': explicit request/trace ID from attributes or canonical fields
        Source IP is NEVER used as an identity key unless enable_ip_correlation is explicitly set.
        """
        keys: Set[Tuple[str, str]] = set()

        # 1. Primary entity on finding
        entity = finding.get("matched_entity")
        matched_conds = finding.get("matched_conditions", {})
        rule_id = finding.get("rule_id", "")

        # For AUTH and PRIV rules, matched_entity is user_principal
        if entity and entity not in ("unknown_entity", "unknown_source", "none"):
            if rule_id.startswith("AUTH-") or rule_id.startswith("PRIV-"):
                keys.add(("user_principal", str(entity).strip().lower()))

        # Inspect matched conditions for explicit user or target
        if "user_principal" in matched_conds and matched_conds["user_principal"]:
            keys.add(("user_principal", str(matched_conds["user_principal"]).strip().lower()))
        if "target_user" in matched_conds and matched_conds["target_user"]:
            keys.add(("user_principal", str(matched_conds["target_user"]).strip().lower()))

        # 2. Inspect supporting events for user, session, or request IDs
        for evt in supporting_events:
            user = evt.get("user_principal")
            if user and str(user).strip().lower() not in ("unknown", "none", "anonymous"):
                keys.add(("user_principal", str(user).strip().lower()))

            attrs = evt.get("attributes", {})
            session_id = attrs.get("session_id") or attrs.get("session")
            if session_id and str(session_id).strip():
                keys.add(("session_id", str(session_id).strip()))

            request_id = attrs.get("request_id") or attrs.get("trace_id") or evt.get("target_resource")
            if attrs.get("request_id") or attrs.get("trace_id"):
                req_val = str(attrs.get("request_id") or attrs.get("trace_id")).strip()
                if req_val:
                    keys.add(("request_id", req_val))

            # Strictly enforce that IP is NOT used as an identity correlation key
            if self.enable_ip_correlation and evt.get("source_ip"):
                keys.add(("source_ip", str(evt["source_ip"]).strip()))

        return sorted(list(keys), key=lambda x: (x[0], x[1]))

    def run_correlation(
        self,
        repository: IngestionRepository,
        limit_findings: int = 1000,
    ) -> Dict[str, Any]:
        """
        Execute deterministic correlation over active findings and assemble or update cases.
        """
        start_time = time.perf_counter()
        eval_id = f"corr_eval_{hashlib.sha256(str(time.time()).encode()).hexdigest()[:12]}"

        # 1. Fetch eligible findings
        findings, total_findings = repository.list_findings(limit=limit_findings, offset=0)
        if not findings:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            audit_record = {
                "evaluation_id": eval_id,
                "evaluated_at": datetime.now(timezone.utc).isoformat(),
                "findings_scanned": 0,
                "events_scanned": 0,
                "cases_created": 0,
                "cases_updated": 0,
                "duration_ms": duration_ms,
            }
            repository.record_correlation_evaluation(audit_record)
            return audit_record

        # Ensure deterministic ordering of findings
        findings.sort(key=lambda f: (f.get("first_observed_at", ""), f.get("finding_id", "")))

        # 2. Extract full details and supporting events for each finding
        detailed_findings: List[Dict[str, Any]] = []
        all_event_ids: Set[str] = set()
        for f in findings:
            det = repository.get_finding(f["finding_id"])
            if det:
                detailed_findings.append(det)
                for eid in det.get("supporting_event_ids", []):
                    all_event_ids.add(eid)

        # 3. Group findings by (key_type, key_value, window_bucket)
        # Groups: (key_type, key_value, window_bucket) -> List of detailed findings
        case_groups: Dict[Tuple[str, str, int], List[Dict[str, Any]]] = {}

        for finding in detailed_findings:
            supp_evts = finding.get("supporting_events", [])
            keys = self.extract_correlation_keys(finding, supp_evts)
            epoch = parse_utc_epoch(finding["first_observed_at"])
            if epoch is None:
                continue

            window_bucket = int(epoch // self.window_seconds)

            if not keys:
                # If no correlation key can be extracted, create an isolated single-finding case
                # using rule_id and finding_id as deterministic fallback key
                fallback_key = ("isolated_finding", finding["finding_id"])
                case_groups.setdefault((fallback_key[0], fallback_key[1], window_bucket), []).append(finding)
            else:
                # Prioritize 'user_principal', then 'session_id', then 'request_id'
                key_priority = {"user_principal": 1, "session_id": 2, "request_id": 3, "source_ip": 4}
                sorted_keys = sorted(keys, key=lambda k: (key_priority.get(k[0], 99), k[1]))
                primary_key = sorted_keys[0]
                case_groups.setdefault((primary_key[0], primary_key[1], window_bucket), []).append(finding)

        # 4. Build or update Case objects from groups
        assembled_cases: List[Case] = []
        assembled_case_findings: List[CaseFinding] = []
        assembled_case_events: List[CaseEvent] = []
        assembled_relationships: List[CorrelationRelationship] = []

        now_iso = datetime.now(timezone.utc).isoformat()

        for (k_type, k_val, bucket), group_findings in case_groups.items():
            # Deterministic sort
            group_findings.sort(key=lambda f: (f["first_observed_at"], f["finding_id"]))

            case_id = compute_case_id(k_type, k_val, bucket)
            dedupe_key = f"{k_type}:{k_val}:{bucket}"

            # Compute observed boundaries
            first_obs = group_findings[0]["first_observed_at"]
            last_obs = group_findings[-1]["last_observed_at"]
            for f in group_findings:
                if f["first_observed_at"] < first_obs:
                    first_obs = f["first_observed_at"]
                if f["last_observed_at"] > last_obs:
                    last_obs = f["last_observed_at"]

            # Derive severity
            finding_severities = [f.get("severity", "Medium") for f in group_findings]
            derived_sev, sev_rationale = derive_case_severity(finding_severities)

            # Build human-readable title & description
            rule_ids = sorted(list({f["rule_id"] for f in group_findings}))
            rules_str = ", ".join(rule_ids)

            if k_type == "user_principal":
                title = f"Suspicious Activity Correlated for User '{k_val}'"
                description = (
                    f"Correlated {len(group_findings)} security finding(s) ({rules_str}) "
                    f"affecting user '{k_val}' within a {self.window_seconds}s time window."
                )
            elif k_type == "session_id":
                title = f"Suspicious Activity in Session '{k_val[:12]}...'"
                description = (
                    f"Correlated {len(group_findings)} security finding(s) ({rules_str}) "
                    f"sharing session ID '{k_val}'."
                )
            elif k_type == "request_id":
                title = f"Activity Correlated on Request '{k_val[:12]}...'"
                description = (
                    f"Correlated {len(group_findings)} security finding(s) ({rules_str}) "
                    f"sharing request/trace ID '{k_val}'."
                )
            else:
                title = f"Security Finding {group_findings[0]['title']}"
                description = group_findings[0]["description"]

            # Collect linked event IDs across all findings in group
            group_event_ids: Set[str] = set()
            for f in group_findings:
                for eid in f.get("supporting_event_ids", []):
                    group_event_ids.add(eid)

            sorted_event_ids = sorted(list(group_event_ids))
            linked_finding_ids = [f["finding_id"] for f in group_findings]

            metadata = {
                "correlation_rationale": (
                    f"Grouped {len(group_findings)} finding(s) and {len(sorted_event_ids)} event(s) "
                    f"sharing {k_type} '{k_val}' within {self.window_seconds}s observation window."
                ),
                "severity_derivation": sev_rationale,
                "ip_correlation_used": False,
                "window_seconds": self.window_seconds,
                "window_bucket": bucket,
                "rule_ids": rule_ids,
            }

            case_obj = Case(
                case_id=case_id,
                title=title,
                description=description,
                status="Open",
                severity=derived_sev,
                correlation_key_type=k_type,
                correlation_key_value=k_val,
                first_observed_at=first_obs,
                last_observed_at=last_obs,
                dedupe_key=dedupe_key,
                algorithm_version=self.ALGORITHM_VERSION,
                metadata=metadata,
                linked_finding_ids=linked_finding_ids,
                linked_event_ids=sorted_event_ids,
                created_at=now_iso,
                updated_at=now_iso,
            )
            assembled_cases.append(case_obj)

            # Generate CaseFinding links
            for f in group_findings:
                cf = CaseFinding(
                    case_id=case_id,
                    finding_id=f["finding_id"],
                    correlation_rationale=(
                        f"Linked finding {f['rule_id']} ('{f['title']}') to case {case_id} via "
                        f"shared {k_type} '{k_val}' within time window."
                    ),
                    created_at=now_iso,
                )
                assembled_case_findings.append(cf)

            # Generate CaseEvent links
            for eid in sorted_event_ids:
                ce = CaseEvent(
                    case_id=case_id,
                    event_id=eid,
                    relationship_type="correlated_evidence",
                    correlation_rationale=(
                        f"Event {eid} was established as supporting evidence for finding(s) in this case "
                        f"and correlated under {k_type} '{k_val}'."
                    ),
                    created_at=now_iso,
                )
                assembled_case_events.append(ce)

            # Record formal CorrelationRelationship
            rel_id = f"rel_{hashlib.sha256(f'{case_id}:{k_type}:{k_val}'.encode()).hexdigest()[:16]}"
            rel = CorrelationRelationship(
                relationship_id=rel_id,
                case_id=case_id,
                relationship_type="shared_correlation_key",
                key_type=k_type,
                key_value=k_val,
                time_window_start=first_obs,
                time_window_end=last_obs,
                related_finding_ids=linked_finding_ids,
                related_event_ids=sorted_event_ids,
                rationale=(
                    f"These records were grouped because they share the same {k_type} '{k_val}' "
                    f"and occurred within the configured correlation window of {self.window_seconds} seconds. "
                    f"Source IP was not used to establish identity."
                ),
                algorithm_version=self.ALGORITHM_VERSION,
                created_at=now_iso,
            )
            assembled_relationships.append(rel)

        # 5. Persist cases, links, and relationships into SQLite repository
        persist_stats = repository.persist_cases_batch(
            cases=assembled_cases,
            case_findings=assembled_case_findings,
            case_events=assembled_case_events,
            relationships=assembled_relationships,
        )

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        audit_record = {
            "evaluation_id": eval_id,
            "evaluated_at": now_iso,
            "findings_scanned": len(detailed_findings),
            "events_scanned": len(all_event_ids),
            "cases_created": persist_stats.get("cases_created", 0),
            "cases_updated": persist_stats.get("cases_updated", 0),
            "duration_ms": duration_ms,
        }
        repository.record_correlation_evaluation(audit_record)

        logger.info(
            "Correlation run %s completed: %d findings scanned, %d cases created, %d updated in %.2fms",
            eval_id,
            len(detailed_findings),
            audit_record["cases_created"],
            audit_record["cases_updated"],
            duration_ms,
        )

        return audit_record

