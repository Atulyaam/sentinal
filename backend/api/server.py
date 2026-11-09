"""HTTP Server Runner for Project Sentinel."""

import logging
import sys
from http.server import ThreadingHTTPServer

from backend.api.handler import SentinelRequestHandler
from backend.config.settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sentinel.server")


def create_server(host: str | None = None, port: int | None = None) -> ThreadingHTTPServer:
    """Create and configure the Sentinel HTTP server instance."""
    settings = get_settings()
    server_host = host if host is not None else settings.host
    server_port = port if port is not None else settings.port
    server_address = (server_host, server_port)
    return ThreadingHTTPServer(server_address, SentinelRequestHandler)


def run_server(host: str | None = None, port: int | None = None) -> None:
    """Start the Sentinel HTTP server and serve requests indefinitely."""
    import os
    settings = get_settings()
    from backend.persistence.connection import get_connection
    from backend.persistence.migrations import apply_migrations
    from backend.persistence.repository import IngestionRepository

    db_conn = get_connection(settings.db_path)
    apply_migrations(db_conn)
    repo = IngestionRepository(db_conn)
    reconciled = repo.reconcile_pending_jobs()
    if reconciled > 0:
        logger.warning("Reconciled %d interrupted pending job(s) from prior crash.", reconciled)

    if settings.demo_mode and settings.demo_seed_on_startup:
        try:
            from backend.persistence.demo_seeder import seed_demo_baseline_if_needed
            seed_demo_baseline_if_needed(repo)
        except Exception as err:
            logger.warning("Demo seeder failed during startup: %s", err)

    server = create_server(host, port)
    bound_host, bound_port = server.server_address
    logger.info("Project Sentinel Backend service starting on http://%s:%d", bound_host, bound_port)
    logger.info("Health check endpoint available at: http://%s:%d/health", bound_host, bound_port)
    logger.info("Readiness endpoint available at: http://%s:%d/ready", bound_host, bound_port)
    if settings.demo_mode:
        logger.info("[MODE] Public Demo Mode ENABLED: Real pipeline execution on synthetic fixtures only.")
    if settings.static_dir and os.path.isdir(settings.static_dir):
        logger.info("[STATIC] Serving frontend assets directly from: %s", settings.static_dir)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down Project Sentinel Backend service...")
        server.shutdown()
        server.server_close()
        logger.info("Server terminated cleanly.")


if __name__ == "__main__":
    run_server()
