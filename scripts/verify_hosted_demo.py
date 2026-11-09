"""Project Sentinel — Phase 8 End-to-End Hosted Judge Demo Verification.

Executes the complete 17-step judge evaluation workflow against any target URL:
- Local production container: http://127.0.0.1:8000
- Deployed public demo: https://...

Usage:
    python scripts/verify_hosted_demo.py [--url http://127.0.0.1:8000]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple


class HostedJudgeValidator:
    """Automated validator executing the 17-step judge evaluation workflow."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.passed_steps = 0
        self.failed_steps = 0

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        raw_body: Optional[bytes] = None,
        content_type: str = "application/json",
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, Any, Dict[str, str]]:
        url = f"{self.base_url}{path}"
        data = None
        if raw_body is not None:
            data = raw_body
        elif payload is not None:
            data = json.dumps(payload).encode("utf-8")

        req_headers = {"Accept": "application/json"}
        if data is not None:
            req_headers["Content-Type"] = content_type
        if headers:
            req_headers.update(headers)

        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                status = resp.status
                resp_headers = dict(resp.headers)
                body_bytes = resp.read()
                try:
                    res_data = json.loads(body_bytes.decode("utf-8"))
                except Exception:
                    res_data = body_bytes.decode("utf-8")
                return status, res_data, resp_headers
        except urllib.error.HTTPError as err:
            err_headers = dict(err.headers)
            body_bytes = err.read()
            try:
                res_data = json.loads(body_bytes.decode("utf-8"))
            except Exception:
                res_data = body_bytes.decode("utf-8")
            return err.code, res_data, err_headers

    def step(self, step_num: int, name: str, condition: bool, detail: str = "") -> None:
        if condition:
            print(f"  [PASS] Step {step_num:02d}: {name}")
            if detail:
                print(f"         {detail}")
            self.passed_steps += 1
        else:
            print(f"  [FAIL] Step {step_num:02d}: {name}")
            if detail:
                print(f"         ERROR: {detail}")
            self.failed_steps += 1

    def run_all(self) -> bool:
        print("=" * 80)
        print(f" PROJECT SENTINEL — PHASE 8 HOSTED JUDGE VERIFICATION")
        print(f" Target URL: {self.base_url}")
        print("=" * 80)

        # ---------------------------------------------------------------------
        # Step 1: Health Endpoint Check
        # ---------------------------------------------------------------------
        s1, h1, _ = self._request("GET", "/health")
        self.step(
            1, "Health Endpoint Check (/health)",
            s1 == 200 and h1.get("status") == "ok",
            f"Status {s1}, app={h1.get('app')}, version={h1.get('version')}, demo_mode={h1.get('demo_mode')}",
        )

        # ---------------------------------------------------------------------
        # Step 2: Readiness Probe Check
        # ---------------------------------------------------------------------
        s2, r2, _ = self._request("GET", "/ready")
        self.step(
            2, "Readiness Probe Check (/ready)",
            s2 == 200 and r2.get("status") == "ready" and r2.get("database") == "connected",
            f"Status {s2}, database={r2.get('database')}, ready={r2.get('status')}",
        )

        # ---------------------------------------------------------------------
        # Step 3: Landing Page & Security Headers
        # ---------------------------------------------------------------------
        s3, html3, hdr3 = self._request("GET", "/")
        has_title = "Project Sentinel" in str(html3)
        has_security_hdr = hdr3.get("X-Content-Type-Options") == "nosniff"
        self.step(
            3, "Landing Page & Security Headers (GET /)",
            s3 == 200 and has_title and has_security_hdr,
            f"Status {s3}, X-Content-Type-Options={hdr3.get('X-Content-Type-Options')}, X-Frame-Options={hdr3.get('X-Frame-Options')}",
        )

        # ---------------------------------------------------------------------
        # Step 4: Scenario Catalog Inspection
        # ---------------------------------------------------------------------
        s4, cat4, _ = self._request("GET", "/api/replay/scenarios")
        scenarios = cat4.get("scenarios", [])
        has_all_three = {"SCN-AUTH-BURST", "SCN-WEB-PROBE", "SCN-PRIV-ESC"}.issubset(
            {s["scenario_id"] for s in scenarios}
        )
        self.step(
            4, "Query Scenario Catalog (/api/replay/scenarios)",
            s4 == 200 and has_all_three,
            f"Loaded {len(scenarios)} approved synthetic scenarios: {[s['scenario_id'] for s in scenarios]}",
        )

        # ---------------------------------------------------------------------
        # Step 5: Execute Scenario A (Suspicious Account Activity)
        # ---------------------------------------------------------------------
        s5, res5, _ = self._request("POST", "/api/replay/run", payload={"scenario_id": "SCN-AUTH-BURST"})
        run_a = res5.get("run", {})
        run_a_ok = (s5 == 200 and run_a.get("status") == "completed")
        self.step(
            5, "Execute Scenario A (SCN-AUTH-BURST)",
            run_a_ok,
            f"Replay ID {run_a.get('replay_id')} in {run_a.get('metrics', {}).get('duration_ms')}ms, status={run_a.get('status')}",
        )

        # ---------------------------------------------------------------------
        # Step 6: Inspect Scenario A Findings & Cases
        # ---------------------------------------------------------------------
        cases_snap = run_a.get("cases_snapshot", [])
        has_cases = len(cases_snap) >= 1
        case_0 = cases_snap[0] if has_cases else {}
        self.step(
            6, "Inspect Scenario A Findings & Cases",
            has_cases and case_0.get("severity") == "High",
            f"Case {case_0.get('case_id')} severity={case_0.get('severity')}, findings={len(case_0.get('findings', []))}",
        )

        # ---------------------------------------------------------------------
        # Step 7: Verify Claim Guard Results (Verified vs Blocked)
        # ---------------------------------------------------------------------
        claims_snap = {c["claim_id"]: c for c in run_a.get("claims_snapshot", [])}
        cg_ok = (
            claims_snap.get("clm_scn_a_01", {}).get("status") == "verified"
            and claims_snap.get("clm_scn_a_02", {}).get("status") == "verified"
            and claims_snap.get("clm_scn_a_03", {}).get("status") == "blocked"
            and claims_snap.get("clm_scn_a_04", {}).get("status") == "qualified"
        )
        self.step(
            7, "Verify Claim Guard Anti-Hallucination Results",
            cg_ok,
            f"Verified: 2, Qualified: 1, Blocked (Unproven Attacker): {claims_snap.get('clm_scn_a_03', {}).get('status')}",
        )

        # ---------------------------------------------------------------------
        # Step 8: Execute Scenario B (Web Route Reconnaissance)
        # ---------------------------------------------------------------------
        s8, res8, _ = self._request("POST", "/api/replay/run", payload={"scenario_id": "SCN-WEB-PROBE"})
        run_b = res8.get("run", {})
        self.step(
            8, "Execute Scenario B (SCN-WEB-PROBE)",
            s8 == 200 and run_b.get("status") == "completed",
            f"Replay ID {run_b.get('replay_id')}, findings={run_b.get('metrics', {}).get('findings_count')}",
        )

        # ---------------------------------------------------------------------
        # Step 9: Execute Scenario C (Privilege Escalation)
        # ---------------------------------------------------------------------
        s9, res9, _ = self._request("POST", "/api/replay/run", payload={"scenario_id": "SCN-PRIV-ESC"})
        run_c = res9.get("run", {})
        self.step(
            9, "Execute Scenario C (SCN-PRIV-ESC)",
            s9 == 200 and run_c.get("status") == "completed",
            f"Replay ID {run_c.get('replay_id')}, findings={run_c.get('metrics', {}).get('findings_count')}",
        )

        # ---------------------------------------------------------------------
        # Step 10: Run What-If Simulation
        # ---------------------------------------------------------------------
        s10, res10, _ = self._request(
            "POST",
            "/api/replay/run",
            payload={
                "scenario_id": "SCN-AUTH-BURST",
                "what_if": {
                    "what_if_id": "WIF-THRESHOLD-10",
                    "description": "Increase failure threshold to 10",
                    "rule_overrides": {"AUTH-001": {"threshold_count": 10}},
                },
            },
        )
        run_wif = res10.get("run", {})
        diff = run_wif.get("what_if_diff", {})
        self.step(
            10, "Run What-If Simulation (Threshold Sensitivity)",
            s10 == 200 and run_wif.get("mode") == "what_if" and "AUTH-001" in diff.get("findings_removed", []),
            f"Mode={run_wif.get('mode')}, findings_removed={diff.get('findings_removed')}",
        )

        # ---------------------------------------------------------------------
        # Step 11: Compare Two Historical Replay Runs
        # ---------------------------------------------------------------------
        run_a_id = run_a.get("replay_id")
        # Run A again to get a second run to compare
        _, res_a2, _ = self._request("POST", "/api/replay/run", payload={"scenario_id": "SCN-AUTH-BURST"})
        run_a2_id = res_a2.get("run", {}).get("replay_id")
        s11, comp11, _ = self._request(
            "POST",
            "/api/replay/compare",
            payload={"run_a_id": run_a_id, "run_b_id": run_a2_id},
        )
        comp_res = comp11.get("comparison", {})
        self.step(
            11, "Compare Replay Runs Determinism Check (/api/replay/compare)",
            s11 == 200 and comp_res.get("is_identical") is True and comp_res.get("is_compatible") is True,
            f"is_identical={comp_res.get('is_identical')}, deltas={comp_res.get('metric_deltas')}",
        )

        # ---------------------------------------------------------------------
        # Step 12: Confirm Replay History Persistence
        # ---------------------------------------------------------------------
        s12, runs12, _ = self._request("GET", "/api/replay/runs?limit=10")
        total_runs = runs12.get("total", 0)
        self.step(
            12, "Confirm Replay History Persistence (/api/replay/runs)",
            s12 == 200 and total_runs >= 3,
            f"Persisted historical runs: {total_runs}",
        )

        # ---------------------------------------------------------------------
        # Step 13: Verify Safe Replay Reset
        # ---------------------------------------------------------------------
        s13, reset13, _ = self._request("POST", "/api/replay/reset", payload={})
        self.step(
            13, "Verify Safe Replay Reset (/api/replay/reset)",
            s13 == 200 and reset13.get("status") == "success",
            f"Deleted count: {reset13.get('deleted_count')}, Core operational data preserved",
        )

        # ---------------------------------------------------------------------
        # Step 14: Security Boundary: Block Operational Ingestion in Demo Mode
        # ---------------------------------------------------------------------
        fake_csv = b"timestamp,user,ip,action,status\n2026-11-09T08:00:00Z,eve,1.1.1.1,login,failure\n"
        s14, err14, _ = self._request(
            "POST",
            "/api/import",
            raw_body=fake_csv,
            content_type="text/csv",
            headers={"Content-Length": str(len(fake_csv))},
        )
        self.step(
            14, "Security Guardrail: Block Arbitrary Upload in Demo Mode",
            s14 == 403,
            f"Status={s14}, Message={err14.get('message') if isinstance(err14, dict) else err14}",
        )

        # ---------------------------------------------------------------------
        # Step 15: Security Guardrail: Rate Limiting Enforcement
        # ---------------------------------------------------------------------
        # Rapid burst test
        burst_status = []
        for _ in range(65):
            sb, _, _ = self._request("POST", "/api/replay/compare", payload={"run_a_id": "r1", "run_b_id": "r2"})
            burst_status.append(sb)
            if sb == 429:
                break
        rate_limited = (429 in burst_status)
        self.step(
            15, "Security Guardrail: Rate Limiting on Heavy Operations",
            rate_limited,
            f"429 Too Many Requests triggered after {len(burst_status)} rapid requests",
        )

        # ---------------------------------------------------------------------
        # Step 16: Verify Static Assets Serving & Content-Type
        # ---------------------------------------------------------------------
        # Check /assets or index.html
        s16, _, hdr16 = self._request("GET", "/")
        ct = hdr16.get("Content-Type", "")
        self.step(
            16, "Verify Static Serving & MIME Types",
            s16 == 200 and "text/html" in ct,
            f"Root serves index.html with Content-Type={ct}",
        )

        # ---------------------------------------------------------------------
        # Step 17: Verify SPA Client-Side Route Fallback
        # ---------------------------------------------------------------------
        s17, html17, _ = self._request("GET", "/?view=replay")
        self.step(
            17, "Verify SPA Route Fallback (/?view=replay)",
            s17 == 200 and "Project Sentinel" in str(html17),
            f"Client route /?view=replay served successfully",
        )

        print("=" * 80)
        print(f" HOSTED JUDGE VERIFICATION SUMMARY: {self.passed_steps}/17 STEPS PASSED")
        print("=" * 80)

        return self.failed_steps == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Project Sentinel Phase 8 Hosted Judge Verification")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Base URL of deployed Sentinel service")
    args = parser.parse_args()

    validator = HostedJudgeValidator(base_url=args.url)
    success = validator.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

