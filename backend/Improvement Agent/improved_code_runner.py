"""
Improved Code Runner

Reads improvement_memory.json to obtain:
  - The already-generated improved validation code path
  - baseline validation metrics for comparison
  - dataset context for LLM self-repair prompts
  - task_type

Then:
  1. Runs the code in a subprocess
  2. Parses metrics from stdout using regex (reliable, no eval injection)
  3. Compares resulting metrics to baseline and prints a clear before/after table
  4. If metrics regressed or the script errored, asks the LLM to repair
     (up to MAX_ITERATIONS = 3 total attempts)
  5. Writes the best passing code back and updates improvement_memory.json

NOTE: This file does NOT generate the improved code itself.
      Code generation is handled exclusively by improved_code_gen.py.
"""

import json
import re
import sys
import subprocess
import traceback
from pathlib import Path
from typing import Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from llm_config import DEFAULT_LLM_MODEL, DEFAULT_LLM_ENDPOINT, create_chat_llm

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from improvement_steps_generator import (
    check_improvement_feasibility,
    compare_metrics,
    format_feasibility_message,
    MIN_IMPROVEMENT_THRESHOLD,
)

MODEL = DEFAULT_LLM_MODEL
ENDPOINT = DEFAULT_LLM_ENDPOINT

def _find_improvement_memory() -> Path:
    flat = current_dir / "improvement_memory.json"
    if flat.exists():
        return flat
    for sub in sorted(current_dir.iterdir()):
        if sub.is_dir():
            candidate = sub / "improvement_memory.json"
            if candidate.exists():
                return candidate
    return flat


def resolve_improvement_memory_path(explicit: Optional[Path]) -> Path:
    """Prefer CLI --memory path; otherwise first improvement_memory.json under agent dir."""
    if explicit is not None:
        p = explicit.expanduser().resolve()
        if p.exists():
            return p
        print(f"[WARN] --memory path does not exist: {p}, falling back to auto-discovery.")
    return _find_improvement_memory()


MAX_ITERATIONS = 3

# Canonical metric names → regex alternation for stdout (beyond _METRIC_PATTERNS)
_R2_ALIASES = r"(?:R2|R\^2|R²|r2)"


# ============================================================
# STDOUT METRIC PARSING  (primary capture method)
# ============================================================

_NUM = r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)"

_METRIC_PATTERNS = {
    "MAE":       rf"(?<!\w)MAE\s*[:\s=]+{_NUM}",
    "MSE":       rf"(?<!\w)MSE\s*[:\s=]+{_NUM}",
    "RMSE":      rf"(?<!\w)RMSE\s*[:\s=]+{_NUM}",
    "R2":        rf"(?<!\w){_R2_ALIASES}\s*[:\s=]+{_NUM}",
    "Accuracy":  rf"(?<!\w)Accuracy\s*[:\s=]+{_NUM}",
    "Precision": rf"(?<!\w)Precision\s*[:\s=]+{_NUM}",
    "Recall":    rf"(?<!\w)Recall\s*[:\s=]+{_NUM}",
    "F1":        rf"(?<!\w)F1\s*[:\s=]+{_NUM}",
    "ROC_AUC":   rf"(?<!\w)ROC[_\s-]?AUC\s*[:\s=]+{_NUM}",
    "MAPE":      rf"(?<!\w)MAPE\s*[:\s=]+{_NUM}",
}

_TASK_METRIC_KEYS = {
    "regression":     ["MAE", "MSE", "RMSE", "R2"],
    "classification": ["Accuracy", "Precision", "Recall", "F1", "ROC_AUC"],
    "forecasting":    ["MAE", "RMSE", "MAPE"],
}


def parse_metrics_from_stdout(stdout: str, task_type: str = "regression") -> dict:
    """Parse metrics from printed stdout — works with both 'KEY: value' and 'KEY = value'."""
    keys = _TASK_METRIC_KEYS.get(task_type, list(_METRIC_PATTERNS.keys()))
    metrics: dict = {}
    for key in keys:
        pattern = _METRIC_PATTERNS.get(key)
        if not pattern:
            continue
        # Find the LAST occurrence (after train metrics, before test metrics)
        matches = list(re.finditer(pattern, stdout, re.IGNORECASE))
        if matches:
            try:
                metrics[key] = float(matches[-1].group(1))
            except ValueError:
                pass
    return metrics


