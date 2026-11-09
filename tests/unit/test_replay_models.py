"""Unit tests for Replay Lab data models and contract schemas."""

import unittest

from backend.replay.models import (
    ScenarioFixture,
    ScenarioExpectations,
    ScenarioManifest,
    ReplayAssertion,
    ReplayStage,
    ReplayMetrics,
    WhatIfConfig,
    ReplayRunReport,
)


class TestReplayModels(unittest.TestCase):
    """Test suite for serialization, validation, and contract integrity of Replay Lab models."""

    def test_scenario_fixture_serialization(self) -> None:
        """ScenarioFixture cleanly serializes and deserializes."""
        fix = ScenarioFixture(
            filename="test_fixture.csv",
            parser_id="auth_csv",
            sha256="a" * 64,
            size_bytes=1024,
            description="Test fixture file",
        )
        data = fix.to_dict()
        self.assertEqual(data["filename"], "test_fixture.csv")
        self.assertEqual(data["parser_id"], "auth_csv")
        self.assertEqual(data["size_bytes"], 1024)

        restored = ScenarioFixture.from_dict(data)
        self.assertEqual(restored.filename, fix.filename)
        self.assertEqual(restored.sha256, fix.sha256)

    def test_scenario_expectations_serialization(self) -> None:
        """ScenarioExpectations accurately models committed expectations."""
        exp = ScenarioExpectations(
            expected_imported_records=10,
            expected_normalized_events=10,
            expected_rules=["AUTH-001", "AUTH-002"],
            expected_findings_count=2,
            expected_cases_count=1,
            expected_claim_outcomes={"clm_01": "verified", "clm_02": "blocked"},
            expected_timeline_types=["event", "finding"],
        )
        data = exp.to_dict()
        self.assertEqual(data["expected_imported_records"], 10)
        self.assertEqual(data["expected_findings_count"], 2)

        restored = ScenarioExpectations.from_dict(data)
        self.assertEqual(restored.expected_rules, ["AUTH-001", "AUTH-002"])
        self.assertEqual(restored.expected_claim_outcomes["clm_01"], "verified")

    def test_replay_assertion_serialization(self) -> None:
        """ReplayAssertion tracks individual test comparisons."""
        assertion = ReplayAssertion(
            assertion_id="asrt_001",
            category="detection",
            description="Rule AUTH-001 must trigger",
            expected=1,
            actual=1,
            passed=True,
            message="1 finding generated.",
        )
        d = assertion.to_dict()
        self.assertTrue(d["passed"])
        self.assertEqual(d["category"], "detection")

    def test_replay_run_report_serialization(self) -> None:
        """ReplayRunReport captures complete execution state."""
        metrics = ReplayMetrics(
            imported_records=5,
            normalized_events=5,
            findings_count=1,
            cases_count=1,
            duration_ms=45.2,
        )
        stage = ReplayStage(
            stage_id="stage_ingest",
            name="Ingestion",
            status="completed",
            duration_ms=12.1,
            summary="Accepted 5 records",
        )
        report = ReplayRunReport(
            replay_id="rply_test_001",
            scenario_id="SCN-AUTH-BURST",
            scenario_name="Auth Burst",
            scenario_version="1.0.0",
            status="completed",
            mode="standard",
            pipeline_versions={"engine": "1.0.0"},
            fixture_checksums={"test.csv": "hash"},
            what_if_config={},
            metrics=metrics,
            assertion_results=[],
            stages=[stage],
        )
        d = report.to_dict()
        self.assertEqual(d["replay_id"], "rply_test_001")
        self.assertEqual(d["metrics"]["imported_records"], 5)
        self.assertEqual(len(d["stages"]), 1)


if __name__ == "__main__":
    unittest.main()

