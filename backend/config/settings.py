"""Settings and Environment Configuration for Project Sentinel."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


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


def resolve_static_dir() -> Optional[str]:
    """Resolve directory containing built frontend static assets if available."""
    env_dir = os.getenv("SENTINEL_STATIC_DIR")
    if env_dir and os.path.isdir(env_dir):
        return os.path.abspath(env_dir)
    repo_root = Path(__file__).resolve().parent.parent.parent
    candidate = repo_root / "apps" / "crew-app" / "dist"
    if candidate.is_dir():
        return str(candidate)
    return None


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
    demo_mode: bool = False
    static_dir: Optional[str] = None
    rate_limit_per_minute: int = 60
    demo_seed_on_startup: bool = True


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

    # Standard PaaS environments (Railway, Render, Fly, Cloud Run) provide $PORT
    raw_port = os.getenv("PORT") or os.getenv("SENTINEL_PORT", "8000")
    try:
        resolved_port = int(raw_port)
    except ValueError:
        resolved_port = 8000

    env_name = os.getenv("SENTINEL_ENV", "development").lower()
    demo_mode_env = os.getenv("SENTINEL_DEMO_MODE")
    if demo_mode_env is not None:
        is_demo_mode = demo_mode_env.lower() in ("true", "1", "yes")
    else:
        # Default to demo_mode=True if running in production to ensure safety
        is_demo_mode = (env_name == "production")

    demo_seed_env = os.getenv("SENTINEL_DEMO_SEED", "true").lower() in ("true", "1", "yes")
    rate_limit = int(os.getenv("SENTINEL_RATE_LIMIT_PER_MINUTE", "60"))

    return Settings(
        app_name=os.getenv("SENTINEL_APP_NAME", "Project Sentinel"),
        version=os.getenv("SENTINEL_VERSION", "0.2.0"),
        host=os.getenv("SENTINEL_HOST", "0.0.0.0" if env_name == "production" else "127.0.0.1"),
        port=resolved_port,
        environment=env_name,
        log_level=os.getenv("SENTINEL_LOG_LEVEL", "INFO"),
        approved_inbox=os.getenv("SENTINEL_APPROVED_INBOX", "./inbox"),
        allowed_origins=parsed_origins,
        db_path=resolve_default_db_path(),
        max_import_size_bytes=int(os.getenv("SENTINEL_MAX_IMPORT_SIZE_BYTES", str(20 * 1024 * 1024))),
        max_records_per_file=int(os.getenv("SENTINEL_MAX_RECORDS_PER_FILE", "100000")),
        demo_mode=is_demo_mode,
        static_dir=resolve_static_dir(),
        rate_limit_per_minute=rate_limit,
        demo_seed_on_startup=demo_seed_env,
    )
