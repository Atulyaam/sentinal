"""Approved local inbox scanner with path containment, stability checks, and pause controls."""

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config.settings import Settings
from backend.ingestion.engine import ImportEngine
from backend.persistence.repository import IngestionRepository

logger = logging.getLogger("sentinel.scanner")

# Forbidden directories for approved inbox scanning
FORBIDDEN_ROOTS = {"/", "\\", "c:\\", "c:/", "d:\\", "d:/"}
FORBIDDEN_NAME_PATTERNS = {"windows", "system32", "program files", "etc", "sys", "usr", "bin"}


def is_safe_inbox_path(inbox_path: str | Path) -> bool:
    """Validate that the candidate inbox directory does not target sensitive system paths."""
    resolved = Path(inbox_path).resolve()
    resolved_str = str(resolved).lower()

    # Reject filesystem root
    if resolved_str in FORBIDDEN_ROOTS or resolved == resolved.parent:
        return False

    # Reject user home root
    if resolved == Path.home().resolve():
        return False

    # Reject system directories
    lower_parts = {p.lower() for p in resolved.parts}
    if bool(FORBIDDEN_NAME_PATTERNS & lower_parts):
        return False

    return True


def is_symlink_or_junction(path: Path) -> bool:
    """Detect whether a path is a symbolic link or Windows NTFS junction point."""
    if path.is_symlink():
        return True
    if hasattr(os.path, "isjunction") and os.path.isjunction(str(path)):
        return True
    return False


class InboxScanner:
    """Monitors an approved local directory for new log files and triggers deterministic ingestion."""

    def __init__(
        self,
        engine: ImportEngine,
        repository: IngestionRepository,
        settings: Settings,
        poll_interval_seconds: float = 3.0,
        stability_wait_seconds: float = 0.5,
    ) -> None:
        self.engine = engine
        self.repo = repository
        self.settings = settings
        self.poll_interval = poll_interval_seconds
        self.stability_wait = stability_wait_seconds

        self.inbox_dir = Path(settings.approved_inbox).resolve()
        self._is_paused = False
        self._is_running = False  # Monitoring is disabled by default
        self._lock = threading.Lock()
        self._worker_thread: Optional[threading.Thread] = None

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._is_paused

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    def pause(self) -> None:
        """Pause inbox scanning."""
        with self._lock:
            self._is_paused = True
            logger.info("Inbox scanner paused.")

    def resume(self) -> None:
        """Resume inbox scanning."""
        with self._lock:
            self._is_paused = False
            logger.info("Inbox scanner resumed.")

    def ensure_inbox_directory(self) -> bool:
        """Ensure the approved inbox directory exists and is safe."""
        if not is_safe_inbox_path(self.inbox_dir):
            logger.error("Configured approved inbox '%s' is unsafe. Scanner aborted.", self.inbox_dir)
            return False

        try:
            self.inbox_dir.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as err:
            logger.error("Failed to create inbox directory '%s': %s", self.inbox_dir, err)
            return False

    def is_file_stable(self, file_path: Path) -> bool:
        """Verify that the file size is stable and not actively being written."""
        try:
            size1 = file_path.stat().st_size
            time.sleep(self.stability_wait)
            size2 = file_path.stat().st_size
            return size1 == size2
        except (OSError, FileNotFoundError):
            return False

    def scan_once(self) -> List[Dict[str, Any]]:
        """Perform a single non-recursive scan iteration across the approved inbox."""
        if self.is_paused:
            logger.debug("Scanner is paused; skipping scan iteration.")
            return []

        if not self.ensure_inbox_directory():
            return []

        results: List[Dict[str, Any]] = []

        # Ensure approved inbox event source exists in SQLite
        source_id = "src_inbox_approved"
        source = self.repo.get_or_create_source(
            source_id=source_id,
            source_name="Approved Local Inbox",
            parser_profile="generic_jsonl",
            configured_path=str(self.inbox_dir),
            enabled=1,
        )

        # Respect source enabled/disabled state
        if not source.get("enabled", 1):
            logger.info("Approved inbox source '%s' is disabled. Skipping scan iteration.", source_id)
            return []

        # Parser profile MUST come from the configured source; never inferred from filename
        configured_parser_id = source.get("parser_profile", "generic_jsonl")

        real_inbox_path = self.inbox_dir.resolve(strict=True)

        try:
            # Non-recursive direct listing of the inbox
            entries = sorted(self.inbox_dir.iterdir(), key=lambda p: p.name)
        except OSError as err:
            logger.error("Failed to read inbox directory: %s", err)
            return []

        for entry in entries:
            # Check pause state before processing each file
            if self.is_paused:
                break

            # Strictly ignore directories, hidden files, symlinks, or junctions
            if not entry.is_file() or is_symlink_or_junction(entry) or entry.name.startswith("."):
                continue

            # Symlink & Junction escape defense: verify canonical target is strictly within inbox
            try:
                real_entry = entry.resolve(strict=True)
                # Boundary check immediately before opening: file parent must strictly match real inbox
                if real_entry.parent != real_inbox_path:
                    logger.warning(
                        "Directory boundary escape detected for '%s' (resolved to '%s'); skipping.",
                        entry.name,
                        real_entry,
                    )
                    continue
            except (OSError, RuntimeError) as err:
                logger.warning("Error resolving canonical path for '%s': %s", entry.name, err)
                continue

            # Stability check
            if not self.is_file_stable(entry):
                logger.info("File '%s' is actively changing; skipping this poll cycle.", entry.name)
                continue

            # Read file bytes safely in read-only binary mode
            try:
                with open(real_entry, "rb") as f:
                    content_bytes = f.read()
            except OSError as err:
                logger.error("Failed to read file '%s': %s", entry.name, err)
                continue

            # Ingest via ImportEngine with explicit configured parser (preserves file, skips duplicates via SHA-256)
            logger.info(
                "Ingesting inbox file '%s' using explicitly configured source parser '%s'",
                entry.name,
                configured_parser_id,
            )
            result = self.engine.ingest_file(
                source_id=source_id,
                filename=entry.name,
                content_bytes=content_bytes,
                parser_id=configured_parser_id,
            )
            results.append(result)

        return results

    def start_background_scanning(self) -> None:
        """Start background polling thread."""
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
            self._worker_thread = threading.Thread(
                target=self._run_loop, daemon=True, name="sentinel-inbox-scanner"
            )
            self._worker_thread.start()
            logger.info("Background inbox scanner started for directory '%s'", self.inbox_dir)

    def stop_background_scanning(self) -> None:
        """Stop background polling thread."""
        with self._lock:
            self._is_running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=3.0)
            logger.info("Background inbox scanner stopped.")

    def _run_loop(self) -> None:
        """Internal daemon loop."""
        while self.is_running:
            try:
                self.scan_once()
            except Exception as exc:
                logger.error("Unexpected error during inbox scan loop: %s", exc, exc_info=True)
            time.sleep(self.poll_interval)
