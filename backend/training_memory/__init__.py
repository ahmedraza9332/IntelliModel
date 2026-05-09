"""Training run catalog: read-only ingest from per-job master_memory.json (v1)."""

from training_memory.ingest import record_run_after_preprocess

__all__ = [
    "record_run_after_preprocess",
]
