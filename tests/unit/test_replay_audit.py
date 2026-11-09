"""Independent Technical and Security Audit Test Suite for Phase 7 (Replay Lab).

Verifies:
1. Real pipeline service reuse (no mock ingestion, normalization, detection, correlation, or claims).
2. Host database zero contamination and complete ephemeral isolation.
3. 3x execution determinism across all scenarios with 0 metric deltas.
4. Scenario A correctness and Claim Guard unproven attacker attribution block.
5. Scenario B correctness and IP Guardrail identity attribution block.
6. Scenario C correctness and fabricated claim count block.
7. What-If isolation and global rule registry immutability.
8. What-If input validation against malformed overrides and unknown rules.
9. Fixture SHA-256 integrity check and directory path traversal guards.
10. Run comparison compatibility detection and warning semantics.
11. Replay reset safety preserving core operational tables.
12. Graceful pipeline error handling and isolated resource cleanup.
"""
from __future__ import annotations

import copy
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from backend.detection.rules import RuleRegistry
from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository
from backend.replay.engine import ReplayEngine
from backend.replay.models import ScenarioFixture, ScenarioManifest, WhatIfConfig
from backend.replay.scenarios import (
    SCENARIO_CATALOG,
    get_fixture_path,
    get_scenario_manifest,
)


