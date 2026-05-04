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
            "You are an expert Python ML engineer. Fix the provided preprocessing code "
            "without changing the preprocessing plan semantics. Maintain the exact step "
            "order and intent defined in the plan JSON. Use the dataset context to reason "
            "about required columns and shapes. Return only valid Python code that prevents "
            "the reported error from reoccurring.",
        ),
        (
            "user",
            "Preprocessing plan (do not deviate):\n{plan_json}\n\n"
            "Dataset context:\n{dataset_context}\n\n"
            "Current code:\n{code}\n\n"
            "Execution error traceback:\n{error}\n\n"
            "Return only corrected Python code.",
        ),
    ]
)


# --------------------------------------------------------------------
# Utility helpers
# --------------------------------------------------------------------
def sanitize_non_printable(code: str) -> str:
    """Remove non-printable Unicode characters that cause SyntaxErrors (e.g. U+0001)."""
    return re.sub(r"[^\x09\x0A\x0D\x20-\x7E\u00A0-\uFFFF]", "", code)


def extract_code_snippet(content: str) -> str:
    """
    Extract the first fenced code block from the LLM response.
    Falls back to stripping fences if no explicit block is found.
    """
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
            f"Workflow memory not found at {memory_file}. "
            "Run the preprocessing workflow agent first."
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


def fix_code_with_llm(code: str, error: str, plan_json: str, dataset_context: str) -> str:
    chain = FIX_PROMPT | llm | parser
    fixed = chain.invoke(
        {
            "code": code,
            "error": error,
            "plan_json": plan_json,
            "dataset_context": dataset_context,
        }
    )
    return sanitize_non_printable(extract_code_snippet(fixed))


# --------------------------------------------------------------------
# Main execution
# --------------------------------------------------------------------
def main():
    base_dir = Path(__file__).parent
    memory_file = base_dir / "workflow_memory.json"
    memory_data = load_memory(memory_file)

    code_path = resolve_path(
        base_dir,
        memory_data.get("code_path"),
        memory_data.get("file_history", {}).get("generated_code"),
    )
    plan_path = resolve_path(
        base_dir,
        memory_data.get("plan_path"),
        memory_data.get("file_history", {}).get("preprocessing_plan"),
    )

    if not code_path.exists():
        raise FileNotFoundError(f"Generated preprocessing code not found at {code_path}")
    if not plan_path.exists():
        raise FileNotFoundError(f"Preprocessing plan file not found at {plan_path}")

    plan_json = plan_path.read_text(encoding="utf-8")
    dataset_context = json.dumps(memory_data.get("dataset_info", {}), indent=2)

    retries = 0
    while retries < MAX_RETRIES:
        try:
            print(f"[INFO] Running preprocessing script: {code_path}")
            result = subprocess.run(
                [sys.executable, str(code_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            if result.stdout:
                print(result.stdout)
            print("[INFO] Script executed successfully.")
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
            print(f"[ERROR] Script execution failed:\n{detailed_error}")

            code_content = code_path.read_text(encoding="utf-8")
            print("[INFO] Sending failing code to LLM for repair...")
            corrected_code = fix_code_with_llm(
                code_content, detailed_error, plan_json, dataset_context
            )
            code_path.write_text(corrected_code, encoding="utf-8")
            retries += 1
            print(f"[INFO] Retry {retries}/{MAX_RETRIES}")

    raise RuntimeError(
        "Maximum retries reached. Please inspect the generated code manually."
    )


if __name__ == "__main__":
    main()

