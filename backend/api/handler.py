"""HTTP Request Handler for Project Sentinel."""

import json
import logging
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from typing import Optional
from urllib.parse import parse_qs, urlparse

from backend.api.upload import parse_import_payload
from backend.config.settings import get_settings
from backend.detection.engine import DetectionEngine
from backend.ingestion.engine import ImportEngine
from backend.normalization.engine import NormalizationEngine
from backend.parsers.registry import list_available_parsers
from backend.persistence.connection import get_connection
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository

logger = logging.getLogger("sentinel.api")

# Cached repository and engine instances
_repo: Optional[IngestionRepository] = None
_engine: Optional[ImportEngine] = None
_norm_engine: Optional[NormalizationEngine] = None
_detection_engine: Optional[DetectionEngine] = None


def get_repository() -> IngestionRepository:
    """Obtain or initialize the SQLite ingestion repository."""
    global _repo
    if _repo is None:
        settings = get_settings()
        conn = get_connection(settings.db_path)
        apply_migrations(conn)
        _repo = IngestionRepository(conn)
        _repo.reconcile_pending_jobs()
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
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                self._send_json_response(200, payload, origin=origin)
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

            if clean_path == "/api/import":
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