_INTELLIMODEL_JSON_TAG = "INTELLIMODEL_METRICS_JSON"

# Lowercased / common aliases → canonical keys used by orchestrator + frontend
_METRIC_KEY_ALIASES: dict[str, str] = {
    "mae": "MAE",
    "mse": "MSE",
    "rmse": "RMSE",
    "r2": "R2",
    "r²": "R2",
    "r^2": "R2",
    "accuracy": "Accuracy",
    "precision": "Precision",
    "recall": "Recall",
    "f1": "F1",
    "f1_score": "F1",
    "roc_auc": "ROC_AUC",
    "rocauc": "ROC_AUC",
    "auc": "ROC_AUC",
    "mape": "MAPE",
}


def _slug_metric_key(key: str) -> str:
    return re.sub(r"[\s\-]+", "_", key.strip().lower())


def normalize_metrics_keys(
    metrics: dict,
    baseline: dict | None = None,
) -> dict[str, float]:
    """Map aliases / odd casing to canonical names so UI keys align with baseline."""
    out: dict[str, float] = {}
    baseline = baseline or {}

    for raw_k, raw_v in metrics.items():
        if raw_v is None:
            continue
        k = str(raw_k).strip()
        slug = _slug_metric_key(k)
        canon = _METRIC_KEY_ALIASES.get(slug)
        if canon is None:
            for bk in baseline:
                if _slug_metric_key(bk) == slug or bk.lower() == k.lower():
                    canon = bk
                    break
            if canon is None and k in _METRIC_PATTERNS:
                canon = k
            elif canon is None:
                for std in _METRIC_PATTERNS:
                    if std.lower() == k.lower():
                        canon = std
                        break
        if canon is None:
            continue
        try:
            out[canon] = float(raw_v)
        except (TypeError, ValueError):
            pass
    return out


def parse_metrics_json_line(stdout: str) -> dict:
    """
    Fallback: one line containing INTELLIMODEL_METRICS_JSON followed by a JSON object.
    Example: INTELLIMODEL_METRICS_JSON {"MAE": 1.2, "R2": 0.45}
    """
    for line in reversed(stdout.splitlines()):
        s = line.strip()
        if _INTELLIMODEL_JSON_TAG not in s:
            continue
        idx = s.find(_INTELLIMODEL_JSON_TAG)
        payload = s[idx + len(_INTELLIMODEL_JSON_TAG) :].strip().lstrip("=: \t")
        if not payload:
            continue
        try:
            d = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(d, dict):
            continue
        parsed: dict[str, float] = {}
        for kk, vv in d.items():
            try:
                parsed[str(kk)] = float(vv)
            except (TypeError, ValueError):
                pass
        if parsed:
            return parsed
    return {}


def collect_parsed_metrics(
    stdout: str,
    task_type: str,
    baseline: dict,
) -> dict[str, float]:
    """Regex stdout parse, then JSON-line fallback; keys aligned to baseline naming."""
    merged = dict(parse_metrics_from_stdout(stdout, task_type))
    for k, v in parse_metrics_json_line(stdout).items():
        merged.setdefault(k, v)
    return normalize_metrics_keys(merged, baseline)


# ============================================================
# BEFORE / AFTER DISPLAY
# ============================================================

