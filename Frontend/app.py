import json
import io
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1] / "backend"
PREPROCESSING_DIR = PROJECT_ROOT / "Pre Processing Agent"
LLM_ORCHESTRATOR_DIR = PROJECT_ROOT / "LLM Orchestrator"
IMPROVEMENT_DIR = PROJECT_ROOT / "Improvement Agent"


def _add_backend_to_path():
    """Ensure backend packages can be imported without modifying backend code."""
    import sys

    for p in [str(PROJECT_ROOT), str(PREPROCESSING_DIR), str(LLM_ORCHESTRATOR_DIR), str(IMPROVEMENT_DIR)]:
        if p not in sys.path:
            sys.path.insert(0, p)


_add_backend_to_path()

# Backend imports (do not modify backend files)
from master_orchestrator import MasterOrchestratorAgent  # type: ignore[import]
from model_recommender import (  # type: ignore[import]
    parse_model_names,
)


class StreamlitOutputCapture:
    """Capture stdout/stderr and display in Streamlit in real-time."""
    def __init__(self, container):
        self.container = container
        self.output_buffer = io.StringIO()
        self.output_text = ""
    
    def __enter__(self):
        self.old_stdout = sys.stdout
        self.old_stderr = sys.stderr
        sys.stdout = self
        sys.stderr = self
        return self
    
    def __exit__(self, *args):
        sys.stdout = self.old_stdout
        sys.stderr = self.old_stderr
        # Display captured output in Streamlit
        output_text = self.output_buffer.getvalue()
        if output_text:
            self.container.code(output_text, language=None)
    
    def write(self, text):
        self.output_buffer.write(text)
        self.output_text += text
        # Update display in real-time (Streamlit will batch updates)
        if len(self.output_text) > 0:
            # Show last 5000 chars to avoid overwhelming the UI
            display_text = self.output_text[-5000:] if len(self.output_text) > 5000 else self.output_text
            self.container.code(display_text, language=None)
        self.old_stdout.write(text)  # Also write to real stdout for debugging
    
    def flush(self):
        pass


def run_backend_initial_workflow(
    csv_path: Path,
    target_column: str,
    dataset_context: str,
    output_container
) -> dict:
    """
    Run the initial backend workflow (preprocessing + recommendations).
    Stops before model selection to allow UI interaction.
    """
    # Import LLM orchestrator workflow agent (after path setup)
    from llm_orchestrator_workflow_agent import LLMOrchestratorWorkflowAgent  # type: ignore[import]
    
    # Initialize master orchestrator
    orchestrator = MasterOrchestratorAgent(output_dir=PROJECT_ROOT)
    
    # Capture output
    with StreamlitOutputCapture(output_container):
        # Step 1: Run preprocessing agent
        prep_report = orchestrator.run_preprocessing_agent(
            csv_path=csv_path,
            target_column=target_column,
            context=dataset_context
        )
        
        # Step 2: Run LLM orchestrator (this will generate recommendations)
        orchestrator.save_memory(orchestrator.output_dir / "master_memory.json")
        
        llm_agent = LLMOrchestratorWorkflowAgent(
            master_memory_path=orchestrator.output_dir / "master_memory.json",
            output_dir=LLM_ORCHESTRATOR_DIR
        )
        
        # Load master memory
        llm_agent.load_master_memory()
        
        # Generate model recommendations
        recommendations_text = llm_agent.generate_model_recommendations()
        
        # Parse recommended models
        recommended_models = parse_model_names(recommendations_text)
        
        # Save orchestrator state for continuation
        llm_agent.save_memory()
        
        # Get preprocessing plan from master memory (try orchestrator memory first, then load from file)
        preprocessing_plan = orchestrator.memory.preprocessing_plan
        preprocessing_plan_path = orchestrator.memory.preprocessing_plan_path
        
        # Fallback: Load from master_memory.json if not in orchestrator memory
        if not preprocessing_plan:
            master_memory_path = orchestrator.output_dir / "master_memory.json"
            if master_memory_path.exists():
                try:
                    with master_memory_path.open("r", encoding="utf-8") as f:
                        master_memory = json.load(f)
                    preprocessing = master_memory.get("preprocessing", {})
                    preprocessing_plan = preprocessing.get("plan", {})
                    plan_path_str = preprocessing.get("plan_path")
                    if plan_path_str:
                        preprocessing_plan_path = Path(plan_path_str)
                except Exception:
                    pass
        
        return {
            "reasoning": recommendations_text,
            "recommended_models": recommended_models,
            "output_text": "",
            "needs_model_selection": True,
            "preprocessing_plan": preprocessing_plan,
            "preprocessing_plan_path": str(preprocessing_plan_path) if preprocessing_plan_path else None
        }


