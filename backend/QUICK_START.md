# Quick Start Guide

## 🚀 Run Everything in 3 Steps

### Prerequisites
```powershell
# 1. Start Ollama (if not running)
ollama serve

# 2. Pull a model (if needed)
ollama pull phi4
```

---

## Step 1: Generate Dataset Report

```powershell
cd "Pre Processing Agent"
python report_generator.py --csv "../Datasets/Housing.csv" --target "price" --output "../Housing.json"
cd ..
```

**Output**: `Housing.json` (dataset analysis report)

---

## Step 2: Train Models (Uses Report Directly)

```powershell
cd "Reasoning Agent"

# Train models (complete pipeline - uses Pre Processing report directly)
python -m src.main train-models "../housing report.json" "../Datasets/Housing.csv" ^
  --test-size 0.2

cd ..
```

**Output**: 
- `generated_code/Housing_validate_models.py` (validation code)
- `generated_code/Housing_deploy_best_model.py` (deployment code)

**Note**: No metadata generation needed! The Reasoning Agent uses the Pre Processing Agent report directly.

---

## Step 3: Run Generated Code

```powershell
cd "Reasoning Agent"
python generated_code/Housing_validate_models.py
```

---

## 📋 For Different Datasets

### Housing Dataset (Regression)
```powershell
# Step 1
cd "Pre Processing Agent"
python report_generator.py --csv "../Datasets/Housing.csv" --target "price" --output "../Housing.json"
cd ..

# Step 2
cd "Reasoning Agent"
python -m src.main train-models "../Housing.json" "../Datasets/Housing.csv" --test-size 0.2
cd ..
```

### AAPL Dataset (Classification)
```powershell
# Step 1
cd "Pre Processing Agent"
python report_generator.py --csv "../Datasets/AAPL.csv" --target "Day" --output "../AAPL.json"
cd ..

# Step 2
cd "Reasoning Agent"
python -m src.main train-models "../AAPL.json" "../Datasets/AAPL.csv" --test-size 0.2
cd ..
```

---

## 📁 Output Files Structure

```
IntelliModel/
├── Housing.json                          # Dataset report (from Pre Processing Agent)
├── AAPL.json                             # Dataset report (from Pre Processing Agent)
├── Datasets/
│   ├── Housing.csv
│   ├── AAPL.csv
│   └── ...
└── Reasoning Agent/
    └── generated_code/
        ├── Housing_validate_models.py    # Validation code
        ├── Housing_deploy_best_model.py  # Deployment code
        ├── AAPL_validate_models.py      # Validation code
        └── AAPL_deploy_best_model.py    # Deployment code
```

---

## ⚡ One-Liner (After Setup)

```powershell
# For Housing dataset
cd "Pre Processing Agent" && python report_generator.py --csv "../Datasets/Housing.csv" --target "price" --output "../Housing.json" && cd .. && cd "Reasoning Agent" && python -m src.main train-models "../Housing.json" "../Datasets/Housing.csv" --test-size 0.2 && cd ..
```

---

## Google Sign-In and user database (optional)
## 🔧 Troubleshooting

Full checklist, file list, and verification steps: **[AUTH_SETUP.md](../AUTH_SETUP.md)** in the repo root.
**Ollama not running?**
```powershell
ollama serve
```

The workflow API (`api_server.py`) stores basic Google profile fields in **SQLite** and issues an HTTP-only session cookie after sign-in.
**Missing dependencies?**
```powershell
cd "Pre Processing Agent" && pip install -r requirements.txt && cd ..
cd "Reasoning Agent" && pip install -r requirements.txt && cd ..
```

**Backend**
**File not found?**
- Make sure you're in the correct directory
- Check that dataset files exist in `Datasets/` folder
- Use relative paths: `../Datasets/Housing.csv`

1. Install dependencies from `backend/requirements.txt` (includes `google-auth`).
2. Environment variables:
   - `GOOGLE_OAUTH_CLIENT_ID` — OAuth 2.0 **Web** client ID from Google Cloud Console (must match the frontend).
   - `INTELLIMODEL_CORS_ORIGINS` — Comma-separated browser origins allowed to send cookies (default: `http://localhost:5173,http://127.0.0.1:5173`).
   - `INTELLIMODEL_SQLITE_PATH` — Optional full path to the SQLite file (default: `backend/data/intellimodel_users.db`).
   - `INTELLIMODEL_COOKIE_SECURE` — Set to `true` in production (HTTPS) so the session cookie is marked `Secure`.
---

**Frontend**
For detailed documentation, see `COMPLETE_WORKFLOW_GUIDE.md`

1. Copy `Frontend/.env.example` to `Frontend/.env.local`.
2. Set `VITE_GOOGLE_CLIENT_ID` to the same Web client ID.
3. In Google Cloud Console, under the OAuth client, add **Authorized JavaScript origins** for your dev URL (for example `http://localhost:5173`).

**Auth endpoints**

- `POST /api/auth/google` — body `{ "credential": "<Google ID token>" }`, sets cookie `im_session`.
- `GET /api/auth/me` — returns the signed-in user or `401`.
- `POST /api/auth/logout` — clears the session.

---

## Training run catalog (v1)

After each job finishes **preprocessing**, a row is written to **`backend/data/training_catalog.db`** (read-only ingest from `runs/<job_id>/master_memory.json`). See **`TRAINING_MEMORY_V1.md`** in the repo root and `backend/training_memory/README.md`. Optional env: `TRAINING_CATALOG_SQLITE_PATH`.

Read-only API: **`GET /api/training/similar/{job_id}`** — similar prior runs from the catalog (no UI in this repo change).

Optional warm-start decisioning toggles:
- `TRAINING_MEMORY_DECISION_ENABLED=false`
- `TRAINING_MEMORY_POLICY=none` (`warm_start_if_compatible` to enable compatible-candidate reuse)
- `TRAINING_MEMORY_PROMOTION_DELTA=0.0` (minimum normalized score gain to promote a new artifact)

Startup note: API startup runs idempotent training catalog initialization, so existing `training_catalog.db` files are backfilled with newer tables (for example `training_artifacts`) automatically.

---

## 🔧 Troubleshooting

**Ollama not running?**
```powershell
ollama serve
```

**Missing dependencies?**
```powershell
cd "Pre Processing Agent" && pip install -r requirements.txt && cd ..
cd "Reasoning Agent" && pip install -r requirements.txt && cd ..
```

**File not found?**
- Make sure you're in the correct directory
- Check that dataset files exist in `Datasets/` folder
- Use relative paths: `../Datasets/Housing.csv`

---

For detailed documentation, see `COMPLETE_WORKFLOW_GUIDE.md`

