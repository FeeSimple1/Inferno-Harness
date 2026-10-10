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


def safe_fallback_for(state: dict[str, Any]) -> dict[str, Any] | None:
    """Pick from the actual menu, including the owner of a pending decision."""
    moves = [m for m in enumerate_legal(state) if not m.get("action", "").startswith("<")]
    if not moves:
        return None
    # Decline optional actions / finish a filled plan before adding anything.
    preferred = ("cmd_fpd_pay_done", "plan_done", "cmd_end_card", "levy_pay_done",
                 "levy_disband", "levy_disband_done", "levy_muster_done",
                 "campaign_discard_done", "levy_cta_skip", "end_grow_skip")
    for name in preferred:
        for move in moves:
            if move["action"] == name:
                return {k: move[k] for k in ("action", "side", "args") if k in move}
    for move in moves:
        if move["action"] == "plan_add_card" and move.get("args", {}).get("card_id") == "PASS":
            return {k: move[k] for k in ("action", "side", "args") if k in move}
    move = moves[0]
    return {k: move[k] for k in ("action", "side", "args") if k in move}


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