def display_metrics_comparison(
    model_name: str,
    baseline: dict,
    improved: dict,
    task_type: str,
    improvement_steps: str,
) -> None:
    """Print a clear side-by-side before/after metrics table with change highlights."""
    keys = _TASK_METRIC_KEYS.get(task_type, list(_METRIC_PATTERNS.keys()))
    all_keys = list(dict.fromkeys(list(keys) + list(baseline.keys()) + list(improved.keys())))

    _DIRECTION = {
        "MAE": "lower", "MSE": "lower", "RMSE": "lower", "MAPE": "lower",
        "R2": "higher", "Accuracy": "higher", "Precision": "higher",
        "Recall": "higher", "F1": "higher", "ROC_AUC": "higher",
    }

    print("\n" + "=" * 65)
    print(f"  BEFORE vs AFTER IMPROVEMENT — {model_name}")
    print("=" * 65)
    print(f"  {'Metric':<15} {'Before':>12} {'After':>12} {'Change':>12}  {'Status'}")
    print("-" * 65)

    for key in all_keys:
        b = baseline.get(key)
        a = improved.get(key)
        if b is None and a is None:
            continue
        b_str = f"{b:.6f}" if isinstance(b, float) else str(b) if b is not None else "N/A"
        a_str = f"{a:.6f}" if isinstance(a, float) else str(a) if a is not None else "N/A"

        if isinstance(b, float) and isinstance(a, float):
            delta = a - b
            pct = (abs(delta) / abs(b) * 100) if b != 0 else 0.0
            delta_str = f"{delta:+.6f}"
            direction = _DIRECTION.get(key, "higher")
            if direction == "lower":
                status = "✅ better" if delta < -0.0001 else ("❌ worse" if delta > 0.0001 else "— same")
            else:
                status = "✅ better" if delta > 0.0001 else ("❌ worse" if delta < -0.0001 else "— same")
        else:
            delta_str = "N/A"
            status = ""

        print(f"  {key:<15} {b_str:>12} {a_str:>12} {delta_str:>12}  {status}")

    print("=" * 65)

    # Print what changed in the code
    print("\n  CHANGES APPLIED:")
    for i, line in enumerate(improvement_steps.strip().splitlines(), 1):
        stripped = line.strip()
        if stripped:
            print(f"  {stripped}")
        if i >= 15:
            print("  ...")
            break
    print()


# ============================================================
# LLM SELF-REPAIR
# ============================================================

def clean_code_block(text: str) -> str:
    fenced = re.findall(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        return fenced[-1].strip()
    return text.strip()


def generate_fixed_code(
    original_code: str,
    error_text: str,
    improvement_steps: str,
    dataset_context: str,
    task_type: str,
) -> str:
    """Ask the LLM to repair broken or regressing improved code."""
    from improvement_steps_generator import _TASK_METRIC_KEYS

    metric_keys = _TASK_METRIC_KEYS.get(task_type, ["MAE", "MSE", "RMSE", "R2"])
    metric_print_reminder = "\n".join(
        [f'print(f"{k}: {{{k.lower()}}}")' for k in metric_keys]
    )

    FIX_PROMPT = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an expert Python ML engineer. Fix the provided improved validation "
                "code without changing the model logic or evaluation semantics. "
                "You MUST ensure the fixed code prints metrics in this exact format at the end:\n"
                f"{metric_print_reminder}\n"
                "Additionally, print exactly one line: "
                f'print("INTELLIMODEL_METRICS_JSON " + json.dumps({{...metric names as strings...}})) '
                "using the same numeric values (so metrics can be parsed even if f-strings differ).\n"
                "Return ONLY valid Python code. No explanations.",
            ),
            (
                "user",
                "Improvement steps (maintain intent):\n{steps}\n\n"
                "Dataset context:\n{dataset_context}\n\n"
                "Current code:\n{code}\n\n"
                "Error:\n{error}\n\n"
                "Return only corrected Python code.",
            ),
        ]
    )

    llm = create_chat_llm(model=MODEL, endpoint=ENDPOINT, temperature=0.1)
    chain = FIX_PROMPT | llm | StrOutputParser()

    raw = chain.invoke({
        "steps": improvement_steps,
        "dataset_context": dataset_context,
        "code": original_code,
        "error": error_text,
    })
    return clean_code_block(raw)


# ============================================================
# CODE EXECUTION
# ============================================================

