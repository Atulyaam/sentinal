# Steering Directive — Product Strategy & Boundaries
**Project Sentinel — Kiroween 2026**

## 1. Product Audience
Project Sentinel is built for:
- Small engineering teams running production workloads without a dedicated 24/7 Security Operations Center (SOC).
- Student security laboratories and computer science researchers learning evidence-based triage.
- Independent developers requiring defensible, transparent investigation of suspicious authentication or access anomalies.

## 2. Product Promise
> **Project Sentinel turns approved security logs into an evidence-linked investigation that a human can understand, replay, challenge and review. It detects explainable patterns, shows exactly which records support each finding, and refuses to present an AI-generated claim unless its structured evidence checks pass.**

Headline differentiator: **Proof-Carrying Investigation**. Sentinel does not ask operators to trust its AI. It verifies structured claims against deterministic event evidence before rendering them as facts.

## 3. P0 Scope (Mandatory Capabilities)
1. **Local-First Inbox Ingestion:** Parse structured JSONL/CSV authentication and web access logs from an explicitly approved local directory.
2. **Deterministic Detection Rules:** Execute versioned, inspectable rules with transparent thresholds and condition matching.
3. **Evidence-Linked Case Timeline:** Correlate findings and raw events into a coherent timeline with explicit relationship labels.
4. **Constrained AI Investigator:** Kiro Crew agent that produces typed claim objects only, never free-form unverified prose.
5. **Deterministic Claim Guard:** Recomputes entity counts, time windows, and supporting record IDs from the case bundle; blocks unsupported claims.
6. **Reproducible Replay Lab:** Re-executes synthetic fixtures and asserts identical findings and verified claim outputs.
7. **Read-Only Judge Demo:** Safe, synthetic scenario browser preview requiring no local filesystem access, private logs, or secrets.

## 4. Explicit Non-Goals (Out of Scope)
- **No autonomous remediation:** Sentinel does not execute firewall rules, kill processes, ban IPs, or alter remote state.
- **No arbitrary shell execution:** Never invoke arbitrary commands or subshells.
- **No vulnerability or network scanning:** No port scanning, nmap, or network probing.
- **No enterprise SIEM replacement:** We do not build a distributed log cluster, broad syslog listener, or multi-tenant fleet manager.
- **No unconstrained chat agent:** No conversational chatbot that hallucinates unverified claims about raw log data.
- **No fake metrics:** No fabricated threat percentages, simulated incidents presented as live data, or artificial KPI counters.

