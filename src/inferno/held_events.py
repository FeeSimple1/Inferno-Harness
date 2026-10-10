"""Discover argument choices for Held Events without consuming cards or dice.

The action dispatcher remains authoritative. The menu previews only the Event
handler on a private copy with a fixed RNG; availability must never depend on
future rolls. Combat resolution is not run just to list Surprise as an option.
"""
from __future__ import annotations

import copy
from itertools import combinations
from typing import Any

from . import card_data as cd
from . import card_effects as ce
from . import static_data as sd
from .rng import HarnessRNG


def _subsets(items):
    for n in range(1, len(items) + 1):
        yield from combinations(items, n)


def event_argument_candidates(state, side: str, cid: str) -> list[dict[str, Any]]:
    """All exposed target/mode/payment choices, not a preselected strategy."""
    own = [lid for lid, l in state["lords"].items()
           if l.get("side") == side and l.get("status") == "mustered"]
    enemy = [lid for lid, l in state["lords"].items()
             if l.get("side") != side and l.get("status") == "mustered"]
    treachery = state["decks"][side].get("treachery_set_aside", [])
    if cid in ("F4", "S4"):
        return [{"target_lord_id": lid} for lid in own]
    if cid == "S16":
        return [{"target_lord_id": lid} for lid in enemy
                if state["lords"][lid].get("forces", {}).get("Cavalieri", 0)]
    if cid in ("F7", "S7"):
        return [{"enemy_lord_id": lid, "unit_to_remove": unit,
                 **({"capability_to_discard": cap} if cap is not None else {})}
                for lid in enemy
                for unit, count in state["lords"][lid].get("forces", {}).items() if count > 0
                for cap in (state["lords"][lid].get("capabilities") or [None])]
    if cid == "F11":
        return ([{"mode": "lordship", "target_lord_id": lid} for lid in own]
                + [{"mode": "treachery", "treachery_card": card} for card in treachery])
    if cid == "F15":
        return ([{"mode": "auto_succeed"}] + ([{"mode": "treachery"}]
                if "treachery_firenze" in treachery else []))
    if cid == "F18":
        return [{"mode": "auto_treachery_at_grosseto"}, {"mode": "shift_santa_fiora"}]
    if cid == "F19":
        return [{"mode": "auto_treachery_at_volterra"}, {"mode": "shift_pisa"}]
    if cid == "F23":
        payers = [lid for lid in own if state["lords"][lid].get("assets", {}).get("Coin", 0) > 0]
        payments = [{lid: 2} for lid in payers
                    if state["lords"][lid]["assets"]["Coin"] >= 2]
        payments += [{a: 1, b: 1} for a, b in combinations(payers, 2)]
        return ([{"mode": "declare_cta", "coin_sources": pay} for pay in payments]
                + [{"mode": "treachery", "coin_sources": pay, "treachery_card": card}
                   for pay in payments for card in treachery])
    if cid == "S17":
        targets = [lid for lid in ("provenzano", "santa_fiora") if lid in own]
        shifts = [{"mode": "shift_other", "target": lid}
                  for lid in ("provenzano", "santa_fiora")
                  if state["lords"][lid].get("calendar_box") is not None]
        return (shifts + [{"mode": "lordship", "targets": list(group)} for group in _subsets(targets)]
                + [{"mode": "treachery", "treachery_for": lid}
                   for lid in ("provenzano", "santa_fiora") if "treachery_" + lid in treachery])
    if cid == "S18":
        return ([{"mode": "treachery_free"}, {"mode": "revolt_roll"}]
                + [{"mode": "add_treachery", "treachery_card": card} for card in treachery])
    if cid == "S19":
        return [{"target_lord_id": lid, "receiver_lord_id": receiver, "bundle": bundle}
                for lid in enemy for receiver in ("giordano", "astimberg")
                for bundle in ("coin", "loot", "carts_prov")]
    if cid == "S21":
        return [{"mode": mode, "target": lid} for lid in ("siena", "pisa")
                for mode in ("shift", "lordship")]
    return [{}]


def _candidate_in_context(state, side, cid, args):
    """Do not advertise target/mode choices outside their printed context."""
    from .actions import _hold_event_window_ok
    if not _hold_event_window_ok(state, side, cid):
        return False
    # Outset-of-Battle cards refer to the actual approaching armies, not any
    # Lord at a siege elsewhere. Doctors also has a Storm window.
    field = {"F4", "S4", "F6", "S6", "F8", "S8", "F12", "S12", "F16", "S16"}
    approach = [p for p in state.get("pending", []) if p.get("type") == "approach_response"]
    if cid in field:
        if not approach:
            return False
        locale = approach[0].get("info", {}).get("locale")
        if cid in ("F6", "S6", "F8", "S8") and side == state["meta"].get("approach_attacker_side"):
            return False
        target = args.get("target_lord_id")
        if target and state["lords"][target].get("location") != locale:
            return False
    # Lordship options are used during Muster / CtA Allies, not stored across
    # arbitrary Campaign turns. Direct shift and Treachery-add modes remain free.
    if args.get("mode") == "lordship":
        if state["meta"].get("phase") != "levy":
            return False
        if state["meta"].get("levy_step") != "3.4" and not (
                state["meta"].get("levy_step") == "3.5" and state["meta"].get("cta_substep") == "allies"):
            return False
        if args.get("target") and state["lords"][args["target"]].get("status") != "mustered":
            return False
    if cid == "F23" and args.get("mode") == "declare_cta":
        from .actions import _cta_treasurers_playable
        if not _cta_treasurers_playable(state):
            return False
    auto_modes = {"F15": "auto_succeed", "F18": "auto_treachery_at_grosseto",
                  "F19": "auto_treachery_at_volterra", "S18": "treachery_free"}
    if cid in auto_modes and args.get("mode") == auto_modes[cid]:
        card = state.get("current_card") or ""
        if not card.startswith("treachery_"):
            return False
        lid = state.get("current_lord_id")
        if cid == "F15" and lid != "firenze":
            return False
        loc = state.get("lords", {}).get(lid, {}).get("location")
        nearby = {loc} | {n for n, _ in sd.adjacent_to(loc)} if loc else set()
        target = {"F18": "Grosseto", "F19": "Volterra", "S18": "Cortona"}.get(cid)
        if target and target not in nearby:
            return False
        if cid == "F15" and not any(state["locales"][n].get("type") == "castle" for n in nearby):
            return False
    return True


def held_event_options(state, side: str) -> list[dict[str, Any]]:
    """Concrete play_event actions. Does not mutate state, history, or RNG."""
    out = []
    for cid in state["decks"][side].get("aow_held", []):
        card = cd.AOW_CARDS_BY_ID.get(cid)
        if not card or card.get("event_kind") != "hold":
            continue
        for args in event_argument_candidates(state, side, cid):
            if not _candidate_in_context(state, side, cid, args):
                continue
            # Event preview on a copy, NOT dispatch or combat. Use a constant
            # seed to ensure neither future dice nor hidden deck order affect
            # the palette. Required choices must be applied, not 'manual'.
            trial = copy.deepcopy({k: v for k, v in state.items() if k != "history"})
            effect = ce.apply_event_effect(trial, cid, side, copy.deepcopy(args), HarnessRNG(seed=0))
            if not effect.get("applied") or effect.get("manual"):
                continue
            action_args = {"card_id": cid}
            if args:
                action_args["effect_args"] = args
            detail = f" — {args}" if args else ""
            out.append({"action": "play_event", "side": side, "args": action_args,
                        "description": f"Play {cid} {card['event_name']}{detail}.",
                        "rule_citation": f"{cid} / 3.1.3"})
    return out
