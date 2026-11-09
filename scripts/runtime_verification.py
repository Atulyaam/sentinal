"""Runtime verification script executing full headless browser and connectivity tests."""

import json
import os
import subprocess
import sys
import time
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading

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
    raise RuntimeError("No Chromium-based browser (Chrome/Edge) found on system.")


def wait_for_url(url: str, timeout: float = 5.0) -> bool:
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
    """Run headless Chromium and dump the rendered DOM after JavaScript execution."""
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


def main() -> None:
    print("=" * 70)
    print(" PROJECT SENTINEL — Phase 3 Runtime Verification")
    print("=" * 70)

    browser_exe = find_browser()
    print(f"[+] Found Browser for Runtime Verification: {browser_exe}")

    if not (DIST_DIR / "index.html").exists():
        print(f"[!] dist/index.html not found at {DIST_DIR}. Building...", file=sys.stderr)
        subprocess.run(["npm", "run", "build"], cwd=str(ROOT_DIR / "apps" / "crew-app"), check=True)

    # 1. Start Static Preview Server on port 4173 in a background thread
    print("[*] Starting production preview server on 127.0.0.1:4173...")
    handler = partial(SimpleHTTPRequestHandler, directory=str(DIST_DIR))
    preview_server = ThreadingHTTPServer(("127.0.0.1", 4173), handler)
    preview_thread = threading.Thread(target=preview_server.serve_forever, daemon=True)
    preview_thread.start()

    if not wait_for_url("http://127.0.0.1:4173/index.html"):
        print("[!] Preview server failed to start.", file=sys.stderr)
        sys.exit(1)
    print("[+] Production preview server is ACTIVE on http://127.0.0.1:4173")

    # 2. Start Backend Server on port 8000
    print("[*] Starting Backend service on 127.0.0.1:8000...")
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "backend.api.server"],
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if not wait_for_url("http://127.0.0.1:8000/health"):
        print("[!] Backend service failed to start.", file=sys.stderr)
        backend_proc.kill()
        preview_server.shutdown()
        sys.exit(1)
    print("[+] Backend service is ACTIVE on http://127.0.0.1:8000")

    try:
        # STEP 1: Verify Initial Render & Backend Connected State
        print("\n--> [Test 1/5] Verifying Initial UI Render and Backend Connectivity...")
        dom = run_headless_browser(browser_exe, "http://127.0.0.1:4173/?view=overview")

        assert "Project Sentinel" in dom, "Project Sentinel header missing from DOM"
        assert "Welcome to Project Sentinel" in dom, "Welcome banner missing from DOM"
        assert "No Active Investigations" in dom, "Empty state missing from DOM"
        assert "Backend Connected" in dom, f"Expected 'Backend Connected' in DOM. Got: {dom[:400]}"
        assert "Operational" in dom, "Expected 'Operational' status in DOM"
        print("    [PASS] DOM rendered successfully with active 'Backend Connected' state!")

        # STEP 2: Verify All 8 Navigation Routes
        print("\n--> [Test 2/5] Testing all 8 navigation routes in browser runtime...")
        routes_to_test = [
            ("overview", "Welcome to Project Sentinel"),
            ("investigations", "Investigations Module"),
            ("findings", "Findings Module"),
            ("events", "Canonical Events"),
            ("replay", "Replay Lab Module"),
            ("sources", "Data Ingestion"),
            ("digests", "Digests Module"),
            ("settings", "Settings Module"),
        ]

        for route_id, expected_text in routes_to_test:
            url = f"http://127.0.0.1:4173/?view={route_id}"
            route_dom = run_headless_browser(browser_exe, url)
            assert expected_text in route_dom, f"Route '{route_id}' failed: '{expected_text}' not found in DOM."
            print(f"    [PASS] Route '{route_id}' rendered: '{expected_text}' verified.")

        # STEP 3: Verify Events View Specific Components
        print("\n--> [Test 3/5] Verifying Events view interactive controls and canonical metrics...")
        events_dom = run_headless_browser(browser_exe, "http://127.0.0.1:4173/?view=events")
        assert "Canonical Events" in events_dom, "Expected 'Canonical Events' in Events view"
        assert "Total Normalized Events" in events_dom, "Expected 'Total Normalized Events' in Events view"
        assert "Run Normalization" in events_dom, "Expected 'Run Normalization' button in Events view"
        assert "Timestamp (UTC)" in events_dom, "Expected table headers in Events view"
        print("    [PASS] Events view verified: controls, metrics bar, and canonical table present.")

        # Verify Sources view specific components
        print("\n--> [Test 3b/5] Verifying Sources view interactive controls and genuine history...")
        sources_dom = run_headless_browser(browser_exe, "http://127.0.0.1:4173/?view=sources")
        assert "Configured Event Sources" in sources_dom, "Expected 'Configured Event Sources' in Sources view"
        assert "Manual Log Import" in sources_dom, "Expected 'Manual Log Import' in Sources view"
        assert "Persisted Import History" in sources_dom, "Expected 'Persisted Import History' in Sources view"
        print("    [PASS] Sources view verified: controls, event sources, and history table present.")

        # STEP 4: Verify Offline / Backend Disconnected State
        print("\n--> [Test 4/5] Testing Backend Disconnect and Offline Error State...")
        print("    [*] Stopping backend service...")
        backend_proc.terminate()
        backend_proc.wait(timeout=3.0)
        time.sleep(0.5)

        offline_dom = run_headless_browser(browser_exe, "http://127.0.0.1:4173/?view=overview")
        assert "Backend Unavailable" in offline_dom, "Expected 'Backend Unavailable' indicator in offline state."
        assert "Backend Engine Offline" in offline_dom, "Expected 'Backend Engine Offline' banner in offline state."
        assert "python -m backend.api.server" in offline_dom, "Expected recovery instruction in offline state."
        print("    [PASS] Offline state correctly displayed with 'Backend Unavailable' and recovery guidance!")

        # STEP 5: Verify Backend Recovery
        print("\n--> [Test 5/5] Testing Backend Restart and UI Recovery...")
        print("    [*] Restarting backend service...")
        backend_proc = subprocess.Popen(
            [sys.executable, "-m", "backend.api.server"],
            cwd=str(ROOT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if not wait_for_url("http://127.0.0.1:8000/health"):
            raise RuntimeError("Backend failed to restart.")

        recovered_dom = run_headless_browser(browser_exe, "http://127.0.0.1:4173/?view=overview")
        assert "Backend Connected" in recovered_dom, "Expected 'Backend Connected' to recover."
        print("    [PASS] Backend recovery confirmed: UI resumed 'Backend Connected' operational state!")

    finally:
        print("\n[*] Shutting down test processes cleanly...")
        if backend_proc.poll() is None:
            backend_proc.terminate()
            backend_proc.wait(timeout=2.0)
        preview_server.shutdown()
        preview_server.server_close()
        print("[+] All test servers stopped cleanly. Zero background processes remaining.")

    print("\n" + "=" * 70)
    print(" ALL RUNTIME VERIFICATION STEPS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    main()

