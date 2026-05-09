# Training Memory Implementation Notes

## What was implemented

1. Added a decision layer for warm-start candidate selection:
   - `backend/training_memory/decision.py`
   - Computes `cold_start` vs `reuse_checkpoint_candidate` using catalog history.
   - Respects environment gates:
     - `TRAINING_MEMORY_DECISION_ENABLED`
     - `TRAINING_MEMORY_POLICY` (`none` or `warm_start_if_compatible`)

2. Added strict catalog-level compatibility checks:
   - `backend/training_memory/compatibility.py`
   - Checks:
     - `task_type` match (when anchor has task type)
     - `target_column` match
     - `schema_hash` match
   - Returns structured check results and failure reasons.

3. Upgraded warm-start resolver:
   - `backend/training_memory/warm_start.py`
   - Instead of always returning `None`, it now:
     - Looks up candidate run by `job_id` in catalog
     - Resolves run directory from `master_memory_path`
     - Picks latest `.pkl` from `training/` or run-wide fallback

4. Added a DB helper for row retrieval:
   - `backend/training_memory/db.py`
   - New helper: `get_training_run(...)`

5. Wired non-blocking decision observability into training:
   - `backend/api_server.py` (`_task_train`)
   - Before generating/running full training code, it computes decision and logs:
     - `[INFO] training_memory decision: {...}`
   - Any decision failure is warning-only and non-blocking.

6. Added artifact lineage and promotion support:
   - `backend/training_memory/artifacts.py`
   - `backend/training_memory/db.py` (`training_artifacts` table + helpers)
   - Registers trained `.pkl` with hash, parent job linkage, metric score, and promotion status.

7. Wired warm-start path handoff into training execution:
   - `backend/api_server.py` + `backend/LLM Orchestrator/llm_orchestrator_workflow_agent.py`
   - Passes `INTELLIMODEL_WARM_START_PATH` as an optional env var to the full-training runner.
   - Full-training code generation injects a best-effort warm-start load block.

8. Added startup DB migration/backfill behavior:
   - `backend/api_server.py` lifespan now initializes training-memory DB on startup.
   - Existing `training_catalog.db` files are idempotently upgraded with new tables (e.g. `training_artifacts`).
   - Failures are warning-only and non-blocking.

9. Updated docs:
   - `backend/training_memory/README.md`
   - `backend/.env.example`
   - `backend/QUICK_START.md`
   - Added decision/promotion env vars and migration behavior notes.

## Why this approach

- Keeps changes minimal and isolated to `training_memory` plus one hook in training task.
- Avoids major rewrites to existing orchestrator/trainer agents.
- Preserves safety:
  - Feature-gated (default off)
  - Non-blocking on failures
  - Falls back to cold start by default
- Preserves backward compatibility through optional env-based warm-start handoff.
- Adds artifact-level lineage/promotion so model updates are traceable and controllable.

## Current limitations

- Warm-start loading in generated scripts is best-effort and depends on generated model variable shape.
- Promotion currently uses a generic metric-priority heuristic; per-task metric policy may need tightening.
- Runtime end-to-end verification is still required in a fully configured local Python environment.
