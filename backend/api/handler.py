"""HTTP Request Handler for Project Sentinel."""

import json
import logging
import mimetypes
import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from backend.api.upload import parse_import_payload
from backend.cases.engine import CorrelationEngine
from backend.claims.engine import ClaimGuardEngine
from backend.claims.models import (
    SUPPORTED_CLAIM_TYPES,
    VERIFIER_VERSION,
    ClaimProposal,
)
from backend.claims.templates import APPROVED_TEMPLATES
from backend.config.settings import get_settings
from backend.detection.engine import DetectionEngine
from backend.ingestion.engine import ImportEngine
from backend.normalization.engine import NormalizationEngine
from backend.parsers.registry import list_available_parsers
from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository
from backend.replay.engine import ReplayEngine
from backend.replay.models import WhatIfConfig
from backend.replay.scenarios import (
    get_scenario_manifest,
    list_scenario_manifests,
)

logger = logging.getLogger("sentinel.api")

# Cached repository and engine instances
_repo: Optional[IngestionRepository] = None
_engine: Optional[ImportEngine] = None
_norm_engine: Optional[NormalizationEngine] = None
_detection_engine: Optional[DetectionEngine] = None
_correlation_engine: Optional[CorrelationEngine] = None
_claim_engine: Optional[ClaimGuardEngine] = None
_replay_engine: Optional[ReplayEngine] = None


class RateLimiter:
    """Thread-safe in-memory rate limiter using a rolling 60-second window."""

    def __init__(self, limit_per_minute: int = 60) -> None:
        self.limit = limit_per_minute
        self._requests: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, client_ip: str) -> bool:
        now = time.time()
        cutoff = now - 60.0
        with self._lock:
            timestamps = self._requests.setdefault(client_ip, [])
            filtered = [t for t in timestamps if t > cutoff]
            if len(filtered) >= self.limit:
                self._requests[client_ip] = filtered
                return False
            filtered.append(now)
            self._requests[client_ip] = filtered
            return True


_rate_limiter = RateLimiter(limit_per_minute=60)


def get_repository() -> IngestionRepository:
    """Obtain or initialize the SQLite ingestion repository."""
    global _repo
    if _repo is None:
        settings = get_settings()
        conn = get_connection(settings.db_path)
        apply_migrations(conn)
        _repo = IngestionRepository(conn)
        _repo.reconcile_pending_jobs()
        if settings.demo_mode and settings.demo_seed_on_startup:
            try:
                from backend.persistence.demo_seeder import seed_demo_baseline_if_needed
                seed_demo_baseline_if_needed(_repo)
            except Exception as seeder_err:
                logger.warning("Could not seed demo baseline: %s", seeder_err)
    return _repo


