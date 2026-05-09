"""
Deployment API: FastAPI app for generating predictions from a trained PKL model.
Feature names are read from the preprocessed dataset report; file paths are read from
master agent memory (processed_output_report_path).

The /predict_raw endpoint accepts raw (original dataset) feature values, runs them
through the same preprocessing code that was used during training, and returns the
model prediction — so users never have to worry about encoded/scaled column names.

Usage
-----
    cd backend
    python deployment/main.py

    # Do NOT use --reload: the workflow server writes JSON files (master_memory.json,
    # orchestrator_memory.json, etc.) into the backend directory while running.
    # Uvicorn's --reload watcher would restart this server on every such write,
    # causing brief downtime during active pipeline runs.
    # If you need live-reload while editing this file, restrict watching to .py only:
    #
    #   uvicorn deployment.main:app --host 0.0.0.0 --port 8000 --reload \
    #       --reload-exclude "*.json" --reload-exclude "*.pkl" \
    #       --reload-exclude "Datasets/*"
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Deployment folder is backend/deployment; backend root is parent
BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MASTER_MEMORY_PATH = BACKEND_ROOT / "master_memory.json"


def _load_master_memory(master_memory_path: Optional[Path] = None) -> dict:
    """Load master memory JSON. Path from env MASTER_MEMORY_PATH or default."""
    path = master_memory_path or Path(os.environ.get("MASTER_MEMORY_PATH", str(DEFAULT_MASTER_MEMORY_PATH)))
    path = path.resolve() if not path.is_absolute() else path
    if not path.exists():
        raise FileNotFoundError(f"Master memory not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"master_memory.json is corrupted (invalid JSON): {path}\nError: {exc}"
        ) from exc


def _get_processed_output_report_path(master_memory: dict) -> Path:
    """Get processed_output_report_path from master memory (preprocessing section)."""
    prep = master_memory.get("preprocessing", {})
    path_str = prep.get("processed_output_report_path")
    if not path_str:
        raise ValueError(
            "preprocessing.processed_output_report_path not found in master memory. "
            "Run the preprocessing and save master memory first."
        )
    path = Path(path_str)
    if not path.is_absolute():
        path = (BACKEND_ROOT / path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Processed output report not found: {path}")
    return path


def _load_report_and_feature_names(report_path: Path) -> Tuple[List[str], Optional[str]]:
    """Load processed output report JSON; return (feature names, target_column)."""
    try:
        with report_path.open("r", encoding="utf-8") as f:
            report = json.load(f)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Processed output report is corrupted (invalid JSON): {report_path}\nError: {exc}"
        ) from exc
    columns = report.get("columns", {})
    if not columns:
        raise ValueError("Report has no 'columns' key or it is empty.")
    overview = report.get("dataset_overview", {})
    target = overview.get("target_column")
    return list(columns.keys()), target


def _resolve_pkl_path(master_memory: dict) -> Path:
    """Resolve path to the trained model PKL. Default: most recent *_full.pkl in full_training."""
    full_training_dir = BACKEND_ROOT / "LLM Orchestrator" / "full_training"
    if not full_training_dir.exists():
        raise FileNotFoundError(f"Full training directory not found: {full_training_dir}")
    pkl_files = list(full_training_dir.glob("*_full.pkl"))
    if not pkl_files:
        raise FileNotFoundError(f"No *_full.pkl file found in {full_training_dir}")
    return max(pkl_files, key=lambda p: p.stat().st_mtime)


def _get_preprocessing_code_path(master_memory: dict) -> Path:
    """Resolve the generated preprocessing code script from master memory."""
    prep = master_memory.get("preprocessing", {})
    code_path_str = prep.get("code_path")
    if not code_path_str:
        fh = master_memory.get("file_history", {})
        code_path_str = fh.get("preprocessing_code") or fh.get("generated_code")
    if not code_path_str:
        raise ValueError(
            "preprocessing.code_path not found in master memory. "
            "Run the preprocessing step first."
        )
    path = Path(code_path_str)
    if not path.is_absolute():
        path = (BACKEND_ROOT / path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Preprocessing code not found: {path}")
    return path


def _get_original_report(master_memory: dict) -> dict:
    """Load the original (pre-processing) dataset report from master memory."""
    prep = master_memory.get("preprocessing", {})
    report_path_str = (
        prep.get("report_path")
        or master_memory.get("file_history", {}).get("preprocessing_report")
        or master_memory.get("file_history", {}).get("report")
    )
    if report_path_str:
        rp = Path(report_path_str)
        if not rp.is_absolute():
            rp = (BACKEND_ROOT / rp).resolve()
        if rp.exists():
            with rp.open("r", encoding="utf-8") as f:
                return json.load(f)
    inline = prep.get("report")
    if inline and isinstance(inline, dict):
        return inline
    raise ValueError("Original dataset report not found in master memory.")


# Cached state — reloaded automatically when master_memory.json changes
_master_memory: Optional[dict] = None
_report_path: Optional[Path] = None
_feature_names: Optional[List[str]] = None
_model = None
_target_column: Optional[str] = None
_preprocessing_code_path: Optional[Path] = None
_original_report: Optional[dict] = None
_raw_feature_names: Optional[List[str]] = None
_mm_mtime: float = 0.0


def _ensure_loaded() -> None:
    """Load (or reload when master_memory.json has changed) all cached state."""
    global _master_memory, _report_path, _feature_names, _model, _target_column
    global _preprocessing_code_path, _original_report, _raw_feature_names
    global _mm_mtime

    mm_path = BACKEND_ROOT / "master_memory.json"
    try:
        current_mtime = mm_path.stat().st_mtime
    except FileNotFoundError:
        current_mtime = 0.0

    needs_reload = (
        _model is None
        or _feature_names is None
        or current_mtime != _mm_mtime
    )
    if not needs_reload:
        return

    _master_memory = _load_master_memory()
    _mm_mtime = current_mtime
    _report_path = _get_processed_output_report_path(_master_memory)
    _feature_names, _target_column = _load_report_and_feature_names(_report_path)
    if _target_column is None:
        _target_column = _master_memory.get("target_column")
    pkl_path = _resolve_pkl_path(_master_memory)
    _model = joblib.load(pkl_path)

    _preprocessing_code_path = _get_preprocessing_code_path(_master_memory)
    _original_report = _get_original_report(_master_memory)
    raw_cols = list(_original_report.get("columns", {}).keys())
    _raw_feature_names = [c for c in raw_cols if c != _target_column]


def _get_original_dataset_path(master_memory: dict) -> Path:
    """Resolve the path to the original (pre-preprocessing) training dataset."""
    path_str = master_memory.get("dataset_path") or master_memory.get(
        "file_history", {}
    ).get("dataset")
    if not path_str:
        raise ValueError(
            "Original dataset path not found in master memory (dataset_path). "
            "Run the preprocessing step first."
        )
    path = Path(path_str)
    if not path.is_absolute():
        path = (BACKEND_ROOT / path).resolve()
    if not path.exists():
        raise FileNotFoundError(
            f"Original training dataset not found at {path}. "
            "It is required to preprocess user inputs the same way the model was trained."
        )
    return path


def _run_preprocessing_on_raw(raw_row: Dict[str, Any]) -> pd.DataFrame:
    """
    Preprocess a single raw user row the SAME way the training dataset was
    preprocessed.

    Strategy (robust, no fit-skipping hacks):
      1. Load the original training dataset with encoding fallback.
      2. Coerce each user-supplied value to the same dtype as the corresponding
         training column so that numeric columns (e.g. year=2019) are never
         misclassified as dates and string categoricals are not force-cast to float.
      3. Tag the user row with a unique sentinel value in a temporary
         '__inference_marker__' column so that drop_duplicates() in the
         preprocessing script can never silently remove it (even if every feature
         value exactly matches a training row).
      4. Append the user row, write combined CSV, patch and run the script.
      5. Strip the sentinel column and return the last row by marker, not by
         positional index, so train-side dedup never causes an off-by-one error.
    """
    if (
        _preprocessing_code_path is None
        or _target_column is None
        or _master_memory is None
    ):
        raise RuntimeError("Preprocessing code / target / master memory not loaded.")

    dataset_path = _get_original_dataset_path(_master_memory)

    # ── 1. Load training data with encoding fallback ──────────────────────────
    try:
        original_df = pd.read_csv(dataset_path, encoding="utf-8")
    except UnicodeDecodeError:
        original_df = pd.read_csv(dataset_path, encoding="latin-1")

    if _target_column not in original_df.columns:
        raise RuntimeError(
            f"Target column '{_target_column}' missing from original dataset."
        )

    # ── 2. Placeholder for target, dtype-coerced feature values ──────────────
    target_series = original_df[_target_column]
    if pd.api.types.is_numeric_dtype(target_series):
        placeholder_target: Any = float(target_series.median())
    else:
        placeholder_target = target_series.mode(dropna=True).iloc[0]

    appended_row: Dict[str, Any] = {}
    for col in original_df.columns:
        if col == _target_column:
            appended_row[col] = placeholder_target
            continue

        if col not in raw_row:
            raise RuntimeError(
                f"Raw input is missing required feature: '{col}'"
            )

        val = raw_row[col]
        col_dtype = original_df[col].dtype

        # Coerce to match training column dtype to avoid date misclassification
        # and dtype conflicts in the combined DataFrame.
        if pd.api.types.is_integer_dtype(col_dtype):
            try:
                appended_row[col] = int(float(val))
            except (TypeError, ValueError):
                appended_row[col] = val
        elif pd.api.types.is_float_dtype(col_dtype):
            try:
                appended_row[col] = float(val)
            except (TypeError, ValueError):
                appended_row[col] = val
        elif pd.api.types.is_bool_dtype(col_dtype):
            if isinstance(val, bool):
                appended_row[col] = val
            else:
                appended_row[col] = str(val).lower() in ("1", "true", "yes")
        else:
            # String / object / categorical — keep as-is
            appended_row[col] = val

    missing_raw = [
        c for c in original_df.columns
        if c != _target_column and c not in raw_row
    ]
    if missing_raw:
        raise RuntimeError(
            f"Raw input is missing required feature(s): {missing_raw}"
        )

    # ── 3. Tag with unique sentinel so dedup cannot remove the user row ───────
    SENTINEL_COL = "__inference_marker__"
    SENTINEL_VAL = "__USER_INPUT_ROW__"
    original_df[SENTINEL_COL] = ""          # blank for all training rows
    appended_row[SENTINEL_COL] = SENTINEL_VAL

    combined_df = pd.concat(
        [original_df, pd.DataFrame([appended_row], columns=original_df.columns)],
        ignore_index=True,
    )

    tmp_dir = Path(tempfile.mkdtemp(prefix="intellimodel_pred_"))
    try:
        input_csv = tmp_dir / "input.csv"
        combined_df.to_csv(input_csv, index=False, encoding="utf-8")

        original_code = _preprocessing_code_path.read_text(encoding="utf-8")
        patched_code = _patch_preprocessing_code(
            original_code, str(input_csv), sentinel_col=SENTINEL_COL
        )

        script_path = tmp_dir / "preprocess.py"
        script_path.write_text(patched_code, encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(tmp_dir),
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Preprocessing script failed:\n{result.stderr[-2000:]}"
            )

        output_csv = tmp_dir / "processed_output.csv"
        if not output_csv.exists():
            raise FileNotFoundError(
                "Preprocessing script did not produce processed_output.csv in "
                f"{tmp_dir}"
            )

        df_out = pd.read_csv(output_csv, encoding="utf-8")

        # ── 5. Locate user row by sentinel, not by positional index ───────────
        if SENTINEL_COL in df_out.columns:
            user_rows = df_out[df_out[SENTINEL_COL] == SENTINEL_VAL]
            if user_rows.empty:
                raise RuntimeError(
                    "Preprocessing dropped the user's inference row (sentinel not found "
                    "in output). Check that the preprocessing script does not remove rows "
                    "based on outlier filtering or uniqueness constraints."
                )
            user_processed = user_rows.iloc[[0]].copy()
            user_processed = user_processed.drop(columns=[SENTINEL_COL])
        else:
            # Sentinel column was dropped by the preprocessing script — fall back
            # to the last row (safe only if the script preserves row order)
            if len(df_out) == 0:
                raise RuntimeError("Preprocessing produced an empty output CSV.")
            user_processed = df_out.iloc[[-1]].copy()

        if _target_column in user_processed.columns:
            user_processed = user_processed.drop(columns=[_target_column])

        # Align with the model's expected feature order. Fill any missing
        # one-hot dummies (reference category) with 0.
        for col in _feature_names:
            if col not in user_processed.columns:
                user_processed[col] = 0
        user_processed = user_processed[list(_feature_names)]
        return user_processed
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _patch_preprocessing_code(
    original_code: str, input_csv_path: str, sentinel_col: str = "__inference_marker__"
) -> str:
    """
    Minimal, safe patch for inference:

    1. Redirect only the FIRST pd.read_csv(...) call to the combined dataset.
       Uses a DOTALL regex so multi-line calls (with encoding=, dtype= kwargs
       spread over several lines) are matched correctly.

    2. Inject a snippet right after the read_csv replacement to:
       a. Preserve the sentinel column through the entire script so we can
          locate the user's row in the output even after drop_duplicates().
       b. Patch drop_duplicates() to exclude the sentinel column from the
          duplicate-detection comparison, so the user's row is NEVER removed
          even if every feature value happens to match a training row exactly.

    3. Neutralise uniqueness/shape assertions that would crash when the user
       row shares a value already present in training data.

    4. Inject code at the END of the script to carry the sentinel column
       through into processed_output.csv.
    """
    import re

    safe_input = input_csv_path.replace("\\", "\\\\")

    # ── 1. Replace first pd.read_csv(...) — DOTALL so multi-line args match ──
    patched = re.sub(
        r"pd\.read_csv\([\s\S]*?\)",   # DOTALL: matches across line breaks
        f"pd.read_csv(r'{safe_input}', encoding='utf-8')",
        original_code,
        count=1,
    )

    # ── 2a. Inject sentinel preservation right after the first read_csv line ─
    #    We find the replacement we just made and inject after the line it's on.
    SENTINEL_PRESERVE = f"""
