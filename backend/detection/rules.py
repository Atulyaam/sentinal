"""Deterministic Detection Rules and Rule Registry for Project Sentinel."""

from datetime import datetime, timezone
import hashlib
import json
import logging
import posixpath
import re
from typing import Any, Callable, Dict, List, Optional, Tuple
import urllib.parse

from backend.detection.models import Finding, RuleDefinition, compute_rule_config_hash

compute_config_hash = compute_rule_config_hash

logger = logging.getLogger("sentinel.detection.rules")

RULE_ID_REGEX = re.compile(r"^[A-Z]{3,8}-\d{3}$")
VALID_SEVERITIES = {"Critical", "High", "Medium", "Low", "Info"}


def compute_finding_id(rule_id: str, rule_version: str, config_hash: str, dedupe_key: str) -> str:
    """Generate a collision-resistant, deterministic finding identifier."""
    seed = f"{rule_id}:{rule_version}:{config_hash}:{dedupe_key}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()[:24]
    return f"find_{digest}"


def normalize_web_route(raw: str) -> str:
    """
    Safely normalize a raw URI/route string for security inspection:
    - Strips query string and fragments
    - Handles redundant leading slashes (e.g. //admin -> /admin)
    - URL unquotes percent-encoded sequences
    - Resolves redundant slashes and relative path traversal (..)
    - Returns lowercase normalized path
    """
    if not raw or not isinstance(raw, str):
        return ""
    cleaned = raw.strip()
    if "://" in cleaned:
        try:
            parts = urllib.parse.urlsplit(cleaned)
            path = parts.path
        except Exception:
            path = cleaned.split("?")[0].split("#")[0]
    else:
        path = cleaned.split("?")[0].split("#")[0]
        if path.startswith("//"):
            path = "/" + path.lstrip("/")

    if not path:
        return ""

    unquoted = urllib.parse.unquote(path)
    normalized = posixpath.normpath(unquoted)
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    return normalized.lower()


def is_sensitive_route(target: str, sensitive_routes: List[str]) -> bool:
    """
    Determine if a target route matches any configured sensitive route pattern.
    Handles exact matches, path-prefix matches (/admin/...), and dotfile suffixes (/.env).
    Prevents false-positive partial matches like /administrator matching /admin.
    """
    norm_target = normalize_web_route(target)
    if not norm_target:
        return False

    for pattern in sensitive_routes:
        if not pattern:
            continue
        norm_p = normalize_web_route(str(pattern))
        if not norm_p:
            continue

        # Exact match (e.g. /admin == /admin)
        if norm_target == norm_p:
            return True
        # Directory prefix match (e.g. /admin/users matches /admin)
        if norm_target.startswith(norm_p.rstrip("/") + "/"):
            return True
        # Dotfile or sub-resource match (e.g. /sub/app/.env matches /.env)
        if norm_p.startswith("/.") and norm_target.endswith(norm_p):
            return True

    return False


def parse_utc_epoch(iso_ts: str) -> Optional[float]:
    """Parse an ISO-8601 UTC timestamp string to a unix epoch float."""
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return None


def validate_rule_definition(definition: Any) -> None:
    """
    Validate that a rule definition dictionary satisfies strict schema and security rules.
    Raises ValueError on validation failure.
    """
    if hasattr(definition, "to_dict"):
        definition = definition.to_dict()
    elif not isinstance(definition, dict):
        raise ValueError("Rule definition must be a dictionary.")

    required_fields = ["rule_id", "version", "name", "description", "severity", "enabled", "config", "limitations"]
    for field in required_fields:
        if field not in definition:
            raise ValueError(f"Rule definition missing required field: '{field}'")

    rule_id = str(definition["rule_id"]).strip()
    if not RULE_ID_REGEX.match(rule_id):
        raise ValueError(f"Invalid rule_id '{rule_id}'. Must match pattern '^[A-Z]{{3,8}}-\\d{{3}}$'")

    version = str(definition["version"]).strip()
    if not version or not re.match(r"^\d+\.\d+(\.\d+)?$", version):
        raise ValueError(f"Invalid rule version '{version}'. Must be semantic format (e.g. 1.0.0).")

    severity = str(definition["severity"]).strip()
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"Invalid severity '{severity}'. Must be one of {sorted(VALID_SEVERITIES)}")

    if not isinstance(definition["enabled"], bool):
        raise ValueError("Field 'enabled' must be a boolean.")

    if not isinstance(definition["config"], dict):
        raise ValueError("Field 'config' must be a dictionary.")

    name = str(definition["name"]).strip()
    if not name:
        raise ValueError("Field 'name' cannot be empty.")

    description = str(definition["description"]).strip()
    if not description:
        raise ValueError("Field 'description' cannot be empty.")

    limitations = str(definition["limitations"]).strip()
    if not limitations:
        raise ValueError("Field 'limitations' cannot be empty.")


