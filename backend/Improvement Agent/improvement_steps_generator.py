import os
import json
import sys
from pathlib import Path
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from llm_config import DEFAULT_LLM_MODEL, DEFAULT_LLM_ENDPOINT, create_chat_llm

MEMORY_FILE = BASE_DIR / "master_memory.json"
DEFAULT_MODEL = DEFAULT_LLM_MODEL
DEFAULT_ENDPOINT = DEFAULT_LLM_ENDPOINT

MIN_IMPROVEMENT_THRESHOLD = 0.01  # 1%
MIN_IMPROVEMENT_THRESHOLD = 0.01  # 1% relative improvement required

# ============================================================
# METRIC DEFINITIONS PER TASK TYPE
# ============================================================

# For each metric: (direction, "higher"|"lower")
# For each metric: direction "higher"|"lower"
_METRIC_DIRECTION = {
    # Regression
    "MAE":      "lower",
    "MSE":      "lower",
    "RMSE":     "lower",
    "R2":       "higher",
    "MAE":       "lower",
    "MSE":       "lower",
    "RMSE":      "lower",
    "R2":        "higher",
    # Classification
    "Accuracy": "higher",
    "Precision":"higher",
    "Recall":   "higher",
    "F1":       "higher",
    "ROC_AUC":  "higher",
    "Accuracy":  "higher",
    "Precision": "higher",
    "Recall":    "higher",
    "F1":        "higher",
    "ROC_AUC":   "higher",
    # Forecasting
    "MAPE":     "lower",
    "MAPE":      "lower",
}

_TASK_METRIC_KEYS = {
    "regression":     ["MAE", "MSE", "RMSE", "R2"],
    "classification": ["Accuracy", "Precision", "Recall", "F1", "ROC_AUC"],
    "forecasting":    ["MAE", "RMSE", "MAPE"],
}


def load_master_memory():
    if not MEMORY_FILE.exists():
        print(f"[ERROR] Master memory file not found: {MEMORY_FILE}")
        return None
    try:
        with MEMORY_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] master_memory.json is corrupted or invalid JSON: {exc}")
        return None


def read_file(file_path):
    if not os.path.exists(file_path):
        print(f"[ERROR] File not found: {file_path}")
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


# ============================================================
# DATASET CEILING CHECKS
# ============================================================

