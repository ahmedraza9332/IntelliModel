"""Compatibility checks for training-memory warm-start candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class CompatibilityResult:
    """Structured compatibility verdict with machine-readable reasons."""

    compatible: bool
    reasons: List[str]
    checks: Dict[str, bool]


def _normalize_str(value: Optional[str]) -> str:
    if not value or not isinstance(value, str):
        return ""
    return value.strip().lower()


def evaluate_candidate_compatibility(
    *,
    anchor_row: Dict[str, Any],
    candidate_row: Dict[str, Any],
) -> CompatibilityResult:
    """
    Evaluate whether a catalog candidate is compatible for warm start.

    Current strict checks rely only on fields guaranteed in training_runs.
    """
    checks: Dict[str, bool] = {}
    reasons: List[str] = []

    anchor_task = _normalize_str(anchor_row.get("task_type"))
    cand_task = _normalize_str(candidate_row.get("task_type"))
    if anchor_task:
        checks["task_type_match"] = anchor_task == cand_task
        if not checks["task_type_match"]:
            reasons.append("task_type_mismatch")
    else:
        checks["task_type_match"] = True

    anchor_target = _normalize_str(str(anchor_row.get("target_column") or ""))
    cand_target = _normalize_str(str(candidate_row.get("target_column") or ""))
    checks["target_column_match"] = anchor_target == cand_target
    if not checks["target_column_match"]:
        reasons.append("target_column_mismatch")

    anchor_schema = str(anchor_row.get("schema_hash") or "")
    cand_schema = str(candidate_row.get("schema_hash") or "")
    checks["schema_hash_match"] = bool(anchor_schema) and anchor_schema == cand_schema
    if not checks["schema_hash_match"]:
        reasons.append("schema_hash_mismatch")

    compatible = all(checks.values())
    return CompatibilityResult(compatible=compatible, reasons=reasons, checks=checks)
