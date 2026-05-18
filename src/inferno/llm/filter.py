"""Hidden-info filter at the LLM boundary.

Per CROSS_PROJECT_LESSONS §5: "Strip the opposing side's hand, plan,
and any face-down state before serializing. Don't trust the LLM to
ignore visible information; just don't show it."

Inferno's hidden information (per 1.5.2 Hidden Mats option + general
practice in L&C):
  - Opposing side's aow_held cards (face-down Held Events).
  - Opposing side's aow_deck (face-down).
  - Opposing side's aow_discard (visible — discards are public).
  - Opposing side's plan_stacks (face-down until revealed).
  - Opposing side's treachery_set_aside (visible — public knowledge).
  - Opposing side's command_deck composition (visible — public).
  - With Hidden Mats option: Lord mats' Forces, Vassals, Capabilities.

This module produces a deep copy with opponent secrets redacted to
counts ("<hidden:N>") rather than card IDs, so the LLM can reason
about deck size without knowing specific cards.
"""

from __future__ import annotations

import copy
from typing import Any


def hide_for_side(state: dict[str, Any], visible_side: str,
                  hidden_mats: bool = False) -> dict[str, Any]:
    """Return a deep-copy of `state` with opposing-side secrets redacted.

    args:
      state:         full state object
      visible_side:  the side whose perspective the result should match
      hidden_mats:   if True, also redact opposing Lord mats (1.5.2)
    """
    if visible_side not in ("guelph", "ghibelline"):
        raise ValueError(f"Unknown side: {visible_side!r}")
    opp = "ghibelline" if visible_side == "guelph" else "guelph"
    s = copy.deepcopy(state)

    # Redact opposing deck secrets
    if opp in s.get("decks", {}):
        deck = s["decks"][opp]
        deck["aow_deck"] = [f"<hidden:{len(deck.get('aow_deck', []))}>"] if deck.get("aow_deck") else []
        deck["aow_held"] = [f"<hidden:{len(deck.get('aow_held', []))}>"] if deck.get("aow_held") else []
        # Plan stack is face-down until revealed; redact card identities,
        # keep position count.
    if opp in s.get("plan_stacks", {}):
        n = len(s["plan_stacks"][opp])
        s["plan_stacks"][opp] = [f"<facedown:{i+1}>" for i in range(n)]

    # 1.5.2 Hidden Mats option: redact Lord mat contents (Forces,
    # Vassals readiness, Assets) for the opposing side. Lord names,
    # locations, and ratings remain visible — those are public.
    if hidden_mats:
        for lid, lord in s.get("lords", {}).items():
            if lord.get("side") == opp and lord.get("status") in ("mustered", "on_calendar"):
                # Public: name, side, status, location, calendar_box, service_box, ratings, podesta, commander
                # Hidden: forces, assets, vassals (readiness), capabilities, routed_units, flags
                lord["forces"] = {"<hidden_force_count>": sum(lord.get("forces", {}).values())}
                lord["assets"] = {"<hidden>": True}
                lord["vassals"] = [{"<hidden_vassal_count>": len(lord.get("vassals", []))}]
                lord["capabilities"] = [f"<hidden:{len(lord.get('capabilities', []))}>"]
                lord["routed_units"] = {"<hidden>": True}
                lord["flags"] = {k: v for k, v in (lord.get("flags") or {}).items()
                                 if k in ("moved_fought", "in_stronghold", "bypassing",
                                          "has_lower_lord", "lower_lord_of")}

    # Mark the filtered view so callers know which perspective produced this.
    s["_filtered_for"] = visible_side
    s["_hidden_mats"] = hidden_mats
    return s
