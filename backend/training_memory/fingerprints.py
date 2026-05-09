"""Derive stable fingerprints from read-only master_memory dict (post-preprocess)."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional, Tuple


def _sha256_utf8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_target(name: Optional[str]) -> str:
    if not name or not isinstance(name, str):
        return ""
    return name.strip().lower()


def _schema_signature(preprocessing: Dict[str, Any]) -> str:
    """
    Canonical signature from preprocessing.report.columns:
    sorted column names with dtypes (excluding heavy stats).
    """
    report = preprocessing.get("report") or {}
    cols = report.get("columns") or {}
    if not isinstance(cols, dict):
        return ""
    parts: list[tuple[str, str]] = []
    for col_name in sorted(cols.keys()):
        meta = cols.get(col_name) or {}
        if not isinstance(meta, dict):
            dtype = ""
        else:
            dtype = str(meta.get("dtype", "") or "")
        parts.append((str(col_name), dtype))
    return json.dumps(parts, sort_keys=False, separators=(",", ":"))


def compute_fingerprints(master: Dict[str, Any]) -> Tuple[str, str, str, Optional[str], str]:
    """
    Returns:
        target_normalized, context_hash, schema_hash, task_type, fingerprints_json
    """
    target_raw = master.get("target_column")
    target_norm = _normalize_target(
        target_raw if isinstance(target_raw, str) else None
    )

    ctx = master.get("context_of_dataset")
    if isinstance(ctx, str):
        context_hash = _sha256_utf8(ctx.strip())
    else:
        context_hash = _sha256_utf8("")

    prep = master.get("preprocessing") or {}
    if not isinstance(prep, dict):
        prep = {}

    schema_sig = _schema_signature(prep)
    schema_hash = _sha256_utf8(schema_sig) if schema_sig else _sha256_utf8("")

    tt = master.get("task_type")
    task_type: Optional[str] = tt.strip().lower() if isinstance(tt, str) and tt.strip() else None

    blob = {
        "target_normalized": target_norm,
        "context_hash": context_hash,
        "schema_hash": schema_hash,
        "task_type": task_type,
        "schema_signature_preview": schema_sig[:2000] if schema_sig else "",
    }
    fingerprints_json = json.dumps(blob, separators=(",", ":"))

    return target_norm, context_hash, schema_hash, task_type, fingerprints_json
