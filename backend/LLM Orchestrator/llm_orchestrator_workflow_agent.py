#usage: python "LLM Orchestrator/llm_orchestrator_workflow_agent.py"
"""
AI Agent for LLM Orchestration Workflow

This agent orchestrates the model recommendation workflow:
1. Load master memory and extract dataset information
2. Generate model recommendations using model_recommender.py

The agent maintains memory of all steps and their outputs.
"""

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Literal, Optional, TypedDict, Union

from langgraph.graph import END, StateGraph  # type: ignore[import]

# Add current directory to path for imports
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from model_recommender import recommend_models, select_models_for_validation, DEFAULT_MODEL, DEFAULT_ENDPOINT
import re


def parse_model_recommendations(recommendations_text: str) -> list[Dict[str, str]]:
    """
    Parse LLM response to extract model names and reasons.
    
    Args:
        recommendations_text: Raw text response from LLM
        
    Returns:
        List of dictionaries with "Model Recommended" and "Reason" keys
    """
    structured: list[Dict[str, str]] = []

    # Strategy 1: Strict format "Model 1: Name\nReason: ..."
    # This is the primary format we request from the LLM
    pattern_strict = re.compile(
        r'Model\s+(\d+)\s*:\s*(.+?)(?=\s+Reason\s*:|\s+Model\s+\d+\s*:|$)',
        re.IGNORECASE | re.DOTALL
    )
    pattern_reason = re.compile(
        r'Reason\s*:\s*(.+?)(?=\s+Model\s+\d+\s*:|$)',
        re.IGNORECASE | re.DOTALL
    )
    
    # Find all Model N: entries
    model_matches = list(pattern_strict.finditer(recommendations_text))
    
    for i, model_match in enumerate(model_matches):
        model_num = model_match.group(1)
        model_name = model_match.group(2).strip()
        # Clean markdown formatting
        model_name = re.sub(r'\*\*?', '', model_name).strip()
        
        # Find the corresponding Reason: block
        start_pos = model_match.end()
        if i + 1 < len(model_matches):
            end_pos = model_matches[i + 1].start()
        else:
            end_pos = len(recommendations_text)
        
        reason_block = recommendations_text[start_pos:end_pos]
        reason_match = pattern_reason.search(reason_block)
        
        if reason_match:
            reason_text = reason_match.group(1).strip()
        else:
            # Try to find any text after "Reason:" even if not in strict format
            reason_lines = []
            for line in reason_block.split('\n'):
                line = line.strip()
                if line.startswith('Reason') or (line and not line.startswith('Model')):
                    cleaned = re.sub(r'^\s*Reason\s*:?\s*', '', line, flags=re.IGNORECASE)
                    cleaned = re.sub(r'\*\*?', '', cleaned).strip()
                    if cleaned and not cleaned.startswith('Model'):
                        reason_lines.append(cleaned)
            reason_text = ' '.join(reason_lines).strip()
        
        # Clean up reason text
        reason_text = re.sub(r'\*\*?', '', reason_text).strip()
        
        if model_name:
            structured.append({
                "Model Recommended": model_name,
                "Reason": reason_text if reason_text else "No reason provided",
            })
    
    if structured:
        return structured

    # Strategy 2: Fallback - Handle "Model N: Name" format (without strict spacing)
    pattern_model_reason = re.compile(
        r'Model\s+(\d+)\s*:\s*(.+?)\s*(?:\r?\n)+\s*Reason\s*:\s*(.+?)(?=\r?\n\s*Model\s+\d+\s*:|\Z)',
        re.IGNORECASE | re.DOTALL
    )
    matches = pattern_model_reason.findall(recommendations_text)
    for model_num, model_name, reason_block in matches:
        name_clean = re.sub(r'\*\*?', '', model_name).strip()
        reason_clean = re.sub(r'\*\*?', '', reason_block).strip()
        if name_clean:
            structured.append({
                "Model Recommended": name_clean,
                "Reason": reason_clean if reason_clean else "No reason provided",
            })
    
    if structured:
        return structured

    # Strategy 3: Fallback - Handle markdown numbered list format "1. **Model**"
    lines = recommendations_text.split('\n')
    current_model = None
    current_reason_parts: list[str] = []
    collecting_reason = False

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        # Numbered markdown models: "1. **Random Forest Regressor**"
        model_match = re.match(r'^(\d+)\.\s*\*\*?(.+?)\*\*?\s*$', line, re.IGNORECASE)
        if model_match:
            if current_model and current_reason_parts:
                reason_text = ' '.join(current_reason_parts).strip()
                structured.append({
                    "Model Recommended": current_model,
                    "Reason": reason_text if reason_text else "No reason provided",
                })
            current_model = re.sub(r'\*\*?', '', model_match.group(2)).strip()
            current_reason_parts = []
            collecting_reason = False
            i += 1
            continue

        # Reason or Fit-to-Findings lines
        reason_match = re.match(
            r'^\s*[-*]?\s*\*\*?(?:Reason|Fit to Findings|Fit)\*\*?[:\-]?\s*(.*)$',
            line,
            re.IGNORECASE,
        )
        if reason_match:
            collecting_reason = True
            reason_text = reason_match.group(1).strip()
            if reason_text:
                current_reason_parts.append(reason_text)
            i += 1
            continue

        # Additional reason lines (indented or continuation)
        if collecting_reason and current_model:
            if re.match(r'^(\d+)\.', line) or re.match(
                r'^(Model\s+\d+|Task|Format|These models)', line, re.IGNORECASE
            ):
                collecting_reason = False
                continue
            cleaned = re.sub(r'\*\*?', '', line).strip()
            # Skip lines that look like new model entries
            if cleaned and not re.match(r'^Model\s+\d+', cleaned, re.IGNORECASE):
                current_reason_parts.append(cleaned)

        i += 1

    if current_model and current_reason_parts:
        reason_text = ' '.join(current_reason_parts).strip()
        structured.append({
            "Model Recommended": current_model,
            "Reason": reason_text if reason_text else "No reason provided",
        })

    return structured