def continue_backend_workflow(
    selected_models_for_validation: list[str],
    output_container
) -> dict:
    """
    Continue the backend workflow from where it left off (after model selection).
    Only runs validation code generation, skipping preprocessing.
    """
    # Import LLM orchestrator workflow agent (after path setup)
    from llm_orchestrator_workflow_agent import LLMOrchestratorWorkflowAgent  # type: ignore[import]
    
    master_memory_path = PROJECT_ROOT / "master_memory.json"
    
    if not master_memory_path.exists():
        raise FileNotFoundError("Master memory not found. Please run initial workflow first.")
    
    # Capture output
    with StreamlitOutputCapture(output_container):
        llm_agent = LLMOrchestratorWorkflowAgent(
            master_memory_path=master_memory_path,
            output_dir=LLM_ORCHESTRATOR_DIR
        )
        
        # Load master memory (which includes the recommendations we generated)
        llm_agent.load_master_memory()
        
        # Load orchestrator memory to restore structured recommendations and other state
        orchestrator_memory_path = LLM_ORCHESTRATOR_DIR / "orchestrator_memory.json"
        if orchestrator_memory_path.exists():
            llm_agent.load_memory(orchestrator_memory_path)
        else:
            # Ensure we persist an absolute master memory path for downstream scripts
            llm_agent.memory.master_memory_path = master_memory_path
            llm_agent.save_memory()
        
        validation_metrics: dict = {}
        last_error: Exception | None = None
        
        # Try a couple of self-healing passes: regenerate code then run it.
        for attempt in range(2):
            try:
                # User has selected models - continue workflow
                # Manually set selected models in memory (bypassing input() call)
                llm_agent.memory.selected_models_for_validation = selected_models_for_validation
                llm_agent.save_memory()
                
                # Continue with validation code generation
                llm_agent.generate_validation_code()
                llm_agent.run_validation_code()
                
                # Reload orchestrator memory to ensure we have the latest validation metrics
                # The run_validation_code() method updates the memory file, so we need to reload it
                if orchestrator_memory_path.exists():
                    llm_agent.load_memory(orchestrator_memory_path)
                
                # Get validation metrics from the reloaded memory
                validation_metrics = llm_agent.memory.validation_metrics or {}
                
                if validation_metrics:
                    break  # success
                else:
                    print(f"[WARN] Attempt {attempt + 1}: no validation metrics captured, retrying regeneration...")
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                print(f"[ERROR] Attempt {attempt + 1} failed during validation generation/run: {exc}")
        
        # If still no metrics, raise a concise, actionable error for the UI
        if not validation_metrics:
            hint = (
                "Validation generation/execution did not produce metrics. "
                "Check backend output above for the first traceback. "
                "Try re-running with fewer models or ensure the dataset columns "
                "match the preprocessing report."
            )
            if last_error:
                raise RuntimeError(f"{hint} Last error: {last_error}") from last_error
            raise RuntimeError(hint)
        
        # Debug: Print what we got
        print(f"\n[DEBUG] Validation metrics keys: {list(validation_metrics.keys()) if validation_metrics else 'None'}")
        print(f"[DEBUG] Selected models: {selected_models_for_validation}")
        
        return {
            "reasoning": llm_agent.memory.model_recommendations or "",
            "recommended_models": llm_agent.memory.recommended_models,
            "output_text": "",
            "needs_model_selection": False,
            "validation_metrics": validation_metrics
        }


def generate_training_code(
    model_name: str,
    output_container
) -> dict:
    """
    Generate full training code for the selected model.
    """
    # Import LLM orchestrator workflow agent (after path setup)
    from llm_orchestrator_workflow_agent import LLMOrchestratorWorkflowAgent  # type: ignore[import]
    
    master_memory_path = PROJECT_ROOT / "master_memory.json"
    
    if not master_memory_path.exists():
        raise FileNotFoundError("Master memory not found. Please run initial workflow first.")
    
    # Capture output
    with StreamlitOutputCapture(output_container):
        llm_agent = LLMOrchestratorWorkflowAgent(
            master_memory_path=master_memory_path,
            output_dir=LLM_ORCHESTRATOR_DIR
        )
        
        # Load master memory
        llm_agent.load_master_memory()
        
        # Load orchestrator memory to restore state
        orchestrator_memory_path = LLM_ORCHESTRATOR_DIR / "orchestrator_memory.json"
        if orchestrator_memory_path.exists():
            llm_agent.load_memory(orchestrator_memory_path)
        
        # Get validation code path for the selected model to determine output filename
        validation_code_path = None
        if model_name in llm_agent.memory.validation_metrics:
            validation_code_path = llm_agent.memory.validation_metrics[model_name].get("code_path")
        
        # Generate full training code for the selected model
        llm_agent.generate_full_training_code(model_name)
        
        # Save the selected model in memory
        llm_agent.memory.selected_model_for_full_training = model_name
        llm_agent.save_memory()
        
        # Construct the expected file path - try multiple approaches
        training_code_path = None
        
        # Approach 1: Use validation code path if available
        if validation_code_path:
            code_path = Path(validation_code_path)
            filename = code_path.stem + "_full.py"
            potential_path = LLM_ORCHESTRATOR_DIR / "full_training" / filename
            if potential_path.exists():
                training_code_path = potential_path
        
        # Approach 2: Search for the most recent _full.py file in full_training directory
        if not training_code_path or not training_code_path.exists():
            full_training_dir = LLM_ORCHESTRATOR_DIR / "full_training"
            if full_training_dir.exists():
                matching_files = list(full_training_dir.glob("*_full.py"))
                if matching_files:
                    # Use the most recently created one
                    training_code_path = max(matching_files, key=lambda p: p.stat().st_mtime)
        
        # Approach 3: Try using generated_code_paths from memory
        if (not training_code_path or not training_code_path.exists()) and llm_agent.memory.generated_code_paths:
            # Use the first generated code path to construct filename
            first_code_path = Path(llm_agent.memory.generated_code_paths[0])
            filename = first_code_path.stem + "_full.py"
            potential_path = LLM_ORCHESTRATOR_DIR / "full_training" / filename
            if potential_path.exists():
                training_code_path = potential_path
        
        # Approach 4: Try to find any file with model name in it (case-insensitive)
        if not training_code_path or not training_code_path.exists():
            full_training_dir = LLM_ORCHESTRATOR_DIR / "full_training"
            if full_training_dir.exists():
                # Normalize model name for search
                model_name_normalized = model_name.lower().replace(" ", "_")
                matching_files = [f for f in full_training_dir.glob("*_full.py") 
                                if model_name_normalized in f.stem.lower()]
                if matching_files:
                    training_code_path = max(matching_files, key=lambda p: p.stat().st_mtime)
        
        return {
            "model_name": model_name,
            "success": True,
            "training_code_path": str(training_code_path.resolve()) if training_code_path and training_code_path.exists() else None
        }


