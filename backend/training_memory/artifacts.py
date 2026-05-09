"""Artifact lineage and promotion helpers for training memory."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from training_memory.db import (
    clear_promoted_for_model,
    get_best_artifact_for_model,
    get_connection,
    init_db,
    upsert_training_artifact,
)


@dataclass
class ArtifactRegisterResult:
    is_promoted: bool
    previous_best_score: Optional[float]
    current_score: Optional[float]


def _utc_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def register_artifact(
    *,
    job_id: str,
    model_name: str,
    artifact_path: Path,
    parent_job_id: Optional[str],
    metric_name: Optional[str],
    metric_value: Optional[float],
    metric_score: Optional[float],
    promotion_delta: float = 0.0,
) -> ArtifactRegisterResult:
    conn = get_connection()
    try:
        init_db(conn)
        best = get_best_artifact_for_model(conn, model_name)
        best_score: Optional[float] = None
        if best and best.get("metric_score") is not None:
            try:
                best_score = float(best["metric_score"])
            except (TypeError, ValueError):
                best_score = None

        should_promote = False
        if best_score is None:
            should_promote = True
        elif metric_score is not None and metric_score >= (best_score + promotion_delta):
            should_promote = True

        if should_promote:
            clear_promoted_for_model(conn, model_name)

        upsert_training_artifact(
            conn,
            job_id=job_id,
            model_name=model_name,
            artifact_path=str(artifact_path.resolve()),
            artifact_hash=file_sha256(artifact_path),
            parent_job_id=parent_job_id,
            metric_name=metric_name,
            metric_value=metric_value,
            metric_score=metric_score,
            is_promoted=should_promote,
            created_at=_utc_iso(),
        )
        return ArtifactRegisterResult(
            is_promoted=should_promote,
            previous_best_score=best_score,
            current_score=metric_score,
        )
    finally:
        conn.close()
