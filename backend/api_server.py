"""
IntelliModel Workflow API Server
=================================
FastAPI app that exposes the full ML pipeline as HTTP endpoints for the React
frontend.  No agent logic is duplicated here — every route delegates to the
same Python functions already used by the Streamlit app (Frontend/app.py),
after setting up the same sys.path entries.

Routes
------
POST  /api/upload               – upload CSV, get job_id
POST  /api/preprocess/{job_id}  – run preprocessing + LLM recommendations (async)
GET   /api/status/{job_id}      – poll status / logs / results
POST  /api/validate/{job_id}    – run model validation for selected models (async)
POST  /api/train/{job_id}       – generate + run full training code (async)
POST  /api/improve/{job_id}     – run improvement agent (async)
GET   /api/deployment/{job_id}  – return /predict URL + example payload
GET   /api/health               – server health

Ports
-----
This server:          http://localhost:9000
Deployment server:    http://localhost:8000  (backend/deployment/main.py)

Usage
-----
    cd backend
    python api_server.py

    # ── Development note ──────────────────────────────────────────────────────
    # Do NOT use "uvicorn api_server:app --reload" here.
    # The preprocessing / training agents write JSON files (master_memory.json,
    # orchestrator_memory.json, etc.) into this directory while they run.
    # Uvicorn's --reload watcher treats those writes as source-code changes,
    # restarts the server process, and wipes the in-memory _jobs dict — causing
    # every subsequent GET /api/status/{job_id} to return 404 while the
    # background thread is still running.
    #
    # If you need live-reload for editing api_server.py itself, restrict the
    # watched directory to only .py files and exclude the data directories:
    #
    #   uvicorn api_server:app --port 9000 --reload \
    #       --reload-dir . \
    #       --reload-exclude "*.json" \
    #       --reload-exclude "Datasets/*" \
    #       --reload-exclude "Pre Processing Agent/*" \
    #       --reload-exclude "LLM Orchestrator/*" \
    #       --reload-exclude "Improvement Agent/*"
"""
import re
from typing import Any, Dict
import json
import sys
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import uvicorn
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Path setup — mirrors Frontend/app.py _add_backend_to_path()
# ---------------------------------------------------------------------------
BACKEND_ROOT = Path(__file__).resolve().parent
PREPROCESSING_DIR = BACKEND_ROOT / "Pre Processing Agent"
LLM_ORCHESTRATOR_DIR = BACKEND_ROOT / "LLM Orchestrator"
IMPROVEMENT_DIR = BACKEND_ROOT / "Improvement Agent"
DATASETS_DIR = BACKEND_ROOT / "Datasets"
RUNS_DIR = BACKEND_ROOT / "runs"


