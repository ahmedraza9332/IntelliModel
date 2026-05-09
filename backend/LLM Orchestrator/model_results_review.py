import json
import os
from pathlib import Path

def load_memory():
    # Get the directory where this script is located
    script_dir = Path(__file__).parent
    memory_file = script_dir / "orchestrator_memory.json"
    
    if not memory_file.exists():
        print(f"[ERROR] orchestrator_memory.json not found at: {memory_file}")
        return None
    try:
        with open(memory_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] orchestrator_memory.json is corrupted (invalid JSON): {exc}")
        print(f"        Please delete or repair: {memory_file}")
        return None


def print_model_metrics(validation_dict):
    print("\n================= MODEL PERFORMANCE METRICS =================\n")

    # Determine which metric keys are actually present across all models
    # so we can display regression, classification, or forecasting metrics
    _ALL_REGRESSION   = ["MAE", "MSE", "RMSE", "R2"]
    _ALL_CLASSIFICATION = ["Accuracy", "Precision", "Recall", "F1", "ROC_AUC"]
    _ALL_FORECASTING  = ["MAE", "RMSE", "MAPE"]

    for model_name, model_info in validation_dict.items():
        metrics = model_info.get("metrics", {})
        task_type = model_info.get("task_type", "regression")
        print(f"Model: {model_name}  (task: {task_type})")

        if task_type == "classification":
            keys = _ALL_CLASSIFICATION
        elif task_type == "forecasting":
            keys = _ALL_FORECASTING
        else:
            keys = _ALL_REGRESSION

        for key in keys:
            val = metrics.get(key)
            if val is not None:
                print(f"  {key}: {val}")

        # Also print any extra keys the generated code happened to produce
        extra = {k: v for k, v in metrics.items() if k not in keys and v is not None}
        for k, v in extra.items():
            print(f"  {k}: {v}")

        print(f"  Code Path: {model_info.get('code_path')}")
        print()

    print("==============================================================\n")


def ask_yes_no(prompt):
    while True:
        choice = input(prompt + " (y/n): ").strip().lower()
        if choice in ["y", "n"]:
            return choice
        print("Invalid input. Enter 'y' or 'n'.")


