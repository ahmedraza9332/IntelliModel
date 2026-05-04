import json
import re
import sys
from pathlib import Path
from typing import Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from llm_config import DEFAULT_LLM_MODEL, DEFAULT_LLM_ENDPOINT, create_chat_llm

# Phi4 LLM settings
DEFAULT_MODEL = DEFAULT_LLM_MODEL
DEFAULT_ENDPOINT = DEFAULT_LLM_ENDPOINT

class PreprocessingCodeAgent:
    def __init__(
        self, 
        model=DEFAULT_MODEL, 
        endpoint=DEFAULT_ENDPOINT,
        dataset_path: Optional[Path] = None
    ):
        """
        Initialize the preprocessing code generator agent.
        
        Args:
            model: LLM model name (default: "phi4")
            endpoint: LLM endpoint URL (default: "http://127.0.0.1:11434")
            dataset_path: Path to the original dataset file (optional, can be set later)
        """
        # Store dataset path - will be used when generating code
        self.dataset_path = dataset_path
        self.dataset_filename = None
        
        self.llm = create_chat_llm(model=model, endpoint=endpoint, temperature=0.0)

        self.parser = StrOutputParser()

    def set_dataset_path(self, dataset_path: Path):
        """
        Set the dataset path for code generation.
        
        Args:
            dataset_path: Path to the original dataset file
        """
        self.dataset_path = Path(dataset_path)
        # Extract just the filename for use in generated code
        self.dataset_filename = self.dataset_path.name

    @staticmethod
    def _sanitize_non_printable(code: str) -> str:
        """
        Remove non-printable / invisible Unicode characters that cause SyntaxErrors
        (e.g. U+0001 SOH, U+0002 STX … U+001F, U+007F DEL, U+200B zero-width space,
        U+FEFF BOM, etc.) while keeping legitimate whitespace (\n, \r, \t, space).
        """
        # Allow only printable chars + normal whitespace
        return re.sub(r"[^\x09\x0A\x0D\x20-\x7E\u00A0-\uFFFF]", "", code)

    @staticmethod
    def _strip_code_fences(code: str) -> str:
        """
        Remove markdown code fences from LLM output.
        
        This is robust to:
        - Fenced blocks with language hints (```python)
        - Fences that don't appear at the very start of the string
        - Extra text before/after the fenced block
        """
        if not code:
            return code

        # First, try to extract the first fenced code block if present
        # NOTE: Use proper regex escapes so we correctly capture only the code block
        match = re.search(r"```(?:[\w+-]+)?\s*([\s\S]*?)```", code)
        if match:
            return match.group(1).strip()

        # Fallback: treat the whole string as possibly fenced and strip leading/trailing fences
        cleaned = code.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
            newline_idx = cleaned.find("\n")
            if newline_idx != -1:
                first_line = cleaned[:newline_idx].strip().lower()
                # Drop optional language hint (e.g., python)
                if first_line.isalpha():
                    cleaned = cleaned[newline_idx + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return cleaned.strip()

    def run(self, plan_json: str, dataset_path: Optional[Path] = None) -> str:
        """
        Generate preprocessing code from the plan.
        
        Args:
            plan_json: JSON string containing the preprocessing plan
            dataset_path: Optional dataset path (if not set via set_dataset_path)
            
        Returns:
            Generated Python code as string
        """
        # Use provided dataset_path or the one set in __init__/set_dataset_path
        if dataset_path:
            self.set_dataset_path(dataset_path)
        
        if not self.dataset_path:
            raise ValueError(
                "Dataset path not set. Provide dataset_path in run() or use set_dataset_path()"
            )
        
        # Ensure dataset_filename is set
        if not self.dataset_filename:
            self.dataset_filename = self.dataset_path.name
        dataset_full_path = str(self.dataset_path.resolve())
        
        # Build prompt with current dataset filename and absolute path for reliability
        # IMPORTANT: We explicitly instruct the LLM to NEVER drop the target column.
        # The generated code MUST ensure that the final 'processed_output.csv' contains
        # the original target column together with all processed feature columns.
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are an expert Python ML engineer. "
                    "Write ONLY valid production-ready Python code. "
                    "You must strictly follow the preprocessing steps given in the JSON. "
                    "Do not invent steps or modify the order. "
                    "Use pandas, numpy, and scikit-learn only. "
                    "Use sklearn pipelines when possible. "
                    "CRITICAL: The target column from the input dataset MUST be preserved "
                    "and included in the final saved CSV together with the processed features. "
                    "It is NOT allowed to drop the target column in the final output.",
                ),
                (
                    "user",
                    "Here is the preprocessing plan:\n\n{plan_json}\n\n"
                    "Now generate Python code that:\n"
                    "- Loads the dataset from this absolute path: '{dataset_full_path}'\n"
                    "  Use encoding='utf-8' first; if that raises UnicodeDecodeError, retry with encoding='latin-1'.\n"
                    "  Example pattern:\n"
                    "    try:\n"
                    "        df = pd.read_csv(path, encoding='utf-8')\n"
                    "    except UnicodeDecodeError:\n"
                    "        df = pd.read_csv(path, encoding='latin-1')\n"
                    "- (Optional) You may also refer to the filename '{dataset_filename}' for user messages.\n"
                    "- BEFORE any processing, detect and DROP ID-like columns: columns whose name "
                    "  contains 'id', 'ID', '_id', 'Id', 'index', 'Index', or any column that is "
                    "  numeric with unique values equal to the number of rows (i.e. n_unique == len(df)). "
                    "  Do NOT drop the target column even if its name contains 'id'.\n"
                    "- Detect and DROP duplicate rows (df.drop_duplicates()) before any transformations.\n"
                    "- For any string column that looks like a date (e.g. '2024-01-15', '01/15/2024'), "
                    "  parse it with pd.to_datetime(errors='coerce') and extract: year, month, day, "
                    "  dayofweek, quarter as new integer columns. Then add cyclical encoding for month "
                    "  (month_sin = sin(2π*month/12), month_cos = cos(2π*month/12)) and dayofweek "
                    "  (dow_sin, dow_cos). Drop the original string date column after extraction.\n"
                    "- For numeric columns with very low cardinality (e.g. <= 5 unique integer values "
                    "  that look like years such as 2018, 2019, 2020), do NOT parse them as dates — "
                    "  leave them as numeric features.\n"
                    "- For free-text string columns (unique ratio > 0.5, i.e. n_unique / len(df) > 0.5), "
                    "  drop them instead of trying to encode them as categorical, unless they are the target.\n"
                    "- Applies steps in the exact order provided\n"
                    "- Performs any feature-only transformations on X/features, but always keeps a copy of the original target column\n"
                    "- Saves output to a file named 'processed_output.csv' LOCATED IN THE SAME FOLDER AS THIS SCRIPT "
                    "  (i.e., use Path(__file__).parent / 'processed_output.csv')\n"
                    "- The saved 'processed_output.csv' must include BOTH the processed features AND the (untransformed) target variable\n"
                    "- The target variable must appear exactly once in the saved CSV alongside the processed features\n"
                    "- IMPORTANT: The saved CSV MUST contain exactly the same number of rows as the input dataset "
                    "  (after deduplication), in the same original row order. Do NOT drop rows for outliers — "
                    "  use Winsorization/clipping instead. If you perform a train/test split for fitting transformers, "
                    "  concatenate them back in original index order before saving.\n"
                    "- Adds comments for each step and DO NOT CHANGE THE COLUMN NAMES (except for newly extracted date features).\n"
                    "- Returns ONLY pure Python code with no syntactical errors"
                ),
            ]
        )
        
        chain = prompt | self.llm | self.parser
        raw_code = chain.invoke({
            "plan_json": plan_json,
            "dataset_filename": self.dataset_filename,
            "dataset_full_path": dataset_full_path
        })
        cleaned = self._strip_code_fences(raw_code)
        return self._sanitize_non_printable(cleaned)