def run_improvement_agent(
    model_name: str,
    output_container,
    validation_metrics_from_session: dict = None
) -> dict:
    """
    Run the improvement agent workflow for the selected model.
    
    Args:
        model_name: Name of the model to improve
        output_container: Streamlit container for displaying output
        validation_metrics_from_session: Validation metrics from session state (preferred source)
        
    Returns:
        Dictionary with improvement results
    """
    from improvement_workflow_agent import ImprovementWorkflowAgent  # type: ignore[import]
    
    master_memory_path = PROJECT_ROOT / "master_memory.json"
    
    if not master_memory_path.exists():
        raise FileNotFoundError("Master memory not found. Please run initial workflow first.")
    
    # Load master memory to extract model info
    with master_memory_path.open("r", encoding="utf-8") as f:
        master_memory = json.load(f)
    
    # Prefer validation metrics from session state (most up-to-date)
    if validation_metrics_from_session:
        validation_metrics_full = validation_metrics_from_session
        selected_models_for_validation = list(validation_metrics_full.keys())
    else:
        # Fallback to master memory
        llm_orch = master_memory.get("llm_orchestrator", {})
        orch_mem = llm_orch.get("orchestrator_memory", {})
        selected_models_for_validation = orch_mem.get("selected_models_for_validation", [])
        validation_metrics_full = orch_mem.get("validation_metrics", {})
    
    # Normalize model names for flexible matching (case-insensitive, ignore spaces)
    def normalize_model_name(name):
        """Normalize model name for comparison."""
        if not name:
            return ""
        return name.lower().replace(" ", "").replace("_", "").replace("-", "")
    
    normalized_input = normalize_model_name(model_name)
    
    # Try to find matching model in selected_models_for_validation
    matched_model = None
    for valid_model in selected_models_for_validation:
        if normalize_model_name(valid_model) == normalized_input:
            matched_model = valid_model
            break
    
    # If not found, try to find in validation_metrics_full keys
    if not matched_model:
        for valid_model in validation_metrics_full.keys():
            if normalize_model_name(valid_model) == normalized_input:
                matched_model = valid_model
                break
    
    if not matched_model:
        # Provide helpful error message with available models
        available_models = list(validation_metrics_full.keys()) if validation_metrics_full else selected_models_for_validation
        available_str = ", ".join(available_models) if available_models else "none"
        raise ValueError(
            f"Model '{model_name}' not found in validated models.\n"
            f"Available models: {available_str}\n"
            f"Please select one of the available models."
        )
    
    # Use the matched model name (which might have different formatting)
    actual_model_name = matched_model
    
    # Capture output
    with StreamlitOutputCapture(output_container):
        improvement_agent = ImprovementWorkflowAgent(
            master_memory_path=master_memory_path,
            output_dir=IMPROVEMENT_DIR
        )
        
        # Manually set up the memory to bypass interactive input
        # Extract dataset context
        improvement_agent.memory.dataset_context = master_memory.get("context_of_dataset")
        
        # Extract preprocessing report path
        preprocessing = master_memory.get("preprocessing", {})
        report_path_str = preprocessing.get("report_path")
        if report_path_str:
            improvement_agent.memory.dataset_report_path = Path(report_path_str)
        
        # Set the selected model and extract its validation info
        # Use the actual matched model name (which might have different formatting)
        improvement_agent.memory.model_name = actual_model_name
        
        # Extract validation info - handle both dict format (from session) and nested format
        if actual_model_name in validation_metrics_full:
            info = validation_metrics_full[actual_model_name]
            # Handle both formats: direct dict or nested with "metrics" key
            if isinstance(info, dict):
                if "metrics" in info:
                    # Nested format: {"model_name": {"metrics": {...}, "code_path": "..."}}
                    improvement_agent.memory.validation_metrics = info.get("metrics", {}) or {}
                    code_path_str = info.get("code_path")
                else:
                    # Direct format: {"model_name": {"MAE": ..., "MSE": ...}}
                    improvement_agent.memory.validation_metrics = info
                    code_path_str = None
                
                # Set validation code path
                if code_path_str:
                    improvement_agent.memory.validation_code_path = Path(code_path_str)
                else:
                    # Try to find validation code path from orchestrator memory or generated paths
                    orchestrator_memory_path = LLM_ORCHESTRATOR_DIR / "orchestrator_memory.json"
                    if orchestrator_memory_path.exists():
                        try:
                            with orchestrator_memory_path.open("r", encoding="utf-8") as f:
                                orch_mem = json.load(f)
                            orch_validation_metrics = orch_mem.get("validation_metrics", {})
                            if actual_model_name in orch_validation_metrics:
                                orch_code_path = orch_validation_metrics[actual_model_name].get("code_path")
                                if orch_code_path:
                                    improvement_agent.memory.validation_code_path = Path(orch_code_path)
                        except Exception:
                            pass
            else:
                raise ValueError(f"Unexpected format for validation metrics: {type(info)}")
        else:
            raise ValueError(f"Validation metrics for {actual_model_name} not found in validation_metrics_full")
        
        # Track files in file_history
        try:
            improvement_agent.memory.file_history["master_memory"] = str(master_memory_path.resolve())
            if improvement_agent.memory.dataset_report_path:
                improvement_agent.memory.file_history["dataset_report"] = str(
                    improvement_agent.memory.dataset_report_path.resolve()
                )
            if improvement_agent.memory.validation_code_path:
                improvement_agent.memory.file_history["validation_code"] = str(
                    improvement_agent.memory.validation_code_path.resolve()
                )
        except Exception:
            pass
        
        # Validate required fields
        if not improvement_agent.memory.model_name:
            raise ValueError("Model selection failed")
        if not improvement_agent.memory.validation_metrics:
            raise ValueError(f"Validation metrics for {actual_model_name} not found in master memory")
        if not improvement_agent.memory.dataset_context:
            raise ValueError("context_of_dataset not found in master memory")
        if not improvement_agent.memory.dataset_report_path:
            raise ValueError("preprocessing.report_path not found in master memory")
        if not improvement_agent.memory.validation_code_path:
            raise ValueError(f"Validation code path for {actual_model_name} not found in master memory")
        
        # Save intermediate memory
        improvement_agent.save_memory()
        
        # Generate improvement steps
        improvement_steps = improvement_agent.generate_improvement_steps()
        
        # Generate improved code
        improved_code_path = improvement_agent.run_improved_code_generation()
        
        # Run improved code
        improved_metrics = improvement_agent.run_improved_code_runner()
        
        # Save final memory
        improvement_agent.save_memory()
        
        return {
            "model_name": actual_model_name,  # Return the actual matched model name
            "improvement_steps": improvement_steps,
            "improved_validation_code_path": str(improved_code_path) if improved_code_path else None,
            "improved_validation_metrics": improved_metrics or {},
            "success": True
        }


