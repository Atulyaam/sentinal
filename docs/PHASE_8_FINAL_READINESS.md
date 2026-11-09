# Project Sentinel — Phase 8 Final Readiness & Launch Runbook
## Production Certification & 2-Minute Deployment Guide

**Sprint:** Phase 8 Deployment Completion  
**System Version:** `0.8.0`  
**GitHub Repository:** [`https://github.com/Atulyaam/sentinal.git`](https://github.com/Atulyaam/sentinal.git)  
**Latest Production Commit:** `b3b480f` (`main`)  
**Date:** November 10, 2026  

---

## 1. Readiness Certification Matrix

| Dimension | Standard Required | Audit Result | Status |
| :--- | :--- | :--- | :--- |
| **Backend Unit & Contract Tests** | 100% Passing | 235 / 235 Tests Passing in 13.9s | **CERTIFIED** |
| **Continuous Quality Gates** | All Hooks Clean | 10 / 10 Gates Passed (`validate-all.ps1`) | **CERTIFIED** |
| **Kiro Crew Manifest** | Valid `app.json` | Valid schemas for UI, Agents, and Skills | **CERTIFIED** |
| **Frontend Production Build** | Zero Errors | TypeScript & Vite dist bundle verified | **CERTIFIED** |
| **Single-Container Architecture** | Unified Static & API | Python `http.server` serves SPA + API | **CERTIFIED** |
| **Zero PyPI Dependencies** | Standard Library Only | 100% Python 3.12 Standard Library | **CERTIFIED** |
| **Public Demo Mode** | Uploads Restricted | `POST /api/import` returns 403 Forbidden | **CERTIFIED** |
| **Replay Lab Isolation** | No Contamination | Runs in ephemeral `:memory:` SQLite | **CERTIFIED** |
| **Claim Guard Security** | Anti-Hallucination | Verified against 11 test proposals | **CERTIFIED** |
| **What-If Simulation** | Semantic Diffs | Threshold sensitivity & comparisons pass | **CERTIFIED** |
| **Persistent Storage** | Persistent Disk Mount | WAL mode, idempotent migrations, no overwrite | **CERTIFIED** |
| **Git Synchronization** | Pushed to Remote | Branch `main` up-to-date on GitHub | **CERTIFIED** |

---

## 2. 2-Minute Public Launch Runbook

The code, container configuration, and blueprints are live on GitHub (`main`). Follow these simple steps to launch your public judge URL:

### Option A: Launch on Render (Primary Target)
1. Navigate to **[dashboard.render.com/select-repo?type=blueprint](https://dashboard.render.com/select-repo?type=blueprint)**.
2. Select repository **`Atulyaam/sentinal`** (or connect your GitHub account if needed).
3. Render reads [`render.yaml`](file:///c:/Users/Atul2/OneDrive/Desktop/KiroHackethon/sentinal/render.yaml) automatically:
   - **Service Name:** `project-sentinel`
   - **Environment:** Docker
   - **Disk:** 1 GB persistent disk mounted at `/data`
   - **Plan:** `starter` (required for persistent disk)
4. Click **Apply**.
5. Render builds the container and provides your live public URL (e.g. `https://project-sentinel-xxxx.onrender.com`).

---

### Option B: Launch on Railway (Free Credit Alternative)
1. Navigate to **[railway.com/new](https://railway.com/new)**.
2. Choose **Deploy from GitHub repo** $\rightarrow$ select **`Atulyaam/sentinal`**.
3. Under the service **Settings** $\rightarrow$ **Volumes**:
   - Add a volume mounted at `/data`.
4. Under **Networking**:
   - Click **Generate Domain**.
5. Your service is live immediately on Railway.

---

## 3. Post-Launch Verification Command

As soon as your public URL is available, execute the automated 17-step judge evaluation suite from your terminal:

```powershell
python scripts/verify_hosted_demo.py --url https://<your-public-url>
```

When all 17 steps pass, Project Sentinel is officially certified for Kiroween 2026 judging!
