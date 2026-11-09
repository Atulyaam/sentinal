"""Integration tests for Phase 8 Production API, Demo Mode, Readiness, and Static Asset Serving."""
from __future__ import annotations

import gc
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Dict, Optional
import unittest
import urllib.error
import urllib.request

from backend.api import handler
from backend.api.server import create_server
from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository


class TestProductionAPI(unittest.TestCase):
    """Integration test suite for production endpoints, demo mode enforcement, and static serving."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = str(Path(cls.temp_dir.name) / "test_production.db")
        cls.static_dir = str(Path(cls.temp_dir.name) / "dist")
        os.makedirs(cls.static_dir, exist_ok=True)
        os.makedirs(os.path.join(cls.static_dir, "assets"), exist_ok=True)

        # Create mock index.html and sample js asset
        cls.index_content = "<html><head><title>Project Sentinel Production</title></head><body>Sentinel App</body></html>"
        with open(os.path.join(cls.static_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(cls.index_content)

        cls.js_content = "console.log('Sentinel Asset Loaded');"
        with open(os.path.join(cls.static_dir, "assets", "sample.js"), "w", encoding="utf-8") as f:
            f.write(cls.js_content)

        # Save ambient environment before test configuration
        cls._saved_env = {}
        for key in (
            "SENTINEL_DB_PATH",
            "SENTINEL_ENV",
            "SENTINEL_DEMO_MODE",
            "SENTINEL_DEMO_SEED",
            "SENTINEL_STATIC_DIR",
            "SENTINEL_RATE_LIMIT_PER_MINUTE",
        ):
            if key in os.environ:
                cls._saved_env[key] = os.environ[key]

        # Set environment variables for production demo mode
        os.environ["SENTINEL_DB_PATH"] = cls.db_path
        os.environ["SENTINEL_ENV"] = "production"
        os.environ["SENTINEL_DEMO_MODE"] = "true"
        os.environ["SENTINEL_DEMO_SEED"] = "false"  # Explicitly controlled in test
        os.environ["SENTINEL_STATIC_DIR"] = cls.static_dir
        os.environ["SENTINEL_RATE_LIMIT_PER_MINUTE"] = "5"

        # Reset handler singletons
        handler._repo = None
        handler._engine = None
        handler._norm_engine = None
        handler._detection_engine = None
        handler._correlation_engine = None
        handler._claim_engine = None
        handler._replay_engine = None
        handler._rate_limiter = handler.RateLimiter(limit_per_minute=5)

        cls.conn = get_connection(cls.db_path)
        apply_migrations(cls.conn)
        cls.repo = IngestionRepository(cls.conn)

        # Start Server on dynamic port
        cls.server = create_server(host="127.0.0.1", port=0)
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        if handler._repo and handler._repo.conn:
            try:
                handler._repo.conn.close()
            except Exception:
                pass
            handler._repo = None
        try:
            cls.conn.close()
        except Exception:
            pass
        gc.collect()
        time.sleep(0.1)
        cls.temp_dir.cleanup()

        # Restore ambient environment
        for key in (
            "SENTINEL_DB_PATH",
            "SENTINEL_ENV",
            "SENTINEL_DEMO_MODE",
            "SENTINEL_DEMO_SEED",
            "SENTINEL_STATIC_DIR",
            "SENTINEL_RATE_LIMIT_PER_MINUTE",
        ):
            if key in cls._saved_env:
                os.environ[key] = cls._saved_env[key]
            elif key in os.environ:
                del os.environ[key]

        # Reset handler rate limiter to clean defaults
        handler._rate_limiter = handler.RateLimiter(limit_per_minute=60)

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        raw_body: Optional[bytes] = None,
        content_type: str = "application/json",
        headers: Optional[Dict[str, str]] = None,
    ) -> tuple[int, Any, Dict[str, str]]:
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
            with urllib.request.urlopen(req, timeout=5.0) as resp:
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

    def test_health_and_readiness_endpoints(self) -> None:
        """Health & Readiness endpoints report 200 OK with demo_mode and database status."""
        status, health_data, _ = self._request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(health_data["status"], "ok")
        self.assertTrue(health_data["demo_mode"])

        status, ready_data, _ = self._request("GET", "/ready")
        self.assertEqual(status, 200)
        self.assertEqual(ready_data["status"], "ready")
        self.assertEqual(ready_data["database"], "connected")
        self.assertTrue(ready_data["demo_mode"])

    def test_static_asset_serving_and_spa_fallback(self) -> None:
        """Root and client paths serve index.html with security headers, assets serve with proper MIME."""
        # 1. Root /
        status, html_body, headers = self._request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("Project Sentinel Production", str(html_body))
        self.assertEqual(headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")

        # 2. Client-side route /?view=overview
        status, html_body, _ = self._request("GET", "/?view=overview")
        self.assertEqual(status, 200)
        self.assertIn("Project Sentinel Production", str(html_body))

        # 3. Static asset /assets/sample.js
        status, js_body, headers = self._request("GET", "/assets/sample.js")
        self.assertEqual(status, 200)
        self.assertIn("Sentinel Asset Loaded", str(js_body))
        self.assertIn("javascript", headers.get("Content-Type", "").lower())

        # 4. Unregistered API path returns 404 JSON, NOT index.html
        status, not_found_data, _ = self._request("GET", "/api/phantom_endpoint")
        self.assertEqual(status, 404)
        self.assertEqual(not_found_data["error"], "Not Found")

    def test_demo_mode_blocks_operational_import(self) -> None:
        """POST /api/import is strictly blocked with 403 Forbidden in Demo Mode."""
        dummy_csv = b"timestamp,user,ip,action,status\n2026-11-09T08:00:00Z,attacker,1.1.1.1,login,failure\n"
        status, err_data, _ = self._request(
            "POST",
            "/api/import",
            raw_body=dummy_csv,
            content_type="text/csv",
            headers={"Content-Length": str(len(dummy_csv))},
        )
        self.assertEqual(status, 403)
        self.assertEqual(err_data["error"], "Forbidden")
        self.assertIn("Public Demo Mode Active", err_data["message"])

    def test_rate_limiting_enforcement(self) -> None:
        """Exceeding configured requests in a minute on /api/replay/run triggers 429 Too Many Requests."""
        test_ip = "198.51.100.99"
        # Configured limit in setUpClass is 5
        for i in range(5):
            s, _, _ = self._request(
                "POST",
                "/api/replay/run",
                payload={"scenario_id": "SCN-AUTH-BURST"},
                headers={"X-Forwarded-For": test_ip},
            )
            self.assertEqual(s, 200, f"Request {i+1} failed with status {s}")

        # 6th request from same IP must be rejected with 429
        s_exceeded, data_exceeded, _ = self._request(
            "POST",
            "/api/replay/run",
            payload={"scenario_id": "SCN-AUTH-BURST"},
            headers={"X-Forwarded-For": test_ip},
        )
        self.assertEqual(s_exceeded, 429)
        self.assertEqual(data_exceeded["error"], "Too Many Requests")
        self.assertIn("Rate limit exceeded", data_exceeded["message"])


if __name__ == "__main__":
    unittest.main()
