"""SQLite catalog for training run fingerprints (separate from auth DB)."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB = _BACKEND_ROOT / "data" / "training_catalog.db"


def catalog_db_path() -> Path:
    raw = os.environ.get("TRAINING_CATALOG_SQLITE_PATH", "").strip()
    return Path(raw) if raw else _DEFAULT_DB


def get_connection() -> sqlite3.Connection:
    path = catalog_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS training_runs (
            job_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            target_column TEXT NOT NULL,
            context_hash TEXT NOT NULL,
            schema_hash TEXT NOT NULL,
            task_type TEXT,
            master_memory_path TEXT NOT NULL,
            fingerprints_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_training_runs_schema_hash
            ON training_runs(schema_hash);
        CREATE INDEX IF NOT EXISTS idx_training_runs_target
            ON training_runs(target_column);
        CREATE INDEX IF NOT EXISTS idx_training_runs_task
            ON training_runs(task_type);

        CREATE TABLE IF NOT EXISTS training_artifacts (
            job_id TEXT NOT NULL,
            model_name TEXT NOT NULL,
            artifact_path TEXT NOT NULL,
            artifact_hash TEXT NOT NULL,
            parent_job_id TEXT,
            metric_name TEXT,
            metric_value REAL,
            metric_score REAL,
            is_promoted INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            PRIMARY KEY (job_id, model_name)
        );

        CREATE INDEX IF NOT EXISTS idx_training_artifacts_model
            ON training_artifacts(model_name);
        CREATE INDEX IF NOT EXISTS idx_training_artifacts_promoted
            ON training_artifacts(is_promoted);
        """
    )
    conn.commit()


def upsert_training_run(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    created_at: str,
    target_column: str,
    context_hash: str,
    schema_hash: str,
    task_type: Optional[str],
    master_memory_path: str,
    fingerprints_json: str,
) -> None:
    conn.execute(
        """
        INSERT INTO training_runs (
            job_id, created_at, target_column, context_hash, schema_hash,
            task_type, master_memory_path, fingerprints_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET
            created_at = excluded.created_at,
            target_column = excluded.target_column,
            context_hash = excluded.context_hash,
            schema_hash = excluded.schema_hash,
            task_type = excluded.task_type,
            master_memory_path = excluded.master_memory_path,
            fingerprints_json = excluded.fingerprints_json
        """,
        (
            job_id,
            created_at,
            target_column,
            context_hash,
            schema_hash,
            task_type,
            master_memory_path,
            fingerprints_json,
        ),
    )
    conn.commit()


def get_training_run(conn: sqlite3.Connection, job_id: str) -> Optional[Dict[str, Any]]:
    """Return one catalog row as a plain dict, or None when absent."""
    cur = conn.execute("SELECT * FROM training_runs WHERE job_id = ?", (job_id,))
    row = cur.fetchone()
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def upsert_training_artifact(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    model_name: str,
    artifact_path: str,
    artifact_hash: str,
    parent_job_id: Optional[str],
    metric_name: Optional[str],
    metric_value: Optional[float],
    metric_score: Optional[float],
    is_promoted: bool,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO training_artifacts (
            job_id, model_name, artifact_path, artifact_hash, parent_job_id,
            metric_name, metric_value, metric_score, is_promoted, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_id, model_name) DO UPDATE SET
            artifact_path = excluded.artifact_path,
            artifact_hash = excluded.artifact_hash,
            parent_job_id = excluded.parent_job_id,
            metric_name = excluded.metric_name,
            metric_value = excluded.metric_value,
            metric_score = excluded.metric_score,
            is_promoted = excluded.is_promoted,
            created_at = excluded.created_at
        """,
        (
            job_id,
            model_name,
            artifact_path,
            artifact_hash,
            parent_job_id,
            metric_name,
            metric_value,
            metric_score,
            1 if is_promoted else 0,
            created_at,
        ),
    )
    conn.commit()


def clear_promoted_for_model(conn: sqlite3.Connection, model_name: str) -> None:
    conn.execute(
        "UPDATE training_artifacts SET is_promoted = 0 WHERE model_name = ?",
        (model_name,),
    )
    conn.commit()


def get_best_artifact_for_model(
    conn: sqlite3.Connection,
    model_name: str,
) -> Optional[Dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT * FROM training_artifacts
        WHERE model_name = ?
        ORDER BY
            is_promoted DESC,
            COALESCE(metric_score, -1e308) DESC,
            created_at DESC
        LIMIT 1
        """,
        (model_name,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}
