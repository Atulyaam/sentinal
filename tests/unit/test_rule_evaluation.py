"""Unit tests for Deterministic Detection Rule Evaluation."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from backend.detection.rules import (
    Auth001RepeatedFailuresRule,
    Auth002SuccessAfterFailuresRule,
    Web001SensitiveRouteBurstRule,
    Priv001PrivilegeChangeRule,
    Ingest001DataQualityRule,
)


def _make_event(
    event_id: str,
    event_type: str,
    timestamp: str,
    status: str = "SUCCESS",
    user_principal: str | None = None,
    source_ip: str = "192.168.1.100",
    target_resource: str | None = None,
    attributes: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "event_id": event_id,
        "import_id": "imp_test123",
        "event_type": event_type,
        "timestamp": timestamp,
        "source_ip": source_ip,
        "user_principal": user_principal,
        "target_resource": target_resource,
        "status": status,
        "raw_payload_hash": "a" * 64,
        "schema_version": "1.0.0",
        "parser_version": "1.0.0",
        "created_at": "2026-11-09T10:00:00Z",
        "attributes": attributes or {},
    }


class TestRuleEvaluation(unittest.TestCase):
    """Test deterministic evaluation logic for all 5 security rules."""

    def test_auth001_positive(self) -> None:
        """5 authentication failures within 10 minutes produce an AUTH-001 finding."""
        rule = Auth001RepeatedFailuresRule()
        base_time = datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id=f"evt_fail_{i}",
                event_type="user_authentication",
                timestamp=(base_time + timedelta(seconds=i * 60)).isoformat(),
                status="FAILURE",
                user_principal="alice",
            )
            for i in range(5)
        ]

        findings = rule.evaluate(events)
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.rule_id, "AUTH-001")
        self.assertEqual(finding.severity, "Medium")
        self.assertEqual(finding.matched_entity, "alice")
        self.assertEqual(len(finding.supporting_event_ids), 5)
        self.assertEqual(finding.matched_conditions["failure_count"], 5)
        self.assertIn("user error", finding.limitations)

    def test_auth001_below_threshold(self) -> None:
        """4 authentication failures within 10 minutes produce no finding."""
        rule = Auth001RepeatedFailuresRule()
        base_time = datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id=f"evt_fail_{i}",
                event_type="user_authentication",
                timestamp=(base_time + timedelta(seconds=i * 60)).isoformat(),
                status="FAILURE",
                user_principal="alice",
            )
            for i in range(4)
        ]

        findings = rule.evaluate(events)
        self.assertEqual(len(findings), 0)

    def test_auth001_outside_window(self) -> None:
        """5 authentication failures spanning 11 minutes produce no finding."""
        rule = Auth001RepeatedFailuresRule()
        base_time = datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone.utc)
        # 5 events spaced by 3 minutes = 12 minutes total
        events = [
            _make_event(
                event_id=f"evt_fail_{i}",
                event_type="user_authentication",
                timestamp=(base_time + timedelta(minutes=i * 3)).isoformat(),
                status="FAILURE",
                user_principal="alice",
            )
            for i in range(5)
        ]

        findings = rule.evaluate(events)
        self.assertEqual(len(findings), 0)

    def test_auth001_different_users_isolated(self) -> None:
        """Failures across distinct users do not combine to trigger a finding."""
        rule = Auth001RepeatedFailuresRule()
        base_time = datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id=f"evt_fail_alice_{i}",
                event_type="user_authentication",
                timestamp=(base_time + timedelta(seconds=i * 30)).isoformat(),
                status="FAILURE",
                user_principal="alice",
            )
            for i in range(3)
        ] + [
            _make_event(
                event_id=f"evt_fail_bob_{i}",
                event_type="user_authentication",
                timestamp=(base_time + timedelta(seconds=i * 30)).isoformat(),
                status="FAILURE",
                user_principal="bob",
            )
            for i in range(3)
        ]

        findings = rule.evaluate(events)
        self.assertEqual(len(findings), 0)

    def test_auth001_disabled(self) -> None:
        """Disabled rule returns empty findings even if conditions match."""
        rule = Auth001RepeatedFailuresRule(enabled=False)
        base_time = datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id=f"evt_fail_{i}",
                event_type="user_authentication",
                timestamp=(base_time + timedelta(seconds=i * 60)).isoformat(),
                status="FAILURE",
                user_principal="alice",
            )
            for i in range(5)
        ]

        findings = rule.evaluate(events)
        self.assertEqual(len(findings), 0)

    def test_auth002_positive(self) -> None:
        """5 failures followed by a success within 30 minutes produce an AUTH-002 finding."""
        rule = Auth002SuccessAfterFailuresRule()
        base_time = datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id=f"evt_fail_{i}",
                event_type="user_authentication",
                timestamp=(base_time + timedelta(seconds=i * 60)).isoformat(),
                status="FAILURE",
                user_principal="alice",
            )
            for i in range(5)
        ]
        # Success 5 minutes after the last failure (at minute 9)
        events.append(
            _make_event(
                event_id="evt_succ_1",
                event_type="user_authentication",
                timestamp=(base_time + timedelta(minutes=9)).isoformat(),
                status="SUCCESS",
                user_principal="alice",
            )
        )

        findings = rule.evaluate(events)
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.rule_id, "AUTH-002")
        self.assertEqual(finding.severity, "High")
        self.assertEqual(finding.matched_entity, "alice")
        self.assertEqual(len(finding.supporting_event_ids), 6)  # 5 fails + 1 success
        self.assertEqual(finding.matched_conditions["success_event_id"], "evt_succ_1")
        self.assertIn("Does not identify the human", finding.limitations)

    def test_auth002_negative_isolated_success(self) -> None:
        """A normal success without preceding failures produces no AUTH-002 finding."""
        rule = Auth002SuccessAfterFailuresRule()
        base_time = datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="evt_succ_1",
                event_type="user_authentication",
                timestamp=base_time.isoformat(),
                status="SUCCESS",
                user_principal="alice",
            )
        ]

        findings = rule.evaluate(events)
        self.assertEqual(len(findings), 0)

    def test_auth002_negative_success_after_timeout(self) -> None:
        """A success occurring 40 minutes after failures (> 30 min limit) produces no finding."""
        rule = Auth002SuccessAfterFailuresRule()
        base_time = datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id=f"evt_fail_{i}",
                event_type="user_authentication",
                timestamp=(base_time + timedelta(seconds=i * 60)).isoformat(),
                status="FAILURE",
                user_principal="alice",
            )
            for i in range(5)
        ]
        # Success 45 minutes after failures
        events.append(
            _make_event(
                event_id="evt_succ_late",
                event_type="user_authentication",
                timestamp=(base_time + timedelta(minutes=45)).isoformat(),
                status="SUCCESS",
                user_principal="alice",
            )
        )

        findings = rule.evaluate(events)
        self.assertEqual(len(findings), 0)

    def test_web001_positive(self) -> None:
        """3 requests to sensitive routes within 15 minutes trigger WEB-001."""
        rule = Web001SensitiveRouteBurstRule()
        base_time = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id=f"evt_web_{i}",
                event_type="web_request",
                timestamp=(base_time + timedelta(seconds=i * 60)).isoformat(),
                status="FAILURE",
                source_ip="203.0.113.42",
                target_resource=route,
            )
            for i, route in enumerate(["/admin/login", "/.env", "/wp-admin/setup.php"])
        ]

        findings = rule.evaluate(events)
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.rule_id, "WEB-001")
        self.assertEqual(finding.severity, "Medium")
        self.assertEqual(finding.matched_entity, "203.0.113.42")
        self.assertEqual(len(finding.supporting_event_ids), 3)

    def test_web001_benign_routes(self) -> None:
        """Requests to ordinary public routes do not trigger WEB-001."""
        rule = Web001SensitiveRouteBurstRule()
        base_time = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id=f"evt_web_{i}",
                event_type="web_request",
                timestamp=(base_time + timedelta(seconds=i * 60)).isoformat(),
                status="SUCCESS",
                source_ip="203.0.113.42",
                target_resource=route,
            )
            for i, route in enumerate(["/home", "/about", "/contact", "/products"])
        ]

        findings = rule.evaluate(events)
        self.assertEqual(len(findings), 0)

    def test_web001_percent_encoded_and_traversal(self) -> None:
        """URL percent-encoding, redundant slashes, and path traversal resolve to sensitive routes."""
        rule = Web001SensitiveRouteBurstRule()
        base_time = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="evt_enc_1",
                event_type="web_request",
                timestamp=(base_time + timedelta(seconds=10)).isoformat(),
                status="FAILURE",
                source_ip="198.51.100.5",
                target_resource="/%61%64%6d%69%6e/login",
            ),
            _make_event(
                event_id="evt_enc_2",
                event_type="web_request",
                timestamp=(base_time + timedelta(seconds=20)).isoformat(),
                status="FAILURE",
                source_ip="198.51.100.5",
                target_resource="/foo/../admin/dashboard",
            ),
            _make_event(
                event_id="evt_enc_3",
                event_type="web_request",
                timestamp=(base_time + timedelta(seconds=30)).isoformat(),
                status="FAILURE",
                source_ip="198.51.100.5",
                target_resource="//admin",
            ),
        ]
        findings = rule.evaluate(events)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].matched_entity, "198.51.100.5")
        self.assertEqual(len(findings[0].supporting_event_ids), 3)

    def test_web001_false_positive_query_and_prefix(self) -> None:
        """Query parameters containing sensitive paths or benign word prefixes do not trigger WEB-001."""
        rule = Web001SensitiveRouteBurstRule()
        base_time = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="evt_fp_1",
                event_type="web_request",
                timestamp=(base_time + timedelta(seconds=10)).isoformat(),
                status="SUCCESS",
                source_ip="198.51.100.99",
                target_resource="/search?q=/admin",
            ),
            _make_event(
                event_id="evt_fp_2",
                event_type="web_request",
                timestamp=(base_time + timedelta(seconds=20)).isoformat(),
                status="SUCCESS",
                source_ip="198.51.100.99",
                target_resource="/administrator",
            ),
            _make_event(
                event_id="evt_fp_3",
                event_type="web_request",
                timestamp=(base_time + timedelta(seconds=30)).isoformat(),
                status="SUCCESS",
                source_ip="198.51.100.99",
                target_resource="/docs/how-to-administer-system",
            ),
        ]
        findings = rule.evaluate(events)
        self.assertEqual(len(findings), 0)

    def test_web001_anonymous_missing_identity(self) -> None:
        """Requests without source_ip or user_principal cannot be attributed to a single entity burst."""
        rule = Web001SensitiveRouteBurstRule()
        base_time = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id=f"evt_anon_{i}",
                event_type="web_request",
                timestamp=(base_time + timedelta(seconds=i * 10)).isoformat(),
                status="FAILURE",
                source_ip="",
                user_principal=None,
                target_resource="/admin",
            )
            for i in range(5)
        ]
        findings = rule.evaluate(events)
        self.assertEqual(len(findings), 0)

    def test_priv001_positive(self) -> None:
        """Explicit role alteration triggers PRIV-001 finding immediately with actor and target separated."""
        rule = Priv001PrivilegeChangeRule()
        events = [
            _make_event(
                event_id="evt_priv_1",
                event_type="role_changed",
                timestamp="2026-11-09T14:30:00Z",
                status="SUCCESS",
                user_principal="secops_admin",
                attributes={"action": "grant_role", "target": "bob", "new_role": "administrator"},
            )
        ]

        findings = rule.evaluate(events)
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.rule_id, "PRIV-001")
        self.assertEqual(finding.severity, "High")
        self.assertIn("evt_priv_1", finding.supporting_event_ids)
        self.assertEqual(finding.matched_conditions["actor"], "secops_admin")
        self.assertEqual(finding.matched_conditions["target_user"], "bob")

    def test_ingest001_future_dated_event(self) -> None:
        """Events with timestamps > 24 hours into the future trigger INGEST-001."""
        rule = Ingest001DataQualityRule()
        future_time = datetime.now(timezone.utc) + timedelta(days=2)
        events = [
            _make_event(
                event_id="evt_future_1",
                event_type="user_authentication",
                timestamp=future_time.isoformat(),
                status="SUCCESS",
            )
        ]

        findings = rule.evaluate(events)
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.rule_id, "INGEST-001")
        self.assertEqual(finding.severity, "Info")
        self.assertIn("future", finding.description.lower())
        self.assertIn("Future-Dated", finding.title)

    def test_ingest001_quarantined_error(self) -> None:
        """Quarantined normalization records trigger INGEST-001 findings."""
        rule = Ingest001DataQualityRule()
        errors = [
            {
                "record_id": "rec_err_123",
                "import_id": "imp_test123",
                "source_file": "access.log",
                "error_code": "NORM_TIMEZONE_UNKNOWN",
                "error_message": "Timestamp lacks explicit timezone offset",
                "quarantined_at": "2026-11-09T10:00:00Z",
            }
        ]

        findings = rule.evaluate(events=[], errors=errors)
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.rule_id, "INGEST-001")
        self.assertEqual(finding.matched_entity, "imp_test123")
        self.assertIn("rec_err_123", finding.matched_conditions["record_ids"])


if __name__ == "__main__":
    unittest.main()