def check_improvement_feasibility(dataset_report: str, validation_metrics: dict) -> dict:
    """
    Analyse the dataset report and current metrics to determine whether
    meaningful improvement is feasible.
    """
    reasons = []
    warnings = []

    try:
        report = json.loads(dataset_report)
    except (json.JSONDecodeError, TypeError):
        return {"feasible": True, "reasons": [], "warnings": []}

    # 1. Dataset too small
    rows = report.get("dataset_overview", {}).get("rows", None)
    if rows is not None and rows < 500:
        reasons.append(
            f"The dataset is too small ({rows} rows). Models cannot reliably "
            "improve on datasets this size — more training data is required."
        )

    # 2. Weak feature-target correlation
    correlations = report.get("top_correlated_with_target", {})
    if correlations:
        max_corr = max(abs(v) for v in correlations.values() if isinstance(v, (int, float)))
        if max_corr < 0.2:
            reasons.append(
                f"All features have weak correlation with the target "
                f"(highest |r| = {round(max_corr, 3)}). The dataset lacks "
                "sufficient predictive signal for meaningful improvement."
            )
        elif max_corr < 0.4:
            warnings.append(
                f"Feature-target correlations are low (highest |r| = {round(max_corr, 3)}). "
                "Improvement potential is limited."
            )

    # 3. High missing values
    columns = report.get("columns", {})
    high_missing_cols = [
        col for col, info in columns.items()
        if isinstance(info, dict) and info.get("missing_percent", 0) > 0.3
    ]
    if high_missing_cols:
        reasons.append(
            f"Critical data quality issue: columns {high_missing_cols} have >30% missing "
            "values. This limits model accuracy regardless of algorithm tuning."
        )

    # 4. Skewed target
    target_analysis = report.get("target_analysis", {})
    target_skew = target_analysis.get("skew", None)
    llm_flags = report.get("llm_flags", [])
    if target_skew is not None and abs(target_skew) > 2:
        if "target_skewed" in llm_flags:
            warnings.append(
                f"The target variable is highly skewed (skew={round(target_skew, 3)}). "
                "A log/power transform on the target was not applied during preprocessing, "
                "which caps regression model performance."
            )

    # 5. Current metrics already excellent — task-aware check
    task_type = report.get("task_type", "regression")

    # Regression: R2 ceiling
    r2 = validation_metrics.get("R2") or validation_metrics.get("r2")
    if r2 is not None and task_type == "regression":
        try:
            r2 = float(r2)
            if r2 >= 0.97:
                reasons.append(
                    f"The model already achieves R²={round(r2, 4)}, which is near-perfect. "
                    "Further improvement is not meaningful."
                )
            elif r2 >= 0.92:
                warnings.append(
                    f"R²={round(r2, 4)} is already very high. Marginal improvement is possible "
                    "but gains will be small."
                )
        except (TypeError, ValueError):
            pass

    # Classification: F1 / Accuracy ceiling
    if task_type == "classification":
        f1 = validation_metrics.get("F1") or validation_metrics.get("f1")
        acc = validation_metrics.get("Accuracy") or validation_metrics.get("accuracy")
        for label, val in [("F1", f1), ("Accuracy", acc)]:
            if val is not None:
                try:
                    val = float(val)
                    if val >= 0.97:
                        reasons.append(
                            f"The model already achieves {label}={round(val, 4)}, near-perfect. "
                            "Further improvement is not meaningful."
                        )
                    elif val >= 0.93:
                        warnings.append(
                            f"{label}={round(val, 4)} is already very high. Marginal gains only."
                        )
                except (TypeError, ValueError):
                    pass

    # Forecasting: low MAPE is already good
    if task_type == "forecasting":
        mape = validation_metrics.get("MAPE") or validation_metrics.get("mape")
        if mape is not None:
            try:
                mape = float(mape)
                if mape < 3.0:
                    reasons.append(
                        f"The model already achieves MAPE={round(mape, 2)}%, which is excellent. "
                        "Further improvement is not meaningful."
                    )
                elif mape < 8.0:
                    warnings.append(
                        f"MAPE={round(mape, 2)}% is already low. Gains will be marginal."
                    )
            except (TypeError, ValueError):
                pass

    # 6. High class imbalance
    imbalance = target_analysis.get("class_imbalance_ratio", None)
    if imbalance is not None:
        try:
            if float(imbalance) > 0.85:
                warnings.append(
                    f"Severe class imbalance detected (dominant class = {round(float(imbalance)*100, 1)}%). "
                    "Metrics may be misleadingly high due to class skew."
                )
        except (TypeError, ValueError):
            pass

    feasible = len(reasons) == 0
    return {"feasible": feasible, "reasons": reasons, "warnings": warnings}


def format_feasibility_message(feasibility: dict) -> str:
    lines = []
    if not feasibility["feasible"]:
        lines.append("⚠️  IMPROVEMENT NOT RECOMMENDED")
        lines.append("")
        lines.append("The following dataset limitations prevent meaningful improvement:")
        for i, reason in enumerate(feasibility["reasons"], 1):
            lines.append(f"  {i}. {reason}")
    if feasibility["warnings"]:
        lines.append("")
        lines.append("⚠️  Warnings (improvement may still run but gains will be limited):")
        for w in feasibility["warnings"]:
            lines.append(f"  • {w}")
    return "\n".join(lines)


# ============================================================
# METRIC COMPARISON  (task-aware)
# ============================================================

