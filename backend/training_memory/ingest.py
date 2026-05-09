"""Ingest one training run into the catalog from per-job master_memory.json (read-only)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from training_memory.db import (
    catalog_db_path,
    get_connection,
    init_db,
    upsert_training_run,
)
from training_memory.fingerprints import compute_fingerprints


def _utc_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def record_run_after_preprocess(job_id: str, master_memory_path: Path) -> None:
    """
    Read master_memory.json for this job, compute fingerprints, upsert catalog row.

    Raises on failure; caller should catch and log.
    Does not modify master_memory.json.
    """
    path = Path(master_memory_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"master_memory not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        master: Dict[str, Any] = json.load(fh)

    target_norm, context_hash, schema_hash, task_type, fingerprints_json = (
        compute_fingerprints(master)
    )

    conn = get_connection()
    try:
        init_db(conn)
        upsert_training_run(
            conn,
            job_id=job_id,
            created_at=_utc_iso(),
            target_column=target_norm or (master.get("target_column") or "")[:512],
            context_hash=context_hash,
            schema_hash=schema_hash,
            task_type=task_type,
            master_memory_path=str(path),
            fingerprints_json=fingerprints_json,
        )
    finally:
        conn.close()


def catalog_path_for_display() -> str:
    """Resolved default or env path (for logs)."""
    return str(catalog_db_path().resolve())
