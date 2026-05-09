# Training Memory Change Log (2026-05-07)

## Goal
- Restore and verify training-memory wiring after duplicate-file cleanup.
- Keep original pipeline behavior unchanged by default.

## What was changed

### 1) Ingest hook after preprocess (non-blocking)
- File: `backend/api_server.py`
- Behavior:
  - Calls `training_memory.ingest.record_run_after_preprocess(...)` after preprocess completes.
  - Failures log warning only; job continues.

### 2) Warm-start decision in training (non-blocking)
- File: `backend/api_server.py` (`_task_train`)
- Behavior:
  - Calls `training_memory.decision.decide_warm_start(...)`.
  - Logs decision payload to job logs.
  - If decision is `reuse_checkpoint_candidate`, forwards checkpoint path to orchestrator full-training run.
  - Decision failures are warning-only.

### 3) Warm-start env handoff into orchestrator runner
- File: `backend/LLM Orchestrator/llm_orchestrator_workflow_agent.py`
- Behavior:
  - `run_full_training_code(...)` accepts optional `warm_start_checkpoint_path`.
  - Passes `INTELLIMODEL_WARM_START_PATH` via subprocess env when present.

### 4) Artifact registration after training (non-blocking)
- File: `backend/api_server.py` (`_task_train`)
- Behavior:
  - Resolves produced `.pkl` artifact.
  - Extracts a comparable metric score from validation metrics.
  - Registers artifact through `training_memory.artifacts.register_artifact(...)`.
  - Reads `TRAINING_MEMORY_PROMOTION_DELTA` (fallback `0.0` on invalid/missing value).
  - Registration failures are warning-only.

### 5) Startup idempotent DB init/backfill
- File: `backend/api_server.py`
- Behavior:
  - Startup hook calls `training_memory.db.init_db(...)` best-effort.
  - Ensures catalog tables/indexes exist for older DB files.
  - Failures are warning-only.

### 6) Similar-runs route registration
- File: `backend/api_server.py`
- Behavior:
  - Includes `training_memory.routes` router in guarded try/except.
  - Route import failure does not break core pipeline.

## Verification performed
- Verified hook presence in code:
  - ingest, decision, warm-start handoff, artifact registration, startup init, router include.
- Python compile checks passed:
  - `backend/api_server.py`
  - `backend/LLM Orchestrator/llm_orchestrator_workflow_agent.py`
  - `backend/LLM Orchestrator/generate_full_training_code.py`
  - `backend/LLM Orchestrator/run_full_training_code_with_llm.py`

## Behavior safety
- Default behavior remains cold-start and unchanged unless enabled by env:
  - `TRAINING_MEMORY_DECISION_ENABLED=false`
  - `TRAINING_MEMORY_POLICY=none`
- All training-memory integration points are non-blocking and warning-only on failures.

