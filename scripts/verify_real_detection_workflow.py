"""Verification script for real Ingestion-to-Detection and SQLite audit workflow."""
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
    print(" PROJECT SENTINEL — Phase 4 Real Detection & Findings Workflow Audit")
    print("=" * 70)

    temp_dir = tempfile.TemporaryDirectory()
    db_path = Path(temp_dir.name) / "sentinel_audit.db"
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
        # STEP 1: Baseline rules check
        print("\n--> [Step 1] Checking registered detection rules...")
        status, rules_data = request_json("GET", "/api/rules")
        assert status == 200, f"Expected 200 from /api/rules, got {status}"
        assert len(rules_data["rules"]) == 5, f"Expected 5 rules, got {len(rules_data['rules'])}"
        rule_ids = [r["rule_id"] for r in rules_data["rules"]]
        print(f"    [PASS] Registered rules: {', '.join(rule_ids)}")

        # STEP 2: Ingest Multi-Format Logs
        print("\n--> [Step 2] Ingesting multi-format test logs for detection evaluation...")
        run_ts = int(time.time() * 1000)

        # 2a. Auth CSV with 5 failures + 1 success for victim_user
        auth_csv = (
            "timestamp,username,auth_result,source_ip,session_id\n"
            f"2026-11-09T09:00:00Z,target_secops,FAILURE,198.51.100.88,sess_{run_ts}_1\n"
            f"2026-11-09T09:01:00Z,target_secops,FAILURE,198.51.100.88,sess_{run_ts}_2\n"
            f"2026-11-09T09:02:00Z,target_secops,FAILURE,198.51.100.88,sess_{run_ts}_3\n"
            f"2026-11-09T09:03:00Z,target_secops,FAILURE,198.51.100.88,sess_{run_ts}_4\n"
            f"2026-11-09T09:04:00Z,target_secops,FAILURE,198.51.100.88,sess_{run_ts}_5\n"
            f"2026-11-09T09:06:00Z,target_secops,SUCCESS,198.51.100.88,sess_{run_ts}_6\n"
        )
        status, auth_res = request_json("POST", "/api/import", {
            "filename": f"auth_burst_{run_ts}.csv",
            "content": auth_csv,
            "parser_id": "auth_csv",
            "source_id": "src_manual_default",
        })
        assert status == 200 and auth_res["accepted_records"] == 6
        print(f"    [PASS] Auth CSV ingested: 6 records (5 failures, 1 success)")

        # 2b. Web Access CSV with 3 sensitive route hits from 203.0.113.88
        web_csv = (
            "timestamp,http_method,request_path,status_code,source_ip\n"
            f"2026-11-09T09:10:00Z,GET,/.env,404,203.0.113.88\n"
            f"2026-11-09T09:11:00Z,POST,/admin/login,401,203.0.113.88\n"
            f"2026-11-09T09:12:00Z,GET,/wp-admin/setup.php,404,203.0.113.88\n"
        )
        status, web_res = request_json("POST", "/api/import", {
            "filename": f"web_sensitive_{run_ts}.csv",
            "content": web_csv,
            "parser_id": "web_access_csv",
            "source_id": "src_manual_default",
        })
        assert status == 200 and web_res["accepted_records"] == 3
        print(f"    [PASS] Web Access CSV ingested: 3 sensitive route requests")

        # 2c. JSONL with explicit role change event
        priv_jsonl = (
            f'{{"timestamp": "2026-11-09T09:20:00Z", "event_type": "role_changed", '
            f'"user_principal": "ciso_admin", "target_resource": "db_admin", '
            f'"attributes": {{"action": "grant_role", "subject": "analyst_temp"}}}}\n'
        )
        status, priv_res = request_json("POST", "/api/import", {
            "filename": f"priv_event_{run_ts}.jsonl",
            "content": priv_jsonl,
            "parser_id": "generic_jsonl",
            "source_id": "src_manual_default",
        })
        assert status == 200 and priv_res["accepted_records"] == 1
        print(f"    [PASS] Privilege JSONL ingested: 1 role_changed event")

        # STEP 3: Run Normalization
        print("\n--> [Step 3] Running Canonical Normalization Engine...")
        status, norm_res = request_json("POST", "/api/normalization/run", {})
        assert status == 200
        print(f"    [PASS] Normalization complete: {norm_res['result']['accepted']} canonical events accepted.")

        # STEP 4: Run Detection Engine
        print("\n--> [Step 4] Running Deterministic Detection Engine...")
        status, det_res = request_json("POST", "/api/detection/run", {})
        assert status == 200 and det_res["status"] == "success"
        stats = det_res["result"]
        print(f"    [PASS] Detection run {stats['evaluation_id']}: {stats['rule_count']} rules evaluated, "
              f"{stats['events_scanned']} events scanned, {stats['findings_generated']} new findings generated in {stats['duration_ms']:.2f}ms.")
        assert stats["findings_generated"] >= 4, f"Expected at least 4 findings, got {stats['findings_generated']}"

        # STEP 5: Verify Findings through API
        print("\n--> [Step 5] Querying /api/findings to inspect generated detections...")
        status, findings_data = request_json("GET", "/api/findings")
        assert status == 200
        findings = findings_data["findings"]
        generated_rules = {f["rule_id"] for f in findings}
        print(f"    [PASS] Retrieved {findings_data['total']} total findings from API.")
        print(f"    [PASS] Rules represented in findings: {', '.join(sorted(generated_rules))}")

        assert "AUTH-001" in generated_rules, "Missing AUTH-001 finding"
        assert "AUTH-002" in generated_rules, "Missing AUTH-002 finding"
        assert "WEB-001" in generated_rules, "Missing WEB-001 finding"
        assert "PRIV-001" in generated_rules, "Missing PRIV-001 finding"

        # Check detail and evidence linkage
        auth001 = next(f for f in findings if f["rule_id"] == "AUTH-001")
        status, detail = request_json("GET", f"/api/findings/{auth001['finding_id']}")
        assert status == 200
        assert len(detail["supporting_events"]) == 5
        print(f"    [PASS] AUTH-001 detail verified: {len(detail['supporting_events'])} linked evidence events with full provenance.")

        # STEP 6: Direct SQLite Database Verification
        print("\n--> [Step 6] Inspecting SQLite persistence directly on disk...")
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Check findings count
        cursor.execute("SELECT COUNT(*) FROM findings;")
        db_findings_count = cursor.fetchone()[0]
        assert db_findings_count >= 4
        print(f"    [PASS] SQLite 'findings' table contains {db_findings_count} records.")

        # Check junction table
        cursor.execute("SELECT COUNT(*) FROM finding_events;")
        db_junction_count = cursor.fetchone()[0]
        assert db_junction_count >= 10
        print(f"    [PASS] SQLite 'finding_events' junction table contains {db_junction_count} relational evidence links.")

        # Check foreign keys
        cursor.execute("PRAGMA foreign_key_check;")
        fk_errors = cursor.fetchall()
        assert len(fk_errors) == 0, f"Foreign key errors detected: {fk_errors}"
        print("    [PASS] SQLite PRAGMA foreign_key_check passed with 0 violations!")

        conn.close()

        # STEP 7: Lifecycle Status Update
        print("\n--> [Step 7] Updating finding status to 'acknowledged'...")
        status, patch_res = request_json("PATCH", f"/api/findings/{auth001['finding_id']}", {"status": "acknowledged"})
        assert status == 200
        assert patch_res["status"] == "acknowledged"
        print(f"    [PASS] Status updated to '{patch_res['status']}' successfully.")

        # STEP 8: Idempotency & Deduplication
        print("\n--> [Step 8] Testing engine re-evaluation idempotency...")
        status, det_res2 = request_json("POST", "/api/detection/run", {})
        assert status == 200
        stats2 = det_res2["result"]
        print(f"    [PASS] Second run: {stats2['findings_generated']} new, {stats2['findings_duplicate']} duplicate suppressed.")
        assert stats2["findings_generated"] == 0
        assert stats2["findings_duplicate"] >= 4

        # Verify acknowledged status was preserved
        status, detail_final = request_json("GET", f"/api/findings/{auth001['finding_id']}")
        assert status == 200
        assert detail_final["status"] == "acknowledged"
        print(f"    [PASS] Acknowledged finding status safely preserved under re-evaluation.")

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
    print(" ALL REAL DETECTION WORKFLOW VERIFICATION CHECKS PASSED!")
    print("=" * 70)


if __name__ == "__main__":
    main()
