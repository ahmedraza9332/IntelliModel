# usage: python "Improvement Agent/improvement_workflow_agent.py"
"""
AI Agent for Improvement Workflow

Orchestrates the improvement workflow:

  1. load_memory        — Load master_memory.json; ask user which model to improve.
  2. generate_steps     — Generate improvement steps via LLM.
  3. generate_code      — Generate improved validation code (improved_code_gen.py).
  4. run_improved_code  — Execute the generated code and compare metrics
                          (improved_code_runner.py).
  5. decision_loop      — Show before/after to user:
       a. Satisfied → proceed to full training (deployment path).
       b. Not satisfied → re-run improvement OR select a different model
          (no fixed cycle limit).
  6. persist_memory     — Write final state to improvement_memory.json and
                          master_memory.json.

Per-dataset folder isolation:
  All outputs (improvement_steps.txt, improved_training/, Improved_code_running/,
  improvement_memory.json) are written under a dataset-scoped subdirectory:
    <ImprovementAgent dir>/<dataset_name>/
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Literal, Optional, TypedDict

from langgraph.graph import END, StateGraph  # type: ignore[import]

current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent

if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from improvement_steps_generator import (  # type: ignore[import]
    get_improvement_steps,
    read_file,
    compare_metrics,
    DEFAULT_MODEL,
    DEFAULT_ENDPOINT,
)


class MetricsAlreadyGoodError(Exception):
    """Raised when baseline metrics are already above the excellence threshold.

    This is a sentinel — caught by the graph node to route directly to
    persist_memory without generating improvement steps or code.
    """


@dataclass
class ImprovementMemory:
    """Memory structure to store improvement workflow state and outputs."""

    master_memory_path: Optional[Path] = None
    dataset_name: Optional[str] = None
    model_name: Optional[str] = None
    task_type: Optional[str] = None
    validation_metrics: Dict[str, Any] = field(default_factory=dict)
    dataset_context: Optional[str] = None
    validation_code_path: Optional[Path] = None
    dataset_report_path: Optional[Path] = None
    improvement_steps: Optional[str] = None
    improvement_steps_path: Optional[Path] = None
    improved_validation_code_path: Optional[Path] = None
    improved_validation_metrics: Dict[str, Any] = field(default_factory=dict)
    regeneration_count: int = 0
    user_satisfied: Optional[bool] = None
    proceed_to_deployment: bool = False
    file_history: Dict[str, str] = field(default_factory=dict)


class ImprovementWorkflowAgent:
    """
    AI Agent that orchestrates the improvement workflow and maintains memory.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        endpoint: str = DEFAULT_ENDPOINT,
        output_dir: Optional[Path] = None,
        master_memory_path: Optional[Path] = None,
    ):
        self.model = model
        self.endpoint = endpoint

        # Resolve master memory path
        if master_memory_path:
            master_memory_path = Path(master_memory_path)
            if not master_memory_path.is_absolute():
                for base in [Path.cwd(), project_root]:
                    candidate = base / master_memory_path
                    if candidate.exists():
                        master_memory_path = candidate.resolve()
                        break
                else:
                    master_memory_path = (Path.cwd() / master_memory_path).resolve()
            else:
                master_memory_path = master_memory_path.resolve()
        else:
            master_memory_path = project_root / "master_memory.json"

        self.master_memory_path = master_memory_path

        # Initialize memory
        self.memory = ImprovementMemory()
        self.memory.master_memory_path = self.master_memory_path

        self.conversation_history: list[Dict[str, str]] = []

        # Output dir will be set after dataset_name is loaded (per-dataset folder)
        self._requested_output_dir = Path(output_dir) if output_dir else None
        self.output_dir: Optional[Path] = None
        self.memory_file_path: Optional[Path] = None

        self.workflow = self._build_workflow_graph()

    # ======================================================================
    # PER-DATASET FOLDER SETUP
    # ======================================================================

    def _init_output_dir(self, dataset_name: Optional[str]) -> None:
        """Set up a per-dataset output directory under the Improvement Agent folder."""
        if self._requested_output_dir:
            base = self._requested_output_dir
        else:
            base = current_dir

        if dataset_name:
            safe = dataset_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
            self.output_dir = base / safe
        else:
            self.output_dir = base / "default_dataset"

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.memory.improvement_steps_path = self.output_dir / "improvement_steps.txt"
        self.memory_file_path = self.output_dir / "improvement_memory.json"

    # ======================================================================
    # STEP 1: LOAD MASTER MEMORY
    # ======================================================================

    def load_master_memory(self) -> Dict[str, Any]:
        """Step 1: Load master memory and extract required information."""
        print("\n" + "=" * 60)
        print("IMPROVEMENT WORKFLOW - STEP 1: Loading Master Memory")
        print("=" * 60)

        if not self.master_memory_path or not self.master_memory_path.exists():
            raise FileNotFoundError(
                f"Master memory file not found: {self.master_memory_path}"
            )

        with self.master_memory_path.open("r", encoding="utf-8") as f:
            master_memory = json.load(f)

        # Dataset name for folder scoping
        dataset_name = master_memory.get("dataset_name") or master_memory.get("name") or "dataset"
        self.memory.dataset_name = dataset_name
        self._init_output_dir(dataset_name)

        # Extract dataset context
        self.memory.dataset_context = master_memory.get("context_of_dataset")

        # Extract task_type
        preprocessing = master_memory.get("preprocessing", {})
        report_json = preprocessing.get("report", {})
        self.memory.task_type = (
            master_memory.get("task_type")
            or report_json.get("task_type")
            or "regression"
        )

        # Extract preprocessing report path
        report_path_str = preprocessing.get("report_path")
        if report_path_str:
            self.memory.dataset_report_path = Path(report_path_str)

        # Extract validation info from LLM orchestrator memory
        llm_orch = master_memory.get("llm_orchestrator", {})
        orch_mem = llm_orch.get("orchestrator_memory", {})

        selected_models = orch_mem.get("selected_models_for_validation", [])
        validation_metrics_full = orch_mem.get("validation_metrics", {})

        if not selected_models:
            raise ValueError(
                "No models were selected for validation testing. Cannot perform improvement."
            )

        # Ask user which model to improve
        print("\nAvailable models for improvement:")
        for idx, model_name in enumerate(selected_models, 1):
            metrics = validation_metrics_full.get(model_name, {}).get("metrics", {})
            print(f"  {idx}. {model_name}")
            if metrics:
                print(f"     Current metrics: {metrics}")

        while True:
            try:
                choice = input(
                    f"\nSelect model to improve (1-{len(selected_models)}): "
                ).strip()
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(selected_models):
                    selected_model = selected_models[choice_idx]
                    break
                print(f"Please enter a number between 1 and {len(selected_models)}")
            except ValueError:
                print("Please enter a valid number")
            except (EOFError, KeyboardInterrupt):
                raise ValueError("User cancelled model selection")

        self.memory.model_name = selected_model

        if selected_model in validation_metrics_full:
            info = validation_metrics_full[selected_model]
            self.memory.validation_metrics = info.get("metrics", {}) or {}
            code_path_str = info.get("code_path")
            if code_path_str:
                self.memory.validation_code_path = Path(code_path_str)

        # Store dataset report path if only report JSON exists (no file path)
        if not self.memory.dataset_report_path and report_json:
            # Write the report JSON to disk for the runner
            report_out = self.output_dir / "dataset_report.json"
            report_out.write_text(json.dumps(report_json, indent=2), encoding="utf-8")
            self.memory.dataset_report_path = report_out

        # Validation
        if not self.memory.validation_metrics:
            raise ValueError(f"Validation metrics for {selected_model} not found")
        if not self.memory.dataset_context:
            raise ValueError("context_of_dataset not found in master memory")
        if not self.memory.validation_code_path:
            raise ValueError(f"Validation code path for {selected_model} not found")

        print(f"\nSelected model: {self.memory.model_name}")
        print(f"Task type: {self.memory.task_type}")
        print(f"Baseline metrics: {self.memory.validation_metrics}")
        print(f"Output directory: {self.output_dir}")

        self.save_memory()
        return master_memory

    # ======================================================================
    # METRICS QUALITY CHECK (before generating steps)
    # ======================================================================

    # Thresholds above which improvement is unnecessary
    _GOOD_ENOUGH_THRESHOLDS = {
        "R2":       ("higher", 0.97),
        "Accuracy": ("higher", 0.97),
        "F1":       ("higher", 0.97),
        "ROC_AUC":  ("higher", 0.97),
        "MAE":      ("lower",  None),   # no absolute threshold for error metrics
        "RMSE":     ("lower",  None),
        "MAPE":     ("lower",  None),
    }

    def _metrics_are_good_enough(self) -> tuple[bool, str]:
        """
        Return (True, reason_message) if the baseline metrics are already
        good enough that improvement is unnecessary (≥ 0.97 for quality metrics).
        """
        metrics = self.memory.validation_metrics or {}
        for key, (direction, threshold) in self._GOOD_ENOUGH_THRESHOLDS.items():
            if threshold is None:
                continue
            val = metrics.get(key)
            if val is None:
                continue
            try:
                val = float(val)
            except (TypeError, ValueError):
                continue
            if direction == "higher" and val >= threshold:
                return True, (
                    f"✅ Metrics are already excellent — {key} = {val:.4f} "
                    f"(threshold ≥ {threshold}). No improvement needed."
                )
        return False, ""

    # ======================================================================
    # STEP 2: GENERATE IMPROVEMENT STEPS
    # ======================================================================

    def generate_improvement_steps(self) -> str:
        """Step 2: Generate improvement steps using the LLM."""
        print("\n" + "=" * 60)
        print("IMPROVEMENT WORKFLOW - STEP 2: Generating Improvement Steps")
        print("=" * 60)

        # ── Early-exit: metrics already excellent ──────────────────────────
        good_enough, reason = self._metrics_are_good_enough()
        if good_enough:
            print(f"\n{reason}")
            # Write an informational steps file so downstream paths don't break
            self.memory.improvement_steps = reason
            self.memory.improvement_steps_path.parent.mkdir(parents=True, exist_ok=True)
            self.memory.improvement_steps_path.write_text(reason, encoding="utf-8")
            self.memory.user_satisfied = True
            self.memory.proceed_to_deployment = True
            self.save_memory()
            # Use a special status string recognised by the graph router
            raise MetricsAlreadyGoodError(reason)

        validation_code = read_file(str(self.memory.validation_code_path))
        dataset_report = read_file(str(self.memory.dataset_report_path))

        if validation_code is None or dataset_report is None:
            raise RuntimeError("Failed to read validation code or dataset report.")

        steps_text = get_improvement_steps(
            model_name=self.memory.model_name,
            validation_metrics=self.memory.validation_metrics,
            validation_code=validation_code,
            dataset_report=dataset_report,
            dataset_context=self.memory.dataset_context,
            model=self.model,
            endpoint=self.endpoint,
        )

        self.memory.improvement_steps = steps_text
        self.memory.improvement_steps_path.parent.mkdir(parents=True, exist_ok=True)
        self.memory.improvement_steps_path.write_text(steps_text, encoding="utf-8")

        print("\n=== IMPROVEMENT STEPS ===")
        print(steps_text)
        print("=========================\n")

        self.save_memory()
        return steps_text

    # ======================================================================
    # STEP 3: GENERATE IMPROVED VALIDATION CODE
    # ======================================================================

    def run_improved_code_generation(self) -> Optional[Path]:
        """Step 3: Run improved_code_gen.py to generate improved validation code."""
        import subprocess

        print("\n" + "=" * 60)
        print("IMPROVEMENT WORKFLOW - STEP 3: Generating Improved Validation Code")
        print("=" * 60)

        improved_script = current_dir / "improved_code_gen.py"
        if not improved_script.exists():
            print(f"[WARN] improved_code_gen.py not found: {improved_script}. Skipping.")
            return None

        cmd_gen = [sys.executable, str(improved_script)]
        if self.memory_file_path and self.memory_file_path.exists():
            cmd_gen.extend(["--memory", str(self.memory_file_path.resolve())])
            print(f"[INFO] Passing memory path to code gen: {self.memory_file_path}")
        else:
            print("[WARN] No memory_file_path available — improved_code_gen will use auto-discovery.")

        try:
            subprocess.run(
                cmd_gen,
                cwd=str(project_root),
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError("improved_code_gen.py failed.") from exc

        # Reload memory to pick up improved_validation_code_path
        if self.memory_file_path and self.memory_file_path.exists():
            try:
                with self.memory_file_path.open("r", encoding="utf-8") as f:
                    refreshed = json.load(f)
                updated = refreshed.get("improved_validation_code_path")
                if updated:
                    self.memory.improved_validation_code_path = Path(updated)
            except Exception as exc:
                print(f"[WARN] Could not reload memory after code gen: {exc}")

        # Fallback: search for generated file
        if not self.memory.improved_validation_code_path or \
                not self.memory.improved_validation_code_path.exists():
            if self.memory.model_name:
                safe = self.memory.model_name.lower().replace(" ", "_").replace("-", "_")
                # Check both the current_dir/improved_training and dataset-scoped dir
                candidates = [
                    current_dir / "improved_training" / f"{safe}_improved_validation.py",
                    self.output_dir / "improved_training" / f"{safe}_improved_validation.py",
                ]
                for c in candidates:
                    if c.exists():
                        self.memory.improved_validation_code_path = c.resolve()
                        break

        if self.memory.improved_validation_code_path and \
                self.memory.improved_validation_code_path.exists():
            print(f"[INFO] Improved code at: {self.memory.improved_validation_code_path}")
            return self.memory.improved_validation_code_path

        print("[WARN] Improved validation code not found after code generation.")
        return None

    # ======================================================================
    # STEP 4: RUN IMPROVED CODE AND CAPTURE METRICS
    # ======================================================================

    def run_improved_code_runner(self) -> Optional[Dict[str, Any]]:
        """Step 4: Run improved_code_runner.py to execute and compare metrics."""
        import subprocess

        print("\n" + "=" * 60)
        print("IMPROVEMENT WORKFLOW - STEP 4: Running Improved Validation Code")
        print("=" * 60)

        self.save_memory()

        runner_script = current_dir / "improved_code_runner.py"
        if not runner_script.exists():
            print(f"[WARN] improved_code_runner.py not found: {runner_script}. Skipping.")
            return None

        cmd: list[str] = [sys.executable, str(runner_script)]
        if self.memory_file_path and self.memory_file_path.exists():
            cmd.extend(["--memory", str(self.memory_file_path.resolve())])

        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=False,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            print(f"[WARN] improved_code_runner.py exited with code {result.returncode}.")

        # Read back metrics
        improved_metrics = {}
        if self.memory_file_path and self.memory_file_path.exists():
            try:
                with self.memory_file_path.open("r", encoding="utf-8") as f:
                    refreshed = json.load(f)
                improved_metrics = refreshed.get("improved_validation_metrics") or {}
                if improved_metrics:
                    self.memory.improved_validation_metrics = improved_metrics
                    updated_code = refreshed.get("improved_validation_code_path")
                    if updated_code:
                        self.memory.improved_validation_code_path = Path(updated_code)
            except Exception as exc:
                print(f"[WARN] Could not read improved metrics: {exc}")

        return improved_metrics or None

    # ======================================================================
    # STEP 5: USER DECISION LOOP
    # ======================================================================

    def run_decision_loop(self) -> str:
        """
        Step 5: Show before/after metrics and ask the user what to do.

        Returns one of:
          'deploy'          — user is satisfied, proceed to full training
          'regenerate'      — user wants another improvement cycle
          'select_model'    — user wants to pick a different model
        """
        baseline = self.memory.validation_metrics
        improved = self.memory.improved_validation_metrics
        task_type = self.memory.task_type or "regression"

        print("\n" + "=" * 65)
        print("  IMPROVEMENT RESULTS")
        print("=" * 65)

        if improved and baseline:
            comparison = compare_metrics(baseline, improved, task_type=task_type)
            print(comparison["summary"])
        elif improved:
            print(f"Improved metrics: {improved}")
        else:
            print("⚠️  No improved metrics were captured.")

        print(f"\n  Improvement runs so far: {self.memory.regeneration_count}\n")

        print("What would you like to do?")
        print("  a. Proceed to full training / deployment (satisfied)")
        print("  b. Try another improvement cycle")
        print("  c. Select a different model")

        while True:
            try:
                choice = input("\nEnter choice (a/b/c): ").strip().lower()
                if choice == "a":
                    self.memory.user_satisfied = True
                    self.memory.proceed_to_deployment = True
                    return "deploy"
                elif choice == "b":
                    self.memory.user_satisfied = False
                    self.memory.regeneration_count += 1
                    return "regenerate"
                elif choice == "c":
                    self.memory.user_satisfied = False
                    return "select_model"
                else:
                    print("Please enter a, b, or c.")
            except (EOFError, KeyboardInterrupt):
                print("\nUsing default: proceed to deployment.")
                self.memory.user_satisfied = True
                self.memory.proceed_to_deployment = True
                return "deploy"

    # ======================================================================
    # WORKFLOW GRAPH
    # ======================================================================

    def _build_workflow_graph(self):
        class WorkflowState(TypedDict, total=False):
            master_memory: Dict[str, Any]
            improvement_steps: str
            improved_validation_code_path: Optional[str]
            improved_validation_metrics: Optional[Dict[str, Any]]
            decision: str
            status: Literal["pending", "ok", "error", "success"]
            error: str
            memory_snapshot: Dict[str, Any]

        state_graph = StateGraph(WorkflowState)

        state_graph.add_node("load_memory", self._graph_load_memory)
        state_graph.add_node("generate_improvements", self._graph_generate_improvements)
        state_graph.add_node("generate_improved_code", self._graph_generate_improved_code)
        state_graph.add_node("run_improved_code", self._graph_run_improved_code)
        state_graph.add_node("decision_loop", self._graph_decision_loop)
        state_graph.add_node("persist_memory", self._graph_finalize_memory)

        state_graph.set_entry_point("load_memory")

        state_graph.add_conditional_edges(
            "load_memory",
            self._status_router,
            {"error": END, "ok": "generate_improvements"},
        )
        state_graph.add_conditional_edges(
            "generate_improvements",
            # If metrics were already good (skip_improvement=True), jump straight to deploy
            lambda s: "persist_memory" if s.get("skip_improvement") else (
                "error" if s.get("status") == "error" else "generate_improved_code"
            ),
            {"error": END, "generate_improved_code": "generate_improved_code",
             "persist_memory": "persist_memory"},
        )
        state_graph.add_conditional_edges(
            "generate_improved_code",
            self._status_router,
            {"error": END, "ok": "run_improved_code"},
        )
        state_graph.add_conditional_edges(
            "run_improved_code",
            self._status_router,
            {"error": END, "ok": "decision_loop"},
        )
        state_graph.add_conditional_edges(
            "decision_loop",
            self._decision_router,
            {
                "deploy": "persist_memory",
                "regenerate": "generate_improvements",
                "select_model": "load_memory",
                "error": END,
            },
        )
        state_graph.add_edge("persist_memory", END)

        return state_graph.compile()

    @staticmethod
    def _status_router(state: Dict[str, Any]) -> str:
        return "error" if state.get("status") == "error" else "ok"

    @staticmethod
    def _decision_router(state: Dict[str, Any]) -> str:
        return state.get("decision", "deploy")

    def _add_memory_entry(self, user_text: str, ai_text: str) -> None:
        self.conversation_history.append({"input": user_text, "output": ai_text})

    # ------------------------------------------------------------------
    # Graph nodes
    # ------------------------------------------------------------------

    def _graph_load_memory(self, state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            master_memory = self.load_master_memory()
            self._add_memory_entry("Load master memory", f"Selected: {self.memory.model_name}")
            return {"master_memory": master_memory, "status": "ok", "error": ""}
        except Exception as exc:
            msg = f"Memory loading failed: {exc}"
            self._add_memory_entry("Load master memory", msg)
            return {"status": "error", "error": msg}

    def _graph_generate_improvements(self, state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            steps = self.generate_improvement_steps()
            self._add_memory_entry("Generate improvement steps", f"{len(steps)} chars")
            return {"improvement_steps": steps, "status": "ok", "error": ""}
        except MetricsAlreadyGoodError as exc:
            # Metrics are already excellent — skip improvement, go straight to deploy
            msg = str(exc)
            self._add_memory_entry("Generate improvement steps", msg)
            return {"improvement_steps": msg, "status": "ok", "decision": "deploy",
                    "skip_improvement": True, "error": ""}
        except Exception as exc:
            msg = f"Improvement step generation failed: {exc}"
            self._add_memory_entry("Generate improvement steps", msg)
            return {"status": "error", "error": msg}

    def _graph_generate_improved_code(self, state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            path = self.run_improved_code_generation()
            path_str = str(path) if path else ""
            self._add_memory_entry("Generate improved code", path_str or "none")
            if not path_str:
                print("[WARN] Improved code generation produced no output.")
            return {
                "improved_validation_code_path": path_str,
                "status": "ok",
                "error": "",
            }
        except Exception as exc:
            msg = f"Improved code generation failed: {exc}"
            self._add_memory_entry("Generate improved code", msg)
            return {"status": "error", "error": msg}

    def _graph_run_improved_code(self, state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            metrics = self.run_improved_code_runner()
            self._add_memory_entry("Run improved code", str(metrics))
            if metrics:
                self.save_memory()
            return {
                "improved_validation_metrics": metrics,
                "status": "ok",
                "error": "",
            }
        except Exception as exc:
            msg = f"Improved code runner failed: {exc}"
            self._add_memory_entry("Run improved code", msg)
            return {"status": "error", "error": msg}

    def _graph_decision_loop(self, state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            decision = self.run_decision_loop()
            self._add_memory_entry("User decision", decision)
            self.save_memory()
            return {"decision": decision, "status": "ok", "error": ""}
        except Exception as exc:
            msg = f"Decision loop failed: {exc}"
            return {"status": "error", "error": msg, "decision": "error"}

    def _graph_finalize_memory(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Final node: save improvement memory and copy into master_memory.json."""
        snapshot = self.get_memory()
        self.save_memory()

        if self.master_memory_path and self.master_memory_path.exists():
            try:
                with self.master_memory_path.open("r", encoding="utf-8") as f:
                    master_memory = json.load(f)

                mem_dict = self.get_memory()
                master_memory["improvement"] = {
                    "improvement_steps": mem_dict.get("improvement_steps"),
                    "improvement_steps_path": mem_dict.get("improvement_steps_path"),
                    "model_name": mem_dict.get("model_name"),
                    "validation_metrics": mem_dict.get("validation_metrics"),
                    "improved_validation_metrics": mem_dict.get("improved_validation_metrics", {}),
                    "user_satisfied": mem_dict.get("user_satisfied"),
                    "proceed_to_deployment": mem_dict.get("proceed_to_deployment"),
                    "regeneration_count": mem_dict.get("regeneration_count", 0),
                    "dataset_folder": str(self.output_dir) if self.output_dir else None,
                }

                with self.master_memory_path.open("w", encoding="utf-8") as f:
                    json.dump(master_memory, f, indent=2)

                self._add_memory_entry("Persist to master", "Done.")
            except Exception as exc:
                print(f"[WARN] Could not update master_memory.json: {exc}")

        return {"memory_snapshot": snapshot, "status": "success"}

    # ======================================================================
    # PUBLIC API
    # ======================================================================

    def get_memory(self) -> Dict[str, Any]:
        return {
            "master_memory_path": str(self.memory.master_memory_path) if self.memory.master_memory_path else None,
            "dataset_name": self.memory.dataset_name,
            "model_name": self.memory.model_name,
            "task_type": self.memory.task_type,
            "validation_metrics": self.memory.validation_metrics,
            "dataset_context": self.memory.dataset_context,
            "validation_code_path": str(self.memory.validation_code_path) if self.memory.validation_code_path else None,
            "dataset_report_path": str(self.memory.dataset_report_path) if self.memory.dataset_report_path else None,
            "improvement_steps": self.memory.improvement_steps,
            "improvement_steps_path": str(self.memory.improvement_steps_path) if self.memory.improvement_steps_path else None,
            "improved_validation_code_path": str(self.memory.improved_validation_code_path) if self.memory.improved_validation_code_path else None,
            "improved_validation_metrics": self.memory.improved_validation_metrics,
            "regeneration_count": self.memory.regeneration_count,
            "user_satisfied": self.memory.user_satisfied,
            "proceed_to_deployment": self.memory.proceed_to_deployment,
            "file_history": self.memory.file_history,
            "conversation_history": self.conversation_history,
            "dataset_folder": str(self.output_dir) if self.output_dir else None,
        }

    def save_memory(self, path: Optional[Path] = None) -> None:
        if path is None:
            path = self.memory_file_path
        if path is None:
            return

        memory_dict = self.get_memory()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(memory_dict, f, indent=2)

        self.memory_file_path = path
        print(f"[INFO] Improvement memory saved to: {path}")

    def load_memory_from_file(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"Improvement memory file not found: {path}")

        with path.open("r", encoding="utf-8") as f:
            d = json.load(f)

        if d.get("master_memory_path"):
            self.memory.master_memory_path = Path(d["master_memory_path"])
        self.memory.dataset_name = d.get("dataset_name")
        self.memory.model_name = d.get("model_name")
        self.memory.task_type = d.get("task_type")
        self.memory.validation_metrics = d.get("validation_metrics", {})
        self.memory.dataset_context = d.get("dataset_context")
        self.memory.regeneration_count = d.get("regeneration_count", 0)
        self.memory.user_satisfied = d.get("user_satisfied")
        self.memory.proceed_to_deployment = d.get("proceed_to_deployment", False)

        for attr, key in [
            ("validation_code_path", "validation_code_path"),
            ("dataset_report_path", "dataset_report_path"),
            ("improvement_steps_path", "improvement_steps_path"),
            ("improved_validation_code_path", "improved_validation_code_path"),
        ]:
            val = d.get(key)
            if val:
                setattr(self.memory, attr, Path(val))

        if self.memory.improvement_steps_path and self.memory.improvement_steps_path.exists():
            self.memory.improvement_steps = self.memory.improvement_steps_path.read_text(encoding="utf-8")

        self.memory.improved_validation_metrics = d.get("improved_validation_metrics", {})
        self.memory.file_history = d.get("file_history", {})

        # Re-init output dir
        if self.memory.dataset_name:
            self._init_output_dir(self.memory.dataset_name)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="AI Agent for Improvement Workflow")
    parser.add_argument("--master-memory", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--endpoint", type=str, default=DEFAULT_ENDPOINT)
    args = parser.parse_args()

    try:
        agent = ImprovementWorkflowAgent(
            model=args.model,
            endpoint=args.endpoint,
            output_dir=args.output_dir,
            master_memory_path=args.master_memory,
        )

        initial_state = {"status": "pending"}
        result_state = agent.workflow.invoke(initial_state)

        if result_state.get("status") == "success":
            print("\n" + "=" * 60)
            print("IMPROVEMENT WORKFLOW COMPLETED")
            print("=" * 60)
            mem = agent.get_memory()
            print(f"  Model: {mem.get('model_name')}")
            print(f"  Dataset folder: {mem.get('dataset_folder')}")
            print(f"  Proceed to deployment: {mem.get('proceed_to_deployment')}")
            print(f"  Improvement runs recorded: {mem.get('regeneration_count', 0)}")
            sys.exit(0)

        error = result_state.get("error", "Unknown error")
        print(f"\n[ERROR] Improvement workflow failed: {error}")
        sys.exit(1)

    except FileNotFoundError as exc:
        print(f"\n[ERROR] Required file not found: {exc}")
        sys.exit(1)
    except RuntimeError as exc:
        print(f"\n[ERROR] {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"\n[ERROR] Unexpected error: {type(exc).__name__}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
