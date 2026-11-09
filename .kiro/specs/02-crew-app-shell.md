# Kiro Specification: 02-crew-app-shell
**Status:** In Progress (Phase 1 Baseline)  
**Parent Plan:** `Project_Sentinel_Kiroween_2026_WINNING_MASTER_PLAN_v3.md`  
**Owner:** Senior Full-Stack Engineer  

---

## 1. Overview & Objective
This specification defines the frontend application shell for Project Sentinel. It establishes the navigation architecture, responsive layout, visual styling, backend connectivity monitoring, and state handling across all views.

The shell must conform to the **Kiro Crew App Kit** specification for native host integration while supporting a standalone preview mode for independent verification and the hosted judge demo.

---

## 2. Navigation Architecture & Route Contract

The application shell provides 8 distinct navigation views:

| Index | View | Route | Purpose | Phase 1 Status |
|---|---|---|---|---|
| 1 | **Overview** | `/` (or `/apps/project-sentinel`) | System status, backend connectivity, empty state, workflow guidance | IMPLEMENTED (Active) |
| 2 | **Investigations** | `/investigations` | Active cases, evidence timelines, operator review actions | Planned State |
| 3 | **Findings** | `/findings` | Rule detections, matching conditions, supporting event references | Planned State |
| 4 | **Events** | `/events` | Raw normalized records, byte offsets, provenance hashes | Planned State |
| 5 | **Replay Lab** | `/replay` | Deterministic synthetic scenario player and verification runner | Planned State |
| 6 | **Sources** | `/sources` | Approved inbox folder configuration, scan pause/resume controls | Planned State |
| 7 | **Digests** | `/digests` | Periodic summary reports, typed Claim Guard audit log | Planned State |
| 8 | **Settings** | `/settings` | Redaction rules, API URLs, log level, environment bounds | Planned State |

For routes scheduled for future phases (2 through 8), the view displays a clean, transparent "Planned Feature" state describing the upcoming capability and its planned sprint. It strictly avoids fake data or dummy buttons.

---

## 3. UI Shell Architecture & Kiro Crew Integration

### 3.1 Kiro Crew Manifest (`app.json`)
The canonical manifest declares:
- `name`: `project-sentinel`
- `ui.entry`: `dist/index.mjs`
- `ui.pages`: Registered route `/apps/project-sentinel`
- `agents`: `agents/sentinel-investigator.json`
- `skills`: `skills/evidence-led-investigation`
- `permissions`: Declares allowed `/api/health`, `/api/status`, `/api/cases`, etc.

### 3.2 Host Dependencies & Externalization
Per App Kit documentation, the Kiro Crew dashboard host injects:
- `react`, `react-dom`, `react/jsx-runtime`
- `@kirocrew/app-sdk`
- `lucide-react`
The Vite configuration externalizes these packages in library mode (`formats: ['es']`).
In standalone demo mode, local package dependencies provide seamless rendering.

---

## 4. Design Decisions & Visual Standards
- **Surface Palette:** Dark graphite (`#0B0D11`, `#11141B`, `#161B22`) with hairline borders (`#21262D`).
- **Accent:** Controlled cobalt blue (`#388BFD`) for active states.
- **Iconography:** Clean SVG vector icons (Lucide-style); strict prohibition of emojis in interface controls.
- **Backend Connectivity:** Real-time ping to `GET /health` with visual status indicator (Connected / Connecting / Disconnected).

---

## 5. Implementation Tasks

- [x] Scaffold `apps/crew-app` directory structure.
- [x] Author valid `app.json` manifest following App Kit reference.
- [x] Configure Vite build with ESM output and externals handling.
- [x] Build sidebar navigation supporting all 8 routes with keyboard navigation.
- [x] Build Overview dashboard with genuine backend health status check.
- [x] Implement planned state screens for upcoming modules.
- [x] Build loading, empty, and backend offline state handling.
- [x] Verify production build and TypeScript compilation.

