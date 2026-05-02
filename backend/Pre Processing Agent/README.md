## Pre-Processing Agent

This lightweight LangChain agent inspects an input dataset, distils metadata (schema, stats, data quality signals), and asks your locally hosted LLM (exposed at `http://127.0.0.1:11434`) for recommended data preprocessing steps.

### Features
- Supports CSV/TSV and Excel files with automatic delimiter detection for CSV/TSV.
- Extracts only metadata (column dtypes, missing counts, unique counts, numeric stats, top categorical frequencies) — never raw rows.
- Accepts inline context text or a separate context file.
- Uses LangChain with `ChatOllama` to query your self-hosted `llama3.1` model.

### Requirements
1. Python 3.9+
2. A running LLM server at `http://127.0.0.1:11434` (e.g. Ollama).

Install dependencies:
```
pip install -r requirements.txt
```

### Usage
```
python preprocessing_agent.py path/to/data.file \
  --context "Binary classification for churn"
```

Optional flags:
- `--context-file`: load additional context from a text/markdown file.

The agent prints:
1. The generated dataset summary (for transparency).
2. The LLM's recommended preprocessing plan.

- Only the first 2,000 rows are analysed locally to keep the metadata concise (tweak `DEFAULT_MAX_ROWS` in `preprocessing_agent.py` if needed).
- Metadata JSON is logged before sending to the LLM for transparency.
- The LangChain stack pins the local `llama3.1` model at `http://127.0.0.1:11434`; edit the constants at the top of `preprocessing_agent.py` to change this.