# --- IntelliModel inference: preserve sentinel column ---
_inference_sentinel_col = {sentinel_col!r}
_inference_sentinel_vals = df[_inference_sentinel_col].copy() if _inference_sentinel_col in df.columns else None
# --------------------------------------------------------
"""
    # Insert after the first occurrence of the patched read_csv line
    first_read_csv_end = patched.find(f"pd.read_csv(r'{safe_input}'")
    if first_read_csv_end != -1:
        line_end = patched.find("\n", first_read_csv_end)
        if line_end == -1:
            line_end = len(patched)
        patched = patched[: line_end + 1] + SENTINEL_PRESERVE + patched[line_end + 1:]

    # ── 2b. Patch drop_duplicates() to exclude the sentinel column ────────────
    # Replace df.drop_duplicates() / df.drop_duplicates(inplace=True)
    # with a version that only considers non-sentinel columns for comparison.
    patched = re.sub(
        r"(df)\s*=\s*\1\.drop_duplicates\(\s*\)",
        (
            r"\1 = \1.drop_duplicates("
            f"subset=[c for c in \\1.columns if c != {sentinel_col!r}])"
        ),
        patched,
    )
    patched = re.sub(
        r"(df)\.drop_duplicates\(\s*inplace\s*=\s*True\s*\)",
        (
            r"\1.drop_duplicates("
            f"subset=[c for c in \\1.columns if c != {sentinel_col!r}], inplace=True)"
        ),
        patched,
    )

    # ── 3. Neutralise uniqueness / duplicate assertions ───────────────────────
    patched = re.sub(
        r"^\s*assert\b[^\n]*(?:nunique|unique\(\))[^\n]*(?:==|!=)[^\n]*(?:len\s*\(|nunique|shape)[^\n]*\n",
        "    pass  # inference: uniqueness assertion skipped\n",
        patched,
        flags=re.MULTILINE,
    )
    patched = re.sub(
        r"^\s*assert\b[^\n]*,\s*[\"'][^\n]*(?:[Dd]uplicate|[Uu]nique)[^\n]*[\"'][^\n]*\n",
        "    pass  # inference: uniqueness assertion skipped\n",
        patched,
        flags=re.MULTILINE,
    )

    # ── 4. Carry sentinel into the saved processed_output.csv ─────────────────
    # Find the to_csv(...) call and prepend a snippet that re-attaches the
    # sentinel column before saving, so we can locate the user row in output.
    SENTINEL_REATTACH = f"""
