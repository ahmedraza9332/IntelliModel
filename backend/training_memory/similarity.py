"""Rank prior catalog rows against a reference job (read-only queries)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from training_memory.db import get_connection, init_db


def _public_row(row: Any) -> Dict[str, Any]:
    """Omit fingerprints_json from API payload by default (caller can trim)."""
    d = {k: row[k] for k in row.keys()}
    d.pop("fingerprints_json", None)
    return d


def find_similar_runs(job_id: str, limit: int = 15) -> tuple[bool, List[Dict[str, Any]]]:
    """
    Return (anchor_found, ranked_similar).

    Precedence:
      tier 1 — same schema_hash (strong structural match)
      tier 2 — same target_column + same task_type (when anchor has task_type)
      tier 3 — same target_column only

    Excludes the anchor job_id. Dedupes by job_id; preserves tier order.
    """
    conn = get_connection()
    try:
        init_db(conn)
        cur = conn.execute(
            "SELECT * FROM training_runs WHERE job_id = ?",
            (job_id,),
        )
        anchor = cur.fetchone()
        if anchor is None:
            return False, []

        anchor_s = anchor["schema_hash"]
        anchor_t = anchor["target_column"]
        anchor_tt: Optional[str] = anchor["task_type"]
        seen: set[str] = {job_id}
        out: List[Dict[str, Any]] = []

        def _append_rows(rows: Any, tier: str) -> None:
            nonlocal out
            for row in rows:
                jid = row["job_id"]
                if jid in seen:
                    continue
                seen.add(jid)
                item = _public_row(row)
                item["match_tier"] = tier
                out.append(item)
                if len(out) >= limit:
                    return

        cur = conn.execute(
            """
            SELECT * FROM training_runs
            WHERE job_id != ? AND schema_hash = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (job_id, anchor_s, limit),
        )
        _append_rows(cur.fetchall(), "schema_hash")

        if len(out) < limit and anchor_tt:
            cur = conn.execute(
                """
                SELECT * FROM training_runs
                WHERE job_id != ? AND target_column = ?
                  AND COALESCE(task_type, '') = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (job_id, anchor_t, anchor_tt, limit),
            )
            _append_rows(cur.fetchall(), "target_and_task_type")

        if len(out) < limit:
            cur = conn.execute(
                """
                SELECT * FROM training_runs
                WHERE job_id != ? AND target_column = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (job_id, anchor_t, limit * 2),
            )
            _append_rows(cur.fetchall(), "target_column")

        return True, out[:limit]
    finally:
        conn.close()