def _job_output_dir(job_id: str) -> Path:
    """Return (and create) the per-job output directory with stage subdirs."""
    base = RUNS_DIR / job_id
    for sub in ("preprocessing", "validation", "training", "improvement"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base

for _p in [
    str(BACKEND_ROOT),
    str(PREPROCESSING_DIR),
    str(LLM_ORCHESTRATOR_DIR),
    str(IMPROVEMENT_DIR),
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# In-memory job store
# ---------------------------------------------------------------------------
@dataclass
class JobState:
    job_id: str
    csv_path: Path
    target_column: str
    goal: str
    output_dir: Path = field(default_factory=lambda: Path("."))
    status: str = "uploaded"
    # status progression:
    #   uploaded → preprocessing → preprocessing_done
    #            → recommending  → preprocessing_done  (re-recommendation)
    #            → validating    → validation_done
    #            → training      → training_done
    #            → improving     → improvement_done
    #   any step → error
    logs: str = ""
    error: Optional[str] = None
    # Populated after preprocessing
    recommendations_text: Optional[str] = None
    recommended_models: List[str] = field(default_factory=list)
    preprocessing_plan: Optional[Dict[str, Any]] = None
    task_type: Optional[str] = None
    # Populated after validation
    validation_metrics: Optional[Dict[str, Any]] = None
    # Populated after training
    training_code_path: Optional[str] = None
    # Populated after improvement
    improvement_steps: Optional[str] = None
    improved_metrics: Optional[Dict[str, Any]] = None
    original_metrics: Optional[Dict[str, Any]] = None
    regeneration_count: int = 0
    improvement_memory_path: Optional[str] = None
    improvement_halted: bool = False
    improvement_halt_reason: Optional[str] = None
    improvement_run_succeeded: Optional[bool] = None
    improvement_run_error: Optional[str] = None


_jobs: Dict[str, JobState] = {}
_jobs_lock = threading.Lock()


def _get_job(job_id: str) -> JobState:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job


# ---------------------------------------------------------------------------
# Log capture
# ---------------------------------------------------------------------------
# Thread-local registry: maps thread-id → _JobLogCapture instance.
# This lets the write proxy route output only for the agent thread, while
# uvicorn's request-handler threads (status polls, health checks, etc.) still
# write directly to the original stdout/stderr.
_capture_registry: Dict[int, "_JobLogCapture"] = {}
_registry_lock = threading.Lock()


class _WriteProxy:
    """
    Installed once as sys.stdout / sys.stderr at startup.
    Writes are routed to the active _JobLogCapture for the calling thread
    (if one is registered) and always also forwarded to the real stream.
    """

    def __init__(self, real_stream: Any) -> None:
        self._real = real_stream

    def write(self, text: str) -> None:
        tid = threading.get_ident()
        with _registry_lock:
            capture = _capture_registry.get(tid)
        if capture is not None:
            capture._job.logs += text
        self._real.write(text)

    def flush(self) -> None:
        self._real.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


# Install the proxies once at import time so every thread shares them.
_real_stdout = sys.stdout
_real_stderr = sys.stderr
sys.stdout = _WriteProxy(_real_stdout)  # type: ignore[assignment]
sys.stderr = _WriteProxy(_real_stderr)  # type: ignore[assignment]


class _JobLogCapture:
    """
    Register the current (background) thread so that its stdout/stderr output
    is captured into the job log buffer.  The proxy installed above handles
    the actual routing; this class just manages the registry entry.
    """

    def __init__(self, job: JobState) -> None:
        self._job = job
        self._tid: Optional[int] = None

    def __enter__(self) -> "_JobLogCapture":
        self._tid = threading.get_ident()
        with _registry_lock:
            _capture_registry[self._tid] = self
        return self

    def __exit__(self, *_: Any) -> None:
        if self._tid is not None:
            with _registry_lock:
                _capture_registry.pop(self._tid, None)
            self._tid = None

    def write(self, text: str) -> None:
        self._job.logs += text

    def flush(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Background task implementations
# Each function runs in a daemon thread and updates job.status / fields.
# Imports are deferred to the function body so that the FastAPI app starts
# instantly even if heavy agent deps (langgraph, langchain, etc.) are slow.
# ---------------------------------------------------------------------------

def _task_preprocess_and_recommend(job: JobState) -> None:
    """Thread: preprocessing agent → LLM model recommendations."""
    job.status = "preprocessing"
    out = job.output_dir
    mm_path = out / "master_memory.json"
    try:
        from master_orchestrator import MasterOrchestratorAgent  # type: ignore[import]
        from llm_orchestrator_workflow_agent import LLMOrchestratorWorkflowAgent  # type: ignore[import]
        from model_recommender import parse_model_names  # type: ignore[import]
        with _JobLogCapture(job):
            # Step 1 – preprocessing agent
            orchestrator = MasterOrchestratorAgent(output_dir=out)
            orchestrator.run_preprocessing_agent(
                csv_path=job.csv_path,
                target_column=job.target_column,
                context=job.goal,
            )
            orchestrator.save_memory(mm_path)

            # Also save a copy to BACKEND_ROOT for the deployment server
            _sync_master_memory(mm_path)

            # Step 2 – LLM model recommendations (stops before user model selection)
            llm_agent = LLMOrchestratorWorkflowAgent(
                master_memory_path=mm_path,
                output_dir=LLM_ORCHESTRATOR_DIR,
            )
            llm_agent.load_master_memory()
            recommendations_text = llm_agent.generate_model_recommendations()
            llm_agent.save_memory()

            job.recommendations_text = recommendations_text
            job.recommended_models = parse_model_names(recommendations_text)
            job.preprocessing_plan = orchestrator.memory.preprocessing_plan or {}
            job.task_type = orchestrator.memory.task_type

            # Fallback: read plan and task_type from master_memory.json if agent memory is empty
            if mm_path.exists():
                with mm_path.open("r", encoding="utf-8") as fh:
                    mm = json.load(fh)
                if not job.preprocessing_plan:
                    job.preprocessing_plan = mm.get("preprocessing", {}).get("plan", {})
                if not job.task_type:
                    job.task_type = mm.get("task_type")

        _collect_artifacts(job)
        job.status = "preprocessing_done"

    except Exception as exc:
        job.status = "error"
        job.error = str(exc)
        job.logs += f"\n[ERROR] {exc}"


def _task_recommend(job: JobState) -> None:
    """Thread: re-generate model recommendations (excluding previously validated models)."""
    job.status = "recommending"
    out = job.output_dir
    mm_path = out / "master_memory.json"
    orch_memory_path = LLM_ORCHESTRATOR_DIR / "orchestrator_memory.json"
    try:
        from llm_orchestrator_workflow_agent import LLMOrchestratorWorkflowAgent  # type: ignore[import]
        from model_recommender import parse_model_names  # type: ignore[import]
        with _JobLogCapture(job):
            llm_agent = LLMOrchestratorWorkflowAgent(
                master_memory_path=mm_path,
                output_dir=LLM_ORCHESTRATOR_DIR,
            )
            llm_agent.load_master_memory()
            if orch_memory_path.exists():
                llm_agent.load_memory(orch_memory_path)

            # Inject job-level validation_metrics as a safety net in case
            # orchestrator_memory.json was overwritten by load_master_memory
            if job.validation_metrics and not llm_agent.memory.validation_metrics:
                llm_agent.memory.validation_metrics = job.validation_metrics

            # Log which models will be excluded
            to_exclude = set(llm_agent.memory.validation_history or [])
            to_exclude.update(llm_agent.memory.validation_metrics.keys())
            print(f"[RE-RECOMMEND] Models to exclude: {sorted(to_exclude)}")

            # Move validated models into validation_history so the LLM is told
            # to exclude them, then generate fresh recommendations
            llm_agent._prepare_for_reselection()

            recommendations_text = llm_agent.generate_model_recommendations()
            llm_agent.save_memory()

            job.recommendations_text = recommendations_text
            job.recommended_models = parse_model_names(recommendations_text)

        job.status = "preprocessing_done"

    except Exception as exc:
        job.status = "error"
        job.error = str(exc)
        job.logs += f"\n[ERROR] {exc}"


def _sync_master_memory(src: Path) -> None:
    """Copy master_memory.json to BACKEND_ROOT so the deployment server can find it."""
    import shutil
    dst = BACKEND_ROOT / "master_memory.json"
    try:
        shutil.copy2(str(src), str(dst))
    except Exception:
        pass


def _collect_artifacts(job: JobState) -> None:
    """
    Copy runtime-generated artifacts from agent directories into the per-job
    output dir so that runs/{job_id}/ is self-contained.
    """
    import shutil
    out = job.output_dir

    def _copy_glob(src_dir: Path, pattern: str, dest_dir: Path) -> None:
        dest_dir.mkdir(parents=True, exist_ok=True)
        for f in src_dir.glob(pattern):
            if f.is_file():
                try:
                    shutil.copy2(str(f), str(dest_dir / f.name))
                except Exception:
                    pass

    # Validation scripts
    val_src = LLM_ORCHESTRATOR_DIR / "model_testing"
    if val_src.exists():
        _copy_glob(val_src, "*.py", out / "validation")

    # Orchestrator memory
    orch_mem = LLM_ORCHESTRATOR_DIR / "orchestrator_memory.json"
    if orch_mem.exists():
        try:
            shutil.copy2(str(orch_mem), str(out / "validation" / "orchestrator_memory.json"))
        except Exception:
            pass

    # Full training code + pkl
    ft_src = LLM_ORCHESTRATOR_DIR / "full_training"
    if ft_src.exists():
        _copy_glob(ft_src, "*.py", out / "training")
        _copy_glob(ft_src, "*.pkl", out / "training")

    # Improvement artifacts
    # Improvement agent now writes dataset-scoped files under
    # `Improvement Agent/<dataset_name>/...`. Preserve those by copying:
    #   1) direct files in IMPROVEMENT_DIR (legacy layout), and
    #   2) recursively from the dataset folder inferred from improvement_memory_path.
    for pattern in ("*.py", "*.json", "*.txt"):
        _copy_glob(IMPROVEMENT_DIR, pattern, out / "improvement")

    def _copy_recursive(src_root: Path, pattern: str, dest_root: Path) -> None:
        for f in src_root.rglob(pattern):
            if not f.is_file():
                continue
            try:
                rel = f.relative_to(src_root)
            except Exception:
                rel = Path(f.name)
            dst = dest_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(str(f), str(dst))
            except Exception:
                pass

    if job.improvement_memory_path:
        mem_path = Path(job.improvement_memory_path)
        if mem_path.exists():
            dataset_dir = mem_path.parent
            # Keep dataset folder name to avoid collisions across runs/datasets.
            dest = out / "improvement" / dataset_dir.name
            for pattern in ("*.py", "*.json", "*.txt"):
                _copy_recursive(dataset_dir, pattern, dest)


def _task_validate(job: JobState, selected_models: List[str]) -> None:
    """Thread: generate + run validation code for selected models."""
    job.status = "validating"
    try:
        from llm_orchestrator_workflow_agent import LLMOrchestratorWorkflowAgent  # type: ignore[import]
    except Exception as exc:
        job.status = "error"
        job.error = str(exc)
        job.logs += f"\n[ERROR] Import failed: {exc}"
        return
    out = job.output_dir
    master_memory_path = out / "master_memory.json"
    orchestrator_memory_path = LLM_ORCHESTRATOR_DIR / "orchestrator_memory.json"

    try:
        with _JobLogCapture(job):
            llm_agent = LLMOrchestratorWorkflowAgent(
                master_memory_path=master_memory_path,
                output_dir=LLM_ORCHESTRATOR_DIR,
            )
            llm_agent.load_master_memory()
            if orchestrator_memory_path.exists():
                llm_agent.load_memory(orchestrator_memory_path)
            else:
                llm_agent.memory.master_memory_path = master_memory_path
                llm_agent.save_memory()

            validation_metrics: Dict[str, Any] = {}
            last_error: Optional[Exception] = None

            # Two self-healing attempts (mirrors Streamlit app behaviour)
            for attempt in range(2):
                try:
                    # Bypass interactive input() by injecting selected models directly
                    llm_agent.memory.selected_models_for_validation = selected_models
                    llm_agent.save_memory()
                    llm_agent.generate_validation_code()
                    llm_agent.run_validation_code()
                    # Reload memory — run_validation_code() updates the file
                    if orchestrator_memory_path.exists():
                        llm_agent.load_memory(orchestrator_memory_path)
                    validation_metrics = llm_agent.memory.validation_metrics or {}
                    if validation_metrics:
                        break
                    job.logs += f"\n[WARN] Attempt {attempt + 1}: no metrics captured, retrying…"
                except Exception as exc:
                    last_error = exc
                    job.logs += f"\n[WARN] Attempt {attempt + 1} failed: {exc}"

            if not validation_metrics:
                msg = "Validation produced no metrics after 2 attempts."
                if last_error:
                    msg += f" Last error: {last_error}"
                raise RuntimeError(msg)

            job.validation_metrics = validation_metrics

            # Capture task_type — run_validation_code_with_llm.py writes it into
            # orchestrator_memory.json; read it back directly since OrchestratorMemory
            # has no task_type field and load_memory() does not restore it.
            if not job.task_type and orchestrator_memory_path.exists():
                try:
                    with orchestrator_memory_path.open("r", encoding="utf-8") as _f:
                        _om = json.load(_f)
                    job.task_type = _om.get("task_type")
                except Exception:
                    pass
            # Final fallback: read from master_memory.json
            if not job.task_type and master_memory_path.exists():
                try:
                    with master_memory_path.open("r", encoding="utf-8") as _f:
                        _mm = json.load(_f)
                    job.task_type = (
                        _mm.get("task_type")
                        or _mm.get("preprocessing", {}).get("report", {}).get("task_type")
                    )
                except Exception:
                    pass

        _collect_artifacts(job)
        job.status = "validation_done"

    except Exception as exc:
        job.status = "error"
        job.error = str(exc)
        job.logs += f"\n[ERROR] {exc}"


def _improvement_memory_resolved_validation_code_path(
    imp_mem: Dict[str, Any],
) -> Tuple[Optional[str], bool]:
    """
    Full-training base script: prefer improved_validation_code_path, else validation_code_path.

    Returns (resolved_path_or_none, used_improved_key) where used_improved_key is True iff
    improved_validation_code_path was a non-empty string.
    """
    imp_raw = imp_mem.get("improved_validation_code_path")
    val_raw = imp_mem.get("validation_code_path")
    improved = imp_raw.strip() if isinstance(imp_raw, str) else None
    if improved == "":
        improved = None
    fallback = val_raw.strip() if isinstance(val_raw, str) else None
    if fallback == "":
        fallback = None
    resolved: Optional[str] = improved or fallback
    return resolved, bool(improved)


def _log_full_training_validation_code_path_source(used_improved: bool, resolved: Optional[str]) -> None:
    if not resolved:
        return
    if used_improved:
        print("[INFO] Using improved validation code for full training.")
    else:
        print(
            "[INFO] No improved code found — using original validation code for full training "
            "(metrics were already good enough)."
        )


def _patch_orchestrator_from_improvement_memory_for_train(
    job: JobState,
    llm_agent: Any,
    model_name: str,
) -> None:
    """
    If improvement_memory.json exists for this job, sync validation_metrics[model].code_path
    into the orchestrator agent memory so generate_full_training_code reads the right base.
    """
    if not job.improvement_memory_path:
        return
    mem_path = Path(job.improvement_memory_path)
    if not mem_path.is_file():
        return
    try:
        with mem_path.open("r", encoding="utf-8") as fh:
            imp_mem = json.load(fh)
    except Exception:
        return
    resolved, used_improved = _improvement_memory_resolved_validation_code_path(imp_mem)
    if not resolved or not Path(resolved).exists():
        return

    def _norm(n: str) -> str:
        return n.lower().replace(" ", "").replace("_", "").replace("-", "")

    vm = llm_agent.memory.validation_metrics or {}
    matched = next((k for k in vm if _norm(k) == _norm(model_name)), None)
    if not matched:
        return
    entry = vm[matched]
    if not isinstance(entry, dict):
        return
    _log_full_training_validation_code_path_source(used_improved, resolved)
    if entry.get("code_path") == resolved:
        return
    entry["code_path"] = resolved
    llm_agent.save_memory()


def _task_train(job: JobState, model_name: str) -> None:
    """Thread: generate + run full training code, save .pkl artifact."""
    job.status = "training"
    try:
        from llm_orchestrator_workflow_agent import LLMOrchestratorWorkflowAgent  # type: ignore[import]
    except Exception as exc:
        job.status = "error"
        job.error = str(exc)
        job.logs += f"\n[ERROR] Import failed: {exc}"
        return
    out = job.output_dir
    master_memory_path = out / "master_memory.json"
    orchestrator_memory_path = LLM_ORCHESTRATOR_DIR / "orchestrator_memory.json"

    try:
        with _JobLogCapture(job):
            llm_agent = LLMOrchestratorWorkflowAgent(
                master_memory_path=master_memory_path,
                output_dir=LLM_ORCHESTRATOR_DIR,
            )

            # Snapshot validation_metrics BEFORE load_master_memory calls save_memory()
            # internally and overwrites orchestrator_memory.json with a fresh (empty) state.
            _saved_vm: dict = {}
            if orchestrator_memory_path.exists():
                try:
                    with orchestrator_memory_path.open("r", encoding="utf-8") as _f:
                        _saved_vm = json.load(_f).get("validation_metrics") or {}
                except Exception:
                    pass

            llm_agent.load_master_memory()
            if orchestrator_memory_path.exists():
                llm_agent.load_memory(orchestrator_memory_path)

            # Restore validation_metrics if load_master_memory wiped them from the file.
            if not llm_agent.memory.validation_metrics and _saved_vm:
                llm_agent.memory.validation_metrics = _saved_vm
                llm_agent.save_memory()

            # Prefer improved_validation_code_path from improvement_memory.json; fall back to
            # validation_code_path when improvement skipped (e.g. metrics already excellent).
            _patch_orchestrator_from_improvement_memory_for_train(job, llm_agent, model_name)

            # Generate full training code (*_full.py) then execute it → .pkl
            llm_agent.generate_full_training_code(model_name)
            llm_agent.memory.selected_model_for_full_training = model_name
            llm_agent.save_memory()
            llm_agent.run_full_training_code()

            # Resolve the generated training script path
            training_code_path: Optional[Path] = None
            validation_metrics = llm_agent.memory.validation_metrics or {}
            if model_name in validation_metrics:
                vcp = validation_metrics[model_name].get("code_path")
                if vcp:
                    candidate = LLM_ORCHESTRATOR_DIR / "full_training" / (
                        Path(vcp).stem + "_full.py"
                    )
                    if candidate.exists():
                        training_code_path = candidate

            if not training_code_path:
                full_dir = LLM_ORCHESTRATOR_DIR / "full_training"
                if full_dir.exists():
                    py_files = sorted(
                        full_dir.glob("*_full.py"),
                        key=lambda p: p.stat().st_mtime,
                    )
                    if py_files:
                        training_code_path = py_files[-1]

            job.training_code_path = (
                str(training_code_path.resolve()) if training_code_path else None
            )

            _sync_master_memory(master_memory_path)

        _collect_artifacts(job)
        job.status = "training_done"

    except Exception as exc:
        job.status = "error"
        job.error = str(exc)
        job.logs += f"\n[ERROR] {exc}"


def _task_improve(job: JobState, model_name: str) -> None:
    """Thread: improvement agent — generate steps, improved code, and new metrics."""
    job.status = "improving"
    try:
        from improvement_workflow_agent import (  # type: ignore[import]
            ImprovementWorkflowAgent,
            MetricsAlreadyGoodError,
        )
    except Exception as exc:
        job.status = "error"
        job.error = str(exc)
        job.logs += f"\n[ERROR] Import failed: {exc}"
        return
    out = job.output_dir
    master_memory_path = out / "master_memory.json"
    orchestrator_memory_path = LLM_ORCHESTRATOR_DIR / "orchestrator_memory.json"

    try:
        with master_memory_path.open("r", encoding="utf-8") as fh:
            master_memory = json.load(fh)

        # Prefer in-memory validation metrics (most up-to-date); fall back to disk
        validation_metrics_full: Dict[str, Any] = job.validation_metrics or {}
        if not validation_metrics_full:
            orch = master_memory.get("llm_orchestrator", {}).get("orchestrator_memory", {})
            validation_metrics_full = orch.get("validation_metrics", {})

        def _norm(name: str) -> str:
            return name.lower().replace(" ", "").replace("_", "").replace("-", "")

        matched_model = next(
            (m for m in validation_metrics_full if _norm(m) == _norm(model_name)),
            None,
        )
        if matched_model is None:
            raise ValueError(
                f"Model '{model_name}' not found in validated models. "
                f"Available: {list(validation_metrics_full.keys())}"
            )

        with _JobLogCapture(job):
            job.improvement_halted = False
            job.improvement_halt_reason = None
            job.improvement_run_succeeded = None
            job.improvement_run_error = None

            agent = ImprovementWorkflowAgent(
                master_memory_path=master_memory_path,
                output_dir=IMPROVEMENT_DIR,
            )

            # Initialise per-dataset output folder (mirrors load_master_memory behaviour)
            dataset_name: str = (
                master_memory.get("dataset_name")
                or master_memory.get("name")
                or "dataset"
            )
            agent.memory.dataset_name = dataset_name
            agent._init_output_dir(dataset_name)

            agent.memory.dataset_context = master_memory.get("context_of_dataset")
            prep = master_memory.get("preprocessing", {})
            if prep.get("report_path"):
                agent.memory.dataset_report_path = Path(prep["report_path"])

            agent.memory.model_name = matched_model
            info = validation_metrics_full[matched_model]
            if not isinstance(info, dict):
                raise ValueError(f"Unexpected metrics format for {matched_model}: {type(info)}")

            if "metrics" in info:
                agent.memory.validation_metrics = info.get("metrics", {}) or {}
                code_path_str: Optional[str] = info.get("code_path")
            else:
                agent.memory.validation_metrics = info
                code_path_str = None

            if code_path_str:
                agent.memory.validation_code_path = Path(code_path_str)
            elif orchestrator_memory_path.exists():
                with orchestrator_memory_path.open("r", encoding="utf-8") as fh:
                    orch = json.load(fh)
                vm = orch.get("validation_metrics", {})
                if matched_model in vm:
                    cp = vm[matched_model].get("code_path")
                    if cp:
                        agent.memory.validation_code_path = Path(cp)

            # Guard rails — mirror the Streamlit validation checks
            missing: List[str] = []
            if not agent.memory.model_name:
                missing.append("model_name")
            if not agent.memory.validation_metrics:
                missing.append(f"validation_metrics for {matched_model}")
            if not agent.memory.dataset_context:
                missing.append("context_of_dataset")
            if not agent.memory.dataset_report_path:
                missing.append("preprocessing.report_path")
            if not agent.memory.validation_code_path:
                missing.append(f"validation_code_path for {matched_model}")
            if missing:
                raise ValueError(f"Missing required fields: {', '.join(missing)}")

            # Carry regeneration_count forward across cycles: read from existing
            # improvement_memory.json written by a previous cycle (if any).
            prev_mem_path: Optional[Path] = None
            if job.improvement_memory_path:
                prev_mem_path = Path(job.improvement_memory_path)
            elif agent.memory_file_path and agent.memory_file_path.exists():
                prev_mem_path = agent.memory_file_path

            if prev_mem_path and prev_mem_path.exists():
                try:
                    with prev_mem_path.open("r", encoding="utf-8") as fh:
                        prev = json.load(fh)
                    agent.memory.regeneration_count = int(prev.get("regeneration_count", 0))
                except Exception:
                    pass

            agent.save_memory()

            try:
                improvement_steps = agent.generate_improvement_steps()
            except MetricsAlreadyGoodError as exc:
                # Baseline already excellent — skip code gen / runner; finish as success.
                msg = str(exc)
                job.improvement_steps = msg
                job.original_metrics = agent.memory.validation_metrics or {}
                job.improved_metrics = dict(job.original_metrics)
                job.improvement_run_succeeded = False
                job.improvement_run_error = None
                job.improvement_halted = False
                job.improvement_halt_reason = None
                agent.memory.regeneration_count += 1
                agent.save_memory()
                job.regeneration_count = agent.memory.regeneration_count
                if agent.memory_file_path:
                    job.improvement_memory_path = str(agent.memory_file_path)
                    try:
                        mp = Path(job.improvement_memory_path)
                        md: Dict[str, Any] = {}
                        if mp.exists():
                            with mp.open("r", encoding="utf-8") as fh:
                                md = json.load(fh)
                        md["improvement_run_succeeded"] = False
                        md["improvement_steps"] = msg
                        md["improved_validation_metrics"] = job.improved_metrics
                        md.pop("improvement_run_error", None)
                        with mp.open("w", encoding="utf-8") as fh:
                            json.dump(md, fh, indent=2)
                    except Exception:
                        pass
            else:
                agent.run_improved_code_generation()
                improved_metrics = agent.run_improved_code_runner()

                # Increment cycle counter and persist
                agent.memory.regeneration_count += 1
                agent.save_memory()

                job.improvement_steps = improvement_steps
                job.improved_metrics = improved_metrics or {}
                job.original_metrics = agent.memory.validation_metrics
                job.regeneration_count = agent.memory.regeneration_count
                if agent.memory_file_path:
                    job.improvement_memory_path = str(agent.memory_file_path)

                # Runner / memory: halt flags, run outcome, parsed metrics
                mem_path_for_halt = (
                    Path(job.improvement_memory_path) if job.improvement_memory_path else None
                )
                if mem_path_for_halt and mem_path_for_halt.exists():
                    try:
                        with mem_path_for_halt.open("r", encoding="utf-8") as _fh:
                            _mem_data = json.load(_fh)
                        job.improvement_run_succeeded = _mem_data.get(
                            "improvement_run_succeeded"
                        )
                        err = _mem_data.get("improvement_run_error")
                        job.improvement_run_error = err if err else None
                        if _mem_data.get("improvement_halted"):
                            job.improvement_halted = True
                            job.improvement_halt_reason = _mem_data.get(
                                "improvement_halt_reason"
                            )
                            # Use the baseline metrics written by the runner so
                            # the frontend can show identical Before/After values.
                            baseline = (
                                _mem_data.get("improved_validation_metrics")
                                or job.original_metrics
                                or {}
                            )
                            job.improved_metrics = baseline
                    except Exception:
                        pass

        _collect_artifacts(job)
        job.status = "improvement_done"

    except Exception as exc:
        job.status = "error"
        job.error = str(exc)
        job.logs += f"\n[ERROR] {exc}"


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="IntelliModel Workflow API",
    description=(
        "HTTP wrapper around the IntelliModel ML pipeline.  "
        "All heavy work runs in background threads; poll GET /api/status/{job_id}."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all origins — localhost-only dev API
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Pydantic request bodies
# ---------------------------------------------------------------------------
class ValidateRequest(BaseModel):
    selected_models: List[str]


class TrainRequest(BaseModel):
    model_name: str


class ImproveRequest(BaseModel):
    model_name: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/api/upload", status_code=201)
async def upload_dataset(
    file: UploadFile = File(...),
    target_column: str = Form(...),
    goal: str = Form(...),
) -> Dict[str, Any]:
    """
    Accept a CSV file upload.

    Form fields
    -----------
    file          : CSV file (.csv only)
    target_column : name of the prediction target column
    goal          : plain-English description of the dataset / prediction goal

    Returns
    -------
    { job_id, filename, target_column, goal, status }
    """
    # ── Input validation ──────────────────────────────────────────────────────
    # 1. Blank / whitespace-only target column
    target_column = target_column.strip()
    if not target_column:
        raise HTTPException(
            status_code=400,
            detail="'target_column' cannot be empty or whitespace.",
        )

    # 2. Blank / too-short dataset context/goal
    goal_stripped = goal.strip()
    if len(goal_stripped) < 10:
        raise HTTPException(
            status_code=400,
            detail=(
                "'goal' (dataset context) is too short — please provide at least "
                "10 characters describing the dataset and prediction objective. "
                "Without sufficient context the LLM may produce poor recommendations."
            ),
        )

    # 3. File extension check — only .csv accepted
    original_name = Path(file.filename or "dataset.csv").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in (".csv",):
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '{suffix}'. "
                "Only CSV files (.csv) are currently supported. "
                "If your data is in Excel (.xlsx/.xls), JSON, or Parquet format, "
                "please convert it to CSV first."
            ),
        )

    # 4. Read file contents and validate it is a parseable CSV
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        import io
        import pandas as pd

        # Try UTF-8 first, fall back to latin-1 for non-UTF-8 files
        try:
            df_peek = pd.read_csv(io.BytesIO(contents), nrows=5, encoding="utf-8")
        except UnicodeDecodeError:
            try:
                df_peek = pd.read_csv(io.BytesIO(contents), nrows=5, encoding="latin-1")
            except Exception as enc_exc:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Could not decode the CSV file: {enc_exc}. "
                        "Please ensure the file is saved in UTF-8 or latin-1 encoding."
                    ),
                )
    except HTTPException:
        raise
    except Exception as parse_exc:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File does not appear to be a valid CSV: {parse_exc}. "
                "Please check the file format and try again."
            ),
        )

    # 5. Minimum column count — need at least 2 columns (1 feature + 1 target)
    if df_peek.shape[1] < 2:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Dataset has only {df_peek.shape[1]} column(s). "
                "At least 2 columns (one feature and one target) are required."
            ),
        )

    # 6. Target column existence check (using the peek header)
    if target_column not in df_peek.columns:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Target column '{target_column}' not found in the uploaded CSV. "
                f"Available columns: {list(df_peek.columns)}"
            ),
        )

    # ── Persist & register job ────────────────────────────────────────────────
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)

    job_id = str(uuid.uuid4())
    output_dir = _job_output_dir(job_id)

    # Save with the original filename inside the per-job directory so the
    # preprocessing agent derives clean output names (e.g., Housing.json,
    # Housing_preprocessing_code.py) instead of job-prefixed ones.
    csv_path = output_dir / original_name
    csv_path.write_bytes(contents)

    job = JobState(
        job_id=job_id,
        csv_path=csv_path,
        target_column=target_column,
        goal=goal_stripped,
        output_dir=output_dir,
    )
    with _jobs_lock:
        _jobs[job_id] = job

    return {
        "job_id": job_id,
        "filename": original_name,
        "target_column": target_column,
        "goal": goal_stripped,
        "status": "uploaded",
    }


