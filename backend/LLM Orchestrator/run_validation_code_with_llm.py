# Usage: python "LLM Orchestrator/run_validation_code_with_llm.py"
"""
Run validation/testing code for selected models.
After all models are validated, ask the user:
  a. Satisfied → proceed to full training (writes selected_model_for_full_training)
  b. Not satisfied → redirect to improvement agent
  c. Select another model from recommendations
"""
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from llm_config import DEFAULT_LLM_MODEL, DEFAULT_LLM_ENDPOINT, create_chat_llm


# --------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------
LLM_MODEL = DEFAULT_LLM_MODEL
LLM_ENDPOINT = DEFAULT_LLM_ENDPOINT
MAX_RETRIES = 3

llm = create_chat_llm(model=LLM_MODEL, endpoint=LLM_ENDPOINT, temperature=0.0)
parser = StrOutputParser()

FIX_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an expert Python ML engineer. Fix the provided validation/testing code "
            "without changing the model or evaluation logic. Maintain the exact model implementation "
            "and metrics calculation. Use the dataset context and report to reason about required "
            "columns and data types. Return only valid Python code that prevents "
            "the reported error from reoccurring.",
        ),
        (
            "user",
            "Model recommendations context:\n{model_recommendations}\n\n"
            "Dataset context:\n{dataset_context}\n\n"
            "Dataset report:\n{dataset_report}\n\n"
            "Current code:\n{code}\n\n"
            "Execution error traceback:\n{error}\n\n"
            "Return only corrected Python code.",
        ),
    ]
)


# --------------------------------------------------------------------
# Utility helpers
# --------------------------------------------------------------------
def extract_code_snippet(content: str) -> str:
    if not content:
        return content
    match = re.search(r"```(?:[\w+-]+)?\s*([\s\S]*?)```", content)
    if match:
        return match.group(1).strip()
    return strip_code_fences(content)


def strip_code_fences(content: str) -> str:
    """Remove markdown code fences from LLM output."""
    if not content:
        return content
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
        newline_idx = cleaned.find("\n")
        if newline_idx != -1:
            maybe_lang = cleaned[:newline_idx].strip().lower()
            if maybe_lang.isalpha():
                cleaned = cleaned[newline_idx + 1:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def load_memory(memory_file: Path) -> dict:
    if not memory_file.exists():
        raise FileNotFoundError(
            f"Orchestrator memory not found at {memory_file}. "
            "Run the LLM orchestrator workflow agent first."
        )
    try:
        with memory_file.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Memory file is corrupted (invalid JSON): {memory_file}\n"
            f"Error: {exc}\n"
            "Please delete or repair the file and re-run the workflow."
        ) from exc


def resolve_path(base_dir: Path, stored_path: Optional[str], fallback_name: Optional[str]) -> Path:
    if stored_path:
        stored = Path(stored_path)
        return stored if stored.is_absolute() else (base_dir / stored).resolve()
    if fallback_name:
        fallback = Path(fallback_name)
        if fallback.is_absolute():
            return fallback
        return (base_dir / fallback).resolve()
    raise FileNotFoundError("Unable to determine required path from memory.")


def fix_code_with_llm(
    code: str,
    error: str,
    model_recommendations: str,
    dataset_context: str,
    dataset_report: str,
) -> str:
    chain = FIX_PROMPT | llm | parser
    fixed = chain.invoke({
        "code": code,
        "error": error,
        "model_recommendations": model_recommendations,
        "dataset_context": dataset_context,
        "dataset_report": dataset_report,
    })
    return extract_code_snippet(fixed)


# All metrics we know how to parse, keyed by their printed label.
_ALL_METRIC_PATTERNS = {
    "MAE":       r"MAE\s*[:\s]+([0-9eE+\-.]+)",
    "MSE":       r"MSE\s*[:\s]+([0-9eE+\-.]+)",
    "RMSE":      r"RMSE\s*[:\s]+([0-9eE+\-.]+)",
    "R2":        r"R2\s*[:\s]+([0-9eE+\-.]+)",
    "Accuracy":  r"Accuracy\s*[:\s]+([0-9eE+\-.]+)",
    "Precision": r"Precision\s*[:\s]+([0-9eE+\-.]+)",
    "Recall":    r"Recall\s*[:\s]+([0-9eE+\-.]+)",
    "F1":        r"F1\s*[:\s]+([0-9eE+\-.]+)",
    "ROC_AUC":   r"ROC_AUC\s*[:\s]+([0-9eE+\-.]+)",
    "MAPE":      r"MAPE\s*[:\s]+([0-9eE+\-.]+)",
}

