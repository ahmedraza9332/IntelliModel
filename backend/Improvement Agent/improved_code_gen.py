"""
Improved Code Generator

Reads the improvement memory (improvement_memory.json) to obtain:
  - improvement_steps (text)
  - validation_code_path (the original validation/testing script)
  - dataset_context
  - task_type

Prompts the LLM to produce an improved version of the validation code
that incorporates the improvement steps, then saves the result to:
  Improvement Agent/improved_training/{model_name}_improved_validation.py

KEY FIX: The prompt now strictly enforces metric printing format so the
runner can always capture metrics via stdout regex (no eval() dependency).
"""

import json
import re
import sys
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from llm_config import DEFAULT_LLM_MODEL, DEFAULT_LLM_ENDPOINT, create_chat_llm

CURRENT_DIR = Path(__file__).resolve().parent


def _find_improvement_memory() -> Path:
    """
    Find improvement_memory.json — checks the flat path first, then
    searches one level of subdirectories (per-dataset folders).
    """
    flat = CURRENT_DIR / "improvement_memory.json"
    if flat.exists():
        return flat
    # Search dataset-scoped subfolders
    for sub in sorted(CURRENT_DIR.iterdir()):
        if sub.is_dir():
            candidate = sub / "improvement_memory.json"
            if candidate.exists():
                return candidate
    # Return flat path anyway so the error message is meaningful
    return flat


IMPROVEMENT_MEMORY_PATH = _find_improvement_memory()

# Metric printing blocks per task type — injected verbatim into the prompt
# so the LLM copies them exactly into the improved code.
_METRIC_PRINT_BLOCKS = {
    "regression": """\
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import numpy as np
mae = mean_absolute_error(y_test, y_pred)
mse = mean_squared_error(y_test, y_pred)
rmse = np.sqrt(mse)
r2 = r2_score(y_test, y_pred)
print(f"MAE: {mae}")
print(f"MSE: {mse}")
print(f"RMSE: {rmse}")
print(f"R2: {r2}")
""",
    "classification": """\
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
accuracy = accuracy_score(y_test, y_pred)
precision = precision_score(y_test, y_pred, average='weighted', zero_division=0)
recall = recall_score(y_test, y_pred, average='weighted', zero_division=0)
f1 = f1_score(y_test, y_pred, average='weighted', zero_division=0)
try:
    roc_auc = roc_auc_score(y_test, y_pred_proba, average='weighted', multi_class='ovr')
except Exception:
    roc_auc = float('nan')
print(f"Accuracy: {accuracy}")
print(f"Precision: {precision}")
print(f"Recall: {recall}")
print(f"F1: {f1}")
print(f"ROC_AUC: {roc_auc}")
""",
    "forecasting": """\
from sklearn.metrics import mean_absolute_error, mean_squared_error
import numpy as np
mae = mean_absolute_error(y_test, y_pred)
mse = mean_squared_error(y_test, y_pred)
rmse = np.sqrt(mse)
mape = float(np.mean(np.abs((np.array(y_test) - np.array(y_pred)) / (np.array(y_test) + 1e-10))) * 100)
print(f"MAE: {mae}")
print(f"RMSE: {rmse}")
print(f"MAPE: {mape}")
""",
}