@app.post("/api/preprocess/{job_id}")
async def start_preprocessing(job_id: str) -> Dict[str, Any]:
    """
    Trigger the Preprocessing Agent + LLM model recommendations for *job_id*.

    The work runs in a background thread.
    Poll GET /api/status/{job_id} until status == 'preprocessing_done' (or 'error').
    """
    job = _get_job(job_id)
    if job.status not in ("uploaded", "error"):
        raise HTTPException(
            status_code=409,
            detail=f"Job is already in state '{job.status}'. "
                   "Only 'uploaded' or 'error' jobs can be (re)started.",
        )
    job.status = "preprocessing"
    job.logs = ""
    job.error = None
    threading.Thread(
        target=_task_preprocess_and_recommend, args=(job,), daemon=True
    ).start()
    return {"status": "started", "job_id": job_id}


@app.post("/api/recommend/{job_id}")
async def re_recommend_models(job_id: str) -> Dict[str, Any]:
    """
    Re-generate model recommendations, excluding all previously validated models.

    Requires status == 'validation_done' or 'preprocessing_done'.
    Poll GET /api/status/{job_id} until status returns to 'preprocessing_done'.
    """
    job = _get_job(job_id)
    if job.status not in ("preprocessing_done", "validation_done", "error"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot re-recommend in state '{job.status}'.",
        )
    job.logs = ""
    job.error = None
    threading.Thread(
        target=_task_recommend, args=(job,), daemon=True
    ).start()
    return {"status": "started", "job_id": job_id}


