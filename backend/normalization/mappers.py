"""Field mappers for transforming parsed records into canonical normalized events."""

import hashlib
import ipaddress
import logging
from typing import Any, Dict, Optional

from backend.normalization.timestamps import parse_and_normalize_timestamp

logger = logging.getLogger("sentinel.normalization.mappers")


def compute_event_id(source_sha256: str, record_number: int, parser_id: str, norm_version: str) -> str:
    """
    Generate a deterministic, collision-resistant event ID.
    Derived via SHA-256 of (source_sha256, record_number, parser_id, norm_version).
    """
    seed = f"{source_sha256}:{record_number}:{parser_id}:{norm_version}".encode("utf-8")
    hex_digest = hashlib.sha256(seed).hexdigest()[:24]
    return f"evt_{hex_digest}"


def clean_ip(val: Any) -> Optional[str]:
    """Validate and normalize an IP address string. Returns None if invalid or absent."""
    if not val:
        return None
    val_str = str(val).strip()
    try:
        ip_obj = ipaddress.ip_address(val_str)
        return str(ip_obj)
    except ValueError:
        return None


class BaseMapper:
    """Abstract base class for parser-specific normalization mappers."""

    parser_id: str = ""

    def map_record(
        self,
        raw_record: Dict[str, Any],
        context: Dict[str, Any],
        normalization_version: str = "1.0.0",
    ) -> Dict[str, Any]:
        """
        Transform a parsed record into a canonical NormalizedEventContract dictionary.

        Args:
            raw_record: The deserialized JSON object from parsed_records(record_json).
            context: Metadata containing source_id, filename, sha256, record_number, import_id, record_id.
            normalization_version: The version string for the normalization algorithm.

        Returns:
            Dict[str, Any] conforming to shared/contracts/event_contract.json.
        """
        raise NotImplementedError("Subclasses must implement map_record()")


class GenericJsonlMapper(BaseMapper):
    """Maps generic JSONL parsed records to the canonical schema."""

    parser_id = "generic_jsonl"

    TIMESTAMP_CANDIDATE_KEYS = (
        "timestamp",
        "time",
        "@timestamp",
        "ts",
        "datetime",
        "event_time",
        "logged_at",
    )

    USER_CANDIDATE_KEYS = (
        "user_principal",
        "username",
        "user",
        "principal",
        "user_id",
        "actor",
        "account",
    )

    IP_CANDIDATE_KEYS = (
        "source_ip",
        "src_ip",
        "client_ip",
        "ip",
        "remote_addr",
    )

    RESOURCE_CANDIDATE_KEYS = (
        "target_resource",
        "resource",
        "target",
        "uri",
        "path",
        "endpoint",
        "destination",
    )

    STATUS_CANDIDATE_KEYS = (
        "status",
        "result",
        "outcome",
        "auth_result",
    )

    def map_record(
        self,
        raw_record: Dict[str, Any],
        context: Dict[str, Any],
        normalization_version: str = "1.0.0",
    ) -> Dict[str, Any]:
        attrs = dict(raw_record.get("attributes", {}))

        # 1. Timestamp
        raw_ts = raw_record.get("timestamp")
        if not raw_ts:
            for k in self.TIMESTAMP_CANDIDATE_KEYS:
                if k in attrs and attrs[k] is not None:
                    raw_ts = attrs[k]
                    break

        utc_ts, is_naive = parse_and_normalize_timestamp(raw_ts)

        # 2. Deterministic Event ID
        event_id = compute_event_id(
            source_sha256=context["sha256"],
            record_number=context["record_number"],
            parser_id=self.parser_id,
            norm_version=normalization_version,
        )

        # 3. User Principal
        user_principal: Optional[str] = None
        for k in self.USER_CANDIDATE_KEYS:
            if k in attrs and attrs[k]:
                user_principal = str(attrs[k]).strip()
                break

        # 4. Source IP
        source_ip: Optional[str] = None
        for k in self.IP_CANDIDATE_KEYS:
            if k in attrs and attrs[k]:
                parsed_ip = clean_ip(attrs[k])
                if parsed_ip:
                    source_ip = parsed_ip
                    break

        # 5. Target Resource
        target_resource: Optional[str] = None
        for k in self.RESOURCE_CANDIDATE_KEYS:
            if k in attrs and attrs[k]:
                target_resource = str(attrs[k]).strip()
                break

        # 6. Status
        status_val = "UNKNOWN"
        for k in self.STATUS_CANDIDATE_KEYS:
            if k in attrs and attrs[k]:
                raw_st = str(attrs[k]).strip().upper()
                if raw_st in ("SUCCESS", "OK", "PASS", "ALLOWED", "200"):
                    status_val = "SUCCESS"
                elif raw_st in ("FAILURE", "FAIL", "DENIED", "BLOCKED", "REJECTED", "401", "403"):
                    status_val = "FAILURE"
                elif raw_st in ("ERROR", "ERR", "CRASH", "500"):
                    status_val = "ERROR"
                break

        # 7. Event Type
        event_type = raw_record.get("event_type") or "generic_event"

        # 8. Provenance Metadata
        if is_naive:
            attrs.setdefault("__provenance", {})["timezone_inferred"] = "UTC_ASSUMED"

        return {
            "event_id": event_id,
            "timestamp": utc_ts,
            "source_type": self.parser_id,
            "source_file": context["filename"],
            "source_line": context["record_number"],
            "source_sha256": context["sha256"],
            "event_type": event_type,
            "user_principal": user_principal,
            "source_ip": source_ip,
            "target_resource": target_resource,
            "status": status_val,
            "attributes": attrs,
            "import_id": context["import_id"],
            "record_id": context["record_id"],
            "source_id": context["source_id"],
            "record_number": context["record_number"],
            "normalization_version": normalization_version,
        }


