"""
Continual-learning hooks (NOT wired in v1).

Future: replay buffer sampling, distillation losses, EWC-style penalties.
Training loops do not import this module yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class LearningPolicyConfig:
    """Reserved for future policy knobs (replay ratio, LR cap, etc.)."""

    replay_fraction: float = 0.0
    notes: str = "v1 stub — no training integration"


def describe_planned_policies() -> Dict[str, Any]:
    """Human-readable map of planned techniques (documentation aid only)."""
    return {
        "replay": "Mix historical rows into each training batch (not active).",
        "distillation": "Match old model outputs on a replay set (not active).",
        "ewc": "Penalize movement on important weights (not active).",
    }
