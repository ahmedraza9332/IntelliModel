import json
import sys
from pathlib import Path
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from llm_config import DEFAULT_LLM_MODEL, DEFAULT_LLM_ENDPOINT, create_chat_llm

DEFAULT_MODEL = DEFAULT_LLM_MODEL
DEFAULT_ENDPOINT = DEFAULT_LLM_ENDPOINT

current_dir = Path(__file__).parent
OUTPUT_FOLDER = current_dir / "model_testing"
OUTPUT_FOLDER.mkdir(exist_ok=True)


def _strip_code_fences(code: str) -> str:
    if not code:
        return code
    cleaned = code.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
        newline_idx = cleaned.find("\n")
        if newline_idx != -1:
            first_line = cleaned[:newline_idx].strip().lower()
            if first_line.isalpha():
                cleaned = cleaned[newline_idx + 1:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


# Metric printing instructions per task type.
# IMPORTANT: we now also print TRAIN metrics so the runner can detect
# overfitting (large gap between train and test metrics).
METRIC_INSTRUCTIONS = {
    "regression": (
        "After fitting, evaluate on BOTH the train split and the test split.\n"
        "Print ALL of the following metrics on separate lines with the EXACT labels shown:\n"
        "  Train_MAE: <value>\n"
        "  Train_MSE: <value>\n"
        "  Train_RMSE: <value>\n"
        "  Train_R2: <value>\n"
        "  MAE: <value>\n"
        "  MSE: <value>\n"
        "  RMSE: <value>\n"
        "  R2: <value>"
    ),
    "classification": (
        "After fitting, evaluate on BOTH the train split and the test split.\n"
        "Print ALL of the following metrics on separate lines with the EXACT labels shown:\n"
        "  Train_Accuracy: <value>\n"
        "  Train_F1: <value>\n"
        "  Accuracy: <value>\n"
        "  Precision: <value>\n"
        "  Recall: <value>\n"
        "  F1: <value>\n"
        "  ROC_AUC: <value>\n"
        "Use weighted averaging for Precision/Recall/F1 (average='weighted').\n"
        "For ROC_AUC use roc_auc_score; for multi-class use average='weighted' and multi_class='ovr'."
    ),
    "forecasting": (
        "After fitting, evaluate on BOTH the train split and the test split.\n"
        "Print ALL of the following metrics on separate lines with the EXACT labels shown:\n"
        "  Train_MAE: <value>\n"
        "  Train_RMSE: <value>\n"
        "  MAE: <value>\n"
        "  RMSE: <value>\n"
        "  MAPE: <value>\n"
        "Compute MAPE as mean(abs((y_true - y_pred) / (y_true + 1e-10))) * 100.\n"
        "Use a TIME-BASED train/test split (first 80% rows for train, last 20% for test). "
        "Do NOT use random shuffle."
    ),
}


def build_prompt():
    return ChatPromptTemplate.from_template(
        """
You are an ML testing code generator.
Base everything ONLY on the dataset context, dataset report, and the recommended ML model below.
Do NOT invent columns or metadata. Use ONLY what is in the report.

Task type: {task_type}

Write Python code that:
- Loads the cleaned dataset from the exact path: {dataset_file}
- Drops any columns listed in id_columns (these are likely ID/key columns that leak into features): {id_columns}
- Splits into train/test (80/20). For forecasting use the FIRST 80% rows as train.
- Encodes categorical columns if needed (based on report)
- Trains the given ML model
- Evaluates on BOTH the train split AND the test split
- {metric_instructions}
- After printing all metrics, check for overfitting: if train R2 (or train F1/train Accuracy)
  exceeds the test equivalent by more than 0.15, print exactly:
  OVERFITTING_DETECTED: train=<train_value> test=<test_value>
- After printing all metrics, check for underfitting: if test R2 < 0.4 (regression),
  test F1 < 0.5 (classification), or test MAE > 20%% of target range (forecasting), print exactly:
  UNDERFITTING_DETECTED: metric=<metric_name> value=<value>
- Store the trained feature column names as a list and print:
  FEATURE_COLUMNS: <json_list_of_column_names>
  This is required so the inference endpoint knows the exact column order.

STRICT RULES:
- OUTPUT ONLY PYTHON CODE
- NO COMMENTS
- NO MARKDOWN
- NO EXPLANATIONS
- Use the exact full path provided: {dataset_file}
- The path is absolute and should be used as-is in pd.read_csv()

Model to implement:
{model}

Dataset Context:
{context}

Dataset Report:
{report}
"""
    )


def generate_test_code(
    model_name,
    context,
    report,
    dataset_file,
    task_type="regression",
    id_columns=None,
    model=DEFAULT_MODEL,
    endpoint=DEFAULT_ENDPOINT,
):
    llm = create_chat_llm(model=model, endpoint=endpoint, temperature=0.1)
    prompt = build_prompt()
    chain = prompt | llm | StrOutputParser()

    metric_instructions = METRIC_INSTRUCTIONS.get(task_type, METRIC_INSTRUCTIONS["regression"])
    id_cols_str = json.dumps(id_columns or [])

    return chain.invoke({
        "model": model_name,
        "context": context,
        "report": report,
        "dataset_file": dataset_file,
        "task_type": task_type,
        "metric_instructions": metric_instructions,
        "id_columns": id_cols_str,
    })


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate testing code for model recommendations")
    parser.add_argument("--memory", type=Path, default=None)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--endpoint", type=str, default=DEFAULT_ENDPOINT)
    args = parser.parse_args()

    try:
        # Resolve memory file path
        if args.memory is None:
            memory_path = current_dir / "orchestrator_memory.json"
        else:
            memory_path = Path(args.memory)
            if not memory_path.is_absolute():
                if not memory_path.exists():
                    alt_path = current_dir / memory_path
                    if alt_path.exists():
                        memory_path = alt_path
                    else:
                        cwd_path = Path.cwd() / memory_path
                        if cwd_path.exists():
                            memory_path = cwd_path

        if not memory_path.exists():
            raise FileNotFoundError(f"orchestrator_memory.json not found at: {memory_path}")

        with memory_path.open("r", encoding="utf-8") as f:
            orchestrator_memory = json.load(f)

        master_memory_path = orchestrator_memory.get("master_memory_path")
        if not master_memory_path:
            raise ValueError("'master_memory_path' not found in orchestrator_memory.json")

        master_memory_path = Path(master_memory_path)
        if not master_memory_path.exists():
            raise FileNotFoundError(f"Master memory file not found: {master_memory_path}")

        with master_memory_path.open("r", encoding="utf-8") as f:
            master_memory = json.load(f)

        # Resolve dataset file path
        processed_output_path = master_memory.get("preprocessing", {}).get("processed_output_path", "")
        dataset_path = master_memory.get("dataset_path", "")

        if processed_output_path:
            dataset_file_path = Path(processed_output_path)
            if not dataset_file_path.is_absolute():
                dataset_file_path = (master_memory_path.parent / dataset_file_path).resolve()
            dataset_file = str(dataset_file_path)
        elif dataset_path:
            dataset_file_path = Path(dataset_path)
            if not dataset_file_path.is_absolute():
                dataset_file_path = (master_memory_path.parent / dataset_file_path).resolve()
            dataset_file = str(dataset_file_path)
        else:
            raise ValueError("Neither 'processed_output_path' nor 'dataset_path' found in master_memory.json")

        report_json = master_memory.get("preprocessing", {}).get("report", {})
        if not report_json:
            raise ValueError("'report' not found in master_memory.json under 'preprocessing'")

        # Extract ID columns from report so generated code excludes them
        id_columns = report_json.get("id_columns", [])
        if id_columns:
            print(f"[INFO] ID columns that will be excluded from features: {id_columns}")

        selected_models_for_validation = orchestrator_memory.get("selected_models_for_validation", [])
        if not selected_models_for_validation:
            raise ValueError(
                "'selected_models_for_validation' not found in orchestrator_memory.json. "
                "Please select models for validation first."
            )

        structured_recommendations = orchestrator_memory.get("model_recommendations_structured", [])
        context = orchestrator_memory.get("context_of_dataset", "")

        if not structured_recommendations:
            raw_recommendations = orchestrator_memory.get("model_recommendations", "")
            if raw_recommendations:
                import re
                print("Warning: Using raw recommendations, structured format not found. Parsing...")
                model_lines = []
                for line in raw_recommendations.splitlines():
                    match = re.search(r'\d+\.\s*\*\*?(.+?)\*\*?', line)
                    if match:
                        model_lines.append(match.group(1).strip())
                if model_lines:
                    structured_recommendations = [
                        {"Model Recommended": model, "Reason": "No reason provided"}
                        for model in model_lines
                    ]
                else:
                    raise ValueError("No model recommendations found in orchestrator_memory.json")
            else:
                raise ValueError("'model_recommendations_structured' not found in orchestrator_memory.json")

        if not context:
            raise ValueError("'context_of_dataset' missing in orchestrator_memory.json")

        report_str = json.dumps(report_json, indent=2)

        task_type = (
            master_memory.get("task_type")
            or report_json.get("task_type")
            or "regression"
        )
        print(f"Task type: {task_type}")

        print("\n=== Generating validation/testing code for selected models ===\n")
        print(f"Selected models for validation: {', '.join(selected_models_for_validation)}\n")

        generated_files = []

        filtered_recommendations = [
            entry for entry in structured_recommendations
            if entry.get("Model Recommended", "") in selected_models_for_validation
        ]

        for model_entry in filtered_recommendations:
            model_name = model_entry.get("Model Recommended", "")
            if not model_name:
                continue
            print(f"-> Generating testing code for: {model_name}")

            code = generate_test_code(
                model_name=model_name,
                context=context,
                report=report_str,
                dataset_file=dataset_file,
                task_type=task_type,
                id_columns=id_columns,
                model=args.model,
                endpoint=args.endpoint,
            )

            code = _strip_code_fences(code)

            file_name = model_name.lower().replace(" ", "_") + "_test.py"
            file_path = OUTPUT_FOLDER / file_name

            with file_path.open("w", encoding="utf-8") as f:
                f.write(code)

            generated_files.append(str(file_path.resolve()))
            print(f"Saved: {file_path}")

        print("\n=== DONE! Testing code saved in 'model_testing/' folder ===")
        return {"generated_files": generated_files, "task_type": task_type}

    except Exception as exc:
        print(f"\n[ERROR] Validation code generation failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
