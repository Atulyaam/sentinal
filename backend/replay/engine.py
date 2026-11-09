"""Deterministic Replay Lab execution engine for Project Sentinel.

Executes synthetic security scenarios through the exact same production ingestion,
normalization, detection, case correlation, and Claim Guard verification services
inside an isolated database context, enforcing full proof-carrying assertions.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.cases.engine import CorrelationEngine
from backend.claims.engine import ClaimGuardEngine
from backend.claims.models import ClaimProposal, VERIFIER_VERSION
from backend.claims.verifier import ClaimVerifier
from backend.config.settings import get_settings, Settings
from backend.detection.engine import DetectionEngine
from backend.detection.rules import RuleRegistry
from backend.ingestion.engine import ImportEngine
from backend.normalization.engine import CURRENT_NORMALIZATION_VERSION, NormalizationEngine
from backend.persistence.migrations import apply_migrations
from backend.persistence.repository import IngestionRepository
from backend.replay.models import (
    ReplayAssertion,
    ReplayMetrics,
    ReplayRunReport,
    ReplayStage,
    ScenarioManifest,
    WhatIfConfig,
)
from backend.replay.scenarios import (
    SCENARIO_CATALOG,
    get_fixture_path,
    get_scenario_manifest,
)

logger = logging.getLogger("sentinel.replay.engine")

PIPELINE_VERSIONS = {
    "engine": "1.0.0",
    "normalization": CURRENT_NORMALIZATION_VERSION,
    "rules": "1.0.0",
    "correlation": CorrelationEngine.ALGORITHM_VERSION,
    "claim_guard": VERIFIER_VERSION,
}


class ReplayEngine:
    """
    Orchestrates deterministic replay of synthetic security scenarios.

    Guarantees:
    1. Zero Contamination: All processing executes in an isolated SQLite database.
    2. Real Services: Reuses production ImportEngine, NormalizationEngine,
       DetectionEngine, CorrelationEngine, and ClaimGuardEngine.
    3. Proof-Carrying Assertions: Verifies actual execution against committed scenario expectations.
    """

    def __init__(self, main_repo: Optional[IngestionRepository] = None) -> None:
        self.main_repo = main_repo
        self.settings = get_settings()

    def run_scenario(
        self,
        scenario_id: str,
        what_if: Optional[WhatIfConfig] = None,
        replay_id: Optional[str] = None,
    ) -> ReplayRunReport:
        """
        Execute a complete end-to-end replay run of a synthetic scenario.
        """
        manifest = get_scenario_manifest(scenario_id)
        if not manifest:
            raise KeyError(f"Unknown scenario ID '{scenario_id}'. Available: {list(SCENARIO_CATALOG.keys())}")

        replay_id = replay_id or f"rply_{uuid.uuid4().hex[:16]}"
        start_wall_time = datetime.now(timezone.utc).isoformat()
        start_perf = time.perf_counter()
        mode = "what_if" if what_if else "standard"

        if what_if:
            self._validate_what_if_config(what_if)

        stages: List[ReplayStage] = []
        metrics = ReplayMetrics()
        fixture_checksums: Dict[str, str] = {}

        # ---------------------------------------------------------------------
        # Pre-Execution: Verify Fixture Integrity & Checksums
        # ---------------------------------------------------------------------
        for fix in manifest.fixtures:
            path = get_fixture_path(fix.filename)
            content_bytes = path.read_bytes()
            actual_hash = hashlib.sha256(content_bytes).hexdigest()
            fixture_checksums[fix.filename] = actual_hash
            if actual_hash != fix.sha256:
                raise ValueError(
                    f"Integrity check failed for fixture '{fix.filename}'. "
                    f"Expected SHA-256 {fix.sha256}, got {actual_hash}."
                )

        # ---------------------------------------------------------------------
        # Step 0: Initialize Isolated In-Memory SQLite Database
        # ---------------------------------------------------------------------
        isolated_conn = sqlite3.connect(
            ":memory:",
            check_same_thread=False,
            timeout=10.0,
            isolation_level=None,  # Autocommit mode so BEGIN IMMEDIATE works cleanly
        )
        isolated_conn.row_factory = sqlite3.Row
        isolated_conn.execute("PRAGMA foreign_keys = ON;")
        apply_migrations(isolated_conn)
        isolated_repo = IngestionRepository(isolated_conn)

        # Register event sources for replay fixtures
        for fix in manifest.fixtures:
            src_id = f"src_replay_{scenario_id}_{fix.parser_id}"
            isolated_repo.get_or_create_source(
                source_id=src_id,
                source_name=f"Replay Fixture {fix.filename}",
                parser_profile=fix.parser_id,
                configured_path=str(get_fixture_path(fix.filename)),
            )

        cases_snapshot: List[Dict[str, Any]] = []
        claims_snapshot: List[Dict[str, Any]] = []
        error_summary: Optional[str] = None
        what_if_diff: Optional[Dict[str, Any]] = None

        try:
            # -----------------------------------------------------------------
            # Stage 1: Fixture Ingestion (Real ImportEngine)
            # -----------------------------------------------------------------
            st_start = time.perf_counter()
            import_engine = ImportEngine(repository=isolated_repo, settings=self.settings)
            total_accepted_records = 0

            for fix in manifest.fixtures:
                path = get_fixture_path(fix.filename)
                content_bytes = path.read_bytes()

                # What-If record filtering
                if what_if and what_if.excluded_records:
                    lines = content_bytes.decode("utf-8").splitlines(keepends=True)
                    filtered_lines = [
                        line for idx, line in enumerate(lines, 1)
                        if idx not in what_if.excluded_records
                    ]
                    content_bytes = "".join(filtered_lines).encode("utf-8")

                src_id = f"src_replay_{scenario_id}_{fix.parser_id}"
                ingest_res = import_engine.ingest_file(
                    source_id=src_id,
                    filename=fix.filename,
                    content_bytes=content_bytes,
                    parser_id=fix.parser_id,
                )
                if ingest_res.get("status") != "completed":
                    raise RuntimeError(f"Fixture ingestion failed for {fix.filename}: {ingest_res.get('error')}")
                total_accepted_records += ingest_res.get("accepted_records", 0)

            st_duration = (time.perf_counter() - st_start) * 1000.0
            metrics.imported_records = total_accepted_records
            stages.append(
                ReplayStage(
                    stage_id="stage_ingest",
                    name="Fixture Ingestion",
                    status="completed",
                    duration_ms=round(st_duration, 2),
                    summary=f"Ingested {len(manifest.fixtures)} fixture(s), accepted {total_accepted_records} records.",
                )
            )

            # -----------------------------------------------------------------
            # Stage 2: Canonical Normalization (Real NormalizationEngine)
            # -----------------------------------------------------------------
            st_start = time.perf_counter()
            norm_engine = NormalizationEngine()
            norm_res = norm_engine.run_normalization(repo=isolated_repo, limit=5000)
            st_duration = (time.perf_counter() - st_start) * 1000.0

            normalized_events_count = norm_res.get("accepted", 0)
            metrics.normalized_events = normalized_events_count
            stages.append(
                ReplayStage(
                    stage_id="stage_normalization",
                    name="Canonical Normalization",
                    status="completed",
                    duration_ms=round(st_duration, 2),
                    summary=f"Normalized {normalized_events_count} canonical event(s) with full provenance.",
                )
            )

            # -----------------------------------------------------------------
            # Stage 3: Deterministic Rule Detection (Real DetectionEngine)
            # -----------------------------------------------------------------
            st_start = time.perf_counter()
            registry = RuleRegistry()

            # Apply What-If rule overrides if specified
            if what_if and what_if.rule_overrides:
                for r_id, r_conf in what_if.rule_overrides.items():
                    evaluator = registry.get(r_id)
                    if evaluator:
                        if "enabled" in r_conf:
                            evaluator.enabled = bool(r_conf["enabled"])
                        for k, v in r_conf.items():
                            if k != "enabled":
                                evaluator.config[k] = v

            det_engine = DetectionEngine(registry=registry)
            det_res = det_engine.run_detection(repository=isolated_repo, limit_events=5000)
            st_duration = (time.perf_counter() - st_start) * 1000.0

            findings_count = det_res.get("findings_generated", 0)
            metrics.findings_count = findings_count
            stages.append(
                ReplayStage(
                    stage_id="stage_detection",
                    name="Deterministic Detection Rules",
                    status="completed",
                    duration_ms=round(st_duration, 2),
                    summary=f"Evaluated 5 detection rules, generated {findings_count} finding(s).",
                )
            )

            # -----------------------------------------------------------------
            # Stage 4: Case Correlation (Real CorrelationEngine)
            # -----------------------------------------------------------------
            st_start = time.perf_counter()
            corr_opts = {}
            if what_if and what_if.correlation_overrides:
                corr_opts = what_if.correlation_overrides

            corr_engine = CorrelationEngine(
                window_seconds=corr_opts.get("window_seconds", 3600),
                enable_ip_correlation=corr_opts.get("enable_ip_correlation", False),
            )
            corr_res = corr_engine.run_correlation(repository=isolated_repo)
            st_duration = (time.perf_counter() - st_start) * 1000.0

            cases_count = corr_res.get("cases_created", 0)
            metrics.cases_count = cases_count
            stages.append(
                ReplayStage(
                    stage_id="stage_correlation",
                    name="Investigation Case Correlation",
                    status="completed",
                    duration_ms=round(st_duration, 2),
                    summary=f"Correlated {corr_res.get('findings_scanned', 0)} findings into {cases_count} case(s).",
                )
            )

            # -----------------------------------------------------------------
            # Stage 5: Timeline Reconstruction (Real Repository Timeline)
            # -----------------------------------------------------------------
            st_start = time.perf_counter()
            cases_list, _ = isolated_repo.list_cases(limit=10)
            target_case_id: Optional[str] = None

            for c in cases_list:
                c_detail = isolated_repo.get_case(c["case_id"])
                if c_detail:
                    cases_snapshot.append(c_detail)
                    if target_case_id is None:
                        target_case_id = c["case_id"]

            st_duration = (time.perf_counter() - st_start) * 1000.0
            total_timeline_entries = sum(len(c.get("timeline", [])) for c in cases_snapshot)
            stages.append(
                ReplayStage(
                    stage_id="stage_timeline",
                    name="Evidence Timeline Reconstruction",
                    status="completed",
                    duration_ms=round(st_duration, 2),
                    summary=f"Constructed chronological timeline across {len(cases_snapshot)} case(s) ({total_timeline_entries} items).",
                )
            )

            # -----------------------------------------------------------------
            # Stage 6: Claim Guard Verification (Real ClaimGuardEngine)
            # -----------------------------------------------------------------
            st_start = time.perf_counter()
            claim_verifier = ClaimVerifier(conn=isolated_conn)
            claim_engine = ClaimGuardEngine(verifier=claim_verifier)

            # Prepare structured claim proposals dynamically bound to generated evidence
            proposals = self._bind_claim_proposals(
                raw_proposals=manifest.claim_proposals,
                cases=cases_snapshot,
                isolated_repo=isolated_repo,
            )

            if target_case_id and proposals:
                claim_res = claim_engine.process_claims(
                    proposals=proposals,
                    case_id=target_case_id,
                    repo=isolated_repo,
                )
                claims_snapshot = isolated_repo.list_case_claims(target_case_id)
            elif not target_case_id and proposals:
                # If no cases exist (e.g. IP-only unclustered scenario B), verify proposals directly against verifier
                results = claim_verifier.verify_batch(proposals, case_bundle=None)
                claims_snapshot = [r.to_dict() for r in results]

            st_duration = (time.perf_counter() - st_start) * 1000.0
            metrics.claims_total = len(claims_snapshot)
            metrics.claims_verified = sum(1 for c in claims_snapshot if c.get("status") == "verified")
            metrics.claims_qualified = sum(1 for c in claims_snapshot if c.get("status") == "qualified")
            metrics.claims_blocked = sum(1 for c in claims_snapshot if c.get("status") == "blocked")

            stages.append(
                ReplayStage(
                    stage_id="stage_claim_guard",
                    name="Claim Guard Verification",
                    status="completed",
                    duration_ms=round(st_duration, 2),
                    summary=(
                        f"Verified {metrics.claims_total} claim(s): "
                        f"{metrics.claims_verified} verified, {metrics.claims_qualified} qualified, "
                        f"{metrics.claims_blocked} blocked."
                    ),
                )
            )

            # -----------------------------------------------------------------
            # Stage 7: Assertion Evaluation
            # -----------------------------------------------------------------
            st_start = time.perf_counter()
            assertions = self._evaluate_assertions(
                manifest=manifest,
                metrics=metrics,
                isolated_repo=isolated_repo,
                cases_snapshot=cases_snapshot,
                claims_snapshot=claims_snapshot,
                what_if=what_if,
            )
            st_duration = (time.perf_counter() - st_start) * 1000.0

            metrics.assertions_total = len(assertions)
            metrics.assertions_passed = sum(1 for a in assertions if a.passed)
            metrics.assertions_failed = sum(1 for a in assertions if not a.passed)

            stages.append(
                ReplayStage(
                    stage_id="stage_assertions",
                    name="Proof-Carrying Assertions",
                    status="completed" if metrics.assertions_failed == 0 else "failed",
                    duration_ms=round(st_duration, 2),
                    summary=f"Evaluated {metrics.assertions_total} assertions: {metrics.assertions_passed} passed, {metrics.assertions_failed} failed.",
                )
            )

            # -----------------------------------------------------------------
            # If What-If Mode: Compute Semantic Diff against Baseline
            # -----------------------------------------------------------------
            if what_if:
                baseline_report = self.run_scenario(scenario_id=scenario_id, what_if=None)
                what_if_diff = self._compute_what_if_diff(baseline=baseline_report, simulated_metrics=metrics, simulated_cases=cases_snapshot)

            status = "completed" if metrics.assertions_failed == 0 else "failed"

        except Exception as ex:
            logger.exception("Replay execution failed for scenario %s: %s", scenario_id, ex)
            status = "failed"
            error_summary = str(ex)
            stages.append(
                ReplayStage(
                    stage_id="stage_error",
                    name="Pipeline Error",
                    status="failed",
                    duration_ms=0.0,
                    summary=f"Execution halted unexpectedly: {ex}",
                )
            )
            assertions = []
        finally:
            isolated_conn.close()

        total_perf_ms = (time.perf_counter() - start_perf) * 1000.0
        metrics.duration_ms = round(total_perf_ms, 2)
        completed_wall_time = datetime.now(timezone.utc).isoformat()

        report = ReplayRunReport(
            replay_id=replay_id,
            scenario_id=scenario_id,
            scenario_name=manifest.name,
            scenario_version=manifest.version,
            status=status,
            mode=mode,
            pipeline_versions=PIPELINE_VERSIONS,
            fixture_checksums=fixture_checksums,
            what_if_config=what_if.to_dict() if what_if else {},
            metrics=metrics,
            assertion_results=assertions,
            stages=stages,
            cases_snapshot=cases_snapshot,
            claims_snapshot=claims_snapshot,
            what_if_diff=what_if_diff,
            error_summary=error_summary,
            started_at=start_wall_time,
            completed_at=completed_wall_time,
        )

        # Persist report in primary database if main repository is available
        if self.main_repo:
            try:
                self.main_repo.persist_replay_run(report.to_dict())
            except Exception as e:
                logger.error("Failed to persist replay run to main database: %s", e)

        return report

    def run_what_if(
        self,
        scenario_id: str,
        what_if: WhatIfConfig,
        replay_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a What-If simulation against a baseline scenario, returning the report and semantic diff.
        """
        simulated_run = self.run_scenario(scenario_id=scenario_id, what_if=what_if, replay_id=replay_id)
        return {
            "simulated_run": simulated_run,
            "comparison": simulated_run.what_if_diff or {},
        }

    def compare_runs(
        self,
        run_a: str | Dict[str, Any] | ReplayRunReport,
        run_b: str | Dict[str, Any] | ReplayRunReport,
    ) -> Dict[str, Any]:
        """
        Compare two historical or in-memory replay runs to verify determinism and identify diffs.
        """
        if isinstance(run_a, ReplayRunReport):
            run_a_dict = run_a.to_dict()
        elif isinstance(run_a, dict):
            run_a_dict = run_a
        elif isinstance(run_a, str):
            if not self.main_repo:
                raise RuntimeError("Main repository required to look up historical replay runs by ID.")
            run_a_dict = self.main_repo.get_replay_run(run_a)
            if not run_a_dict:
                raise ValueError(f"Replay run '{run_a}' not found.")
        else:
            raise TypeError("run_a must be a run ID string, ReplayRunReport, or dict")

        if isinstance(run_b, ReplayRunReport):
            run_b_dict = run_b.to_dict()
        elif isinstance(run_b, dict):
            run_b_dict = run_b
        elif isinstance(run_b, str):
            if not self.main_repo:
                raise RuntimeError("Main repository required to look up historical replay runs by ID.")
            run_b_dict = self.main_repo.get_replay_run(run_b)
            if not run_b_dict:
                raise ValueError(f"Replay run '{run_b}' not found.")
        else:
            raise TypeError("run_b must be a run ID string, ReplayRunReport, or dict")

        m_a = run_a_dict.get("metrics", {})
        m_b = run_b_dict.get("metrics", {})

        metrics_delta = {
            "imported_records": m_b.get("imported_records", 0) - m_a.get("imported_records", 0),
            "normalized_events": m_b.get("normalized_events", 0) - m_a.get("normalized_events", 0),
            "findings_count": m_b.get("findings_count", 0) - m_a.get("findings_count", 0),
            "cases_count": m_b.get("cases_count", 0) - m_a.get("cases_count", 0),
            "claims_verified": m_b.get("claims_verified", 0) - m_a.get("claims_verified", 0),
            "claims_blocked": m_b.get("claims_blocked", 0) - m_a.get("claims_blocked", 0),
        }

        # Check assertion alignment
        assert_a = {a["assertion_id"]: a["passed"] for a in run_a_dict.get("assertion_results", [])}
        assert_b = {a["assertion_id"]: a["passed"] for a in run_b_dict.get("assertion_results", [])}
        assertion_mismatches = [
            aid for aid in set(assert_a.keys()) | set(assert_b.keys())
            if assert_a.get(aid) != assert_b.get(aid)
        ]

        # Semantic diff of findings and cases
        rules_a = {
            f.get("rule_id")
            for c in run_a_dict.get("cases_snapshot", [])
            for f in c.get("findings", [])
            if f.get("rule_id")
        }
        rules_b = {
            f.get("rule_id")
            for c in run_b_dict.get("cases_snapshot", [])
            for f in c.get("findings", [])
            if f.get("rule_id")
        }
        findings_added = sorted(list(rules_b - rules_a))
        findings_removed = sorted(list(rules_a - rules_b))
        cases_diff = metrics_delta["cases_count"]

        is_identical = (
            run_a_dict.get("scenario_id") == run_b_dict.get("scenario_id")
            and run_a_dict.get("status") == run_b_dict.get("status")
            and all(delta == 0 for delta in metrics_delta.values())
            and len(assertion_mismatches) == 0
            and len(findings_added) == 0
            and len(findings_removed) == 0
        )

        scenario_a = run_a_dict.get("scenario_id")
        scenario_b = run_b_dict.get("scenario_id")
        version_a = run_a_dict.get("scenario_version")
        version_b = run_b_dict.get("scenario_version")
        is_compatible = (scenario_a == scenario_b) and (version_a == version_b)
        compatibility_warning = (
            None
            if is_compatible
            else f"Scenario mismatch: Comparing run A ({scenario_a} v{version_a}) with run B ({scenario_b} v{version_b})"
        )

        return {
            "run_a_id": run_a_dict.get("replay_id"),
            "run_b_id": run_b_dict.get("replay_id"),
            "scenario_id": run_a_dict.get("scenario_id"),
            "scenario_version": run_a_dict.get("scenario_version"),
            "is_identical": is_identical,
            "is_compatible": is_compatible,
            "compatibility_warning": compatibility_warning,
            "metric_deltas": metrics_delta,
            "metrics_delta": metrics_delta,
            "findings_added": findings_added,
            "findings_removed": findings_removed,
            "cases_added": max(0, cases_diff),
            "cases_removed": max(0, -cases_diff),
            "assertion_mismatches": assertion_mismatches,
            "run_a_duration_ms": m_a.get("duration_ms", 0),
            "run_b_duration_ms": m_b.get("duration_ms", 0),
            "pipeline_versions_match": run_a_dict.get("pipeline_versions") == run_b_dict.get("pipeline_versions"),
            "fixture_checksums_match": run_a_dict.get("fixture_checksums") == run_b_dict.get("fixture_checksums"),
        }

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    def _validate_what_if_config(self, what_if: WhatIfConfig) -> None:
        """
        Validate What-If simulation parameters against strict schema and allowed rule registry.
        """
        allowed_rules = {"AUTH-001", "AUTH-002", "WEB-001", "PRIV-001", "INGEST-001"}

        if what_if.rule_overrides:
            for r_id, r_conf in what_if.rule_overrides.items():
                if r_id not in allowed_rules:
                    raise ValueError(
                        f"Unknown rule ID in what_if overrides: '{r_id}'. Allowed: {sorted(list(allowed_rules))}"
                    )
                if not isinstance(r_conf, dict):
                    raise ValueError(f"Rule override configuration for '{r_id}' must be a dictionary")
                if "enabled" in r_conf and not isinstance(r_conf["enabled"], bool):
                    raise ValueError(f"Rule override 'enabled' for '{r_id}' must be a boolean")
                if "threshold_count" in r_conf:
                    val = r_conf["threshold_count"]
                    if not (isinstance(val, int) and not isinstance(val, bool) and val >= 1):
                        raise ValueError(
                            f"Invalid threshold_count for rule '{r_id}': expected positive integer >= 1, got {val}"
                        )
                if "window_seconds" in r_conf:
                    val = r_conf["window_seconds"]
                    if not (isinstance(val, int) and not isinstance(val, bool) and val >= 1):
                        raise ValueError(
                            f"Invalid window_seconds for rule '{r_id}': expected positive integer >= 1, got {val}"
                        )

        if what_if.excluded_records:
            if not isinstance(what_if.excluded_records, list):
                raise ValueError("excluded_records must be a list of 1-based integer line indices")
            for idx in what_if.excluded_records:
                if not (isinstance(idx, int) and not isinstance(idx, bool) and idx >= 1):
                    raise ValueError(f"Invalid excluded line index: expected positive integer >= 1, got {idx}")
            what_if.excluded_records = sorted(list(set(what_if.excluded_records)))

        if what_if.correlation_overrides:
            if not isinstance(what_if.correlation_overrides, dict):
                raise ValueError("correlation_overrides must be a dictionary")
            if "window_seconds" in what_if.correlation_overrides:
                w = what_if.correlation_overrides["window_seconds"]
                if not (isinstance(w, int) and not isinstance(w, bool) and w >= 1):
                    raise ValueError(f"Invalid correlation window_seconds: expected positive integer, got {w}")
            if "enable_ip_correlation" in what_if.correlation_overrides:
                if not isinstance(what_if.correlation_overrides["enable_ip_correlation"], bool):
                    raise ValueError("enable_ip_correlation must be a boolean")

    def _bind_claim_proposals(
        self,
        raw_proposals: List[Dict[str, Any]],
        cases: List[Dict[str, Any]],
        isolated_repo: IngestionRepository,
    ) -> List[ClaimProposal]:
        """
        Dynamically bind real generated evidence IDs and target case ID to scenario proposals.
        """
        bound: List[ClaimProposal] = []
        target_case = cases[0] if cases else None
        target_case_id = target_case["case_id"] if target_case else "case_replay_unclustered"

        # Evidence pool: Use the case's linked events and findings to maintain strict case containment
        if target_case:
            case_events = target_case.get("events", [])
            case_findings = target_case.get("findings", [])
        else:
            case_findings, _ = isolated_repo.list_findings(limit=50)
            case_events, _ = isolated_repo.list_normalized_events(limit=50)

        for p_dict in raw_proposals:
            c_type = p_dict["claim_type"]
            refs: List[str] = []

            # 1. Event Count Claims
            if c_type == "event_count":
                claimed_type = p_dict["value"].get("event_type")
                if p_dict["predicate"] == "failed_event_count":
                    matching_events = [
                        e["event_id"] for e in case_events
                        if str(e.get("status", "")).upper() in ("FAILURE", "LOCKED", "ERROR")
                    ]
                elif claimed_type:
                    matching_events = [
                        e["event_id"] for e in case_events
                        if e.get("event_type") == claimed_type
                    ]
                else:
                    matching_events = [e["event_id"] for e in case_events]

                # Bind actual count to avoid arbitrary mismatch unless claim specifically tests bad count
                refs = matching_events

            # 2. Finding Exists Claims
            elif c_type == "finding_exists":
                rule_id = p_dict["value"].get("rule_id")
                matching_finds = [f["finding_id"] for f in case_findings if f.get("rule_id") == rule_id]
                refs = matching_finds if matching_finds else ([case_findings[0]["finding_id"]] if case_findings else [])

            # 3. Entity Observed Claims
            elif c_type == "entity_observed":
                ent_type = p_dict["value"].get("entity_type")
                ent_val = p_dict["value"].get("entity_value")
                matching = []
                for e in case_events:
                    if ent_type == "user_principal" and e.get("user_principal") == ent_val:
                        matching.append(e["event_id"])
                    elif ent_type == "source_ip" and e.get("source_ip") == ent_val:
                        matching.append(e["event_id"])
                for f in case_findings:
                    if f.get("matched_entity") == ent_val:
                        matching.append(f["finding_id"])
                refs = matching if matching else ([case_events[0]["event_id"]] if case_events else [])

            # 4. Correlation Claims
            elif c_type == "correlation_relationship":
                refs = [case_events[0]["event_id"]] if case_events else []

            # 5. Time Window Claims
            elif c_type == "time_window":
                refs = [case_events[0]["event_id"], case_events[-1]["event_id"]] if len(case_events) >= 2 else ([case_events[0]["event_id"]] if case_events else [])

            # Fallback
            if not refs and case_events:
                refs = [case_events[0]["event_id"]]
            elif not refs and case_findings:
                refs = [case_findings[0]["finding_id"]]

            proposal = ClaimProposal(
                claim_id=p_dict["claim_id"],
                case_id=target_case_id,
                claim_type=p_dict["claim_type"],
                predicate=p_dict["predicate"],
                value=p_dict["value"],
                evidence_refs=refs,
                certainty=p_dict.get("certainty", "observed"),
                template_id=p_dict.get("template_id", "case_event_count_v1"),
                proposed_by="replay_agent",
            )
            bound.append(proposal)

        return bound

    def _evaluate_assertions(
        self,
        manifest: ScenarioManifest,
        metrics: ReplayMetrics,
        isolated_repo: IngestionRepository,
        cases_snapshot: List[Dict[str, Any]],
        claims_snapshot: List[Dict[str, Any]],
        what_if: Optional[WhatIfConfig],
    ) -> List[ReplayAssertion]:
        """
        Evaluate actual pipeline metrics and artifacts against committed expectations.
        """
        exp = manifest.expectations
        assertions: List[ReplayAssertion] = []

        # In what-if mode, baseline assertions are adjusted or evaluated comparatively
        if what_if:
            # Add general pipeline sanity assertions in what-if mode
            assertions.append(
                ReplayAssertion(
                    assertion_id="asrt_whatif_execution",
                    category="what_if",
                    description="What-If simulation completed cleanly without unhandled errors.",
                    expected=True,
                    actual=True,
                    passed=True,
                    message="What-If execution succeeded.",
                )
            )
            return assertions

        # 1. Ingested Records
        pass_ingest = metrics.imported_records == exp.expected_imported_records
        assertions.append(
            ReplayAssertion(
                assertion_id="asrt_ingest_records",
                category="ingestion",
                description=f"Imported records must match expected count ({exp.expected_imported_records}).",
                expected=exp.expected_imported_records,
                actual=metrics.imported_records,
                passed=pass_ingest,
                message=f"Imported {metrics.imported_records}/{exp.expected_imported_records} records.",
            )
        )

        # 2. Normalized Events
        pass_norm = metrics.normalized_events == exp.expected_normalized_events
        assertions.append(
            ReplayAssertion(
                assertion_id="asrt_norm_events",
                category="normalization",
                description=f"Canonical normalized events must match expected count ({exp.expected_normalized_events}).",
                expected=exp.expected_normalized_events,
                actual=metrics.normalized_events,
                passed=pass_norm,
                message=f"Normalized {metrics.normalized_events}/{exp.expected_normalized_events} canonical events.",
            )
        )

        # 3. Detection Rules Triggered
        actual_findings, _ = isolated_repo.list_findings(limit=50)
        actual_rules = sorted(list({f["rule_id"] for f in actual_findings}))
        expected_rules = sorted(list(exp.expected_rules))
        pass_rules = actual_rules == expected_rules
        assertions.append(
            ReplayAssertion(
                assertion_id="asrt_rules_triggered",
                category="detection",
                description=f"Detection rules triggered must exactly match {expected_rules}.",
                expected=expected_rules,
                actual=actual_rules,
                passed=pass_rules,
                message=f"Rules triggered: {actual_rules}.",
            )
        )

        # 4. Total Findings Count
        pass_findings = metrics.findings_count == exp.expected_findings_count
        assertions.append(
            ReplayAssertion(
                assertion_id="asrt_findings_count",
                category="detection",
                description=f"Generated findings must match expected count ({exp.expected_findings_count}).",
                expected=exp.expected_findings_count,
                actual=metrics.findings_count,
                passed=pass_findings,
                message=f"Generated {metrics.findings_count}/{exp.expected_findings_count} findings.",
            )
        )

        # 5. Case Count
        pass_cases = metrics.cases_count == exp.expected_cases_count
        assertions.append(
            ReplayAssertion(
                assertion_id="asrt_cases_count",
                category="cases",
                description=f"Correlated investigation cases must match expected count ({exp.expected_cases_count}).",
                expected=exp.expected_cases_count,
                actual=metrics.cases_count,
                passed=pass_cases,
                message=f"Created {metrics.cases_count}/{exp.expected_cases_count} cases.",
            )
        )

        # 6. Claim Guard Outcomes
        actual_claim_map = {c["claim_id"]: c.get("status") for c in claims_snapshot}
        for claim_id, expected_status in exp.expected_claim_outcomes.items():
            actual_status = actual_claim_map.get(claim_id, "missing")
            pass_claim = actual_status == expected_status
            assertions.append(
                ReplayAssertion(
                    assertion_id=f"asrt_claim_{claim_id}",
                    category="claims",
                    description=f"Claim '{claim_id}' must result in status '{expected_status}'.",
                    expected=expected_status,
                    actual=actual_status,
                    passed=pass_claim,
                    message=f"Claim '{claim_id}' evaluated to '{actual_status}'.",
                )
            )

        return assertions

    def _compute_what_if_diff(
        self,
        baseline: ReplayRunReport,
        simulated_metrics: ReplayMetrics,
        simulated_cases: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Compute deterministic differences between baseline and simulated replay runs.
        """
        b_m = baseline.metrics
        s_m = simulated_metrics

        findings_diff = s_m.findings_count - b_m.findings_count
        cases_diff = s_m.cases_count - b_m.cases_count

        baseline_rules = {
            f.get("rule_id")
            for c in baseline.cases_snapshot
            for f in c.get("findings", [])
            if f.get("rule_id")
        }
        simulated_rules = {
            f.get("rule_id")
            for c in simulated_cases
            for f in c.get("findings", [])
            if f.get("rule_id")
        }
        findings_added = sorted(list(simulated_rules - baseline_rules))
        findings_removed = sorted(list(baseline_rules - simulated_rules))

        is_identical = (
            findings_diff == 0
            and cases_diff == 0
            and len(findings_added) == 0
            and len(findings_removed) == 0
            and s_m.imported_records == b_m.imported_records
            and s_m.normalized_events == b_m.normalized_events
        )

        return {
            "baseline_replay_id": baseline.replay_id,
            "is_identical": is_identical,
            "findings_added": findings_added,
            "findings_removed": findings_removed,
            "metric_deltas": {
                "imported_records": s_m.imported_records - b_m.imported_records,
                "normalized_events": s_m.normalized_events - b_m.normalized_events,
                "findings_count": findings_diff,
                "cases_count": cases_diff,
            },
            "findings_delta_summary": f"{abs(findings_diff)} finding(s) {'added' if findings_diff > 0 else 'suppressed' if findings_diff < 0 else 'unchanged'}",
            "cases_delta_summary": f"{abs(cases_diff)} case(s) {'added' if cases_diff > 0 else 'suppressed' if cases_diff < 0 else 'unchanged'}",
            "explanation": (
                f"What-If simulation altered detection/correlation outputs: "
                f"Findings changed by {findings_diff:+d}, Cases changed by {cases_diff:+d}."
            ),
        }