_TASK_METRIC_KEYS = {
    "regression":     ["MAE", "MSE", "RMSE", "R2"],
    "classification": ["Accuracy", "Precision", "Recall", "F1", "ROC_AUC"],
    "forecasting":    ["MAE", "RMSE", "MAPE"],
}


def _parse_metrics(stdout: str, task_type: str) -> dict:
    """Parse whichever metrics are relevant for task_type from the script's stdout."""
    keys = _TASK_METRIC_KEYS.get(task_type, list(_ALL_METRIC_PATTERNS.keys()))
    metrics: dict = {}
    for key in keys:
        pattern = _ALL_METRIC_PATTERNS.get(key)
        if not pattern:
            continue
        m = re.search(pattern, stdout, re.IGNORECASE)
        if m:
            try:
                metrics[key] = float(m.group(1))
            except ValueError:
                metrics[key] = m.group(1)
    return metrics


# --------------------------------------------------------------------
# Post-validation decision
# --------------------------------------------------------------------
def ask_post_validation_decision(
    memory_data: dict,
    validation_metrics: dict,
    memory_file: Path,
) -> str:
    """
    After validation, show metrics for all models and ask the user:
      a. Satisfied → select a model for full training
      b. Not satisfied → go to improvement agent
      c. Select another model from the recommendations list

    Returns: 'full_training' | 'improvement' | 'select_another'
    """
    print("\n" + "=" * 65)
    print("  VALIDATION RESULTS SUMMARY")
    print("=" * 65)

    model_list = list(validation_metrics.keys())
    for model_name, info in validation_metrics.items():
        print(f"\n  Model: {model_name}")
        metrics = info.get("metrics", {})
        if metrics:
            for k, v in metrics.items():
                print(f"    {k}: {v}")
        else:
            print("    (no metrics captured)")

    print("\n" + "=" * 65)
    print("What would you like to do?")
    print("  a. Proceed to full dataset training (satisfied with a model)")
    print("  b. Go to improvement agent (improve one of the models)")
    print("  c. Select a different model from recommendations")

    while True:
        try:
            choice = input("\nEnter choice (a/b/c): ").strip().lower()
            if choice == "a":
                print("\nWhich model do you want to use for full training?")
                for i, name in enumerate(model_list, 1):
                    print(f"  {i}. {name}")
                while True:
                    try:
                        idx = int(input(f"Enter number (1-{len(model_list)}): ").strip()) - 1
                        if 0 <= idx < len(model_list):
                            selected = model_list[idx]
                            memory_data["selected_model_for_full_training"] = selected
                            with memory_file.open("w", encoding="utf-8") as f:
                                json.dump(memory_data, f, indent=2)
                            print(f"\n[INFO] Selected '{selected}' for full training.")
                            return "full_training"
                        print(f"Please enter 1-{len(model_list)}")
                    except ValueError:
                        print("Please enter a valid number.")
            elif choice == "b":
                return "improvement"
            elif choice == "c":
                return "select_another"
            else:
                print("Please enter a, b, or c.")
        except (EOFError, KeyboardInterrupt):
            print("\nDefaulting to full training.")
            if model_list:
                memory_data["selected_model_for_full_training"] = model_list[0]
                with memory_file.open("w", encoding="utf-8") as f:
                    json.dump(memory_data, f, indent=2)
            return "full_training"


