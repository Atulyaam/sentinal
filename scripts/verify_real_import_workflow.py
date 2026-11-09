"""End-to-End Real Ingestion Workflow and SQLite State Verification.

Executes the full 13-step verification sequence specified in Phase 2.5:
1. Start backend and frontend.
2. Select valid auth CSV.
3. Select auth_csv parser.
4. Import file via multipart upload.
5. Verify API response.
6. Query SQLite and confirm records.
7. Verify frontend history entry in Chrome DOM.
8. Re-import exact same file.
9. Verify duplicate skipping and unchanged DB records.
10. Import file containing malformed rows.
11. Verify accepted/rejected counts and error details.
12. Restart backend.
13. Verify history remains available in SQLite and UI.
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "apps" / "crew-app" / "dist"

CHROME_PATHS = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
]


def find_browser() -> Path:
    for p in CHROME_PATHS:
        if p.exists():
            return p
    raise RuntimeError("No Chromium browser found.")


def wait_for_url(url: str, timeout: float = 6.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as resp:
                if resp.status in (200, 204):
                    return True
        except Exception:
            time.sleep(0.1)
    return False


def run_headless_browser(browser_exe: Path, url: str) -> str:
    cmd = [
        str(browser_exe),
        "--headless=new",
        "--dump-dom",
        "--virtual-time-budget=4000",
        "--disable-gpu",
        "--no-sandbox",
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return proc.stdout


def send_multipart_import(base_url: str, filename: str, content: bytes, parser_id: str) -> dict:
    boundary = "----SentinelFormBoundary" + str(int(time.time() * 1000))
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="parser_id"\r\n\r\n'
        f"{parser_id}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/api/import",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    print("=" * 75)
    print(" PROJECT SENTINEL — Phase 2.5 Real Browser & SQLite Verification")
    print("=" * 75)

    browser_exe = find_browser()
    print(f"[+] Found Browser: {browser_exe}")

    temp_dir = tempfile.TemporaryDirectory()
    db_file = Path(temp_dir.name) / "live_audit.db"
    inbox_dir = Path(temp_dir.name) / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    os.environ["SENTINEL_DB_PATH"] = str(db_file)
    os.environ["SENTINEL_APPROVED_INBOX"] = str(inbox_dir)
    os.environ["SENTINEL_ALLOWED_ORIGINS"] = "http://127.0.0.1:4173,http://localhost:4173"

    # Step 1: Start frontend preview server and backend
    print("\n--> [Step 1/13] Starting Frontend Preview (127.0.0.1:4173) and Backend (127.0.0.1:8000)...")
    handler = partial(SimpleHTTPRequestHandler, directory=str(DIST_DIR))
    preview_server = ThreadingHTTPServer(("127.0.0.1", 4173), handler)
    preview_thread = threading.Thread(target=preview_server.serve_forever, daemon=True)
    preview_thread.start()

    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "backend.api.server"],
        cwd=str(ROOT_DIR),
        env=dict(os.environ),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if not wait_for_url("http://127.0.0.1:4173/index.html") or not wait_for_url("http://127.0.0.1:8000/health"):
        raise RuntimeError("Failed to start preview server or backend service.")
    print("    [PASS] Both servers are ACTIVE and reachable.")

    try:
        # Step 2 & 3: Prepare valid auth CSV
        print("\n--> [Step 2-3/13] Preparing valid authentication CSV with parser 'auth_csv'...")
        valid_csv_content = (
            b"timestamp,username,auth_result,source_ip,session_id\n"
            b"2026-11-09T09:40:01Z,secops_lead,SUCCESS,192.168.1.100,sess_111\n"
            b"2026-11-09T09:40:15Z,analyst_bob,FAILURE,192.168.1.105,sess_222\n"
        )
        test_filename = "auth_valid_audit.csv"
        print(f"    Payload size: {len(valid_csv_content)} bytes (2 records).")

        # Step 4 & 5: Import via API and verify response
        print("\n--> [Step 4-5/13] Importing file via POST /api/import and verifying response...")
        resp1 = send_multipart_import("http://127.0.0.1:8000", test_filename, valid_csv_content, "auth_csv")
        print(f"    API Response: status={resp1.get('status')}, duplicate={resp1.get('duplicate')}, accepted={resp1.get('accepted_records')}")
        assert resp1["status"] == "completed", f"Expected completed, got {resp1.get('status')}"
        assert resp1["duplicate"] is False, "Expected duplicate to be False"
        assert resp1["accepted_records"] == 2, f"Expected 2 accepted records, got {resp1.get('accepted_records')}"
        assert resp1["rejected_records"] == 0, "Expected 0 rejected records"
        import_id_1 = resp1["import_id"]
        sha256_1 = resp1["sha256"]
        print(f"    [PASS] API response verified: import_id={import_id_1}, sha256={sha256_1[:12]}...")

        # Step 6: Query SQLite directly to confirm records
        print("\n--> [Step 6/13] Querying SQLite database directly to verify persisted records...")
        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("SELECT * FROM import_jobs WHERE import_id = ?;", (import_id_1,))
        job_row = cur.fetchone()
        assert job_row is not None, f"Import job {import_id_1} not found in SQLite"
        assert job_row["status"] == "completed"
        assert job_row["total_records"] == 2
        assert job_row["accepted_records"] == 2
        assert job_row["rejected_records"] == 0

        cur.execute("SELECT count(*) FROM parsed_records WHERE import_id = ?;", (import_id_1,))
        rec_count = cur.fetchone()[0]
        assert rec_count == 2, f"Expected 2 records in parsed_records table, found {rec_count}"

        cur.execute("SELECT record_json FROM parsed_records WHERE import_id = ? ORDER BY record_number ASC;", (import_id_1,))
        rows = [json.loads(r[0]) for r in cur.fetchall()]
        assert rows[0]["attributes"]["username"] == "secops_lead"
        assert rows[0]["attributes"]["auth_result"] == "SUCCESS"
        assert rows[1]["attributes"]["username"] == "analyst_bob"
        assert rows[1]["attributes"]["auth_result"] == "FAILURE"
        conn.close()
        print(f"    [PASS] SQLite verified: 1 import_job ('completed') and 2 parsed_records confirmed!")

        # Step 7: Verify frontend history entry in Chrome DOM
        print("\n--> [Step 7/13] Verifying frontend Sources view in Headless Chrome DOM...")
        dom1 = run_headless_browser(browser_exe, "http://127.0.0.1:4173/?view=sources")
        assert test_filename in dom1, f"Filename '{test_filename}' not found in rendered DOM table."
        assert sha256_1[:12] in dom1, f"SHA-256 hash prefix '{sha256_1[:12]}' not found in DOM."
        assert "auth_csv" in dom1, "Parser profile 'auth_csv' not found in DOM."
        print(f"    [PASS] Chrome rendered history row with '{test_filename}', '{sha256_1[:12]}...', and 'auth_csv'!")

        # Step 8 & 9: Import exact same file again and verify idempotency
        print("\n--> [Step 8-9/13] Re-importing identical file to test SHA-256 deduplication...")
        resp2 = send_multipart_import("http://127.0.0.1:8000", test_filename, valid_csv_content, "auth_csv")
        assert resp2["status"] == "skipped", f"Expected 'skipped', got {resp2.get('status')}"
        assert resp2["duplicate"] is True, "Expected duplicate to be True"
        assert resp2["import_id"] == import_id_1, "Expected duplicate to reference original import_id"

        # Verify SQLite counts are strictly unchanged
        conn = sqlite3.connect(str(db_file))
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM import_jobs;")
        total_jobs = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM parsed_records;")
        total_records = cur.fetchone()[0]
        assert total_jobs == 1, f"Job count should still be 1, found {total_jobs}"
        assert total_records == 2, f"Record count should still be 2, found {total_records}"
        conn.close()
        print(f"    [PASS] Duplicate skipped: SQLite records strictly unchanged (1 job, 2 records).")

        # Step 10 & 11: Import file containing malformed rows
        print("\n--> [Step 10-11/13] Ingesting CSV with malformed rows to verify error diagnostics...")
        malformed_csv = (
            b"timestamp,username,auth_result,source_ip\n"
            b"2026-11-09T09:41:00Z,good_user,SUCCESS,192.168.1.50\n"
            b"2026-11-09T09:41:05Z,bad_user,INVALID_STATUS,192.168.1.51\n"
            b"2026-11-09T09:41:10Z,,SUCCESS,192.168.1.52\n"
        )
        malformed_fn = "auth_with_errors.csv"
        resp3 = send_multipart_import("http://127.0.0.1:8000", malformed_fn, malformed_csv, "auth_csv")
        assert resp3["status"] == "partial", f"Expected 'partial', got {resp3.get('status')}"
        assert resp3["total_records"] == 3
        assert resp3["accepted_records"] == 1
        assert resp3["rejected_records"] == 2
        import_id_3 = resp3["import_id"]

        # Check SQLite error records
        conn = sqlite3.connect(str(db_file))
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM import_errors WHERE import_id = ?;", (import_id_3,))
        error_count = cur.fetchone()[0]
        assert error_count == 2, f"Expected 2 error rows in SQLite, found {error_count}"

        cur.execute("SELECT record_number, safe_error_message FROM import_errors WHERE import_id = ? ORDER BY record_number ASC;", (import_id_3,))
        err_rows = cur.fetchall()
        assert err_rows[0][0] == 3  # line 3 is row 2 (INVALID_STATUS)
        assert "Invalid auth_result" in err_rows[0][1]
        assert err_rows[1][0] == 4  # line 4 is row 3 (missing username)
        assert "Missing required username" in err_rows[1][1]
        conn.close()
        print(f"    [PASS] Partial import verified: 1 accepted, 2 rejected rows with line attribution in SQLite!")

        # Step 12 & 13: Restart backend and verify history persistence
        print("\n--> [Step 12-13/13] Restarting backend service and verifying history retention...")
        backend_proc.terminate()
        backend_proc.wait(timeout=3.0)
        time.sleep(0.5)

        backend_proc = subprocess.Popen(
            [sys.executable, "-m", "backend.api.server"],
            cwd=str(ROOT_DIR),
            env=dict(os.environ),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if not wait_for_url("http://127.0.0.1:8000/health"):
            raise RuntimeError("Backend failed to restart.")

        # Verify API returns both jobs after restart
        req = urllib.request.Request("http://127.0.0.1:8000/api/imports")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert len(data["imports"]) == 2, f"Expected 2 historical jobs after restart, got {len(data['imports'])}"

        # Verify Chrome renders both historical jobs
        dom2 = run_headless_browser(browser_exe, "http://127.0.0.1:4173/?view=sources")
        assert test_filename in dom2, "First job missing from rendered UI after restart"
        assert malformed_fn in dom2, "Second job missing from rendered UI after restart"
        assert "Total Jobs: 2" in dom2, "Header job count missing from UI"
        print(f"    [PASS] Restart verified: both jobs persisted and rendered in Chrome DOM!")

    finally:
        print("\n[*] Shutting down test processes cleanly...")
        if backend_proc.poll() is None:
            backend_proc.terminate()
            backend_proc.wait(timeout=2.0)
        preview_server.shutdown()
        preview_server.server_close()
        temp_dir.cleanup()
        print("[+] Teardown complete. All test processes terminated.")

    print("\n" + "=" * 75)
    print(" ALL 13 REAL WORKFLOW & SQLITE VERIFICATION STEPS PASSED 100%!")
    print("=" * 75)


if __name__ == "__main__":
    main()

