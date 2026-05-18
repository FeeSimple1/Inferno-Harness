"""Phase / step flow control.

Manages the Levy and Campaign sequence transitions and player order
within each step. The data lives in state["meta"]; this module provides
the helpers that advance the meta forward.

Sequence (per Inferno_Sequence_of_Play.txt):
  LEVY (3.0):
    3.1 Arts of War     — Guelphs draw 2, then Ghibellines.
    3.2 Pay             — Guelphs Pay (n actions, then done); then Ghib.
    3.3 Disband         — Guelphs auto-process Disbandable Lords; then Ghib.
    3.4 Muster          — Guelphs activate each eligible Mustered Lord; then Ghib.
    3.5 Call to Arms    — gated; Phase 2 skip-only.
  CAMPAIGN (4.0):
    A capability_discard — Guelphs then Ghibellines discard excess side-wide Caps.
    B plan               — Guelphs then Ghibellines build Plan stacks (private).
    C command_phase      — Alternating reveals; FPD between cards.
    D end_campaign       — Phase 3c+ handles 4.9 (Grow, Ransom, Repair, Waste, Reset).

After both sides finish Levy 3.5, phase advances to campaign,
campaign_step="capability_discard". Phase 3a stops after command_phase
empties both plans (transitions to "end_campaign" which is a no-op stub
that advances the Calendar Levy marker and re-enters Levy).
"""

from __future__ import annotations

from typing import Any

from .state import Side

LEVY_STEPS: list[str] = ["3.1", "3.2", "3.3", "3.4", "3.5"]
CAMPAIGN_STEPS: list[str] = [
    "capability_discard", "plan", "command_phase", "end_campaign",
]
SIDE_ORDER: list[Side] = ["guelph", "ghibelline"]


def current_step(state: dict[str, Any]) -> str | None:
    return state["meta"].get("levy_step")


def current_campaign_step(state: dict[str, Any]) -> str | None:
    return state["meta"].get("campaign_step")


def current_side(state: dict[str, Any]) -> Side:
    return state["meta"]["active_player"]


def advance_to_next_side_or_step(state: dict[str, Any]) -> None:
    """Levy-step advancer. After active player finishes their work in
    the current Levy step, pass to the other side; if both sides done,
    advance to the next Levy step (or to Campaign)."""
    step = current_step(state)
    side = current_side(state)
    if side == SIDE_ORDER[0]:
        state["meta"]["active_player"] = SIDE_ORDER[1]
        return
    idx = LEVY_STEPS.index(step)
    if idx + 1 < len(LEVY_STEPS):
        new_step = LEVY_STEPS[idx + 1]
        state["meta"]["levy_step"] = new_step
        state["meta"]["active_player"] = SIDE_ORDER[0]
        # Reset per-Lord lordship_used when entering Muster (3.4)
        if new_step == "3.4":
            for lord in state["lords"].values():
                lord.get("flags", {}).pop("lordship_used", None)
    else:
        # End of Levy: enter Campaign at the capability-discard step.
        state["meta"]["phase"] = "campaign"
        state["meta"]["levy_step"] = None
        state["meta"]["campaign_step"] = CAMPAIGN_STEPS[0]
        state["meta"]["active_player"] = SIDE_ORDER[0]


def advance_campaign_step(state: dict[str, Any]) -> None:
    """Move to the next Campaign step (or finalize)."""
    cur = current_campaign_step(state)
    if cur is None:
        return
    idx = CAMPAIGN_STEPS.index(cur)
    if idx + 1 < len(CAMPAIGN_STEPS):
        state["meta"]["campaign_step"] = CAMPAIGN_STEPS[idx + 1]
        state["meta"]["active_player"] = SIDE_ORDER[0]
    else:
        # End of Campaign: Phase 3a stops here. Phase 3c+ implements 4.9 in full.
        # For now, advance Calendar and re-enter Levy for the next turn.
        cal = state["calendar"]
        cur_box = cal["levy_box"]
        # Remove "levy" marker from current box
        if str(cur_box) in cal["boxes"]:
            if "levy" in cal["boxes"][str(cur_box)]["markers"]:
                cal["boxes"][str(cur_box)]["markers"].remove("levy")
        new_box = cur_box + 1
        cal["levy_box"] = new_box
        if new_box <= 16:
            cal["boxes"].setdefault(str(new_box),
                {"cylinders": [], "services": [], "victory": [], "markers": []})
            cal["boxes"][str(new_box)]["markers"].append("levy")
            state["meta"]["turn"] = new_box
            state["meta"]["phase"] = "levy"
            state["meta"]["levy_step"] = LEVY_STEPS[0]
            state["meta"]["campaign_step"] = None
            state["meta"]["active_player"] = SIDE_ORDER[0]
            state["meta"]["exhaustion_rolled_this_levy"] = False
        else:
            state["meta"]["phase"] = "victory"
            state["meta"]["campaign_step"] = None


def advance_campaign_side_or_step(state: dict[str, Any]) -> None:
    """Within Campaign capability_discard / plan / end_campaign substeps:
    pass to other side if first, else advance to next Campaign step
    (except in end_campaign — substeps drive their own progression via
    state.meta.end_substep_done).
    """
    side = current_side(state)
    step = current_campaign_step(state)
    if side == SIDE_ORDER[0]:
        state["meta"]["active_player"] = SIDE_ORDER[1]
    elif step == "end_campaign":
        # End-of-Campaign substeps stay within end_campaign; active resets to
        # Guelph for the next substep.
        state["meta"]["active_player"] = SIDE_ORDER[0]
    else:
        advance_campaign_step(state)


def is_first_levy(state: dict[str, Any]) -> bool:
    """First Levy of the scenario uses 3.1.2 (Capabilities) vs 3.1.3 (Events)."""
    return not state["meta"].get("first_levy_aow_drawn", False)


def mark_first_levy_aow_drawn(state: dict[str, Any]) -> None:
    state["meta"]["first_levy_aow_drawn"] = True
