# Training catalog (v1) — scope

Cross-run **historical metadata** from read-only `master_memory.json` after preprocessing. **Minimal changes** to existing pipeline code.

---

## In scope (v1)

1. **New package** — `backend/training_memory/` (`db`, `fingerprints`, `ingest`).
2. **Separate SQLite catalog** — default `backend/data/training_catalog.db` (optional `TRAINING_CATALOG_SQLITE_PATH` in `backend/.env`).
3. **Fingerprints** — From **per-job** `runs/<job_id>/master_memory.json` only (read-only): normalized target, SHA-256 of context text, SHA-256 of canonical column names + dtypes from `preprocessing.report.columns`, `task_type` if present.
4. **One hook** — After preprocess succeeds in `api_server.py`, call ingest inside `try`/`except` so catalog failures **do not** break the job.
5. **Docs** — This file + `backend/training_memory/README.md` + optional `.env.example` entry.

---

## Explicitly **not** wired to training (without further confirmation)

- **No warm-start in training** — no loading an old `.pkl` into the training pipeline. A stub module exists (`warm_start.py`) returning `None` until explicitly integrated.
- **No continual-learning in training** — no replay, distillation, or EWC in generated training code. A stub module exists (`learning_policy.py`) for future policy only.

## v1.1 additions (read-only / optional HTTP)

- **`GET /api/training/similar/{job_id}`** — JSON list of similar **catalog** rows (tiered: `schema_hash`, then `target`+`task_type`, then `target`). **No frontend UI** in this change set.
- **SQLite indexes** on `schema_hash`, `target_column`, `task_type` for faster similarity queries.

---

## Success check

After preprocess completes for a job, open `training_catalog.db` and confirm a **row** for that `job_id` with hashes and `master_memory_path`.

```sql
SELECT job_id, target_column, task_type, master_memory_path FROM training_runs ORDER BY created_at DESC LIMIT 5;
```
