"""Decision layer for optional warm-start selection from training catalog."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from training_memory.compatibility import evaluate_candidate_compatibility
from training_memory.db import get_connection, get_training_run, init_db
from training_memory.similarity import find_similar_runs
from training_memory.warm_start import resolve_warm_start_checkpoint


@dataclass
class WarmStartDecision:
    enabled: bool
    policy: str
    decision: str
    reason: str
    candidate_job_id: Optional[str] = None
    candidate_match_tier: Optional[str] = None
    candidate_checkpoint_path: Optional[str] = None
    checks: Dict[str, bool] = field(default_factory=dict)
    checks_failed: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _is_enabled() -> bool:
    raw = os.environ.get("TRAINING_MEMORY_DECISION_ENABLED", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _policy() -> str:
    return os.environ.get("TRAINING_MEMORY_POLICY", "none").strip().lower() or "none"


def _model_family_token(name: Optional[str]) -> str:
    if not name:
        return ""
    s = name.strip().lower().replace("-", "_").replace(" ", "_")
    known = [
        "random_forest",
        "xgboost",
        "lightgbm",
        "catboost",
        "gradient_boosting",
        "ridge",
        "lasso",
        "elasticnet",
        "logistic_regression",
        "svm",
        "knn",
        "decision_tree",
    ]
    for token in known:
        if token in s:
            return token
    return s


def decide_warm_start(
    job_id: str,
    *,
    requested_model_name: Optional[str] = None,
    limit: int = 15,
) -> WarmStartDecision:
    """
    Decide if a historical checkpoint can be reused for this job.

    This function is read-only and safe to call even when catalog is incomplete.
    """
    enabled = _is_enabled()
    policy = _policy()
    if not enabled:
        return WarmStartDecision(
            enabled=False,
            policy=policy,
            decision="cold_start",
            reason="decision_disabled",
        )
    if policy not in {"warm_start_if_compatible"}:
        return WarmStartDecision(
            enabled=True,
            policy=policy,
            decision="cold_start",
            reason="policy_none_or_unsupported",
        )

    anchor_found, similar = find_similar_runs(job_id, limit=limit)
    if not anchor_found:
        return WarmStartDecision(
            enabled=True,
            policy=policy,
            decision="cold_start",
            reason="anchor_not_found",
        )
    if not similar:
        return WarmStartDecision(
            enabled=True,
            policy=policy,
            decision="cold_start",
            reason="no_similar_runs",
        )

    conn = get_connection()
    try:
        init_db(conn)
        anchor_row = get_training_run(conn, job_id)
    finally:
        conn.close()

    if not anchor_row:
        return WarmStartDecision(
            enabled=True,
            policy=policy,
            decision="cold_start",
            reason="anchor_row_missing",
        )

    for candidate in similar:
        result = evaluate_candidate_compatibility(
            anchor_row=anchor_row,
            candidate_row=candidate,
        )
        if not result.compatible:
            continue

        candidate_id = str(candidate.get("job_id") or "")
        checkpoint = resolve_warm_start_checkpoint(candidate_id) if candidate_id else None
        if not checkpoint:
            return WarmStartDecision(
                enabled=True,
                policy=policy,
                decision="cold_start",
                reason="compatible_but_no_checkpoint_found",
                candidate_job_id=candidate_id or None,
                candidate_match_tier=candidate.get("match_tier"),
                checks=result.checks,
                checks_failed=result.reasons,
            )

        req_family = _model_family_token(requested_model_name)
        cand_family = _model_family_token(checkpoint.stem.replace("_full", ""))
        if req_family and cand_family and req_family != cand_family:
            continue

        return WarmStartDecision(
            enabled=True,
            policy=policy,
            decision="reuse_checkpoint_candidate",
            reason="compatible_candidate_found",
            candidate_job_id=candidate_id,
            candidate_match_tier=candidate.get("match_tier"),
            candidate_checkpoint_path=str(checkpoint),
            checks=result.checks,
            checks_failed=result.reasons,
        )

    return WarmStartDecision(
        enabled=True,
        policy=policy,
        decision="cold_start",
        reason="all_candidates_incompatible",
    )
