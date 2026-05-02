# Master Orchestrator Agent

The Master Orchestrator Agent maintains ultimate memory and context across all agents in the FYP workflow. It coordinates and tracks outputs from:

1. **Preprocessing Agent** - Dataset analysis, preprocessing plan, and code generation
2. **LLM Orchestrator (Reasoning Agent)** - Model recommendations, validation code, and trained models
3. **Improvement Agent** - Optimization reports and improved code

## Features

- **Comprehensive Memory**: Tracks all outputs, file paths, and context from all agents
- **Complete Workflow Orchestration**: Runs the entire pipeline from preprocessing to improvement
- **File History Tracking**: Maintains a complete history of all generated files
- **Workflow History**: Records all steps and agent interactions
- **Memory Persistence**: Save and load complete workflow state

## Memory Structure

The master agent maintains memory similar to `preprocessing_workflow_agent.py` but extends it to cover all agents:

### Preprocessing Agent Memory
- Dataset path and target column
- Dataset info (rows, columns, column names)
- Generated report (dataset analysis)
- Preprocessing plan (LLM-suggested steps)
- Generated preprocessing code
- All file paths (report, plan, code, processed output)

### LLM Orchestrator Memory
- Metadata (converted from preprocessing report)
- Model recommendations
- Selected models
- Generated validation code
- Trained model paths
- Evaluation results

### Improvement Agent Memory
- Optimization report
- Optimized code
- Optimized model paths
- List of improvements applied

### Complete File History
- Tracks all files created across all agents
- Easy reference to any generated file

## Usage

### Command Line

Run the complete workflow:

```bash
python master_orchestrator.py \
  --csv "../Datasets/Housing.csv" \
  --target "price" \
  --context "Real estate price prediction" \
  --test-size 0.2 \
  --min-models 1 \
  --max-models 3 \
  --save-memory
```

### Python API

```python
from pathlib import Path
from master_orchestrator import MasterOrchestratorAgent

# Initialize orchestrator
orchestrator = MasterOrchestratorAgent(
    model="phi4",
    endpoint="http://127.0.0.1:11434",
    output_dir=Path("./output")
)

# Run complete workflow
result = orchestrator.run_complete_workflow(
    csv_path=Path("../Datasets/Housing.csv"),
    target_column="price",
    llm_context="Real estate price prediction",
    test_size=0.2,
    min_models=1,
    max_models=3,
    run_improvement=True
)

# Access memory
memory = orchestrator.get_memory()
print(f"Dataset: {memory['dataset_path']}")
print(f"Preprocessing report: {memory['preprocessing']['report_path']}")
print(f"Selected models: {memory['llm_orchestrator']['selected_models']}")

# Save memory
orchestrator.save_memory()
```

### Run Individual Agents

You can also run agents individually:

```python
# Run preprocessing agent only
orchestrator.run_preprocessing_agent(
    csv_path=Path("../Datasets/Housing.csv"),
    target_column="price"
)

# Run LLM orchestrator (requires preprocessing to be done first)
orchestrator.run_llm_orchestrator(
    context="Real estate price prediction",
    test_size=0.2
)

# Run improvement agent (requires LLM orchestrator to be done first)
orchestrator.run_improvement_agent()
```

## Memory Access

The master agent provides complete access to all memory:

```python
memory = orchestrator.get_memory()

# Access preprocessing memory
preprocessing = memory['preprocessing']
print(f"Report: {preprocessing['report_path']}")
print(f"Plan: {preprocessing['plan_path']}")
print(f"Code: {preprocessing['code_path']}")

# Access LLM orchestrator memory
llm = memory['llm_orchestrator']
print(f"Selected models: {llm['selected_models']}")
print(f"Validation code: {llm['validation_code_path']}")
print(f"Evaluation results: {llm['evaluation_results']}")

# Access improvement memory
improvement = memory['improvement']
print(f"Optimization report: {improvement['optimization_report_path']}")
print(f"Improvements applied: {improvement['improvements_applied']}")

# Access complete file history
file_history = memory['complete_file_history']
for file_type, file_path in file_history.items():
    print(f"{file_type}: {file_path}")

# Access workflow history
workflow_history = memory['workflow_history']
for entry in workflow_history:
    print(f"{entry['agent']}: {entry['message']}")
```