@app.get("/api/status/{job_id}")
def get_status(job_id: str) -> Dict[str, Any]:
    """
    Poll for current job status, live logs, and any completed results.

    Response fields
    ---------------
    status               : current pipeline stage
    logs                 : captured stdout/stderr (last 10 000 chars)
    error                : error message if status == 'error'
    recommendations_text : raw LLM recommendation text (after preprocessing_done)
    recommended_models   : parsed list of model names
    preprocessing_plan   : preprocessing steps dict
    task_type            : 'regression' | 'classification' | 'forecasting'
    validation_metrics   : per-model { metrics: {MAE/R2 or Accuracy/F1/…}, code_path }
    training_code_path   : absolute path to generated *_full.py
    improvement_steps    : LLM-generated improvement steps text
    improved_metrics     : metrics after improvement (before vs after shown on frontend)
    original_metrics     : metrics before improvement
    """
    import time
    job = _get_job(job_id)

    # ── Stale-job guard ───────────────────────────────────────────────────────
    # If a background thread has been running for more than 30 minutes on a
    # single stage, surface a timeout error so the frontend stops spinning.
    STAGE_TIMEOUT_SECONDS = 1800  # 30 min
    in_progress_statuses = {"preprocessing", "recommending", "validating", "training", "improving"}
    now = time.time()
    if job.status in in_progress_statuses:
        stage_key = f"_stage_start_{job.status}"
        stage_start = getattr(job, stage_key, None)
        if stage_start is None:
            object.__setattr__(job, stage_key, now)
        elif now - stage_start > STAGE_TIMEOUT_SECONDS:
            job.status = "error"
            job.error = (
                f"Stage timed out after {STAGE_TIMEOUT_SECONDS // 60} minutes. "
                "The LLM or a subprocess may be unresponsive. "
                "Check that the Ollama server is running and try again."
            )

    return {
        "job_id": job_id,
        "status": job.status,
        "logs": job.logs[-10_000:],
        "error": job.error,
        "recommendations_text": job.recommendations_text,
        "recommended_models": job.recommended_models,
        "preprocessing_plan": job.preprocessing_plan,
        "task_type": job.task_type,
        "validation_metrics": job.validation_metrics,
        "training_code_path": job.training_code_path,
        "improvement_steps": job.improvement_steps,
        "improved_metrics": job.improved_metrics,
        "original_metrics": job.original_metrics,
        "regeneration_count": job.regeneration_count,
        "improvement_halted": job.improvement_halted,
        "improvement_halt_reason": job.improvement_halt_reason,
        "improvement_run_succeeded": job.improvement_run_succeeded,
        "improvement_run_error": job.improvement_run_error,
    }