class TestReplayAudit(unittest.TestCase):
    """Independent audit test suite verifying Replay Lab guarantees."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "sentinel_host_audit.db")
        self.conn = get_connection(self.db_path)
        apply_migrations(self.conn)
        self.host_repo = IngestionRepository(self.conn)
        self.engine = ReplayEngine(main_repo=self.host_repo)

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1. Pipeline Reuse Audit
    # -------------------------------------------------------------------------
    def test_real_pipeline_reuse(self) -> None:
        """Verify that ReplayEngine invokes the actual production pipeline components."""
        report = self.engine.run_scenario("SCN-AUTH-BURST")

        # Must execute all 7 production stages in strict sequence
        expected_stages = [
            "stage_ingest",
            "stage_normalization",
            "stage_detection",
            "stage_correlation",
            "stage_timeline",
            "stage_claim_guard",
            "stage_assertions",
        ]
        actual_stages = [s.stage_id for s in report.stages]
        self.assertEqual(actual_stages, expected_stages)

        # Verify real versions are embedded and match production modules
        self.assertIn("normalization", report.pipeline_versions)
        self.assertIn("correlation", report.pipeline_versions)
        self.assertIn("claim_guard", report.pipeline_versions)
        self.assertEqual(report.pipeline_versions["claim_guard"], "1.0.0")

        # Verify actual cases and timeline entries are populated
        self.assertGreater(len(report.cases_snapshot), 0)
        c0 = report.cases_snapshot[0]
        self.assertTrue(c0["case_id"].startswith("case_"))
        self.assertGreater(len(c0["findings"]), 0)
        self.assertGreater(len(c0["timeline"]), 0)

    # -------------------------------------------------------------------------
    # 2. Host Database Isolation & Zero Contamination
    # -------------------------------------------------------------------------
    def test_host_database_zero_contamination(self) -> None:
        """Verify that executing all scenarios produces ZERO rows in host core tables."""
        # Seed an operational source in the host database to verify it remains untouched
        self.host_repo.get_or_create_source(
            source_id="src_host_operational",
            source_name="Host Operational Logs",
            parser_profile="auth_csv",
            configured_path="host.log",
        )

        cur = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('sqlite_sequence', 'schema_migrations', 'replay_runs');"
        )
        core_tables = [row[0] for row in cur.fetchall()]

        def get_core_counts():
            counts = {}
            for t in core_tables:
                c = self.conn.execute(f"SELECT COUNT(*) FROM {t};")
                counts[t] = c.fetchone()[0]
            return counts

        pre_counts = get_core_counts()

        # Run all three scenarios
        for scn_id in ["SCN-AUTH-BURST", "SCN-WEB-PROBE", "SCN-PRIV-ESC"]:
            r = self.engine.run_scenario(scn_id)
            self.assertEqual(r.status, "completed")

        post_counts = get_core_counts()

        # Every core operational table must have exactly 0 change
        for t in core_tables:
            self.assertEqual(
                post_counts[t],
                pre_counts[t],
                f"Contamination detected in host table '{t}': pre={pre_counts[t]}, post={post_counts[t]}",
            )

        # Host event_sources table should have exactly the pre-existing sources
        cur = self.conn.execute("SELECT COUNT(*) FROM event_sources;")
        self.assertEqual(cur.fetchone()[0], pre_counts["event_sources"])

        # Only replay_runs in host DB should have recorded the 3 runs
        cur = self.conn.execute("SELECT COUNT(*) FROM replay_runs;")
        self.assertEqual(cur.fetchone()[0], 3)

    # -------------------------------------------------------------------------
    # 3. Determinism Repeatability (3x Run Equivalence)
    # -------------------------------------------------------------------------
    def test_triple_run_determinism(self) -> None:
        """Verify identical metric, finding, and assertion outputs across 3 consecutive runs."""
        for scn_id in ["SCN-AUTH-BURST", "SCN-WEB-PROBE", "SCN-PRIV-ESC"]:
            run1 = self.engine.run_scenario(scn_id)
            run2 = self.engine.run_scenario(scn_id)
            run3 = self.engine.run_scenario(scn_id)

            comp12 = self.engine.compare_runs(run1, run2)
            comp23 = self.engine.compare_runs(run2, run3)

            self.assertTrue(comp12["is_identical"])
            self.assertTrue(comp23["is_identical"])
            self.assertTrue(comp12["is_compatible"])
            self.assertIsNone(comp12["compatibility_warning"])

            for k, delta in comp12["metric_deltas"].items():
                self.assertEqual(delta, 0, f"Scenario {scn_id} metric delta {k} != 0 in run1 vs run2")

            for k, delta in comp23["metric_deltas"].items():
                self.assertEqual(delta, 0, f"Scenario {scn_id} metric delta {k} != 0 in run2 vs run3")

            self.assertEqual(len(comp12["assertion_mismatches"]), 0)
            self.assertEqual(len(comp23["assertion_mismatches"]), 0)

    # -------------------------------------------------------------------------
    # 4. Scenario A Correctness & Attacker Attribution Block
    # -------------------------------------------------------------------------
    def test_scenario_a_correctness_and_claim_guard_attribution_block(self) -> None:
        """Scenario A evaluates AUTH-001 & AUTH-002, and blocks unproven attacker attribution."""
        report = self.engine.run_scenario("SCN-AUTH-BURST")

        self.assertEqual(report.status, "completed")
        self.assertEqual(report.metrics.imported_records, 6)
        self.assertEqual(report.metrics.findings_count, 2)
        self.assertEqual(report.metrics.cases_count, 1)

        case = report.cases_snapshot[0]
        self.assertEqual(case["correlation_key_type"], "user_principal")
        self.assertEqual(case["correlation_key_value"], "operator_dave")
        self.assertEqual(case["severity"], "High")

        claims = {c["claim_id"]: c for c in report.claims_snapshot}
        # clm_scn_a_01: Observed failure count (5) -> verified
        self.assertEqual(claims["clm_scn_a_01"]["status"], "verified")
        # clm_scn_a_02: Finding exists AUTH-002 -> verified
        self.assertEqual(claims["clm_scn_a_02"]["status"], "verified")
        # clm_scn_a_03: Attacker attribution (attacker_eve) -> BLOCKED
        self.assertEqual(claims["clm_scn_a_03"]["status"], "blocked")
        self.assertTrue(any("attacker_eve" in r or "not present" in r for r in claims["clm_scn_a_03"]["blocked_reasons"]))
        # clm_scn_a_04: Correlation relationship -> qualified
        self.assertEqual(claims["clm_scn_a_04"]["status"], "qualified")

    # -------------------------------------------------------------------------
    # 5. Scenario B Correctness & IP Guardrail Block
    # -------------------------------------------------------------------------
    def test_scenario_b_correctness_and_ip_guardrail_block(self) -> None:
        """Scenario B evaluates WEB-001 and enforces the IP Guardrail against identity claims."""
        report = self.engine.run_scenario("SCN-WEB-PROBE")

        self.assertEqual(report.status, "completed")
        self.assertEqual(report.metrics.imported_records, 5)
        self.assertEqual(report.metrics.findings_count, 1)

        claims = {c["claim_id"]: c for c in report.claims_snapshot}
        # clm_scn_b_01: Finding exists WEB-001 -> verified
        self.assertEqual(claims["clm_scn_b_01"]["status"], "verified")
        # clm_scn_b_02: Source IP observed -> verified
        self.assertEqual(claims["clm_scn_b_02"]["status"], "verified")
        # clm_scn_b_03: User entity inferred from source IP -> BLOCKED by IP Guardrail
        self.assertEqual(claims["clm_scn_b_03"]["status"], "blocked")
        self.assertTrue(any("suspect_ip_user" in r or "not present" in r for r in claims["clm_scn_b_03"]["blocked_reasons"]))

    # -------------------------------------------------------------------------
    # 6. Scenario C Correctness & Fabricated Claim Block
    # -------------------------------------------------------------------------
    def test_scenario_c_correctness_and_fabricated_claim_block(self) -> None:
        """Scenario C evaluates PRIV-001 and blocks fabricated event count claims."""
        report = self.engine.run_scenario("SCN-PRIV-ESC")

        self.assertEqual(report.status, "completed")
        self.assertEqual(report.metrics.findings_count, 1)

        case = report.cases_snapshot[0]
        self.assertEqual(case["severity"], "High")

        claims = {c["claim_id"]: c for c in report.claims_snapshot}
        # clm_scn_c_01: Finding exists PRIV-001 -> verified
        self.assertEqual(claims["clm_scn_c_01"]["status"], "verified")
        # clm_scn_c_02: Observed user analyst_bob -> verified
        self.assertEqual(claims["clm_scn_c_02"]["status"], "verified")
        # clm_scn_c_03: Fabricated 50 role change count -> BLOCKED
        self.assertEqual(claims["clm_scn_c_03"]["status"], "blocked")
        self.assertTrue(any("50" in r or "does not match verified count" in r for r in claims["clm_scn_c_03"]["blocked_reasons"]))
        # clm_scn_c_04: Inferred time window -> qualified
        self.assertEqual(claims["clm_scn_c_04"]["status"], "qualified")

    # -------------------------------------------------------------------------
    # 7. What-If Isolation & Global Immutability
    # -------------------------------------------------------------------------
    def test_what_if_global_immutability(self) -> None:
        """Verify that What-If simulation parameters do NOT mutate default RuleRegistry."""
        base_registry = RuleRegistry()
        auth_001_default = base_registry.get("AUTH-001")
        self.assertIsNotNone(auth_001_default)
        default_threshold = auth_001_default.config.get("threshold_count", 5)
        default_enabled = auth_001_default.enabled

        # Execute What-If mutating threshold to 99 and disabling rule
        what_if = WhatIfConfig(
            rule_overrides={"AUTH-001": {"threshold_count": 99, "enabled": False}}
        )
        report = self.engine.run_scenario("SCN-AUTH-BURST", what_if=what_if)
        self.assertEqual(report.mode, "what_if")

        # Verify global RuleRegistry remains untouched
        fresh_registry = RuleRegistry()
        auth_001_fresh = fresh_registry.get("AUTH-001")
        self.assertEqual(auth_001_fresh.config.get("threshold_count"), default_threshold)
        self.assertEqual(auth_001_fresh.enabled, default_enabled)

    # -------------------------------------------------------------------------
    # 8. What-If Input Validation
    # -------------------------------------------------------------------------
    def test_what_if_input_validation(self) -> None:
        """Verify strict rejection of unknown rules and malformed simulation parameters."""
        # 1. Unknown rule ID
        with self.assertRaises(ValueError) as cm:
            self.engine.run_scenario(
                "SCN-AUTH-BURST",
                what_if=WhatIfConfig(rule_overrides={"INVALID-999": {"threshold_count": 10}}),
            )
        self.assertIn("Unknown rule ID in what_if overrides", str(cm.exception))

        # 2. Negative threshold
        with self.assertRaises(ValueError) as cm:
            self.engine.run_scenario(
                "SCN-AUTH-BURST",
                what_if=WhatIfConfig(rule_overrides={"AUTH-001": {"threshold_count": -5}}),
            )
        self.assertIn("Invalid threshold_count", str(cm.exception))

        # 3. Non-integer threshold
        with self.assertRaises(ValueError) as cm:
            self.engine.run_scenario(
                "SCN-AUTH-BURST",
                what_if=WhatIfConfig(rule_overrides={"AUTH-001": {"threshold_count": "five"}}),  # type: ignore
            )
        self.assertIn("Invalid threshold_count", str(cm.exception))

        # 4. Invalid line index in excluded_records
        with self.assertRaises(ValueError) as cm:
            self.engine.run_scenario(
                "SCN-AUTH-BURST",
                what_if=WhatIfConfig(excluded_records=[0, 1]),
            )
        self.assertIn("Invalid excluded line index", str(cm.exception))

        # 5. Invalid correlation window_seconds
        with self.assertRaises(ValueError) as cm:
            self.engine.run_scenario(
                "SCN-AUTH-BURST",
                what_if=WhatIfConfig(correlation_overrides={"window_seconds": -100}),
            )
        self.assertIn("Invalid correlation window_seconds", str(cm.exception))

    # -------------------------------------------------------------------------
    # 9. Fixture Integrity & Path Traversal Guards
    # -------------------------------------------------------------------------
    def test_fixture_integrity_and_path_traversal_guards(self) -> None:
        """Verify SHA-256 fixture integrity validation and directory traversal prevention."""
        # Directory traversal attempt
        with self.assertRaises(ValueError) as cm:
            get_fixture_path("../../etc/passwd")
        self.assertIn("Path traversal detected", str(cm.exception))

        # Non-existent fixture file
        with self.assertRaises(FileNotFoundError):
            get_fixture_path("phantom_scenario.jsonl")

        # Checksum tampering detection
        tampered_manifest = copy.deepcopy(get_scenario_manifest("SCN-AUTH-BURST"))
        tampered_manifest.fixtures[0].sha256 = "0000000000000000000000000000000000000000000000000000000000000000"

        with patch("backend.replay.engine.get_scenario_manifest", return_value=tampered_manifest):
            with self.assertRaises(ValueError) as cm:
                self.engine.run_scenario("SCN-AUTH-BURST")
            self.assertIn("Integrity check failed for fixture", str(cm.exception))

    # -------------------------------------------------------------------------
    # 10. Run Comparison Compatibility
    # -------------------------------------------------------------------------
    def test_run_comparison_compatibility(self) -> None:
        """Verify cross-scenario comparison returns is_compatible=False with descriptive warning."""
        run_a = self.engine.run_scenario("SCN-AUTH-BURST")
        run_b = self.engine.run_scenario("SCN-WEB-PROBE")

        comp = self.engine.compare_runs(run_a, run_b)
        self.assertFalse(comp["is_compatible"])
        self.assertFalse(comp["is_identical"])
        self.assertIsNotNone(comp["compatibility_warning"])
        self.assertIn("Scenario mismatch", comp["compatibility_warning"])

        # Intra-scenario comparison is compatible
        run_a2 = self.engine.run_scenario("SCN-AUTH-BURST")
        comp_same = self.engine.compare_runs(run_a, run_a2)
        self.assertTrue(comp_same["is_compatible"])
        self.assertTrue(comp_same["is_identical"])
        self.assertIsNone(comp_same["compatibility_warning"])

    # -------------------------------------------------------------------------
    # 11. Replay Reset Safety
    # -------------------------------------------------------------------------
    def test_replay_reset_safety(self) -> None:
        """Verify that clearing replay_runs leaves all operational tables completely untouched."""
        self.host_repo.get_or_create_source(
            source_id="src_active",
            source_name="Active Source",
            parser_profile="auth_csv",
            configured_path="test.log",
        )
        self.engine.run_scenario("SCN-AUTH-BURST")

        # Verify 1 replay run recorded
        runs, count = self.host_repo.list_replay_runs()
        self.assertEqual(count, 1)

        # Clear replay runs
        self.conn.execute("DELETE FROM replay_runs;")

        runs_after, count_after = self.host_repo.list_replay_runs()
        self.assertEqual(count_after, 0)

        # Operational source is untouched
        src = self.host_repo.get_source("src_active")
        self.assertIsNotNone(src)
        self.assertEqual(src["source_name"], "Active Source")

    # -------------------------------------------------------------------------
    # 12. Pipeline Error Graceful Recovery
    # -------------------------------------------------------------------------
    def test_pipeline_error_recovery(self) -> None:
        """Verify that pipeline execution errors produce an inspectable failed report."""
        with patch.object(ReplayEngine, "_evaluate_assertions", side_effect=RuntimeError("Simulated pipeline assertion crash")):
            report = self.engine.run_scenario("SCN-AUTH-BURST")

            self.assertEqual(report.status, "failed")
            self.assertIsNotNone(report.error_summary)
            self.assertIn("Simulated pipeline assertion crash", report.error_summary)
            error_stages = [s for s in report.stages if s.stage_id == "stage_error"]
            self.assertEqual(len(error_stages), 1)
            self.assertEqual(error_stages[0].status, "failed")


if __name__ == "__main__":
    unittest.main()