def save_uploaded_file(uploaded_file) -> Path:
    """Persist the uploaded CSV into the backend Datasets folder."""
    datasets_dir = PROJECT_ROOT / "Datasets"
    datasets_dir.mkdir(parents=True, exist_ok=True)

    # Use original filename; if missing, fall back to a generic one.
    filename = uploaded_file.name or "uploaded_dataset.csv"
    target_path = datasets_dir / filename

    with target_path.open("wb") as f:
        f.write(uploaded_file.getbuffer())

    return target_path


def main():
    st.set_page_config(page_title="IntelliModel Reasoning UI", layout="centered")

    st.title("IntelliModel")

    # Initialize session state
    if "reasoning" not in st.session_state:
        st.session_state["reasoning"] = None
    if "recommended_models" not in st.session_state:
        st.session_state["recommended_models"] = []
    if "csv_path" not in st.session_state:
        st.session_state["csv_path"] = None
    if "target_column" not in st.session_state:
        st.session_state["target_column"] = ""
    if "dataset_context" not in st.session_state:
        st.session_state["dataset_context"] = ""
    if "stage" not in st.session_state:
        # Stages: "upload" -> "select_validation_models" -> "generating"
        st.session_state["stage"] = "upload"
    if "selected_validation_models" not in st.session_state:
        st.session_state["selected_validation_models"] = None
    if "backend_output" not in st.session_state:
        st.session_state["backend_output"] = ""
    if "training_code_path" not in st.session_state:
        st.session_state["training_code_path"] = None
    if "validation_metrics" not in st.session_state:
        st.session_state["validation_metrics"] = {}
    if "improvement_stage" not in st.session_state:
        st.session_state["improvement_stage"] = None  # None, "select_model", "improving", "completed"
    if "improvement_steps" not in st.session_state:
        st.session_state["improvement_steps"] = None
    if "improved_validation_metrics" not in st.session_state:
        st.session_state["improved_validation_metrics"] = {}
    if "improved_validation_code_path" not in st.session_state:
        st.session_state["improved_validation_code_path"] = None
    if "preprocessing_plan" not in st.session_state:
        st.session_state["preprocessing_plan"] = None
    if "preprocessing_plan_path" not in st.session_state:
        st.session_state["preprocessing_plan_path"] = None

    # --- User inputs ---
    uploaded_file = st.file_uploader("Upload your CSV dataset", type=["csv"])
    target_column = st.text_input("Target column name")
    dataset_context = st.text_area("Describe your dataset and prediction goal")

    # Terminal output display area
    terminal_container = st.container()
    with terminal_container:
        st.subheader("Backend Output")
        output_display = st.empty()

    # Separate button for uploading data and triggering backend reasoning
    upload_button = st.button("Upload data")

    # Stage: upload data and run reasoning
    if upload_button and st.session_state["stage"] == "upload":
        if not uploaded_file:
            st.error("Please upload a CSV file.")
            return
        if not target_column.strip():
            st.error("Please provide the target column name.")
            return
        if not dataset_context.strip():
            st.error("Please provide some context for the dataset.")
            return

        csv_path = save_uploaded_file(uploaded_file)
        
        with st.spinner("Running backend workflow..."):
            try:
                result = run_backend_initial_workflow(
                    csv_path=csv_path,
                    target_column=target_column.strip(),
                    dataset_context=dataset_context.strip(),
                    output_container=output_display
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"Backend workflow failed: {exc}")
                return

        # Store results
        st.session_state["reasoning"] = result["reasoning"]
        st.session_state["recommended_models"] = result["recommended_models"]
        st.session_state["csv_path"] = str(csv_path)
        st.session_state["target_column"] = target_column.strip()
        st.session_state["dataset_context"] = dataset_context.strip()
        st.session_state["stage"] = "select_validation_models"
        st.session_state["preprocessing_plan"] = result.get("preprocessing_plan")
        st.session_state["preprocessing_plan_path"] = result.get("preprocessing_plan_path")

    # --- Display preprocessing steps ---
    if st.session_state["stage"] != "upload":
        # Try to get preprocessing plan from session state or load from file
        preprocessing_plan = st.session_state.get("preprocessing_plan")
        preprocessing_plan_path = st.session_state.get("preprocessing_plan_path")
        
        # If plan is not in session state but path is available, try to load from file
        if not preprocessing_plan and preprocessing_plan_path:
            plan_path = Path(preprocessing_plan_path)
            if plan_path.exists():
                try:
                    with plan_path.open("r", encoding="utf-8") as f:
                        preprocessing_plan = json.load(f)
                    st.session_state["preprocessing_plan"] = preprocessing_plan
                except Exception:
                    pass
        
        # Also try to load from master_memory.json as fallback
        if not preprocessing_plan:
            master_memory_path = PROJECT_ROOT / "master_memory.json"
            if master_memory_path.exists():
                try:
                    with master_memory_path.open("r", encoding="utf-8") as f:
                        master_memory = json.load(f)
                    preprocessing = master_memory.get("preprocessing", {})
                    preprocessing_plan = preprocessing.get("plan", {})
                    if preprocessing_plan:
                        st.session_state["preprocessing_plan"] = preprocessing_plan
                    plan_path_str = preprocessing.get("plan_path")
                    if plan_path_str and not preprocessing_plan_path:
                        st.session_state["preprocessing_plan_path"] = plan_path_str
                        preprocessing_plan_path = plan_path_str
                except Exception:
                    pass
        
        if preprocessing_plan:
            st.subheader("📋 Preprocessing Steps")
            preprocessing_steps = preprocessing_plan.get("preprocessing_steps", [])
            
            if preprocessing_steps:
                with st.expander("View Preprocessing Steps", expanded=True):
                    for i, step in enumerate(preprocessing_steps, 1):
                        step_name = step.get("step", "Unknown step")
                        step_reason = step.get("reason", "")
                        step_columns = step.get("columns", [])
                        
                        st.markdown(f"**{i}. {step_name}**")
                        if step_reason:
                            st.markdown(f"   *Reason: {step_reason}*")
                        if step_columns:
                            st.markdown(f"   *Columns: {', '.join(step_columns)}*")
                        st.markdown("---")
            
            # Download button for preprocessing steps
            preprocessing_steps_text = json.dumps(preprocessing_plan, indent=2)
            st.download_button(
                label="📥 Download Preprocessing Steps (JSON)",
                data=preprocessing_steps_text,
                file_name="preprocessing_steps.json",
                mime="application/json",
                key="download_preprocessing_steps"
            )
            
            # Also try to download from file if path is available
            if st.session_state.get("preprocessing_plan_path"):
                plan_path = Path(st.session_state["preprocessing_plan_path"])
                if plan_path.exists():
                    try:
                        with plan_path.open("r", encoding="utf-8") as f:
                            plan_file_contents = f.read()
                        st.download_button(
                            label="📥 Download Preprocessing Plan File",
                            data=plan_file_contents,
                            file_name=plan_path.name,
                            mime="application/json",
                            key="download_preprocessing_plan_file"
                        )
                    except Exception as e:
                        st.warning(f"Could not read preprocessing plan file: {e}")
            else:
                st.info("No preprocessing steps available in the plan.")
        
        st.divider()
    
    # --- Display reasoning and model selection UI ---
    if st.session_state.get("reasoning"):
        st.subheader("Model Recommendations")
        st.write(st.session_state["reasoning"])

        # Model selection for validation testing
        if st.session_state["stage"] == "select_validation_models":
            st.subheader("SELECT MODELS FOR VALIDATION TESTING")
            st.write("\nRecommended models:")
            
            recommended = st.session_state["recommended_models"]
            selected_indices = st.multiselect(
                "Select models for validation testing:",
                options=list(range(len(recommended))),
                format_func=lambda i: f"{i+1}. {recommended[i]}",
                key="validation_model_selection"
            )
            
            select_validation_button = st.button("Confirm Selection")
            
            if select_validation_button:
                if not selected_indices:
                    st.error("Please select at least one model for validation testing.")
                else:
                    selected_models = [recommended[i] for i in selected_indices]
                    st.session_state["selected_validation_models"] = selected_models
                    
                    # Continue backend workflow with selected models (without restarting)
                    with st.spinner("Generating validation code..."):
                        try:
                            result = continue_backend_workflow(
                                selected_models_for_validation=selected_models,
                                output_container=output_display
                            )
                            st.session_state["stage"] = "generating"
                            validation_metrics = result.get("validation_metrics", {})
                            # Fallback: try loading validation metrics from orchestrator memory if empty
                            if not validation_metrics:
                                orchestrator_memory_path = LLM_ORCHESTRATOR_DIR / "orchestrator_memory.json"
                                if orchestrator_memory_path.exists():
                                    try:
                                        with orchestrator_memory_path.open("r", encoding="utf-8") as f:
                                            orch_mem = json.load(f)
                                        validation_metrics = orch_mem.get("validation_metrics", {})
                                    except Exception:
                                        pass
                            # Persist the fallback (if found) so UI can render metrics
                            st.session_state["validation_metrics"] = validation_metrics
                            
                            # Debug info
                            if validation_metrics:
                                st.info(f"📊 Metrics received for {len(validation_metrics)} model(s): {', '.join(validation_metrics.keys())}")
                            else:
                                st.warning("⚠️ No validation metrics received. Check backend output for errors.")
                            
                            st.success(f"Selected {len(selected_models)} model(s) for validation: {', '.join(selected_models)}")
                        except Exception as exc:  # noqa: BLE001
                            st.error(f"Validation code generation failed: {exc}")

        # Display evaluation metrics if available (only after validation completes)
        if st.session_state["stage"] == "generating" and st.session_state.get("validation_metrics"):
            st.subheader("Evaluation Metrics")
            metrics = st.session_state["validation_metrics"]
            
            # Show how many models we have metrics for
            if metrics:
                st.info(f"📊 Displaying metrics for {len(metrics)} model(s): {', '.join(metrics.keys())}")
            else:
                st.warning("⚠️ No validation metrics available. Check backend output for errors.")
            
            if metrics:
                # Create columns for each model's metrics
                for model_name, model_data in metrics.items():
                    model_metrics = model_data.get("metrics", {})
                    if model_metrics:
                        with st.expander(f"📊 {model_name}", expanded=True):
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                if "MAE" in model_metrics:
                                    st.markdown('<div style="font-size: 0.85rem;"><strong>MAE (Mean Absolute Error)</strong></div>', unsafe_allow_html=True)
                                    st.markdown(f'<div style="font-size: 1.1rem; font-weight: 600;">{model_metrics["MAE"]:.4f}</div>', unsafe_allow_html=True)
                            with col2:
                                if "MSE" in model_metrics:
                                    st.markdown('<div style="font-size: 0.85rem;"><strong>MSE (Mean Squared Error)</strong></div>', unsafe_allow_html=True)
                                    st.markdown(f'<div style="font-size: 1.1rem; font-weight: 600;">{model_metrics["MSE"]:.4f}</div>', unsafe_allow_html=True)
                            with col3:
                                if "R2" in model_metrics:
                                    st.markdown('<div style="font-size: 0.85rem;"><strong>R² (R-squared)</strong></div>', unsafe_allow_html=True)
                                    st.markdown(f'<div style="font-size: 1.1rem; font-weight: 600;">{model_metrics["R2"]:.4f}</div>', unsafe_allow_html=True)
                    else:
                        st.info(f"No metrics available for {model_name} yet.")
            else:
                st.info("Validation metrics will appear here after validation code execution completes.")
        
        # Ask user which model they want for training
        if st.session_state["stage"] == "generating":
            # Get available models from validation metrics
            available_models = []
            if st.session_state.get("validation_metrics"):
                available_models = list(st.session_state["validation_metrics"].keys())
            
            if available_models:
                model_for_training = st.selectbox(
                    "Select Model for Full Training",
                    options=available_models,
                    help="Select a model from the validated models to generate full training code.",
                    key="model_for_training",
                )
            else:
                model_for_training = st.text_input(
                    "Enter Model for training",
                    help=(
                        "Input must be the model name only, exactly as it appears in the reasoning "
                        "text (for example: 'Random Forest Regressor'). Do not enter numbers, "
                        "indexes like 'Model 1', or any extra text. Enter a single model name only."
                    ),
                    key="model_for_training",
                )

            # Separate button for selecting models, placed below the user input
            select_models_button = st.button("Generate Training Code")

            if select_models_button:
                if not model_for_training.strip():
                    st.error("Please enter the model name for training before continuing.")
                else:
                    # Generate full training code
                    with st.spinner(f"Generating full training code for {model_for_training}..."):
                        try:
                            result = generate_training_code(
                                model_name=model_for_training.strip(),
                                output_container=output_display
                            )
                            st.session_state["training_code_path"] = result.get("training_code_path")
                            st.success(f"Full training code generated successfully for {model_for_training}!")
                            
                            # Immediately try to show download button after generation
                            training_path = result.get("training_code_path")
                            if training_path:
                                training_file = Path(training_path)
                                if training_file.exists():
                                    try:
                                        with training_file.open("r", encoding="utf-8") as f:
                                            file_contents = f.read()
                                        st.download_button(
                                            label="📥 Download Training Code",
                                            data=file_contents,
                                            file_name=training_file.name,
                                            mime="text/x-python",
                                            key="download_training_code_immediate"
                                        )
                                    except Exception as e:
                                        st.warning(f"Could not read file immediately: {e}")
                        except Exception as exc:  # noqa: BLE001
                            st.error(f"Training code generation failed: {exc}")
            
            # Show download button if training code path is available (persists after generation)
            # First, try to find the file even if path isn't in session state
            training_file_path = None
            
            # Check if we have a path in session state
            if st.session_state.get("training_code_path"):
                training_file_path = Path(st.session_state["training_code_path"])
                if not training_file_path.exists():
                    training_file_path = None
            
            # Approach 2: Try to find the most recent file in full_training directory
            if not training_file_path or not training_file_path.exists():
                full_training_dir = LLM_ORCHESTRATOR_DIR / "full_training"
                if full_training_dir.exists():
                    matching_files = list(full_training_dir.glob("*_full.py"))
                    if matching_files:
                        # Use the most recently created one
                        training_file_path = max(matching_files, key=lambda p: p.stat().st_mtime)
                        st.session_state["training_code_path"] = str(training_file_path.resolve())
            
            # Approach 3: Try to construct from generated_code_paths if available
            if (not training_file_path or not training_file_path.exists()) and st.session_state.get("validation_metrics"):
                # Try to get generated_code_paths from orchestrator memory
                orchestrator_memory_path = LLM_ORCHESTRATOR_DIR / "orchestrator_memory.json"
                if orchestrator_memory_path.exists():
                    try:
                        with orchestrator_memory_path.open("r", encoding="utf-8") as f:
                            memory_data = json.load(f)
                        generated_paths = memory_data.get("generated_code_paths", [])
                        if generated_paths:
                            # Use the first path to construct filename
                            first_code_path = Path(generated_paths[0])
                            filename = first_code_path.stem + "_full.py"
                            potential_path = LLM_ORCHESTRATOR_DIR / "full_training" / filename
                            if potential_path.exists():
                                training_file_path = potential_path
                                st.session_state["training_code_path"] = str(training_file_path.resolve())
                    except Exception:
                        pass
            
            # Also try to construct path from validation metrics if available
            if (not training_file_path or not training_file_path.exists()) and st.session_state.get("validation_metrics"):
                # Get the selected model name from the widget value (model_for_training is the widget value)
                selected_model = model_for_training
                if selected_model and selected_model in st.session_state["validation_metrics"]:
                    validation_code_path = st.session_state["validation_metrics"][selected_model].get("code_path")
                    if validation_code_path:
                        code_path = Path(validation_code_path)
                        filename = code_path.stem + "_full.py"
                        potential_path = LLM_ORCHESTRATOR_DIR / "full_training" / filename
                        if potential_path.exists():
                            training_file_path = potential_path
                            st.session_state["training_code_path"] = str(training_file_path.resolve())
            
            # Show download button if we found a file
            if training_file_path and training_file_path.exists():
                try:
                    with training_file_path.open("r", encoding="utf-8") as f:
                        file_contents = f.read()
                    st.download_button(
                        label="📥 Download Training Code",
                        data=file_contents,
                        file_name=training_file_path.name,
                        mime="text/x-python",
                        key="download_training_code"
                    )
                except Exception as e:
                    st.error(f"Error reading training code file: {e}")
                    st.info(f"File path: {training_file_path}")
            else:
                # Try to find any training code files in the full_training directory
                full_training_dir = LLM_ORCHESTRATOR_DIR / "full_training"
                if full_training_dir.exists():
                    # Look for any Python files (not just *_full.py)
                    all_py_files = list(full_training_dir.glob("*.py"))
                    if all_py_files:
                        # Show download buttons for all available training code files
                        st.info("📁 Training code files available:")
                        for py_file in sorted(all_py_files, key=lambda p: p.stat().st_mtime, reverse=True):
                            try:
                                with py_file.open("r", encoding="utf-8") as f:
                                    file_contents = f.read()
                                st.download_button(
                                    label=f"📥 Download {py_file.name}",
                                    data=file_contents,
                                    file_name=py_file.name,
                                    mime="text/x-python",
                                    key=f"download_training_{py_file.stem}"
                                )
                            except Exception as e:
                                st.warning(f"Could not read {py_file.name}: {e}")
                    else:
                        # No files found, show simple message
                        st.info("💡 Training code will be available in the backend folder after generation. Check: `backend/LLM Orchestrator/full_training/`")
                else:
                    # Directory doesn't exist, show simple message
                    st.info("💡 Training code will be available in the backend folder after generation. Check: `backend/LLM Orchestrator/full_training/`")
        
        # --- Improvement Agent Section ---
        if st.session_state["stage"] == "generating" and st.session_state.get("validation_metrics"):
            st.divider()
            st.subheader("🔧 Model Improvement (Optional)")
            st.write("Improve a validated model's performance using ML best practices.")
            
            # Get available models from validation metrics
            available_models_for_improvement = list(st.session_state["validation_metrics"].keys())
            
            if available_models_for_improvement:
                if st.session_state["improvement_stage"] is None:
                    # Stage 1: Select model for improvement
                    model_for_improvement = st.selectbox(
                        "Select Model to Improve",
                        options=available_models_for_improvement,
                        help="Select a validated model to improve its performance.",
                        key="model_for_improvement_selectbox",
                    )
                    
                    run_improvement_button = st.button("Run Improvement Agent")
                    
                    if run_improvement_button:
                        st.session_state["improvement_stage"] = "improving"
                        st.session_state["selected_model_for_improvement"] = model_for_improvement
                        st.rerun()
                
                elif st.session_state["improvement_stage"] == "improving":
                    # Stage 2: Running improvement
                    model_for_improvement = st.session_state.get("selected_model_for_improvement")
                    if model_for_improvement:
                        with st.spinner(f"Running improvement agent for {model_for_improvement}..."):
                            try:
                                result = run_improvement_agent(
                                    model_name=model_for_improvement,
                                    output_container=output_display,
                                    validation_metrics_from_session=st.session_state.get("validation_metrics", {})
                                )
                                
                                st.session_state["improvement_steps"] = result.get("improvement_steps")
                                st.session_state["improved_validation_code_path"] = result.get("improved_validation_code_path")
                                
                                # Store improved metrics
                                improved_metrics = result.get("improved_validation_metrics", {})
                                st.session_state["improved_validation_metrics"] = improved_metrics
                                
                                # Also try to load from improvement memory file if metrics are empty
                                if not improved_metrics:
                                    improvement_memory_path = IMPROVEMENT_DIR / "improvement_memory.json"
                                    if improvement_memory_path.exists():
                                        try:
                                            with improvement_memory_path.open("r", encoding="utf-8") as f:
                                                improvement_memory = json.load(f)
                                            loaded_metrics = improvement_memory.get("improved_validation_metrics", {})
                                            if loaded_metrics:
                                                st.session_state["improved_validation_metrics"] = loaded_metrics
                                        except Exception:
                                            pass
                                
                                st.session_state["improvement_stage"] = "completed"
                                st.success(f"✅ Improvement agent completed for {model_for_improvement}!")
                                
                                # Show a quick summary of improved metrics
                                if st.session_state.get("improved_validation_metrics"):
                                    st.info("📊 Improved metrics are available below. Scroll down to see the detailed comparison.")
                                
                                st.rerun()
                            except Exception as exc:  # noqa: BLE001
                                st.error(f"❌ Improvement agent failed: {exc}")
                                import traceback
                                with st.expander("Error Details"):
                                    st.code(traceback.format_exc())
                                st.session_state["improvement_stage"] = None
                
                elif st.session_state["improvement_stage"] == "completed":
                    # Stage 3: Display improvement results
                    model_for_improvement = st.session_state.get("selected_model_for_improvement")
                    
                    if st.session_state.get("improvement_steps"):
                        st.subheader("📋 Improvement Steps")
                        with st.expander("View Improvement Steps", expanded=True):
                            st.text(st.session_state["improvement_steps"])
                        
                        # Download improvement steps
                        if st.session_state["improvement_steps"]:
                            st.download_button(
                                label="📥 Download Improvement Steps",
                                data=st.session_state["improvement_steps"],
                                file_name=f"{model_for_improvement}_improvement_steps.txt",
                                mime="text/plain",
                                key="download_improvement_steps"
                            )
                    
                    # Display improved metrics comparison
                    improved_metrics = st.session_state.get("improved_validation_metrics", {})
                    # Fallback: if empty, reload from improvement memory file
                    if not improved_metrics:
                        improvement_memory_path = IMPROVEMENT_DIR / "improvement_memory.json"
                        if improvement_memory_path.exists():
                            try:
                                with improvement_memory_path.open("r", encoding="utf-8") as f:
                                    improvement_memory = json.load(f)
                                improved_metrics = improvement_memory.get("improved_validation_metrics", {}) or {}
                                if improved_metrics:
                                    st.session_state["improved_validation_metrics"] = improved_metrics
                            except Exception:
                                pass
                    original_metrics = st.session_state["validation_metrics"].get(model_for_improvement, {}).get("metrics", {}) if model_for_improvement else {}
                    
                    if improved_metrics:
                        st.markdown('<h3 style="font-size: 1.1rem;">📊 Improved Validation Metrics</h3>', unsafe_allow_html=True)
                        
                        # Display improved metrics in cards with delta comparison
                        if original_metrics and improved_metrics:
                            # Create columns for metrics with delta indicators
                            metric_cols = st.columns(min(4, len(improved_metrics)))
                            
                            metric_index = 0
                            for metric_name, improved_val in improved_metrics.items():
                                if metric_index < len(metric_cols):
                                    with metric_cols[metric_index]:
                                        original_val = original_metrics.get(metric_name)
                                        
                                        if isinstance(improved_val, (int, float)):
                                            # Calculate delta for display
                                            delta_value = None
                                            if isinstance(original_val, (int, float)) and original_val is not None:
                                                if metric_name in ["R2"]:  # Higher is better
                                                    delta_value = improved_val - original_val
                                                else:  # Lower is better (MAE, MSE, RMSE)
                                                    delta_value = original_val - improved_val  # Negative delta means improvement
                                            
                                            # Format metric name
                                            metric_label = metric_name
                                            if metric_name == "R2":
                                                metric_label = "R² Score"
                                            
                                            # Wrap metric in smaller font size
                                            st.markdown(f'<div style="font-size: 0.85rem;">', unsafe_allow_html=True)
                                            st.metric(
                                                label=f"Improved {metric_label}",
                                                value=f"{improved_val:.4f}",
                                                delta=f"{delta_value:.4f}" if delta_value is not None else None,
                                                delta_color="normal" if delta_value is None else ("normal" if (metric_name == "R2" and delta_value > 0) or (metric_name != "R2" and delta_value > 0) else "inverse")
                                            )
                                            st.markdown('</div>', unsafe_allow_html=True)
                                        
                                        metric_index += 1
                            
                            # Create detailed comparison table
                            st.markdown('<h4 style="font-size: 0.95rem;">📈 Detailed Metrics Comparison</h4>', unsafe_allow_html=True)
                            comparison_data = []
                            for metric_name in set(list(original_metrics.keys()) + list(improved_metrics.keys())):
                                original_val = original_metrics.get(metric_name, "N/A")
                                improved_val = improved_metrics.get(metric_name, "N/A")
                                
                                # Calculate improvement percentage if both are numbers
                                improvement = "N/A"
                                improvement_pct = None
                                if isinstance(original_val, (int, float)) and isinstance(improved_val, (int, float)):
                                    if original_val != 0:
                                        if metric_name in ["R2"]:  # Higher is better
                                            improvement_pct = ((improved_val - original_val) / abs(original_val)) * 100
                                            improvement = f"{improvement_pct:+.2f}%"
                                        else:  # Lower is better (MAE, MSE, RMSE)
                                            improvement_pct = ((original_val - improved_val) / original_val) * 100
                                            improvement = f"{improvement_pct:+.2f}%"
                                
                                comparison_data.append({
                                    "Metric": metric_name,
                                    "Original": f"{original_val:.4f}" if isinstance(original_val, (int, float)) else original_val,
                                    "Improved": f"{improved_val:.4f}" if isinstance(improved_val, (int, float)) else improved_val,
                                    "Change": improvement,
                                    "Status": "✅ Improved" if improvement_pct and improvement_pct > 0 else ("⚠️ Degraded" if improvement_pct and improvement_pct < 0 else "➡️ No change")
                                })
                            
                            st.markdown('<style>div[data-testid="stDataFrame"] {font-size: 0.85rem;}</style>', unsafe_allow_html=True)
                            st.dataframe(comparison_data, use_container_width=True)
                        else:
                            # Display improved metrics without comparison (if original metrics not available)
                            st.info("⚠️ Original metrics not available for comparison. Showing improved metrics only.")
                            
                            # Display all improved metrics
                            metric_cols = st.columns(min(4, len(improved_metrics)))
                            metric_index = 0
                            for metric_name, improved_val in improved_metrics.items():
                                if metric_index < len(metric_cols):
                                    with metric_cols[metric_index]:
                                        if isinstance(improved_val, (int, float)):
                                            metric_label = metric_name
                                            if metric_name == "R2":
                                                metric_label = "R² Score"
                                            # Wrap metric in smaller font size
                                            st.markdown(f'<div style="font-size: 0.85rem;">', unsafe_allow_html=True)
                                            st.metric(
                                                label=f"Improved {metric_label}",
                                                value=f"{improved_val:.4f}"
                                            )
                                            st.markdown('</div>', unsafe_allow_html=True)
                                        metric_index += 1
                            
                            # Show metrics in a table format
                            metrics_table_data = [
                                {"Metric": name, "Value": f"{val:.4f}" if isinstance(val, (int, float)) else str(val)}
                                for name, val in improved_metrics.items()
                            ]
                            st.markdown('<style>div[data-testid="stDataFrame"] {font-size: 0.85rem;}</style>', unsafe_allow_html=True)
                            st.dataframe(metrics_table_data, use_container_width=True)
                    else:
                        st.info("📊 Improved validation metrics will appear here after the improvement agent completes execution.")
                    
                    # Download improved validation code if available
                    improved_code_path = st.session_state.get("improved_validation_code_path")
                    if improved_code_path:
                        improved_code_file = Path(improved_code_path)
                        if improved_code_file.exists():
                            try:
                                with improved_code_file.open("r", encoding="utf-8") as f:
                                    improved_code_contents = f.read()
                                st.download_button(
                                    label="📥 Download Improved Validation Code",
                                    data=improved_code_contents,
                                    file_name=improved_code_file.name,
                                    mime="text/x-python",
                                    key="download_improved_code"
                                )
                            except Exception as e:
                                st.warning(f"Could not read improved validation code: {e}")
                    
                    # Option to run improvement again
                    if st.button("Run Improvement for Another Model"):
                        st.session_state["improvement_stage"] = None
                        st.session_state["improvement_steps"] = None
                        st.session_state["improved_validation_metrics"] = {}
                        st.session_state["improved_validation_code_path"] = None
                        st.rerun()
                    
                    # Exit button after improvement metrics are displayed
                    st.divider()
                    if st.button("🚪 Exit Program", type="primary", use_container_width=True):
                        st.success("Thank you for using IntelliModel! The program will exit.")
                        st.stop()
            else:
                st.info("No validated models available for improvement. Please complete validation first.")


if __name__ == "__main__":
    main()