@app.get("/api/stream/{job_id}")
async def stream_logs(job_id: str):
    """
    Server-Sent Events endpoint — streams live log lines to the frontend
    without the client needing to poll every second.  The stream closes
    automatically when the job reaches a terminal state.

    Usage (JavaScript):
        const es = new EventSource(`/api/stream/${jobId}`);
        es.onmessage = (e) => {
            const data = JSON.parse(e.data);
            appendLogs(data.chunk);
            if (data.done) es.close();
        };
    """
    from fastapi.responses import StreamingResponse
    import asyncio

    job = _get_job(job_id)
    terminal = {
        "preprocessing_done", "validation_done",
        "training_done", "improvement_done", "error",
    }

    async def _generate():
        sent_chars = 0
        while True:
            current_logs = job.logs
            if len(current_logs) > sent_chars:
                new_text = current_logs[sent_chars:]
                sent_chars = len(current_logs)
                payload = json.dumps({
                    "status": job.status,
                    "chunk": new_text,
                    "error": job.error,
                })
                yield f"data: {payload}\n\n"

            if job.status in terminal:
                await asyncio.sleep(0.1)
                # Flush any final bytes written after we last checked
                final_logs = job.logs
                if len(final_logs) > sent_chars:
                    new_text = final_logs[sent_chars:]
                    payload = json.dumps({
                        "status": job.status,
                        "chunk": new_text,
                        "error": job.error,
                    })
                    yield f"data: {payload}\n\n"
                yield f"data: {json.dumps({'status': job.status, 'done': True, 'error': job.error})}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/validate/{job_id}")
