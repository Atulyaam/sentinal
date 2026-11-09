# ==============================================================================
# PROJECT SENTINEL — PRODUCTION DOCKERFILE
# Multi-stage build for unified single-container judge-ready deployment
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Build React/Vite Frontend
# ------------------------------------------------------------------------------
FROM node:20-alpine AS frontend-builder
WORKDIR /build

# Copy frontend package manifests
COPY apps/crew-app/package*.json ./apps/crew-app/
WORKDIR /build/apps/crew-app
RUN npm ci

# Copy full repository source needed for contracts and frontend
WORKDIR /build
COPY shared/ ./shared/
COPY apps/crew-app/ ./apps/crew-app/

# Build static production bundle
WORKDIR /build/apps/crew-app
ENV VITE_API_URL=""
RUN npm run build

# ------------------------------------------------------------------------------
# Stage 2: Production Python Backend & Static Asset Serving
# ------------------------------------------------------------------------------
FROM python:3.12-slim AS runner

# Create non-privileged service user
RUN groupadd -r sentinel && useradd -r -g sentinel -u 10001 sentinel

WORKDIR /app

# Create persistent data volume mount directory
RUN mkdir -p /data && chown -R sentinel:sentinel /data

# Copy backend code, contracts, fixtures, and licenses
COPY backend/ ./backend/
COPY fixtures/ ./fixtures/
COPY shared/ ./shared/
COPY requirements.txt ./

# Copy built frontend assets from builder stage
COPY --from=frontend-builder /build/apps/crew-app/dist ./apps/crew-app/dist

# Fix ownership
RUN chown -R sentinel:sentinel /app

# Switch to non-root user
USER sentinel

# Environment configuration
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SENTINEL_ENV=production \
    SENTINEL_DEMO_MODE=true \
    SENTINEL_DEMO_SEED=true \
    SENTINEL_HOST=0.0.0.0 \
    PORT=8000 \
    SENTINEL_PORT=8000 \
    SENTINEL_DB_PATH=/data/sentinel.db \
    SENTINEL_STATIC_DIR=/app/apps/crew-app/dist

# Expose server port
EXPOSE 8000

# Volume for durable SQLite database persistence
VOLUME ["/data"]

# Native Python healthcheck
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request, os; p = os.getenv('PORT', '8000'); urllib.request.urlopen(f'http://127.0.0.1:{p}/health', timeout=2)" || exit 1

# Start unified Sentinel production server
CMD ["python", "-m", "backend.api.server"]

