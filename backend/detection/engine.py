"""Deterministic Detection Engine for Project Sentinel."""

from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional
import uuid

from backend.detection.models import EvaluationStats, Finding
from backend.detection.rules import RuleRegistry
from backend.persistence.repository import IngestionRepository

logger = logging.getLogger("sentinel.detection.engine")


class DetectionEngine:
    """Orchestrates deterministic rule evaluation against canonical events."""

    def __init__(self, registry: Optional[RuleRegistry] = None) -> None:
        self.registry = registry or RuleRegistry()

    def run_detection(
        self,
        repository: IngestionRepository,
        rule_ids: Optional[List[str]] = None,
        limit_events: int = 5000,
    ) -> Dict[str, Any]:
        """
        Execute rule evaluation across canonical normalized events.

        Args:
            repository: IngestionRepository instance for database queries and persistence.
            rule_ids: Optional list of specific rule IDs to evaluate. If None, all enabled rules run.
            limit_events: Maximum number of canonical events to scan in this evaluation pass.

        Returns:
            Dict containing evaluation statistics and findings count.
        """
        start_time = time.perf_counter()
        eval_id = f"eval_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Determine active rules
        active_evaluators = []
        for rule_def in self.registry.list_rules():
            if not rule_def.enabled:
                continue
            if rule_ids and rule_def.rule_id not in rule_ids:
                continue
            evaluator = self.registry.get(rule_def.rule_id)
            if evaluator:
                active_evaluators.append(evaluator)

        if not active_evaluators:
            logger.info("No active rules to evaluate.")
            return {
                "evaluation_id": eval_id,
                "evaluated_at": now_iso,
                "rule_count": 0,
                "events_scanned": 0,
                "findings_generated": 0,
                "findings_duplicate": 0,
                "duration_ms": 0.0,
            }

        # 2. Query canonical events chronologically
        events, total_events = repository.list_normalized_events(
            limit=limit_events,
            offset=0,
        )
        # Reverse to chronological order (list_normalized_events defaults to timestamp DESC)
        events_chronological = list(reversed(events))

        # Query normalization errors for data quality rules
        normalization_errors = repository.list_normalization_errors(limit=500)

        # 3. Evaluate each rule
        all_findings: List[Finding] = []
        for evaluator in active_evaluators:
            try:
                rule_findings = evaluator.evaluate(events_chronological, normalization_errors)
                all_findings.extend(rule_findings)
                logger.debug(
                    "Rule %s generated %d candidate finding(s).",
                    evaluator.rule_id,
                    len(rule_findings),
                )
            except Exception as err:
                logger.error("Error evaluating rule %s: %s", evaluator.rule_id, err, exc_info=True)

        # 4. Atomically persist findings and evidence junction in SQLite
        persist_stats = repository.persist_findings_batch(all_findings)
        persisted_count = persist_stats["persisted_findings"]
        duplicate_count = persist_stats["duplicate_findings"]

        duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        # 5. Record evaluation audit log
        eval_stats = EvaluationStats(
            evaluation_id=eval_id,
            evaluated_at=now_iso,
            rule_count=len(active_evaluators),
            events_scanned=len(events_chronological),
            findings_generated=persisted_count,
            findings_duplicate=duplicate_count,
            duration_ms=duration_ms,
        )
        repository.record_evaluation_audit(eval_stats)

        logger.info(
            "Detection run %s completed: %d rules, %d events, %d new findings, %d duplicates in %.2fms",
            eval_id,
            len(active_evaluators),
            len(events_chronological),
            persisted_count,
            duplicate_count,
            duration_ms,
        )

        return eval_stats.to_dict()

