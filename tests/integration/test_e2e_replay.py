"""End-to-end integration tests for Project Sentinel Replay Lab."""
from __future__ import annotations

import gc
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Dict, Optional
import unittest
import urllib.error
import urllib.request

from backend.api import handler
from backend.api.server import create_server
from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository


class TestE2EReplay(unittest.TestCase):
    """End-to-end verification of Replay Lab deterministic incident replay and what-if simulation."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = str(Path(cls.temp_dir.name) / "test_e2e_replay.db")
        os.environ["SENTINEL_DB_PATH"] = cls.db_path
        os.environ["SENTINEL_ALLOWED_ORIGINS"] = "http://localhost:5173"

        handler._repo = None
        handler._norm_engine = None
        handler._engine = None
        handler._detection_engine = None
        handler._correlation_engine = None
        handler._claim_engine = None
        handler._replay_engine = None

        cls.conn = get_connection(cls.db_path)
        apply_migrations(cls.conn)
        cls.repo = IngestionRepository(cls.conn)

        cls.server = create_server(host="127.0.0.1", port=0)
        cls.host, cls.port = cls.server.server_address
        cls.base_url = f"http://{cls.host}:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2.0)

        if hasattr(cls, "conn"):
            cls.conn.close()
        if hasattr(cls, "repo") and hasattr(cls.repo, "conn"):
            try:
                cls.repo.conn.close()
            except Exception:
                pass

        handler._repo = None
        handler._replay_engine = None
        gc.collect()

        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
    ) -> tuple[int, Dict[str, Any]]:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_data = resp.read().decode("utf-8")
                return resp.status, json.loads(resp_data) if resp_data else {}
        except urllib.error.HTTPError as e:
            resp_data = e.read().decode("utf-8")
            try:
                err_json = json.loads(resp_data)
            except Exception:
                err_json = {"raw": resp_data}
            return e.code, err_json

    def test_e2e_scenario_a_complete_lifecycle(self) -> None:
        """E2E Scenario A: Run authentication burst, verify timeline, findings, and claims."""
        # 1. Fetch scenario manifest
        status, manifest_resp = self._request("GET", "/api/replay/scenarios/SCN-AUTH-BURST")
        self.assertEqual(status, 200)
        manifest = manifest_resp["scenario"]
        self.assertEqual(manifest["scenario_id"], "SCN-AUTH-BURST")

        # 2. Execute Replay
        status_run, run_resp = self._request("POST", "/api/replay/run", {"scenario_id": "SCN-AUTH-BURST"})
        self.assertEqual(status_run, 200)
        run = run_resp["run"]
        self.assertEqual(run["status"], "completed")

        # 3. Assertions and Metrics
        metrics = run["metrics"]
        self.assertEqual(metrics["imported_records"], 6)
        self.assertEqual(metrics["normalized_events"], 6)
        self.assertEqual(metrics["findings_count"], 2)
        self.assertEqual(metrics["cases_count"], 1)
        self.assertEqual(metrics["assertions_failed"], 0)
        self.assertGreater(metrics["assertions_passed"], 0)

        # 4. Check Case Timeline in snapshot
        cases = run["cases_snapshot"]
        self.assertEqual(len(cases), 1)
        case = cases[0]
        self.assertEqual(case["severity"], "High")
        self.assertEqual(case["correlation_key_value"], "operator_dave")
        self.assertIn("timeline", case)
        timeline = case["timeline"]
        self.assertGreaterEqual(len(timeline), 7)  # 6 events + findings + correlation notes

        # 5. Check Claim Guard Outcomes
        claims = run["claims_snapshot"]
        claim_map = {c["claim_id"]: c["status"] for c in claims}
        self.assertEqual(claim_map["clm_scn_a_01"], "verified")
        self.assertEqual(claim_map["clm_scn_a_02"], "verified")
        self.assertEqual(claim_map["clm_scn_a_03"], "blocked")  # Unproven attacker identity
        self.assertEqual(claim_map["clm_scn_a_04"], "qualified")

    def test_e2e_scenario_b_web_probe_ip_guardrail(self) -> None:
        """E2E Scenario B: Run web probe, verify WEB-001 finding, and IP guardrail blocking."""
        status_run, run_resp = self._request("POST", "/api/replay/run", {"scenario_id": "SCN-WEB-PROBE"})
        self.assertEqual(status_run, 200)
        run = run_resp["run"]
        self.assertEqual(run["status"], "completed")

        metrics = run["metrics"]
        self.assertEqual(metrics["imported_records"], 5)
        self.assertEqual(metrics["findings_count"], 1)
        self.assertEqual(metrics["assertions_failed"], 0)

        # Verify WEB-001 finding exists
        cases = run["cases_snapshot"]
        self.assertEqual(len(cases), 1)
        finding_rules = [f["rule_id"] for f in cases[0].get("findings", [])]
        self.assertIn("WEB-001", finding_rules)

        # Verify Claim Guard blocked inferring user identity from IP alone
        claims = run["claims_snapshot"]
        claim_map = {c["claim_id"]: c["status"] for c in claims}
        self.assertEqual(claim_map["clm_scn_b_03"], "blocked")

    def test_e2e_scenario_c_priv_esc_provenance_and_fabricated_claim(self) -> None:
        """E2E Scenario C: Run priv-esc, verify PRIV-001 finding, and fabricated count block."""
        status_run, run_resp = self._request("POST", "/api/replay/run", {"scenario_id": "SCN-PRIV-ESC"})
        self.assertEqual(status_run, 200)
        run = run_resp["run"]
        self.assertEqual(run["status"], "completed")

        metrics = run["metrics"]
        self.assertEqual(metrics["imported_records"], 3)
        self.assertEqual(metrics["findings_count"], 1)
        self.assertEqual(metrics["assertions_failed"], 0)

        # Verify PRIV-001 finding
        cases = run["cases_snapshot"]
        self.assertEqual(len(cases), 1)
        finding_rules = [f["rule_id"] for f in cases[0].get("findings", [])]
        self.assertIn("PRIV-001", finding_rules)

        # Verify Claim Guard blocked hallucinated event count (50 claimed vs 1 actual)
        claims = run["claims_snapshot"]
        claim_map = {c["claim_id"]: c["status"] for c in claims}
        self.assertEqual(claim_map["clm_scn_c_03"], "blocked")

    def test_e2e_what_if_and_compare(self) -> None:
        """E2E What-If simulation and side-by-side run comparison."""
        # 1. Run baseline
        _, baseline_resp = self._request("POST", "/api/replay/run", {"scenario_id": "SCN-AUTH-BURST"})
        baseline_id = baseline_resp["run"]["replay_id"]

        # 2. Run What-If with higher threshold
        _, whatif_resp = self._request(
            "POST",
            "/api/replay/run",
            {
                "scenario_id": "SCN-AUTH-BURST",
                "what_if": {
                    "what_if_id": "WIF-THRESHOLD-10",
                    "description": "Increase failure threshold to 10",
                    "rule_overrides": {"AUTH-001": {"threshold_count": 10}},
                },
            },
        )
        whatif_id = whatif_resp["run"]["replay_id"]

        # 3. Compare baseline vs what-if
        status_cmp, cmp_resp = self._request(
            "POST",
            "/api/replay/compare",
            {"run_a_id": baseline_id, "run_b_id": whatif_id},
        )
        self.assertEqual(status_cmp, 200)
        cmp = cmp_resp["comparison"]
        self.assertFalse(cmp["is_identical"])
        self.assertIn("AUTH-001", cmp["findings_removed"])
        self.assertEqual(cmp["metric_deltas"]["findings_count"], -1)

    def test_e2e_z_isolation_verification(self) -> None:
        """Verify replay pipeline operated in memory without writing records to host repository."""
        # Host normalized_events table must have 0 events
        events, total_events = self.repo.list_normalized_events(limit=100)
        self.assertEqual(len(events), 0, "Replay leaked events into host repository!")
        self.assertEqual(total_events, 0)

        # Host findings table must have 0 findings
        findings, total_findings = self.repo.list_findings(limit=100)
        self.assertEqual(len(findings), 0, "Replay leaked findings into host repository!")
        self.assertEqual(total_findings, 0)

        # Host cases table must have 0 cases
        cases, total_cases = self.repo.list_cases(limit=100)
        self.assertEqual(len(cases), 0, "Replay leaked cases into host repository!")
        self.assertEqual(total_cases, 0)

        # Only replay run audit reports are in the host replay_runs table
        runs, total_runs = self.repo.list_replay_runs(limit=100)
        self.assertGreater(total_runs, 0)


if __name__ == "__main__":
    unittest.main()
