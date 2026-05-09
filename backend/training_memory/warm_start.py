"""Resolve a likely checkpoint path from a historical catalog run."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from training_memory.db import get_connection, get_training_run, init_db


def resolve_warm_start_checkpoint(parent_job_id: str) -> Optional[Path]:
    """
    Resolve the newest .pkl artifact under the parent run directory.

    This remains a best-effort helper: missing artifacts safely return None.
    """
    conn = get_connection()
    try:
        init_db(conn)
        row = get_training_run(conn, parent_job_id)
    finally:
        conn.close()

    if not row:
        return None

    mm_path = Path(str(row.get("master_memory_path") or "")).resolve()
    if not mm_path.exists():
        return None

    run_dir = mm_path.parent
    training_dir = run_dir / "training"

    def _latest_pkl(directory: Path) -> Optional[Path]:
        if not directory.exists():
            return None
        candidates = sorted(
            directory.glob("*.pkl"),
            key=lambda p: p.stat().st_mtime,
        )
        return candidates[-1] if candidates else None

    hit = _latest_pkl(training_dir)
    if hit:
        return hit.resolve()

    fallback = sorted(
        run_dir.rglob("*.pkl"),
        key=lambda p: p.stat().st_mtime,
    )
    return fallback[-1].resolve() if fallback else None
