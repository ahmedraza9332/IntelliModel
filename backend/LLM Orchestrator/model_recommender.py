from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
import json
import re
import sys
from pathlib import Path
from typing import List

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from llm_config import DEFAULT_LLM_MODEL, DEFAULT_LLM_ENDPOINT, create_chat_llm

DEFAULT_MODEL = DEFAULT_LLM_MODEL
DEFAULT_ENDPOINT = DEFAULT_LLM_ENDPOINT


def recommend_models(report, context, target, model=DEFAULT_MODEL, endpoint=DEFAULT_ENDPOINT):
    """
    Query the LLM for model recommendations. The LLM will infer the task type
    (regression/classification) itself from the provided report and context.
    """

    model_llm = create_chat_llm(model=model, endpoint=endpoint, temperature=0.2)

    # ---- SHORT, STRICT, REPORT + CONTEXT BASED PROMPT ----
    prompt_text = """
    You are an ML model selector.
    Base all reasoning ONLY on the dataset context and the dataset report and give reasons with the reference of them.
    Do not invent facts.

    Target: {target}

    Dataset Context:
    {context}

    Dataset Report:
    {report}

    First determine whether the task is regression or classification based on the
    report and context. Then recommend exactly 3 ML models appropriate for that task.

    CRITICAL: You MUST use this EXACT format for each model. Do not deviate:

    Model 1: [Model Name Here]
    Reason: [Reason text here explaining why this model fits the dataset characteristics]

    Model 2: [Model Name Here]
    Reason: [Reason text here explaining why this model fits the dataset characteristics]

    Model 3: [Model Name Here]
    Reason: [Reason text here explaining why this model fits the dataset characteristics]

    IMPORTANT RULES:
    - Start each model with "Model 1:", "Model 2:", "Model 3:" exactly as shown
    - Follow immediately with "Reason:" on the next line
    - Do NOT use markdown formatting (no **, no bullets, no numbered lists)
    - Do NOT use "Fit to Findings" or other labels - only use "Reason:"
    - Keep model names simple and clear (e.g., "Random Forest Regressor", not "**Random Forest Regressor**")
    """

    prompt = ChatPromptTemplate.from_template(prompt_text)
    chain = prompt | model_llm | StrOutputParser()

    return chain.invoke({
        "target": target,
        "context": context,
        "report": report
    })


def parse_model_names(recommendations_text: str) -> List[str]:
    """
    Parse model names from recommendations text.
    
    Args:
        recommendations_text: Raw text response from LLM
        
    Returns:
        List of model names
    """
    model_names = []
    
    # Pattern to match "Model N: [Model Name]"
    pattern = re.compile(
        r'Model\s+\d+\s*:\s*(.+?)(?=\s+Reason\s*:|\s+Model\s+\d+\s*:|$)',
        re.IGNORECASE | re.DOTALL
    )
    
    matches = pattern.findall(recommendations_text)
    for match in matches:
        model_name = match.strip()
        # Clean markdown formatting
        model_name = re.sub(r'\*\*?', '', model_name).strip()
        if model_name:
            model_names.append(model_name)
    
    return model_names


def select_models_for_validation(recommendations_text: str) -> List[str]:
    """
    Ask the user which models to perform validation testing on.
    
    Args:
        recommendations_text: Raw text response from LLM with model recommendations
        
    Returns:
        List of selected model names for validation
    """
    # Parse model names from recommendations
    model_names = parse_model_names(recommendations_text)
    
    if not model_names:
        raise ValueError("Could not parse model names from recommendations")
    
    print("\n" + "="*60)
    print("SELECT MODELS FOR VALIDATION TESTING")
    print("="*60)
    print("\nRecommended models:")
    for i, model_name in enumerate(model_names, 1):
        print(f"  {i}. {model_name}")
    
    print("\nWhich models would you like to perform validation testing on?")
    print("Enter model numbers separated by commas (e.g., 1,2,3) or 'all' for all models:")
    
    while True:
        try:
            user_input = input("Selection: ").strip().lower()
            
            if user_input == "all":
                return model_names
            
            # Parse comma-separated numbers
            selected_indices = [int(x.strip()) for x in user_input.split(",")]
            
            # Validate indices
            selected_models = []
            for idx in selected_indices:
                if 1 <= idx <= len(model_names):
                    selected_models.append(model_names[idx - 1])
                else:
                    print(f"Invalid model number: {idx}. Please enter numbers between 1 and {len(model_names)}.")
                    break
            else:
                # All indices were valid
                if selected_models:
                    print(f"\nSelected models for validation: {', '.join(selected_models)}")
                    return selected_models
                else:
                    print("No models selected. Please try again.")
        except ValueError:
            print("Invalid input. Please enter numbers separated by commas (e.g., 1,2,3) or 'all'.")
        except KeyboardInterrupt:
            print("\n\nSelection cancelled.")
            raise


def main():
    """Main program to run model recommendation from master_memory.json"""
    import argparse

    parser = argparse.ArgumentParser(description="Recommend ML models based on dataset analysis")
    parser.add_argument("--memory", type=Path, default="master_memory.json",
                       help="Path to master_memory.json file")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                       help="LLM model name")
    parser.add_argument("--endpoint", type=str, default=DEFAULT_ENDPOINT,
                       help="LLM endpoint URL")

    args = parser.parse_args()

    # Load master memory
    if not args.memory.exists():
        raise FileNotFoundError(f"Master memory file not found: {args.memory}")

    print(f"Loading master memory from: {args.memory}")
    with args.memory.open("r", encoding="utf-8") as f:
        memory = json.load(f)

    # Extract required information
    context = memory.get("context_of_dataset", "")
    report_json = memory.get("preprocessing", {}).get("report", {})
    target_column = memory.get("target_column", "")

    if not context:
        raise ValueError("'context_of_dataset' not found in master_memory.json")

    if not report_json:
        raise ValueError("'report' not found in master_memory.json under 'preprocessing'")

    if not target_column:
        raise ValueError("'target_column' not found in master_memory.json")

    # Convert the report to a string version for LLM
    report_str = json.dumps(report_json, indent=2)

    print(f"\nTarget column: {target_column}")
    print(f"\n=== Querying LLM for model recommendations... ===")

    # Get model recommendations (the LLM will infer task type)
    recommendations = recommend_models(
        report=report_str,
        context=context,
        target=target_column,
        model=args.model,
        endpoint=args.endpoint
    )

    print("\n" + "="*60)
    print("MODEL RECOMMENDATIONS")
    print("="*60)
    print(recommendations)
    print("="*60)

    return recommendations


if __name__ == "__main__":
    main()