def _strip_code_fences(text: str) -> str:
    """Extract the first fenced Python code block, or strip surrounding fences."""
    if not text:
        return text
    match = re.search(r"```(?:python)?\s*([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
        nl = cleaned.find("\n")
        if nl != -1 and cleaned[:nl].strip().isalpha():
            cleaned = cleaned[nl + 1:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def generate_improved_validation_code(
    validation_code: str,
    improvement_steps: str,
    dataset_context: str,
    task_type: str = "regression",
    model: str = DEFAULT_LLM_MODEL,
    endpoint: str = DEFAULT_LLM_ENDPOINT,
) -> str:
    """
    Prompt the LLM to rewrite the validation code incorporating the
    improvement steps.  The metric printing block is injected verbatim
    so the runner can always parse metrics from stdout.
    """
    metric_block = _METRIC_PRINT_BLOCKS.get(task_type, _METRIC_PRINT_BLOCKS["regression"])

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an expert Python ML engineer. "
                "Improve the provided model validation/testing code by applying "
                "ONLY the listed improvement steps. "
                "Do NOT change the ML model type. "
                "Do NOT change the train/test split ratio. "
                "Keep the same dataset loading strategy. "
                "You MUST use the EXACT metric printing block shown below — copy it "
                "verbatim into the code, replacing any existing metric calculation and "
                "print statements. This is mandatory for downstream metric capture.\n\n"
                "MANDATORY METRIC PRINTING BLOCK (copy exactly):\n"
                "{metric_block}\n\n"
                "Return ONLY valid, runnable Python code — no explanations, no markdown.",
            ),
            (
                "user",
                "Improvement steps to apply:\n{steps}\n\n"
                "Dataset context:\n{dataset_context}\n\n"
                "Current validation/testing code:\n{code}\n\n"
                "Return only the improved Python code with the mandatory metric block included.",
            ),
        ]
    )

    llm = create_chat_llm(model=model, endpoint=endpoint, temperature=0.1)
    chain = prompt | llm | StrOutputParser()

    raw = chain.invoke(
        {
            "steps": improvement_steps,
            "dataset_context": dataset_context,
            "code": validation_code,
            "metric_block": metric_block,
        }
    )
    return _strip_code_fences(raw)


def main() -> None:
    # ------------------------------------------------------------------
    # Load everything from improvement_memory.json
    # ------------------------------------------------------------------
    if not IMPROVEMENT_MEMORY_PATH.exists():
        print(f"[ERROR] improvement_memory.json not found at: {IMPROVEMENT_MEMORY_PATH}")
        sys.exit(1)

    with IMPROVEMENT_MEMORY_PATH.open("r", encoding="utf-8") as f:
        mem = json.load(f)

    model_name = mem.get("model_name")
    dataset_context = mem.get("dataset_context", "")
    improvement_steps = mem.get("improvement_steps")
    improvement_steps_path = mem.get("improvement_steps_path")
    validation_code_path = mem.get("validation_code_path")
    task_type = mem.get("task_type", "regression")

    # ------------------------------------------------------------------
    # Resolve improvement steps text
    # ------------------------------------------------------------------
    if not improvement_steps and improvement_steps_path:
        p = Path(improvement_steps_path)
        if p.exists():
            improvement_steps = p.read_text(encoding="utf-8")

    if not improvement_steps:
        print("[ERROR] No improvement steps found in memory.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Load original validation code
    # ------------------------------------------------------------------
    if not validation_code_path:
        print("[ERROR] validation_code_path missing from improvement memory.")
        sys.exit(1)

    vc_path = Path(validation_code_path)
    if not vc_path.exists():
        print(f"[ERROR] Validation code file not found: {vc_path}")
        sys.exit(1)

    validation_code = vc_path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Generate improved code via LLM
    # ------------------------------------------------------------------
    print(f"[INFO] Generating improved validation code for: {model_name} (task: {task_type})")
    improved_code = generate_improved_validation_code(
        validation_code=validation_code,
        improvement_steps=improvement_steps,
        dataset_context=dataset_context,
        task_type=task_type,
    )

    # ------------------------------------------------------------------
    # Save to improved_training/{model_name}_improved_validation.py
    # Use same parent as improvement_memory.json for dataset scoping
    # ------------------------------------------------------------------
    output_dir = IMPROVEMENT_MEMORY_PATH.parent / "improved_training"
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = (model_name or "model").lower().replace(" ", "_").replace("-", "_")
    output_file = output_dir / f"{safe_name}_improved_validation.py"
    output_file.write_text(improved_code, encoding="utf-8")

    print(f"[INFO] Improved validation code saved to: {output_file}")

    # ------------------------------------------------------------------
    # Write the output path back into improvement_memory.json
    # ------------------------------------------------------------------
    try:
        with IMPROVEMENT_MEMORY_PATH.open("r", encoding="utf-8") as f:
            mem_data = json.load(f)
        mem_data["improved_validation_code_path"] = str(output_file.resolve())
        with IMPROVEMENT_MEMORY_PATH.open("w", encoding="utf-8") as f:
            json.dump(mem_data, f, indent=2)
        print(f"[INFO] improvement_memory.json updated with improved_validation_code_path.")
    except Exception as exc:
        print(f"[WARN] Could not update improvement_memory.json: {exc}")


if __name__ == "__main__":
    main()
