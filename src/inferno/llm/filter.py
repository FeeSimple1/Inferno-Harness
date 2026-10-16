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
    prior_side = state.get("_filtered_for")
    if prior_side is not None and prior_side != visible_side:
        raise ValueError("Cannot change perspective using an already-filtered state.")
    hidden_mats = bool(hidden_mats or state.get("meta", {}).get("hidden_mats")
                       or state.get("_hidden_mats"))
    if prior_side == visible_side and bool(state.get("_hidden_mats")) == hidden_mats:
        return copy.deepcopy(state)
    opp = "ghibelline" if visible_side == "guelph" else "guelph"
    # Operator callbacks/scripts are not player-visible game state. In
    # particular, an opponent's prepared combat choices must not be exposed
    # by the focused snapshot endpoint.
    private_channels = {"battle_callback", "approach_battle_decisions",
                        "approach_post_battle_decisions"}
    s = copy.deepcopy({k: v for k, v in state.items() if k not in private_channels})

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

    # Plans remain secret in the transcript too. Draw history can identify
    # held Events, and RNG seeds would allow reconstructing future draws.
    for entry in s.get("history", []):
        # Resolving a public Event/Exiles/placement may also resume a private
        # draw queue. Those continuation notes can reveal a newly Held card,
        # even in an action owned by the OTHER side (Exiles). Public effects
        # remain visible; hands already show their owner's private draws.
        changes = entry.get("state_changes")
        if isinstance(changes, dict) and entry.get("action") != "levy_aow_draw":
            changes.pop("deployment", None)
            changes.pop("aow_deployment", None)
        if entry.get("side") == opp and entry.get("action") in (
                "plan_add_card", "levy_aow_draw"):
            entry["args"] = {}
            entry["state_changes"] = {"hidden": True}
            entry["rolls"] = []
        elif hidden_mats and entry.get("side") == opp:
            entry["args"] = {}
            entry["state_changes"] = {"hidden_mats": True}
    s.get("meta", {}).pop("rng_seed", None)
    s.get("meta", {}).pop("rng_advance", None)
    s.get("meta", {}).pop("post_battle_withdraw", None)
    # A not-yet-resolved card is not a revealed card, even for its future owner.
    resolution = s.get("aow_resolution")
    if isinstance(resolution, dict):
        if resolution.get("side") == opp:
            s.pop("aow_resolution", None)
        else:
            for key in ("remaining", "queue"):
                if isinstance(resolution.get(key), list):
                    resolution[key] = ["<unrevealed>" for _ in resolution[key]]
    for entry in s.get("history", []):
        if entry.get("side") == opp:
            for key in ("scripted_decisions", "post_battle_decisions"):
                entry.get("args", {}).pop(key, None)
    # Pending choices must be complete for their owner, but do not disclose
    # private choice payloads to the other player. Approach geometry is public.
    for i, pending in enumerate(s.get("pending", []) or []):
        if pending.get("side") not in (None, visible_side):
            public = {"type": pending.get("type"), "side": pending["side"], "waiting": True}
            if pending.get("type") == "approach_response":
                public["info"] = {k: v for k, v in pending.get("info", {}).items()
                                  if k in ("lord_id", "locale", "approached_from", "approached_via")}
            s["pending"][i] = public

    # 1.5.2 Hidden Mats option: redact Lord mat contents (Forces,
    # Vassals readiness, Assets) for the opposing side. Lord names,
    # locations, and ratings remain visible — those are public.
    if hidden_mats:
        from ..visibility import combat_visibility
        revealed = combat_visibility(state).get("lords", set())
        for lid, lord in s.get("lords", {}).items():
            if lord.get("side") == opp and lid not in revealed:
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
