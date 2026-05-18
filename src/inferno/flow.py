"""Phase / step flow control.

Manages the Levy and Campaign sequence transitions and player order
within each step. The data lives in state["meta"]; this module provides
the helpers that advance the meta forward by one transition.

Sequence (per Inferno_Sequence_of_Play.txt):
  LEVY (3.0):
    3.1 Arts of War     — Guelphs draw 2, then Ghibellines.
    3.2 Pay             — Guelphs may take Pay actions, then done; same for Ghib.
    3.3 Disband         — Guelphs auto-process Disbandable Lords, then Ghib.
    3.4 Muster          — Guelphs activate each eligible Mustered Lord; then Ghib.
    3.5 Call to Arms    — gated; deferred to Phase 2b in this harness.
  CAMPAIGN (4.0):
    Plan / Command / Feed-Pay-Disband / End Campaign — Phase 3+.

After both sides finish 3.4 (and CtA if invoked), the phase advances to
campaign. Phase 2 stops the engine at the Levy/Campaign boundary —
Phase 3 picks it up there.
"""

from __future__ import annotations

from typing import Any

from .state import Side

# Order in which the Levy steps progress
LEVY_STEPS: list[str] = ["3.1", "3.2", "3.3", "3.4", "3.5"]

# Player order within each Levy step (Guelphs first per 2.2.4)
SIDE_ORDER: list[Side] = ["guelph", "ghibelline"]


def current_step(state: dict[str, Any]) -> str | None:
    return state["meta"].get("levy_step")


def current_side(state: dict[str, Any]) -> Side:
    return state["meta"]["active_player"]


def advance_to_next_side_or_step(state: dict[str, Any]) -> None:
    """After active player finishes their work in the current Levy step,
    pass to the other side; if both sides have completed this step,
    advance to the next step (or to Campaign)."""
    step = current_step(state)
    side = current_side(state)
    if side == SIDE_ORDER[0]:
        state["meta"]["active_player"] = SIDE_ORDER[1]
        return
    # Both sides have completed this step. Advance step.
    idx = LEVY_STEPS.index(step)
    if idx + 1 < len(LEVY_STEPS):
        state["meta"]["levy_step"] = LEVY_STEPS[idx + 1]
        state["meta"]["active_player"] = SIDE_ORDER[0]
    else:
        # End of Levy. Phase 3 picks up at Campaign Plan.
        state["meta"]["phase"] = "campaign"
        state["meta"]["levy_step"] = None
        state["meta"]["active_player"] = SIDE_ORDER[0]


def is_first_levy(state: dict[str, Any]) -> bool:
    """First Levy of the scenario uses 3.1.2 (draw Capabilities) instead
    of 3.1.3 (draw Events). We treat it as first-Levy when the turn
    equals the scenario's starting Levy box and no AoW draw history
    exists yet."""
    # The flag is set false the first time the AoW draw resolves.
    return not state["meta"].get("first_levy_aow_drawn", False)


def mark_first_levy_aow_drawn(state: dict[str, Any]) -> None:
    state["meta"]["first_levy_aow_drawn"] = True
