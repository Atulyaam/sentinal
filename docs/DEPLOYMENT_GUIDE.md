# Project Sentinel — Production Deployment Guide
## Runbook for Render, Railway, Docker, and Cloud Containers

**Sprint:** Phase 8  
**Applicability:** Production & Demo Hosting  
**Last Verified:** November 10, 2026  

---

## 1. Overview & Architecture Summary

Project Sentinel runs as a **unified single-container service** that combines the compiled React Single Page Application (SPA) and the Python 3.12 HTTP backend into one deployable image.

Key deployment characteristics:
- **Zero Third-Party Python Dependencies:** Built 100% on standard library (`sqlite3`, `http.server`, etc.).
- **Self-Contained Frontend Serving:** The Python backend serves static assets (`/assets/*`) with proper MIME types, security headers (`X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`), and client-side SPA routing fallback to `index.html`.
- **Durable Storage:** SQLite in WAL (Write-Ahead Logging) mode on a persistent mount (`/data/sentinel.db`).
- **Public Demo Mode (`SENTINEL_DEMO_MODE=true`):** Restricts arbitrary file uploads/scanning while enabling 100% authentic pipeline execution on approved synthetic scenarios in the **Replay Lab**.
- **Cold Boot Time:** Under 50ms.
- **Resource Footprint:** < 95 MB RAM, < 100 MB Docker image.

---

## 2. Environment Variables Reference

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `PORT` | `8000` | HTTP port to bind. Cloud platforms (Render, Railway, Fly.io, Cloud Run) set this automatically. |
| `SENTINEL_PORT` | `8000` | Fallback port if `PORT` is not defined. |
| `SENTINEL_HOST` | `0.0.0.0` (prod) / `127.0.0.1` (dev) | Interface to bind. Production defaults to all interfaces. |
| `SENTINEL_ENV` | `production` | Environment tier (`production`, `development`, `test`). |
| `SENTINEL_DEMO_MODE` | `true` (when prod) | When `true`, locks operational file uploads (403 Forbidden) and isolates Replay Lab to approved synthetic fixtures. |
| `SENTINEL_DEMO_SEED` | `true` | When `true`, automatically seeds `SCN-AUTH-BURST` into fresh/empty databases on startup so judges land on an active dashboard. |
| `SENTINEL_DB_PATH` | `/data/sentinel.db` (container) | Absolute path to the SQLite database file. |
| `SENTINEL_STATIC_DIR` | `/app/apps/crew-app/dist` | Directory containing compiled frontend assets. |
| `SENTINEL_RATE_LIMIT_PER_MINUTE` | `60` | Maximum requests per minute per IP on expensive endpoints (`/api/replay/*`, `/api/cases/correlate`). Set to `0` to disable. |
| `SENTINEL_ALLOWED_ORIGINS` | Whitelist (5173, 4173, 5476) | Comma-separated list of additional allowed CORS origins. |

---

## 3. Deployment Options

### Option A: Render (Recommended Blueprint)

