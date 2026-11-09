"""Unit tests for Phase 8 Production Configuration & Rate Limiting."""
from __future__ import annotations

import os
import time
import unittest
from unittest.mock import patch

from backend.api.handler import RateLimiter
from backend.config.settings import Settings, get_settings, resolve_static_dir


class TestProductionConfig(unittest.TestCase):
    """Test production settings resolution, demo mode defaults, and rate limiting."""

    def test_port_env_precedence(self) -> None:
        """PaaS standard $PORT takes precedence over SENTINEL_PORT."""
        with patch.dict(os.environ, {"PORT": "9000", "SENTINEL_PORT": "8000"}):
            settings = get_settings()
            self.assertEqual(settings.port, 9000)

    def test_production_env_defaults_to_demo_mode(self) -> None:
        """In production environment without explicit override, demo_mode defaults to True."""
        env_vars = {"SENTINEL_ENV": "production"}
        # Remove SENTINEL_DEMO_MODE if present in ambient environment
        with patch.dict(os.environ, env_vars, clear=False):
            if "SENTINEL_DEMO_MODE" in os.environ:
                del os.environ["SENTINEL_DEMO_MODE"]
            settings = get_settings()
            self.assertTrue(settings.demo_mode)
            self.assertEqual(settings.host, "0.0.0.0")

    def test_explicit_demo_mode_toggle(self) -> None:
        """Explicit SENTINEL_DEMO_MODE controls demo_mode regardless of environment."""
        with patch.dict(os.environ, {"SENTINEL_ENV": "development", "SENTINEL_DEMO_MODE": "true"}):
            settings = get_settings()
            self.assertTrue(settings.demo_mode)

        with patch.dict(os.environ, {"SENTINEL_ENV": "production", "SENTINEL_DEMO_MODE": "false"}):
            settings = get_settings()
            self.assertFalse(settings.demo_mode)

    def test_rate_limiter_rolling_window(self) -> None:
        """RateLimiter permits up to limit and rejects requests exceeding limit in 60s window."""
        limiter = RateLimiter(limit_per_minute=3)
        client_ip = "192.0.2.1"

        # First 3 requests allowed
        self.assertTrue(limiter.is_allowed(client_ip))
        self.assertTrue(limiter.is_allowed(client_ip))
        self.assertTrue(limiter.is_allowed(client_ip))

        # 4th request within same minute rejected
        self.assertFalse(limiter.is_allowed(client_ip))

        # Different client IP is tracked independently
        other_ip = "192.0.2.2"
        self.assertTrue(limiter.is_allowed(other_ip))


if __name__ == "__main__":
    unittest.main()