## Memory Persistence

Save and load complete workflow state:

```python
# Save memory
orchestrator.save_memory()  # Saves to output_dir/master_memory.json
orchestrator.save_memory(Path("./custom_memory.json"))

# Load memory
orchestrator.load_memory(Path("./master_memory.json"))
```

## Command Line Options

```
--csv PATH              Path to the CSV dataset (required)
--target COLUMN         Name of the target column (required)
--output-dir PATH       Directory to save outputs (default: project root)
--model MODEL           LLM model name (default: phi4)
--endpoint URL          LLM endpoint URL (default: http://127.0.0.1:11434)
--context TEXT          Context for model recommendations
--test-size FLOAT       Fraction of data for testing (default: 0.2)
--min-models INT        Minimum number of models to select (default: 1)
--max-models INT        Maximum number of models to select (default: 3)
--skip-improvement      Skip improvement agent
--save-memory           Save master memory to JSON file
```

## Workflow Status

The master agent tracks workflow status:

- `not_started` - Workflow hasn't started
- `preprocessing` - Running preprocessing agent
- `llm_orchestration` - Running LLM orchestrator
- `improvement` - Running improvement agent
- `completed` - All agents completed successfully
- `error` - Workflow encountered an error

## Requirements

- Python 3.9+
- All dependencies from:
  - Pre Processing Agent
  - Reasoning Agent
  - Improvement Agent
- LangGraph for workflow orchestration

## Integration with Other Agents

The master orchestrator integrates with:

1. **Preprocessing Agent** (`Pre Processing Agent/preprocessing_workflow_agent.py`)
   - Runs the complete preprocessing workflow
   - Extracts all outputs and file paths
   - Stores report, plan, and code in memory

2. **LLM Orchestrator** (`Reasoning Agent/src/main.py`)
   - Converts preprocessing report to metadata
   - Runs model recommendation and training pipeline
   - Tracks selected models and evaluation results

3. **Improvement Agent** (`Improvement Agent/`)
   - Tracks optimization reports
   - Monitors optimized code and models
   - Records improvements applied

## Example Output

```
======================================================================
MASTER ORCHESTRATOR: COMPLETE WORKFLOW
======================================================================

======================================================================
MASTER ORCHESTRATOR: Running Preprocessing Agent
======================================================================
...
✓ Preprocessing Agent completed successfully
  Report: Pre Processing Agent\Housing.json
  Plan: Pre Processing Agent\Housing_preprocessing_plan.json
  Code: Pre Processing Agent\Housing_preprocessing_code.py

======================================================================
MASTER ORCHESTRATOR: Running LLM Orchestrator (Reasoning Agent)
======================================================================
...
✓ LLM Orchestrator completed successfully
  Selected models: ['Random Forest', 'XGBoost']
  Validation code: Reasoning Agent\generated_code\Housing_validate_models.py

======================================================================
MASTER ORCHESTRATOR: Running Improvement Agent
======================================================================
...
✓ Improvement Agent completed successfully
  Optimization report: Improvement Agent\optimization_report.json
  Optimized code: Improvement Agent\optimized_validate_models.py

======================================================================
COMPLETE WORKFLOW FINISHED SUCCESSFULLY
======================================================================

Dataset: C:\...\Datasets\Housing.csv
Target: price

Preprocessing Agent:
  - Report: Pre Processing Agent\Housing.json
  - Plan: Pre Processing Agent\Housing_preprocessing_plan.json
  - Code: Pre Processing Agent\Housing_preprocessing_code.py

LLM Orchestrator:
  - Selected models: Random Forest, XGBoost
  - Validation code: Reasoning Agent\generated_code\Housing_validate_models.py

Improvement Agent:
  - Optimization report: Improvement Agent\optimization_report.json
  - Optimized code: Improvement Agent\optimized_validate_models.py

Master memory saved to: master_memory.json
```

