"""Launcher script to start both Project Sentinel backend service and UI preview."""

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def check_backend_alive(url: str = "http://127.0.0.1:8000/health") -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def main() -> None:
    print("=" * 60)
    print(" PROJECT SENTINEL — Phase 1 Demonstration Launcher")
    print("=" * 60)

    # 1. Start Backend in a subprocess
    backend_cmd = [sys.executable, "-m", "backend.api.server"]
    print(f"[*] Starting Backend service: {' '.join(backend_cmd)}")
    backend_proc = subprocess.Popen(
        backend_cmd,
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # Wait for backend to be alive
    print("[*] Waiting for backend to respond on http://127.0.0.1:8000/health ...")
    max_retries = 10
    alive = False
    for i in range(max_retries):
        if check_backend_alive():
            alive = True
            break
        time.sleep(0.5)

    if not alive:
        print("[!] Backend failed to start. Terminating.", file=sys.stderr)
        backend_proc.kill()
        sys.exit(1)

    print("[+] Backend is ACTIVE and responding to /health requests!")
    print("[*] Frontend can be launched via:")
    print("    cd apps/crew-app && npm run dev")
    print("[*] Press Ctrl+C to terminate the demonstration backend.")

    try:
        backend_proc.wait()
    except KeyboardInterrupt:
        print("\n[*] Shutting down backend service...")
        backend_proc.terminate()
        backend_proc.wait(timeout=2.0)
        print("[+] Terminated cleanly.")


if __name__ == "__main__":
    main()
