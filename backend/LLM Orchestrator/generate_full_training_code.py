import os
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


def load_memory():
    # Get the directory where this script is located
    script_dir = Path(__file__).parent
    memory_file = script_dir / "orchestrator_memory.json"
    
    if not memory_file.exists():
        print(f"[ERROR] orchestrator_memory.json not found at: {memory_file}")
        return None
    
    with open(memory_file, "r", encoding="utf-8") as f:
        return json.load(f)


def read_code(code_path):
    with open(code_path, "r", encoding="utf-8") as f:
        return f.read()


def strip_code_fences(text):
    """
    Remove ```python ... ``` or ``` ... ``` fences from LLM output.
    """
    # Remove fenced blocks like ```python ... ``` or ``` ... ```
    text = re.sub(r"```(?:python)?", "", text)
    text = text.replace("```", "")
    text = text.strip()
    return text


def save_full_training_code(filename, code):
    # Get the directory where this script is located
    script_dir = Path(__file__).parent
    output_dir = script_dir / "full_training"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"[INFO] Saved full training code to: {out_path}")


def append_pkl_save(code, model_name_for_filename):
    """Append code to save the trained model as a .pkl file in the script's directory."""
    # e.g. "Gradient Boosting Regressor" -> "gradient_boosting_regressor"; "gradient_boosting_regressor_test" -> "gradient_boosting_regressor"
    base = model_name_for_filename.lower().replace(" ", "_").replace("-", "_")
    if base.endswith("_test"):
        base = base[:-5]
    pkl_suffix = base + "_full.pkl"
    block = f'''
# Save the trained model to a PKL file in this directory
import joblib
from pathlib import Path
_out_dir = Path(__file__).resolve().parent
_out_path = _out_dir / "{pkl_suffix}"
joblib.dump(model, _out_path)
print(f"Saved model to {{_out_path}}")
'''
    return code.rstrip() + "\n" + block.strip() + "\n"


def generate_full_training_code(validation_code, model_llm):
    """
    Send validation/testing code to LLM and convert it to full dataset training code.
    """

    # --- SHORT, STRICT, PHI-4 SAFE PROMPT ---
    prompt_text = """
You are an expert ML code refactorer.

Convert the following VALIDATION TESTING code into FULL DATASET TRAINING code.

STRICT RULES:
- Remove train/test split or any evaluation splitting.
- Train the model on the FULL dataset only.
- Do NOT change the model type, hyperparameters, or imports.
- Do NOT add new functionality.
- Only modify parts related to splitting, evaluation, or predictions.
- Keep the rest of the script IDENTICAL.
- Do NOT add any preprocessing steps (no pd.get_dummies(), no encoding, no scaling, no column drops).
- The CSV is already fully preprocessed. If any encoding exists in the original code, remove it.
- Use exactly: X = df.drop(columns=[target_column]); y = df[target_column]

Return ONLY the final corrected Python code.

Code:
{code}
"""

    prompt = ChatPromptTemplate.from_template(prompt_text)
    chain = prompt | model_llm | StrOutputParser()

    output = chain.invoke({"code": validation_code})

    # Remove any fences that Phi-4 adds
    cleaned_output = strip_code_fences(output)

    return cleaned_output


def main():
    import sys
    
    # Check if a specific model name was provided as argument
    selected_model_name = None
    if len(sys.argv) > 1:
        selected_model_name = sys.argv[1]
    
    memory = load_memory()
    if not memory:
        return

    # Get validation metrics to find the code path for the selected model
    validation_metrics = memory.get("validation_metrics", {})
    generated_paths = memory.get("generated_code_paths", [])
    
    if selected_model_name:
        # Generate code for the specific model only
        if selected_model_name not in validation_metrics:
            print(f"[ERROR] Model '{selected_model_name}' not found in validation metrics.")
            return
        
        model_info = validation_metrics[selected_model_name]
        code_path = model_info.get("code_path")
        
        if not code_path or not os.path.exists(code_path):
            print(f"[ERROR] Code path not found for model '{selected_model_name}': {code_path}")
            return
        
        print(f"[INFO] Generating full training code for: {selected_model_name}\n")
        
        # Prepare LLM
        llm = create_chat_llm(model=DEFAULT_LLM_MODEL, endpoint=DEFAULT_LLM_ENDPOINT, temperature=0.1)
        
        validation_code = read_code(code_path)
        full_training_code = generate_full_training_code(validation_code, llm)
        full_training_code = append_pkl_save(full_training_code, selected_model_name)
        
        # Save new file
        filename = Path(code_path).stem + "_full.py"
        save_full_training_code(filename, full_training_code)
        
        print(f"\n[INFO] Full training code generated successfully for {selected_model_name}.")
    else:
        # Generate code for all models (original behavior)
        if not generated_paths:
            print("[ERROR] No 'generated_code_paths' found in orchestrator_memory.json")
            return

        print("[INFO] Starting LLM conversion of validation → full training code...\n")
        
        # Prepare LLM
        llm = create_chat_llm(model=DEFAULT_LLM_MODEL, endpoint=DEFAULT_LLM_ENDPOINT, temperature=0.1)

        for code_path in generated_paths:
            if not os.path.exists(code_path):
                print(f"[WARNING] Code path does not exist: {code_path}")
                continue

            model_name = Path(code_path).stem
            print(f"[INFO] Processing: {model_name}")

            validation_code = read_code(code_path)

            # Send to LLM
            full_training_code = generate_full_training_code(validation_code, llm)
            full_training_code = append_pkl_save(full_training_code, model_name)

            # Save new file
            filename = model_name + "_full.py"
            save_full_training_code(filename, full_training_code)

        print("\n[INFO] All model codes processed successfully.")


if __name__ == "__main__":
    main()