async def validate_models(
    job_id: str, request: ValidateRequest
) -> Dict[str, Any]:
    """
    Generate and run validation test scripts for *selected_models*.

    Requires status == 'preprocessing_done'.
    Poll GET /api/status/{job_id} until status == 'validation_done' (or 'error').
    """
    job = _get_job(job_id)
    if job.status not in ("preprocessing_done", "validation_done", "error"):
        raise HTTPException(
            status_code=409,
            detail=f"Expected 'preprocessing_done'. Current status: '{job.status}'.",
        )
    if not request.selected_models:
        raise HTTPException(status_code=400, detail="selected_models cannot be empty.")

    job.status = "validating"
    job.error = None
    threading.Thread(
        target=_task_validate, args=(job, request.selected_models), daemon=True
    ).start()
    return {
        "status": "started",
        "job_id": job_id,
        "selected_models": request.selected_models,
    }


@app.post("/api/train/{job_id}")
async def train_model(job_id: str, request: TrainRequest) -> Dict[str, Any]:
    """
    Generate full training code for *model_name* and execute it (produces a .pkl).

    Requires status == 'validation_done'.
    Poll GET /api/status/{job_id} until status == 'training_done' (or 'error').
    """
    job = _get_job(job_id)
    if job.status not in ("validation_done", "training_done", "error"):
        raise HTTPException(
            status_code=409,
            detail=f"Expected 'validation_done'. Current status: '{job.status}'.",
        )

    job.status = "training"
    job.error = None
    threading.Thread(
        target=_task_train, args=(job, request.model_name), daemon=True
    ).start()
    return {"status": "started", "job_id": job_id, "model_name": request.model_name}


