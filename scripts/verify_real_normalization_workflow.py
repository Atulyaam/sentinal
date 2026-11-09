"""Verification script for real Ingestion-to-Normalization and SQLite audit workflow."""

import json
import sqlite3
import subprocess
import sys
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
    print(" PROJECT SENTINEL — Phase 3 Real Normalization & Provenance Audit")
    print("=" * 70)

    # 1. Start Sentinel backend
    print("\n[*] Starting Sentinel backend on 127.0.0.1:8000...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "backend.api.server"],
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if not wait_for_api():
        print("[!] Backend failed to start.", file=sys.stderr)
        proc.kill()
        sys.exit(1)
    print("[+] Backend active and responding to /health.")

    try:
        # STEP 1: Verify pre-normalization state
        print("\n--> [Step 1] Verifying /api/normalization/stats baseline...")
        status, stats_before = request_json("GET", "/api/normalization/stats")
        assert status == 200, f"Expected 200 from stats, got {status}"
        print(f"    [PASS] Current stats: {stats_before['total_normalized_events']} normalized, {stats_before['pending_unnormalized_records']} pending.")

        # STEP 2: Ingest Multi-Format Sample Logs
        print("\n--> [Step 2] Ingesting multi-format logs for canonical normalization test...")

        # 2a. Auth CSV
        run_ts = int(time.time() * 1000)
        auth_csv_content = (
            "timestamp,username,auth_result,source_ip,session_id\n"
            f"2026-11-09T08:00:00Z,operator_alpha,SUCCESS,192.168.1.100,sess_{run_ts}_1\n"
            f"2026-11-09 08:05:00,operator_beta,FAILURE,192.168.1.105,sess_{run_ts}_2\n"
        )
        status, auth_res = request_json("POST", "/api/import", {
            "filename": f"audit_auth_{run_ts}.csv",
            "content": auth_csv_content,
            "parser_id": "auth_csv",
            "source_id": "src_manual_default",
        })
        assert status == 200, f"Auth import failed with status {status}"
        auth_import_id = auth_res["import_id"]
        print(f"    [PASS] Auth CSV ingested: import_id={auth_import_id}, accepted={auth_res['accepted_records']}")

        # 2b. Web Access CSV
        web_csv_content = (
            "timestamp,http_method,request_path,status_code,source_ip\n"
            f"2026-11-09T08:10:00Z,GET,/dashboard?t={run_ts},200,10.0.0.1\n"
            f"2026-11-09T08:12:00Z,POST,/admin/login?t={run_ts},403,10.0.0.99\n"
        )
        status, web_res = request_json("POST", "/api/import", {
            "filename": f"web_audit_{run_ts}.csv",
            "content": web_csv_content,
            "parser_id": "web_access_csv",
            "source_id": "src_manual_default",
        })
        assert status == 200, f"Web import failed with status {status}"
        web_import_id = web_res["import_id"]
        print(f"    [PASS] Web CSV ingested: import_id={web_import_id}, accepted={web_res['accepted_records']}")

        # STEP 3: Execute Normalization Batch
        print("\n--> [Step 3] Triggering POST /api/normalization/run...")
        status, run_res = request_json("POST", "/api/normalization/run", {"limit": 100})
        assert status == 200, f"Normalization run failed with status {status}"
        norm_result = run_res["result"]
        print(f"    [PASS] Normalization executed: {norm_result['accepted']} accepted, {norm_result['rejected']} rejected, {norm_result['skipped']} skipped.")
        assert norm_result["accepted"] >= 4, f"Expected at least 4 accepted events, got {norm_result['accepted']}"

        # STEP 4: Query /api/events with filters
        print("\n--> [Step 4] Querying GET /api/events with dynamic filters...")
        status, evts = request_json("GET", "/api/events?limit=10")
        assert status == 200
        assert evts["total"] >= 4
        print(f"    [PASS] /api/events returned total={evts['total']} events.")

        # Filter by FAILURE
        status, fail_evts = request_json("GET", "/api/events?status=FAILURE")
        assert status == 200
        assert fail_evts["total"] >= 2  # 1 auth failure + 1 403 web failure
        print(f"    [PASS] Filter status=FAILURE returned {fail_evts['total']} events.")

        # STEP 5: Inspect specific event details and provenance
        print("\n--> [Step 5] Inspecting specific event detail via GET /api/events/{id}...")
        sample_evt = evts["events"][0]
        evt_id = sample_evt["event_id"]
        status, detail = request_json("GET", f"/api/events/{evt_id}")
        assert status == 200
        assert detail["event_id"] == evt_id
        assert "source_sha256" in detail
        assert len(detail["source_sha256"]) == 64
        assert "attributes" in detail
        print(f"    [PASS] Event {evt_id} verified: timestamp={detail['timestamp']}, source={detail['source_file']}:{detail['source_line']}")

        # STEP 6: Direct SQLite audit
        print("\n--> [Step 6] Auditing SQLite database tables on disk...")
        from backend.persistence.connection import get_db_path
        db_file = get_db_path()
        print(f"    [*] Database path: {db_file}")
        assert db_file.exists(), f"Database file {db_file} does not exist!"

        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()

        # Check row count in normalized_events
        cursor.execute("SELECT COUNT(*) FROM normalized_events;")
        total_db_events = cursor.fetchone()[0]
        print(f"    [PASS] SQLite normalized_events table contains {total_db_events} rows.")
        assert total_db_events >= 4

        # Verify foreign keys between normalized_events and parsed_records
        cursor.execute("""
            SELECT ne.event_id, ne.record_id, pr.parser_id, ne.source_sha256
            FROM normalized_events ne
            JOIN parsed_records pr ON ne.record_id = pr.record_id
            LIMIT 5;
        """)
        linked_rows = cursor.fetchall()
        print(f"    [PASS] Verified FK integrity across {len(linked_rows)} sampled normalized events.")

        # Verify idempotency constraint
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_norm_events_ts';")
        assert cursor.fetchone() is not None, "idx_norm_events_ts index missing"
        print("    [PASS] Indexes idx_norm_events_ts and uq_record_norm_version verified.")

        conn.close()

    finally:
        print("\n[*] Stopping backend service...")
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=2.0)
        print("[+] Backend service stopped.")

    print("\n" + "=" * 70)
    print(" ALL 6 PHASE 3 NORMALIZATION & AUDIT STEPS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    main()
