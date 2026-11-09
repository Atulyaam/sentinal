"""Unit tests for Replay Lab scenario catalog, fixtures, and manifests."""
from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

from backend.replay.scenarios import (
    FIXTURES_DIR,
    SCENARIO_A,
    SCENARIO_B,
    SCENARIO_C,
    get_scenario,
    list_scenarios,
)


class TestReplayScenarios(unittest.TestCase):
    """Test suite for Replay Lab scenario manifests, catalog lookups, and fixture integrity."""

    def test_list_scenarios(self) -> None:
        """Scenario catalog lists all 3 official scenarios."""
        scenarios = list_scenarios()
        self.assertEqual(len(scenarios), 3)
        ids = [s.scenario_id for s in scenarios]
        self.assertIn("SCN-AUTH-BURST", ids)
        self.assertIn("SCN-WEB-PROBE", ids)
        self.assertIn("SCN-PRIV-ESC", ids)

    def test_get_scenario_success(self) -> None:
        """Retrieves individual scenario manifests by ID."""
        scn_a = get_scenario("SCN-AUTH-BURST")
        self.assertEqual(scn_a.scenario_id, "SCN-AUTH-BURST")
        self.assertEqual(scn_a.name, SCENARIO_A.name)

        scn_b = get_scenario("SCN-WEB-PROBE")
        self.assertEqual(scn_b.scenario_id, "SCN-WEB-PROBE")
        self.assertEqual(scn_b.name, SCENARIO_B.name)

        scn_c = get_scenario("SCN-PRIV-ESC")
        self.assertEqual(scn_c.scenario_id, "SCN-PRIV-ESC")
        self.assertEqual(scn_c.name, SCENARIO_C.name)

    def test_get_scenario_not_found(self) -> None:
        """Unknown scenario IDs raise KeyError."""
        with self.assertRaises(KeyError):
            get_scenario("SCN-DOES-NOT-EXIST")

    def test_fixture_integrity_on_disk(self) -> None:
        """Every fixture file exists on disk with matching SHA-256 and size."""
        scenarios = list_scenarios()
        for scn in scenarios:
            for fixture in scn.fixtures:
                file_path = FIXTURES_DIR / fixture.filename
                self.assertTrue(file_path.exists(), f"Fixture {fixture.filename} does not exist at {file_path}")

                actual_bytes = file_path.read_bytes()
                actual_sha256 = hashlib.sha256(actual_bytes).hexdigest()
                actual_size = len(actual_bytes)

                self.assertEqual(
                    actual_sha256,
                    fixture.sha256,
                    f"SHA-256 mismatch for {fixture.filename}: expected {fixture.sha256}, got {actual_sha256}",
                )
                self.assertEqual(
                    actual_size,
                    fixture.size_bytes,
                    f"Size mismatch for {fixture.filename}: expected {fixture.size_bytes}, got {actual_size}",
                )

    def test_scenario_manifest_structure(self) -> None:
        """Every scenario manifest defines complete learning objectives, claims, and what-ifs."""
        scenarios = list_scenarios()
        for scn in scenarios:
            self.assertTrue(scn.scenario_id.startswith("SCN-"))
            self.assertTrue(len(scn.name) > 5)
            self.assertTrue(len(scn.description) > 10)
            self.assertTrue(len(scn.story) > 20)
            self.assertTrue(len(scn.learning_objective) > 15)
            self.assertGreater(len(scn.fixtures), 0)
            self.assertGreater(len(scn.claim_proposals), 0)
            self.assertGreater(len(scn.supported_what_ifs), 0)

            # Check expectations
            exp = scn.expectations
            self.assertGreater(exp.expected_imported_records, 0)
            self.assertGreater(exp.expected_normalized_events, 0)
            self.assertGreater(len(exp.expected_rules), 0)
            self.assertGreater(exp.expected_findings_count, 0)
            self.assertGreater(exp.expected_cases_count, 0)
            self.assertGreater(len(exp.expected_claim_outcomes), 0)

    def test_manifest_dict_roundtrip(self) -> None:
        """ScenarioManifest cleanly serializes to dict and deserializes."""
        for scn in [SCENARIO_A, SCENARIO_B, SCENARIO_C]:
            d = scn.to_dict()
            self.assertIn("scenario_id", d)
            self.assertIn("fixtures", d)
            self.assertIn("expectations", d)
            self.assertIn("supported_what_ifs", d)

            from backend.replay.models import ScenarioManifest
            restored = ScenarioManifest.from_dict(d)
            self.assertEqual(restored.scenario_id, scn.scenario_id)
            self.assertEqual(len(restored.fixtures), len(scn.fixtures))
            self.assertEqual(restored.expectations.expected_rules, scn.expectations.expected_rules)


if __name__ == "__main__":
    unittest.main()