def main():
    """Standalone main function for backward compatibility."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate preprocessing code from plan")
    parser.add_argument("--plan", type=Path, default="preprocessing_plan.json", 
                       help="Path to preprocessing plan JSON file")
    parser.add_argument("--dataset", type=Path, required=True,
                       help="Path to the original dataset CSV file")
    parser.add_argument("--output", type=Path, default="generated_preprocessing_code.py",
                       help="Output file path for generated code")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="LLM model name")
    parser.add_argument("--endpoint", type=str, default=DEFAULT_ENDPOINT,
                       help="LLM endpoint URL")
    
    args = parser.parse_args()
    
    if not args.plan.exists():
        raise FileNotFoundError(f"Preprocessing plan not found: {args.plan}")

    # Load the preprocessing plan
    with args.plan.open("r", encoding="utf-8") as f:
        plan = json.load(f)

    plan_json = json.dumps(plan, indent=2)

    # Run generator with dataset path
    agent = PreprocessingCodeAgent(model=args.model, endpoint=args.endpoint)
    print("=== Querying LLM for preprocessing code... ===")
    code = agent.run(plan_json, dataset_path=args.dataset)

    # Save generated code
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(code, encoding="utf-8")

    print(f"Preprocessing code saved to: {args.output}")
    print(f"\nRun it using: python {args.output}")


if __name__ == "__main__":
    main()
