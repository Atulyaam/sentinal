# Steering Directive — Testing Strategy & Quality Gates
**Project Sentinel — Kiroween 2026**

## 1. Required Test Types
1. **Unit Tests:** Fast, deterministic checks of configuration parsing, path containment, schema validation, rule evaluation, and claim verification algorithms.
2. **Integration Tests:** End-to-end checks of file ingestion idempotency, database transactions, HTTP endpoint response contracts, and error handling.
3. **Property-Based / Invariant Tests:** Validation of mathematical invariants (e.g. SHA-256 idempotency, path traversal rejection, claim count correctness).
4. **Contract Tests:** Verification that frontend API calls and backend route schemas match identically.
5. **UI & Build Verification:** TypeScript type checks, bundle compilation, and visual state verification across desktop and laptop viewports.

## 2. Non-Negotiable Quality Gates
- **Zero Broken Tests:** All tests in the test suite must pass cleanly.
- **Never Weaken Assertions:** Never delete failing tests or loosen tolerance thresholds to bypass failures. If a test fails, identify the root cause and fix the underlying code.
- **No Mocking of Core Invariants:** Claim Guard verification logic, path canonicalization, and idempotency hashing must be tested against real functions, not dummy mocks.
- **Clean Production Builds:** The frontend build must compile without TypeScript errors or unresolved external imports.
- **Manifest Validation:** The Kiro Crew `app.json` manifest must validate strictly against the App Kit schema.

## 3. Testing Commands Reference
```powershell
# Backend unit & integration test discovery
python -m unittest discover -s tests/unit -p "test_*.py"

# Frontend type checking
cd apps/crew-app
npm run typecheck

# Frontend build verification
npm run build
```

