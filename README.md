# IntelliModel

An end-to-end automated ML pipeline platform powered by LLM agents (Claude via Anthropic). Users upload a CSV dataset, and the system automatically preprocesses the data, recommends models, generates and validates training code, optionally improves it, trains the final model, and exposes a live prediction API — all orchestrated through a React UI backed by FastAPI agents.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Repository Structure](#repository-structure)
3. [Technology Stack](#technology-stack)
4. [Environment Configuration](#environment-configuration)
5. [Getting Started](#getting-started)
6. [Backend — Core Modules](#backend--core-modules)
   - [LLM Configuration](#llm-configuration)
   - [Workflow API Server](#workflow-api-server-port-9000)
   - [Master Orchestrator](#master-orchestrator)
   - [Pre-Processing Agent](#pre-processing-agent)
   - [LLM Orchestrator](#llm-orchestrator)
   - [Improvement Agent](#improvement-agent)
   - [Deployment API](#deployment-api-port-8000)
   - [Training Memory & Catalog](#training-memory--catalog)
   - [Authentication](#authentication)
7. [Frontend](#frontend)
8. [API Reference](#api-reference)
9. [Database Schemas](#database-schemas)
10. [LLM Prompts](#llm-prompts)
11. [End-to-End Data Flow](#end-to-end-data-flow)
12. [Job State Machine](#job-state-machine)
13. [Memory & State Files](#memory--state-files)
14. [Per-Run Artifacts](#per-run-artifacts)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         React Frontend (Vite)                        │
│   LandingPage  /  RequireAuth  /  PipelineView (7 steps)            │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTP + SSE  (port 9000)
┌────────────────────────────▼────────────────────────────────────────┐
│                 Workflow API Server  (api_server.py)                 │
│   FastAPI · in-memory _jobs · daemon threads · SSE log stream        │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │               Master Orchestrator Agent                      │    │
│  │   LangGraph: preprocess → recommend → validate → improve     │    │
│  │                                                              │    │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────┐  │    │
│  │  │ Pre-Processing   │  │  LLM Orchestrator│  │Improvement│ │    │
│  │  │ Agent (LangGraph)│  │  Workflow Agent  │  │  Agent   │  │    │
│  │  │ report→plan→code │  │  recommend→val  │  │(LangGraph)│ │    │
│  │  └──────────────────┘  │  →full-train    │  └──────────┘  │    │
│  │                        └──────────────────┘                │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────┐   ┌───────────────────────────────────┐   │
│  │ Auth  (Google OAuth) │   │ Training Memory (SQLite catalog)  │   │
│  │ SQLite sessions      │   │ fingerprints · warm-start         │   │
│  └──────────────────────┘   └───────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
                             │ port 8000
┌────────────────────────────▼────────────────────────────────────────┐
│                   Deployment API  (deployment/main.py)               │
│  /predict  ·  /predict_raw  ·  /features  ·  /health                │
│  Loads latest *_full.pkl; raw-input preprocessing via generated code │
└──────────────────────────────────────────────────────────────────────┘
```

Claude (`claude-3-5-sonnet-latest`) is used by every agent for reasoning, code generation, and self-healing fix prompts. All inter-agent communication is through subprocess calls with JSON memory files.

---

## Repository Structure

```
IntelliModel/
├── backend/
│   ├── api_server.py                    # Main FastAPI workflow server (port 9000)
│   ├── master_orchestrator.py           # Master agent + LangGraph chaining
│   ├── llm_config.py                    # Anthropic ChatLLM factory
│   ├── master_memory.json               # Global memory synced copy (for deployment)
│   ├── requirements.txt
│   ├── COMPLETE_WORKFLOW_GUIDE.md
│   ├── QUICK_START.md
│   │
│   ├── Pre Processing Agent/
│   │   ├── preprocessing_workflow_agent.py   # LangGraph entrypoint
│   │   ├── preprocessing_steps.py            # LLM plan generation
│   │   ├── preprocessing_code_generator.py   # LLM code generation
│   │   ├── run_preprocessing_with_llm.py     # Execution + LLM self-heal
│   │   ├── report_generator.py               # Dataset metadata report
│   │   └── README.md
│   │
│   ├── LLM Orchestrator/
│   │   ├── llm_orchestrator_workflow_agent.py  # Orchestrator class
│   │   ├── model_recommender.py                # LLM model recommendation
│   │   ├── model_vc_gen.py                     # Validation code generation
│   │   ├── run_validation_code_with_llm.py     # Validation runner + self-heal
│   │   ├── generate_full_training_code.py      # Full-train code refactoring
│   │   ├── run_full_training_code_with_llm.py  # Full-train runner + self-heal
│   │   ├── model_testing/                      # Generated validation scripts
│   │   └── full_training/                      # Generated training scripts + .pkl
│   │
│   ├── Improvement Agent/
│   │   ├── improvement_workflow_agent.py        # LangGraph improvement loop
│   │   ├── improvement_steps_generator.py       # LLM improvement advisor
│   │   ├── improved_code_gen.py                 # LLM improved code generator
│   │   ├── improved_code_runner.py              # Runner + self-heal
│   │   └── {dataset_name}/
│   │       ├── improvement_steps.txt
│   │       ├── improvement_memory.json
│   │       └── improved_training/
│   │
│   ├── auth/
│   │   ├── router.py                   # FastAPI auth routes
│   │   ├── db.py                       # SQLite users + sessions
│   │   ├── google_verify.py            # JWT verification
│   │   └── AUTH_SETUP.md
│   │
│   ├── training_memory/
│   │   ├── db.py                       # training_catalog.db schema
│   │   ├── ingest.py                   # record_run_after_preprocess()
│   │   ├── decision.py                 # decide_warm_start()
│   │   └── routes.py                   # /api/training/similar/{job_id}
│   │
│   ├── deployment/
│   │   ├── main.py                     # Prediction API (port 8000)
│   │   └── requirements.txt
│   │
│   ├── data/
│   │   ├── intellimodel_users.db       # Auth SQLite DB
│   │   └── training_catalog.db         # Training memory SQLite DB
│   │
│   └── runs/
│       └── {job_uuid}/                 # Per-job artifacts
│           ├── {dataset}.csv
│           ├── master_memory.json
│           ├── preprocessing/
│           ├── validation/
│           ├── training/
│           └── improvement/
│
├── Frontend/
│   ├── src/
│   │   ├── App.tsx                     # Router: / and /try-now
│   │   ├── main.tsx                    # GoogleOAuthProvider bootstrap
│   │   ├── api/
│   │   │   └── client.ts               # Typed API client
│   │   ├── components/
│   │   │   ├── pipeline/
│   │   │   │   ├── UploadStep.tsx
│   │   │   │   ├── PreprocessingStep.tsx
│   │   │   │   ├── ModelSelectionStep.tsx
│   │   │   │   ├── ValidationStep.tsx
│   │   │   │   ├── ImprovementStep.tsx
│   │   │   │   ├── TrainingStep.tsx
│   │   │   │   └── DeploymentStep.tsx
│   │   │   └── auth/
│   │   │       └── RequireAuth.tsx
│   │   └── pages/
│   │       ├── LandingPage.tsx
│   │       └── PipelineView.tsx
│   ├── package.json
│   ├── vite.config.ts
│   └── .env                            # VITE_API_BASE_URL, VITE_GOOGLE_CLIENT_ID
│
├── Datasets/
│   └── stock_prediction_dataset.csv    # Sample dataset
│
├── .env                                # Root env (ANTHROPIC_API_KEY, CLAUDE_MODEL, etc.)
└── README.md
```

---

## Technology Stack

| Layer | Technologies |
|---|---|
| **Frontend** | Vite 5, React 18, TypeScript, TanStack Query, react-router-dom, shadcn/ui (Radix), Tailwind CSS, `@react-oauth/google` |
| **Backend API** | Python 3.13, FastAPI, Uvicorn, Server-Sent Events |
| **Agent framework** | LangChain, LangGraph, `langchain-anthropic` |
| **LLM** | Anthropic Claude (`claude-3-5-sonnet-latest` default) |
| **ML libs** | scikit-learn, XGBoost, LightGBM, pandas, numpy |
| **Auth** | Google OAuth 2.0 (ID token verification via `google-auth`), HTTP-only session cookies, SQLite |
| **Persistence** | SQLite (auth + training catalog), JSON memory files, `.pkl` model artifacts |
| **Deployment** | Separate FastAPI server loading `.pkl` artifact + running generated preprocessing code |

---

## Environment Configuration

### Root `.env` (or `backend/.env`)

```env
ANTHROPIC_API_KEY=sk-ant-...           # Required — used by ChatAnthropic
CLAUDE_MODEL=claude-3-5-sonnet-latest  # Optional override
CLAUDE_BASE_URL=https://api.anthropic.com  # Optional override

GOOGLE_OAUTH_CLIENT_ID=xxx.apps.googleusercontent.com  # Google OAuth

# Optional training memory knobs
TRAINING_MEMORY_DECISION_ENABLED=true
TRAINING_MEMORY_POLICY=warm_start_if_compatible
INTELLIMODEL_COOKIE_SECURE=false       # Set true in HTTPS production
```

### `Frontend/.env`

```env
VITE_API_BASE_URL=http://localhost:9000
VITE_GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
```

`llm_config.py` loads `.env` from both the project root and `backend/` using `python-dotenv`. The `ChatAnthropic` instance reads `ANTHROPIC_API_KEY` from the environment automatically via LangChain conventions.

---

## Getting Started

### 1. Install backend dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Start the workflow API server

> **Do not use `--reload`** — file writes from agents trigger restart and wipe in-memory job state.

```bash
cd backend
uvicorn api_server:app --host 0.0.0.0 --port 9000
```

### 3. Start the frontend

```bash
cd Frontend
npm install
npm run dev
```

### 4. (Optional) Start the deployment prediction server

After a full training run completes:

```bash
cd backend/deployment
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## Backend — Core Modules

---

### LLM Configuration

**File:** `backend/llm_config.py`

Central factory for the Anthropic LLM instance shared across all agents.

```python
DEFAULT_LLM_MODEL: Final[str] = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-latest")
DEFAULT_LLM_ENDPOINT: Final[str] = os.getenv("CLAUDE_BASE_URL", "https://api.anthropic.com")

def create_chat_llm(model: str = DEFAULT_LLM_MODEL) -> ChatAnthropic:
    """Returns a configured ChatAnthropic instance."""
```

Loads `.env` from project root and `backend/` on import.

---

### Workflow API Server (port 9000)

**File:** `backend/api_server.py`

The single HTTP surface for the React frontend. All ML work runs in **daemon threads**; results accumulate in an in-memory `_jobs` dict.

#### `JobState` dataclass

| Field | Description |
|---|---|
| `job_id` | UUID string |
| `csv_path` | Path to uploaded CSV |
| `target_column` | User-specified prediction target |
| `goal` | Free-text task description |
| `output_dir` | `runs/{job_id}/` |
| `status` | One of the states in the [job state machine](#job-state-machine) |
| `logs` | Captured stdout/stderr from worker thread (truncated to 10k chars in polling) |
| `validation_metrics` | Dict model_name → metrics dict |
| `recommended_models` | List of recommendation dicts |
| `preprocessing_report` | Dataset metadata string |

#### Worker task functions

| Function | Actions |
|---|---|
| `_task_preprocess_and_recommend` | Calls `MasterOrchestratorAgent.run_preprocessing_agent` → `LLMOrchestratorWorkflowAgent.generate_model_recommendations` → optionally `training_memory.ingest.record_run_after_preprocess` |
| `_task_validate` | Generates + runs validation code with up to **2 self-heal attempts** |
| `_task_train` | Generates + runs full training code; optional warm-start via `decide_warm_start`; registers artifact |
| `_task_improve` | Runs `ImprovementWorkflowAgent`; handles `MetricsAlreadyGoodError` path |

#### `_sync_master_memory(job_id)`

Copies `runs/{job_id}/master_memory.json` → `backend/master_memory.json` so the deployment server can find it.

---

### Master Orchestrator

**File:** `backend/master_orchestrator.py`

#### `MasterMemory` dataclass

Holds the complete cross-agent state for a run:

- `dataset_path`, `target_column`, `goal`, `task_type`
- `preprocessing_report_path`, `preprocessing_plan_path`, `preprocessing_code_path`, `processed_csv_path`, `processed_report_path`
- `llm_orchestrator` — nested snapshot: `recommendations`, `validation_metrics`, `validation_history`, `selected_model_for_full_training`, `generated_code_paths`
- `improvement_steps_path`, `improved_code_path`, `improvement_memory_path`
- `file_history`, `workflow_history`

Serialized to/from `master_memory.json` at every stage.

#### `MasterOrchestratorAgent`

| Method | Description |
|---|---|
| `run_preprocessing_agent(dataset_path, target_column, goal, output_dir)` | Launches `Pre Processing Agent/preprocessing_workflow_agent.py` as subprocess; reads resulting `workflow_memory.json`; merges into master memory via `_copy_preprocessing_memory` |
| `run_llm_orchestrator(output_dir)` | Launches `LLM Orchestrator/llm_orchestrator_workflow_agent.py` as subprocess |
| `run_improvement_agent(output_dir)` | Launches `Improvement Agent/improvement_workflow_agent.py` as subprocess |
| `_build_workflow_graph()` | LangGraph: `preprocessing → llm_orchestration → improvement → persist_memory`; improvement node skipped when `selected_model_for_full_training` is set |
| `save_memory(path)` / `load_memory(path)` | JSON serialization of `MasterMemory` |

---

### Pre-Processing Agent

**Directory:** `backend/Pre Processing Agent/`

Entry: `preprocessing_workflow_agent.py`  
CLI args: `--dataset`, `--target-column`, `--goal`, `--output-dir`, `--save-memory`

#### `WorkflowMemory` dataclass

```python
@dataclass
class WorkflowMemory:
    dataset_path: str
    target_column: str
    goal: str
    report_path: str           # {dataset}.json
    plan_path: str             # {dataset}_preprocessing_plan.json
    code_path: str             # {dataset}_preprocessing_code.py
    processed_csv_path: str    # processed_output.csv
    processed_report_path: str # {dataset}_processed.json
    task_type: str             # regression | classification | forecasting
```

#### LangGraph pipeline (`PreprocessingWorkflowAgent`)

```
generate_report → generate_plan → generate_code → run_code → generate_processed_report
```

**`generate_report` node (`report_generator.py`)**

- Reads CSV with pandas; computes column stats (dtype, null %, unique count, sample values)
- Calls `infer_task_type(target_column, df)` to set `task_type`
- Writes compact JSON metadata report — **never sends raw rows to LLM**

**Task type inference (`TASK_METRICS` / `TASK_PRIMARY_METRIC`)**

```python
TASK_METRICS = {
    "regression":       ["MAE", "RMSE", "R2", "MAPE"],
    "classification":   ["Accuracy", "F1", "Precision", "Recall", "ROC_AUC"],
    "forecasting":      ["MAE", "RMSE", "R2", "MAPE"],
}
TASK_PRIMARY_METRIC = {
    "regression":     "R2",
    "classification": "F1",
    "forecasting":    "MAE",
}
```

**`generate_plan` node (`preprocessing_steps.py`)**

Calls Claude with a structured prompt (see [LLM Prompts](#llm-prompts)). Returns a plan with `preprocessing_steps[]` objects:

```json
{
  "preprocessing_steps": [
    {
      "step": 1,
      "action": "drop_duplicates",
      "columns": ["all"],
      "reason": "Remove exact duplicate rows"
    }
  ]
}
```

**`generate_code` node (`preprocessing_code_generator.py`)**

Generates a standalone Python script from the plan. The script:
- Reads the original CSV
- Applies all preprocessing steps
- Saves `processed_output.csv`

**`run_code` node (`run_preprocessing_with_llm.py`)**

Executes the generated script. On failure, calls Claude with a `FIX_PROMPT` to patch the error, then retries.

---

### LLM Orchestrator

**File:** `backend/LLM Orchestrator/llm_orchestrator_workflow_agent.py`

#### `OrchestratorMemory` dataclass

| Field | Description |
|---|---|
| `master_memory_path` | Path to master_memory.json |
| `recommended_models` | List of parsed recommendation dicts |
| `selected_models_for_validation` | User-chosen subset |
| `generated_code_paths` | model_name → validation script path |
| `validation_metrics` | model_name → metrics dict |
| `validation_history` | Previously validated models (used to exclude on re-recommend) |
| `selected_model_for_full_training` | Chosen model for final training |
| `full_training_code_path` | Path to full training script |
| `full_training_artifact_path` | Path to `.pkl` |
| `file_history`, `workflow_history` | Audit trail |

#### `LLMOrchestratorWorkflowAgent` methods

| Method | Description |
|---|---|
| `load_master_memory()` | Reads preprocessing report + processed report; saves initial `orchestrator_memory.json` |
| `generate_model_recommendations(exclude_validated)` | Calls `model_recommender.recommend_models`; appends exclusion context from `validation_history`; parses structured rows |
| `generate_validation_code(selected_models)` | Subprocess → `model_vc_gen.py` per model |
| `run_validation_code(model_name)` | Subprocess → `run_validation_code_with_llm.py`; captures metrics |
| `generate_full_training_code(model_name)` | Subprocess → `generate_full_training_code.py` |
| `run_full_training_code(model_name, warm_start_path)` | Subprocess → `run_full_training_code_with_llm.py`; sets env `INTELLIMODEL_WARM_START_PATH` if warm-start |

**Subprocess stdin** is set to `subprocess.DEVNULL` for all agent calls to prevent blocking on interactive prompts in API mode.

---

### Improvement Agent

**Directory:** `backend/Improvement Agent/`

**File:** `improvement_workflow_agent.py`

Per-dataset working directory: `Improvement Agent/{dataset_name}/`

#### LangGraph pipeline (`ImprovementWorkflowAgent`)

```
load_master_memory → check_feasibility → get_improvement_steps
    → generate_improved_code → run_improved_code → save_memory
```

**`check_feasibility` node**

Raises `MetricsAlreadyGoodError` if the primary metric already exceeds a threshold (e.g. R² > 0.95 for regression), skipping the improvement loop.

**`get_improvement_steps` node (`improvement_steps_generator.py`)**

Calls Claude to produce a numbered list of actionable improvements. See [LLM Prompts](#llm-prompts).

**`generate_improved_code` node (`improved_code_gen.py`)**

Claude generates a new version of the validation script incorporating the improvement steps.

**`run_improved_code` node (`improved_code_runner.py`)**

Executes the improved script. On failure, calls Claude with a `FIX_PROMPT`. Captures new metrics and compares against baseline.

#### `improvement_memory.json` schema

```json
{
  "model_name": "gradient_boosting_regressor",
  "validation_code_path": "...",
  "improved_validation_code_path": "...",
  "improvement_steps": "...",
  "regeneration_count": 1,
  "improvement_run_succeeded": true,
  "metrics_improved": true,
  "halt_no_improvement": false,
  "halt_max_regenerations": false
}
```

The API `POST /api/confirm_improvement/{job_id}` reads this file and patches `orchestrator_memory.json` with the improved code path. `POST /api/discard_improvement/{job_id}` resets job status to `validation_done`.

---

### Deployment API (port 8000)

**File:** `backend/deployment/main.py`

Loads `backend/master_memory.json` with mtime-based cache (reloads when file changes). Finds the latest `*_full.pkl` under `LLM Orchestrator/full_training/` using joblib.

#### Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Returns `{"status": "ok", "model_loaded": bool}` |
| GET | `/features` | Processed feature names expected by model |
| GET | `/raw_features` | Original CSV column names (excluding target) |
| POST | `/predict` | Body: `{feature: value, ...}` (processed feature names) |
| POST | `/predict_raw` | Body: raw column names → runs `_run_preprocessing_on_raw` → predict |

#### `_run_preprocessing_on_raw`

Patches the generated preprocessing script to inject a sentinel column trick: combines the raw input row with the training CSV header, runs the preprocessing script, extracts the processed row for inference. This allows raw-input prediction without maintaining a separate preprocessing service.

---

### Training Memory & Catalog

**Directory:** `backend/training_memory/`

Optional feature gated by `TRAINING_MEMORY_DECISION_ENABLED=true`.

#### `training_catalog.db` schema

```sql
CREATE TABLE training_runs (
    job_id           TEXT PRIMARY KEY,
    created_at       TEXT,
    target_column    TEXT,
    context_hash     TEXT,   -- hash of goal + target_column
    schema_hash      TEXT,   -- hash of column names + dtypes
    task_type        TEXT,
    master_memory_path TEXT,
    fingerprints_json  TEXT  -- JSON of column-level fingerprints
);

CREATE TABLE training_artifacts (
    job_id         TEXT,
    model_name     TEXT,
    artifact_path  TEXT,
    artifact_hash  TEXT,
    parent_job_id  TEXT,    -- set when warm-started from another job
    mae            REAL,
    rmse           REAL,
    r2             REAL,
    accuracy       REAL,
    f1             REAL,
    is_promoted    INTEGER DEFAULT 0,
    PRIMARY KEY (job_id, model_name)
);
```

#### Key functions

| Function | File | Description |
|---|---|---|
| `record_run_after_preprocess(job_id, master_memory_path)` | `ingest.py` | Computes fingerprints; inserts into `training_runs` |
| `decide_warm_start(job_id, requested_model_name)` | `decision.py` | Finds compatible prior artifact when `TRAINING_MEMORY_POLICY=warm_start_if_compatible`; returns artifact path or None |
| `find_similar_runs(job_id)` | `routes.py` | Returns runs with matching schema/context hash |
| `register_artifact(job_id, model_name, artifact_path, metrics)` | `ingest.py` | Records final `.pkl` and metrics in `training_artifacts` |

---

### Authentication

**Directory:** `backend/auth/`

Google OAuth 2.0 with HTTP-only session cookie (`im_session`, 30-day expiry).

#### Auth routes (`auth/router.py`)

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/google` | Body: `{"credential": "<Google JWT>"}` → verify → upsert user → create session → set cookie |
| GET | `/api/auth/me` | Returns current user info from session cookie |
| POST | `/api/auth/logout` | Deletes session; clears cookie |

#### `auth/db.py` schema

```sql
CREATE TABLE users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    google_sub     TEXT UNIQUE NOT NULL,   -- Google's stable user ID
    email          TEXT NOT NULL,
    email_verified INTEGER,
    name           TEXT,
    picture_url    TEXT,
    created_at     TEXT,
    updated_at     TEXT
);

CREATE TABLE sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id),
    token_hash  TEXT UNIQUE NOT NULL,
    expires_at  TEXT,
    created_at  TEXT
);
```

#### `auth/google_verify.py`

Uses `google.oauth2.id_token.verify_oauth2_token` with `google.auth.transport.requests.Request`. Supports comma-separated `GOOGLE_OAUTH_CLIENT_ID` for multiple OAuth clients.

#### `get_current_user_optional` dependency

Available for route protection but **workflow routes are not currently enforcing login at the backend level** — auth is enforced only in the React `RequireAuth` component. See `AUTH_SETUP.md` for adding backend enforcement.

#### CORS note

`api_server.py` uses `allow_origins=["*"]` with `allow_credentials=True`. Browsers reject credentialed requests with wildcard origins. For production, set an explicit origin list matching the frontend URL.

---

## Frontend

**Directory:** `Frontend/`  
**Stack:** Vite 5, React 18, TypeScript, TanStack Query, react-router-dom, shadcn/ui, Tailwind

### Routing (`App.tsx`)

```
/           → LandingPage
/try-now    → RequireAuth → PipelineView
*           → LandingPage (redirect)
```

### `RequireAuth` component

On mount calls `getAuthMe()`. If the response is 401, renders a Google sign-in button (`GoogleLogin` from `@react-oauth/google`) and triggers `signInWithGoogle` (POSTs credential to `/api/auth/google`). Renders children only when a valid session exists.

### `GoogleOAuthProvider` bootstrap (`main.tsx`)

```tsx
const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? "";

const tree = googleClientId ? (
  <GoogleOAuthProvider clientId={googleClientId}>
    <App />
  </GoogleOAuthProvider>
) : <App />;
```

If `VITE_GOOGLE_CLIENT_ID` is empty, OAuth is skipped and `RequireAuth` will not render the Google button — useful for local dev without OAuth.

### Pipeline steps (`PipelineView.tsx`)

| Step | Component | What it does |
|---|---|---|
| 1 | `UploadStep` | File picker + target column + goal; calls `POST /api/upload` |
| 2 | `PreprocessingStep` | Polls `GET /api/status/{job_id}` or `GET /api/stream/{job_id}` (SSE); shows live logs + preprocessing report |
| 3 | `ModelSelectionStep` | Displays LLM recommendations; user selects models; calls `POST /api/validate/{job_id}` |
| 4 | `ValidationStep` | Shows validation metrics per model; option to re-recommend |
| 5 | `ImprovementStep` | Triggers `POST /api/improve/{job_id}`; confirm or discard |
| 6 | `TrainingStep` | User picks model for full training; `POST /api/train/{job_id}` |
| 7 | `DeploymentStep` | Shows predict URLs + example payload from `GET /api/deployment/{job_id}` |

### API client (`src/api/client.ts`)

```typescript
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:9000";

// All requests use credentials: "include" for cookie-based auth
```

**Typed interfaces:** `JobStatus`, `StatusResponse` (includes `recommended_models`, `validation_metrics`, `preprocessing_report`, `deployment_info`), `DeploymentInfo`, `ModelRecommendation`, auth helpers.

### Legacy Streamlit UI (`Frontend/app.py`)

A parallel Streamlit interface that imports `MasterOrchestratorAgent`, `model_recommender`, etc. directly. Mirrors the React pipeline flow. Not recommended for production use.

---

## API Reference

### Workflow API (port 9000)

#### Upload

```
POST /api/upload
Content-Type: multipart/form-data

file:          CSV file
target_column: string
goal:          string (optional context)

Response: { "job_id": "uuid", "filename": "...", "status": "uploaded" }
```

#### Preprocess + Recommend

```
POST /api/preprocess/{job_id}

Response: { "job_id": "...", "status": "preprocessing" }
(Long-running — poll /api/status or stream /api/stream)
```

#### Re-recommend (excluding already-validated models)

```
POST /api/recommend/{job_id}

Response: { "job_id": "...", "status": "preprocessing_done" }
```

#### Status polling

```
GET /api/status/{job_id}

Response: StatusResponse {
  job_id, status, logs (truncated 10k),
  recommended_models, validation_metrics,
  preprocessing_report, deployment_info, error
}
```

#### SSE log stream

```
GET /api/stream/{job_id}
Accept: text/event-stream

Events: data: <log line>\n\n
        data: [DONE]\n\n  (on terminal status)
```

#### Validate

```
POST /api/validate/{job_id}
Content-Type: application/json

{ "selected_models": ["random_forest_regressor", "xgboost_regressor"] }

Response: { "job_id": "...", "status": "validating" }
```

#### Train

```
POST /api/train/{job_id}
Content-Type: application/json

{ "model_name": "gradient_boosting_regressor" }

Response: { "job_id": "...", "status": "training" }
```

#### Improve

```
POST /api/improve/{job_id}
Content-Type: application/json

{ "model_name": "gradient_boosting_regressor" }

Response: { "job_id": "...", "status": "improving" }
```

#### Confirm / Discard Improvement

```
POST /api/confirm_improvement/{job_id}
POST /api/discard_improvement/{job_id}
```

#### Deployment info

```
GET /api/deployment/{job_id}

Response: DeploymentInfo {
  predict_url: "http://localhost:8000/predict",
  predict_raw_url: "http://localhost:8000/predict_raw",
  features_url: "http://localhost:8000/features",
  example_payload: { feature1: value, ... }
}
```

#### Health

```
GET /api/health

Response: { "status": "ok", "active_jobs": 2 }
```

### Auth routes

```
POST /api/auth/google         { "credential": "<JWT>" }
GET  /api/auth/me
POST /api/auth/logout
```

### Training memory

```
GET /api/training/similar/{job_id}
```

### Deployment API (port 8000)

```
GET  /health
GET  /features
GET  /raw_features
POST /predict        { "feature1": 1.0, "feature2": "A", ... }
POST /predict_raw    { "Open": 100.5, "High": 105.0, ... }
```

---

## Database Schemas

### Auth DB (`backend/data/intellimodel_users.db`)

```sql
users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    google_sub     TEXT UNIQUE NOT NULL,
    email          TEXT NOT NULL,
    email_verified INTEGER,
    name           TEXT,
    picture_url    TEXT,
    created_at     TEXT,
    updated_at     TEXT
)

sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id),
    token_hash  TEXT UNIQUE NOT NULL,
    expires_at  TEXT,
    created_at  TEXT
)
```

### Training Catalog (`backend/data/training_catalog.db`)

```sql
training_runs (
    job_id             TEXT PRIMARY KEY,
    created_at         TEXT,
    target_column      TEXT,
    context_hash       TEXT,
    schema_hash        TEXT,
    task_type          TEXT,
    master_memory_path TEXT,
    fingerprints_json  TEXT
)

training_artifacts (
    job_id         TEXT,
    model_name     TEXT,
    artifact_path  TEXT,
    artifact_hash  TEXT,
    parent_job_id  TEXT,
    mae            REAL,
    rmse           REAL,
    r2             REAL,
    accuracy       REAL,
    f1             REAL,
    is_promoted    INTEGER DEFAULT 0,
    PRIMARY KEY (job_id, model_name)
)
```

---

## LLM Prompts

All prompts use Claude via LangChain's `ChatAnthropic`. Below are the complete prompt designs.

### 1. Preprocessing Plan (`preprocessing_steps.py`)

**System:**
> You are a meticulous data preprocessing expert. You only see dataset metadata — never raw rows. You must return a valid JSON plan with a `preprocessing_steps` array. Each step has: `step` (int), `action` (str), `columns` (list), `reason` (str).

**User (template variables: `metadata`, `target_column`, `task_type`):**

```
Dataset metadata:
{metadata}

Target column: {target_column}
Task type: {task_type}

Generate a preprocessing plan. Rules:
- Handle duplicates (check and remove if present)
- Drop ID-like columns (high cardinality, non-predictive)
- Handle datetime columns (extract features or drop)
- Encode high-cardinality text with target encoding or drop
- Ensure target column quality (no nulls, correct dtype)
- Output must be valid UTF-8 Python-executable friendly values
- Flag class imbalance for classification tasks
- Return ONLY a JSON object, no markdown.
```

### 2. Preprocessing Code Generation (`preprocessing_code_generator.py`)

**System:**
> You are an expert Python data engineer. Generate a standalone preprocessing script.

**User:**

```
Given the following preprocessing plan and dataset metadata, write a complete Python script that:
1. Reads the CSV from the given path
2. Applies every step in the plan
3. Saves the processed output to {output_path}
4. Prints a summary of changes made

Plan: {plan}
Dataset path: {dataset_path}
Target column: {target_column}
Columns info: {columns_info}

Return ONLY the Python code. No explanations.
```

### 3. Model Recommendation (`model_recommender.py`)

**System:**
> You are an ML model selector. Recommend exactly 3 models. Format each recommendation strictly as:
> ```
> Model 1: <model_name>
> Reason: <one sentence>
> ```
> No markdown. No numbering variations. No extra text.

**User (template variables: `task_type`, `dataset_info`, `target_column`, `goal`, `exclusions`):**

```
Task type: {task_type}
Target column: {target_column}
Goal: {goal}
Dataset summary: {dataset_info}

{exclusions}

Recommend exactly 3 scikit-learn compatible models suitable for this task.
Consider dataset size, feature types, and the goal.
```

### 4. Validation Code Generation (`model_vc_gen.py` → `build_prompt`)

**System:**
> You are an ML testing code generator. Generate a standalone Python script that:
> - Loads the processed CSV
> - Splits into 80/20 train/test
> - Trains the specified model
> - Evaluates and prints metrics in EXACT format (required for parsing)

**Metric format instructions (`METRIC_INSTRUCTIONS`):**

```python
METRIC_INSTRUCTIONS = {
    "regression": """
Print metrics exactly as:
MAE: <value>
RMSE: <value>
R2: <value>
MAPE: <value>
TRAIN_MAE: <value>
TRAIN_R2: <value>
OVERFITTING_DETECTED: <True/False>  # True if abs(TRAIN_R2 - TEST_R2) > 0.15
""",
    "classification": """
Print metrics exactly as:
ACCURACY: <value>
F1: <value>
PRECISION: <value>
RECALL: <value>
ROC_AUC: <value>
TRAIN_ACCURACY: <value>
OVERFITTING_DETECTED: <True/False>
""",
    "forecasting": """
Print metrics exactly as:
MAE: <value>
RMSE: <value>
R2: <value>
MAPE: <value>
TRAIN_MAE: <value>
TRAIN_R2: <value>
OVERFITTING_DETECTED: <True/False>
"""
}
```

**User:**

```
Model: {model_name}
Task type: {task_type}
Dataset path: {processed_csv_path}
Target column: {target_column}
ID columns to exclude: {id_columns}

{metric_instructions}

Return ONLY the Python code. No markdown fences.
```

### 5. Full Training Code Refactor (`generate_full_training_code.py`)

**System:**
> You are an expert ML code refactorer.

**User:**

```
Convert the following VALIDATION TESTING code into FULL DATASET TRAINING code.

STRICT RULES:
- Remove train/test split or any evaluation splitting.
- Train the model on the FULL dataset only.
- Do NOT change the model type, hyperparameters, or imports.
- Save the trained model to: {output_path}
- Use joblib.dump() to save.
- Print "MODEL SAVED: {output_path}" when done.
- Do NOT print any metrics.

Code:
{code}
```

### 6. Improvement Steps (`improvement_steps_generator.py`)

**System:**
> You are an ML optimization advisor.

**User:**

```
Model: {model_name}
Current metrics: {metrics}
Task type: {task_type}

Validation code:
{validation_code}

Dataset report:
{dataset_report}

Context: {goal}

Provide a numbered list of actionable improvement steps.
Rules:
- Cannot change the model type
- If dataset has fewer than 1000 rows, do not increase model complexity
- Focus on: hyperparameter tuning, feature engineering, cross-validation
- Be specific — include exact parameter values where applicable
- Return ONLY the numbered list, no explanations
```

### 7. Self-Heal Fix Prompts (all runners)

Used in `run_preprocessing_with_llm.py`, `run_validation_code_with_llm.py`, `run_full_training_code_with_llm.py`, `improved_code_runner.py`.

**System:**
> You are an expert Python debugger. Fix the provided code so it runs without errors.

**User (FIX_PROMPT template):**

```
The following Python code failed with this error:

ERROR:
{error}

CODE:
{code}

Fix the code. Return ONLY the corrected Python code. No explanations. No markdown.
```

---

## End-to-End Data Flow

```
User uploads CSV + target_column + goal
            │
            ▼
POST /api/upload
  → Creates runs/{job_id}/
  → Saves CSV
  → Status: "uploaded"
            │
            ▼
POST /api/preprocess/{job_id}
  → Thread: _task_preprocess_and_recommend
  → MasterOrchestratorAgent.run_preprocessing_agent()
      → subprocess: preprocessing_workflow_agent.py
          → report_generator: dataset metadata JSON
          → preprocessing_steps.py: LLM → plan JSON
          → preprocessing_code_generator.py: LLM → preprocessing script
          → run_preprocessing_with_llm.py: execute script → processed_output.csv
      → reads workflow_memory.json → merges to master_memory.json
  → training_memory.ingest.record_run_after_preprocess()
  → LLMOrchestratorWorkflowAgent.generate_model_recommendations()
      → model_recommender.py: LLM → 3 model names + reasons
  → Status: "preprocessing_done"
            │
            ▼ (user selects models)
POST /api/validate/{job_id}
  → Thread: _task_validate
  → per selected model (up to 2 self-heal attempts each):
      → model_vc_gen.py: LLM → validation script
      → run_validation_code_with_llm.py: execute → parse metrics
          (on error: FIX_PROMPT → regenerate → retry)
  → validation_metrics stored in job + orchestrator_memory.json
  → Status: "validation_done"
            │
            ├─────────────────────────────────────┐
            ▼ (optional)                           ▼ (skip improvement)
POST /api/improve/{job_id}               POST /api/train/{job_id}
  → ImprovementWorkflowAgent                → _task_train
      → check feasibility                       → decide_warm_start()
      → improvement_steps_generator.py:         → generate_full_training_code.py:
          LLM → numbered steps                      LLM → full train script
      → improved_code_gen.py:                   → run_full_training_code_with_llm.py:
          LLM → improved script                     execute → save .pkl
      → improved_code_runner.py: run            → register_artifact()
  → improvement_memory.json                     → Status: "training_done"
  → Status: "improvement_done"
            │
            ▼
POST /api/confirm_improvement/{job_id}
  → patches orchestrator_memory.json
  → Status: "validation_done" (ready to train)
            │
            ▼
GET /api/deployment/{job_id}
  → returns predict URLs + example payload
            │
            ▼
User starts: uvicorn deployment/main:app --port 8000
  → loads *_full.pkl
  → POST /predict_raw → _run_preprocessing_on_raw → model.predict()
```

---

## Job State Machine

```
uploaded
    │
    ▼
preprocessing ──(error)──► error
    │
    ▼
preprocessing_done
    │
    ▼
validating ──(error)──► error
    │
    ▼
validation_done ◄─────────────────────────────────┐
    │                                              │
    ├──► improving ──(error)──► error              │
    │        │                                     │
    │        ▼                                     │
    │    improvement_done                          │
    │        │                                     │
    │        ├──(confirm)──► validation_done ──────┘
    │        └──(discard)──► validation_done
    │
    ▼
training ──(error)──► error
    │
    ▼
training_done
```

---

## Memory & State Files

| File | Location | Purpose | Lifetime |
|---|---|---|---|
| `master_memory.json` | `runs/{job_id}/` | Per-job authoritative state after preprocessing | Per-run |
| `master_memory.json` | `backend/` | Synced copy for deployment server | Overwritten per new run |
| `workflow_memory.json` | `runs/{job_id}/preprocessing/` | Preprocessing agent state | Per-run |
| `orchestrator_memory.json` | `runs/{job_id}/validation/` | Orchestrator state + validation metrics | Per-run |
| `improvement_memory.json` | `Improvement Agent/{dataset}/` | Improvement loop state + code paths | Per-dataset |
| `_jobs` dict | `api_server.py` in-memory | All live job states + logs | **Lost on server restart** |
| `intellimodel_users.db` | `backend/data/` | Users + sessions | Persistent |
| `training_catalog.db` | `backend/data/` | Training runs + artifacts fingerprints | Persistent |

> **Important:** Restarting the workflow API server (`api_server.py`) clears all in-memory job states. Do not run with `--reload`.

---

## Per-Run Artifacts

Each job creates a directory `backend/runs/{job_uuid}/` with the following structure:

```
runs/{job_id}/
├── {dataset}.csv                              # Original uploaded file
├── master_memory.json                         # Complete run state
│
├── preprocessing/
│   ├── {dataset}.json                         # Dataset metadata report
│   ├── {dataset}_preprocessing_plan.json      # LLM-generated plan
│   ├── {dataset}_preprocessing_plan.raw.txt   # Raw LLM response
│   ├── {dataset}_preprocessing_code.py        # Generated preprocessing script
│   ├── processed_output.csv                   # Preprocessed data
│   ├── {dataset}_processed.json               # Processed dataset report
│   └── workflow_memory.json                   # Preprocessing agent memory
│
├── validation/
│   ├── {model}_test.py                        # Generated validation script per model
│   └── orchestrator_memory.json               # Orchestrator + metrics state
│
├── training/
│   ├── {model}_test_full.py                   # Generated full-training script
│   └── {model}_full.pkl                       # Trained model artifact
│
└── improvement/
    ├── improved_code_gen.py                   # Copied improvement modules
    ├── improved_code_runner.py
    ├── improvement_steps_generator.py
    ├── improvement_workflow_agent.py
    ├── improvement_memory.json
    ├── improvement_steps.txt
    └── {dataset}/improved_training/
        └── {model}_improved_validation.py     # Improved script
```
