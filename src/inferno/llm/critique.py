"""Post-game self-critique helper.

Per CROSS_PROJECT_LESSONS §5: "After terminal, hand the transcript back
to the model with the simple prompt 'what would you do differently?'
The output is surprisingly useful for surfacing strategy and rule-
edge cases that didn't crash but felt wrong."
"""
from __future__ import annotations

from typing import Any


def build_self_critique_prompt(state: dict[str, Any], side: str,
                               max_history: int = 80) -> str:
    """Build a self-critique prompt for the post-game model call."""
    history = state.get("history", [])[-max_history:]
    vp = state.get("vp", {})
    winner = state["meta"].get("winner")
    parts = [
        f"# Inferno post-game self-critique — {side.upper()}",
        "",
        f"Scenario {state['meta'].get('scenario')}. "
        f"Outcome: {'WIN' if winner == side else ('LOSS' if winner else 'DRAW')}.",
        f"Final VP: Guelph={vp.get('guelph', 0)}, "
        f"Ghibelline={vp.get('ghibelline', 0)}.",
        "",
        f"## Last {len(history)} actions (chronological)",
        "",
    ]
    for h in history:
        parts.append(
            f"- [{h.get('side')}] {h.get('action')}  "
            f"args={h.get('args', {})}  rolls={h.get('rolls', [])}"
        )
    parts += [
        "",
        "## Your task",
        "",
        "1. Identify 3-5 decisions you made that felt suboptimal in hindsight.",
        "2. For each, describe what you would do differently and why.",
        "3. Flag any moments where the rules engine gave you a surprising",
        "   result you didn't fully understand. These may indicate harness",
        "   bugs or unclear rule interactions worth reporting.",
        "4. Suggest one strategic prior to add to STRATEGY_DIGEST.md.",
        "",
        "Keep your response under 600 words.",
    ]
    return "\n".join(parts)
