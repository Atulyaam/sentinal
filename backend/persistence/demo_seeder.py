"""Automatic synthetic baseline seeder for Project Sentinel Public Demo Mode.

Ensures that judges opening the application on a fresh deployment immediately
experience populated events, findings, cases, and Claim Guard verifications
without having to run any manual commands or wait for file ingestion.
"""
from __future__ import annotations

import logging
from typing import Optional

from backend.cases.engine import CorrelationEngine
from backend.claims.engine import ClaimGuardEngine
from backend.claims.models import ClaimProposal
from backend.claims.verifier import ClaimVerifier
from backend.config.settings import get_settings
from backend.detection.engine import DetectionEngine
from backend.ingestion.engine import ImportEngine
from backend.normalization.engine import NormalizationEngine
from backend.persistence.repository import IngestionRepository
from backend.replay.engine import ReplayEngine
from backend.replay.scenarios import SCENARIO_A, get_fixture_path

logger = logging.getLogger("sentinel.demo_seeder")


def seed_demo_baseline_if_needed(repo: IngestionRepository) -> bool:
    """
    If running in a fresh database with 0 cases and 0 replay runs, execute
    the baseline synthetic scenario (SCN-AUTH-BURST) so that judges landing
    on the application immediately see populated events, findings, cases, and claims.
    """
    try:
        cases, total_cases = repo.list_cases(limit=1)
        runs, total_runs = repo.list_replay_runs(limit=1)

        if total_cases == 0 and total_runs == 0:
            logger.info("Initializing public demo baseline: seeding Scenario A synthetic dataset...")
            settings = get_settings()

            # 1. Register synthetic demo source
            src_id = "src_demo_synthetic_auth"
            repo.get_or_create_source(
                source_id=src_id,
                source_name="Synthetic Demo: Authentication Logs",
                parser_profile="auth_csv",
                configured_path="fixtures/scenarios/scenario_a_auth_burst.csv",
            )

            # 2. Ingest Scenario A fixture
            fix_path = get_fixture_path("scenario_a_auth_burst.csv")
            content_bytes = fix_path.read_bytes()
            import_engine = ImportEngine(repository=repo, settings=settings)
            ingest_res = import_engine.ingest_file(
                source_id=src_id,
                filename="scenario_a_auth_burst.csv",
                content_bytes=content_bytes,
                parser_id="auth_csv",
            )
            logger.info("Demo seeder ingested fixture: %s", ingest_res.get("status"))

            # 3. Canonical Normalization
            norm_engine = NormalizationEngine()
            norm_res = norm_engine.run_normalization(repo=repo)
            logger.info("Demo seeder normalized events: %d accepted", norm_res.get("accepted", 0))

            # 4. Deterministic Detection
            det_engine = DetectionEngine()
            det_res = det_engine.run_detection(repository=repo)
            logger.info("Demo seeder generated findings: %d", det_res.get("findings_generated", 0))

            # 5. Correlation into Investigation Case
            corr_engine = CorrelationEngine()
            corr_res = corr_engine.run_correlation(repository=repo)
            logger.info("Demo seeder created cases: %d", corr_res.get("cases_created", 0))

            # 6. Verify Claim Guard Proposals for the Case
            cases_list, _ = repo.list_cases(limit=1)
            if cases_list:
                target_case = cases_list[0]
                case_id = target_case["case_id"]
                proposals = []
                for p_dict in SCENARIO_A.claim_proposals:
                    p_copy = dict(p_dict)
                    p_copy["case_id"] = case_id
                    p = ClaimProposal.from_dict(p_copy)
                    proposals.append(p)

                claim_engine = ClaimGuardEngine(verifier=ClaimVerifier(conn=repo.conn))
                claim_res = claim_engine.process_claims(proposals=proposals, case_id=case_id, repo=repo)
                logger.info(
                    "Demo seeder processed Claim Guard: %d verified, %d qualified, %d blocked",
                    claim_res.get("verified_count", 0),
                    claim_res.get("qualified_count", 0),
                    claim_res.get("blocked_count", 0),
                )

            # 7. Also record baseline in Replay Lab history
            replay_engine = ReplayEngine(main_repo=repo)
            replay_engine.run_scenario("SCN-AUTH-BURST")

            logger.info("Public demo baseline successfully initialized for judge evaluation.")
            return True

        return False
    except Exception as ex:
        logger.warning("Could not initialize demo baseline: %s", ex, exc_info=True)
        return False
