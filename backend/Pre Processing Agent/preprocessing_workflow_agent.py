#usage:C:/Users/Administrator/AppData/Local/Programs/Python/Python313/python.exe preprocessing_workflow_agent.py --csv "../Datasets/Housing.csv" --target "price"
"""
AI Agent for Preprocessing Workflow

This agent orchestrates the complete preprocessing workflow:
1. Generate dataset report using report_generator.py
2. Generate preprocessing plan using preprocessing_steps.py
3. Generate preprocessing code using preprocessing_code_generator.py

The agent maintains memory of all steps and their outputs.
"""

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Literal, Optional, TypedDict

from langgraph.graph import END, StateGraph  # type: ignore[import]

# Add current directory to path for imports
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

backend_dir = current_dir.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from llm_config import DEFAULT_LLM_MODEL, DEFAULT_LLM_ENDPOINT
from report_generator import generate_compact_report
from preprocessing_steps import PreprocessingAgent as PreprocessingStepsAgent
from preprocessing_code_generator import PreprocessingCodeAgent
import pandas as pd


def infer_task_type(report: Dict[str, Any], df: "pd.DataFrame", target_column: str) -> str:
    """
    Deterministically infer whether the task is 'regression', 'classification',
    or 'forecasting' from the dataset report and raw dataframe.

    Rules (in priority order):
    1. Forecasting — any feature column is datetime AND target is numeric AND
       rows are time-ordered (monotonic index or date column).
    2. Classification — target is categorical/object/bool, OR target is numeric
       with low unique count (≤ 20 distinct values) AND unique/rows ratio < 0.05.
    3. Regression — everything else (continuous numeric target).
    """
    target_analysis = report.get("target_analysis", {})
    target_type = target_analysis.get("type", "numeric")
    col_summary = report.get("columns", {})
    rows = report.get("dataset_overview", {}).get("rows", 1)

    # --- Forecasting check ---
    has_datetime_feature = any(
        info.get("dtype", "").startswith("datetime")
        or ("min_date" in info and "max_date" in info)
        for info in col_summary.values()
    )
    if has_datetime_feature and target_type == "numeric":
        return "forecasting"

    # --- Classification check ---
    if target_type == "categorical":
        return "classification"

    if target_type == "numeric":
        unique_count = int(df[target_column].nunique())
        if unique_count <= 20 and (unique_count / max(rows, 1)) < 0.05:
            return "classification"

    # --- Regression (default for continuous numeric target) ---
    return "regression"


# Metrics emitted per task type (used to drive both code-gen and parsing)
TASK_METRICS: Dict[str, list] = {
    "regression":     ["MAE", "MSE", "RMSE", "R2"],
    "classification": ["Accuracy", "Precision", "Recall", "F1", "ROC_AUC"],
    "forecasting":    ["MAE", "RMSE", "MAPE"],
}

# Which metric determines the best model (higher is better → positive; lower is better → negative)
TASK_PRIMARY_METRIC: Dict[str, tuple] = {
    "regression":     ("R2",       "higher"),
    "classification": ("F1",       "higher"),
    "forecasting":    ("MAE",      "lower"),
}


@dataclass
class WorkflowMemory:
    """Memory structure to store workflow state and outputs."""
    dataset_path: Optional[Path] = None
    target_column: Optional[str] = None
    dataset_info: Dict[str, Any] = field(default_factory=dict)
    report: Dict[str, Any] = field(default_factory=dict)
    preprocessing_plan: Dict[str, Any] = field(default_factory=dict)
    generated_code: Optional[str] = None
    report_path: Optional[Path] = None
    plan_path: Optional[Path] = None
    code_path: Optional[Path] = None
    # Report for processed_output.csv (generated after preprocessing code runs)
    processed_output_report_path: Optional[Path] = None
    # ---- NEW: history of filenames created by the workflow ----
    file_history: Dict[str, str] = field(default_factory=dict)
    # ---- Task type inferred from report ----
    task_type: Optional[str] = None


