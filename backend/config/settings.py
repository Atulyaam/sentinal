"""Settings and Environment Configuration for Project Sentinel."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:4173",
    "http://localhost:4173",
    "http://127.0.0.1:5476",
    "http://localhost:5476",
)


def resolve_default_db_path() -> str:
    """Resolve default SQLite storage path outside repository in OS user app data."""
    env_override = os.getenv("SENTINEL_DB_PATH")
    if env_override:
        return env_override
    if sys.platform == "win32":
        local_app_data = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        base = Path(local_app_data) / "ProjectSentinel"
    else:
        base = Path.home() / ".local" / "share" / "project-sentinel"
    return str(base / "sentinel.db")


@dataclass(frozen=True)
class Settings:
    """Immutable application settings loaded from environment with safe defaults."""
    app_name: str
    version: str
    host: str
    port: int
    environment: str
    log_level: str
    approved_inbox: str
    allowed_origins: tuple[str, ...]
    db_path: str
    max_import_size_bytes: int = 20 * 1024 * 1024
    max_records_per_file: int = 100_000


def get_settings() -> Settings:
    """Resolve settings from environment variables."""
    raw_origins = os.getenv("SENTINEL_ALLOWED_ORIGINS")
    if raw_origins is not None:
        parsed_origins = tuple(
            origin.strip().rstrip("/")
            for origin in raw_origins.split(",")
            if origin.strip()
        )
    else:
        parsed_origins = DEFAULT_ALLOWED_ORIGINS

    return Settings(
        app_name=os.getenv("SENTINEL_APP_NAME", "Project Sentinel"),
        version=os.getenv("SENTINEL_VERSION", "0.2.0"),
        host=os.getenv("SENTINEL_HOST", "127.0.0.1"),
        port=int(os.getenv("SENTINEL_PORT", "8000")),
        environment=os.getenv("SENTINEL_ENV", "development"),
        log_level=os.getenv("SENTINEL_LOG_LEVEL", "INFO"),
        approved_inbox=os.getenv("SENTINEL_APPROVED_INBOX", "./inbox"),
        allowed_origins=parsed_origins,
        db_path=resolve_default_db_path(),
        max_import_size_bytes=int(os.getenv("SENTINEL_MAX_IMPORT_SIZE_BYTES", str(20 * 1024 * 1024))),
        max_records_per_file=int(os.getenv("SENTINEL_MAX_RECORDS_PER_FILE", "100000")),
    )
