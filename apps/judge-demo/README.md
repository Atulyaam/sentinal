# Project Sentinel — Judge Demo Surface

This directory hosts the standalone, synthetic-only demo environment for Kiroween 2026 judges.

## Judge Demo Safety Guarantees
- **Synthetic Data Only:** No local operator files or private log inboxes are ever accessible from this demo surface.
- **Read-Only Investigation:** Pre-configured scenarios (Credential Storm, Privilege Jump, Web Enumeration) can be selected, replayed, and inspected.
- **Claim Guard Showcase:** Demonstrates deterministic verification and blocked claims without needing any API keys or local software installation.

Scheduled for full synthetic fixture hosting in Sprint 8 per the Master Plan.
In Phase 1, the shared application shell is compiled from `apps/crew-app/` and runs standalone via `npm run preview`.