@app.post("/api/improve/{job_id}")
async def improve_model(job_id: str, request: ImproveRequest) -> Dict[str, Any]:
    """
    Run the Improvement Agent for *model_name*.

    Requires at least validation_done (training is optional but recommended).
    Poll GET /api/status/{job_id} until status == 'improvement_done' (or 'error').
    """
    job = _get_job(job_id)
    if job.status not in (
        "validation_done", "training_done", "improvement_done", "error"
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Expected at least 'validation_done'. Current: '{job.status}'.",
        )

    job.status = "improving"
    job.error = None
    threading.Thread(
        target=_task_improve, args=(job, request.model_name), daemon=True
    ).start()
    return {"status": "started", "job_id": job_id, "model_name": request.model_name}


@app.post("/api/confirm_improvement/{job_id}")
async def confirm_improvement(job_id: str) -> Dict[str, Any]:
    """
    Persist the improved code path into orchestrator_memory.json so that the
    subsequent /api/train call generates full training code from the improved
    validation logic.

    Steps:
    1. Read improvement_memory.json → improved_validation_code_path or validation_code_path
    2. Read orchestrator_memory.json → patch validation_metrics[model_name]["code_path"]
    3. Write orchestrator_memory.json back
    4. Update in-memory job.validation_metrics similarly
    5. Reset job.status from 'improvement_done' → 'validation_done'

    Requires status == 'improvement_done'.
    """
    job = _get_job(job_id)
    if job.status != "improvement_done":
        raise HTTPException(
            status_code=409,
            detail=f"Expected 'improvement_done'. Current status: '{job.status}'.",
        )

    # Prefer the per-dataset memory file written by _task_improve; fall back to
    # the flat legacy path for backward compatibility.
    improvement_memory_path: Path
    if job.improvement_memory_path:
        improvement_memory_path = Path(job.improvement_memory_path)
    else:
        improvement_memory_path = IMPROVEMENT_DIR / "improvement_memory.json"

    orchestrator_memory_path = LLM_ORCHESTRATOR_DIR / "orchestrator_memory.json"

    if not improvement_memory_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"improvement_memory.json not found at {improvement_memory_path}. Cannot confirm improvement.",
        )

    try:
        with improvement_memory_path.open("r", encoding="utf-8") as fh:
            imp_mem = json.load(fh)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to read improvement_memory.json: {exc}"
        )

    resolved_code_path, used_improved = _improvement_memory_resolved_validation_code_path(
        imp_mem
    )
    model_name: Optional[str] = imp_mem.get("model_name")
    proceed_to_deployment = bool(imp_mem.get("proceed_to_deployment"))
    user_satisfied = bool(imp_mem.get("user_satisfied"))
    improvement_steps_text = str(imp_mem.get("improvement_steps") or "")
    steps_lower = improvement_steps_text.lower()
    steps_indicate_no_code_needed = (
        "no improvement needed" in steps_lower or "already excellent" in steps_lower
    )

    missing_path = not resolved_code_path
    # Missing both paths is expected when metrics were already good enough and code gen was skipped.
    skip_missing_path_error = (
        proceed_to_deployment
        or user_satisfied
        or steps_indicate_no_code_needed
    )

    if missing_path and skip_missing_path_error:
        job.status = "validation_done"
        return {
            "status": "confirmed",
            "job_id": job_id,
            "note": "No improved code path required (metrics already excellent or improvement skipped).",
        }

    if missing_path:
        raise HTTPException(
            status_code=500,
            detail=(
                "Neither improved_validation_code_path nor validation_code_path "
                "found in improvement_memory.json."
            ),
        )
    if not model_name:
        raise HTTPException(
            status_code=500,
            detail="model_name not found in improvement_memory.json.",
        )

    _log_full_training_validation_code_path_source(used_improved, resolved_code_path)

    # Patch orchestrator_memory.json on disk
    if orchestrator_memory_path.exists():
        try:
            with orchestrator_memory_path.open("r", encoding="utf-8") as fh:
                orch_mem = json.load(fh)

            vm: dict = orch_mem.get("validation_metrics", {})
            # Fuzzy-match model name (same logic as _task_improve)
            def _norm(n: str) -> str:
                return n.lower().replace(" ", "").replace("_", "").replace("-", "")

            matched = next(
                (k for k in vm if _norm(k) == _norm(model_name)), None
            )
            if matched:
                if isinstance(vm[matched], dict):
                    vm[matched]["code_path"] = resolved_code_path
                orch_mem["validation_metrics"] = vm
                with orchestrator_memory_path.open("w", encoding="utf-8") as fh:
                    json.dump(orch_mem, fh, indent=2)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to patch orchestrator_memory.json: {exc}",
            )

    # Mirror the patch into the in-memory job state
    if job.validation_metrics:
        def _norm2(n: str) -> str:
            return n.lower().replace(" ", "").replace("_", "").replace("-", "")

        for k in list(job.validation_metrics.keys()):
            if _norm2(k) == _norm2(model_name):
                entry = job.validation_metrics[k]
                if isinstance(entry, dict):
                    entry["code_path"] = resolved_code_path
                break

    job.status = "validation_done"
    return {"status": "confirmed", "job_id": job_id}


@app.post("/api/discard_improvement/{job_id}")
async def discard_improvement(job_id: str) -> Dict[str, Any]:
    """
    Discard the current improvement run and reset job status to 'validation_done'
    so the user can choose a different model or re-run validation.

    Requires status == 'improvement_done'.
    """
    job = _get_job(job_id)
    if job.status != "improvement_done":
        raise HTTPException(
            status_code=409,
            detail=f"Expected 'improvement_done'. Current status: '{job.status}'.",
        )
    job.status = "validation_done"
    return {"status": "discarded", "job_id": job_id}