class AuthCsvMapper(BaseMapper):
    """Maps authentication CSV parsed records to the canonical schema."""

    parser_id = "auth_csv"

    def map_record(
        self,
        raw_record: Dict[str, Any],
        context: Dict[str, Any],
        normalization_version: str = "1.0.0",
    ) -> Dict[str, Any]:
        attrs = dict(raw_record.get("attributes", {}))

        # 1. Timestamp
        raw_ts = raw_record.get("timestamp") or attrs.get("timestamp")
        utc_ts, is_naive = parse_and_normalize_timestamp(raw_ts)

        # 2. Deterministic Event ID
        event_id = compute_event_id(
            source_sha256=context["sha256"],
            record_number=context["record_number"],
            parser_id=self.parser_id,
            norm_version=normalization_version,
        )

        # 3. User Principal
        user_principal = attrs.get("username") or attrs.get("user_id") or attrs.get("user")
        if user_principal:
            user_principal = str(user_principal).strip()

        # 4. Source IP
        raw_ip = attrs.get("source_ip") or attrs.get("ip") or attrs.get("client_ip")
        source_ip = clean_ip(raw_ip)

        # 5. Target Resource
        target_resource = attrs.get("target_resource") or attrs.get("domain") or attrs.get("service")
        if target_resource:
            target_resource = str(target_resource).strip()

        # 6. Status
        auth_result = str(attrs.get("auth_result", "")).strip().upper()
        if auth_result == "SUCCESS":
            status_val = "SUCCESS"
        elif auth_result in ("FAILURE", "LOCKED"):
            status_val = "FAILURE"
        elif auth_result == "CHALLENGE":
            status_val = "UNKNOWN"
        else:
            status_val = "UNKNOWN"

        # 7. Event Type
        event_type = raw_record.get("event_type") or "user_authentication"

        # 8. Provenance metadata
        if is_naive:
            attrs.setdefault("__provenance", {})["timezone_inferred"] = "UTC_ASSUMED"

        return {
            "event_id": event_id,
            "timestamp": utc_ts,
            "source_type": self.parser_id,
            "source_file": context["filename"],
            "source_line": context["record_number"],
            "source_sha256": context["sha256"],
            "event_type": event_type,
            "user_principal": user_principal,
            "source_ip": source_ip,
            "target_resource": target_resource,
            "status": status_val,
            "attributes": attrs,
            "import_id": context["import_id"],
            "record_id": context["record_id"],
            "source_id": context["source_id"],
            "record_number": context["record_number"],
            "normalization_version": normalization_version,
        }


class WebAccessCsvMapper(BaseMapper):
    """Maps web access CSV parsed records to the canonical schema."""

    parser_id = "web_access_csv"

    def map_record(
        self,
        raw_record: Dict[str, Any],
        context: Dict[str, Any],
        normalization_version: str = "1.0.0",
    ) -> Dict[str, Any]:
        attrs = dict(raw_record.get("attributes", {}))

        # 1. Timestamp
        raw_ts = raw_record.get("timestamp") or attrs.get("timestamp")
        utc_ts, is_naive = parse_and_normalize_timestamp(raw_ts)

        # 2. Deterministic Event ID
        event_id = compute_event_id(
            source_sha256=context["sha256"],
            record_number=context["record_number"],
            parser_id=self.parser_id,
            norm_version=normalization_version,
        )

        # 3. User Principal
        user_principal = attrs.get("username") or attrs.get("user")
        if user_principal:
            user_principal = str(user_principal).strip()

        # 4. Source IP
        raw_ip = attrs.get("source_ip") or attrs.get("client_ip") or attrs.get("ip")
        source_ip = clean_ip(raw_ip)

        # 5. Target Resource
        target_resource = attrs.get("request_path") or attrs.get("path") or attrs.get("uri")
        if target_resource:
            target_resource = str(target_resource).strip()

        # 6. Status based on HTTP Status Code
        status_code_raw = attrs.get("status_code")
        status_val = "UNKNOWN"
        if status_code_raw is not None:
            try:
                code_int = int(status_code_raw)
                if 100 <= code_int < 400:
                    status_val = "SUCCESS"
                elif 400 <= code_int < 500:
                    status_val = "FAILURE"
                elif 500 <= code_int <= 599:
                    status_val = "ERROR"
            except (ValueError, TypeError):
                status_val = "UNKNOWN"

        # 7. Event Type
        event_type = raw_record.get("event_type") or "web_request"

        # 8. Provenance metadata
        if is_naive:
            attrs.setdefault("__provenance", {})["timezone_inferred"] = "UTC_ASSUMED"

        return {
            "event_id": event_id,
            "timestamp": utc_ts,
            "source_type": self.parser_id,
            "source_file": context["filename"],
            "source_line": context["record_number"],
            "source_sha256": context["sha256"],
            "event_type": event_type,
            "user_principal": user_principal,
            "source_ip": source_ip,
            "target_resource": target_resource,
            "status": status_val,
            "attributes": attrs,
            "import_id": context["import_id"],
            "record_id": context["record_id"],
            "source_id": context["source_id"],
            "record_number": context["record_number"],
            "normalization_version": normalization_version,
        }