# --- IntelliModel inference: re-attach sentinel before saving ---
if _inference_sentinel_vals is not None:
    try:
        _sentinel_aligned = _inference_sentinel_vals.reindex(df.index).fillna('')
        df[{sentinel_col!r}] = _sentinel_aligned.values
    except Exception:
        pass
# ----------------------------------------------------------------
"""
    # Insert before the first .to_csv( that writes processed_output.csv
    to_csv_match = re.search(r"\.to_csv\(", patched)
    if to_csv_match:
        patched = patched[: to_csv_match.start()] + SENTINEL_REATTACH + patched[to_csv_match.start():]

    return patched


app = FastAPI(
    title="IntelliModel Prediction API",
    description=(
        "Generate predictions from the trained model. "
        "POST /predict_raw accepts original dataset features — preprocessing "
        "is applied automatically before prediction."
    ),
)

# Allow the Vite dev server (and any localhost origin) to call /predict from the browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PredictRequest(BaseModel):
    """Request body: feature names as keys, numeric values. Extra keys are ignored."""

    class Config:
        extra = "allow"


class PredictResponse(BaseModel):
    prediction: Any  # float for regression, str/int for classification
    target_column: Optional[str] = None
    task_type: Optional[str] = None  # 'regression' | 'classification' | 'forecasting'


class FeaturesResponse(BaseModel):
    features: List[str]
    processed_output_report_path: str
    target_column: Optional[str] = None


class RawFeaturesResponse(BaseModel):
    features: List[str]
    target_column: Optional[str] = None
    original_report: Optional[Dict[str, Any]] = None


@app.on_event("startup")
def startup() -> None:
    """Load model and feature names from master memory and processed report on startup."""
    try:
        _ensure_loaded()
        print(
            f"[IntelliModel] Model loaded successfully. "
            f"Features: {_feature_names}. Target: {_target_column}. "
            f"Raw features: {_raw_feature_names}."
        )
    except Exception as e:
        print(
            f"[IntelliModel] WARNING: Model not loaded at startup — {e}\n"
            "  The server is running but /predict will return 503 until the model is available.\n"
            "  Complete the training step in the workflow first, then restart this server."
        )


@app.get("/features", response_model=FeaturesResponse)
def get_features() -> FeaturesResponse:
    """
    Return the list of feature names required for prediction, read from the
    preprocessed dataset report (path from master memory: processed_output_report_path).
    """
    try:
        _ensure_loaded()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
    return FeaturesResponse(
        features=_feature_names,
        processed_output_report_path=str(_report_path),
        target_column=_target_column,
    )


@app.get("/raw_features", response_model=RawFeaturesResponse)
def get_raw_features() -> RawFeaturesResponse:
    """
    Return the original (pre-preprocessing) feature names so callers know what
    raw values to supply to POST /predict_raw.
    """
    try:
        _ensure_loaded()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
    return RawFeaturesResponse(
        features=_raw_feature_names or [],
        target_column=_target_column,
        original_report=_original_report,
    )


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest) -> PredictResponse:
    """
    Generate a prediction from the trained PKL model.
    Request body must contain the feature names returned by GET /features.
    """
    try:
        _ensure_loaded()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
    # Build feature vector in the order expected by the model
    data = request.model_dump(exclude_none=True)
    missing = [n for n in _feature_names if n not in data]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required features: {missing}. Required: {_feature_names}.",
        )
    try:
        X = [[float(data[name]) for name in _feature_names]]
    except (TypeError, ValueError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"All feature values must be numeric. Expected features: {_feature_names}. Error: {e}",
        )
    pred_raw = _model.predict(X)
    pred_val = pred_raw[0]
    try:
        prediction_out: Any = float(pred_val)
    except (TypeError, ValueError):
        prediction_out = str(pred_val)
    return PredictResponse(
        prediction=prediction_out,
        target_column=_target_column,
    )


@app.post("/predict_raw", response_model=PredictResponse)
def predict_raw(request: PredictRequest) -> PredictResponse:
    """
    Accept original (raw) dataset features, run the preprocessing pipeline on
    them, then generate a prediction.  The caller sends the same column names
    that appear in the original CSV (before encoding/scaling).
    """
    try:
        _ensure_loaded()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    data = request.model_dump(exclude_none=True)

    if not _raw_feature_names:
        raise HTTPException(
            status_code=503,
            detail="Raw feature names not loaded. Restart the server after training.",
        )

    missing = [n for n in _raw_feature_names if n not in data]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing raw features: {missing}. Required: {_raw_feature_names}.",
        )

    # Keep values as-is — dtype coercion to match training column types happens
    # inside _run_preprocessing_on_raw. Force-casting everything to float here
    # would break categorical features (e.g. "Male", "Urban") by raising ValueError
    # or silently producing NaN, which corrupts the preprocessing pipeline.
    raw_row: Dict[str, Any] = {name: data[name] for name in _raw_feature_names}

    try:
        processed_df = _run_preprocessing_on_raw(raw_row)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Preprocessing failed: {e}",
        )

    processed_cols = list(processed_df.columns)
    missing_model = [c for c in _feature_names if c not in processed_cols]
    if missing_model:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Preprocessing output is missing columns the model expects: {missing_model}. "
                f"Got: {processed_cols}"
            ),
        )

    try:
        X = processed_df[[c for c in _feature_names]].values[:1]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Could not build feature matrix after preprocessing: {e}",
        )

    pred_raw = _model.predict(X)
    pred_val = pred_raw[0]

    # Support both regression (numeric) and classification (string/int label)
    try:
        prediction_out: Any = float(pred_val)
    except (TypeError, ValueError):
        prediction_out = str(pred_val)

    # Determine task_type for the response
    task_type = (
        _master_memory.get("task_type")
        or _original_report.get("task_type")
        if _master_memory and _original_report
        else None
    )

    return PredictResponse(
        prediction=prediction_out,
        target_column=_target_column,
        task_type=task_type,
    )


@app.get("/health")
def health() -> Dict[str, Any]:
    """Health check. Indicates whether model and report are loaded."""
    try:
        _ensure_loaded()
        return {"status": "ok", "model_loaded": True, "features_count": len(_feature_names)}
    except Exception as e:
        return {"status": "degraded", "model_loaded": False, "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    # reload=False is intentional — see module-level docstring
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