def run_code_subprocess(code_path: Path, cwd: Path, timeout: int = 300):
    """Execute a Python script via subprocess and return (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            [sys.executable, str(code_path)],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "[TIMEOUT] Script exceeded time limit."
    except Exception:
        return False, "", traceback.format_exc()


# ============================================================
# MAIN
# ============================================================

def main(memory_path: Optional[Path] = None) -> None:
    print("=== Improved Code Runner ===")

    mem_path = resolve_improvement_memory_path(memory_path)
    print(f"[INFO] Using improvement memory: {mem_path}")

    if not mem_path.exists():
        print(f"[ERROR] improvement_memory.json not found at: {mem_path}")
        return

    with mem_path.open("r", encoding="utf-8") as f:
        improv_mem = json.load(f)

    dataset_context = improv_mem.get("dataset_context", "")
    improvement_steps_path_str = improv_mem.get("improvement_steps_path")
    validation_code_path_str = (
        improv_mem.get("improved_validation_code_path")
        or improv_mem.get("validation_code_path")
    )
    baseline_metrics = normalize_metrics_keys(
        improv_mem.get("validation_metrics") or {},
        {},
    )
    dataset_report_path_str = improv_mem.get("dataset_report_path")
    task_type = improv_mem.get("task_type") or "regression"
    model_name = improv_mem.get("model_name", "model")

    # Validate required fields
    missing = []
    if not dataset_context:
        missing.append("dataset_context")
    if not improvement_steps_path_str:
        missing.append("improvement_steps_path")
    if not validation_code_path_str:
        missing.append("improved_validation_code_path / validation_code_path")

    if missing:
        print("[ERROR] Missing required fields in improvement_memory.json:")
        for m in missing:
            print(f"  - {m}")
        return

    improvement_steps_path = Path(improvement_steps_path_str)
    validation_code_path = Path(validation_code_path_str)

    if not improvement_steps_path.exists():
        print(f"[ERROR] improvement_steps file not found: {improvement_steps_path}")
        return
    if not validation_code_path.exists():
        print(f"[ERROR] validation code file not found: {validation_code_path}")
        return

    improvement_steps = improvement_steps_path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Feasibility check
    # ------------------------------------------------------------------
    if dataset_report_path_str:
        dp = Path(dataset_report_path_str)
        if dp.exists():
            dataset_report_str = dp.read_text(encoding="utf-8")
            print("\n[INFO] Running improvement feasibility checks...")
            feasibility = check_improvement_feasibility(dataset_report_str, baseline_metrics)
            msg = format_feasibility_message(feasibility)
            if msg:
                print(msg)
            if not feasibility["feasible"]:
                print("\n[INFO] Improvement agent halted. Reasons displayed above.")
                # Write baseline metrics so frontend shows numbers not dashes
                _halt_reason = " | ".join(feasibility.get("reasons", ["Dataset limitations prevent improvement."]))
                try:
                    _mem_path = mem_path
                    if _mem_path.exists():
                        import json as _json
                        with _mem_path.open("r", encoding="utf-8") as _f:
                            _mem = _json.load(_f)
                        _mem["improved_validation_metrics"] = baseline_metrics
                        _mem["improvement_run_succeeded"] = False
                        _mem["improvement_halted"] = True
                        _mem["improvement_halt_reason"] = _halt_reason
                        with _mem_path.open("w", encoding="utf-8") as _f:
                            _json.dump(_mem, _f, indent=2)
                        print("[INFO] Wrote baseline metrics to memory (no improvement attempted).")
                except Exception as _exc:
                    print(f"[WARN] Could not update memory after halt: {_exc}")
                return
    else:
        print("[WARN] Dataset report not available — skipping feasibility checks.")

    # ------------------------------------------------------------------
    # Output directory — use same folder as improvement_memory.json
    # so it is always dataset-scoped
    # ------------------------------------------------------------------
    improved_running_dir = mem_path.parent / "Improved_code_running"
    improved_running_dir.mkdir(parents=True, exist_ok=True)

    safe_name = model_name.lower().replace(" ", "_").replace("-", "_")
    output_path = improved_running_dir / f"{safe_name}_improved_running.py"

    # Copy improved code to running dir
    improved_code_text = validation_code_path.read_text(encoding="utf-8")
    output_path.write_text(improved_code_text, encoding="utf-8")

    # ------------------------------------------------------------------
    # IDENTITY CHECK: abort early if the "improved" code is the same as
    # the original validation code — this means code generation failed
    # silently (wrong memory path, LLM returned nothing, etc.)
    # ------------------------------------------------------------------
    original_code_path_str = improv_mem.get("validation_code_path")
    if original_code_path_str:
        original_path = Path(original_code_path_str)
        if original_path.exists():
            original_text = original_path.read_text(encoding="utf-8")
            if improved_code_text.strip() == original_text.strip():
                error_msg = (
                    "Improved code is identical to the original validation code. "
                    "Code generation did not apply any changes — "
                    "improved_code_gen.py may have used the wrong memory path or failed silently."
                )
                print(f"\n[ERROR] {error_msg}")
                try:
                    with mem_path.open("r", encoding="utf-8") as f:
                        mem_data = json.load(f)
                    mem_data["improved_validation_metrics"] = baseline_metrics or {}
                    mem_data["improvement_run_succeeded"] = False
                    mem_data["improvement_run_error"] = error_msg
                    with mem_path.open("w", encoding="utf-8") as f:
                        json.dump(mem_data, f, indent=2)
                except Exception as exc:
                    print(f"[WARN] Could not write identity-check error to memory: {exc}")
                return
            else:
                print(f"[INFO] Identity check passed — improved code differs from original.")
        else:
            print(f"[WARN] Original validation code not found at {original_path} — skipping identity check.")
    else:
        print("[WARN] validation_code_path missing from memory — skipping identity check.")

    # Debug info: confirm exactly what file is being executed
    print(f"[DEBUG] Executing improved code: {output_path}")
    print(f"[DEBUG] File size: {output_path.stat().st_size} bytes")
    print(f"[DEBUG] First 300 chars:\n{improved_code_text[:300]}\n")

    project_root = Path(__file__).resolve().parents[1]

    # ------------------------------------------------------------------
    # Iteration loop
    # ------------------------------------------------------------------
    best_metrics: dict = {}
    best_code: str = output_path.read_text(encoding="utf-8")
    succeeded = False

    for iteration in range(MAX_ITERATIONS):
        print(f"\n=== Running improved code (Iteration {iteration + 1}/{MAX_ITERATIONS}) ===")

        success, stdout, stderr = run_code_subprocess(output_path, cwd=project_root)

        if stdout:
            print(stdout)
        if stderr and not success:
            print(f"[STDERR]\n{stderr}")

        if not success:
            print(f"[ERROR] Script failed on iteration {iteration + 1}. Sending to LLM for repair...")
            error_detail = f"STDERR:\n{stderr}\nSTDOUT:\n{stdout}"
            fixed = generate_fixed_code(
                original_code=output_path.read_text(encoding="utf-8"),
                error_text=error_detail,
                improvement_steps=improvement_steps,
                dataset_context=dataset_context,
                task_type=task_type,
            )
            output_path.write_text(fixed, encoding="utf-8")
            continue

        # Parse metrics from stdout (regex + JSON fallback + key alignment)
        new_metrics = collect_parsed_metrics(stdout, task_type, baseline_metrics)

        if not new_metrics:
            print("[WARN] Could not parse metrics from stdout on this run.")
            # Try to fix the metric printing
            fix_error = (
                "The script ran but did not print metrics in the expected format.\n"
                f"Expected metrics for {task_type}: {_TASK_METRIC_KEYS.get(task_type, [])}\n"
                "Each metric must be printed as: print(f'METRIC_NAME: {value}')\n"
                "Also print one line: print('INTELLIMODEL_METRICS_JSON ' + json.dumps({...})) "
                "with the same numbers (import json if needed).\n"
                f"Stdout was:\n{stdout[:500]}"
            )
            fixed = generate_fixed_code(
                original_code=output_path.read_text(encoding="utf-8"),
                error_text=fix_error,
                improvement_steps=improvement_steps,
                dataset_context=dataset_context,
                task_type=task_type,
            )
            output_path.write_text(fixed, encoding="utf-8")
            continue

        print(f"\n[INFO] Metrics captured: {new_metrics}")

        # Compare against baseline
        if baseline_metrics:
            comparison = compare_metrics(baseline_metrics, new_metrics, task_type=task_type)
            print("\n" + comparison["summary"])

            if comparison["regressed"]:
                print("\n❌ Metrics regressed — attempting further repair...")
                regression_error = (
                    f"The improved code made metrics WORSE.\n"
                    f"Baseline: {json.dumps(baseline_metrics)}\n"
                    f"Result:   {json.dumps(new_metrics)}\n"
                    "Revise so validation metrics improve without overfitting."
                )
                fixed = generate_fixed_code(
                    original_code=output_path.read_text(encoding="utf-8"),
                    error_text=regression_error,
                    improvement_steps=improvement_steps,
                    dataset_context=dataset_context,
                    task_type=task_type,
                )
                output_path.write_text(fixed, encoding="utf-8")
                continue

            # Improvement or no meaningful change — accept
            best_metrics = new_metrics
            best_code = output_path.read_text(encoding="utf-8")
            succeeded = True
            if comparison["no_change"]:
                print(f"\n— No meaningful change (threshold={MIN_IMPROVEMENT_THRESHOLD*100:.0f}%). Stopping.")
            else:
                print("\n✅ Improvement confirmed.")
            break
        else:
            print("[WARN] No baseline metrics — accepting result as-is.")
            best_metrics = new_metrics
            best_code = output_path.read_text(encoding="utf-8")
            succeeded = True
            break

    if not succeeded:
        print(f"\n⚠️  Reached maximum iterations ({MAX_ITERATIONS}) without confirmed improvement.")
        if baseline_metrics:
            print(
                "❌ Could not improve metrics. Original validation code will be retained.\n"
                "Possible reasons:\n"
                "  • The model may be near its performance ceiling on this dataset.\n"
                "  • Feature-target relationships may be too weak for further gains.\n"
                "  • The dataset may be too small to generalise improvements reliably.\n"
            )
        # Bug 3 fix: fall back to baseline so the frontend never shows dashes
        if not best_metrics and baseline_metrics:
            best_metrics = dict(baseline_metrics)
            print("[INFO] Falling back to baseline metrics for display (no improvement achieved).")

    # ------------------------------------------------------------------
    # Display before/after table
    # ------------------------------------------------------------------
    if best_metrics and baseline_metrics:
        display_metrics_comparison(
            model_name=model_name,
            baseline=baseline_metrics,
            improved=best_metrics,
            task_type=task_type,
            improvement_steps=improvement_steps,
        )

    # ------------------------------------------------------------------
    # Save final code and update memory
    # ------------------------------------------------------------------
    output_path.write_text(best_code, encoding="utf-8")

    # Always write back to memory with real numbers so the frontend
    # shows metrics instead of dashes, even when improvement failed.
    try:
        if mem_path.exists():
            with mem_path.open("r", encoding="utf-8") as f:
                mem_data = json.load(f)
            # Use best_metrics (may be baseline fallback) — never write empty {}
            metrics_to_store = best_metrics if best_metrics else baseline_metrics
            mem_data["improved_validation_metrics"] = metrics_to_store
            mem_data["improved_validation_code_path"] = str(output_path.resolve())
            mem_data["improvement_run_succeeded"] = succeeded
            if not succeeded:
                mem_data["improvement_run_error"] = (
                    "Metrics could not be improved within the allowed iterations. "
                    "Baseline metrics are shown for reference."
                ) if not best_metrics else None
                if mem_data["improvement_run_error"] is None:
                    mem_data.pop("improvement_run_error", None)
            else:
                mem_data.pop("improvement_run_error", None)
            with mem_path.open("w", encoding="utf-8") as f:
                json.dump(mem_data, f, indent=2)
            print(f"[INFO] Updated improvement_memory.json with metrics: {metrics_to_store}")
        else:
            print(f"[WARN] improvement_memory.json not found at {mem_path} — metrics not saved.")
    except Exception as exc:
        print(f"[WARN] Could not update improvement_memory.json: {exc}")


if __name__ == "__main__":
    import argparse

    _parser = argparse.ArgumentParser(description="Run improved validation code and update memory.")
    _parser.add_argument(
        "--memory",
        type=str,
        default=None,
        help="Absolute path to improvement_memory.json for this job (required when multiple datasets exist).",
    )
    _args = _parser.parse_args()
    _explicit = Path(_args.memory).resolve() if _args.memory else None
    main(memory_path=_explicit)
