# Steering Directive — Security, Privacy & Safety
**Project Sentinel — Kiroween 2026**

## 1. Local-First Boundary & Source Consent
- **Approved Inbox Only:** Sentinel only ingests files from a single, explicitly approved local inbox path confirmed by the operator.
- **Directory Traversal Defense:** All target paths are strictly canonicalized (`os.path.realpath`) and verified against the approved inbox boundary. Symlink or junction escapes outside the boundary must be rejected immediately.
- **Forbidden Directories:** Filesystem roots (`C:\`, `/`), user home directories (`~`), and system directories (`Windows`, `Program Files`, `/etc`, `/usr`) are prohibited as inbox locations.
- **Non-Recursive Default:** Subdirectory scanning is disabled unless explicitly consented to.

## 2. Untrusted Data Handling & Input Sanitation
- **Zero Trust for Log Content:** All imported text (filenames, user-agents, request paths, IPs, usernames, error messages) is treated as potentially adversarial input.
- **Safe Parsing:** Enforce strict byte limits (max 50 MB per file, max 10,000 records per batch) and validate UTF-8 encoding. Never execute code during parsing.
- **Prompt Injection Defense:** AI agents never receive raw unparsed log strings as system instructions. Log fields are packaged into structured, bounded JSON data objects marked explicitly as untrusted evidence.

## 3. Privacy & Secret Containment
- **Automatic Redaction:** Authorization headers, bearer tokens, passwords, cookies, and secret keys must be redacted before persistence or transmission to an agent context.
- **Synthetic Data for Demos:** The public judge demo and CI test suites use synthetic fixtures only. Real operational logs or private operator telemetry must never be committed or hosted.
- **No Unconsented External Egress:** Sentinel does not send log contents to external cloud endpoints without explicit, informed operator configuration.

## 4. Remediation Safety
- **No Autonomous Remediation:** Sentinel is strictly an investigative and triage workbench. It does not block IP addresses, alter firewall configurations, terminate system processes, or modify external services.
- **Human in the Loop:** All triage status transitions (e.g. Reviewed, False Positive, Escalated) require explicit operator review.

