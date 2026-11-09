"""Unit tests for Sentinel Configuration and Environment loading."""

import os
import unittest
from backend.config.settings import DEFAULT_ALLOWED_ORIGINS, get_settings


class TestSettings(unittest.TestCase):
    """Test configuration defaults and environment overrides."""

    def test_default_settings(self) -> None:
        """Verify default configuration values."""
        # Ensure clean environment for keys
        saved_env = {}
        keys = [
            "SENTINEL_APP_NAME",
            "SENTINEL_VERSION",
            "SENTINEL_HOST",
            "SENTINEL_PORT",
            "SENTINEL_ENV",
            "SENTINEL_ALLOWED_ORIGINS",
        ]
        for k in keys:
            if k in os.environ:
                saved_env[k] = os.environ.pop(k)

        try:
            settings = get_settings()
            self.assertEqual(settings.app_name, "Project Sentinel")
            self.assertEqual(settings.version, "0.2.0")
            self.assertEqual(settings.host, "127.0.0.1")
            self.assertEqual(settings.port, 8000)
            self.assertEqual(settings.environment, "development")
            self.assertEqual(settings.approved_inbox, "./inbox")
            self.assertEqual(settings.allowed_origins, DEFAULT_ALLOWED_ORIGINS)
            self.assertGreater(settings.max_import_size_bytes, 0)
            self.assertGreater(settings.max_records_per_file, 0)
        finally:
            os.environ.update(saved_env)

    def test_env_override(self) -> None:
        """Verify that environment variables cleanly override defaults."""
        os.environ["SENTINEL_PORT"] = "9999"
        os.environ["SENTINEL_ENV"] = "test"
        os.environ["SENTINEL_ALLOWED_ORIGINS"] = "http://custom-origin.test:3000, http://another.test:4000/"
        try:
            settings = get_settings()
            self.assertEqual(settings.port, 9999)
            self.assertEqual(settings.environment, "test")
            self.assertEqual(
                settings.allowed_origins,
                ("http://custom-origin.test:3000", "http://another.test:4000"),
            )
        finally:
            os.environ.pop("SENTINEL_PORT", None)
            os.environ.pop("SENTINEL_ENV", None)
            os.environ.pop("SENTINEL_ALLOWED_ORIGINS", None)


if __name__ == "__main__":
    unittest.main()
