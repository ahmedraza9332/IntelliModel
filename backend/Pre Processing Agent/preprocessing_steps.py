import json
import sys
from pathlib import Path
from langchain_core.prompts import ChatPromptTemplate  # type: ignore[import]
from langchain_core.output_parsers import StrOutputParser  # type: ignore[import]

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from llm_config import DEFAULT_LLM_MODEL, DEFAULT_LLM_ENDPOINT, create_chat_llm


DEFAULT_MODEL = DEFAULT_LLM_MODEL
DEFAULT_ENDPOINT = DEFAULT_LLM_ENDPOINT


class PreprocessingAgent:
    def __init__(self, model: str = DEFAULT_MODEL, endpoint: str = DEFAULT_ENDPOINT) -> None:
        self.llm = create_chat_llm(model=model, endpoint=endpoint, temperature=0.0)
        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a meticulous data preprocessing expert. "
                    "You only see dataset metadata—never raw rows.",
                ),
                (
                    "user",
                    "Dataset metadata (JSON):\n{metadata_json}\n\n"
                    "Please provide:\n"
                    "1. Data quality or readiness issues detected from metadata.\n"
                    "2. Ordered preprocessing plan with justification.\n"
                    "3. Risks, assumptions, or validation checks to perform.\n\n"
                    "When building the plan, always check for and address the following:\n"
                    "- DUPLICATE ROWS: if the report shows duplicate counts > 0, add a step to drop duplicates.\n"
                    "- ID COLUMNS: flag any column whose name contains 'id', 'ID', '_id', 'Id', 'index', or 'Index', "
                    "  or any numeric column whose unique count equals the row count — mark these for REMOVAL "
                    "  as they cause data leakage.\n"
                    "- DATE/DATETIME COLUMNS: if a column dtype is object/string but values look like dates "
                    "  (e.g. '2024-01-15'), add steps to parse and extract year, month, day, dayofweek, quarter, "
                    "  plus cyclical sin/cos encoding for month and dayofweek.\n"
                    "- FREE-TEXT COLUMNS: if a string column has very high cardinality (unique ratio > 0.5), "
                    "  mark it for REMOVAL — do not try to encode free text as categorical.\n"
                    "- TARGET COLUMN QUALITY: flag if the target column has all-null values, zero variance "
                    "  (all same value), or if its name appears duplicated among feature columns.\n"
                    "- ENCODING: do NOT assume UTF-8 encoding — note if the report shows encoding issues.\n"
                    "- IMBALANCED CLASSIFICATION: if task is classification and the target has very unequal "
                    "  class distribution, recommend class_weight='balanced' or note SMOTE as an option.\n\n"
                    "Output should be a JSON object with key 'preprocessing_steps', each step having:\n"
                    "- step: short name\n"
                    "- action: what to do\n"
                    "- columns: relevant columns\n"
                    "- reason: explanation",
                ),
            ]
        )
        self.parser = StrOutputParser()

    def run(self, metadata_json: str) -> str:
        chain = self.prompt | self.llm | self.parser
        return chain.invoke({"metadata_json": metadata_json})


def main():
    report_path = Path("report.json")
    if not report_path.exists():
        raise FileNotFoundError(f"{report_path} not found.")

    # Load report JSON
    with report_path.open("r", encoding="utf-8") as f:
        report = json.load(f)

    metadata_json = json.dumps(report, indent=2)

    agent = PreprocessingAgent()

    print("\n=== Querying LLM for preprocessing plan... ===\n")
    response = agent.run(metadata_json)

    print(response)

    # Save preprocessing plan
    output_path = Path("preprocessing_plan.json")
    try:
        plan_dict = json.loads(response)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(plan_dict, f, indent=2)
        print(f"\nPreprocessing plan saved to {output_path}")
    except json.JSONDecodeError:
        output_path.write_text(response, encoding="utf-8")
        print(f"\nCould not parse JSON. Raw response saved to {output_path}")


if __name__ == "__main__":
    main()