def get_import_engine() -> ImportEngine:
    """Obtain or initialize the log ingestion engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        repo = get_repository()
        _engine = ImportEngine(repository=repo, settings=settings)
    return _engine


def get_normalization_engine() -> NormalizationEngine:
    """Obtain or initialize the canonical normalization engine."""
    global _norm_engine
    if _norm_engine is None:
        _norm_engine = NormalizationEngine()
    return _norm_engine


def get_detection_engine() -> DetectionEngine:
    """Obtain or initialize the deterministic detection engine."""
    global _detection_engine
    if _detection_engine is None:
        _detection_engine = DetectionEngine()
    return _detection_engine


def get_correlation_engine() -> CorrelationEngine:
    """Obtain or initialize the deterministic correlation engine."""
    global _correlation_engine
    if _correlation_engine is None:
        _correlation_engine = CorrelationEngine()
    return _correlation_engine


def get_claim_engine() -> ClaimGuardEngine:
    """Obtain or initialize the Claim Guard engine."""
    global _claim_engine
    if _claim_engine is None:
        _claim_engine = ClaimGuardEngine()
    return _claim_engine


def get_replay_engine() -> ReplayEngine:
    """Obtain or initialize the Replay Lab deterministic engine."""
    global _replay_engine
    if _replay_engine is None:
        _replay_engine = ReplayEngine(main_repo=get_repository())
    return _replay_engine


class SentinelRequestHandler(BaseHTTPRequestHandler):
    """Standard HTTP request handler providing health, ingestion, normalization, and detection endpoints."""

    server_version = "ProjectSentinel/0.4.0"

    def _get_request_origin(self) -> Optional[str]:
        """Extract and normalize incoming Origin header if present."""
        origin = self.headers.get("Origin")
        if origin:
            return origin.strip().rstrip("/")
        return None

    def _is_origin_allowed(self, origin: Optional[str]) -> bool:
        """Check if the origin is explicitly permitted."""
        if not origin:
            return False
        settings = get_settings()
        return origin in settings.allowed_origins

    def _apply_cors_headers(self, origin: Optional[str]) -> None:
        """Set explicit, non-wildcard CORS headers if the origin is permitted."""
        if origin and self._is_origin_allowed(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, Authorization, X-Requested-With")
            self.send_header("Access-Control-Max-Age", "86400")

    def _serve_static_file(
        self,
        file_path: Path,
        origin: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> None:
        """Serve a static file with appropriate Content-Type, security headers, and caching."""
        if not content_type:
            guessed, _ = mimetypes.guess_type(str(file_path))
            content_type = guessed or "application/octet-stream"

        try:
            content_bytes = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content_bytes)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            if "text/html" in content_type:
                self.send_header("Cache-Control", "no-cache, must-revalidate")
            else:
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self._apply_cors_headers(origin)
            self.end_headers()
            self.wfile.write(content_bytes)
        except Exception as e:
            logger.error("Failed to serve static file %s: %s", file_path, e)
            self._send_json_response(500, {"error": "Internal Server Error", "message": "Failed to read static file."}, origin=origin)

    def _send_json_response(self, status_code: int, data: dict, origin: Optional[str] = None) -> None:
        """Serialize and send a JSON response with security headers."""
        response_body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self._apply_cors_headers(origin)
        self.end_headers()
        self.wfile.write(response_body)

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests strictly."""
        origin = self._get_request_origin()
        if origin is not None and not self._is_origin_allowed(origin):
            self.send_response(403)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(b'{"error":"Forbidden","message":"Origin not allowed by CORS policy."}')
            return

        self.send_response(204)
        self._apply_cors_headers(origin)
        self.end_headers()

    def do_GET(self) -> None:
        """Handle incoming GET requests safely."""
        origin = self._get_request_origin()

        try:
            parsed_url = urlparse(self.path)
            clean_path = parsed_url.path.rstrip("/")
            if not clean_path:
                clean_path = "/"

            # 1. Health check endpoints
            if clean_path in ("/health", "/api/health"):
                settings = get_settings()
                payload = {
                    "app": settings.app_name,
                    "status": "ok",
                    "version": settings.version,
                    "environment": settings.environment,
                    "demo_mode": settings.demo_mode,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                self._send_json_response(200, payload, origin=origin)
                return

            # 1b. Readiness probe endpoints
            if clean_path in ("/ready", "/api/ready"):
                settings = get_settings()
                repo = get_repository()
                try:
                    cur = repo.conn.execute("SELECT 1;")
                    db_ok = cur.fetchone()[0] == 1
                except Exception:
                    db_ok = False
                payload = {
                    "app": settings.app_name,
                    "status": "ready" if db_ok else "degraded",
                    "database": "connected" if db_ok else "unreachable",
                    "demo_mode": settings.demo_mode,
                    "version": settings.version,
                    "environment": settings.environment,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                self._send_json_response(200 if db_ok else 503, payload, origin=origin)
                return

            # 2. Registered parser profiles
            if clean_path == "/api/parsers":
                parsers = list_available_parsers()
                self._send_json_response(200, {"parsers": parsers}, origin=origin)
                return

            # 3. Configured event sources
            if clean_path == "/api/sources":
                repo = get_repository()
                sources = repo.list_sources()
                self._send_json_response(200, {"sources": sources}, origin=origin)
                return

            # 4. List import history
            if clean_path == "/api/imports":
                query_params = parse_qs(parsed_url.query)
                limit = 50
                offset = 0
                if "limit" in query_params:
                    try:
                        limit = min(max(int(query_params["limit"][0]), 1), 200)
                    except ValueError:
                        pass
                if "offset" in query_params:
                    try:
                        offset = max(int(query_params["offset"][0]), 0)
                    except ValueError:
                        pass

                repo = get_repository()
                jobs = repo.list_import_jobs(limit=limit, offset=offset)
                self._send_json_response(200, {"imports": jobs, "count": len(jobs)}, origin=origin)
                return

            # 5. Get specific import details with errors
            if clean_path.startswith("/api/imports/"):
                import_id = clean_path[len("/api/imports/"):].strip()
                if not import_id:
                    self._send_json_response(400, {"error": "Bad Request", "message": "Missing import ID."}, origin=origin)
                    return

                repo = get_repository()
                job = repo.get_import_job(import_id)
                if not job:
                    self._send_json_response(404, {"error": "Not Found", "message": f"Import '{import_id}' not found."}, origin=origin)
                    return

                self._send_json_response(200, job, origin=origin)
                return

            # 6. List normalized events (with dynamic filtering)
            if clean_path == "/api/events":
                query_params = parse_qs(parsed_url.query)
                limit = 50
                offset = 0
                if "limit" in query_params:
                    try:
                        limit = min(max(int(query_params["limit"][0]), 1), 200)
                    except ValueError:
                        pass
                if "offset" in query_params:
                    try:
                        offset = max(int(query_params["offset"][0]), 0)
                    except ValueError:
                        pass

                event_type = query_params.get("event_type", [None])[0]
                source_id = query_params.get("source_id", [None])[0]
                user_principal = query_params.get("user_principal", [None])[0]
                status = query_params.get("status", [None])[0]
                import_id = query_params.get("import_id", [None])[0]

                repo = get_repository()
                events, total = repo.list_normalized_events(
                    limit=limit,
                    offset=offset,
                    event_type=event_type,
                    source_id=source_id,
                    user_principal=user_principal,
                    status=status,
                    import_id=import_id,
                )
                self._send_json_response(200, {
                    "events": events,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }, origin=origin)
                return

            # 7. Get specific normalized event with provenance details
            if clean_path.startswith("/api/events/"):
                event_id = clean_path[len("/api/events/"):].strip()
                if not event_id:
                    self._send_json_response(400, {"error": "Bad Request", "message": "Missing event ID."}, origin=origin)
                    return

                repo = get_repository()
                event = repo.get_normalized_event(event_id)
                if not event:
                    self._send_json_response(404, {"error": "Not Found", "message": f"Event '{event_id}' not found."}, origin=origin)
                    return

                self._send_json_response(200, event, origin=origin)
                return

            # 8. Normalization statistics
            if clean_path == "/api/normalization/stats":
                repo = get_repository()
                stats = repo.get_normalization_stats()
                self._send_json_response(200, stats, origin=origin)
                return

            # 9. List normalization errors
            if clean_path == "/api/normalization/errors":
                query_params = parse_qs(parsed_url.query)
                limit = 50
                offset = 0
                import_id = query_params.get("import_id", [None])[0]
                if "limit" in query_params:
                    try:
                        limit = min(max(int(query_params["limit"][0]), 1), 200)
                    except ValueError:
                        pass
                if "offset" in query_params:
                    try:
                        offset = max(int(query_params["offset"][0]), 0)
                    except ValueError:
                        pass

                repo = get_repository()
                errors = repo.list_normalization_errors(limit=limit, offset=offset, import_id=import_id)
                self._send_json_response(200, {"errors": errors, "count": len(errors)}, origin=origin)
                return

            # 10. List detection rules (Phase 4)
            if clean_path == "/api/rules":
                repo = get_repository()
                rules = repo.list_detection_rules()
                self._send_json_response(200, {"rules": rules, "count": len(rules)}, origin=origin)
                return

            # 11. Get specific detection rule
            if clean_path.startswith("/api/rules/"):
                rule_id = clean_path[len("/api/rules/"):].strip()
                if not rule_id:
                    self._send_json_response(400, {"error": "Bad Request", "message": "Missing rule ID."}, origin=origin)
                    return
                repo = get_repository()
                rule = repo.get_detection_rule(rule_id)
                if not rule:
                    self._send_json_response(404, {"error": "Not Found", "message": f"Rule '{rule_id}' not found."}, origin=origin)
                    return
                self._send_json_response(200, rule, origin=origin)
                return

            # 12. Detection statistics (Phase 4)
            if clean_path == "/api/detection/stats":
                repo = get_repository()
                stats = repo.get_detection_stats()
                self._send_json_response(200, stats, origin=origin)
                return

            # 13. List findings (Phase 4)
            if clean_path == "/api/findings":
                query_params = parse_qs(parsed_url.query)
                limit = 50
                offset = 0
                if "limit" in query_params:
                    try:
                        limit = min(max(int(query_params["limit"][0]), 1), 200)
                    except ValueError:
                        pass
                if "offset" in query_params:
                    try:
                        offset = max(int(query_params["offset"][0]), 0)
                    except ValueError:
                        pass

                severity = query_params.get("severity", [None])[0]
                status = query_params.get("status", [None])[0]
                rule_id = query_params.get("rule_id", [None])[0]

                repo = get_repository()
                findings, total = repo.list_findings(
                    limit=limit,
                    offset=offset,
                    severity=severity,
                    status=status,
                    rule_id=rule_id,
                )
                self._send_json_response(200, {
                    "findings": findings,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }, origin=origin)
                return

            # 14. Get specific finding with supporting events (Phase 4)
            if clean_path.startswith("/api/findings/"):
                finding_id = clean_path[len("/api/findings/"):].strip()
                if not finding_id:
                    self._send_json_response(400, {"error": "Bad Request", "message": "Missing finding ID."}, origin=origin)
                    return
                repo = get_repository()
                finding = repo.get_finding(finding_id)
                if not finding:
                    self._send_json_response(404, {"error": "Not Found", "message": f"Finding '{finding_id}' not found."}, origin=origin)
                    return
                self._send_json_response(200, finding, origin=origin)
                return

            # 15. Case statistics (Phase 5)
            if clean_path == "/api/cases/stats":
                repo = get_repository()
                stats = repo.get_case_stats()
                self._send_json_response(200, stats, origin=origin)
                return

            # 16. List cases (Phase 5)
            if clean_path == "/api/cases":
                query_params = parse_qs(parsed_url.query)
                limit = 50
                offset = 0
                if "limit" in query_params:
                    try:
                        limit = min(max(int(query_params["limit"][0]), 1), 200)
                    except ValueError:
                        pass
                if "offset" in query_params:
                    try:
                        offset = max(int(query_params["offset"][0]), 0)
                    except ValueError:
                        pass

                status = query_params.get("status", [None])[0]
                severity = query_params.get("severity", [None])[0]
                correlation_key_type = query_params.get("correlation_key_type", [None])[0]
                search = query_params.get("search", [None])[0]

                repo = get_repository()
                cases, total = repo.list_cases(
                    limit=limit,
                    offset=offset,
                    status=status,
                    severity=severity,
                    correlation_key_type=correlation_key_type,
                    search=search,
                )
                self._send_json_response(200, {
                    "cases": cases,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }, origin=origin)
                return

            # 17. Claim templates catalog (Phase 6)
            if clean_path == "/api/claims/templates":
                self._send_json_response(200, {
                    "templates": APPROVED_TEMPLATES,
                    "supported_claim_types": sorted(list(SUPPORTED_CLAIM_TYPES)),
                    "version": VERIFIER_VERSION,
                }, origin=origin)
                return

            # 18. Case claims list (Phase 6)
            if clean_path.startswith("/api/cases/") and clean_path.endswith("/claims"):
                parts = clean_path.split("/")
                if len(parts) == 5 and parts[2] == "cases" and parts[4] == "claims":
                    case_id = parts[3].strip()
                    query_params = parse_qs(parsed_url.query)
                    status_filter = query_params.get("status", [None])[0]
                    repo = get_repository()
                    case = repo.get_case(case_id)
                    if not case:
                        self._send_json_response(404, {"error": "Not Found", "message": f"Case '{case_id}' not found."}, origin=origin)
                        return
                    claims = repo.list_case_claims(case_id, status=status_filter)
                    self._send_json_response(200, {
                        "case_id": case_id,
                        "claims": claims,
                        "total": len(claims),
                    }, origin=origin)
                    return

            # 19. Single claim detail (Phase 6)
            if clean_path.startswith("/api/claims/"):
                claim_id = clean_path[len("/api/claims/"):].strip()
                if not claim_id:
                    self._send_json_response(400, {"error": "Bad Request", "message": "Missing claim ID."}, origin=origin)
                    return
                repo = get_repository()
                claim = repo.get_claim(claim_id)
                if not claim:
                    self._send_json_response(404, {"error": "Not Found", "message": f"Claim '{claim_id}' not found."}, origin=origin)
                    return
                self._send_json_response(200, claim, origin=origin)
                return

            # 20. Get specific case detail with timeline and review history (Phase 5)
            if clean_path.startswith("/api/cases/"):
                case_id = clean_path[len("/api/cases/"):].strip()
                if not case_id:
                    self._send_json_response(400, {"error": "Bad Request", "message": "Missing case ID."}, origin=origin)
                    return
                repo = get_repository()
                case = repo.get_case(case_id)
                if not case:
                    self._send_json_response(404, {"error": "Not Found", "message": f"Case '{case_id}' not found."}, origin=origin)
                    return
                self._send_json_response(200, case, origin=origin)
                return

            # 21. Replay Lab scenarios list (Phase 7)
            if clean_path == "/api/replay/scenarios":
                manifests = list_scenario_manifests()
                self._send_json_response(200, {
                    "scenarios": [m.to_dict() for m in manifests],
                    "total": len(manifests),
                }, origin=origin)
                return

            # 22. Replay Lab scenario detail (Phase 7)
            if clean_path.startswith("/api/replay/scenarios/"):
                scenario_id = clean_path[len("/api/replay/scenarios/"):].strip()
                manifest = get_scenario_manifest(scenario_id)
                if not manifest:
                    self._send_json_response(404, {"error": "Not Found", "message": f"Scenario '{scenario_id}' not found."}, origin=origin)
                    return
                self._send_json_response(200, {"scenario": manifest.to_dict()}, origin=origin)
                return

            # 23. Replay Lab runs list (Phase 7)
            if clean_path == "/api/replay/runs":
                query_params = parse_qs(parsed_url.query)
                scenario_id = query_params.get("scenario_id", [None])[0]
                try:
                    limit = min(int(query_params.get("limit", [50])[0]), 100)
                    offset = max(int(query_params.get("offset", [0])[0]), 0)
                except ValueError:
                    self._send_json_response(400, {"error": "Bad Request", "message": "Invalid limit or offset parameter."}, origin=origin)
                    return
                repo = get_repository()
                runs, total = repo.list_replay_runs(scenario_id=scenario_id, limit=limit, offset=offset)
                self._send_json_response(200, {
                    "runs": runs,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }, origin=origin)
                return

            # 24. Replay Lab single run report (Phase 7)
            if clean_path.startswith("/api/replay/runs/"):
                replay_id = clean_path[len("/api/replay/runs/"):].strip()
                if not replay_id:
                    self._send_json_response(400, {"error": "Bad Request", "message": "Missing replay ID."}, origin=origin)
                    return
                repo = get_repository()
                run_data = repo.get_replay_run(replay_id)
                if not run_data:
                    self._send_json_response(404, {"error": "Not Found", "message": f"Replay run '{replay_id}' not found."}, origin=origin)
                    return
                self._send_json_response(200, {"run": run_data}, origin=origin)
                return

            # 25. Static asset & SPA fallback serving
            settings = get_settings()
            if settings.static_dir and os.path.isdir(settings.static_dir):
                static_root = Path(settings.static_dir).resolve()
                rel_path = clean_path.lstrip("/")
                if rel_path:
                    target_file = (static_root / rel_path).resolve()
                    if str(target_file).startswith(str(static_root)) and target_file.is_file():
                        self._serve_static_file(target_file, origin=origin)
                        return

                # SPA fallback: Serve index.html for known client-side routes or root
                known_spa_routes = {
                    "",
                    "/",
                    "/index.html",
                    "/overview",
                    "/sources",
                    "/events",
                    "/findings",
                    "/investigations",
                    "/cases",
                    "/replay",
                }
                accept_header = self.headers.get("Accept", "")
                is_html_browser_nav = "text/html" in accept_header and "." not in clean_path and not clean_path.startswith("/api/")

                if clean_path in known_spa_routes or is_html_browser_nav:
                    index_file = static_root / "index.html"
                    if index_file.is_file():
                        self._serve_static_file(index_file, origin=origin, content_type="text/html; charset=utf-8")
                        return

            # 404 for unhandled paths
            self._send_json_response(404, {
                "error": "Not Found",
                "path": clean_path,
                "status": 404,
                "message": f"Endpoint '{clean_path}' is not registered on this service."
            }, origin=origin)

        except Exception as exc:
            logger.error("Unhandled exception during GET request processing: %s", exc, exc_info=True)
            self._send_json_response(500, {
                "error": "Internal Server Error",
                "status": 500,
                "message": "An internal error occurred while processing the request."
            }, origin=origin)

    def do_POST(self) -> None:
        """Handle incoming POST requests safely."""
        origin = self._get_request_origin()

        try:
            parsed_url = urlparse(self.path)
            clean_path = parsed_url.path.rstrip("/")

            # Rate-limit expensive / state-changing endpoints
            expensive_paths = (
                "/api/replay/run",
                "/api/replay/compare",
                "/api/replay/reset",
                "/api/cases/correlate",
                "/api/cases/run",
                "/api/detection/run",
                "/api/normalization/run",
            )
            if clean_path in expensive_paths:
                settings = get_settings()
                if settings.environment != "test" and settings.rate_limit_per_minute > 0:
                    _rate_limiter.limit = settings.rate_limit_per_minute
                    client_ip = (
                        self.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                        or (self.client_address[0] if self.client_address else "127.0.0.1")
                    )
                    if not _rate_limiter.is_allowed(client_ip):
                        self._send_json_response(429, {
                            "error": "Too Many Requests",
                            "status": 429,
                            "message": "Rate limit exceeded for simulation/expensive operations. Please wait a moment before trying again.",
                        }, origin=origin)
                        return

            if clean_path == "/api/import":
                settings = get_settings()
                if settings.demo_mode:
                    self._send_json_response(403, {
                        "error": "Forbidden",
                        "status": 403,
                        "message": "Public Demo Mode Active: Log ingestion and file uploads are restricted to approved synthetic scenarios in the Replay Lab.",
                    }, origin=origin)
                    return

                content_length_str = self.headers.get("Content-Length")
                if not content_length_str:
                    self._send_json_response(400, {
                        "error": "Bad Request",
                        "message": "Missing Content-Length header."
                    }, origin=origin)
                    return

                try:
                    content_length = int(content_length_str)
                except ValueError:
                    self._send_json_response(400, {
                        "error": "Bad Request",
                        "message": "Invalid Content-Length header."
                    }, origin=origin)
                    return

                settings = get_settings()
                if content_length > settings.max_import_size_bytes:
                    self._send_json_response(413, {
                        "error": "Payload Too Large",
                        "message": f"Request body size exceeds maximum limit of {settings.max_import_size_bytes} bytes."
                    }, origin=origin)
                    return

                raw_body = self.rfile.read(content_length)
                content_type = self.headers.get("Content-Type", "")

                filename, content_bytes, parser_id, source_id, err_msg = parse_import_payload(
                    content_type_header=content_type,
                    raw_body=raw_body,
                )

                if err_msg or content_bytes is None or parser_id is None:
                    self._send_json_response(400, {
                        "error": "Bad Request",
                        "message": err_msg or "Failed to extract import payload."
                    }, origin=origin)
                    return

                engine = get_import_engine()
                result = engine.ingest_file(
                    source_id=source_id or "src_manual_default",
                    filename=filename or "uploaded_file.log",
                    content_bytes=content_bytes,
                    parser_id=parser_id,
                )

                if result.get("status") == "rejected":
                    self._send_json_response(422, result, origin=origin)
                else:
                    self._send_json_response(200, result, origin=origin)
                return

            # Normalization trigger endpoint
            if clean_path == "/api/normalization/run":
                content_length_str = self.headers.get("Content-Length")
                payload_data = {}
                if content_length_str:
                    try:
                        content_length = int(content_length_str)
                        if content_length > 0:
                            raw_body = self.rfile.read(content_length)
                            payload_data = json.loads(raw_body.decode("utf-8"))
                    except Exception as err:
                        logger.warning("Could not parse normalization/run payload: %s", err)

                import_id = payload_data.get("import_id")
                limit = int(payload_data.get("limit", 500))

                repo = get_repository()
                norm_engine = get_normalization_engine()
                run_res = norm_engine.run_normalization(repo=repo, import_id=import_id, limit=limit)
                self._send_json_response(200, {
                    "status": "success",
                    "result": run_res,
                }, origin=origin)
                return

            # Detection trigger endpoint (Phase 4)
            if clean_path == "/api/detection/run":
                content_length_str = self.headers.get("Content-Length")
                payload_data = {}
                if content_length_str:
                    try:
                        content_length = int(content_length_str)
                        if content_length > 0:
                            raw_body = self.rfile.read(content_length)
                            payload_data = json.loads(raw_body.decode("utf-8"))
                    except Exception as err:
                        logger.warning("Could not parse detection/run payload: %s", err)

                rule_ids = payload_data.get("rule_ids")
                limit_events = int(payload_data.get("limit_events", 5000))

                repo = get_repository()
                detection_engine = get_detection_engine()
                det_res = detection_engine.run_detection(
                    repository=repo,
                    rule_ids=rule_ids,
                    limit_events=limit_events,
                )
                self._send_json_response(200, {
                    "status": "success",
                    "result": det_res,
                }, origin=origin)
                return

            # Correlation trigger endpoint (Phase 5)
            if clean_path in ("/api/cases/correlate", "/api/cases/run"):
                content_length_str = self.headers.get("Content-Length")
                payload_data = {}
                if content_length_str:
                    try:
                        content_length = int(content_length_str)
                        if content_length > 0:
                            raw_body = self.rfile.read(content_length)
                            payload_data = json.loads(raw_body.decode("utf-8"))
                    except Exception as err:
                        logger.warning("Could not parse cases/correlate payload: %s", err)

                limit_findings = int(payload_data.get("limit_findings", 1000))
                repo = get_repository()
                corr_engine = get_correlation_engine()
                corr_res = corr_engine.run_correlation(
                    repository=repo,
                    limit_findings=limit_findings,
                )
                self._send_json_response(200, {
                    "status": "success",
                    "result": corr_res,
                }, origin=origin)
                return

            # Add operator review action / note / decision to case (Phase 5)
            if clean_path.startswith("/api/cases/") and clean_path.endswith("/review"):
                # Path format: /api/cases/{case_id}/review
                parts = clean_path.split("/")
                if len(parts) == 5 and parts[2] == "cases" and parts[4] == "review":
                    case_id = parts[3].strip()
                    content_length_str = self.headers.get("Content-Length")
                    if not content_length_str:
                        self._send_json_response(400, {"error": "Bad Request", "message": "Missing Content-Length header."}, origin=origin)
                        return

                    try:
                        content_length = int(content_length_str)
                        raw_body = self.rfile.read(content_length)
                        payload = json.loads(raw_body.decode("utf-8"))
                    except Exception:
                        self._send_json_response(400, {"error": "Bad Request", "message": "Invalid JSON payload in request body."}, origin=origin)
                        return

                    note = payload.get("note") or payload.get("operator_note") or ""
                    new_status = payload.get("status") or payload.get("new_status") or payload.get("to_status")
                    author = payload.get("author") or payload.get("operator") or "secops_operator"

                    if not note and not new_status:
                        self._send_json_response(400, {"error": "Bad Request", "message": "Either 'note' or 'status' must be provided."}, origin=origin)
                        return

                    repo = get_repository()
                    existing_case = repo.get_case(case_id)
                    if not existing_case:
                        self._send_json_response(404, {"error": "Not Found", "message": f"Case '{case_id}' not found."}, origin=origin)
                        return

                    try:
                        if new_status and new_status != existing_case["status"]:
                            updated_case = repo.update_case_status(
                                case_id=case_id,
                                new_status=new_status,
                                operator_note=note,
                                author=author,
                            )
                        elif note:
                            updated_case = repo.add_case_note(
                                case_id=case_id,
                                operator_note=note,
                                author=author,
                            )
                        else:
                            updated_case = existing_case

                        self._send_json_response(200, {
                            "status": "success",
                            "case": updated_case,
                        }, origin=origin)
                        return
                    except ValueError as err:
                        self._send_json_response(400, {
                            "error": "Bad Request",
                            "message": str(err),
                        }, origin=origin)
                        return

            # Claim Guard verification endpoint (Phase 6)
            if clean_path in ("/api/claims/verify", "/api/claims/run"):
                content_length_str = self.headers.get("Content-Length")
                if not content_length_str:
                    self._send_json_response(400, {"error": "Bad Request", "message": "Missing Content-Length header."}, origin=origin)
                    return

                try:
                    content_length = int(content_length_str)
                    raw_body = self.rfile.read(content_length)
                    payload_data = json.loads(raw_body.decode("utf-8"))
                except Exception:
                    self._send_json_response(400, {"error": "Bad Request", "message": "Invalid JSON payload in request body."}, origin=origin)
                    return

                case_id = payload_data.get("case_id") or payload_data.get("subject_ref")
                raw_claims = payload_data.get("claims")

                if raw_claims is None:
                    if "claim_type" in payload_data:
                        raw_claims = [payload_data]
                    else:
                        self._send_json_response(400, {"error": "Bad Request", "message": "Payload must include 'claims' list or a single claim object."}, origin=origin)
                        return

                if not isinstance(raw_claims, list):
                    self._send_json_response(400, {"error": "Bad Request", "message": "'claims' must be a list of claim proposals."}, origin=origin)
                    return

                proposals = []
                for idx, c_dict in enumerate(raw_claims):
                    if not isinstance(c_dict, dict):
                        self._send_json_response(400, {"error": "Bad Request", "message": f"Claim at index {idx} must be a JSON object."}, origin=origin)
                        return
                    if case_id and not c_dict.get("case_id"):
                        c_dict["case_id"] = case_id
                    try:
                        proposal = ClaimProposal.from_dict(c_dict)
                        proposals.append(proposal)
                    except ValueError as ve:
                        self._send_json_response(400, {"error": "Bad Request", "message": f"Invalid claim at index {idx}: {str(ve)}"}, origin=origin)
                        return

                if not proposals:
                    self._send_json_response(400, {"error": "Bad Request", "message": "No claims provided to verify."}, origin=origin)
                    return

                target_case_id = case_id or proposals[0].case_id
                repo = get_repository()
                engine = get_claim_engine()

                try:
                    verification_report = engine.process_claims(proposals, target_case_id, repo)
                    self._send_json_response(200, {
                        "status": "success",
                        "report": verification_report,
                    }, origin=origin)
                    return
                except (KeyError, ValueError) as ve:
                    self._send_json_response(404, {"error": "Not Found", "message": str(ve)}, origin=origin)
                    return

            # Claim Guard demo claims generation and verification (Phase 6)
            if clean_path.startswith("/api/cases/") and clean_path.endswith("/claims/demo"):
                parts = clean_path.split("/")
                if len(parts) == 6 and parts[2] == "cases" and parts[4] == "claims" and parts[5] == "demo":
                    case_id = parts[3].strip()
                    repo = get_repository()
                    case = repo.get_case(case_id)
                    if not case:
                        self._send_json_response(404, {"error": "Not Found", "message": f"Case '{case_id}' not found."}, origin=origin)
                        return

                    engine = get_claim_engine()
                    demo_proposals = engine.generate_demo_claims(case_id, repo)
                    report = engine.process_claims(demo_proposals, case_id, repo)
                    self._send_json_response(200, {
                        "status": "success",
                        "case_id": case_id,
                        "report": report,
                    }, origin=origin)
                    return

            # Propose and verify claims for specific case (Phase 6)
            if clean_path.startswith("/api/cases/") and clean_path.endswith("/claims/propose"):
                parts = clean_path.split("/")
                if len(parts) == 6 and parts[2] == "cases" and parts[4] == "claims" and parts[5] == "propose":
                    case_id = parts[3].strip()
                    content_length_str = self.headers.get("Content-Length")
                    if not content_length_str:
                        self._send_json_response(400, {"error": "Bad Request", "message": "Missing Content-Length header."}, origin=origin)
                        return

                    try:
                        content_length = int(content_length_str)
                        raw_body = self.rfile.read(content_length)
                        payload_data = json.loads(raw_body.decode("utf-8"))
                    except Exception:
                        self._send_json_response(400, {"error": "Bad Request", "message": "Invalid JSON payload in request body."}, origin=origin)
                        return

                    raw_claims = payload_data.get("claims")
                    if raw_claims is None:
                        if "claim_type" in payload_data:
                            raw_claims = [payload_data]
                        else:
                            self._send_json_response(400, {"error": "Bad Request", "message": "Payload must include 'claims' or single claim."}, origin=origin)
                            return

                    proposals = []
                    for idx, c_dict in enumerate(raw_claims):
                        if not isinstance(c_dict, dict):
                            self._send_json_response(400, {"error": "Bad Request", "message": f"Claim at index {idx} must be a JSON object."}, origin=origin)
                            return
                        c_dict["case_id"] = case_id
                        try:
                            proposal = ClaimProposal.from_dict(c_dict)
                            proposals.append(proposal)
                        except ValueError as ve:
                            self._send_json_response(400, {"error": "Bad Request", "message": f"Invalid claim at index {idx}: {str(ve)}"}, origin=origin)
                            return

                    repo = get_repository()
                    engine = get_claim_engine()
                    try:
                        report = engine.process_claims(proposals, case_id, repo)
                        self._send_json_response(200, {
                            "status": "success",
                            "case_id": case_id,
                            "report": report,
                        }, origin=origin)
                        return
                    except ValueError as ve:
                        self._send_json_response(404, {"error": "Not Found", "message": str(ve)}, origin=origin)
                        return

            # -------------------------------------------------------------
            # Replay Lab Execution Endpoints (Phase 7)
            # -------------------------------------------------------------

            # Execute a deterministic scenario or What-If simulation
            if clean_path == "/api/replay/run":
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len) if content_len > 0 else b"{}"
                try:
                    payload_data = json.loads(body.decode("utf-8")) if body else {}
                except Exception as e:
                    self._send_json_response(400, {"error": "Bad Request", "message": f"Malformed JSON: {e}"}, origin=origin)
                    return

                scenario_id = payload_data.get("scenario_id")
                if not scenario_id:
                    self._send_json_response(400, {"error": "Bad Request", "message": "Missing required field 'scenario_id'."}, origin=origin)
                    return

                what_if_dict = payload_data.get("what_if")
                what_if: Optional[WhatIfConfig] = None
                if what_if_dict and isinstance(what_if_dict, dict):
                    what_if = WhatIfConfig(
                        what_if_id=what_if_dict.get("what_if_id", "wif_custom"),
                        description=what_if_dict.get("description", "Custom simulation"),
                        rule_overrides=what_if_dict.get("rule_overrides"),
                        correlation_overrides=what_if_dict.get("correlation_overrides"),
                        excluded_records=what_if_dict.get("excluded_records"),
                    )

                engine = get_replay_engine()
                try:
                    report = engine.run_scenario(scenario_id=scenario_id, what_if=what_if)
                    self._send_json_response(200, {
                        "status": "success",
                        "run": report.to_dict(),
                    }, origin=origin)
                    return
                except (KeyError, ValueError) as ve:
                    self._send_json_response(404, {"error": "Not Found", "message": str(ve)}, origin=origin)
                    return
                except Exception as ex:
                    logger.error("Error executing replay scenario %s: %s", scenario_id, ex, exc_info=True)
                    self._send_json_response(500, {"error": "Internal Server Error", "message": str(ex)}, origin=origin)
                    return

            # Compare two historical replay runs
            if clean_path == "/api/replay/compare":
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len) if content_len > 0 else b"{}"
                try:
                    payload_data = json.loads(body.decode("utf-8")) if body else {}
                except Exception as e:
                    self._send_json_response(400, {"error": "Bad Request", "message": f"Malformed JSON: {e}"}, origin=origin)
                    return

                run_a_id = payload_data.get("run_a_id")
                run_b_id = payload_data.get("run_b_id")
                if not run_a_id or not run_b_id:
                    self._send_json_response(400, {"error": "Bad Request", "message": "Payload must include 'run_a_id' and 'run_b_id'."}, origin=origin)
                    return

                engine = get_replay_engine()
                try:
                    comparison = engine.compare_runs(run_a_id, run_b_id)
                    self._send_json_response(200, {
                        "status": "success",
                        "comparison": comparison,
                    }, origin=origin)
                    return
                except (KeyError, ValueError) as ve:
                    self._send_json_response(404, {"error": "Not Found", "message": str(ve)}, origin=origin)
                    return
                except Exception as ex:
                    logger.error("Error comparing replay runs: %s", ex, exc_info=True)
                    self._send_json_response(500, {"error": "Internal Server Error", "message": str(ex)}, origin=origin)
                    return

            # Reset replay runs safely without touching core security data
            if clean_path == "/api/replay/reset":
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len) if content_len > 0 else b"{}"
                payload_data = {}
                if body:
                    try:
                        payload_data = json.loads(body.decode("utf-8"))
                    except Exception:
                        pass

                scenario_id = payload_data.get("scenario_id") if isinstance(payload_data, dict) else None
                repo = get_repository()
                deleted = repo.reset_replay_runs(scenario_id=scenario_id)
                self._send_json_response(200, {
                    "status": "success",
                    "deleted_count": deleted,
                    "message": f"Safely reset {deleted} replay run record(s). Core security data untouched.",
                }, origin=origin)
                return

            # 404 for unhandled POST paths
            self._send_json_response(404, {
                "error": "Not Found",
                "path": clean_path,
                "status": 404,
                "message": f"Endpoint '{clean_path}' is not registered on this service."
            }, origin=origin)

        except Exception as exc:
            logger.error("Unhandled exception during POST request processing: %s", exc, exc_info=True)
            self._send_json_response(500, {
                "error": "Internal Server Error",
                "status": 500,
                "message": "An internal error occurred while processing the request."
            }, origin=origin)

    def do_PATCH(self) -> None:
        """Handle incoming PATCH requests safely (e.g. finding status or rule state updates)."""
        origin = self._get_request_origin()

        try:
            parsed_url = urlparse(self.path)
            clean_path = parsed_url.path.rstrip("/")

            content_length_str = self.headers.get("Content-Length")
            if not content_length_str:
                self._send_json_response(400, {
                    "error": "Bad Request",
                    "message": "Missing Content-Length header."
                }, origin=origin)
                return

            try:
                content_length = int(content_length_str)
                raw_body = self.rfile.read(content_length)
                payload = json.loads(raw_body.decode("utf-8"))
            except Exception:
                self._send_json_response(400, {
                    "error": "Bad Request",
                    "message": "Invalid JSON payload in request body."
                }, origin=origin)
                return

            # 1. Update finding status (Phase 4)
            if clean_path.startswith("/api/findings/"):
                finding_id = clean_path[len("/api/findings/"):].strip()
                if not finding_id:
                    self._send_json_response(400, {"error": "Bad Request", "message": "Missing finding ID."}, origin=origin)
                    return

                new_status = payload.get("status")
                if not new_status or not isinstance(new_status, str):
                    self._send_json_response(400, {
                        "error": "Bad Request",
                        "message": "Field 'status' is required and must be a string."
                    }, origin=origin)
                    return

                try:
                    repo = get_repository()
                    updated = repo.update_finding_status(finding_id, new_status)
                    if not updated:
                        self._send_json_response(404, {
                            "error": "Not Found",
                            "message": f"Finding '{finding_id}' not found."
                        }, origin=origin)
                        return
                    self._send_json_response(200, updated, origin=origin)
                    return
                except ValueError as val_err:
                    self._send_json_response(400, {
                        "error": "Bad Request",
                        "message": str(val_err)
                    }, origin=origin)
                    return

            # 2. Toggle detection rule enabled state (Phase 4)
            if clean_path.startswith("/api/rules/"):
                rule_id = clean_path[len("/api/rules/"):].strip()
                if not rule_id:
                    self._send_json_response(400, {"error": "Bad Request", "message": "Missing rule ID."}, origin=origin)
                    return

                enabled_val = payload.get("enabled")
                if not isinstance(enabled_val, bool):
                    self._send_json_response(400, {
                        "error": "Bad Request",
                        "message": "Field 'enabled' is required and must be a boolean."
                    }, origin=origin)
                    return

                repo = get_repository()
                success = repo.update_detection_rule_enabled(rule_id, enabled_val)
                if not success:
                    self._send_json_response(404, {
                        "error": "Not Found",
                        "message": f"Rule '{rule_id}' not found."
                    }, origin=origin)
                    return

                # Update in-memory engine registry as well
                engine = get_detection_engine()
                engine.registry.set_enabled(rule_id, enabled_val)

                self._send_json_response(200, {
                    "status": "success",
                    "rule_id": rule_id,
                    "enabled": enabled_val,
                }, origin=origin)
                return

            # 3. Update case status (Phase 5)
            if clean_path.startswith("/api/cases/"):
                case_id = clean_path[len("/api/cases/"):].strip()
                if not case_id:
                    self._send_json_response(400, {"error": "Bad Request", "message": "Missing case ID."}, origin=origin)
                    return

                new_status = payload.get("status")
                if not new_status or not isinstance(new_status, str):
                    self._send_json_response(400, {
                        "error": "Bad Request",
                        "message": "Field 'status' is required and must be a string."
                    }, origin=origin)
                    return

                note = payload.get("note") or payload.get("operator_note") or ""
                author = payload.get("author", "secops_operator")

                try:
                    repo = get_repository()
                    updated = repo.update_case_status(
                        case_id=case_id,
                        new_status=new_status,
                        operator_note=note,
                        author=author,
                    )
                    if not updated:
                        self._send_json_response(404, {"error": "Not Found", "message": f"Case '{case_id}' not found."}, origin=origin)
                        return
                    self._send_json_response(200, {
                        "status": "success",
                        "case": updated,
                    }, origin=origin)
                    return
                except ValueError as val_err:
                    self._send_json_response(400, {
                        "error": "Bad Request",
                        "message": str(val_err),
                    }, origin=origin)
                    return

            # 404 for unhandled PATCH paths
            self._send_json_response(404, {
                "error": "Not Found",
                "path": clean_path,
                "status": 404,
                "message": f"Endpoint '{clean_path}' is not registered on this service."
            }, origin=origin)

        except Exception as exc:
            logger.error("Unhandled exception during PATCH request processing: %s", exc, exc_info=True)
            self._send_json_response(500, {
                "error": "Internal Server Error",
                "status": 500,
                "message": "An internal error occurred while processing the request."
            }, origin=origin)

    def log_message(self, format: str, *args) -> None:
        """Suppress default stderr noise and format with clean logger."""
        logger.info("%s - - [%s] %s", self.address_string(), self.log_date_time_string(), format % args)
