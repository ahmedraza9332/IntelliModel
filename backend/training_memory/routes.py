"""Optional HTTP surface for the training catalog (read-only queries)."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Query

from training_memory.similarity import find_similar_runs

router = APIRouter(prefix="/api/training", tags=["training"])


@router.get("/similar/{job_id}")
def get_similar_runs(
    job_id: str,
    limit: int = Query(15, ge=1, le=50),
) -> Dict[str, Any]:
    """
    Return catalog rows similar to the given job_id (requires ingest row).

    Does not read master_memory at request time beyond what is already in SQLite.
    """
    anchor_found, similar = find_similar_runs(job_id, limit=limit)
    return {
        "job_id": job_id,
        "anchor_found": anchor_found,
        "count": len(similar),
        "similar": similar,
    }