class BaseRuleEvaluator:
    """Base interface for deterministic rule evaluators."""

    rule_id: str
    version: str
    name: str
    description: str
    severity: str
    limitations: str
    default_config: Dict[str, Any]

    def __init__(self, config: Optional[Dict[str, Any]] = None, enabled: bool = True) -> None:
        self.config = dict(self.default_config)
        if config:
            self.config.update(config)
        self.enabled = enabled
        self._rule_def = RuleDefinition(
            rule_id=self.rule_id,
            version=self.version,
            name=self.name,
            description=self.description,
            severity=self.severity,
            enabled=self.enabled,
            config=self.config,
            limitations=self.limitations,
        )

    @property
    def definition(self) -> RuleDefinition:
        return self._rule_def

    def evaluate(
        self,
        events: List[Dict[str, Any]],
        errors: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Finding]:
        """
        Evaluate canonical events (and optional errors) and return generated findings.
        Must be implemented by subclasses.
        """
        raise NotImplementedError


class Auth001RepeatedFailuresRule(BaseRuleEvaluator):
    """
    AUTH-001: Repeated Authentication Failures.
    Detects at least 5 failed authentications for the same user within 10 minutes.
    """

    rule_id = "AUTH-001"
    version = "1.0.0"
    name = "Repeated Authentication Failures"
    description = "Detects 5 or more failed authentications for the same user within a 10-minute window."
    severity = "Medium"
    limitations = "Could be user error, forgotten password, or misconfigured client."
    default_config = {
        "target_event_type": "user_authentication",
        "target_status": "FAILURE",
        "threshold_count": 5,
        "window_seconds": 600,
    }

    def evaluate(
        self,
        events: List[Dict[str, Any]],
        errors: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Finding]:
        if not self.enabled:
            return []

        target_type = self.config.get("target_event_type", "user_authentication")
        target_status = self.config.get("target_status", "FAILURE")
        threshold = int(self.config.get("threshold_count", 5))
        window_sec = float(self.config.get("window_seconds", 600))

        # Filter eligible failure events with valid user and timestamp
        user_failures: Dict[str, List[Tuple[float, Dict[str, Any]]]] = {}
        for evt in events:
            if evt.get("event_type") == target_type and evt.get("status") == target_status:
                user = evt.get("user_principal")
                if user:
                    epoch = parse_utc_epoch(evt["timestamp"])
                    if epoch is not None:
                        user_failures.setdefault(user, []).append((epoch, evt))

        findings: List[Finding] = []
        for user, user_evts in user_failures.items():
            user_evts.sort(key=lambda x: x[0])
            i = 0
            n = len(user_evts)
            while i < n:
                # Find matching sliding window starting at i
                window_events = [user_evts[i]]
                start_epoch = user_evts[i][0]
                j = i + 1
                while j < n and (user_evts[j][0] - start_epoch) <= window_sec:
                    window_events.append(user_evts[j])
                    j += 1

                if len(window_events) >= threshold:
                    # Construct finding
                    matching_evts = [item[1] for item in window_events]
                    first_obs = matching_evts[0]["timestamp"]
                    last_obs = matching_evts[-1]["timestamp"]
                    event_ids = [e["event_id"] for e in matching_evts]
                    window_bucket = int(start_epoch // window_sec)
                    dedupe_key = f"auth_fail:{user}:{window_bucket}"
                    finding_id = compute_finding_id(
                        self.rule_id, self.version, self.definition.config_hash, dedupe_key
                    )

                    duration = int(matching_evts[-1]["timestamp"] != matching_evts[0]["timestamp"])
                    finding = Finding(
                        finding_id=finding_id,
                        rule_id=self.rule_id,
                        rule_version=self.version,
                        rule_config_hash=self.definition.config_hash,
                        severity=self.severity,
                        status="open",
                        title=f"Repeated Authentication Failures for {user}",
                        description=(
                            f"Detected {len(matching_evts)} failed authentication attempts for user '{user}' "
                            f"within {int(window_events[-1][0] - start_epoch)} seconds."
                        ),
                        first_observed_at=first_obs,
                        last_observed_at=last_obs,
                        matched_entity=user,
                        matched_conditions={
                            "failure_count": len(matching_evts),
                            "threshold": threshold,
                            "window_seconds": int(window_sec),
                            "user_principal": user,
                            "source_ips": sorted(list({e.get("source_ip") for e in matching_evts if e.get("source_ip")})),
                        },
                        supporting_event_ids=event_ids,
                        limitations=self.limitations,
                        dedupe_key=dedupe_key,
                    )
                    findings.append(finding)
                    # Advance i to j to avoid overlapping duplicate windows for the same burst
                    i = j
                else:
                    i += 1

        return findings


class Auth002SuccessAfterFailuresRule(BaseRuleEvaluator):
    """
    AUTH-002: Success After Authentication Failures.
    Detects successful authentication within 30 minutes after an AUTH-001 failure burst for the same user.
    """

    rule_id = "AUTH-002"
    version = "1.0.0"
    name = "Success After Authentication Failures"
    description = "Detects successful authentication within 30 minutes following an authentication failure burst for the same user."
    severity = "High"
    limitations = "Does not identify the human at the keyboard; credentials may have been guessed or legitimately recalled."
    default_config = {
        "failure_threshold": 5,
        "failure_window_seconds": 600,
        "success_window_seconds": 1800,
    }

    def evaluate(
        self,
        events: List[Dict[str, Any]],
        errors: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Finding]:
        if not self.enabled:
            return []

        fail_threshold = int(self.config.get("failure_threshold", 5))
        fail_window_sec = float(self.config.get("failure_window_seconds", 600))
        succ_window_sec = float(self.config.get("success_window_seconds", 1800))

        # Group all user auth events by user_principal
        user_events: Dict[str, List[Tuple[float, Dict[str, Any]]]] = {}
        for evt in events:
            if evt.get("event_type") == "user_authentication" and evt.get("user_principal"):
                epoch = parse_utc_epoch(evt["timestamp"])
                if epoch is not None:
                    user_events.setdefault(evt["user_principal"], []).append((epoch, evt))

        findings: List[Finding] = []
        for user, evts_list in user_events.items():
            evts_list.sort(key=lambda x: x[0])
            n = len(evts_list)
            i = 0
            while i < n:
                # Look for a sequence of >= fail_threshold failures within fail_window_sec
                if evts_list[i][1].get("status") == "FAILURE":
                    start_epoch = evts_list[i][0]
                    fail_events = [(evts_list[i][0], evts_list[i][1], i)]
                    j = i + 1
                    while j < n and (evts_list[j][0] - start_epoch) <= fail_window_sec:
                        if evts_list[j][1].get("status") == "FAILURE":
                            fail_events.append((evts_list[j][0], evts_list[j][1], j))
                        j += 1

                    if len(fail_events) >= fail_threshold:
                        last_fail_epoch = fail_events[-1][0]
                        last_fail_idx = fail_events[-1][2]
                        # Look for a SUCCESS event within succ_window_sec of last failure
                        k = last_fail_idx + 1
                        while k < n and (evts_list[k][0] - last_fail_epoch) <= succ_window_sec:
                            if evts_list[k][1].get("status") == "SUCCESS":
                                succ_evt = evts_list[k][1]
                                supporting_ids = [e[1]["event_id"] for e in fail_events] + [succ_evt["event_id"]]
                                dedupe_key = f"auth_succ_after_fail:{user}:{succ_evt['event_id']}"
                                finding_id = compute_finding_id(
                                    self.rule_id, self.version, self.definition.config_hash, dedupe_key
                                )
                                finding = Finding(
                                    finding_id=finding_id,
                                    rule_id=self.rule_id,
                                    rule_version=self.version,
                                    rule_config_hash=self.definition.config_hash,
                                    severity=self.severity,
                                    status="open",
                                    title=f"Successful Authentication Following Failure Burst for {user}",
                                    description=(
                                        f"User '{user}' successfully authenticated at {succ_evt['timestamp']} "
                                        f"within 30 minutes following {len(fail_events)} authentication failures."
                                    ),
                                    first_observed_at=fail_events[0][1]["timestamp"],
                                    last_observed_at=succ_evt["timestamp"],
                                    matched_entity=user,
                                    matched_conditions={
                                        "preceding_failures": len(fail_events),
                                        "success_event_id": succ_evt["event_id"],
                                        "user_principal": user,
                                        "success_ip": succ_evt.get("source_ip"),
                                        "delta_seconds": int(evts_list[k][0] - last_fail_epoch),
                                    },
                                    supporting_event_ids=supporting_ids,
                                    limitations=self.limitations,
                                    dedupe_key=dedupe_key,
                                )
                                findings.append(finding)
                                break
                            k += 1
                        i = j
                    else:
                        i += 1
                else:
                    i += 1

        return findings


class Web001SensitiveRouteBurstRule(BaseRuleEvaluator):
    """
    WEB-001: Sensitive Route Burst.
    Detects at least 3 requests to sensitive routes from the same source within 15 minutes.
    """

    rule_id = "WEB-001"
    version = "1.0.0"
    name = "Sensitive Route Burst"
    description = "Detects 3 or more requests to sensitive administrative endpoints from the same source within 15 minutes."
    severity = "Medium"
    limitations = "Route access may be legitimate administrative activity; distinguish between successful (200) and denied (401/403) access."
    default_config = {
        "sensitive_routes": ["/admin", "/api/v1/auth", "/login", "/wp-admin", "/internal", "/.env", "/config"],
        "threshold_count": 3,
        "window_seconds": 900,
    }

    def evaluate(
        self,
        events: List[Dict[str, Any]],
        errors: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Finding]:
        if not self.enabled:
            return []

        sensitive_routes = self.config.get("sensitive_routes", [])
        threshold = int(self.config.get("threshold_count", 3))
        window_sec = float(self.config.get("window_seconds", 900))

        # Filter web requests to sensitive routes, grouped by source_ip (or user_principal)
        entity_requests: Dict[str, List[Tuple[float, Dict[str, Any]]]] = {}
        for evt in events:
            if evt.get("event_type") == "web_request":
                raw_resource = evt.get("target_resource") or ""
                if is_sensitive_route(raw_resource, sensitive_routes):
                    # Require an explicit identity or source IP; do not group anonymous disparate traffic
                    entity = evt.get("source_ip") or evt.get("user_principal")
                    if not entity:
                        continue
                    epoch = parse_utc_epoch(evt["timestamp"])
                    if epoch is not None:
                        entity_requests.setdefault(entity, []).append((epoch, evt))

        findings: List[Finding] = []
        for entity, req_list in entity_requests.items():
            req_list.sort(key=lambda x: x[0])
            n = len(req_list)
            i = 0
            while i < n:
                start_epoch = req_list[i][0]
                window_events = [req_list[i]]
                j = i + 1
                while j < n and (req_list[j][0] - start_epoch) <= window_sec:
                    window_events.append(req_list[j])
                    j += 1

                if len(window_events) >= threshold:
                    matching_evts = [item[1] for item in window_events]
                    window_bucket = int(start_epoch // window_sec)
                    dedupe_key = f"sensitive_route:{entity}:{window_bucket}"
                    finding_id = compute_finding_id(
                        self.rule_id, self.version, self.definition.config_hash, dedupe_key
                    )
                    routes_accessed = sorted(list({e.get("target_resource") for e in matching_evts if e.get("target_resource")}))
                    statuses = [e.get("status") for e in matching_evts]
                    success_count = statuses.count("SUCCESS")
                    failure_count = statuses.count("FAILURE")

                    finding = Finding(
                        finding_id=finding_id,
                        rule_id=self.rule_id,
                        rule_version=self.version,
                        rule_config_hash=self.definition.config_hash,
                        severity=self.severity,
                        status="open",
                        title=f"Sensitive Route Access Burst from {entity}",
                        description=(
                            f"Detected {len(matching_evts)} requests to sensitive routes from '{entity}' "
                            f"within {int(window_events[-1][0] - start_epoch)} seconds. "
                            f"Responses: {success_count} SUCCESS (2xx), {failure_count} FAILURE (4xx)."
                        ),
                        first_observed_at=matching_evts[0]["timestamp"],
                        last_observed_at=matching_evts[-1]["timestamp"],
                        matched_entity=entity,
                        matched_conditions={
                            "request_count": len(matching_evts),
                            "threshold": threshold,
                            "window_seconds": int(window_sec),
                            "routes": routes_accessed,
                            "success_count": success_count,
                            "failure_count": failure_count,
                            "entity": entity,
                        },
                        supporting_event_ids=[e["event_id"] for e in matching_evts],
                        limitations=self.limitations,
                        dedupe_key=dedupe_key,
                    )
                    findings.append(finding)
                    i = j
                else:
                    i += 1

        return findings


class Priv001PrivilegeChangeRule(BaseRuleEvaluator):
    """
    PRIV-001: Explicit Privilege Escalation / Role Change.
    Detects explicit role assignments, privilege escalations, or administrative grants.
    """

    rule_id = "PRIV-001"
    version = "1.0.0"
    name = "Explicit Privilege Escalation / Role Change"
    description = "Detects explicit administrative privilege alteration, role modification, or permission grants."
    severity = "High"
    limitations = "Depends on source event quality; may represent legitimate authorized administrative configuration."
    default_config = {
        "privilege_event_types": ["role_changed", "privilege_granted", "admin_escalation", "group_add", "role_assigned"],
        "privilege_actions": ["grant_role", "assign_admin", "sudo", "privilege_escalation"],
    }

    def evaluate(
        self,
        events: List[Dict[str, Any]],
        errors: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Finding]:
        if not self.enabled:
            return []

        target_types = set(self.config.get("privilege_event_types", []))
        target_actions = set(self.config.get("privilege_actions", []))

        findings: List[Finding] = []
        for evt in events:
            evt_type = evt.get("event_type", "")
            attrs = evt.get("attributes", {})
            action = attrs.get("action") or attrs.get("event") or ""

            if evt_type in target_types or action in target_actions:
                actor = evt.get("user_principal")
                target_user = attrs.get("target_user") or attrs.get("user") or attrs.get("target") or evt.get("target_resource")
                entity = target_user or actor or "unknown_entity"
                dedupe_key = f"priv_change:{evt['event_id']}"
                finding_id = compute_finding_id(
                    self.rule_id, self.version, self.definition.config_hash, dedupe_key
                )
                finding = Finding(
                    finding_id=finding_id,
                    rule_id=self.rule_id,
                    rule_version=self.version,
                    rule_config_hash=self.definition.config_hash,
                    severity=self.severity,
                    status="open",
                    title=f"Explicit Privilege Escalation / Role Change for {entity}",
                    description=(
                        f"Observed privilege alteration event '{evt_type}' (action: '{action}') "
                        f"affecting entity '{entity}' at {evt['timestamp']}."
                    ),
                    first_observed_at=evt["timestamp"],
                    last_observed_at=evt["timestamp"],
                    matched_entity=entity,
                    matched_conditions={
                        "event_type": evt_type,
                        "action": action,
                        "actor": actor,
                        "target_entity": entity,
                        "target_user": target_user,
                        "source_ip": evt.get("source_ip"),
                        "event_id": evt["event_id"],
                    },
                    supporting_event_ids=[evt["event_id"]],
                    limitations=self.limitations,
                    dedupe_key=dedupe_key,
                )
                findings.append(finding)

        return findings


class Ingest001DataQualityRule(BaseRuleEvaluator):
    """
    INGEST-001: Ingestion Data Quality Anomaly.
    Detects unparseable timestamps, quarantined naive timestamps, or future-dated events.
    """

    rule_id = "INGEST-001"
    version = "1.0.0"
    name = "Ingestion & Timestamp Data Quality Anomaly"
    description = "Detects data-quality anomalies including quarantined timestamps, clock skew, or future-dated events."
    severity = "Info"
    limitations = "Data-quality issue, clock skew, or log export format error, not attack evidence."
    default_config = {
        "max_future_seconds": 86400,
    }

    def evaluate(
        self,
        events: List[Dict[str, Any]],
        errors: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Finding]:
        if not self.enabled:
            return []

        findings: List[Finding] = []
        max_future = float(self.config.get("max_future_seconds", 86400))
        now_epoch = datetime.now(timezone.utc).timestamp()

        # 1. Future-dated events check
        for evt in events:
            epoch = parse_utc_epoch(evt.get("timestamp", ""))
            if epoch is not None and (epoch - now_epoch) > max_future:
                dedupe_key = f"future_date:{evt['event_id']}"
                finding_id = compute_finding_id(
                    self.rule_id, self.version, self.definition.config_hash, dedupe_key
                )
                finding = Finding(
                    finding_id=finding_id,
                    rule_id=self.rule_id,
                    rule_version=self.version,
                    rule_config_hash=self.definition.config_hash,
                    severity=self.severity,
                    status="open",
                    title=f"Future-Dated Event Ingestion Anomaly in {evt.get('source_file')}",
                    description=(
                        f"Event timestamp '{evt['timestamp']}' is dated > 24 hours into the future "
                        f"in source file '{evt.get('source_file')}', line {evt.get('source_line')}."
                    ),
                    first_observed_at=evt["timestamp"],
                    last_observed_at=evt["timestamp"],
                    matched_entity=evt.get("source_file"),
                    matched_conditions={
                        "event_timestamp": evt["timestamp"],
                        "delta_future_seconds": int(epoch - now_epoch),
                        "source_file": evt.get("source_file"),
                        "source_line": evt.get("source_line"),
                    },
                    supporting_event_ids=[evt["event_id"]],
                    limitations=self.limitations,
                    dedupe_key=dedupe_key,
                )
                findings.append(finding)

        # 2. Normalization errors check (quarantined records)
        if errors:
            errors_by_import: Dict[str, List[Dict[str, Any]]] = {}
            for err in errors:
                errors_by_import.setdefault(err.get("import_id", "unknown"), []).append(err)

            for imp_id, imp_errs in errors_by_import.items():
                first_obs = imp_errs[0].get("created_at") or datetime.now(timezone.utc).isoformat()
                dedupe_key = f"ingest_errors:{imp_id}:{imp_errs[0]['error_code']}"
                finding_id = compute_finding_id(
                    self.rule_id, self.version, self.definition.config_hash, dedupe_key
                )
                finding = Finding(
                    finding_id=finding_id,
                    rule_id=self.rule_id,
                    rule_version=self.version,
                    rule_config_hash=self.definition.config_hash,
                    severity=self.severity,
                    status="open",
                    title=f"Ingestion Quarantine Alert: {imp_errs[0]['error_code']} in Import {imp_id}",
                    description=(
                        f"Encountered {len(imp_errs)} quarantined record(s) with error '{imp_errs[0]['error_code']}'. "
                        f"Sample diagnostic: {imp_errs[0].get('safe_error_message')}."
                    ),
                    first_observed_at=first_obs,
                    last_observed_at=first_obs,
                    matched_entity=imp_id,
                    matched_conditions={
                        "error_code": imp_errs[0]["error_code"],
                        "error_count": len(imp_errs),
                        "import_id": imp_id,
                        "record_ids": [e.get("record_id") for e in imp_errs if e.get("record_id")],
                        "sample_message": imp_errs[0].get("safe_error_message"),
                    },
                    supporting_event_ids=[],  # Quarantined records did not produce normalized events
                    limitations=self.limitations,
                    dedupe_key=dedupe_key,
                )
                findings.append(finding)

        return findings


class RuleRegistry:
    """Registry managing available detection rules."""

    def __init__(self) -> None:
        self._rules: Dict[str, BaseRuleEvaluator] = {}
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        self.register(Auth001RepeatedFailuresRule())
        self.register(Auth002SuccessAfterFailuresRule())
        self.register(Web001SensitiveRouteBurstRule())
        self.register(Priv001PrivilegeChangeRule())
        self.register(Ingest001DataQualityRule())

    def register(self, evaluator: BaseRuleEvaluator) -> None:
        validate_rule_definition(evaluator.definition.to_dict())
        self._rules[evaluator.rule_id] = evaluator
        logger.info("Registered detection rule %s (v%s, severity: %s)", evaluator.rule_id, evaluator.version, evaluator.severity)

    def get(self, rule_id: str) -> Optional[BaseRuleEvaluator]:
        return self._rules.get(rule_id)

    def list_rules(self) -> List[RuleDefinition]:
        return [evaluator.definition for evaluator in self._rules.values()]

    def set_enabled(self, rule_id: str, enabled: bool) -> bool:
        evaluator = self._rules.get(rule_id)
        if not evaluator:
            return False
        evaluator.enabled = enabled
        evaluator._rule_def.enabled = enabled
        return True


def get_builtin_rules() -> List[RuleDefinition]:
    """Return list of default built-in rule definitions."""
    return RuleRegistry().list_rules()