def compare_metrics(baseline: dict, improved: dict, task_type: str = "regression") -> dict:
    """
    Compare improved metrics against baseline for any task type.
    task_type: 'regression' | 'classification' | 'forecasting'

    FIX (Bug 4): Both lower-is-better and higher-is-better metrics now use
    a consistent *relative* threshold so that small but real R² / F1 gains
    are not incorrectly reported as "no change".
    """
    # Determine which metric keys to compare for this task
    metric_keys = _TASK_METRIC_KEYS.get(task_type, _TASK_METRIC_KEYS["regression"])

    # Also accept any metric that exists in both dicts (forward-compatibility)
    all_keys = set(metric_keys) | (set(baseline.keys()) & set(improved.keys()))
    relevant_keys = [k for k in all_keys if k in baseline or k in improved]

    delta = {}
    improved_count = 0
    regressed_count = 0

    for key in relevant_keys:
        base_val = baseline.get(key)
        new_val = improved.get(key)
        if base_val is None or new_val is None:
            continue
        try:
            base_val = float(base_val)
            new_val = float(new_val)
        except (TypeError, ValueError):
            continue

        diff = new_val - base_val
        delta[key] = round(diff, 6)

        direction = _METRIC_DIRECTION.get(key, "higher")

        # Use relative threshold for both directions (Bug 4 fix)
        if base_val == 0:
            # Cannot compute relative change; treat any nonzero diff as change
            relative = abs(diff)
        else:
            relative = abs(diff) / abs(base_val)

        meaningful = relative >= MIN_IMPROVEMENT_THRESHOLD

        if direction == "lower":
            # Negative diff = improvement for lower-is-better metrics
            if base_val != 0:
                relative = abs(diff) / abs(base_val)
                if diff < 0 and relative >= MIN_IMPROVEMENT_THRESHOLD:
                    improved_count += 1
                elif diff > 0 and relative >= MIN_IMPROVEMENT_THRESHOLD:
                    regressed_count += 1
            if diff < 0 and meaningful:
                improved_count += 1
            elif diff > 0 and meaningful:
                regressed_count += 1
        else:
            # Positive diff = improvement for higher-is-better metrics
            if abs(diff) >= MIN_IMPROVEMENT_THRESHOLD:
                if diff > 0:
                    improved_count += 1
                else:
                    regressed_count += 1
            if diff > 0 and meaningful:
                improved_count += 1
            elif diff < 0 and meaningful:
                regressed_count += 1

    total_comparable = improved_count + regressed_count
    no_change = total_comparable == 0

    summary_lines = ["Metric comparison (baseline → improved):"]
    for key, d in delta.items():
        base_val = baseline.get(key, "N/A")
        new_val = improved.get(key, "N/A")
        direction = _METRIC_DIRECTION.get(key, "higher")
        if direction == "lower":
            status = "✅ better" if d < 0 else ("❌ worse" if d > 0 else "— unchanged")
        else:
            status = "✅ better" if d > 0 else ("❌ worse" if d < 0 else "— unchanged")
        summary_lines.append(f"  {key}: {base_val} → {new_val}  ({status}, Δ={d})")

    if improved_count > 0 and regressed_count == 0:
        summary_lines.append("\n✅ Overall: Model improved.")
    elif regressed_count > 0 and improved_count == 0:
        summary_lines.append("\n❌ Overall: Model regressed — reverting to baseline.")
    elif improved_count > 0 and regressed_count > 0:
        summary_lines.append("\n⚠️  Overall: Mixed results — some metrics improved, some regressed.")
    else:
        summary_lines.append("\n— Overall: No meaningful change detected.")

    return {
        "improved": improved_count > 0 and regressed_count == 0,
        "regressed": regressed_count > 0 and improved_count == 0,
        "mixed": improved_count > 0 and regressed_count > 0,
        "no_change": no_change,
        "delta": delta,
        "summary": "\n".join(summary_lines),
    }


# ============================================================
# LLM IMPROVEMENT STEPS
# ============================================================

