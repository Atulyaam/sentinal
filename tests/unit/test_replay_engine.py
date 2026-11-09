"""Unit tests for Replay Lab Deterministic Replay Engine."""
from __future__ import annotations

import os
import tempfile
import unittest

from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository
from backend.replay.engine import ReplayEngine
from backend.replay.models import WhatIfConfig


class TestReplayEngine(unittest.TestCase):
    """Test suite for ReplayEngine execution, assertions, what-if simulations, and repeatability."""

    def setUp(self) -> None:
        self.engine = ReplayEngine()

    def test_run_scenario_a_auth_burst(self) -> None:
        """Scenario A (SCN-AUTH-BURST) executes end-to-end and passes 100% of assertions."""
        report = self.engine.run_scenario("SCN-AUTH-BURST")

        self.assertEqual(report.status, "completed")
        self.assertEqual(report.scenario_id, "SCN-AUTH-BURST")
        self.assertEqual(report.mode, "standard")
        self.assertGreater(len(report.stages), 0)

        # Check metrics
        self.assertEqual(report.metrics.imported_records, 6)
        self.assertEqual(report.metrics.normalized_events, 6)
        self.assertEqual(report.metrics.findings_count, 2)
        self.assertEqual(report.metrics.cases_count, 1)

        # Check assertions
        self.assertGreater(len(report.assertion_results), 0)
        failed_assertions = [a for a in report.assertion_results if not a.passed]
        self.assertEqual(
            len(failed_assertions),
            0,
            f"Failed assertions in Scenario A: {[a.description + ': ' + a.message for a in failed_assertions]}",
        )

        # Verify claim verifications present in claims_snapshot
        self.assertEqual(len(report.claims_snapshot), 4)
        ver_map = {cv["claim_id"]: cv["status"] for cv in report.claims_snapshot}
        self.assertEqual(ver_map["clm_scn_a_01"], "verified")
        self.assertEqual(ver_map["clm_scn_a_02"], "verified")
        self.assertEqual(ver_map["clm_scn_a_03"], "blocked")
        self.assertEqual(ver_map["clm_scn_a_04"], "qualified")

    def test_run_scenario_b_web_probe(self) -> None:
        """Scenario B (SCN-WEB-PROBE) executes end-to-end and passes 100% of assertions."""
        report = self.engine.run_scenario("SCN-WEB-PROBE")

        self.assertEqual(report.status, "completed")
        self.assertEqual(report.scenario_id, "SCN-WEB-PROBE")
        self.assertEqual(report.metrics.imported_records, 5)
        self.assertEqual(report.metrics.normalized_events, 5)
        self.assertEqual(report.metrics.findings_count, 1)
        self.assertEqual(report.metrics.cases_count, 1)

        failed_assertions = [a for a in report.assertion_results if not a.passed]
        self.assertEqual(len(failed_assertions), 0, f"Failed assertions in Scenario B: {failed_assertions}")

    def test_run_scenario_c_priv_esc(self) -> None:
        """Scenario C (SCN-PRIV-ESC) executes end-to-end and passes 100% of assertions."""
        report = self.engine.run_scenario("SCN-PRIV-ESC")

        self.assertEqual(report.status, "completed")
        self.assertEqual(report.scenario_id, "SCN-PRIV-ESC")
        self.assertEqual(report.metrics.imported_records, 3)
        self.assertEqual(report.metrics.normalized_events, 3)
        self.assertEqual(report.metrics.findings_count, 1)
        self.assertEqual(report.metrics.cases_count, 1)

        failed_assertions = [a for a in report.assertion_results if not a.passed]
        self.assertEqual(len(failed_assertions), 0, f"Failed assertions in Scenario C: {failed_assertions}")

    def test_repeatability_and_comparison(self) -> None:
        """Replay runs of the same scenario produce identical findings, cases, and claims."""
        run1 = self.engine.run_scenario("SCN-AUTH-BURST")
        run2 = self.engine.run_scenario("SCN-AUTH-BURST")

        comparison = self.engine.compare_runs(run1, run2)
        self.assertTrue(comparison["is_identical"])
        self.assertEqual(len(comparison["findings_added"]), 0)
        self.assertEqual(len(comparison["findings_removed"]), 0)
        self.assertEqual(comparison["cases_added"], 0)
        self.assertEqual(comparison["cases_removed"], 0)
        for delta in comparison["metric_deltas"].values():
            self.assertEqual(delta, 0)

    def test_what_if_simulation_removes_finding(self) -> None:
        """What-If scenario with elevated threshold removes the brute-force finding as expected."""
        what_if_config = WhatIfConfig(
            what_if_id="WIF-HIGH-THRESHOLD",
            name="Threshold 10",
            description="Raise failure threshold to 10",
            rule_overrides={"AUTH-001": {"threshold_count": 10}},
        )

        res = self.engine.run_what_if("SCN-AUTH-BURST", what_if_config)
        diff = res["comparison"]
        simulated_report = res["simulated_run"]

        self.assertFalse(diff["is_identical"])
        self.assertEqual(diff["metric_deltas"]["findings_count"], -1)
        self.assertIn("AUTH-001", diff["findings_removed"])
        self.assertEqual(simulated_report.metrics.findings_count, 1)

    def test_data_isolation(self) -> None:
        """Replay runs operate in memory and do not write events or findings to the host repository."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            db_path = tf.name

        try:
            conn = get_connection(db_path)
            apply_migrations(conn)
            host_repo = IngestionRepository(conn)

            events_before = len(host_repo.list_normalized_events(limit=100))
            findings_before = len(host_repo.list_findings(limit=100))

            # Run all 3 scenarios via ReplayEngine
            self.engine.run_scenario("SCN-AUTH-BURST")
            self.engine.run_scenario("SCN-WEB-PROBE")
            self.engine.run_scenario("SCN-PRIV-ESC")

            events_after = len(host_repo.list_normalized_events(limit=100))
            findings_after = len(host_repo.list_findings(limit=100))

            self.assertEqual(events_before, events_after, "Replay leaked events into host database")
            self.assertEqual(findings_before, findings_after, "Replay leaked findings into host database")
            conn.close()
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_run_unknown_scenario_raises_error(self) -> None:
        """Running an unregistered scenario raises KeyError."""
        with self.assertRaises(KeyError):
            self.engine.run_scenario("SCN-UNKNOWN")


if __name__ == "__main__":
    unittest.main()