class PreprocessingWorkflowAgent:
    """
    AI Agent that orchestrates the preprocessing workflow and maintains memory.
    """
    
    def __init__(
        self,
        model: str = DEFAULT_LLM_MODEL,
        endpoint: str = DEFAULT_LLM_ENDPOINT,
        output_dir: Optional[Path] = None
    ):
        """
        Initialize the workflow agent.
        
        Args:
            model: LLM model name (default: "phi4")
            endpoint: LLM endpoint URL (default: "http://127.0.0.1:11434")
            output_dir: Directory to save outputs (default: current directory)
        """
        self.model = model
        self.endpoint = endpoint
        self.output_dir = Path(output_dir) if output_dir else Path.cwd()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize memory
        self.memory = WorkflowMemory()
        # Simple conversation history for tracking workflow steps
        self.conversation_history: list[Dict[str, str]] = []
        
        # Initialize sub-agents
        self.steps_agent = PreprocessingStepsAgent(model=model, endpoint=endpoint)
        # Code agent will receive dataset path when workflow runs
        self.code_agent = PreprocessingCodeAgent(model=model, endpoint=endpoint)
        
        # Set default paths (will be updated with dataset name in generate_report)
        self.memory.report_path = self.output_dir / "report.json"
        self.memory.plan_path = self.output_dir / "preprocessing_plan.json"
        self.memory.code_path = self.output_dir / "generated_preprocessing_code.py"
        
        # LangGraph workflow
        self.workflow = self._build_workflow_graph()
    
    def generate_report(self, csv_path: Path, target_column: str) -> Dict[str, Any]:
        """
        Step 1: Generate dataset report.
        
        Args:
            csv_path: Path to the CSV dataset
            target_column: Name of the target column
            
        Returns:
            Generated report dictionary
        """
        print("\n" + "="*60)
        print("STEP 1: Generating Dataset Report")
        print("="*60)
        
        # Store in memory
        self.memory.dataset_path = csv_path
        self.memory.target_column = target_column
        
        # Extract dataset name from path (e.g., "Housing.csv" -> "Housing")
        dataset_name = csv_path.stem  # Gets filename without extension
        
        # Update paths with dataset name
        self.memory.report_path = self.output_dir / f"{dataset_name}.json"
        self.memory.plan_path = self.output_dir / f"{dataset_name}_preprocessing_plan.json"
        self.memory.code_path = self.output_dir / f"{dataset_name}_preprocessing_code.py"
        # Default path for processed_output.csv report (generated after preprocessing code runs)
        self.memory.processed_output_report_path = (
            self.output_dir / f"{dataset_name}_processed.json"
        )
        
        # Load dataset
        if not csv_path.exists():
            raise FileNotFoundError(f"Dataset not found: {csv_path}")
        
        df = pd.read_csv(csv_path)
        if target_column not in df.columns:
            raise ValueError(f"Target column '{target_column}' not found in dataset")
        
        # Store dataset info in memory, include absolute path for reproducible access
        self.memory.dataset_info = {
            "path": str(csv_path),
            "absolute_path": str(csv_path.resolve()),
            "rows": len(df),
            "columns": len(df.columns),
            "column_names": list(df.columns),
            "target_column": target_column,
            "dataset_name": dataset_name
        }
        # Track dataset path in file history for downstream helpers
        try:
            self.memory.file_history["dataset"] = str(csv_path.resolve())
        except Exception:
            pass
        
        print(f"Dataset: {csv_path}")
        print(f"Rows: {len(df)}, Columns: {len(df.columns)}")
        print(f"Target column: {target_column}")
        
        # Generate report using report_generator
        report = generate_compact_report(df, target_column)

        # Infer and store task type
        self.memory.task_type = infer_task_type(report, df, target_column)
        report["task_type"] = self.memory.task_type
        print(f"  - Inferred task type: {self.memory.task_type}")

        # Store report in memory
        self.memory.report = report
        
        # Save report to file
        self.memory.report_path.parent.mkdir(parents=True, exist_ok=True)
        with self.memory.report_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        
        # ---- NEW: record filename in file_history ----
        try:
            self.memory.file_history["report"] = str(self.memory.report_path.resolve())
        except Exception:
            pass
        
        print(f"\nReport generated and saved to: {self.memory.report_path}")
        print(f"Report summary:")
        print(f"  - Dataset size: {report['dataset_overview']['rows']} rows, "
              f"{report['dataset_overview']['columns']} columns")
        print(f"  - Target type: {report['target_analysis']['type']}")
        if report.get('llm_flags'):
            print(f"  - Flags: {', '.join(report['llm_flags'])}")
        
        return report
    
    def generate_preprocessing_plan(self) -> Dict[str, Any]:
        """
        Step 2: Generate preprocessing plan from report.
        
        Returns:
            Generated preprocessing plan dictionary
        """
        print("\n" + "="*60)
        print("STEP 2: Generating Preprocessing Plan")
        print("="*60)
        
        # Check if report exists
        if not self.memory.report_path.exists():
            raise FileNotFoundError(
                f"Report not found: {self.memory.report_path}. "
                "Run generate_report() first."
            )
        
        # Load report
        with self.memory.report_path.open("r", encoding="utf-8") as f:
            report = json.load(f)
        
        # Ensure memory is up to date
        self.memory.report = report
        
        print(f"Using report from: {self.memory.report_path}")
        print("Querying LLM for preprocessing plan...")
        
        # Convert report to JSON string for LLM
        metadata_json = json.dumps(report, indent=2)
        
        # Query LLM for preprocessing plan
        response = self.steps_agent.run(metadata_json)
        
        print("\nLLM Response received.")
        
        # Try to parse JSON response
        try:
            plan_dict = json.loads(response)
            self.memory.preprocessing_plan = plan_dict
        except json.JSONDecodeError:
            # If not valid JSON, try to extract JSON from response
            print("Warning: Response is not valid JSON. Attempting to extract JSON...")
            # Save raw response first
            raw_path = self.memory.plan_path.with_suffix('.raw.txt')
            raw_path.write_text(response, encoding="utf-8")
            print(f"Raw response saved to: {raw_path}")
            
            # Try to find JSON block in response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                try:
                    plan_dict = json.loads(json_match.group())
                    self.memory.preprocessing_plan = plan_dict
                except json.JSONDecodeError:
                    raise ValueError("Could not parse JSON from LLM response")
            else:
                raise ValueError("No JSON found in LLM response")
        
        # Save preprocessing plan
        self.memory.plan_path.parent.mkdir(parents=True, exist_ok=True)
        with self.memory.plan_path.open("w", encoding="utf-8") as f:
            json.dump(plan_dict, f, indent=2)
        
        # ---- NEW: record filename in file_history ----
        try:
            self.memory.file_history["preprocessing_plan"] = str(self.memory.plan_path.resolve())
        except Exception:
            pass
        
        print(f"\nPreprocessing plan saved to: {self.memory.plan_path}")
        
        # Display plan summary
        if 'preprocessing_steps' in plan_dict:
            steps = plan_dict['preprocessing_steps']
            print(f"\nPreprocessing plan contains {len(steps)} steps:")
            for i, step in enumerate(steps, 1):
                print(f"  {i}. {step.get('step', 'Unknown step')}")
                if step.get('columns'):
                    print(f"     Columns: {', '.join(step['columns'])}")
        
        return plan_dict
    
    def generate_preprocessing_code(self) -> str:
        """
        Step 3: Generate preprocessing code from plan.
        
        Returns:
            Generated preprocessing code as string
        """
        print("\n" + "="*60)
        print("STEP 3: Generating Preprocessing Code")
        print("="*60)
        
        # Check if plan exists
        if not self.memory.plan_path.exists():
            raise FileNotFoundError(
                f"Preprocessing plan not found: {self.memory.plan_path}. "
                "Run generate_preprocessing_plan() first."
            )
        
        # Check if dataset path is available in memory
        if not self.memory.dataset_path:
            raise ValueError(
                "Dataset path not found in memory. "
                "Run generate_report() first to set dataset path."
            )
        
        # Load preprocessing plan
        with self.memory.plan_path.open("r", encoding="utf-8") as f:
            plan = json.load(f)
        
        # Ensure memory is up to date
        self.memory.preprocessing_plan = plan
        
        print(f"Using preprocessing plan from: {self.memory.plan_path}")
        print(f"Using dataset: {self.memory.dataset_path}")
        print("Querying LLM for preprocessing code...")
        
        # Convert plan to JSON string for LLM
        plan_json = json.dumps(plan, indent=2)
        
        # Query LLM for code, passing the dataset path from workflow memory
        code = self.code_agent.run(plan_json, dataset_path=self.memory.dataset_path)
        
        # Store code in memory
        self.memory.generated_code = code
        
        # Save code to file
        self.memory.code_path.parent.mkdir(parents=True, exist_ok=True)
        self.memory.code_path.write_text(code, encoding="utf-8")
        
        # ---- NEW: record filename in file_history ----
        try:
            self.memory.file_history["generated_code"] = str(self.memory.code_path.resolve())
        except Exception:
            pass
        
        print(f"\nPreprocessing code saved to: {self.memory.code_path}")
        print(f"Code length: {len(code)} characters")
        print(f"Generated code will load dataset: {self.memory.dataset_path.name}")

        # Execute and auto-fix code if needed
        self._run_generated_code_with_llm()
        
        return code

    def _run_generated_code_with_llm(self) -> None:
        """
        Execute the generated preprocessing code and auto-fix issues via LLM if needed.
        """
        script_path = current_dir / "run_preprocessing_with_llm.py"
        if not script_path.exists():
            print(f"[WARN] Auto-run script not found: {script_path}. Skipping execution.")
            return

        # Ensure workflow memory is persisted for the helper script
        memory_file = current_dir / "workflow_memory.json"
        self.save_memory(memory_file)

        print("\n" + "-" * 60)
        print("Running generated preprocessing script with self-healing helper...")
        try:
            subprocess.run([sys.executable, str(script_path)], check=True)
            print("Generated preprocessing script executed successfully.")
            # After successful execution, generate report for processed_output.csv if available
            self._generate_processed_output_report()
            # Persist updated memory (including processed_output report path)
            self.save_memory(memory_file)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "Execution helper failed to run generated preprocessing script."
            ) from exc
        finally:
            print("-" * 60 + "\n")

    def _generate_processed_output_report(self) -> None:
        """
        Generate a dataset report for the processed_output.csv created by the
        generated preprocessing code and save it as a separate JSON file.
        """
        processed_csv = self.output_dir / "processed_output.csv"
        if not processed_csv.exists():
            processed_csv = current_dir / "processed_output.csv"
        if not processed_csv.exists():
            print(f"[WARN] Processed output CSV not found. Skipping processed report generation.")
            return

        if not self.memory.target_column:
            print("[WARN] target_column missing in workflow memory. Cannot generate processed report.")
            return

        # Load processed CSV and generate a new compact report
        df_processed = pd.read_csv(processed_csv)
        if self.memory.target_column not in df_processed.columns:
            print(f"[WARN] Target column '{self.memory.target_column}' not found in processed_output.csv. Skipping processed report generation.")
            return

        print("\n" + "=" * 60)
        print("STEP 4: Generating Report for processed_output.csv")
        print("=" * 60)

        processed_report = generate_compact_report(df_processed, self.memory.target_column)

        # Determine path to save processed report
        if not self.memory.processed_output_report_path:
            # Fallback: use dataset name from dataset_info or filename stem
            dataset_name = self.memory.dataset_info.get("dataset_name") or processed_csv.stem
            self.memory.processed_output_report_path = (
                self.output_dir / f"{dataset_name}_processed.json"
            )

        self.memory.processed_output_report_path.parent.mkdir(parents=True, exist_ok=True)
        with self.memory.processed_output_report_path.open("w", encoding="utf-8") as f:
            json.dump(processed_report, f, indent=2)

        # Track processed report path in file history
        try:
            self.memory.file_history["processed_output_report"] = str(
                self.memory.processed_output_report_path.resolve()
            )
        except Exception:
            pass

        print(f"Processed output report saved to: {self.memory.processed_output_report_path}")
    
    def _build_workflow_graph(self):
        """
        Build a LangGraph state graph that coordinates the workflow.
        """
        class WorkflowState(TypedDict, total=False):
            dataset_path: str
            target_column: str
            report: Dict[str, Any]
            plan: Dict[str, Any]
            code: str
            status: Literal["pending", "ok", "error", "success"]
            error: str
            memory_snapshot: Dict[str, Any]
        
        state_graph = StateGraph(WorkflowState)
        state_graph.add_node("generate_report", self._graph_generate_report)
        state_graph.add_node("generate_plan", self._graph_generate_plan)
        state_graph.add_node("generate_code", self._graph_generate_code)
        state_graph.add_node("persist_memory", self._graph_finalize_memory)
        
        state_graph.set_entry_point("generate_report")
        state_graph.add_conditional_edges(
            "generate_report",
            self._status_router,
            {"error": END, "ok": "generate_plan"}
        )
        state_graph.add_conditional_edges(
            "generate_plan",
            self._status_router,
            {"error": END, "ok": "generate_code"}
        )
        state_graph.add_conditional_edges(
            "generate_code",
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
    
    def _add_memory_entry(self, user_text: str, ai_text: str) -> None:
        """
        Store a conversational trace for transparency/debugging.
        """
        self.conversation_history.append({
            "input": user_text,
            "output": ai_text
        })
    
    def _graph_generate_report(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph node: generate dataset report.
        """
        csv_path = Path(state["dataset_path"])
        target_column = state["target_column"]
        try:
            report = self.generate_report(csv_path, target_column)
            flags = report.get("llm_flags", [])
            summary = (
                f"Report created with {len(report.get('columns', {}))} columns. "
                f"Flags: {', '.join(flags) if flags else 'none'}."
            )
            self._add_memory_entry(
                f"Generate report for {csv_path.name}",
                summary
            )
            return {
                "report": report,
                "status": "ok",
                "error": ""
            }
        except Exception as exc:
            error_message = f"Report generation failed: {exc}"
            self._add_memory_entry(
                f"Generate report for {csv_path.name}",
                error_message
            )
            return {"status": "error", "error": error_message}
    
    def _graph_generate_plan(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph node: generate preprocessing plan from report.
        """
        try:
            plan = self.generate_preprocessing_plan()
            steps = len(plan.get("preprocessing_steps", []))
            self._add_memory_entry(
                "Create preprocessing plan",
                f"Plan ready with {steps} steps."
            )
            return {
                "plan": plan,
                "status": "ok",
                "error": ""
            }
        except Exception as exc:
            error_message = f"Plan generation failed: {exc}"
            self._add_memory_entry(
                "Create preprocessing plan",
                error_message
            )
            return {"status": "error", "error": error_message}
    
    def _graph_generate_code(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph node: generate preprocessing code from plan.
        """
        try:
            code = self.generate_preprocessing_code()
            code_len = len(code) if code else 0
            self._add_memory_entry(
                "Generate preprocessing code",
                f"Code generated with {code_len} characters."
            )
            return {
                "code": code,
                "status": "ok",
                "error": ""
            }
        except Exception as exc:
            error_message = f"Code generation failed: {exc}"
            self._add_memory_entry(
                "Generate preprocessing code",
                error_message
            )
            return {"status": "error", "error": error_message}
    
    def _graph_finalize_memory(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Final LangGraph node: capture memory snapshot.
        """
        snapshot = self.get_memory()
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
        csv_path: Path,
        target_column: str
    ) -> Dict[str, Any]:
        """
        Run the complete preprocessing workflow using LangGraph.
        """
        print("\n" + "="*60)
        print("PREPROCESSING WORKFLOW AGENT - FULL WORKFLOW")
        print("="*60)
        
        initial_state = {
            "dataset_path": str(csv_path),
            "target_column": target_column,
            "status": "pending"
        }
        
        result_state = self.workflow.invoke(initial_state)
        
        if result_state.get("status") == "success":
            print("\n" + "="*60)
            print("WORKFLOW COMPLETED SUCCESSFULLY")
            print("="*60)
            print(f"\nSummary:")
            print(f"  - Dataset: {self.memory.dataset_path}")
            print(f"  - Target: {self.memory.target_column}")
            print(f"  - Report: {self.memory.report_path}")
            print(f"  - Plan: {self.memory.plan_path}")
            print(f"  - Code: {self.memory.code_path}")
            
            return {
                "status": "success",
                "memory": result_state.get("memory_snapshot", self.get_memory()),
                "report": self.memory.report,
                "plan": self.memory.preprocessing_plan,
                "code_length": len(self.memory.generated_code) if self.memory.generated_code else 0
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
            "dataset_path": str(self.memory.dataset_path) if self.memory.dataset_path else None,
            "target_column": self.memory.target_column,
            "task_type": self.memory.task_type,
            "dataset_info": self.memory.dataset_info,
            "report": self.memory.report,
            "preprocessing_plan": self.memory.preprocessing_plan,
            "generated_code_length": len(self.memory.generated_code) if self.memory.generated_code else 0,
            "report_path": str(self.memory.report_path) if self.memory.report_path else None,
            "plan_path": str(self.memory.plan_path) if self.memory.plan_path else None,
            "code_path": str(self.memory.code_path) if self.memory.code_path else None,
            "processed_output_report_path": str(self.memory.processed_output_report_path) if self.memory.processed_output_report_path else None,
            # ---- NEW: include file history for easy reference ----
            "file_history": self.memory.file_history,
        }
        # Include conversation history
        base_memory["conversation_history"] = self.conversation_history
        return base_memory
    
    def save_memory(self, path: Optional[Path] = None):
        """
        Save workflow memory to a JSON file.
        
        Args:
            path: Path to save memory (default: output_dir/memory.json)
        """
        if path is None:
            path = self.output_dir / "workflow_memory.json"
        
        memory_dict = self.get_memory()
        # Don't save full code in memory file (too large)
        if "generated_code" in memory_dict:
            memory_dict["generated_code_length"] = len(self.memory.generated_code) if self.memory.generated_code else 0
        
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(memory_dict, f, indent=2)
        
        print(f"Memory saved to: {path}")
    
    def load_memory(self, path: Path):
        """
        Load workflow memory from a JSON file.
        
        Args:
            path: Path to load memory from
        """
        if not path.exists():
            raise FileNotFoundError(f"Memory file not found: {path}")
        
        with path.open("r", encoding="utf-8") as f:
            memory_dict = json.load(f)
        
        # Restore memory
        if memory_dict.get("dataset_path"):
            self.memory.dataset_path = Path(memory_dict["dataset_path"])
        self.memory.target_column = memory_dict.get("target_column")
        self.memory.task_type = memory_dict.get("task_type")
        self.memory.dataset_info = memory_dict.get("dataset_info", {})
        
        # Restore file_history if present
        if memory_dict.get("file_history"):
            try:
                self.memory.file_history = dict(memory_dict["file_history"])
            except Exception:
                pass
        
        # Load report if path exists
        if memory_dict.get("report_path") and Path(memory_dict["report_path"]).exists():
            self.memory.report_path = Path(memory_dict["report_path"])
            with self.memory.report_path.open("r", encoding="utf-8") as f:
                self.memory.report = json.load(f)
        
        # Load plan if path exists
        if memory_dict.get("plan_path") and Path(memory_dict["plan_path"]).exists():
            self.memory.plan_path = Path(memory_dict["plan_path"])
            with self.memory.plan_path.open("r", encoding="utf-8") as f:
                self.memory.preprocessing_plan = json.load(f)
        
        # Load code path if present
        if memory_dict.get("code_path"):
            self.memory.code_path = Path(memory_dict["code_path"])
            if self.memory.code_path.exists():
                self.memory.generated_code = self.memory.code_path.read_text(encoding="utf-8")
        # Restore processed_output report path if present
        if memory_dict.get("processed_output_report_path"):
            self.memory.processed_output_report_path = Path(memory_dict["processed_output_report_path"])
        
        print(f"Memory loaded from: {path}")


def main():
    """Main entry point for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="AI Agent for Preprocessing Workflow"
    )
    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="Path to the CSV dataset"
    )
    parser.add_argument(
        "--target",
        type=str,
        required=True,
        help="Name of the target column"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to save outputs (default: current directory)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_LLM_MODEL,
        help=f"LLM model name (default: {DEFAULT_LLM_MODEL})"
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default=DEFAULT_LLM_ENDPOINT,
        help=f"LLM endpoint URL (default: {DEFAULT_LLM_ENDPOINT})"
    )
    parser.add_argument(
        "--save-memory",
        action="store_true",
        help="Save workflow memory to JSON file"
    )
    
    args = parser.parse_args()
    
    # Initialize agent
    agent = PreprocessingWorkflowAgent(
        model=args.model,
        endpoint=args.endpoint,
        output_dir=args.output_dir
    )
    
    # Run full workflow
    result = agent.run_full_workflow(args.csv, args.target)
    
    # Save memory if requested
    if args.save_memory:
        agent.save_memory()
    
    # Exit with appropriate code
    sys.exit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