def choose_model(validation_dict):
    models = list(validation_dict.keys())

    print("\nSelect the model you want to train on the FULL dataset:")
    for idx, model_name in enumerate(models, start=1):
        print(f"{idx}. {model_name}")

    while True:
        choice = input("Enter the number of the model: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(models):
            selected = models[int(choice) - 1]
            print(f"\n[INFO] You selected: {selected}")
            # User is satisfied and has chosen a model; always generate full training code
            return {"action": "generate_full_training", "model": selected}
        print("Invalid choice. Try again.")


def improvement_menu():
def not_satisfied_menu():
    """
    Shown when the user is not happy with validation results.
    The only options are to reselect models and re-run validation,
    or to exit.  The improvement agent runs AFTER full training /
    deployment — it is NOT available at this stage.
    """
    print("\nWhat would you like to do next?")
    print("1. Run improvement agent")
    print("2. Reselect models")
    print("3. Exit")
    print("1. Reselect models and re-run validation")
    print("2. Exit")

    while True:
        option = input("Enter option: ").strip()
        if option == "1":
            # Load master_memory.json
            master_memory = load_master_memory()
            if not master_memory:
                return
            
            # Get the list of models from selected_models_for_validation
            if "llm_orchestrator" not in master_memory:
                master_memory["llm_orchestrator"] = {}
            if "orchestrator_memory" not in master_memory["llm_orchestrator"]:
                master_memory["llm_orchestrator"]["orchestrator_memory"] = {}
            
            orchestrator_memory = master_memory["llm_orchestrator"]["orchestrator_memory"]
            models_list = orchestrator_memory.get("selected_models_for_validation", [])
            
            if not models_list:
                print("[ERROR] No models found in selected_models_for_validation.")
                return
            
            # Display models and let user select
            print("\nSelect the model you would like to improve:")
            for idx, model_name in enumerate(models_list, start=1):
                print(f"{idx}. {model_name}")
            
            while True:
                choice = input("Enter the number of the model: ").strip()
                if choice.isdigit() and 1 <= int(choice) <= len(models_list):
                    selected_model = models_list[int(choice) - 1]
                    print(f"\n[INFO] You selected: {selected_model}")
                    
                    # Update master_memory.json
                    orchestrator_memory["selected_model_for_full_training"] = selected_model
                    save_master_memory(master_memory)
                    print(f"[INFO] Selected model '{selected_model}' saved to master_memory.json")
                    
                    # Also update orchestrator_memory.json to keep them in sync
                    orchestrator_memory_local = load_memory()
                    if orchestrator_memory_local:
                        orchestrator_memory_local["selected_model_for_full_training"] = selected_model
                        save_memory(orchestrator_memory_local)
                        print(f"[INFO] Selected model '{selected_model}' saved to orchestrator_memory.json")
                    
                    print("\n[INFO] Improvement Agent will run here.\n")
                    return
                print("Invalid choice. Try again.")
            print("\n[INFO] Requesting model reselection in LLM Orchestrator workflow.\n")
            memory = load_memory()
            if memory:
                memory["review_action"] = "reselect_models"
                save_memory(memory)
            return {"action": "reselect_models"}
        elif option == "2":
            print("\n[INFO] Requesting model reselection in LLM Orchestrator workflow.\n")
            # Signal to the orchestrator that models should be reselected.
            # Persist this intent in orchestrator_memory.json so the workflow agent can see it.
            memory = load_memory()
            if memory:
                memory["review_action"] = "reselect_models"
                save_memory(memory)
            return {"action": "reselect_models"}
        elif option == "3":
            print("\n[INFO] Exiting program.\n")
            exit(0)
        else:
            print("Invalid input. Try again.")
            print("Invalid input. Enter 1 or 2.")


def load_master_memory():
    """Load master_memory.json from project root"""
def save_memory(memory_data):
    """Save memory back to orchestrator_memory.json"""
    script_dir = Path(__file__).parent
    master_memory_file = script_dir.parent / "master_memory.json"
    
    if not master_memory_file.exists():
        print(f"[ERROR] master_memory.json not found at: {master_memory_file}")
    memory_file = script_dir / "orchestrator_memory.json"
    with open(memory_file, "w", encoding="utf-8") as f:
        json.dump(memory_data, f, indent=2)


def main():
    memory = load_memory()
    if not memory:
        return None
    try:
        with open(master_memory_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] master_memory.json is corrupted (invalid JSON): {exc}")
        print(f"        Please delete or repair: {master_memory_file}")

    validation_dict = memory.get("validation_metrics", {})
    if not validation_dict:
        print("[ERROR] No validation metrics found inside orchestrator_memory.json.")
        return None

    # Print all model metrics
    print_model_metrics(validation_dict)

def save_master_memory(master_memory_data):
    """Save memory back to master_memory.json"""
    script_dir = Path(__file__).parent
    master_memory_file = script_dir.parent / "master_memory.json"
    with open(master_memory_file, "w", encoding="utf-8") as f:
        json.dump(master_memory_data, f, indent=2)
    # Ask if user is satisfied with the validation results
    satisfied = ask_yes_no("Are you satisfied with these results?")
    if satisfied == "y":
        # User picks the model to train on the full dataset → deployment follows automatically
        result = choose_model(validation_dict)
        if result and result.get("action") == "generate_full_training":
            selected_model = result.get("model")
            memory["selected_model_for_full_training"] = selected_model
            save_memory(memory)
            print(f"[INFO] Selected model '{selected_model}' saved to orchestrator_memory.json")
        return result
    else:
        # Not satisfied — user can only reselect models or exit.
        # The improvement agent is available AFTER full training + deployment, not here.
        return not_satisfied_menu()


def save_memory(memory_data):
    """Save memory back to orchestrator_memory.json"""
    script_dir = Path(__file__).parent
    memory_file = script_dir / "orchestrator_memory.json"
    with open(memory_file, "w", encoding="utf-8") as f:
        json.dump(memory_data, f, indent=2)


def main():
    memory = load_memory()
    if not memory:
        return None

    validation_dict = memory.get("validation_metrics", {})
    if not validation_dict:
        print("[ERROR] No validation metrics found inside orchestrator_memory.json.")
        return None

    # Print all model metrics
    print_model_metrics(validation_dict)

    # Ask if user is satisfied
    satisfied = ask_yes_no("Are you satisfied with these results?")
    if satisfied == "y":
        result = choose_model(validation_dict)
        # Save the selected model directly to orchestrator_memory.json
        if result and result.get("action") == "generate_full_training":
            selected_model = result.get("model")
            memory["selected_model_for_full_training"] = selected_model
            save_memory(memory)
            print(f"[INFO] Selected model '{selected_model}' saved to orchestrator_memory.json")
            return result
        elif result:
            # User selected a model but chose not to generate full training code
            # Still save the selection (optional, or clear it)
            memory["selected_model_for_full_training"] = None
            save_memory(memory)
        return result
    else:
        menu_result = improvement_menu()
        return menu_result


if __name__ == "__main__":
    main()