@dataclass
class OrchestratorMemory:
    """Memory structure to store workflow state and outputs."""
    master_memory_path: Optional[Path] = None
    dataset_name: Optional[str] = None
    target_column: Optional[str] = None
    context_of_dataset: Optional[str] = None
    report: Dict[str, Any] = field(default_factory=dict)
    model_recommendations: Optional[str] = None  # Raw text response (for backward compatibility)
    model_recommendations_structured: list[Dict[str, str]] = field(default_factory=list)  # Structured format
    recommended_models: list[str] = field(default_factory=list)  # All recommended models (names only)
    selected_models_for_validation: list[str] = field(default_factory=list)  # Models selected by user for validation testing
    recommendations_path: Optional[Path] = None
    generated_code_paths: list[str] = field(default_factory=list)  # Paths to generated validation/testing code files
    validation_metrics: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # Metrics from validation code execution
    selected_model_for_full_training: Optional[str] = None  # Model selected by user for full dataset training
    # History of filenames created by the workflow
    file_history: Dict[str, str] = field(default_factory=dict)
    # History of all models that have ever been validated (across reselections)
    validation_history: list[str] = field(default_factory=list)


class LLMOrchestratorWorkflowAgent:
    """
    AI Agent that orchestrates the model recommendation workflow and maintains memory.
    """
    
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        endpoint: str = DEFAULT_ENDPOINT,
        output_dir: Optional[Path] = None,
        master_memory_path: Optional[Path] = None
    ):
        """
        Initialize the workflow agent.
        
        Args:
            model: LLM model name (default: "phi4")
            endpoint: LLM endpoint URL (default: "http://127.0.0.1:11434")
            output_dir: Directory to save outputs (default: LLM Orchestrator directory)
            master_memory_path: Path to master_memory.json (default: parent directory/master_memory.json)
        """
        self.model = model
        self.endpoint = endpoint
        # Default output_dir is the LLM Orchestrator directory (where the script is)
        self.output_dir = Path(output_dir) if output_dir else current_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Set master memory path
        if master_memory_path:
            # Resolve relative paths relative to current working directory
            master_memory_path = Path(master_memory_path)
            if not master_memory_path.is_absolute():
                # Try relative to current working directory first
                resolved_path = Path.cwd() / master_memory_path
                if resolved_path.exists():
                    self.master_memory_path = resolved_path.resolve()
                else:
                    # Try relative to script's parent directory
                    resolved_path = current_dir.parent / master_memory_path
                    if resolved_path.exists():
                        self.master_memory_path = resolved_path.resolve()
                    else:
                        # Use as-is (will fail later with better error message)
                        self.master_memory_path = Path.cwd() / master_memory_path
            else:
                self.master_memory_path = master_memory_path.resolve()
        else:
            # Default to parent directory
            self.master_memory_path = current_dir.parent / "master_memory.json"
        
        # Initialize memory
        self.memory = OrchestratorMemory()
        self.memory.master_memory_path = self.master_memory_path
        # Simple conversation history for tracking workflow steps
        self.conversation_history: list[Dict[str, str]] = []
        
        # Set default paths (recommendations will be updated with dataset name)
        self.memory.recommendations_path = self.output_dir / "model_recommendations.txt"
        # Set memory file path - named after agent, not dataset
        self.memory_file_path = self.output_dir / "orchestrator_memory.json"
        
        # LangGraph workflow
        self.workflow = self._build_workflow_graph()
    
    def load_master_memory(self) -> Dict[str, Any]:
        """
        Step 1: Load master memory and extract required information.
        
        Returns:
            Master memory dictionary
        """
        print("\n" + "="*60)
        print("STEP 1: Loading Master Memory")
        print("="*60)
        
        # Check if master memory exists
        if not self.master_memory_path.exists():
            # Try to suggest alternative paths
            suggestions = []
            alt_path1 = current_dir.parent / "master_memory.json"
            if alt_path1.exists():
                suggestions.append(f"Try: {alt_path1}")
            alt_path2 = Path.cwd() / "master_memory.json"
            if alt_path2.exists():
                suggestions.append(f"Try: {alt_path2}")
            
            error_msg = (
                f"Master memory file not found: {self.master_memory_path}\n"
                "Ensure preprocessing workflow has been completed first."
            )
            if suggestions:
                error_msg += f"\n\nAlternative paths found:\n" + "\n".join(suggestions)
            raise FileNotFoundError(error_msg)
        
        print(f"Loading master memory from: {self.master_memory_path}")

        # Load master memory
        try:
            with self.master_memory_path.open("r", encoding="utf-8") as f:
                master_memory = json.load(f)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"master_memory.json is corrupted (invalid JSON): {self.master_memory_path}\n"
                f"Error: {exc}\nPlease delete or repair the file and re-run the workflow."
            ) from exc
        
        # Extract required information
        self.memory.dataset_name = master_memory.get("dataset_name", "Unknown")
        self.memory.target_column = master_memory.get("target_column", "")
        self.memory.context_of_dataset = master_memory.get("context_of_dataset", "")
        self.memory.report = master_memory.get("preprocessing", {}).get("report", {})
        
        # Validate required fields
        if not self.memory.target_column:
            raise ValueError("'target_column' not found in master_memory.json")
        
        if not self.memory.context_of_dataset:
            raise ValueError("'context_of_dataset' not found in master_memory.json")
        
        if not self.memory.report:
            raise ValueError("'report' not found in master_memory.json under 'preprocessing'")
        
        # Update recommendations path with dataset name
        self.memory.recommendations_path = self.output_dir / f"{self.memory.dataset_name}_model_recommendations.txt"
        
        # Memory file path stays the same (named after agent, not dataset)
        # It's already set in __init__ to orchestrator_memory.json
        
        # Track master memory path in file history
        try:
            self.memory.file_history["master_memory"] = str(self.master_memory_path.resolve())
        except Exception:
            pass
        
        print(f"Dataset: {self.memory.dataset_name}")
        print(f"Target column: {self.memory.target_column}")
        print(f"Context: {self.memory.context_of_dataset}")
        print(f"Report loaded: {len(self.memory.report)} keys")
        
        # Save memory after loading master memory
        self.save_memory()
        
        return master_memory
    
    def generate_model_recommendations(self) -> str:
        """
        Step 2: Generate model recommendations from report and context.
        
        Returns:
            Model recommendations as string
        """
        print("\n" + "="*60)
        print("STEP 2: Generating Model Recommendations")
        print("="*60)
        
        # Check if required data is available
        if not self.memory.report:
            raise ValueError(
                "Report not found in memory. "
                "Run load_master_memory() first."
            )
        
        if not self.memory.context_of_dataset:
            raise ValueError(
                "Context not found in memory. "
                "Run load_master_memory() first."
            )
        
        if not self.memory.target_column:
            raise ValueError(
                "Target column not found in memory. "
                "Run load_master_memory() first."
            )
        
        print(f"Target column: {self.memory.target_column}")
        print("Querying LLM for model recommendations...")
        
        # Convert report to JSON string for LLM
        report_str = json.dumps(self.memory.report, indent=2)
        
        # Build context, optionally telling the LLM to avoid previously validated models
        context_for_llm = self.memory.context_of_dataset
        previously_validated = set(self.memory.validation_history or [])
        previously_validated.update(self.memory.validation_metrics.keys())
        if previously_validated:
            avoided = ", ".join(sorted(previously_validated))
            extra_note = (
                "\n\nIMPORTANT: The following models have already been evaluated and "
                "MUST NOT be recommended again. Recommend completely different models:\n"
                f"{avoided}\n"
            )
            context_for_llm = (context_for_llm or "") + extra_note
        
        # Query LLM for model recommendations
        recommendations = recommend_models(
            report=report_str,
            context=context_for_llm,
            target=self.memory.target_column,
            model=self.model,
            endpoint=self.endpoint
        )
        
        # Store raw recommendations in memory (for backward compatibility)
        self.memory.model_recommendations = recommendations
        
        # Parse recommendations into structured format
        structured_recommendations = parse_model_recommendations(recommendations)
        self.memory.model_recommendations_structured = structured_recommendations
        
        # Extract all recommended model names
        self.memory.recommended_models = [
            entry.get("Model Recommended", "") 
            for entry in structured_recommendations 
            if entry.get("Model Recommended")
        ]
        
        # Save recommendations to file
        self.memory.recommendations_path.parent.mkdir(parents=True, exist_ok=True)
        self.memory.recommendations_path.write_text(recommendations, encoding="utf-8")
        
        # Track recommendations path in file history
        try:
            self.memory.file_history["model_recommendations"] = str(self.memory.recommendations_path.resolve())
        except Exception:
            pass
        
        print(f"\nModel recommendations saved to: {self.memory.recommendations_path}")
        print(f"Recommendations length: {len(recommendations)} characters")
        print(f"Parsed {len(structured_recommendations)} models into structured format")
        
        # Save memory after generating recommendations
        self.save_memory()
        
        # Display recommendations summary
        print("\n" + "-"*60)
        print("MODEL RECOMMENDATIONS")
        print("-"*60)
        print(recommendations)
        print("-"*60)
        
        return recommendations
    
    def select_models_for_validation(self) -> list[str]:
        """
        Step 2.5: Ask user which models to perform validation testing on.
        
        Returns:
            List of selected model names for validation
        """
        print("\n" + "="*60)
        print("STEP 2.5: Selecting Models for Validation Testing")
        print("="*60)
        
        # Check if recommendations are available
        if not self.memory.model_recommendations:
            raise ValueError(
                "Model recommendations not found in memory. "
                "Run generate_model_recommendations() first."
            )
        
        # Ask user to select models for validation
        selected_models = select_models_for_validation(self.memory.model_recommendations)
        
        # Store selected models in memory
        self.memory.selected_models_for_validation = selected_models
        
        # Save memory after selection
        self.save_memory()
        
        print(f"\nSelected {len(selected_models)} model(s) for validation testing:")
        for model in selected_models:
            print(f"  - {model}")
        
        return selected_models
    
    def generate_validation_code(self) -> list[str]:
        """
        Step 3: Generate validation/testing code for selected models.
        
        Returns:
            List of paths to generated code files
        """
        print("\n" + "="*60)
        print("STEP 3: Generating Validation/Testing Code")
        print("="*60)
        
        # Check if models were selected for validation
        if not self.memory.selected_models_for_validation:
            raise ValueError(
                "No models selected for validation. "
                "Run select_models_for_validation() first."
            )
        
        # Filter structured recommendations to only include selected models
        selected_structured = [
            entry for entry in self.memory.model_recommendations_structured
            if entry.get("Model Recommended", "") in self.memory.selected_models_for_validation
        ]
        
        if not selected_structured:
            raise ValueError(
                "Selected models not found in structured recommendations. "
                "This should not happen."
            )
        
        # Import and run model_vc_gen
        import subprocess
        
        # Run model_vc_gen.py as a subprocess
        model_vc_gen_script = current_dir / "model_vc_gen.py"
        if not model_vc_gen_script.exists():
            raise FileNotFoundError(f"model_vc_gen.py not found at: {model_vc_gen_script}")
        
        print(f"Running: {model_vc_gen_script}")
        
        try:
            # Run the script and capture output
            result = subprocess.run(
                [sys.executable, str(model_vc_gen_script)],
                cwd=str(current_dir),
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse output to extract file paths
            # The script prints "Saved: <path>" for each file
            generated_files = []
            for line in result.stdout.split('\n'):
                if 'Saved:' in line:
                    # Extract path after "Saved: "
                    path_str = line.split('Saved:', 1)[1].strip()
                    if path_str:
                        generated_files.append(path_str)
            
            # Store generated code paths in memory
            self.memory.generated_code_paths = generated_files
            
            # Track in file history
            try:
                for i, path in enumerate(generated_files):
                    self.memory.file_history[f"validation_code_{i+1}"] = path
            except Exception:
                pass
            
            print(f"\nGenerated {len(generated_files)} validation/testing code files")
            for path in generated_files:
                print(f"  - {path}")
            
            # Save memory after generating code
            self.save_memory()
            
            return generated_files
            
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to generate validation code: {e.stderr}"
            print(f"ERROR: {error_msg}")
            raise RuntimeError(error_msg) from e
    
    def run_validation_code(self) -> None:
        """
        Step 4: Execute validation/testing code and print metrics.
        """
        print("\n" + "="*60)
        print("STEP 4: Running Validation/Testing Code")
        print("="*60)
        
        # Check if validation code paths are available
        if not self.memory.generated_code_paths:
            raise ValueError(
                "Generated validation code paths not found in memory. "
                "Run generate_validation_code() first."
            )
        
        # Run run_validation_code_with_llm.py as a subprocess
        import subprocess
        
        validation_script = current_dir / "run_validation_code_with_llm.py"
        if not validation_script.exists():
            print(f"[WARN] Validation execution script not found: {validation_script}. Skipping execution.")
            return
        
        # Ensure orchestrator memory is persisted for the helper script
        self.save_memory()
        
        print("\n" + "-" * 60)
        print("Running validation/testing code with self-healing helper...")
        try:
            # stdin=DEVNULL ensures any interactive input() calls in the helper
            # immediately receive EOF instead of blocking the background thread.
            subprocess.run(
                [sys.executable, str(validation_script)],
                stdin=subprocess.DEVNULL,
                check=True,
            )
            print("Validation/testing code executed successfully.")
            
            # Reload memory file to get metrics that were saved by the validation script
            if self.memory_file_path.exists():
                try:
                    with self.memory_file_path.open("r", encoding="utf-8") as f:
                        updated_memory = json.load(f)
                    # Update validation_metrics in memory
                    if "validation_metrics" in updated_memory:
                        self.memory.validation_metrics = updated_memory["validation_metrics"]
                except json.JSONDecodeError as exc:
                    print(f"[WARN] Could not reload orchestrator memory after validation (corrupted JSON): {exc}")
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "Execution helper failed to run validation/testing code."
            ) from exc
        finally:
            print("-" * 60 + "\n")
    
    def run_model_results_review(self) -> Optional[Dict[str, str]]:
        """
        Step 5: Run model results review and get user selection.
        
        Returns:
            Dictionary with action and model name if user wants to generate full training code,
            None otherwise
        """
        print("\n" + "="*60)
        print("STEP 5: Model Results Review")
        print("="*60)
        
        # Check if validation metrics are available
        if not self.memory.validation_metrics:
            raise ValueError(
                "Validation metrics not found in memory. "
                "Run run_validation_code() first."
            )
        
        # Run model_results_review.py as a subprocess
        import subprocess
        
        review_script = current_dir / "model_results_review.py"
        if not review_script.exists():
            print(f"[WARN] Model results review script not found: {review_script}. Skipping review.")
            return None
        
        # Ensure orchestrator memory is persisted for the review script
        self.save_memory()
        
        print("\n" + "-" * 60)
        print("Running model results review...")
        try:
            # Run interactively (user will see prompts)
            subprocess.run([sys.executable, str(review_script)], check=True)
            
            # Reload memory file to get the updated review action / selected model
            if self.memory_file_path.exists():
                try:
                    with self.memory_file_path.open("r", encoding="utf-8") as f:
                        updated_memory = json.load(f)
                except json.JSONDecodeError as exc:
                    print(f"[WARN] Could not reload orchestrator memory after review (corrupted JSON): {exc}")
                    return None
                # Check if user requested model reselection
                review_action = updated_memory.get("review_action")
                if review_action == "reselect_models":
                    print("\n[INFO] User requested model reselection. Restarting recommendation and validation steps.")
                    # Clear the flag so it does not persist into future runs
                    updated_memory["review_action"] = None
                    with self.memory_file_path.open("w", encoding="utf-8") as fw:
                        json.dump(updated_memory, fw, indent=2)
                    return {"action": "reselect_models"}

                # Otherwise, update selected model in memory if present
                selected_model = updated_memory.get("selected_model_for_full_training")
                if selected_model:
                    self.memory.selected_model_for_full_training = selected_model
                    print(f"\n[INFO] User selected to generate full training code for: {selected_model}")
                    return {"action": "generate_full_training", "model": selected_model}
                else:
                    print("\n[INFO] User did not select full training code generation.")
                    return None
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "Model results review script failed."
            ) from exc
        finally:
            print("-" * 60 + "\n")
    
    def generate_full_training_code(self, model_name: str) -> None:
        """
        Step 6: Generate full training code for the selected model.
        
        Args:
            model_name: Name of the model to generate full training code for
        """
        print("\n" + "="*60)
        print(f"STEP 6: Generating Full Training Code for {model_name}")
        print("="*60)
        
        # Run generate_full_training_code.py as a subprocess with model name argument
        import subprocess
        
        generate_script = current_dir / "generate_full_training_code.py"
        if not generate_script.exists():
            raise FileNotFoundError(f"Full training code generation script not found: {generate_script}")
        
        print(f"\nGenerating full training code for model: {model_name}")
        try:
            subprocess.run(
                [sys.executable, str(generate_script), model_name],
                check=True
            )
            print(f"\nFull training code generated successfully for {model_name}.")
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"Failed to generate full training code for {model_name}."
            ) from exc
    
    def run_full_training_code(
        self, warm_start_checkpoint_path: Optional[str] = None
    ) -> None:
        """
        Run the full-training code via run_full_training_code_with_llm.py.
        The runner executes the generated full-training script and fixes errors with LLM if needed;
        the script saves the model as .pkl in the full_training directory.
        """
        import subprocess
        
        runner_script = current_dir / "run_full_training_code_with_llm.py"
        if not runner_script.exists():
            raise FileNotFoundError(f"Full training runner not found: {runner_script}")
        
        print("\n" + "="*60)
        print("STEP 7: Running Full Training Code")
        print("="*60)
        print("Running full training code via run_full_training_code_with_llm.py")
        try:
            env = os.environ.copy()
            if warm_start_checkpoint_path:
                env["INTELLIMODEL_WARM_START_PATH"] = warm_start_checkpoint_path
                print(
                    f"[INFO] Warm-start checkpoint candidate: {warm_start_checkpoint_path}"
                )
            subprocess.run(
                [sys.executable, str(runner_script)],
                cwd=str(current_dir),
                env=env,
                check=True,
            )
            print("\nFull training completed. Model saved as .pkl in full_training directory.")
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "Full training code execution failed. See traceback above."
            ) from exc
    
    def deploy_model_api(self) -> None:
        """
        Step 8: Start the FastAPI deployment server using the trained model.
        
        This calls backend/deployment/main.py, which:
        - Loads master_memory.json (via MASTER_MEMORY_PATH or default)
        - Locates the latest *_full.pkl in the full_training directory
        - Starts a FastAPI app exposing /features, /predict, /health
        """
        import subprocess
        
        deployment_script = current_dir.parent / "deployment" / "main.py"
        if not deployment_script.exists():
            raise FileNotFoundError(f"Deployment script not found: {deployment_script}")
        
        print("\n" + "=" * 60)
        print("STEP 8: Deploying Model via FastAPI")
        print("=" * 60)
        
        # Pass master memory path to the deployment app so it can resolve report/model paths
        env = os.environ.copy()
        if self.memory.master_memory_path:
            env["MASTER_MEMORY_PATH"] = str(self.memory.master_memory_path)
        
        print(f"Starting FastAPI deployment server using: {deployment_script}")
        print("Once started, the prediction API will be available at http://127.0.0.1:8000")
        print("Endpoints:")
        print("  - GET  /features  -> required feature names")
        print("  - POST /predict   -> generate predictions")
        print("  - GET  /health    -> health status")
        
        # This call will block while the server is running; stop the server to continue.
        subprocess.run(
            [sys.executable, str(deployment_script)],
            cwd=str(current_dir.parent),
            env=env,
            check=True,
        )
    
    def _build_workflow_graph(self):
        """
        Build a LangGraph state graph that coordinates the workflow.
        """
        class WorkflowState(TypedDict, total=False):
            master_memory: Dict[str, Any]
            recommendations: str
            status: Literal["pending", "ok", "error", "success"]
            error: str
            memory_snapshot: Dict[str, Any]
            review_result: Optional[Dict[str, str]]
        
        state_graph = StateGraph(WorkflowState)
        state_graph.add_node("load_memory", self._graph_load_memory)
        state_graph.add_node("generate_recommendations", self._graph_generate_recommendations)
        state_graph.add_node("select_models_for_validation", self._graph_select_models_for_validation)
        state_graph.add_node("generate_validation_code", self._graph_generate_validation_code)
        state_graph.add_node("run_validation_code", self._graph_run_validation_code)
        state_graph.add_node("model_results_review", self._graph_model_results_review)
        state_graph.add_node("generate_full_training", self._graph_generate_full_training)
        state_graph.add_node("run_full_training_code", self._graph_run_full_training_code)
        state_graph.add_node("deploy_model_api", self._graph_deploy_model)
        state_graph.add_node("persist_memory", self._graph_finalize_memory)
        
        state_graph.set_entry_point("load_memory")
        state_graph.add_conditional_edges(
            "load_memory",
            self._status_router,
            {"error": END, "ok": "generate_recommendations"}
        )
        state_graph.add_conditional_edges(
            "generate_recommendations",
            self._status_router,
            {"error": END, "ok": "select_models_for_validation"}
        )
        state_graph.add_conditional_edges(
            "select_models_for_validation",
            self._status_router,
            {"error": END, "ok": "generate_validation_code"}
        )
        state_graph.add_conditional_edges(
            "generate_validation_code",
            self._status_router,
            {"error": END, "ok": "run_validation_code"}
        )
        state_graph.add_conditional_edges(
            "run_validation_code",
            self._status_router,
            {"error": END, "ok": "model_results_review"}
        )
        state_graph.add_conditional_edges(
            "model_results_review",
            self._review_router,
            {
                "generate_full_training": "generate_full_training",
                "reselect_models": "generate_recommendations",
                "skip": "persist_memory",
                "error": END,
            }
        )
        state_graph.add_conditional_edges(
            "generate_full_training",
            self._status_router,
            {"error": END, "ok": "run_full_training_code"}
        )
        state_graph.add_conditional_edges(
            "run_full_training_code",
            self._status_router,
            {"error": END, "ok": "deploy_model_api"}
        )
        state_graph.add_conditional_edges(
            "deploy_model_api",
            self._status_router,
            {"error": END, "ok": "persist_memory"}
        )
        state_graph.add_edge("persist_memory", END)
        
        return state_graph.compile()
    
    @staticmethod
    def _status_router(state: Dict[str, Any]) -> str:
        """
        Determine next edge based on state.
        """
        return "error" if state.get("status") == "error" else "ok"
    
    @staticmethod
    def _review_router(state: Dict[str, Any]) -> str:
        """
        Determine next edge based on model results review outcome.
        """
        if state.get("status") == "error":
            return "error"
        review_result = state.get("review_result")
        if review_result:
            action = review_result.get("action")
            if action == "generate_full_training":
                return "generate_full_training"
            if action == "reselect_models":
                return "reselect_models"
        return "skip"
    
    
    def _add_memory_entry(self, user_text: str, ai_text: str) -> None:
        """
        Store a conversational trace for transparency/debugging.
        """
        self.conversation_history.append({
            "input": user_text,
            "output": ai_text
        })
    
    def _graph_load_memory(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph node: load master memory.
        """
        try:
            master_memory = self.load_master_memory()
            summary = (
                f"Master memory loaded. Dataset: {self.memory.dataset_name}, "
                f"Target: {self.memory.target_column}."
            )
            self._add_memory_entry(
                "Load master memory",
                summary
            )
            return {
                "master_memory": master_memory,
                "status": "ok",
                "error": ""
            }
        except Exception as exc:
            error_message = f"Memory loading failed: {exc}"
            self._add_memory_entry(
                "Load master memory",
                error_message
            )
            return {"status": "error", "error": error_message}
    
    def _graph_generate_recommendations(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph node: generate model recommendations.
        """
        try:
            recommendations = self.generate_model_recommendations()
            rec_len = len(recommendations) if recommendations else 0
            self._add_memory_entry(
                "Generate model recommendations",
                f"Recommendations generated with {rec_len} characters."
            )
            return {
                "recommendations": recommendations,
                "status": "ok",
                "error": ""
            }
        except Exception as exc:
            error_message = f"Recommendation generation failed: {exc}"
            self._add_memory_entry(
                "Generate model recommendations",
                error_message
            )
            return {"status": "error", "error": error_message}
    
    def _graph_select_models_for_validation(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph node: select models for validation testing.
        """
        try:
            selected_models = self.select_models_for_validation()
            model_count = len(selected_models) if selected_models else 0
            self._add_memory_entry(
                "Select models for validation",
                f"Selected {model_count} model(s) for validation testing."
            )
            return {
                "status": "ok",
                "error": ""
            }
        except Exception as exc:
            error_message = f"Model selection failed: {exc}"
            self._add_memory_entry(
                "Select models for validation",
                error_message
            )
            return {"status": "error", "error": error_message}
    
    def _graph_generate_validation_code(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph node: generate validation/testing code.
        """
        try:
            generated_files = self.generate_validation_code()
            file_count = len(generated_files) if generated_files else 0
            self._add_memory_entry(
                "Generate validation code",
                f"Generated {file_count} validation/testing code files."
            )
            return {
                "status": "ok",
                "error": ""
            }
        except Exception as exc:
            error_message = f"Validation code generation failed: {exc}"
            self._add_memory_entry(
                "Generate validation code",
                error_message
            )
            return {"status": "error", "error": error_message}
    
    def _graph_run_validation_code(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph node: run validation/testing code.
        """
        try:
            self.run_validation_code()
            self._add_memory_entry(
                "Run validation code",
                "Validation/testing code executed successfully."
            )
            return {
                "status": "ok",
                "error": ""
            }
        except Exception as exc:
            error_message = f"Validation code execution failed: {exc}"
            self._add_memory_entry(
                "Run validation code",
                error_message
            )
            return {"status": "error", "error": error_message}
    
    def _graph_model_results_review(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph node: run model results review.
        """
        try:
            review_result = self.run_model_results_review()
            # If user chose to reselect models, prepare for a fresh validation round
            if review_result and review_result.get("action") == "reselect_models":
                self._prepare_for_reselection()
            if review_result and review_result.get("action") == "generate_full_training":
                self._add_memory_entry(
                    "Model results review",
                    f"User selected to generate full training code for: {review_result.get('model')}"
                )
            else:
                self._add_memory_entry(
                    "Model results review",
                    "User reviewed results. Full training code generation skipped."
                )
            return {
                "status": "ok",
                "error": "",
                "review_result": review_result
            }
        except Exception as exc:
            error_message = f"Model results review failed: {exc}"
            self._add_memory_entry(
                "Model results review",
                error_message
            )
            return {"status": "error", "error": error_message, "review_result": None}
    
    def _graph_generate_full_training(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph node: generate full training code for selected model.
        """
        try:
            review_result = state.get("review_result")
            if not review_result or review_result.get("action") != "generate_full_training":
                # Should not happen, but handle gracefully
                return {"status": "ok", "error": ""}
            
            model_name = review_result.get("model")
            if not model_name:
                raise ValueError("Model name not found in review result")
            
            self.generate_full_training_code(model_name)
            self._add_memory_entry(
                "Generate full training code",
                f"Full training code generated for {model_name}."
            )
            return {
                "status": "ok",
                "error": ""
            }
        except Exception as exc:
            error_message = f"Full training code generation failed: {exc}"
            self._add_memory_entry(
                "Generate full training code",
                error_message
            )
            return {"status": "error", "error": error_message}
    
    def _graph_run_full_training_code(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph node: run full training code via run_full_training_code_with_llm.py.
        """
        try:
            self.run_full_training_code()
            self._add_memory_entry(
                "Run full training code",
                "Full training code executed; model saved as .pkl in full_training directory."
            )
            return {
                "status": "ok",
                "error": ""
            }
        except Exception as exc:
            error_message = f"Full training code execution failed: {exc}"
            self._add_memory_entry(
                "Run full training code",
                error_message
            )
            return {"status": "error", "error": error_message}
    
    def _graph_deploy_model(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph node: deploy the trained model via the FastAPI deployment module.
        """
        try:
            self.deploy_model_api()
            self._add_memory_entry(
                "Deploy model API",
                "FastAPI deployment server started for the trained model."
            )
            return {
                "status": "ok",
                "error": ""
            }
        except Exception as exc:
            error_message = f"Model deployment failed: {exc}"
            self._add_memory_entry(
                "Deploy model API",
                error_message
            )
            return {"status": "error", "error": error_message}

    def _prepare_for_reselection(self) -> None:
        """
        Prepare internal memory state for model reselection:
        - Record all previously validated models into validation_history
        - Remove prior validation/testing code files
        - Clear current validation-related fields so the workflow can start fresh.
        """
        # Update validation history with all models that have validation metrics
        previous = set(self.memory.validation_history or [])
        previous.update(self.memory.validation_metrics.keys())
        self.memory.validation_history = sorted(previous)

        # Remove previously generated validation/testing code files
        for path_str in list(self.memory.generated_code_paths):
            try:
                p = Path(path_str)
                if p.exists():
                    p.unlink()
            except Exception:
                # Best-effort cleanup; ignore failures
                pass

        # Clear current validation-related fields
        self.memory.generated_code_paths = []
        self.memory.selected_models_for_validation = []
        self.memory.validation_metrics = {}
        self.memory.recommended_models = []
        self.memory.model_recommendations = None
        self.memory.model_recommendations_structured = []
    
    def _graph_finalize_memory(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Final LangGraph node: capture memory snapshot and save to file.
        """
        snapshot = self.get_memory()
        # Save memory to file
        self.save_memory()
        self._add_memory_entry(
            "Persist workflow memory",
            "Memory snapshot stored."
        )
        return {
            "memory_snapshot": snapshot,
            "status": "success"
        }
    
    def run_full_workflow(
        self,
        master_memory_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Run the complete model recommendation workflow using LangGraph.
        
        Args:
            master_memory_path: Optional path to master_memory.json (overrides default)
        """
        print("\n" + "="*60)
        print("LLM ORCHESTRATOR WORKFLOW AGENT - FULL WORKFLOW")
        print("="*60)
        
        # Update master memory path if provided
        if master_memory_path:
            # Resolve relative paths relative to current working directory
            master_memory_path = Path(master_memory_path)
            if not master_memory_path.is_absolute():
                # Try relative to current working directory first
                resolved_path = Path.cwd() / master_memory_path
                if resolved_path.exists():
                    self.master_memory_path = resolved_path.resolve()
                else:
                    # Try relative to script's parent directory
                    resolved_path = current_dir.parent / master_memory_path
                    if resolved_path.exists():
                        self.master_memory_path = resolved_path.resolve()
                    else:
                        # Use as-is (will fail later with better error message)
                        self.master_memory_path = Path.cwd() / master_memory_path
            else:
                self.master_memory_path = master_memory_path.resolve()
            self.memory.master_memory_path = self.master_memory_path
        
        initial_state = {
            "status": "pending"
        }
        
        result_state = self.workflow.invoke(initial_state)
        
        if result_state.get("status") == "success":
            # Ensure memory is saved one final time
            self.save_memory()
            
            print("\n" + "="*60)
            print("WORKFLOW COMPLETED SUCCESSFULLY")
            print("="*60)
            print(f"\nSummary:")
            print(f"  - Dataset: {self.memory.dataset_name}")
            print(f"  - Target: {self.memory.target_column}")
            print(f"  - Recommendations: {self.memory.recommendations_path}")
            print(f"  - Generated code files: {len(self.memory.generated_code_paths)}")
            print(f"  - Memory saved: {self.memory_file_path}")
            
            return {
                "status": "success",
                "memory": result_state.get("memory_snapshot", self.get_memory()),
                "recommendations": self.memory.model_recommendations,
                "recommendations_path": str(self.memory.recommendations_path) if self.memory.recommendations_path else None,
                "memory_path": str(self.memory_file_path)
            }
        
        error_message = result_state.get("error", "Unknown error")
        print(f"\nERROR: Workflow failed: {error_message}")
        return {
            "status": "error",
            "error": error_message,
            "memory": self.get_memory()
        }
    
    def get_memory(self) -> Dict[str, Any]:
        """
        Get the current workflow memory.
        
        Returns:
            Dictionary containing all stored memory
        """
        base_memory = {
            "master_memory_path": str(self.memory.master_memory_path) if self.memory.master_memory_path else None,
            "dataset_name": self.memory.dataset_name,
            "target_column": self.memory.target_column,
            "context_of_dataset": self.memory.context_of_dataset,
            "report_keys": list(self.memory.report.keys()) if self.memory.report else [],
            "model_recommendations": self.memory.model_recommendations,  # Raw text (for backward compatibility)
            "model_recommendations_structured": self.memory.model_recommendations_structured,  # Structured format
            "recommended_models": self.memory.recommended_models,  # All recommended models (names only)
            "selected_models_for_validation": self.memory.selected_models_for_validation,  # Models selected for validation testing
            "recommendations_path": str(self.memory.recommendations_path) if self.memory.recommendations_path else None,
            "generated_code_paths": self.memory.generated_code_paths,  # Paths to generated validation/testing code
            "validation_metrics": self.memory.validation_metrics,  # Metrics from validation code execution
            "selected_model_for_full_training": self.memory.selected_model_for_full_training,  # Model selected for full training
            # Include file history for easy reference
            "file_history": self.memory.file_history,
        }
        # Include conversation history
        base_memory["conversation_history"] = self.conversation_history
        return base_memory
    
    def save_memory(self, path: Optional[Path] = None):
        """
        Save workflow memory to a JSON file.
        
        Args:
            path: Path to save memory (default: uses memory_file_path - named after agent)
        """
        if path is None:
            # Use memory_file_path if available (named after agent, not dataset)
            if hasattr(self, 'memory_file_path') and self.memory_file_path:
                path = self.memory_file_path
            else:
                # Default to agent-named memory file
                path = self.output_dir / "orchestrator_memory.json"
        
        memory_dict = self.get_memory()
        
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(memory_dict, f, indent=2)
        
        # Update memory_file_path for future saves
        self.memory_file_path = path
        
        # Track memory file in file history
        try:
            self.memory.file_history["orchestrator_memory"] = str(path.resolve())
        except Exception:
            pass
        
        print(f"Orchestrator memory saved to: {path}")
    
    def load_memory(self, path: Path):
        """
        Load workflow memory from a JSON file.
        
        Args:
            path: Path to load memory from
        """
        if not path.exists():
            raise FileNotFoundError(f"Memory file not found: {path}")

        try:
            with path.open("r", encoding="utf-8") as f:
                memory_dict = json.load(f)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Orchestrator memory file is corrupted (invalid JSON): {path}\n"
                f"Error: {exc}\nPlease delete or repair the file and re-run the workflow."
            ) from exc
        
        # Restore memory
        if memory_dict.get("master_memory_path"):
            self.memory.master_memory_path = Path(memory_dict["master_memory_path"])
        self.memory.dataset_name = memory_dict.get("dataset_name")
        self.memory.target_column = memory_dict.get("target_column")
        self.memory.context_of_dataset = memory_dict.get("context_of_dataset")
        
        # Restore file_history if present
        if memory_dict.get("file_history"):
            try:
                self.memory.file_history = dict(memory_dict["file_history"])
            except Exception:
                pass
        
        # Load recommendations if path exists
        if memory_dict.get("recommendations_path") and Path(memory_dict["recommendations_path"]).exists():
            self.memory.recommendations_path = Path(memory_dict["recommendations_path"])
            self.memory.model_recommendations = self.memory.recommendations_path.read_text(encoding="utf-8")
            # Parse recommendations if not already structured
            if not memory_dict.get("model_recommendations_structured"):
                self.memory.model_recommendations_structured = parse_model_recommendations(self.memory.model_recommendations)
            else:
                self.memory.model_recommendations_structured = memory_dict.get("model_recommendations_structured", [])
        
        # Also restore structured recommendations if available in memory dict
        if memory_dict.get("model_recommendations_structured"):
            self.memory.model_recommendations_structured = memory_dict["model_recommendations_structured"]
        
        # Restore recommended models if available
        if memory_dict.get("recommended_models"):
            self.memory.recommended_models = memory_dict["recommended_models"]
        
        # Restore selected models for validation if available
        if memory_dict.get("selected_models_for_validation"):
            self.memory.selected_models_for_validation = memory_dict["selected_models_for_validation"]
        
        # Restore generated code paths if available
        if memory_dict.get("generated_code_paths"):
            self.memory.generated_code_paths = memory_dict["generated_code_paths"]
        
        # Restore validation metrics if available
        if memory_dict.get("validation_metrics"):
            self.memory.validation_metrics = memory_dict["validation_metrics"]
        
        # Restore selected model for full training if available
        if memory_dict.get("selected_model_for_full_training"):
            self.memory.selected_model_for_full_training = memory_dict["selected_model_for_full_training"]
        
        # Restore report if master memory exists
        if self.memory.master_memory_path and self.memory.master_memory_path.exists():
            try:
                with self.memory.master_memory_path.open("r", encoding="utf-8") as f:
                    master_memory = json.load(f)
                self.memory.report = master_memory.get("preprocessing", {}).get("report", {})
            except json.JSONDecodeError as exc:
                print(f"[WARN] Could not reload master_memory.json to restore report (corrupted JSON): {exc}")
        
        print(f"Orchestrator memory loaded from: {path}")


def main():
    """Main entry point for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="AI Agent for LLM Orchestration Workflow"
    )
    parser.add_argument(
        "--master-memory",
        type=Path,
        default=None,
        help="Path to master_memory.json (default: parent directory/master_memory.json)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to save outputs (default: LLM Orchestrator directory)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"LLM model name (default: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default=DEFAULT_ENDPOINT,
        help=f"LLM endpoint URL (default: {DEFAULT_ENDPOINT})"
    )
    parser.add_argument(
        "--save-memory",
        action="store_true",
        help="Save workflow memory to JSON file"
    )
    
    args = parser.parse_args()

    try:
        # Initialize agent
        agent = LLMOrchestratorWorkflowAgent(
            model=args.model,
            endpoint=args.endpoint,
            output_dir=args.output_dir,
            master_memory_path=args.master_memory
        )

        # Run full workflow (memory is automatically saved during workflow)
        result = agent.run_full_workflow()

        # Memory is automatically saved during workflow, but allow explicit save if requested
        if args.save_memory and result["status"] == "success":
            agent.save_memory()
            print("Memory explicitly saved as requested.")

        # Exit with appropriate code
        sys.exit(0 if result["status"] == "success" else 1)

    except FileNotFoundError as exc:
        print(f"\n[ERROR] Required file not found: {exc}")
        print("Make sure the preprocessing step has completed successfully and master_memory.json exists.")
        sys.exit(1)
    except RuntimeError as exc:
        print(f"\n[ERROR] {exc}")
        sys.exit(1)
    except ConnectionError as exc:
        print(f"\n[ERROR] Could not connect to LLM endpoint: {exc}")
        print("Make sure the Ollama server is running (e.g. 'ollama serve') and try again.")
        sys.exit(1)
    except Exception as exc:
        print(f"\n[ERROR] Unexpected error in LLM orchestrator workflow: {type(exc).__name__}: {exc}")
        print("Check the logs above for details. If the problem persists, inspect orchestrator_memory.json.")
        sys.exit(1)


if __name__ == "__main__":
    main()