def get_improvement_steps(
    model_name,
    validation_metrics,
    validation_code,
    dataset_report,
    dataset_context,
    model=DEFAULT_MODEL,
    endpoint=DEFAULT_ENDPOINT,
):
    prompt_text = """
You are a precise ML code advisor.

Your task is to recommend improvements to the ML model to enhance validation metrics
based strictly on the information provided.

INPUT:
- Model Name: {model_name}
- Baseline Validation Metrics on 20% held-out split: {validation_metrics}
- Full Validation Code:
{validation_code}
- Dataset Report:
{dataset_report}
- Dataset Context:
{dataset_context}

RULES FOR RESPONSE:
- ONLY suggest actionable improvements (e.g., preprocessing, feature engineering,
  hyperparameter tuning within the same model type, data augmentation).
- Every suggested step MUST be expected to improve the held-out validation metrics.
  Do NOT suggest changes that only improve training set performance.
- Do NOT invent details or assume missing information.
- Do NOT suggest changing model type.
- Do NOT modify the code directly; suggest steps only.
- Do NOT suggest steps that increase model complexity if the dataset has fewer than
  1000 rows — overfitting risk outweighs potential gain.
- For classification tasks, focus on improving F1/ROC-AUC rather than raw Accuracy.
- For regression tasks, focus on reducing MAE/RMSE and increasing R2.
- For forecasting tasks, focus on reducing MAE/RMSE/MAPE.
- If class imbalance is flagged in the report, suggest class_weight or SMOTE.
- Focus on concrete, numbered steps.

Return as a **numbered list of improvement steps**.
"""

    prompt = ChatPromptTemplate.from_template(prompt_text)
    model_llm = create_chat_llm(model=model, endpoint=endpoint, temperature=0.2)
    chain = prompt | model_llm | StrOutputParser()

    return chain.invoke({
        "model_name": model_name,
        "validation_metrics": json.dumps(validation_metrics, indent=2),
        "validation_code": validation_code,
        "dataset_report": dataset_report,
        "dataset_context": dataset_context,
    })


# ============================================================
# MAIN (standalone usage)
# ============================================================

def main():
    try:
        memory = load_master_memory()
        if not memory:
            return

        orchestrator_memory = memory.get("llm_orchestrator", {}).get("orchestrator_memory", {})
        model_name = orchestrator_memory.get("selected_model_for_full_training")

        validation_metrics_dict = orchestrator_memory.get("validation_metrics", {})
        validation_metrics = None
        validation_code_path = None
        if model_name and model_name in validation_metrics_dict:
            validation_info = validation_metrics_dict[model_name]
            validation_metrics = validation_info.get("metrics", {})
            validation_code_path = validation_info.get("code_path")

        dataset_context = memory.get("context_of_dataset")
        dataset_report_path = memory.get("preprocessing", {}).get("report_path")

        if not all([model_name, validation_metrics, dataset_context, validation_code_path, dataset_report_path]):
            print("[ERROR] Missing required fields in master memory.")
            return

        validation_code = read_file(validation_code_path)
        dataset_report = read_file(dataset_report_path)

        if validation_code is None or dataset_report is None:
            return

        print("\n[INFO] Running improvement feasibility checks...\n")
        feasibility = check_improvement_feasibility(dataset_report, validation_metrics)

        if feasibility["warnings"]:
            print(format_feasibility_message({"feasible": True, "reasons": [], "warnings": feasibility["warnings"]}))

        if not feasibility["feasible"]:
            print(format_feasibility_message(feasibility))
            print("\n[INFO] Improvement agent halted due to dataset limitations.")
            return

        print(f"\n[INFO] Requesting improvement steps from LLM for model: {model_name}\n")
        improvement_steps = get_improvement_steps(
            model_name=model_name,
            validation_metrics=validation_metrics,
            validation_code=validation_code,
            dataset_report=dataset_report,
            dataset_context=dataset_context,
        )

        print("\n=== IMPROVEMENT STEPS ===")
        print(improvement_steps)
        print("=========================\n")

    except Exception as exc:
        print(f"\n[ERROR] Improvement steps generation failed: {exc}")


if __name__ == "__main__":
    main()
