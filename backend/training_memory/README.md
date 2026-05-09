# Training memory (v1)

Read-only ingest: after preprocessing completes for a job, a row is written to **`training_catalog.db`** with fingerprints derived from that job’s **`runs/<job_id>/master_memory.json`**.

- Does **not** modify `master_memory.json` or agent code.
- Failures are logged to the job log as `[WARN] training_memory catalog ingest failed` and do **not** fail the pipeline.

## Environment

| Variable | Meaning |
|----------|---------|
| `TRAINING_CATALOG_SQLITE_PATH` | Optional absolute path to the SQLite file (default: `backend/data/training_catalog.db`). |
| `TRAINING_MEMORY_DECISION_ENABLED` | Optional gate for warm-start decisioning before training (`false` by default). |
| `TRAINING_MEMORY_POLICY` | Decision policy: `none` (default) or `warm_start_if_compatible`. |
| `TRAINING_MEMORY_PROMOTION_DELTA` | Optional minimum score improvement needed to promote a new artifact (default: `0.0`). |

## Schema (`training_runs`)

| Column | Description |
|--------|-------------|
| `job_id` | Pipeline job id (primary key). |
| `created_at` | UTC timestamp of ingest. |
| `target_column` | Normalized target name (lowercase strip). |
| `context_hash` | SHA-256 of `context_of_dataset` text. |
| `schema_hash` | SHA-256 of canonical column name + dtype list from preprocessing report. |
| `task_type` | e.g. `regression`, if present. |
| `master_memory_path` | Absolute path to the ingested JSON file. |
| `fingerprints_json` | Small debug blob with hashes and schema preview. |

## Schema (`training_artifacts`)

| Column | Description |
|--------|-------------|
| `job_id` | Job that produced the artifact. |
| `model_name` | Trained model selected by user. |
| `artifact_path` | Absolute path to saved `.pkl`. |
| `artifact_hash` | SHA-256 for artifact identity/dedup debugging. |
| `parent_job_id` | Historical run used for warm-start candidate (if any). |
| `metric_name` / `metric_value` | Validation metric used during promotion comparison. |
| `metric_score` | Normalized score where higher is better. |
| `is_promoted` | Whether this artifact is current promoted pick for the model. |

## HTTP (read-only)

- **`GET /api/training/similar/{job_id}?limit=15`** — returns `{ anchor_found, similar: [...] }` using tiered SQL matching (`schema_hash` → `target`+`task_type` → `target`). Requires that job to exist in the catalog (post-preprocess ingest).

## Stubs / partials (not fully wired to trainer behavior)

- **`warm_start.resolve_warm_start_checkpoint`** — now resolves candidate `.pkl` paths from prior run folders, but trainer reuse remains opt-in and policy-gated.
- **`learning_policy`** — config placeholder + `describe_planned_policies()` for docs only.

## Decisioning hook (non-blocking)

- Training now logs a pre-train decision record from `training_memory.decision` as:
  - `[INFO] training_memory decision: {...}`
- This is currently **observability-first**: the decision is computed and logged, but
  does not force trainer behavior changes yet.

## Implementation steps completed

1. Added warm-start decisioning gate with policy controls (`decision.py`).
2. Added strict compatibility checks (target/task/schema) plus model-family filter.
3. Enabled optional checkpoint handoff into training via `INTELLIMODEL_WARM_START_PATH`.
4. Updated generated full-training scripts with best-effort warm-start load block.
5. Added artifact lineage + promotion tracking in SQLite (`training_artifacts`).
6. Registered produced `.pkl` artifacts after training with non-blocking logs.

## Out of scope for training integration

See **`TRAINING_MEMORY_V1.md`** for broader constraints: no replay/distillation/EWC in the training loop, no frontend UI for similar runs (API only).
