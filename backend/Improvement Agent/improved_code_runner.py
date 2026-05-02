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


IMPROVEMENT_MEMORY_PATH = _find_improvement_memory()
MAX_ITERATIONS = 3


# ============================================================
# STDOUT METRIC PARSING  (primary capture method)
# ============================================================

_NUM = r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)"

_METRIC_PATTERNS = {
    "MAE":       rf"(?<!\w)MAE\s*[:\s=]+{_NUM}",
    "MSE":       rf"(?<!\w)MSE\s*[:\s=]+{_NUM}",
    "RMSE":      rf"(?<!\w)RMSE\s*[:\s=]+{_NUM}",
    "R2":        rf"R2\s*[:\s=]+{_NUM}",
    "Accuracy":  rf"Accuracy\s*[:\s=]+{_NUM}",
    "Precision": rf"Precision\s*[:\s=]+{_NUM}",
    "Recall":    rf"Recall\s*[:\s=]+{_NUM}",
    "F1":        rf"(?<!\w)F1\s*[:\s=]+{_NUM}",
    "ROC_AUC":   rf"ROC_AUC\s*[:\s=]+{_NUM}",
    "MAPE":      rf"MAPE\s*[:\s=]+{_NUM}",
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

def main():
    print("=== Improved Code Runner ===")

    if not IMPROVEMENT_MEMORY_PATH.exists():
        print(f"[ERROR] improvement_memory.json not found at: {IMPROVEMENT_MEMORY_PATH}")
        return

    with IMPROVEMENT_MEMORY_PATH.open("r", encoding="utf-8") as f:
        improv_mem = json.load(f)

    dataset_context = improv_mem.get("dataset_context", "")
    improvement_steps_path_str = improv_mem.get("improvement_steps_path")
    validation_code_path_str = (
        improv_mem.get("improved_validation_code_path")
        or improv_mem.get("validation_code_path")
    )
    baseline_metrics = improv_mem.get("validation_metrics") or {}
    dataset_report_path_str = improv_mem.get("dataset_report_path")
    task_type = improv_mem.get("task_type", "regression")
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
                    _mem_path = IMPROVEMENT_MEMORY_PATH
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
    improved_running_dir = IMPROVEMENT_MEMORY_PATH.parent / "Improved_code_running"
    improved_running_dir.mkdir(parents=True, exist_ok=True)

    safe_name = model_name.lower().replace(" ", "_").replace("-", "_")
    output_path = improved_running_dir / f"{safe_name}_improved_running.py"

    # Copy improved code to running dir
    output_path.write_text(validation_code_path.read_text(encoding="utf-8"), encoding="utf-8")

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

        # Parse metrics from stdout
        new_metrics = parse_metrics_from_stdout(stdout, task_type)

        if not new_metrics:
            print("[WARN] Could not parse metrics from stdout on this run.")
            # Try to fix the metric printing
            fix_error = (
                "The script ran but did not print metrics in the expected format.\n"
                f"Expected metrics for {task_type}: {_TASK_METRIC_KEYS.get(task_type, [])}\n"
                "Each metric must be printed as: print(f'METRIC_NAME: {value}')\n"
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

    # Always write back to memory — even empty metrics — so the frontend
    # knows the run completed and can show a clear error rather than dashes
    try:
        mem_path = IMPROVEMENT_MEMORY_PATH
        if mem_path.exists():
            with mem_path.open("r", encoding="utf-8") as f:
                mem_data = json.load(f)
            mem_data["improved_validation_metrics"] = best_metrics  # may be {}
            mem_data["improved_validation_code_path"] = str(output_path.resolve())
            mem_data["improvement_run_succeeded"] = succeeded
            if not best_metrics:
                mem_data["improvement_run_error"] = (
                    "Metrics could not be captured from the improved code output. "
                    "Check the generated script for missing print statements."
                )
            else:
                mem_data.pop("improvement_run_error", None)
            with mem_path.open("w", encoding="utf-8") as f:
                json.dump(mem_data, f, indent=2)
            if best_metrics:
                print(f"[INFO] Updated improvement_memory.json with final metrics: {best_metrics}")
            else:
                print("[WARN] Wrote empty metrics to improvement_memory.json — check generated code output above.")
        else:
            print(f"[WARN] improvement_memory.json not found at {mem_path} — metrics not saved.")
    except Exception as exc:
        print(f"[WARN] Could not update improvement_memory.json: {exc}")


if __name__ == "__main__":
    main()
