import os
from pathlib import Path
from typing import Final

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

"""
Central LLM configuration for the IntelliModel backend.

All agents and helper scripts should import these constants instead of
hardcoding model names or endpoints. This allows switching the LLM setup
from a single place.
"""

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(BACKEND_DIR / ".env")

DEFAULT_LLM_MODEL: Final[str] = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-latest")
DEFAULT_LLM_ENDPOINT: Final[str] = os.getenv("CLAUDE_BASE_URL", "https://api.anthropic.com")


def create_chat_llm(
    model: str = DEFAULT_LLM_MODEL,
    endpoint: str = DEFAULT_LLM_ENDPOINT,
    temperature: float = 0.0,
):
    # Endpoint is accepted for compatibility with existing call sites.
    kwargs = {
        "model": model,
        "temperature": temperature,
    }
    if endpoint:
        kwargs["base_url"] = endpoint
    return ChatAnthropic(**kwargs)

