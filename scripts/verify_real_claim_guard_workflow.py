"""Real end-to-end verification script for Claim Guard: Typed AI Claims, Deterministic Verification & Safe Rendering."""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def wait_for_api(api_url: str, timeout: float = 8.0) -> bool:
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
    print("=" * 72)
    print(" PROJECT SENTINEL — Phase 6 Real Claim Guard Workflow Verification")
    print(" 'AI proposes. Deterministic code verifies. The operator decides.'")
    print("=" * 72)

    temp_dir = tempfile.TemporaryDirectory()
    db_path = Path(temp_dir.name) / "sentinel_claim_guard_audit.db"
    port = find_free_port()
    api_url = f"http://127.0.0.1:{port}"

    server_env = {
        **os.environ,
        "SENTINEL_DB_PATH": str(db_path),
        "SENTINEL_PORT": str(port),
    }

    print(f"\n[*] Starting Sentinel backend on 127.0.0.1:{port} with isolated DB: {db_path}...")
    server_log = open(Path(temp_dir.name) / "server.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "backend.api.server", "--port", str(port)],
        cwd=str(ROOT_DIR),
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True,
        env=server_env,
    )

    if not wait_for_api(api_url):
        print("[!] Backend failed to start.", file=sys.stderr)
        proc.kill()
        sys.exit(1)
    print(f"[+] Backend active and responding at {api_url}/health.")

    try:
        # STEP 1: Ingest multi-source investigation data
        print("\n--> [Step 1] Ingesting multi-source authentication and privilege logs...")
        run_ts = int(time.time() * 1000)

        auth_csv = (
            "timestamp,username,auth_result,source_ip,session_id\n"
            f"2026-11-09T10:00:00Z,operator_dave,FAILURE,198.51.100.42,sess_cg_{run_ts}_1\n"
            f"2026-11-09T10:01:00Z,operator_dave,FAILURE,198.51.100.42,sess_cg_{run_ts}_2\n"
            f"2026-11-09T10:02:00Z,operator_dave,FAILURE,198.51.100.42,sess_cg_{run_ts}_3\n"
            f"2026-11-09T10:03:00Z,operator_dave,FAILURE,198.51.100.42,sess_cg_{run_ts}_4\n"
            f"2026-11-09T10:04:00Z,operator_dave,FAILURE,198.51.100.42,sess_cg_{run_ts}_5\n"
            f"2026-11-09T10:05:00Z,operator_dave,SUCCESS,198.51.100.42,sess_cg_{run_ts}_6\n"
        )
        status, auth_res = request_json(api_url, "POST", "/api/import", {
            "filename": f"auth_cg_{run_ts}.csv",
            "content": auth_csv,
            "parser_id": "auth_csv",
            "source_id": "src_manual_default",
        })
        assert status == 200 and auth_res["accepted_records"] == 6
        print("    [PASS] Auth CSV ingested: 6 records for user 'operator_dave'")

        # Privilege escalation
        priv_jsonl = (
            f'{{"timestamp": "2026-11-09T10:15:00Z", "event_type": "role_changed", '
            f'"user_principal": "operator_dave", "target_resource": "cloud_admin", '
            f'"attributes": {{"action": "grant_role", "subject": "operator_dave"}}}}\n'
        )
        status, priv_res = request_json(api_url, "POST", "/api/import", {
            "filename": f"priv_cg_{run_ts}.jsonl",
            "content": priv_jsonl,
            "parser_id": "generic_jsonl",
            "source_id": "src_manual_default",
        })
        assert status == 200 and priv_res["accepted_records"] == 1
        print("    [PASS] Privilege JSONL ingested: 1 record for user 'operator_dave'")

        # Unrelated Web Access logs from IP without user -> WEB-001 (Medium)
        web_csv = (
            "timestamp,http_method,request_path,status_code,source_ip\n"
            f"2026-11-09T10:30:00Z,GET,/.env,404,203.0.113.88\n"
            f"2026-11-09T10:31:00Z,POST,/admin/login,401,203.0.113.88\n"
            f"2026-11-09T10:32:00Z,GET,/wp-admin/setup.php,404,203.0.113.88\n"
        )
        status, web_res = request_json(api_url, "POST", "/api/import", {
            "filename": f"web_cg_{run_ts}.csv",
            "content": web_csv,
            "parser_id": "web_access_csv",
            "source_id": "src_manual_default",
        })
        assert status == 200 and web_res["accepted_records"] == 3
        print("    [PASS] Web Access CSV ingested: 3 probe requests from 203.0.113.88")

        # STEP 2: Normalization
        print("\n--> [Step 2] Normalizing canonical events...")
        status, norm_res = request_json(api_url, "POST", "/api/normalization/run", {})
        assert status == 200
        print(f"    [PASS] Normalized {norm_res['result']['accepted']} events.")

        # STEP 3: Detection
        print("\n--> [Step 3] Running detection engine...")
        status, det_res = request_json(api_url, "POST", "/api/detection/run", {})
        assert status == 200 and det_res["status"] == "success"
        stats = det_res["result"]
        print(f"    [PASS] Detection run: {stats['findings_generated']} findings generated.")
        assert stats["findings_generated"] >= 3

        # STEP 4: Correlation
        print("\n--> [Step 4] Correlating findings into investigation cases...")
        status, corr_res = request_json(api_url, "POST", "/api/cases/correlate", {"window_seconds": 3600})
        assert status == 200 and corr_res["status"] == "success"
        corr_stats = corr_res["result"]
        print(f"    [PASS] Correlation completed: {corr_stats['cases_created']} cases created.")
        assert corr_stats["cases_created"] >= 1

        # Fetch case
        status, cases_data = request_json(api_url, "GET", "/api/cases")
        assert status == 200
        dave_cases = [c for c in cases_data["cases"] if c.get("correlation_key_value") == "operator_dave"]
        assert len(dave_cases) >= 1
        case_id = dave_cases[0]["case_id"]
        print(f"    [PASS] Target investigation case identified: {case_id} (user: 'operator_dave')")

        status, case_detail = request_json(api_url, "GET", f"/api/cases/{case_id}")
        assert status == 200
        events = case_detail["events"]
        findings = case_detail["findings"]
        failure_events = [e for e in events if str(e.get("status", "")).upper() == "FAILURE"]
        failure_ids = [e["event_id"] for e in failure_events]
        finding_ids = [f["finding_id"] for f in findings]
        print(f"    [PASS] Case evidence: {len(events)} events ({len(failure_ids)} failures), {len(findings)} findings.")

        # Identify another case to test genuine cross-case reference injection
        other_cases = [c for c in cases_data["cases"] if c.get("case_id") != case_id]
        if other_cases:
            other_detail = request_json(api_url, "GET", f"/api/cases/{other_cases[0]['case_id']}")[1]
            foreign_evidence_id = (other_detail.get("events", [{}])[0].get("event_id") or
                                   other_detail.get("findings", [{}])[0].get("finding_id") or
                                   "evt_foreign_case_tamper_9999")
        else:
            foreign_evidence_id = "evt_foreign_case_tamper_9999"

        # STEP 5: Verify Claim Guard Template Catalog
        print("\n--> [Step 5] Checking approved template catalog at /api/claims/templates...")
        status, templates_res = request_json(api_url, "GET", "/api/claims/templates")
        assert status == 200
        template_count = len(templates_res.get("templates", []))
        type_count = len(templates_res.get("supported_claim_types", []))
        print(f"    [PASS] Catalog returns {template_count} approved templates and {type_count} claim types.")
        assert template_count >= 8
        assert type_count >= 8

        # STEP 6: Execute Signature Demo Moment via /api/cases/{case_id}/claims/demo
        print(f"\n--> [Step 6] Executing Claim Guard Signature Demo on case {case_id}...")
        status, demo_res = request_json(api_url, "POST", f"/api/cases/{case_id}/claims/demo", {})
        assert status == 200
        report = demo_res["report"]
        print(f"    [PASS] Demo run finished:")
        print(f"           Verified claims:  {report['verified_count']}")
        print(f"           Qualified claims: {report['qualified_count']}")
        print(f"           Blocked claims:   {report['blocked_count']}")
        assert report["verified_count"] >= 2
        assert report["qualified_count"] >= 1
        assert report["blocked_count"] >= 2

        # Verify that blocked claims in demo are quarantined and never render factual affirmations
        blocked_results = [r for r in report["results"] if r["status"] == "blocked"]
        assert len(blocked_results) == report["blocked_count"]
        for blk in blocked_results:
            assert blk["status"] == "blocked"
            assert blk["rendered_text"].startswith("[BLOCKED CLAIM]")
            assert len(blk["blocked_reasons"]) > 0
            assert blk["suggested_remedy"] is not None
        print("    [PASS] All demo blocked claims correctly quarantined with remedies.")

        # STEP 7: Submit Adversarial and Custom Proposals via /api/claims/verify
        print("\n--> [Step 7] Testing security guardrails with adversarial proposals...")
        adversarial_proposals = [
            # 1. Valid proposal
            {
                "claim_id": "clm_adv_valid_01",
                "case_id": case_id,
                "claim_type": "event_count",
                "predicate": "contains_events_of_type",
                "value": {"count": len(failure_ids), "event_type": "user_authentication"},
                "evidence_refs": failure_ids,
                "certainty": "observed",
                "template_id": "case_event_count_v1",
            },
            # 2. Cross-case reference injection (referencing evidence from another case)
            {
                "claim_id": "clm_adv_cross_case",
                "case_id": case_id,
                "claim_type": "event_count",
                "predicate": "contains_events_of_type",
                "value": {"count": 1, "event_type": "user_authentication"},
                "evidence_refs": [foreign_evidence_id],
                "certainty": "observed",
                "template_id": "case_event_count_v1",
            },
            # 3. IP-only identity inference attempt
            {
                "claim_id": "clm_adv_ip_inference",
                "case_id": case_id,
                "claim_type": "entity_observed",
                "predicate": "identifies_entity",
                "value": {"entity_type": "user_principal", "entity_value": "mallory_attacker"},
                "evidence_refs": [e["event_id"] for e in events if e.get("source_ip") and not e.get("user_principal")][:1] or [failure_ids[0]],
                "certainty": "observed",
                "template_id": "case_entity_observed_v1",
            },
            # 4. Script injection in template parameter
            {
                "claim_id": "clm_adv_xss_injection",
                "case_id": case_id,
                "claim_type": "entity_observed",
                "predicate": "identifies_entity",
                "value": {"entity_type": "user", "entity_value": "<script>alert('XSS')</script>"},
                "evidence_refs": [failure_ids[0]],
                "certainty": "observed",
                "template_id": "case_entity_observed_v1",
            },
            # 5. Client attempts to forge status "verified" on hallucinated count
            {
                "claim_id": "clm_adv_forged_status",
                "case_id": case_id,
                "claim_type": "event_count",
                "predicate": "contains_events_of_type",
                "value": {"count": 9999, "event_type": "user_authentication"},
                "evidence_refs": failure_ids,
                "certainty": "observed",
                "template_id": "case_event_count_v1",
                "status": "verified",  # Malicious client injection
            },
        ]

        status, verify_res = request_json(api_url, "POST", "/api/claims/verify", {
            "case_id": case_id,
            "claims": adversarial_proposals,
        })
        assert status == 200
        custom_report = verify_res["report"]
        print(f"    [PASS] Custom proposals processed: "
              f"{custom_report['verified_count']} verified, {custom_report['blocked_count']} blocked.")

        # Assertions on adversarial outcomes
        res_by_id = {r["claim_id"]: r for r in custom_report["results"]}
        assert res_by_id["clm_adv_valid_01"]["status"] == "verified"
        assert res_by_id["clm_adv_cross_case"]["status"] == "blocked"
        assert any("cross-case" in reason.lower() for reason in res_by_id["clm_adv_cross_case"]["blocked_reasons"])
        print("    [PASS] Cross-case / foreign evidence reference injection blocked.")
        print("    [PASS] Cross-case / foreign evidence reference injection blocked.")

        assert res_by_id["clm_adv_xss_injection"]["status"] == "blocked"
        assert any("injection pattern detected" in reason.lower() for reason in res_by_id["clm_adv_xss_injection"]["blocked_reasons"])
        print("    [PASS] Script injection in claim payload blocked.")

        assert res_by_id["clm_adv_forged_status"]["status"] == "blocked"
        assert any("does not match verified count" in reason for reason in res_by_id["clm_adv_forged_status"]["blocked_reasons"])
        print("    [PASS] Client-forged 'status: verified' ignored and count mismatch blocked.")

        # STEP 8: Direct SQLite Database Audit
        print("\n--> [Step 8] Auditing SQLite schema, integrity, and foreign keys directly...")
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("PRAGMA foreign_key_check;")
        fk_violations = cur.fetchall()
        assert len(fk_violations) == 0, f"Foreign key violations found: {fk_violations}"
        print("    [PASS] PRAGMA foreign_key_check: 0 violations.")

        cur.execute("SELECT COUNT(*) FROM claim_proposals;")
        proposal_count = cur.fetchone()[0]
        assert proposal_count >= 10
        print(f"    [PASS] SQLite 'claim_proposals' table: {proposal_count} records.")

        cur.execute("SELECT COUNT(*) FROM claim_verifications;")
        verification_count = cur.fetchone()[0]
        assert verification_count >= 10
        print(f"    [PASS] SQLite 'claim_verifications' table: {verification_count} records.")

        cur.execute("SELECT status, count(*) FROM claim_verifications GROUP BY status;")
        counts = dict(cur.fetchall())
        print(f"    [PASS] Database verification breakdown: {counts}")
        assert counts.get("verified", 0) >= 3
        assert counts.get("qualified", 0) >= 1
        assert counts.get("blocked", 0) >= 5

        conn.close()

        # STEP 9: Refresh Case Detail and Confirm Claims Embedded
        print("\n--> [Step 9] Confirming case detail /api/cases/{id} reflects Claim Guard claims...")
        status, updated_case = request_json(api_url, "GET", f"/api/cases/{case_id}")
        assert status == 200
        embedded_claims = updated_case.get("claims", [])
        assert len(embedded_claims) >= 10
        print(f"    [PASS] Case {case_id} contains {len(embedded_claims)} persisted Claim Guard entries.")

    finally:
        print("\n[*] Stopping Sentinel backend service...")
        proc.terminate()
        try:
            proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            proc.kill()
        try:
            server_log.close()
        except Exception:
            pass
        try:
            temp_dir.cleanup()
        except Exception:
            pass
        print("[+] Backend stopped cleanly.")

    print("\n" + "=" * 72)
    print(" ALL REAL CLAIM GUARD WORKFLOW VERIFICATION CHECKS PASSED!")
    print("=" * 72)


if __name__ == "__main__":
    main()