@app.get("/api/deployment/{job_id}")
def get_deployment_info(job_id: str) -> Dict[str, Any]:
    """
    Return the deployment server URL and an example /predict request payload.

    The prediction server (backend/deployment/main.py) must be running separately:
        cd backend/deployment && uvicorn main:app --port 8000

    Requires status == 'training_done' or 'improvement_done'.
    """
    job = _get_job(job_id)
    if job.status not in ("training_done", "improvement_done"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Model has not been trained yet (status: '{job.status}'). "
                "Complete training first."
            ),
        )

    master_memory_path = BACKEND_ROOT / "master_memory.json"
    try:
        with master_memory_path.open("r", encoding="utf-8") as fh:
            mm = json.load(fh)

        prep = mm.get("preprocessing", {})

        # ── Load the ORIGINAL (pre-preprocessing) report ──
        original_report: Optional[Dict[str, Any]] = None
        orig_report_path_str = (
            prep.get("report_path")
            or mm.get("file_history", {}).get("preprocessing_report")
            or mm.get("file_history", {}).get("report")
        )
        if orig_report_path_str:
            orig_rp = Path(orig_report_path_str)
            if not orig_rp.is_absolute():
                orig_rp = (BACKEND_ROOT / orig_rp).resolve()
            if orig_rp.exists():
                with orig_rp.open("r", encoding="utf-8") as fh:
                    original_report = json.load(fh)
        if original_report is None:
            original_report = prep.get("report")

        # ── Also load the processed report (still needed for /predict direct) ──
        report_path_str = prep.get("processed_output_report_path")
        if not report_path_str:
            raise ValueError("processed_output_report_path not found in master_memory.json")

        report_path = Path(report_path_str)
        if not report_path.is_absolute():
            report_path = (BACKEND_ROOT / report_path).resolve()

        with report_path.open("r", encoding="utf-8") as fh:
            report = json.load(fh)

        all_columns: List[str] = list(report.get("columns", {}).keys())
        target_column: Optional[str] = (
            report.get("dataset_overview", {}).get("target_column")
            or mm.get("target_column")
        )
        feature_names = [c for c in all_columns if c != target_column]

        

        def _is_datetime_col(fname: str, col: Dict[str, Any]) -> bool:
            """
            Conservative datetime detection to avoid false positives like 'sentiment'.

            Priority:
            1) Trust explicit report metadata/dtype
            2) Use strict name-token matching (not substring matching)
            """
            dtype = str(col.get("dtype", "")).lower()

            # 1) Strong evidence from report/dtype
            if "datetime" in dtype:
                return True
            if "min_date" in col or "max_date" in col:
                return True

            # 2) Name-based fallback (strict token matching)
            # Split by non-alnum and camelCase boundaries
            # Examples:
            #   "event_time" -> ["event", "time"]
            #   "tradeTimestamp" -> ["trade", "timestamp"]
            #   "sentiment" -> ["sentiment"]  (does NOT match)
            name = (fname or "").strip()
            if not name:
                return False

            # Insert spaces before camelCase capitals, then split
            spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
            tokens = [t.lower() for t in re.split(r"[^A-Za-z0-9]+|\s+", spaced) if t]

            datetime_tokens = {
                "date", "dates",
                "datetime", "timestamp", "timestamps",
                "time", "times",
                "day", "month", "year", "week",
            }

            # Exact token match only
            if any(t in datetime_tokens for t in tokens):
                return True

            # Optional: common abbreviations as whole tokens only
            # (safe: token-based, so "sentiment" still won't match)
            if any(t in {"dt", "ts"} for t in tokens):
                return True

            return False

        def _build_col_stat(fname: str, col: Dict[str, Any]) -> Dict[str, Any]:
            """Convert a report column entry into a frontend-friendly stat dict."""
            stat: Dict[str, Any] = {}
            dtype = col.get("dtype", "")
            stat["dtype"] = dtype

            if _is_datetime_col(fname, col):
                stat["field_type"] = "datetime"
                if col.get("min_date"):
                    stat["min_date"] = str(col["min_date"])
                if col.get("max_date"):
                    stat["max_date"] = str(col["max_date"])
                # Never render datetime as a categorical dropdown
                return stat

            mean_val = col.get("mean")
            if mean_val is not None:
                stat["mean"] = round(mean_val, 4)
            if col.get("std") is not None:
                stat["std"] = round(col["std"], 4)
            if col.get("min") is not None:
                stat["min"] = col["min"]
            if col.get("max") is not None:
                stat["max"] = col["max"]
            if "top_categories" in col:
                stat["categories"] = list(col["top_categories"].keys())
            if (
                dtype in ("int64", "int32", "float64", "float32")
                and mean_val is not None
                and 0.0 <= mean_val <= 1.0
                and col.get("std", 1.0) <= 0.5
            ):
                stat["binary"] = True
            return stat

        # Build per-feature stats from the ORIGINAL report so the UI shows
        # human-readable column names and value hints
        raw_feature_names: List[str] = []
        raw_feature_stats: Dict[str, Any] = {}
        if original_report and "columns" in original_report:
            orig_cols = original_report["columns"]
            raw_feature_names = [c for c in orig_cols if c != target_column]
            for fname in raw_feature_names:
                raw_feature_stats[fname] = _build_col_stat(fname, orig_cols.get(fname, {}))

        # Fallback: if original report not available, use processed report stats
        if not raw_feature_names:
            raw_feature_names = feature_names
            raw_cols_dict: Dict[str, Any] = report.get("columns", {})
            for fname in feature_names:
                raw_feature_stats[fname] = _build_col_stat(fname, raw_cols_dict.get(fname, {}))

    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Could not load feature names: {exc}"
        )

    example_payload = {name: "" for name in raw_feature_names}

    return {
        "predict_url": "http://localhost:8000/predict_raw",
        "features_url": "http://localhost:8000/raw_features",
        "health_url": "http://localhost:8000/health",
        "example_predict_payload": example_payload,
        "feature_names": raw_feature_names,
        "target_column": target_column,
        "feature_stats": raw_feature_stats,
        "start_deployment_server": (
            "cd backend/deployment && uvicorn main:app --host 0.0.0.0 --port 8000"
        ),
    }


@app.get("/api/health")
def api_health() -> Dict[str, Any]:
    """Workflow API health check."""
    with _jobs_lock:
        active = len(_jobs)
    return {"status": "ok", "active_jobs": active}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # reload=False is intentional — see the module-level docstring for why
    # running with --reload breaks the pipeline (in-memory job state is lost).
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=9000,
        reload=False,
    )
