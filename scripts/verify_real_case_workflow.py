"""Verification script for real Ingestion-to-Cases correlation and analyst review workflow."""
from __future__ import annotations

import json
import os
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
API_URL = "http://127.0.0.1:8000"


def wait_for_api(timeout: float = 6.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(f"{API_URL}/health")
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.1)
    return False


def request_json(method: str, endpoint: str, body: dict | None = None) -> tuple[int, dict]:
    url = f"{API_URL}{endpoint}"
    data_bytes = json.dumps(body).encode("utf-8") if body else None
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
    print("=" * 70)
    print(" PROJECT SENTINEL — Phase 5 Real Cases & Correlation Workflow Audit")
    print("=" * 70)

    temp_dir = tempfile.TemporaryDirectory()
    db_path = Path(temp_dir.name) / "sentinel_cases_audit.db"
    server_env = {**os.environ, "SENTINEL_DB_PATH": str(db_path)}

    # 1. Start Sentinel backend
    print(f"\n[*] Starting Sentinel backend on 127.0.0.1:8000 with isolated DB: {db_path}...")
    server_log = open(Path(temp_dir.name) / "server.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "backend.api.server"],
        cwd=str(ROOT_DIR),
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True,
        env=server_env,
    )

    if not wait_for_api():
        print("[!] Backend failed to start.", file=sys.stderr)
        proc.kill()
        sys.exit(1)
    print("[+] Backend active and responding to /health.")

    try:
        # STEP 1: Ingest Auth CSV and Privilege logs for victim_user
        print("\n--> [Step 1] Ingesting multi-source logs containing correlation keys...")
        run_ts = int(time.time() * 1000)

        # 5 failures + 1 success for victim_user -> will trigger AUTH-001 (Medium) and AUTH-002 (High)
        auth_csv = (
            "timestamp,username,auth_result,source_ip,session_id\n"
            f"2026-11-09T10:00:00Z,analyst_bob,FAILURE,198.51.100.99,sess_case_{run_ts}_1\n"
            f"2026-11-09T10:01:00Z,analyst_bob,FAILURE,198.51.100.99,sess_case_{run_ts}_2\n"
            f"2026-11-09T10:02:00Z,analyst_bob,FAILURE,198.51.100.99,sess_case_{run_ts}_3\n"
            f"2026-11-09T10:03:00Z,analyst_bob,FAILURE,198.51.100.99,sess_case_{run_ts}_4\n"
            f"2026-11-09T10:04:00Z,analyst_bob,FAILURE,198.51.100.99,sess_case_{run_ts}_5\n"
            f"2026-11-09T10:05:00Z,analyst_bob,SUCCESS,198.51.100.99,sess_case_{run_ts}_6\n"
        )
        status, auth_res = request_json("POST", "/api/import", {
            "filename": f"auth_case_{run_ts}.csv",
            "content": auth_csv,
            "parser_id": "auth_csv",
            "source_id": "src_manual_default",
        })
        assert status == 200 and auth_res["accepted_records"] == 6
        print(f"    [PASS] Auth CSV ingested: 6 records for user 'analyst_bob'")

        # Privilege escalation for same user 'analyst_bob' within the same 1-hour window -> triggers PRIV-001 (High)
        priv_jsonl = (
            f'{{"timestamp": "2026-11-09T10:20:00Z", "event_type": "role_changed", '
            f'"user_principal": "analyst_bob", "target_resource": "cloud_admin_role", '
            f'"attributes": {{"action": "grant_role", "subject": "analyst_bob"}}}}\n'
        )
        status, priv_res = request_json("POST", "/api/import", {
            "filename": f"priv_case_{run_ts}.jsonl",
            "content": priv_jsonl,
            "parser_id": "generic_jsonl",
            "source_id": "src_manual_default",
        })
        assert status == 200 and priv_res["accepted_records"] == 1
        print(f"    [PASS] Privilege JSONL ingested: 1 record for user 'analyst_bob'")

        # Unrelated Web Access logs from IP without user -> WEB-001 (Medium)
        web_csv = (
            "timestamp,http_method,request_path,status_code,source_ip\n"
            f"2026-11-09T10:30:00Z,GET,/.env,404,203.0.113.77\n"
            f"2026-11-09T10:31:00Z,POST,/admin/login,401,203.0.113.77\n"
            f"2026-11-09T10:32:00Z,GET,/wp-admin/setup.php,404,203.0.113.77\n"
        )
        status, web_res = request_json("POST", "/api/import", {
            "filename": f"web_case_{run_ts}.csv",
            "content": web_csv,
            "parser_id": "web_access_csv",
            "source_id": "src_manual_default",
        })
        assert status == 200 and web_res["accepted_records"] == 3
        print(f"    [PASS] Web Access CSV ingested: 3 probe requests from 203.0.113.77")

        # STEP 2: Normalization
        print("\n--> [Step 2] Normalizing canonical events...")
        status, norm_res = request_json("POST", "/api/normalization/run", {})
        assert status == 200
        print(f"    [PASS] Normalized {norm_res['result']['accepted']} events.")

        # STEP 3: Detection Engine
        print("\n--> [Step 3] Running detection engine to produce findings...")
        status, det_res = request_json("POST", "/api/detection/run", {})
        assert status == 200 and det_res["status"] == "success"
        stats = det_res["result"]
        print(f"    [PASS] Detection run {stats['evaluation_id']}: {stats['findings_generated']} findings generated.")
        assert stats["findings_generated"] >= 4

        # STEP 4: Correlation Engine Execution
        print("\n--> [Step 4] Running deterministic Correlation Engine...")
        status, corr_res = request_json("POST", "/api/cases/correlate", {"window_seconds": 3600})
        assert status == 200 and corr_res["status"] == "success"
        corr_stats = corr_res["result"]
        print(f"    [PASS] Correlation run {corr_stats['evaluation_id']}: {corr_stats['cases_created']} cases created, "
              f"{corr_stats['findings_scanned']} findings scanned in {corr_stats['duration_ms']:.2f}ms.")
        assert corr_stats["cases_created"] >= 1
        assert corr_stats["findings_scanned"] >= 3

        # STEP 5: List & Inspect Cases via API
        print("\n--> [Step 5] Querying /api/cases to verify case clustering and severity...")
        status, cases_data = request_json("GET", "/api/cases")
        assert status == 200
        cases = cases_data["cases"]
        print(f"    [PASS] Total cases returned: {cases_data['total']}")

        # Find the case for analyst_bob
        bob_cases = [c for c in cases if c.get("correlation_key_value") == "analyst_bob"]
        assert len(bob_cases) >= 1, "Expected at least one case correlated for user 'analyst_bob'"
        bob_case = bob_cases[0]
        case_id = bob_case["case_id"]
        print(f"    [PASS] Found correlated case {case_id} for user 'analyst_bob'.")
        print(f"           Title: '{bob_case['title']}'")
        print(f"           Derived Severity: '{bob_case['severity']}'")
        print(f"           Status: '{bob_case['status']}'")
        print(f"           Evidence Counts: {bob_case.get('finding_count')} findings, {bob_case.get('event_count')} events")

        assert bob_case["severity"] == "High", f"Expected severity High, got {bob_case['severity']}"
        assert bob_case["correlation_key_type"] == "user_principal"
        assert bob_case["finding_count"] >= 3  # AUTH-001, AUTH-002, PRIV-001

        # Check IP correlation isolation: IP 203.0.113.77 must NOT be correlated with bob or grouped into an IP case by default
        ip_cases = [c for c in cases if c.get("correlation_key_type") == "source_ip"]
        assert len(ip_cases) == 0, "IP correlation was disabled by default but IP-based case was created"
        print("    [PASS] Verified IP-only grouping is disabled by default: 0 source_ip cases created.")

        # STEP 6: Inspect Detailed Case & Timeline
        print("\n--> [Step 6] Inspecting case detail and unified timeline at /api/cases/{id}...")
        status, detail = request_json("GET", f"/api/cases/{case_id}")
        assert status == 200
        assert "timeline" in detail
        timeline = detail["timeline"]
        print(f"    [PASS] Case timeline contains {len(timeline)} items.")

        types_in_timeline = {item["item_type"] for item in timeline}
        print(f"    [PASS] Timeline item types present: {', '.join(sorted(types_in_timeline))}")
        assert "finding" in types_in_timeline
        assert "event" in types_in_timeline
        assert "correlation" in types_in_timeline

        # Check rationale explanation
        assert "correlation_rationale" in detail
        print(f"    [PASS] Correlation Rationale: {detail['correlation_rationale'][:100]}...")

        # STEP 7: Analyst Review Workflow & State Transitions
        print("\n--> [Step 7] Testing analyst review workflow and audit logging...")
        # 7a. Transition Open -> UnderReview with note
        status, review_res1 = request_json("POST", f"/api/cases/{case_id}/review", {
            "action": "status_change",
            "to_status": "UnderReview",
            "note": "Analyst triage: Investigating multi-stage credential burst followed by admin role assignment.",
            "operator": "analyst_alice",
        })
        assert status == 200
        assert review_res1["case"]["status"] == "UnderReview"
        print("    [PASS] Transitioned Open -> UnderReview with operator note.")

        # 7b. Add standalone analyst note
        status, note_res = request_json("POST", f"/api/cases/{case_id}/review", {
            "action": "note",
            "note": "Identity confirmed as compromised staging test account.",
            "operator": "analyst_alice",
        })
        assert status == 200
        print("    [PASS] Added standalone analyst note.")

        # 7c. Transition UnderReview -> Resolved
        status, review_res2 = request_json("POST", f"/api/cases/{case_id}/review", {
            "action": "status_change",
            "to_status": "Resolved",
            "note": "Credentials revoked and test role cleared.",
            "operator": "lead_secops",
        })
        assert status == 200
        assert review_res2["case"]["status"] == "Resolved"
        print("    [PASS] Transitioned UnderReview -> Resolved.")

        # 7d. Verify review actions appear in timeline
        status, detail_after_review = request_json("GET", f"/api/cases/{case_id}")
        assert status == 200
        assert len(detail_after_review["review_actions"]) == 3
        print(f"    [PASS] Case detail shows {len(detail_after_review['review_actions'])} append-only review actions.")

        # STEP 8: Direct SQLite Database Verification
        print("\n--> [Step 8] Auditing SQLite schema, relations, and foreign keys directly...")
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Check cases count
        cur.execute("SELECT COUNT(*) FROM cases;")
        db_case_count = cur.fetchone()[0]
        assert db_case_count >= 1
        print(f"    [PASS] SQLite 'cases' table contains {db_case_count} records.")

        # Check case_findings
        cur.execute("SELECT COUNT(*) FROM case_findings WHERE case_id = ?;", (case_id,))
        case_findings_count = cur.fetchone()[0]
        assert case_findings_count >= 3
        print(f"    [PASS] SQLite 'case_findings' contains {case_findings_count} links for case {case_id}.")

        # Check case_events
        cur.execute("SELECT COUNT(*) FROM case_events WHERE case_id = ?;", (case_id,))
        case_events_count = cur.fetchone()[0]
        assert case_events_count >= 5
        print(f"    [PASS] SQLite 'case_events' contains {case_events_count} direct event links for case {case_id}.")

        # Check review_actions
        cur.execute("SELECT COUNT(*) FROM review_actions WHERE case_id = ?;", (case_id,))
        review_count = cur.fetchone()[0]
        assert review_count == 3
        print(f"    [PASS] SQLite 'review_actions' contains {review_count} audit records.")

        # Check foreign keys
        cur.execute("PRAGMA foreign_key_check;")
        fk_errors = cur.fetchall()
        assert len(fk_errors) == 0, f"Foreign key errors: {fk_errors}"
        print("    [PASS] SQLite PRAGMA foreign_key_check passed with 0 violations!")

        conn.close()

        # STEP 9: Re-evaluation Idempotency
        print("\n--> [Step 9] Testing correlation engine idempotency...")
        status, corr_res2 = request_json("POST", "/api/cases/correlate", {"window_seconds": 3600})
        assert status == 200
        corr_stats2 = corr_res2["result"]
        print(f"    [PASS] Second correlation: {corr_stats2['cases_created']} new cases created, "
              f"{corr_stats2['cases_updated']} cases updated.")
        assert corr_stats2["cases_created"] == 0
        assert corr_stats2["cases_updated"] >= 1

        # Verify status 'Resolved' and notes were not lost
        status, final_detail = request_json("GET", f"/api/cases/{case_id}")
        assert status == 200
        assert final_detail["status"] == "Resolved"
        assert len(final_detail["review_actions"]) == 3
        print("    [PASS] Analyst status ('Resolved') and 3 review actions preserved without duplication.")

        # STEP 10: Case Stats API
        print("\n--> [Step 10] Testing /api/cases/stats endpoint...")
        status, stats_data = request_json("GET", "/api/cases/stats")
        assert status == 200
        print(f"    [PASS] Stats response: Total={stats_data['total']}, ByStatus={stats_data['by_status']}, BySeverity={stats_data['by_severity']}")
        assert stats_data["by_status"].get("Resolved", 0) >= 1

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

    print("\n" + "=" * 70)
    print(" ALL REAL CASE WORKFLOW VERIFICATION CHECKS PASSED!")
    print("=" * 70)


if __name__ == "__main__":
    main()
