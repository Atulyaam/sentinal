# Project Sentinel — Demonstration Runbook

**Target Audience:** Kiroween 2026 Judges & Technical Reviewers  
**Current Phase:** Phase 1 (Foundation & Application Shell)  

---

## 1. Quickstart (One Command Demo Launcher)

To launch both the backend service and the frontend preview simultaneously:

```powershell
python scripts/run_demo.py
```

This starts the Sentinel backend on `http://127.0.0.1:8000/health` and provides instructions to open the frontend.

---

## 2. Independent Component Launch

### Step A: Start the Backend Service
From the repository root:
```powershell
python -m backend.api.server
```
- Listens on `http://127.0.0.1:8000`.
- Health endpoint: `http://127.0.0.1:8000/health`.
- Test with curl or browser:
  ```powershell
  curl http://127.0.0.1:8000/health
  ```
  Expected output:
  ```json
  {
    "app": "Project Sentinel",
    "status": "ok",
    "version": "0.1.0",
    "environment": "development",
    "timestamp": "2026-11-09T...Z"
  }
  ```

### Step B: Launch the Frontend Workbench Shell
In a new terminal window:
```powershell
cd apps/crew-app
npm run dev
```
- Open `http://localhost:5173` in any modern browser.
- The top header will immediately show **Backend Connected (v0.1.0)** with a green indicator pill.
- If you stop the backend server, clicking **Check Connectivity** or waiting for the 30s poll will transition the status indicator to **Backend Unavailable** with recovery guidance.

---

## 3. Verification & Quality Assurance Commands

### Run Full Backend Test Suite
```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```
Runs unit tests for settings, health endpoint, CORS, 404 handling, and contract parity.

### Run Frontend Typecheck & Production Build
```powershell
cd apps/crew-app
npm run typecheck
npm run build
```
- `npm run typecheck` runs TypeScript strict mode with zero errors.
- `npm run build` compiles:
  1. `dist/index.html` (Standalone SPA for judge browser preview).
  2. `dist/index.mjs` (Canonical ESM library bundle for Kiro Crew App Kit).

### Validate Kiro Crew Manifest & Packaged Resources
```powershell
python scripts/validate_manifest.py
```
Validates `apps/crew-app/app.json` against all required fields, entry paths, agent files, and skill folders.

### Run End-to-End Quality Gate Hook
```powershell
powershell -ExecutionPolicy Bypass -File .kiro/hooks/validate-all.ps1
```
Runs the unified quality gate script.

---

## 4. Navigation & View Inspection Guide

1. **Overview View (`/`):**
   - Displays real backend connectivity details (app name, operational status, version, timestamp).
   - Shows genuine investigation empty state explaining how cases are triggered by logs.
   - Provides roadmap cards for upcoming stages (Inbox Ingestion, Detection Rules, Claim Guard).
2. **Roadmap Views (`/investigations`, `/findings`, `/events`, `/replay`, `/sources`, `/digests`, `/settings`):**
   - Transparently indicates the planned sprint delivery according to Non-Negotiable Rule D.
   - Explains the architectural role of each upcoming module.
   - Zero fake mock alerts or placeholder hallucinated graphs.
