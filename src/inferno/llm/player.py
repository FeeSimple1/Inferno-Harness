"""play_with_callback: 3-strike retry + safe phase-appropriate fallback.

Per CROSS_PROJECT_LESSONS §5: "If the LLM proposes three illegal moves
in a row, fall through to a deterministic no-op move (advance_step /
cmd_pass / end_card / legate_skip depending on phase). Don't deadlock;
don't crash; don't let the whole game stall on one hallucination."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..actions import IllegalAction, dispatch
from ..legal_moves import enumerate_legal


@dataclass
class FallbackUsed:
    reason: str
    rejected_actions: list[dict[str, Any]] = field(default_factory=list)
    fallback_action: dict[str, Any] | None = None


@dataclass
class ActionResult:
    applied: dict[str, Any]
    fallback: FallbackUsed | None = None
    rejected: list[tuple[dict[str, Any], str]] = field(default_factory=list)


# Phase-appropriate safe fallback actions. Each entry returns an action
# dict that's always legal in the corresponding phase/step combination.
SAFE_FALLBACKS = {
    ("levy", "3.1"): lambda side: {"action": "levy_aow_draw", "side": side},
    ("levy", "3.2"): lambda side: {"action": "levy_pay_done", "side": side},
    ("levy", "3.3"): lambda side: {"action": "levy_disband_done", "side": side},
    ("levy", "3.4"): lambda side: {"action": "levy_muster_done", "side": side},
    ("levy", "3.5"): lambda side: {"action": "levy_cta_skip", "side": side},
    ("campaign", "capability_discard"): lambda side: {"action": "campaign_discard_done", "side": side},
    ("campaign", "plan"): lambda side: {"action": "plan_add_card", "side": side,
                                        "args": {"card_id": "PASS"}},
    ("campaign", "command_phase"): lambda side: {"action": "command_reveal", "side": side},
    ("campaign", "end_campaign"): lambda side: {"action": "end_grow_skip", "side": side},
}


def safe_fallback_for(state: dict[str, Any]) -> dict[str, Any] | None:
    """Pick a safe phase-appropriate fallback action for the current side."""
    phase = state["meta"].get("phase")
    side = state["meta"].get("active_player")
    if phase == "levy":
        key = ("levy", state["meta"].get("levy_step"))
    elif phase == "campaign":
        key = ("campaign", state["meta"].get("campaign_step"))
    else:
        return None
    fn = SAFE_FALLBACKS.get(key)
    if fn is None:
        return None
    return fn(side)


def play_with_callback(
    state: dict[str, Any],
    callback: Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]],
    max_strikes: int = 3,
) -> ActionResult:
    """Drive one action via an LLM callback with retry+fallback.

    args:
      state:    full state (mutated in place by dispatch)
      callback: fn(briefing_state, legal_moves) -> action_dict
                The caller is responsible for serializing the briefing
                via filter+briefing, calling the LLM, parsing the
                response into an action dict.
      max_strikes: how many rejected actions before falling back.

    Returns ActionResult capturing whether a fallback was used.
    """
    rejected: list[tuple[dict[str, Any], str]] = []
    for strike in range(1, max_strikes + 1):
        moves = enumerate_legal(state)
        moves = [m for m in moves if not m.get("action", "").startswith("<")]
        try:
            proposed = callback(state, moves)
        except Exception as e:
            rejected.append(({"<callback_error>": str(e)}, "callback_error"))
            continue
        try:
            result = dispatch(state, proposed)
            return ActionResult(applied=result, rejected=rejected)
        except IllegalAction as e:
            rejected.append((proposed, f"{e.code}: {e}"))
            continue
    # Strikes exhausted: fall through to a safe action.
    fb = safe_fallback_for(state)
    if fb is None:
        return ActionResult(applied={}, fallback=FallbackUsed(
            reason=f"max_strikes ({max_strikes}) hit and no fallback for this phase",
            rejected_actions=[r[0] for r in rejected],
        ), rejected=rejected)
    result = dispatch(state, fb)
    return ActionResult(applied=result, fallback=FallbackUsed(
        reason=f"max_strikes ({max_strikes}) hit; fell back to {fb['action']}",
        rejected_actions=[r[0] for r in rejected],
        fallback_action=fb,
    ), rejected=rejected)