The repository includes a ready-to-use [`render.yaml`](file:///c:/Users/Atul2/OneDrive/Desktop/KiroHackethon/sentinal/render.yaml) Blueprint configuration:

1. Push this repository to GitHub or GitLab.
2. In the Render Dashboard, click **New +** -> **Blueprint**.
3. Connect your repository. Render automatically reads `render.yaml`:
   - Service Type: Web Service (Docker)
   - Persistent Disk: 1 GB mounted at `/data`
   - Health Check Path: `/ready`
   - Auto-Deploy: On push to `main`
4. Click **Apply**.
5. Once deployment completes, your public URL will be `https://<app-name>.onrender.com`.

---

### Option B: Railway

The repository includes a [`railway.toml`](file:///c:/Users/Atul2/OneDrive/Desktop/KiroHackethon/sentinal/railway.toml) deployment manifest:

1. In Railway, click **New Project** -> **Deploy from GitHub repo**.
2. Select the Project Sentinel repository.
3. Under **Settings** -> **Volumes**, add a persistent volume:
   - Mount path: `/data`
4. Set Environment Variables:
   - `SENTINEL_ENV`: `production`
   - `SENTINEL_DEMO_MODE`: `true`
   - `SENTINEL_DEMO_SEED`: `true`
   - `SENTINEL_DB_PATH`: `/data/sentinel.db`
5. Railway automatically detects the root `Dockerfile`, builds the multi-stage image, and exposes the service.

---

### Option C: Docker (Local or VPS Deployment)

You can build and run the production image on any Docker-capable host:

```bash
# 1. Build the production Docker image
docker build -t project-sentinel:latest .

# 2. Run the container with a persistent volume on port 8000
docker run -d \
  --name sentinel-production \
  -p 8000:8000 \
  -v sentinel_data:/data \
  -e SENTINEL_ENV=production \
  -e SENTINEL_DEMO_MODE=true \
  -e SENTINEL_DEMO_SEED=true \
  project-sentinel:latest

# 3. View logs
docker logs -f sentinel-production
```

---

### Option D: Docker Compose

Use the provided [`docker-compose.yml`](file:///c:/Users/Atul2/OneDrive/Desktop/KiroHackethon/sentinal/docker-compose.yml):

```bash
# Build and start in detached mode
docker compose up -d --build

# Inspect logs
docker compose logs -f

# Stop container
docker compose down
```

---

### Option E: Bare-Metal / Native Python (No Docker)

If deploying to a traditional Linux/Windows server without Docker:

```bash
# 1. Build the frontend
cd apps/crew-app
npm ci
npm run build
cd ../..

# 2. Run the production server runner
python scripts/run_production_server.py --port 8000 --host 0.0.0.0
```

---

## 4. Post-Deployment Verification (Automated 17-Step Test)

Once deployed to any URL, run the automated verification script from your local machine to confirm 100% operational readiness:

```bash
python scripts/verify_hosted_demo.py --url https://<your-deployed-url>
```

Expected output:
```
================================================================================
 PROJECT SENTINEL — PHASE 8 HOSTED JUDGE VERIFICATION
 Target URL: https://<your-deployed-url>
================================================================================
  [PASS] Step 01: Health Endpoint Check (/health)
  [PASS] Step 02: Readiness Probe Check (/ready)
  [PASS] Step 03: Landing Page & Security Headers (GET /)
  [PASS] Step 04: Query Scenario Catalog (/api/replay/scenarios)
  [PASS] Step 05: Execute Scenario A (SCN-AUTH-BURST)
  [PASS] Step 06: Inspect Scenario A Findings & Cases
  [PASS] Step 07: Verify Claim Guard Anti-Hallucination Results
  [PASS] Step 08: Execute Scenario B (SCN-WEB-PROBE)
  [PASS] Step 09: Execute Scenario C (SCN-PRIV-ESC)
  [PASS] Step 10: Run What-If Simulation (Threshold Sensitivity)
  [PASS] Step 11: Compare Replay Runs Determinism Check (/api/replay/compare)
  [PASS] Step 12: Confirm Replay History Persistence (/api/replay/runs)
  [PASS] Step 13: Verify Safe Replay Reset (/api/replay/reset)
  [PASS] Step 14: Security Guardrail: Block Arbitrary Upload in Demo Mode
  [PASS] Step 15: Security Guardrail: Rate Limiting on Heavy Operations
  [PASS] Step 16: Verify Static Serving & MIME Types
  [PASS] Step 17: Verify SPA Route Fallback (/?view=replay)
================================================================================
 HOSTED JUDGE VERIFICATION SUMMARY: 17/17 STEPS PASSED
================================================================================
```

---

## 5. Maintenance & Troubleshooting

### Database Reset & Re-seeding
To reset the host database back to clean baseline state without redeploying:
1. Hit `POST /api/replay/reset` (purges simulation runs).
2. Or delete `/data/sentinel.db` and restart the container; the `demo_seeder` will automatically recreate migrations and re-seed the baseline scenario.

### Inspecting Container Health
- **Liveness:** `curl -f https://<your-app>/health`
- **Readiness:** `curl -f https://<your-app>/ready`