# --------------------------------------------------------------------
# Main execution
# --------------------------------------------------------------------
def main():
    base_dir = Path(__file__).parent
    memory_file = base_dir / "orchestrator_memory.json"
    memory_data = load_memory(memory_file)

    master_memory_path = memory_data.get("master_memory_path")
    if not master_memory_path:
        raise FileNotFoundError("'master_memory_path' not found in orchestrator_memory.json")

    master_memory_path = Path(master_memory_path)
    if not master_memory_path.exists():
        raise FileNotFoundError(f"Master memory file not found: {master_memory_path}")

    with master_memory_path.open("r", encoding="utf-8") as f:
        master_memory = json.load(f)

    dataset_context = json.dumps({
        "dataset_name": memory_data.get("dataset_name"),
        "target_column": memory_data.get("target_column"),
        "context_of_dataset": memory_data.get("context_of_dataset"),
        "dataset_path": master_memory.get("dataset_path"),
        "processed_output_path": master_memory.get("preprocessing", {}).get("processed_output_path"),
    }, indent=2)

    dataset_report = json.dumps(master_memory.get("preprocessing", {}).get("report", {}), indent=2)
    model_recommendations = json.dumps(memory_data.get("model_recommendations_structured", []), indent=2)

    task_type = (
        memory_data.get("task_type")
        or master_memory.get("task_type")
        or master_memory.get("preprocessing", {}).get("report", {}).get("task_type")
        or "regression"
    )
    print(f"[INFO] Task type: {task_type}")

    generated_code_paths = memory_data.get("generated_code_paths", [])

    if not generated_code_paths:
        file_history = memory_data.get("file_history", {})
        generated_code_paths = [
            file_history[key]
            for key in sorted(file_history.keys())
            if key.startswith("validation_code_")
        ]

    if not generated_code_paths:
        model_testing_dir = base_dir / "model_testing"
        if model_testing_dir.exists():
            generated_code_paths = [
                str(f.resolve()) for f in model_testing_dir.glob("*_test.py")
            ]

    if not generated_code_paths:
        raise FileNotFoundError(
            "No validation/testing code files found. "
            "Run model_vc_gen.py or the LLM orchestrator workflow agent first."
        )

    print(f"[INFO] Found {len(generated_code_paths)} validation/testing code file(s) to run\n")

    structured_recs = memory_data.get("model_recommendations_structured", [])
    selected_models = memory_data.get("selected_models_for_validation", [])
    validation_metrics = memory_data.get("validation_metrics", {})

    for idx, code_path_str in enumerate(generated_code_paths):
        code_path = Path(code_path_str)

        if not code_path.exists():
            print(f"[WARN] Code file not found: {code_path}. Skipping.")
            continue

        model_name = None
        if idx < len(selected_models):
            model_name = selected_models[idx]
        if not model_name:
            code_name = code_path.stem.replace("_test", "").replace("_validation", "")
            for rec in structured_recs:
                rec_name = rec.get("Model Recommended", "")
                if rec_name.lower().replace(" ", "_").replace("-", "_") == code_name.lower():
                    model_name = rec_name
                    break
        if not model_name:
            model_name = code_path.stem

        print(f"[INFO] Running validation/testing code: {code_path.name} (model: {model_name})")

        retries = 0
        last_stdout = ""
        while retries < MAX_RETRIES:
            try:
                result = subprocess.run(
                    [sys.executable, str(code_path)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                last_stdout = result.stdout or ""
                if last_stdout:
                    print(last_stdout)
                print(f"[INFO] {code_path.name} executed successfully.\n")
                break
            except subprocess.CalledProcessError as exc:
                stderr = exc.stderr or ""
                stdout = exc.stdout or ""
                last_stdout = stdout
                detailed_error = "\n".join([
                    "STDERR:",
                    stderr.strip(),
                    "\nSTDOUT:",
                    stdout.strip(),
                    "\nProcess message:",
                    str(exc),
                ])
                retries += 1
                print(f"[ERROR] {code_path.name} execution failed. Attempting to fix and retry ({retries}/{MAX_RETRIES})...")
                code_content = code_path.read_text(encoding="utf-8")
                print("[INFO] Sending failing code to LLM for repair...")
                corrected_code = fix_code_with_llm(
                    code_content,
                    detailed_error,
                    model_recommendations,
                    dataset_context,
                    dataset_report,
                )
                code_path.write_text(corrected_code, encoding="utf-8")
                print("[INFO] Code fixed. Retrying execution...\n")

        if retries < MAX_RETRIES and last_stdout:
            metrics = _parse_metrics(last_stdout, task_type)
            validation_metrics[model_name] = {
                "code_path": str(code_path.resolve()),
                "metrics": metrics,
                "task_type": task_type,
            }

        if retries >= MAX_RETRIES:
            print(f"[ERROR] Maximum retries reached for {code_path.name}. "
                  "Please inspect the code manually.\n")

    memory_data["validation_metrics"] = validation_metrics
    memory_data["task_type"] = task_type
    with memory_file.open("w", encoding="utf-8") as f:
        json.dump(memory_data, f, indent=2)

    print("[INFO] All validation/testing code execution completed and metrics saved to orchestrator_memory.json.\n")

    if not validation_metrics:
        print("[WARN] No metrics were captured. Cannot present decision menu.")
        return

    decision = ask_post_validation_decision(memory_data, validation_metrics, memory_file)

    if decision == "full_training":
        print("\n[INFO] Proceeding to full training. Run generate_full_training_code.py next.")
    elif decision == "improvement":
        print("\n[INFO] Redirecting to improvement agent. Run improvement_workflow_agent.py next.")
        memory_data["next_step"] = "improvement_agent"
        with memory_file.open("w", encoding="utf-8") as f:
            json.dump(memory_data, f, indent=2)
    elif decision == "select_another":
        print("\n[INFO] Please re-run model_vc_gen.py to select different models, then re-run this script.")
        memory_data["next_step"] = "select_another_model"
        with memory_file.open("w", encoding="utf-8") as f:
            json.dump(memory_data, f, indent=2)


if __name__ == "__main__":
    main()
