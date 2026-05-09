# Usage: python LLM Orchestrator/run_full_training_code_with_llm.py
"""
Run the generated full-training code for the selected model.
On execution failure, fix the code with LLM and retry (like run_validation_code_with_llm.py).
"""
import json
import os
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
            "You are an expert Python ML engineer. Fix the provided FULL DATASET TRAINING code "
            "without changing the model or training logic. Add any missing imports (e.g. mean_absolute_error, "
            "mean_squared_error, r2_score from sklearn.metrics). Keep the exact model implementation, "
            "data loading, preprocessing, model.fit, and the code that saves the model to a .pkl file. "
            "Return only valid Python code that prevents the reported error from reoccurring.",
        ),
        (
            "user",
            "Model context:\n{model_recommendations}\n\n"
            "Dataset context:\n{dataset_context}\n\n"
            "Dataset report:\n{dataset_report}\n\n"
            "Current full training code:\n{code}\n\n"
            "Execution error traceback:\n{error}\n\n"
            "Return only corrected Python code.",
        ),
    ]
)


# --------------------------------------------------------------------
# Utility helpers
# --------------------------------------------------------------------
def extract_code_snippet(content: str) -> str:
    """Extract the first fenced code block from the LLM response."""
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
                cleaned = cleaned[newline_idx + 1 :]
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


def fix_code_with_llm(
    code: str,
    error: str,
    model_recommendations: str,
    dataset_context: str,
    dataset_report: str,
) -> str:
    chain = FIX_PROMPT | llm | parser
    fixed = chain.invoke(
        {
            "code": code,
            "error": error,
            "model_recommendations": model_recommendations,
            "dataset_context": dataset_context,
            "dataset_report": dataset_report,
        }
    )
    return extract_code_snippet(fixed)


# --------------------------------------------------------------------
# Main execution
# --------------------------------------------------------------------
def main():
    base_dir = Path(__file__).parent
    memory_file = base_dir / "orchestrator_memory.json"
    memory_data = load_memory(memory_file)

    selected_model = memory_data.get("selected_model_for_full_training")
    if not selected_model:
        raise ValueError(
            "'selected_model_for_full_training' not found in orchestrator_memory.json. "
            "Select a model for full dataset training in the workflow first."
        )

    full_training_dir = base_dir / "full_training"
    if not full_training_dir.exists():
        raise FileNotFoundError(f"Full training directory not found: {full_training_dir}")

    model_snake = selected_model.lower().replace(" ", "_").replace("-", "_")
    matching = list(full_training_dir.glob("*_full.py"))
    code_path = None
    for p in matching:
        if model_snake in p.stem.lower():
            code_path = p
            break
    if not code_path and matching:
        code_path = max(matching, key=lambda p: p.stat().st_mtime)
    if not code_path or not code_path.exists():
        raise FileNotFoundError(
            f"No full training script found for model '{selected_model}' in {full_training_dir}"
        )

    # Load master memory for context (optional)
    master_memory_path = memory_data.get("master_memory_path")
    dataset_context = "{}"
    dataset_report = "{}"
    model_recommendations = json.dumps(
        memory_data.get("model_recommendations_structured", []), indent=2
    )
    if master_memory_path:
        master_path = Path(master_memory_path)
        if master_path.exists():
            with master_path.open("r", encoding="utf-8") as f:
                master_memory = json.load(f)
            dataset_context = json.dumps(
                {
                    "dataset_name": memory_data.get("dataset_name"),
                    "target_column": memory_data.get("target_column"),
                    "context_of_dataset": memory_data.get("context_of_dataset"),
                    "dataset_path": master_memory.get("dataset_path"),
                    "processed_output_path": master_memory.get("preprocessing", {}).get(
                        "processed_output_path"
                    ),
                },
                indent=2,
            )
            dataset_report = json.dumps(
                master_memory.get("preprocessing", {}).get("report", {}), indent=2
            )

    print(f"[INFO] Running full training code: {code_path.name} (model: {selected_model})\n")
    warm_start_path = os.environ.get("INTELLIMODEL_WARM_START_PATH", "").strip()
    if warm_start_path:
        print(f"[INFO] Warm-start checkpoint provided: {warm_start_path}")

    retries = 0
    while retries < MAX_RETRIES:
        try:
            result = subprocess.run(
                [sys.executable, str(code_path)],
                check=True,
                capture_output=True,
                text=True,
                cwd=str(base_dir),
            )
            if result.stdout:
                print(result.stdout)
            print(f"[INFO] {code_path.name} executed successfully.")
            return
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or ""
            stdout = exc.stdout or ""
            detailed_error = "\n".join(
                [
                    "STDERR:",
                    stderr.strip(),
                    "\nSTDOUT:",
                    stdout.strip(),
                    "\nProcess message:",
                    str(exc),
                ]
            )
            retries += 1
            print(
                f"[ERROR] {code_path.name} execution failed. "
                f"Attempting to fix and retry ({retries}/{MAX_RETRIES})..."
            )
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

    print(
        f"[ERROR] Maximum retries reached for {code_path.name}. "
        "Please inspect the code manually."
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
