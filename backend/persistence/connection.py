"""SQLite Connection Factory and Pragma Configuration."""

import logging
import sqlite3
from pathlib import Path

from backend.config.settings import get_settings

logger = logging.getLogger("sentinel.persistence")


def get_db_path() -> Path:
    """Return the resolved database filesystem path."""
    settings = get_settings()
    path = Path(settings.db_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Create and configure a robust SQLite connection."""
    target_path = Path(db_path).resolve() if db_path else get_db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(target_path),
        check_same_thread=False,
        timeout=10.0,
        isolation_level=None,  # Autocommit mode; explicit transactions via BEGIN
    )
    conn.row_factory = sqlite3.Row

    # Enforce mandatory foreign keys and WAL mode
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA synchronous = NORMAL;")

    return conn

