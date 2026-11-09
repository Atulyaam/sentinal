"""Real end-to-end verification script for Replay Lab: Deterministic Incident Replay & What-If Simulation."""
from __future__ import annotations

import gc
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def wait_for_api(api_url: str, timeout: float = 10.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(f"{api_url}/health")
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.1)
    return False


def request_json(api_url: str, method: str, endpoint: str, body: dict | None = None) -> tuple[int, dict]:
    url = f"{api_url}{endpoint}"
    data_bytes = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8")
        return err.code, json.loads(raw) if raw else {}


def main() -> None:
    print("=" * 75)
    print(" PROJECT SENTINEL — Phase 7 Replay Lab & What-If Verification")
    print(" 'Every replay executes the real pipeline. No mocked results.'")
    print("=" * 75)

    temp_dir = tempfile.TemporaryDirectory()
    db_path = Path(temp_dir.name) / "sentinel_replay_lab_verify.db"
    port = find_free_port()
    api_url = f"http://127.0.0.1:{port}"

    server_env = {
        **os.environ,
        "SENTINEL_DB_PATH": str(db_path),
        "SENTINEL_PORT": str(port),
        "SENTINEL_ALLOWED_ORIGINS": "http://localhost:5173",
        "PYTHONUNBUFFERED": "1",
    }

    server_log_path = Path(temp_dir.name) / "server.log"
    server_log = open(server_log_path, "w", encoding="utf-8")

    print(f"\n[1/10] Starting Sentinel API server on port {port}...")
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "backend.api.server", "--port", str(port)],
        env=server_env,
        stdout=server_log,
        stderr=subprocess.STDOUT,
        cwd=str(ROOT_DIR),
        text=True,
    )

    try:
        if not wait_for_api(api_url):
            server_log.flush()
            with open(server_log_path, "r", encoding="utf-8") as f:
                log_content = f.read()
            raise RuntimeError(f"Server failed to start:\n{log_content}")

        print(f"  [+] API server responsive at {api_url}/health")

        # ---------------------------------------------------------------------
        # Step 2: Query Scenario Catalog
        # ---------------------------------------------------------------------
        print("\n[2/10] Querying scenario catalog (/api/replay/scenarios)...")
        status, scenarios_resp = request_json(api_url, "GET", "/api/replay/scenarios")
        assert status == 200, f"Failed to fetch scenarios: HTTP {status}"
        scenarios = scenarios_resp.get("scenarios", [])
        assert len(scenarios) == 3, f"Expected 3 approved scenarios, found {len(scenarios)}"
        scenario_ids = [s["scenario_id"] for s in scenarios]
        print(f"  [+] Catalog loaded: {scenario_ids}")
        assert "SCN-AUTH-BURST" in scenario_ids
        assert "SCN-WEB-PROBE" in scenario_ids
        assert "SCN-PRIV-ESC" in scenario_ids

        # ---------------------------------------------------------------------
        # Step 3: Execute Scenario A (Authentication Burst)
        # ---------------------------------------------------------------------
        print("\n[3/10] Executing Scenario A: Suspicious Account Activity (SCN-AUTH-BURST)...")
        status, resp_a = request_json(api_url, "POST", "/api/replay/run", {"scenario_id": "SCN-AUTH-BURST"})
        assert status == 200, f"Scenario A execution failed: HTTP {status} {resp_a}"
        run_a = resp_a["run"]
        run_a_id = run_a["replay_id"]
        print(f"  [+] Replay completed: {run_a_id} in {run_a['metrics']['duration_ms']}ms")

        # Verify Pipeline metrics
        m_a = run_a["metrics"]
        assert m_a["imported_records"] == 6, f"Expected 6 imported, got {m_a['imported_records']}"
        assert m_a["normalized_events"] == 6, f"Expected 6 normalized, got {m_a['normalized_events']}"
        assert m_a["findings_count"] == 2, f"Expected 2 findings (AUTH-001, AUTH-002), got {m_a['findings_count']}"
        assert m_a["cases_count"] == 1, f"Expected 1 case, got {m_a['cases_count']}"

        # Verify Assertions
        assert m_a["assertions_failed"] == 0, f"Assertions failed: {run_a['assertion_results']}"
        assert m_a["assertions_passed"] >= 8, f"Expected >= 8 passed assertions, got {m_a['assertions_passed']}"
        print(f"  [+] All {m_a['assertions_passed']} proof assertions verified (100% PASS)")

        # Verify Claim Guard Outcomes
        claims_a = {c["claim_id"]: c["status"] for c in run_a["claims_snapshot"]}
        assert claims_a["clm_scn_a_01"] == "verified"
        assert claims_a["clm_scn_a_02"] == "verified"
        assert claims_a["clm_scn_a_03"] == "blocked"  # Unproven attacker identity
        assert claims_a["clm_scn_a_04"] == "qualified"
        print("  [+] Claim Guard verified 2 claims, qualified 1, blocked 1 (unproven attacker identity)")

        # ---------------------------------------------------------------------
        # Step 4: Execute Scenario B (Web Endpoint Probing)
        # ---------------------------------------------------------------------
        print("\n[4/10] Executing Scenario B: Sensitive Endpoint Probing (SCN-WEB-PROBE)...")
        status, resp_b = request_json(api_url, "POST", "/api/replay/run", {"scenario_id": "SCN-WEB-PROBE"})
        assert status == 200, f"Scenario B execution failed: HTTP {status} {resp_b}"
        run_b = resp_b["run"]
        m_b = run_b["metrics"]
        assert m_b["imported_records"] == 5
        assert m_b["findings_count"] == 1
        assert m_b["cases_count"] == 1
        assert m_b["assertions_failed"] == 0

        # Verify IP Guardrail enforcement
        claims_b = {c["claim_id"]: c["status"] for c in run_b["claims_snapshot"]}
        assert claims_b["clm_scn_b_03"] == "blocked"
        print("  [+] WEB-001 detected and IP Guardrail enforced: identity from IP alone BLOCKED")

        # ---------------------------------------------------------------------
        # Step 5: Execute Scenario C (Privilege Escalation)
        # ---------------------------------------------------------------------
        print("\n[5/10] Executing Scenario C: Privilege Escalation Investigation (SCN-PRIV-ESC)...")
        status, resp_c = request_json(api_url, "POST", "/api/replay/run", {"scenario_id": "SCN-PRIV-ESC"})
        assert status == 200, f"Scenario C execution failed: HTTP {status} {resp_c}"
        run_c = resp_c["run"]
        m_c = run_c["metrics"]
        assert m_c["imported_records"] == 3
        assert m_c["findings_count"] == 1
        assert m_c["cases_count"] == 1
        assert m_c["assertions_failed"] == 0

        # Verify exaggerated record count blocked
        claims_c = {c["claim_id"]: c["status"] for c in run_c["claims_snapshot"]}
        assert claims_c["clm_scn_c_03"] == "blocked"
        print("  [+] PRIV-001 detected and fabricated record count (50 vs 1) BLOCKED")

        # ---------------------------------------------------------------------
        # Step 6: What-If Counterfactual Simulation
        # ---------------------------------------------------------------------
        print("\n[6/10] Running What-If simulation with elevated failure threshold (10)...")
        what_if_payload = {
            "scenario_id": "SCN-AUTH-BURST",
            "what_if": {
                "what_if_id": "WIF-THRESHOLD-10",
                "name": "Higher Failure Threshold (10)",
                "description": "Increase failure threshold from 5 to 10 failures.",
                "rule_overrides": {"AUTH-001": {"threshold_count": 10}},
            },
        }
        status, resp_wif = request_json(api_url, "POST", "/api/replay/run", what_if_payload)
        assert status == 200, f"What-If execution failed: HTTP {status}"
        run_wif = resp_wif["run"]
        diff = run_wif["what_if_diff"]
        assert diff is not None
        assert "AUTH-001" in diff["findings_removed"]
        assert diff["metric_deltas"]["findings_count"] == -1
        print(f"  [+] What-If diff computed: AUTH-001 successfully suppressed (-1 finding)")

        # ---------------------------------------------------------------------
        # Step 7: Repeatability and Determinism Verification
        # ---------------------------------------------------------------------
        print("\n[7/10] Verifying run repeatability & determinism (/api/replay/compare)...")
        # Run baseline Scenario A a second time
        status, resp_a2 = request_json(api_url, "POST", "/api/replay/run", {"scenario_id": "SCN-AUTH-BURST"})
        run_a2_id = resp_a2["run"]["replay_id"]

        status, comp_resp = request_json(
            api_url,
            "POST",
            "/api/replay/compare",
            {"run_a_id": run_a_id, "run_b_id": run_a2_id},
        )
        assert status == 200, f"Compare failed: HTTP {status}"
        comp = comp_resp["comparison"]
        assert comp["is_identical"] is True, f"Deterministic replay produced differences: {comp}"
        for k, v in comp["metric_deltas"].items():
            assert v == 0, f"Metric delta {k} non-zero: {v}"
        print("  [+] 100% Identical execution verified across repeated runs (0 metric deltas)")

        # ---------------------------------------------------------------------
        # Step 8: Strict Host Data Isolation Check
        # ---------------------------------------------------------------------
        print("\n[8/10] Verifying strict host SQLite data isolation...")
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) AS cnt FROM normalized_events;")
        evt_cnt = cur.fetchone()["cnt"]
        assert evt_cnt == 0, f"Isolation failure! Found {evt_cnt} normalized events in host DB!"

        cur.execute("SELECT COUNT(*) AS cnt FROM findings;")
        find_cnt = cur.fetchone()["cnt"]
        assert find_cnt == 0, f"Isolation failure! Found {find_cnt} findings in host DB!"

        cur.execute("SELECT COUNT(*) AS cnt FROM cases;")
        case_cnt = cur.fetchone()["cnt"]
        assert case_cnt == 0, f"Isolation failure! Found {case_cnt} cases in host DB!"

        cur.execute("SELECT COUNT(*) AS cnt FROM replay_runs;")
        runs_cnt = cur.fetchone()["cnt"]
        assert runs_cnt >= 4, f"Expected >= 4 replay run records in host DB, found {runs_cnt}"
        conn.close()
        print("  [+] Host SQLite tables contain 0 events, 0 findings, 0 cases (Zero data contamination)")

        # ---------------------------------------------------------------------
        # Step 9: Replay Run History Reset
        # ---------------------------------------------------------------------
        print("\n[9/10] Testing replay run history reset (/api/replay/reset)...")
        status, reset_resp = request_json(api_url, "POST", "/api/replay/reset")
        assert status == 200, f"Reset failed: HTTP {status}"
        assert reset_resp["status"] == "success"
        assert reset_resp["deleted_count"] >= 4

        status, runs_list_resp = request_json(api_url, "GET", "/api/replay/runs")
        assert status == 200
        assert len(runs_list_resp["runs"]) == 0
        print("  [+] Replay history cleanly reset. All historical runs purged.")

        # ---------------------------------------------------------------------
        # Step 10: Final Verification
        # ---------------------------------------------------------------------
        print("\n[10/10] Verification Complete!")
        print("=" * 75)
        print(" SUCCESS: Phase 7 Replay Lab and What-If Simulation fully verified.")
        print("  - Real pipeline execution: Import -> Norm -> Detect -> Correlate -> Timeline -> Claim Guard")
        print("  - Complete database isolation verified")
        print("  - 100% assertions passed across all 3 canonical scenarios")
        print("  - Determinism & What-If semantic diff confirmed")
        print("=" * 75)

    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=3)
        except Exception:
            server_proc.kill()

        try:
            server_log.close()
        except Exception:
            pass

        gc.collect()
        try:
            temp_dir.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    main()
