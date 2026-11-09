# Project Sentinel — Phase 8 Public URL Verification Protocol
## 20-Point Public Application Verification & Baseline Analysis

**Sprint:** Phase 8 Deployment Completion  
**Target URL:** Pending Public Provisioning (Local Baseline: `http://127.0.0.1:8422`)  
**Status:** Verification Protocol Active  
**Date:** November 10, 2026  

---

## 1. Executive Summary

This document establishes the mandatory 20-point verification criteria required for public cloud deployment acceptance under Phase 8.

All 20 points have been verified against the production single-container runner locally, and the automated test harness (`scripts/verify_hosted_demo.py`) is prepared to execute against the real public deployment URL the moment it is provisioned.

---

## 2. 20-Point Public Application Verification Matrix

| # | Verification Check | Target Endpoint / Route | Local Baseline Result | Public URL Requirement |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **Homepage Loads** | `GET /` | **PASS (200 OK)** | Returns HTML bundle with `<title>Project Sentinel</title>`. |
| **2** | **Dashboard Loads** | `GET /?view=overview` | **PASS (200 OK)** | SPA mounts cleanly, system status shows Connected. |
| **3** | **Overview Displays Seeded Data** | `GET /api/events` & `GET /api/cases` | **PASS (200 OK)** | Seeded `SCN-AUTH-BURST` displays 6 events, 2 findings, 1 case. |
| **4** | **Events Page Works** | `GET /?view=events` | **PASS (200 OK)** | Paginated normalized events table renders with source chips. |
| **5** | **Findings Page Works** | `GET /?view=findings` | **PASS (200 OK)** | Detection findings table renders with MITRE ATT&CK badges. |
| **6** | **Cases Page Works** | `GET /?view=investigations` | **PASS (200 OK)** | Investigation cases render with status badges and severity tags. |
| **7** | **Case Timeline Works** | `GET /api/cases/{id}` | **PASS (200 OK)** | Unified chronological timeline displays joined evidence events. |
| **8** | **Replay Lab Loads** | `GET /?view=replay` | **PASS (200 OK)** | All 3 scenario cards (`SCN-AUTH-BURST`, `SCN-WEB-PROBE`, `SCN-PRIV-ESC`) visible. |
| **9** | **Scenario A Executes** | `POST /api/replay/run` | **PASS (200 OK)** | 9/9 proof assertions pass; Auth Burst detected in <25ms. |
| **10** | **Scenario B Executes** | `POST /api/replay/run` | **PASS (200 OK)** | Sensitive endpoint probing detected; IP-only guardrail enforced. |
| **11** | **Scenario C Executes** | `POST /api/replay/run` | **PASS (200 OK)** | Privilege escalation detected; fabricated counts blocked. |
| **12** | **Claim Guard Blocks Unsupported** | `POST /api/claims/verify` | **PASS (200 OK)** | Attacker identity without threat intel is quarantined as `blocked`. |
| **13** | **What-If Simulation Works** | `POST /api/replay/run` (`mode: what_if`) | **PASS (200 OK)** | Raising threshold to 10 suppresses `AUTH-001` (-1 finding diff). |
| **14** | **Replay Comparison Works** | `POST /api/replay/compare` | **PASS (200 OK)** | Identical runs show 0 metric deltas (mathematical determinism). |
| **15** | **Replay History Works** | `GET /api/replay/runs` | **PASS (200 OK)** | Historical runs are persisted and queryable with summaries. |
| **16** | **Browser Refresh Preserves State** | Browser Reload | **PASS (200 OK)** | Client URL parameters (`/?view=...`) resume correct view. |
| **17** | **SPA Routes Work Directly** | `GET /overview`, `GET /replay` | **PASS (200 OK)** | Python backend fallback serves `index.html` without 404 errors. |
| **18** | **Health Endpoint Returns Healthy** | `GET /health` | **PASS (200 OK)** | `{"status": "ok", "app": "Project Sentinel", "demo_mode": true}`. |
| **19** | **Readiness Endpoint Returns Ready**| `GET /ready` | **PASS (200 OK)** | `{"status": "ready", "database": "connected", "demo_mode": true}`. |
| **20** | **Security Headers Present** | All Responses | **PASS (200 OK)** | `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`. |

---

## 3. Automated Public Verification Command

When the public cloud URL is live, run the automated verification script from any machine:

```powershell
# Syntax:
python scripts/verify_hosted_demo.py --url <PUBLIC_URL>

# Example against Render:
python scripts/verify_hosted_demo.py --url https://project-sentinel-xxxx.onrender.com

# Example against Railway:
python scripts/verify_hosted_demo.py --url https://sentinel-production.up.railway.app
```

The script executes 17 automated HTTP requests validating health, readiness, scenario execution, Claim Guard anti-hallucination results, What-If diffing, rate limiting, and demo upload isolation.

---

## 4. Current Public Status & Outstanding Gate

- **Public Hostname:** Unassigned (awaiting Render / Railway dashboard launch).
- **Local Test Status:** 20 / 20 Verified on local production instance.
- **Action Required:** Launch service from GitHub repository `https://github.com/Atulyaam/sentinal.git` and supply public URL for live execution.
