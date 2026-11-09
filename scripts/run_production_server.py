"""Project Sentinel — Production Server Runner.

Builds the frontend if needed, enables Public Demo Mode, and launches the
unified single-container HTTP service serving both the React UI and Python API.

Usage:
    python scripts/run_production_server.py [--port 8000] [--host 0.0.0.0]
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


def ensure_frontend_built(repo_root: Path) -> Path:
    dist_dir = repo_root / "apps" / "crew-app" / "dist"
    index_file = dist_dir / "index.html"
    if not index_file.is_file():
        print("[*] Frontend production build not found. Building with npm...")
        subprocess.run(
            ["npm", "run", "build", "--prefix", "apps/crew-app"],
            cwd=str(repo_root),
            check=True,
            shell=True if sys.platform == "win32" else False,
        )
    return dist_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Start Project Sentinel Production Server")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")), help="Port to listen on")
    parser.add_argument("--host", default=os.getenv("SENTINEL_HOST", "0.0.0.0"), help="Host interface to bind")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    dist_dir = ensure_frontend_built(repo_root)

    # Set environment variables for production demo mode
    os.environ["SENTINEL_ENV"] = "production"
    os.environ["SENTINEL_DEMO_MODE"] = "true"
    os.environ["SENTINEL_DEMO_SEED"] = "true"
    os.environ["SENTINEL_STATIC_DIR"] = str(dist_dir)
    os.environ["PORT"] = str(args.port)
    os.environ["SENTINEL_PORT"] = str(args.port)
    os.environ["SENTINEL_HOST"] = args.host

    # Add repo root to sys.path
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from backend.api.server import run_server
    print("=" * 80)
    print(f" PROJECT SENTINEL — PRODUCTION DEMO SERVER")
    print(f" Host: http://{args.host}:{args.port}")
    print(f" Static Assets: {dist_dir}")
    print(f" Mode: Public Demo (Synthetic Only)")
    print("=" * 80)
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()

