"""Per-card Arts of War effects (BRIEF Phase 4).

The harness implements effects for the cards where the mechanical
description is concrete enough to encode unambiguously. Cards whose
text describes Battle / Storm modifiers that interact with mid-round
state in ways that aren't easily expressible in a deterministic
post-hoc handler are *flagged*: the harness reports that the card is
in play and would affect the current action, and the LLM applies the
narrative effect per the AoW Reference. This is the model the BRIEF
prescribes.

Effect registry shape (by card id):

  EVENT_EFFECTS[card_id] = handler(state, side, args, rng) -> result_dict

  CAPABILITY_HOOKS = {
      "supply": [(card_id, hook_fn), ...],   # called inside _h_cmd_supply
      "storm_walls": [...],
      "forage": [...],
      ...
  }

Effects that aren't mechanically encoded register a "flagged" handler
that returns {"manual": True, "note": ...}; the action handler that
called them surfaces the flag in its result so the LLM consumer can
apply the printed effect per the AoW Reference.
"""

from __future__ import annotations

from typing import Any, Callable

from . import card_data as cd
from . import static_data as sd


# Effect handlers keyed by card id. Event-half registrations.
EVENT_EFFECTS: dict[str, Callable] = {}
# Capability hooks: when a Capability is in play, certain engine paths
# consult these tables.
CAPABILITY_TRIGGERS: dict[str, dict[str, Any]] = {}


def register_event(card_id: str):
    def deco(fn):
        EVENT_EFFECTS[card_id] = fn
        return fn
    return deco


def register_capability(card_id: str, hook: dict[str, Any]):
    """Register a Capability's effect specification.

    hook keys (any subset):
      walls_plus_one_for_seats: list of Lords whose Seat Strongholds get Walls+1
      supply_bonus: dict (e.g. {"max_from_seat": 4})
      storm_attacker_horse_strikes: int  (Feditori-like)
      crossbow_for_units: list[str]      (Balestre Grosse / Balestrieri / Palvasari)
      archery_for_units: dict[str, str]  (Arcieri / Luceria)
      ravage_extra_loot: bool            (Gualdana for Horse Ravage)
      ravage_extra_provender: bool
      sail_provender: bool
      track_as_road: bool                (Road Works This Campaign)
      ...
    """
    CAPABILITY_TRIGGERS[card_id] = hook


def capability_in_play(state, card_id: str, side: str | None = None) -> bool:
    for c in state.get("capabilities_in_play", []):
        if c.get("id") == card_id and (side is None or c.get("side") == side):
            return True
    return False


def active_capabilities_for(state, hook_key: str) -> list[dict[str, Any]]:
    """Return list of {card_id, hook, side, lord_id?} entries currently
    in play that register a value for `hook_key`."""
    out = []
    for c in state.get("capabilities_in_play", []):
        cid = c.get("id")
        hook = CAPABILITY_TRIGGERS.get(cid)
        if hook and hook_key in hook:
            out.append({
                "card_id": cid, "side": c.get("side"),
                "lord_id": c.get("lord_id"),
                "value": hook[hook_key],
            })
    return out


# =====================================================================
# Helper utilities used by many event implementations
# =====================================================================
def _shift_cylinder_left(state, lord_id: str, boxes: int = 1) -> int | None:
    """Shift a Lord's cylinder on the Calendar `boxes` boxes LEFT.
    Returns the new box (None if it falls off the left edge)."""
    lord = state["lords"].get(lord_id)
    if lord is None:
        return None
    cur = lord.get("calendar_box")
    if cur is None:
        return None
    cal_boxes = state["calendar"]["boxes"]
    if str(cur) in cal_boxes and lord_id in cal_boxes[str(cur)]["cylinders"]:
        cal_boxes[str(cur)]["cylinders"].remove(lord_id)
    new = cur - boxes
    if new < 1:
        state["calendar"]["off_left"].append(lord_id)
        lord["calendar_box"] = None
        return None
    lord["calendar_box"] = new
    cal_boxes.setdefault(str(new),
        {"cylinders": [], "services": [], "victory": [], "markers": []})
    cal_boxes[str(new)]["cylinders"].append(lord_id)
    return new


def _shift_service_right(state, lord_id: str, boxes: int = 1) -> int | None:
    lord = state["lords"].get(lord_id)
    if lord is None:
        return None
    cur = lord.get("service_box")
    if cur is None:
        return None
    cal_boxes = state["calendar"]["boxes"]
    if str(cur) in cal_boxes and lord_id in cal_boxes[str(cur)]["services"]:
        cal_boxes[str(cur)]["services"].remove(lord_id)
    new = cur + boxes
    if new > 16:
        state["calendar"]["off_right_service"].append(lord_id)
        lord["service_box"] = None
        return None
    lord["service_box"] = new
    cal_boxes.setdefault(str(new),
        {"cylinders": [], "services": [], "victory": [], "markers": []})
    cal_boxes[str(new)]["services"].append(lord_id)
    return new


def _add_treachery_from_set_aside(state, side: str, lord_slug: str | None = None) -> str | None:
    """Move a set-aside Treachery card into the side's Command deck.
    If `lord_slug` specified, prefer that Lord's Treachery."""
    set_aside = state["decks"][side]["treachery_set_aside"]
    if not set_aside:
        return None
    chosen = None
    if lord_slug:
        target = f"treachery_{lord_slug}"
        if target in set_aside:
            chosen = target
    if chosen is None:
        chosen = set_aside[0]
    set_aside.remove(chosen)
    state["decks"][side]["command_deck"].append(chosen)
    return chosen


def _manual(card_id: str, note: str) -> dict[str, Any]:
    """Standard 'flagged for LLM' result for cards whose Battle/Storm
    in-round effects are not deterministically encoded."""
    return {"manual": True, "card_id": card_id, "note": note}


# =====================================================================
# Guelph Events (F1-F26)
# =====================================================================
@register_event("F1")
def F1_event(state, side, args, rng):
    """F1 AMBUSH (Hold) — registers Approach-time modifier: when enemy
    Lord(s) declare Avoid Battle, force one to Stand/Withdraw instead.
    """
    state.setdefault("approach_modifiers_pending", []).append({
        "id": "F1", "side": "guelph", "effect": "ambush_force_one_stand",
    })
    return {"applied": True, "flag_set": "F1_pending"}


@register_event("F2")
def F2_event(state, side, args, rng):
    """F2 BETRAYALS: per Stronghold w/ side's Siege, roll Revolt OR add 1 Treachery."""
    sieges = sum(1 for loc in state["locales"].values()
                 if any(s.get("side") == side for s in loc.get("siege", [])))
    if sieges == 0:
        return {"applied": True, "no_sieges": True}
    log = {"sieges": sieges, "rolls": []}
    for _ in range(sieges):
        r = rng.roll(f"betrayals_{side}")
        log["rolls"].append(r.value)
        # Default: add 1 Treachery card from set-aside (player choice ignored in defaults)
        added = _add_treachery_from_set_aside(state, side)
        log.setdefault("treachery_added", []).append(added)
    return {"applied": True, **log}


@register_event("F3")
def F3_event(state, side, args, rng):
    """F3 SURPRISE (Hold) — registers Besiege-alone modifier: on next
    Besiege by this side with no other Lord, place 2 Siege markers
    instead of 1 and run an auto-Storm up to 3 rounds with Walls -2.
    """
    state.setdefault("besiege_modifiers_pending", []).append({
        "id": "F3", "side": "guelph", "effect": "surprise_besiege_alone",
    })
    return {"applied": True, "flag_set": "F3_pending"}


@register_event("F4")
def F4_event(state, side, args, rng):
    """F4 SUDDEN CLASH (Hold).

    Sets in_battle_modifier_pending so the Battle engine can consult
    it for Round 1 Strike order. Full Strike-order surgery is reserved
    for a future engine pass; the flag is the contract.
    """
    target = args.get("target_lord_id")
    if not target or target not in state["lords"]:
        return _manual("F4", "Provide target_lord_id (Guelph Lord in upcoming Battle).")
    state.setdefault("battle_modifiers_pending", []).append({
        "id": "F4", "side": "guelph", "lord_id": target,
        "effect": "sudden_clash_r1_horse_first_select_target",
    })
    return {"applied": True, "flag_set": "F4_pending", "for_lord": target}


@register_event("F5")
def F5_event(state, side, args, rng):
    """F5 ROAD WORKS (This Campaign): treat Track as Road; move Laden as Unladen."""
    state.setdefault("active_events", {}).setdefault("this_campaign", []).append({
        "id": "F5", "side": side, "name": "Road Works",
        "effect": "track_as_road_and_unladen_for_side",
    })
    return {"applied": True, "duration": "this_campaign"}


@register_event("F6")
def F6_event(state, side, args, rng):
    """F6: sets in_battle_modifier flag (hills_double_archery_defending)."""
    state.setdefault("battle_modifiers_pending", []).append({
        "id": "F6", "side": "guelph", "effect": "hills_double_archery_defending",
    })
    return {"applied": True, "flag_set": "F6_pending"}


def _greek_fire_apply(state, side, args):
    """Shared Greek Fire mechanic (F7 Guelph / S7 Ghibelline mirror).

    On a Besieging Enemy Lord: reduce his Siege to 1 marker, remove 1
    of his units, and discard 1 of his This Lord Capabilities.
    Returns the standard effect dict.
    """
    card_id = "F7" if side == "guelph" else "S7"
    enemy_side = "ghibelline" if side == "guelph" else "guelph"
    enemy_lid = args.get("enemy_lord_id")
    unit = args.get("unit_to_remove")
    if not enemy_lid or enemy_lid not in state["lords"]:
        return _manual(card_id, "Specify enemy_lord_id + unit_to_remove to apply.")
    enemy = state["lords"][enemy_lid]
    if enemy.get("side") != enemy_side:
        return {"applied": False, "reason": f"{enemy_lid} is not an Enemy ({enemy_side}) Lord."}
    locale = state["locales"].get(enemy.get("location"))
    if not locale or not locale.get("siege"):
        return {"applied": False, "reason": "target not at a Besieged Locale"}
    # Reduce to 1 marker
    if locale["siege"]:
        locale["siege"] = [{"side": locale["siege"][0]["side"],
                            "color": locale["siege"][0]["color"], "count": 1}]
    # Remove one unit
    removed_unit = None
    if unit and enemy["forces"].get(unit, 0) > 0:
        enemy["forces"][unit] -= 1
        if enemy["forces"][unit] <= 0:
            enemy["forces"].pop(unit, None)
        removed_unit = unit
    # Discard first This Lord Capability if any
    discarded_cap = None
    if enemy.get("capabilities"):
        discarded_cap = enemy["capabilities"].pop()
        state["decks"][enemy["side"]]["aow_deck"].append(discarded_cap)
    return {"applied": True, "target": enemy_lid,
            "removed_unit": removed_unit, "discarded_capability": discarded_cap}


@register_event("F7")

def F7_event(state, side, args, rng):
    """F7 GREEK FIRE (Hold): on Besieging Enemy Lord, reduce to 1 Siege marker, remove 1 unit, discard 1 This Lord cap.
    Target args: enemy_lord_id, unit_to_remove, capability_to_discard?
    """
    return _greek_fire_apply(state, side, args)

@register_event("F8")
def F8_event(state, side, args, rng):
    """F8 SWAMP (Hold) — Defending in non-Summer Battle: enemy Horse
    units don't Strike in R1. Registers battle modifier; engine
    consumes at the Horse Melee step in R1.
    """
    from . import static_data as sd
    season = sd.SEASON_BY_BOX.get(state["meta"]["turn"], "winter")
    if season == "summer":
        return {"applied": False, "reason": "Swamp not playable in Summer."}
    state.setdefault("battle_modifiers_pending", []).append({
        "id": "F8", "side": "guelph",
        "effect": "swamp_enemy_horse_no_strike_r1",
    })
    return {"applied": True, "flag_set": "F8_pending"}


@register_event("F9")
def F9_event(state, side, args, rng):
    """F9 GENOVA: shift Firenze/Lucca/Colle cylinder OR Service 1 each, OR add 1 Treachery.
    args: mode = 'shift' (default) or 'treachery'.
    """
    mode = args.get("mode", "shift")
    if mode == "treachery":
        added = _add_treachery_from_set_aside(state, "guelph")
        return {"applied": True, "mode": "treachery", "added": added}
    shifts = {}
    for lid in ("firenze", "lucca", "colle"):
        # Try cylinder left first; if no cylinder on calendar, try Service right.
        new = _shift_cylinder_left(state, lid, boxes=1)
        if new is not None or state["lords"][lid].get("calendar_box") is None:
            shifts[lid] = {"cylinder_to": new}
        else:
            shifts[lid] = {"service_to": _shift_service_right(state, lid, boxes=1)}
    return {"applied": True, "mode": "shift", "shifts": shifts}


@register_event("F10")
def F10_event(state, side, args, rng):
    """F10 CLOSED GATES: remove 1 gold Ruins, or if none, remove 1 purple Ruins where eligible -> Revolt."""
    gold_ruins = [n for n, l in state["locales"].items() if l.get("ruins") == "gold"]
    if gold_ruins:
        loc_name = args.get("locale") or gold_ruins[0]
        state["locales"][loc_name]["ruins"] = None
        state["vp"]["ghibelline"] = max(state["vp"].get("ghibelline", 0) - 0.5, 0)
        return {"applied": True, "removed_ruins_at": loc_name}
    purple_ruins = [n for n, l in state["locales"].items() if l.get("ruins") == "purple"]
    if purple_ruins:
        loc_name = args.get("locale") or purple_ruins[0]
        loc = state["locales"][loc_name]
        size = sd.STRONGHOLDS.get(loc["type"], {}).get("size", 1)
        loc["ruins"] = None
        state["vp"]["guelph"] = max(state["vp"].get("guelph", 0) - 0.5, 0)
        # Revolt: place Guelph allegiance markers
        loc["current_allegiance"] = [m for m in loc.get("current_allegiance", []) if m.get("side") != "ghibelline"]
        for _ in range(size):
            loc["current_allegiance"].append({"side": "guelph", "value": 1})
        state["vp"]["guelph"] = min(state["vp"].get("guelph", 0) + size, 17.5)
        return {"applied": True, "revolted_at": loc_name, "size": size}
    return {"applied": False, "reason": "no eligible Ruins"}


@register_event("F11")
def F11_event(state, side, args, rng):
    """F11 POGGIO BONIZIO answers Firenze's call.

    Conditional: only playable when Poggio Bonizio has no Ghibelline
    (gold) Allegiance markers.
      args.mode = 'lordship' (default): target_lord_id gets Lordship +3
                                         for his next Muster action sequence.
      args.mode = 'treachery':           add 1 Guelph Treachery card.
    """
    pb = state["locales"].get("Poggio Bonizio")
    if pb is None:
        return {"applied": False, "reason": "Poggio Bonizio not in scenario."}
    has_ghib_markers = any(m.get("side") == "ghibelline"
                            for m in pb.get("current_allegiance", []))
    if has_ghib_markers:
        return {"applied": False, "reason": "Poggio Bonizio has Ghibelline markers; condition not met."}
    if args.get("mode") == "treachery":
        return {"applied": True, "added": _add_treachery_from_set_aside(state, "guelph")}
    target = args.get("target_lord_id")
    if not target or target not in state["lords"]:
        return {"applied": False, "reason": "target_lord_id required for lordship mode."}
    # One-shot bonus: applies to this Lord's next Muster segment.
    state["lords"][target].setdefault("flags", {})["lordship_bonus_pending"] = 3
    return {"applied": True, "lordship_bonus_for": target, "bonus": 3}


@register_event("F12")
def F12_event(state, side, args, rng):
    """F12 CAMP ATTACK (Hold) — R1 Asset transfer/removal. Registers
    pre-Battle modifier; engine consumes at 4.4.1 Events phase.
    """
    state.setdefault("battle_modifiers_pending", []).append({
        "id": "F12", "side": "guelph",
        "effect": "camp_attack_r1_asset_transfer",
    })
    return {"applied": True, "flag_set": "F12_pending"}


@register_event("F13")
def F13_event(state, side, args, rng):
    """F13 NO TIME FOR COWARDS: shift Firenze/Arezzo/Lucca 1 each OR add 1 Treachery."""
    if args.get("mode") == "treachery":
        added = _add_treachery_from_set_aside(state, "guelph")
        return {"applied": True, "added": added}
    shifts = {}
    for lid in ("firenze", "arezzo", "lucca"):
        new = _shift_cylinder_left(state, lid, boxes=1)
        if new is not None or state["lords"][lid].get("calendar_box") is None:
            shifts[lid] = {"cylinder_to": new}
        else:
            shifts[lid] = {"service_to": _shift_service_right(state, lid, boxes=1)}
    return {"applied": True, "shifts": shifts}


@register_event("F14")
def F14_event(state, side, args, rng):
    """F14 PROVENZANO sent as ambassador: if Guelph Siege underway, shift Provenzano 2 OR add 1 Treachery."""
    has_siege = any(any(s.get("side") == "guelph" for s in loc.get("siege", [])) for loc in state["locales"].values())
    if not has_siege:
        return {"applied": False, "reason": "no Guelph Siege underway"}
    if args.get("mode") == "treachery":
        added = _add_treachery_from_set_aside(state, "guelph")
        return {"applied": True, "added": added}
    # Shift Provenzano cylinder right 2 boxes or Service left 2 boxes.
    new = _shift_cylinder_left(state, "provenzano", boxes=2)
    return {"applied": True, "shifted_to": new}


@register_event("F15")
def F15_event(state, side, args, rng):
    """F15 CASOLE (Hold).

      mode = 'auto_succeed' (default): flag the next Firenze Treachery
                                       at a Castle to auto-succeed 0 Coin.
      mode = 'treachery':              add the Firenze Treachery card
                                       (if set-aside) to the Guelph deck.
    """
    if args.get("mode") == "treachery":
        return {"applied": True,
                "added": _add_treachery_from_set_aside(state, "guelph", lord_slug="firenze")}
    state.setdefault("active_events", {}).setdefault("this_levy", []).append({
        "id": "F15", "side": side, "name": "Casole",
        "flag": "firenze_treachery_castle_auto",
    })
    return {"applied": True, "flag_set": "firenze_treachery_castle_auto"}


@register_event("F16")
def F16_event(state, side, args, rng):
    """F16 BLOODY RED STREAM (Hold) — at outset of Battle, registers
    a 'first Guelph Rout: pause and roll Protection on Routed units'
    modifier. Engine consumes at the Rout-recovery hook.
    """
    state.setdefault("battle_modifiers_pending", []).append({
        "id": "F16", "side": "guelph",
        "effect": "bloody_red_stream_first_rout",
    })
    return {"applied": True, "flag_set": "F16_pending"}


@register_event("F17")
def F17_event(state, side, args, rng):
    """F17 FOREIGN HELP (Guelph). Two mutually exclusive options:

      mode="service" (default): shift Guido Guerra OR Orvieto Service 2 boxes
            right (requires that Lord's Service marker on the Calendar).
      mode="treachery_cylinder": set aside ONE Guelph Treachery card that is
            already in the Guelph Command deck (acquired, NOT from the Plan) to
            shift Guido's and/or Orvieto's CYLINDER left into the current Levy
            box, from anywhere on the Calendar to the right of that box. If only
            one of the two has an eligible cylinder, only that one may move.

    SMOKE-Inferno-054: the treachery_cylinder branch was previously an
    unimplemented stub ("Phase 4 simplified") that returned applied=False.
    Player choices (mode, target(s), which Treachery card) are supplied by the
    consumer (No-Agent); missing/ambiguous choices return a _manual prompt.
    """
    if side != "guelph":
        return {"applied": False, "reason": "F17 Foreign Help is a Guelph card."}
    mode = args.get("mode", "service")

    if mode == "service":
        target = args.get("target", "guido_guerra")
        if target not in ("guido_guerra", "orvieto"):
            return _manual("F17", "target must be 'guido_guerra' or 'orvieto'.")
        if state["lords"][target].get("service_box") is None:
            return {"applied": False,
                    "reason": f"{target} has no Service marker on the Calendar."}
        new = _shift_service_right(state, target, boxes=2)
        return {"applied": True, "mode": "service", "target": target, "service_to": new}

    if mode == "treachery_cylinder":
        deck = state["decks"]["guelph"]
        cmd = deck["command_deck"]
        levy_box = state["calendar"]["levy_box"]
        treachery_in_deck = [c for c in cmd if c in cd.TREACHERY_CARDS]
        # Eligible cylinders: Guido / Orvieto on the Calendar to the RIGHT of the
        # current Levy box (a higher box number is later / to the right).
        eligible = [t for t in ("guido_guerra", "orvieto")
                    if state["lords"][t].get("calendar_box") is not None
                    and state["lords"][t]["calendar_box"] > levy_box]
        if not eligible:
            return {"applied": False,
                    "reason": "Neither Guido nor Orvieto has a cylinder on the "
                              "Calendar to the right of the current Levy box."}
        if not treachery_in_deck:
            return {"applied": False,
                    "reason": "No Guelph Treachery card in the Command deck to set aside."}
        targets = args.get("targets")
        if targets is None:
            return _manual("F17",
                           f"Provide targets (a non-empty subset of {eligible}) and "
                           f"optionally treachery_card (one of {treachery_in_deck}).")
        targets = [t for t in targets if t in eligible]
        if not targets:
            return _manual("F17", f"targets must be a non-empty subset of {eligible}.")
        card = args.get("treachery_card", treachery_in_deck[0])
        if card not in treachery_in_deck:
            return _manual("F17", f"treachery_card must be one of {treachery_in_deck}.")
        # Set the chosen Treachery card aside again (Command deck -> set-aside).
        cmd.remove(card)
        deck["treachery_set_aside"].append(card)
        # Shift each chosen cylinder LEFT into the current Levy box.
        cal_boxes = state["calendar"]["boxes"]
        moved = []
        for t in targets:
            cur = state["lords"][t]["calendar_box"]
            if str(cur) in cal_boxes and t in cal_boxes[str(cur)]["cylinders"]:
                cal_boxes[str(cur)]["cylinders"].remove(t)
            state["lords"][t]["calendar_box"] = levy_box
            cal_boxes.setdefault(str(levy_box),
                {"cylinders": [], "services": [], "victory": [], "markers": []})
            cal_boxes[str(levy_box)]["cylinders"].append(t)
            moved.append({"lord_id": t, "to_box": levy_box})
        return {"applied": True, "mode": "treachery_cylinder",
                "treachery_set_aside": card, "cylinders_moved": moved}

    return _manual("F17", "mode must be 'service' or 'treachery_cylinder'.")


@register_event("F18")
def F18_event(state, side, args, rng):
    """F18 GROSSETO (Hold).

      mode = 'auto_treachery_at_grosseto' (default): flag next Guelph
            Treachery at Grosseto to auto-succeed 0 Coin.
      mode = 'shift_santa_fiora' (if Grosseto Guelph): shift Santa Fiora
            cylinder right or Service left by 2 boxes.
    """
    mode = args.get("mode", "auto_treachery_at_grosseto")
    grosseto = state["locales"].get("Grosseto")
    if mode == "shift_santa_fiora":
        if not grosseto:
            return {"applied": False, "reason": "Grosseto missing"}
        guelph_markers = any(m.get("side") == "guelph"
                              for m in grosseto.get("current_allegiance", []))
        if not guelph_markers:
            return {"applied": False, "reason": "Grosseto not Guelph-marked"}
        # Adverse shift on Santa Fiora (enemy of Guelphs): cylinder right
        # or Service left.
        sf = state["lords"]["santa_fiora"]
        if sf.get("calendar_box") is not None:
            cur = sf["calendar_box"]
            new_box = min(cur + 2, 17)
            cal_boxes = state["calendar"]["boxes"]
            if str(cur) in cal_boxes and "santa_fiora" in cal_boxes[str(cur)]["cylinders"]:
                cal_boxes[str(cur)]["cylinders"].remove("santa_fiora")
            if new_box > 16:
                state["calendar"]["off_right"].append("santa_fiora")
                sf["calendar_box"] = None
            else:
                sf["calendar_box"] = new_box
                cal_boxes.setdefault(str(new_box),
                    {"cylinders": [], "services": [], "victory": [], "markers": []})
                cal_boxes[str(new_box)]["cylinders"].append("santa_fiora")
            return {"applied": True, "cylinder_to": sf["calendar_box"]}
        elif sf.get("service_box") is not None:
            cur = sf["service_box"]
            new_box = max(cur - 2, 0)
            cal_boxes = state["calendar"]["boxes"]
            if str(cur) in cal_boxes and "santa_fiora" in cal_boxes[str(cur)]["services"]:
                cal_boxes[str(cur)]["services"].remove("santa_fiora")
            if new_box < 1:
                state["calendar"]["off_left_service"].append("santa_fiora")
                sf["service_box"] = None
            else:
                sf["service_box"] = new_box
                cal_boxes.setdefault(str(new_box),
                    {"cylinders": [], "services": [], "victory": [], "markers": []})
                cal_boxes[str(new_box)]["services"].append("santa_fiora")
            return {"applied": True, "service_to": sf["service_box"]}
        return {"applied": False, "reason": "Santa Fiora has no Calendar marker"}
    # Default: auto Treachery flag
    state.setdefault("active_events", {}).setdefault("this_levy", []).append({
        "id": "F18", "side": side, "name": "Grosseto",
        "flag": "guelph_treachery_at_locale_auto", "locale": "Grosseto",
    })
    return {"applied": True, "flag_set": "guelph_treachery_at_grosseto_auto"}


@register_event("F19")
def F19_event(state, side, args, rng):
    """F19 VOLTERRA (Hold).

    Per AoW Reference (and Errata): 'Play for Treachery at Volterra to
    succeed for 0 Coin or, if Volterra Guelph, to shift Pisa cylinder
    or Service 2 boxes.' This mirrors F18 Grosseto for Volterra/Pisa.

      mode = 'auto_treachery_at_volterra' (default): flag.
      mode = 'shift_pisa':                            shift Pisa.
    """
    mode = args.get("mode", "auto_treachery_at_volterra")
    volterra = state["locales"].get("Volterra")
    if mode == "shift_pisa":
        if not volterra:
            return {"applied": False, "reason": "Volterra missing"}
        guelph_markers = any(m.get("side") == "guelph"
                              for m in volterra.get("current_allegiance", []))
        if not guelph_markers:
            return {"applied": False, "reason": "Volterra not Guelph-marked"}
        pisa = state["lords"]["pisa"]
        if pisa.get("calendar_box") is not None:
            cur = pisa["calendar_box"]
            new_box = min(cur + 2, 17)
            cal_boxes = state["calendar"]["boxes"]
            if str(cur) in cal_boxes and "pisa" in cal_boxes[str(cur)]["cylinders"]:
                cal_boxes[str(cur)]["cylinders"].remove("pisa")
            if new_box > 16:
                state["calendar"]["off_right"].append("pisa")
                pisa["calendar_box"] = None
            else:
                pisa["calendar_box"] = new_box
                cal_boxes.setdefault(str(new_box),
                    {"cylinders": [], "services": [], "victory": [], "markers": []})
                cal_boxes[str(new_box)]["cylinders"].append("pisa")
            return {"applied": True, "cylinder_to": pisa["calendar_box"]}
        elif pisa.get("service_box") is not None:
            return {"applied": True, "service_to": _shift_service_right(state, "pisa", -2)}
        return {"applied": False, "reason": "Pisa has no Calendar marker"}
    state.setdefault("active_events", {}).setdefault("this_levy", []).append({
        "id": "F19", "side": side, "name": "Volterra",
        "flag": "guelph_treachery_at_locale_auto", "locale": "Volterra",
    })
    return {"applied": True, "flag_set": "guelph_treachery_at_volterra_auto"}


@register_event("F20")
def F20_event(state, side, args, rng):
    """F20 HEAT & FROST.

    SMOKE-Inferno-018 (card-text fidelity): card actually triggers
    Wastage (4.9.5) for all Lords NOW — twice for Lords at a Siege
    Locale or marked Moved/Fought. If Summer, removes 1 Ritter
    additionally.

    Per AoW Reference Text+Tips: this is NOT a 'each Lord +1 Provender'
    card. It is a Wastage trigger, fired in Summer or Winter only,
    immediately before Feed (4.8.1).
    """
    from . import static_data as sd
    season = sd.SEASON_BY_BOX.get(state["meta"]["turn"], "winter")
    if season not in ("summer", "winter"):
        return {"applied": False, "reason": "Heat & Frost requires Summer or Winter season."}
    log = {"wastage": [], "ritter_removed": []}
    for lid, lord in state["lords"].items():
        if lord["status"] != "mustered":
            continue
        # Determine cycles: 1 by default; 2 if at Siege Locale or Moved/Fought.
        loc = state["locales"].get(lord.get("location") or "")
        at_siege = bool(loc and loc.get("siege"))
        moved = bool(lord.get("flags", {}).get("moved_fought"))
        cycles = 2 if (at_siege or moved) else 1
        # Apply Wastage: for each cycle, if Lord has >1 of any Asset OR
        # >1 'This Lord' Capability, discard one (Asset count -= 1, or
        # capability returned to side AoW deck). Defaulting to first
        # multi-Asset; LLM consumer can re-run with specific choices.
        for _ in range(cycles):
            eligible = False
            for a, c in lord.get("assets", {}).items():
                if c > 1:
                    lord["assets"][a] -= 1
                    log["wastage"].append({"lord_id": lid, "asset": a})
                    eligible = True
                    break
            if not eligible and len(lord.get("capabilities", [])) > 1:
                cid = lord["capabilities"].pop()
                state["decks"][lord["side"]]["aow_deck"].append(cid)
                log["wastage"].append({"lord_id": lid, "capability": cid})
    # Summer: remove 1 Ritter from any side (per the card; play side chooses).
    if season == "summer":
        for lid, lord in state["lords"].items():
            if lord["status"] != "mustered":
                continue
            if lord["forces"].get("Ritter", 0) > 0:
                lord["forces"]["Ritter"] -= 1
                if lord["forces"]["Ritter"] <= 0:
                    lord["forces"].pop("Ritter")
                log["ritter_removed"].append(lid)
                break  # Card says "remove 1 Ritter" (singular)
    return {"applied": True, **log}


@register_event("F21")
def F21_event(state, side, args, rng):
    """F21 PRIMO POPOLO – Guelph merchant class.

    SMOKE-Inferno-021 (card-text fidelity): card text actually reads
    'Shift Firenze or Arezzo cylinder or Service 2 Calendar boxes
    or add 1 of their Treachery.' Tip clarifies cylinder LEFT or
    Service RIGHT.
    """
    if args.get("mode") == "treachery":
        return {"applied": True, "added": _add_treachery_from_set_aside(state, "guelph")}
    target = args.get("target", "firenze")
    if target not in ("firenze", "arezzo"):
        return {"applied": False, "reason": "target must be firenze or arezzo"}
    if state["lords"][target].get("calendar_box") is not None:
        return {"applied": True, "target": target, "cylinder_to": _shift_cylinder_left(state, target, boxes=2)}
    elif state["lords"][target].get("service_box") is not None:
        return {"applied": True, "target": target, "service_to": _shift_service_right(state, target, boxes=2)}
    return {"applied": False, "reason": f"{target} has no Calendar marker to shift"}


@register_event("F22")
def F22_event(state, side, args, rng):
    """F22 MANFREDI holds back.

    SMOKE-Inferno-020 (card-text fidelity): per AoW Reference (Errata
    applied), 'Select a Lord with Ritter. Shift his cylinder or Service
    1 Calendar box or remove 3 of his Assets.' "Ghibelline" deleted by
    Errata so any-side Lord with Ritter qualifies.

    args:
      target_lord_id:  Lord with Ritter (must have at least one Ritter
                       on his mat, including via Turncoat).
      mode:            'shift' (default) | 'remove_assets'
      assets_to_remove: dict for mode=remove_assets, e.g.
                       {"Coin": 1, "Provender": 2}
    """
    target_lid = args.get("target_lord_id")
    if not target_lid or target_lid not in state["lords"]:
        return _manual("F22", "Provide target_lord_id (any Lord with Ritter on mat).")
    target = state["lords"][target_lid]
    if target.get("forces", {}).get("Ritter", 0) == 0:
        return {"applied": False, "reason": f"{target_lid} has no Ritter on mat."}
    mode = args.get("mode", "shift")
    if mode == "shift":
        if target.get("calendar_box") is not None:
            cur = target["calendar_box"]
            cal_boxes = state["calendar"]["boxes"]
            if str(cur) in cal_boxes and target_lid in cal_boxes[str(cur)]["cylinders"]:
                cal_boxes[str(cur)]["cylinders"].remove(target_lid)
            new_box = cur + 1
            if new_box > 16:
                state["calendar"]["off_right"].append(target_lid)
                target["calendar_box"] = None
            else:
                target["calendar_box"] = new_box
                cal_boxes.setdefault(str(new_box),
                    {"cylinders": [], "services": [], "victory": [], "markers": []})
                cal_boxes[str(new_box)]["cylinders"].append(target_lid)
            return {"applied": True, "shifted_cylinder_to": target["calendar_box"]}
        elif target.get("service_box") is not None:
            cur = target["service_box"]
            cal_boxes = state["calendar"]["boxes"]
            if str(cur) in cal_boxes and target_lid in cal_boxes[str(cur)]["services"]:
                cal_boxes[str(cur)]["services"].remove(target_lid)
            new_box = cur - 1
            if new_box < 1:
                state["calendar"]["off_left_service"].append(target_lid)
                target["service_box"] = None
            else:
                target["service_box"] = new_box
                cal_boxes.setdefault(str(new_box),
                    {"cylinders": [], "services": [], "victory": [], "markers": []})
                cal_boxes[str(new_box)]["services"].append(target_lid)
            return {"applied": True, "shifted_service_to": target["service_box"]}
        else:
            return {"applied": False, "reason": "Target has no Calendar marker to shift."}
    elif mode == "remove_assets":
        request = args.get("assets_to_remove", {})
        total_request = sum(request.values())
        if total_request > 3:
            return {"applied": False, "reason": "Cannot remove more than 3 Assets total."}
        removed = {}
        for a, n in request.items():
            have = target["assets"].get(a, 0)
            take = min(n, have)
            if take > 0:
                target["assets"][a] -= take
                removed[a] = take
        return {"applied": True, "removed_assets": removed}
    return {"applied": False, "reason": "mode must be shift or remove_assets"}


@register_event("F23")
def F23_event(state, side, args, rng):
    """F23 TREASURERS (Hold).

      mode = 'declare_cta' (default): pay 2 Coin total (from one or
            more Guelph Lords) to declare Call to Arms this Levy.
      mode = 'treachery':              pay 2 Coin total to add a set-
            aside Guelph Treachery card to the Command deck.
    """
    coin_sources = args.get("coin_sources", {})  # {lord_id: count}
    total = sum(coin_sources.values())
    if total != 2 and not coin_sources:
        # Auto-pick: find 2 Coin from any Mustered Guelph Lords.
        coin_sources = {}
        remaining = 2
        for lid, lord in state["lords"].items():
            if lord["side"] != "guelph" or lord["status"] != "mustered":
                continue
            avail = lord["assets"].get("Coin", 0)
            if avail == 0:
                continue
            take = min(avail, remaining)
            coin_sources[lid] = take
            remaining -= take
            if remaining == 0:
                break
        if remaining > 0:
            return {"applied": False, "reason": "Insufficient Guelph Coin available."}
        total = 2
    if total != 2:
        return {"applied": False, "reason": "Treasurers requires exactly 2 Coin."}
    # Pay Coin
    for lid, n in coin_sources.items():
        if state["lords"][lid]["assets"].get("Coin", 0) < n:
            return {"applied": False, "reason": f"{lid} has insufficient Coin."}
    for lid, n in coin_sources.items():
        state["lords"][lid]["assets"]["Coin"] -= n
    if args.get("mode") == "treachery":
        added = _add_treachery_from_set_aside(state, "guelph")
        return {"applied": True, "mode": "treachery", "paid": coin_sources, "added": added}
    # declare_cta: flag Guelph CtA eligibility for this Levy.
    declared = set(state.get("war_declared_this_levy", []))
    declared.add("guelph")
    state["war_declared_this_levy"] = list(declared)
    return {"applied": True, "mode": "declare_cta", "paid": coin_sources}


@register_event("F24")
def F24_event(state, side, args, rng):
    """F24 DOCTORS: roll for each Routed Guelph unit; recoveries return to mat."""
    log = []
    for lid, lord in state["lords"].items():
        if lord["side"] != "guelph":
            continue
        routed = dict(lord.get("routed_units", {}))
        for unit, count in routed.items():
            if unit == "Villici":
                continue
            u = sd.UNITS.get(unit, {})
            prot = u.get("protection", [])
            for _ in range(count):
                r = rng.roll(f"doctors_{lid}_{unit}")
                if r.value in prot:
                    lord["routed_units"][unit] = lord["routed_units"].get(unit, 0) - 1
                    if lord["routed_units"][unit] <= 0:
                        lord["routed_units"].pop(unit, None)
                    lord["forces"][unit] = lord["forces"].get(unit, 0) + 1
                    log.append({"lord": lid, "unit": unit, "recovered": True})
    return {"applied": True, "recoveries": log}


@register_event("F25")
def F25_event(state, side, args, rng):
    """F25 VAL D'ORCIA — War event. Marks Guelph CtA eligible this Levy."""
    state.setdefault("war_declared_this_levy", set())
    state["war_declared_this_levy"] = list(set(state.get("war_declared_this_levy", [])) | {"guelph"})
    return {"applied": True, "war_event": "guelph"}


@register_event("F26")
def F26_event(state, side, args, rng):
    """F26 MONTALCINO — War event for Guelphs."""
    state["war_declared_this_levy"] = list(set(state.get("war_declared_this_levy", [])) | {"guelph"})
    return {"applied": True, "war_event": "guelph"}


# =====================================================================
# Guelph Capabilities (F1-F26)
# =====================================================================
register_capability("F1", {"supply_max_from_seat": 4, "supply_while_besieged_at_own_seat": True,
                          "applies_to_side": "guelph"})
register_capability("F2", {"siege_extra_marker": 1, "this_lord": True})
register_capability("F3", {"storm_walls_minus": 1, "this_lord": True})  # Siege Towers
register_capability("F4", {"siege_extra_marker": 1, "this_lord": True})  # Trebuchets
register_capability("F5", {"siege_walls_minus_1_storm": True, "this_lord": True})  # War Engineers
register_capability("F6", {"hills": True, "applies_to_side": "guelph"})  # Hills Capability (battle modifier — flagged)
register_capability("F7", {"greek_fire": True, "this_lord": True})  # flagged
register_capability("F8", {"crossbow_for_units": ["Men-at-Arms"], "this_lord": True})  # Balestre Grosse
register_capability("F9", {})  # Genova Capability — situational, flagged
register_capability("F10", {"closed_gates_capability": True})  # flagged
register_capability("F11", {})  # Poggio Bonizio Capability — flagged
register_capability("F12", {"army_reserve": True, "this_lord": True})  # flagged
register_capability("F13", {"no_time_for_cowards_capability": True, "this_lord": True})  # flagged
register_capability("F14", {"this_lord": True})  # Provenzano Capability
register_capability("F15", {"casole_capability": True})
register_capability("F16", {"this_lord": True})  # Bloody Red Stream — flagged
register_capability("F17", {})  # Foreign Help Capability
register_capability("F18", {"ravage_extra_loot": True, "this_lord": True})  # La Cavallata
register_capability("F19", {"ravage_extra_provender": True, "this_lord": True})  # Gualdana
register_capability("F20", {"ravage_extra_loot": True, "this_lord": True})  # Masnadieri
register_capability("F21", {"distringitores": True, "this_lord": True})  # flagged
register_capability("F22", {"tau_company": True, "applies_to_side": "guelph",
                            "lordship_bonus_for": ["firenze", "lucca"], "lordship_value": 1})
register_capability("F23", {"via_francigena": True, "applies_to_side": "guelph",
                            "track_as_road": True})
register_capability("F24", {"astrologers": True, "this_lord": True})  # flagged (event timing)
register_capability("F25", {"walls_plus_one_for_seats": True, "this_lord": True})  # Reinforced Walls
register_capability("F26", {"repair_ruins": True, "this_lord": True})  # Costruttori


# =====================================================================
# Ghibelline Events (S1-S26) — many mirror their Guelph counterparts
# =====================================================================
@register_event("S1")
def S1_event(state, side, args, rng):
    """S1 AMBUSH (Ghib mirror)."""
    state.setdefault("approach_modifiers_pending", []).append({
        "id": "S1", "side": "ghibelline", "effect": "ambush_force_one_stand",
    })
    return {"applied": True, "flag_set": "S1_pending"}


@register_event("S2")
def S2_event(state, side, args, rng):
    """S2 BETRAYALS — Ghib version of F2."""
    sieges = sum(1 for loc in state["locales"].values()
                 if any(s.get("side") == "ghibelline" for s in loc.get("siege", [])))
    if sieges == 0:
        return {"applied": True, "no_sieges": True}
    log = {"sieges": sieges, "rolls": [], "treachery_added": []}
    for _ in range(sieges):
        r = rng.roll("betrayals_ghibelline")
        log["rolls"].append(r.value)
        log["treachery_added"].append(_add_treachery_from_set_aside(state, "ghibelline"))
    return {"applied": True, **log}


@register_event("S3")
def S3_event(state, side, args, rng):
    """S3 SURPRISE (Ghib mirror)."""
    state.setdefault("besiege_modifiers_pending", []).append({
        "id": "S3", "side": "ghibelline", "effect": "surprise_besiege_alone",
    })
    return {"applied": True, "flag_set": "S3_pending"}


@register_event("S4")
def S4_event(state, side, args, rng):
    """S4 SUDDEN CLASH (Ghib mirror) — sets in_battle_modifier flag."""
    target = args.get("target_lord_id")
    if not target or target not in state["lords"]:
        return _manual("S4", "Provide target_lord_id (Ghibelline Lord in upcoming Battle).")
    state.setdefault("battle_modifiers_pending", []).append({
        "id": "S4", "side": "ghibelline", "lord_id": target,
        "effect": "sudden_clash_r1_horse_first_select_target",
    })
    return {"applied": True, "flag_set": "S4_pending", "for_lord": target}


@register_event("S5")
def S5_event(state, side, args, rng):
    """S5 ROAD WORKS (Ghib version): treat Track as Road; Laden as Unladen."""
    state.setdefault("active_events", {}).setdefault("this_campaign", []).append({
        "id": "S5", "side": side, "name": "Road Works",
        "effect": "track_as_road_and_unladen_for_side",
    })
    return {"applied": True, "duration": "this_campaign"}


@register_event("S6")
def S6_event(state, side, args, rng):
    """S6 HILLS (Ghib mirror) — Defending Archery Hits doubled."""
    state.setdefault("battle_modifiers_pending", []).append({
        "id": "S6", "side": "ghibelline",
        "effect": "hills_double_archery_defending",
    })
    return {"applied": True, "flag_set": "S6_pending"}


@register_event("S7")
def S7_event(state, side, args, rng):
    """S7 GREEK FIRE (Ghibelline mirror of F7): on Besieging Enemy (Guelph)
    Lord, reduce to 1 Siege marker, remove 1 unit, discard 1 This Lord cap.
    Target args: enemy_lord_id, unit_to_remove.
    """
    return _greek_fire_apply(state, side, args)


@register_event("S8")
def S8_event(state, side, args, rng):
    """S8 SWAMP (Ghib mirror) — Defending non-Summer; enemy Horse skip R1."""
    from . import static_data as sd
    season = sd.SEASON_BY_BOX.get(state["meta"]["turn"], "winter")
    if season == "summer":
        return {"applied": False, "reason": "Swamp not playable in Summer."}
    state.setdefault("battle_modifiers_pending", []).append({
        "id": "S8", "side": "ghibelline",
        "effect": "swamp_enemy_horse_no_strike_r1",
    })
    return {"applied": True, "flag_set": "S8_pending"}


@register_event("S9")
def S9_event(state, side, args, rng):
    """S9 POPE AT BAY: shift Pisa/Siena cylinder/Service or add 1 Treachery (the Ghib mirror of F9)."""
    if args.get("mode") == "treachery":
        return {"applied": True, "added": _add_treachery_from_set_aside(state, "ghibelline")}
    shifts = {}
    for lid in ("pisa", "siena", "provenzano"):
        new = _shift_cylinder_left(state, lid, boxes=1)
        if new is not None or state["lords"][lid].get("calendar_box") is None:
            shifts[lid] = {"cylinder_to": new}
        else:
            shifts[lid] = {"service_to": _shift_service_right(state, lid, boxes=1)}
    return {"applied": True, "shifts": shifts}


@register_event("S10")
def S10_event(state, side, args, rng):
    """S10 A BETTER PAID DEATH.

    Per AoW Reference: shift cylinder/Service of 2 Ghibelline Lords
    (not Podestà) by 1 box, OR give 1 Lord Lordship +2 this Levy.
    Eligible: Giordano, Astimberg, Provenzano, Santa Fiora.
    """
    eligible = ("giordano", "astimberg", "provenzano", "santa_fiora")
    if args.get("mode") == "lordship":
        target = args.get("target", "giordano")
        if target not in eligible:
            return {"applied": False, "reason": f"target must be one of {eligible}"}
        state["lords"][target].setdefault("flags", {})["lordship_bonus_pending"] = 2
        return {"applied": True, "lordship_bonus_for": target, "bonus": 2}
    # Default: shift 2 Lords
    targets = args.get("targets", list(eligible[:2]))
    shifts = {}
    for t in targets[:2]:
        if t not in eligible:
            continue
        if state["lords"][t].get("calendar_box") is not None:
            shifts[t] = {"cylinder_to": _shift_cylinder_left(state, t, 1)}
        elif state["lords"][t].get("service_box") is not None:
            shifts[t] = {"service_to": _shift_service_right(state, t, 1)}
    return {"applied": True, "shifts": shifts}


@register_event("S11")
def S11_event(state, side, args, rng):
    """S11 VOLTERRA — Ghib mirror; shift Astimberg or Santa Fiora Service 2 OR add 1 Treachery."""
    if args.get("mode") == "treachery":
        return {"applied": True, "added": _add_treachery_from_set_aside(state, "ghibelline")}
    target = args.get("target", "astimberg")
    return {"applied": True, "target": target, "service_to": _shift_service_right(state, target, boxes=2)}


@register_event("S12")
def S12_event(state, side, args, rng):
    """S12 CAMP ATTACK (Ghib mirror) — R1 Asset transfer."""
    state.setdefault("battle_modifiers_pending", []).append({
        "id": "S12", "side": "ghibelline",
        "effect": "camp_attack_r1_asset_transfer",
    })
    return {"applied": True, "flag_set": "S12_pending"}


@register_event("S13")
def S13_event(state, side, args, rng):
    """S13 GENTLE USILIA ransoms prisoners (Hold).

    Guelphs immediately conduct a Ransom (4.9.2). Returns a 'ransom
    triggered for guelph' signal; the harness consumer should
    dispatch end_ransom for guelph next.
    """
    captured = state.get("captured_knights", {}).get("guelph", {})
    total = sum(captured.values())
    state.setdefault("active_events", {}).setdefault("this_levy", []).append({
        "id": "S13", "side": side, "name": "Gentle Usilia",
        "trigger": "immediate_guelph_ransom",
    })
    return {"applied": True, "ransom_triggered_for": "guelph",
            "captured_total": total}


@register_event("S14")
def S14_event(state, side, args, rng):
    """S14 FRIARS sent to deceive Florentines (Hold).

    'This Campaign Guelphs shuffle and play chosen Command cards
    without inspecting stack.' Sets a flag the Plan UI/engine can
    respect.
    """
    state.setdefault("active_events", {}).setdefault("this_campaign", []).append({
        "id": "S14", "side": side, "name": "Friars",
        "effect": "guelph_plan_blind_no_inspect",
    })
    return {"applied": True, "flag_set": "S14_this_campaign"}


@register_event("S15")
def S15_event(state, side, args, rng):
    """S15 WAR LOANS: +1 Coin to one Ghibelline Lord, or add 1 Treachery."""
    if args.get("mode") == "treachery":
        return {"applied": True, "added": _add_treachery_from_set_aside(state, "ghibelline")}
    target = args.get("target", "siena")
    if target in state["lords"]:
        state["lords"][target]["assets"]["Coin"] = state["lords"][target]["assets"].get("Coin", 0) + 1
    return {"applied": True, "target": target}


@register_event("S16")
def S16_event(state, side, args, rng):
    """S16 BOCCA DEGLI ABATI (Hold) — at outset of Battle, target Guelph
    Lord's Cavalieri each take 1 Hit; 1 that Routs joins Ghibelline mat.
    """
    target = args.get("target_lord_id")
    if not target:
        return _manual("S16", "Provide target_lord_id (Guelph Lord at Battle).")
    state.setdefault("battle_modifiers_pending", []).append({
        "id": "S16", "side": "ghibelline",
        "effect": "bocca_cavalieri_auto_hit",
        "target_lord_id": target,
    })
    return {"applied": True, "flag_set": "S16_pending", "target": target}


@register_event("S17")
def S17_event(state, side, args, rng):
    """S17 GHIBELLINE REFUGEES (Hold).

    Playable only if Provenzano or Santa Fiora on map. Three modes:
      'shift_other' — shift the OTHER's cylinder left 2 boxes.
      'lordship'    — +2 Lordship to one or both (one-shot).
      'treachery'   — add a Provenzano or Santa Fiora Treachery card.
    """
    prov_on = state["lords"]["provenzano"]["status"] == "mustered"
    sf_on   = state["lords"]["santa_fiora"]["status"] == "mustered"
    if not (prov_on or sf_on):
        return {"applied": False, "reason": "Neither Provenzano nor Santa Fiora on map."}
    mode = args.get("mode", "shift_other")
    if mode == "treachery":
        target_slug = args.get("treachery_for", "provenzano")
        return {"applied": True,
                "added": _add_treachery_from_set_aside(state, "ghibelline", lord_slug=target_slug)}
    if mode == "lordship":
        targets = args.get("targets", [])
        if not targets:
            targets = [lid for lid in ("provenzano", "santa_fiora")
                       if state["lords"][lid]["status"] == "mustered"]
        for t in targets:
            state["lords"][t].setdefault("flags", {})["lordship_bonus_pending"] = (
                state["lords"][t].get("flags", {}).get("lordship_bonus_pending", 0) + 2
            )
        return {"applied": True, "lordship_bonus_for": targets, "bonus": 2}
    # default shift_other
    if prov_on and not sf_on:
        return {"applied": True, "shifted_cylinder_to": _shift_cylinder_left(state, "santa_fiora", 2)}
    if sf_on and not prov_on:
        return {"applied": True, "shifted_cylinder_to": _shift_cylinder_left(state, "provenzano", 2)}
    target = args.get("target", "santa_fiora")
    return {"applied": True, "shifted_cylinder_to": _shift_cylinder_left(state, target, 2)}


def _locales_within(state, start, max_dist):
    """Set of Locale names within max_dist steps of start (inclusive)."""
    from . import static_data as sd
    seen = {start}
    frontier = [start]
    for _ in range(max_dist):
        nxt = []
        for loc in frontier:
            for n, _w in sd.adjacent_to(loc):
                if n not in seen:
                    seen.add(n)
                    nxt.append(n)
        frontier = nxt
    return seen


@register_event("S18")

def S18_event(state, side, args, rng):
    """S18 CORTONA (Hold). Three uses (AoW Reference):

      mode='treachery_free' (default): play with a Treachery in the Plan so
        that Revolt or Bribe targeting Cortona (or a target at Cortona)
        succeeds for 0 Coin and no roll. Registers a one-shot modifier the
        Treachery handler consumes.
      mode='add_treachery': if Cortona has Ghibelline Allegiance (not Ruins),
        add one set-aside Ghibelline Treachery card to the Ghibelline Command
        deck. args.treachery_card optional (else FIFO).
      mode='revolt_roll': if Cortona Ghibelline, roll the Revolt Table (1
        purple + 1 gold) and flip an eligible Enemy Stronghold (args.
        target_locale) per 1.4.1/1.4.2. The physical Revolt-Table chart
        (die->named Locale) is not reproduced; eligibility (Enemy, not
        Ruins/Outpost, no Enemy Lord at/adjacent, within 1 Locale of a
        Ghibelline cylinder/marker) is the faithful gate, with both dice
        rolled for audit.
    """
    if side != "ghibelline":
        return {"applied": False, "reason": "S18 is a Ghibelline card."}
    cortona = state["locales"].get("Cortona", {})
    cortona_ghib = (not cortona.get("ruins") and
                    any(m.get("side") == "ghibelline"
                        for m in cortona.get("current_allegiance", []) or []))
    mode = args.get("mode", "treachery_free")

    if mode == "treachery_free":
        state.setdefault("treachery_modifiers_pending", []).append({
            "id": "S18", "side": "ghibelline", "effect": "cortona_treachery_free",
        })
        return {"applied": True, "flag_set": "cortona_treachery_free"}

    if mode == "add_treachery":
        if not cortona_ghib:
            return {"applied": False,
                    "reason": "Cortona must have Ghibelline Allegiance (not Ruins)."}
        set_aside = state["decks"]["ghibelline"]["treachery_set_aside"]
        if not set_aside:
            return {"applied": False, "reason": "No set-aside Ghibelline Treachery cards."}
        want = args.get("treachery_card")
        card = want if (want in set_aside) else set_aside[0]
        set_aside.remove(card)
        state["decks"]["ghibelline"]["command_deck"].append(card)
        return {"applied": True, "added_treachery": card}

    if mode == "revolt_roll":
        if not cortona_ghib:
            return {"applied": False,
                    "reason": "Cortona must have Ghibelline Allegiance to roll Revolt."}
        # S18: the Ghibellines roll once on the 'Revolt Against Guelphs' table
        # (1.4.2). Decisions (Submission / fallback) park as pending_revolts;
        # the consumer resolves via cmd_resolve_revolt.
        from . import revolt as _rv
        trig = _rv.trigger_revolts(state, losing_side="guelph", count=1,
                                   rng=rng, context="s18_cortona")
        return {"applied": True, "revolt_rolls": trig["revolt_rolls"]}

    return {"applied": False, "reason": "mode must be treachery_free, add_treachery, or revolt_roll."}


@register_event("S19")
def S19_event(state, side, args, rng):
    """S19 BRIGANDS (Hold). Play as an Enemy (Guelph) Lord Marches within 2
    Locales of Giordano or Astimberg for the receiver to take from that
    Enemy one of: 2 Coin, or 2 Loot, or 4 Carts and 4 Provender.

    args:
      target_lord_id:   the Guelph Lord that just Marched (loses Assets).
      receiver_lord_id: 'giordano' or 'astimberg' (gains Assets); must be
                        Mustered Ghibelline within 2 Locales of the target.
      bundle:           'coin' (2 Coin) | 'loot' (2 Loot) |
                        'carts_prov' (4 Carts + 4 Provender). Default 'coin'.
    Assets are capped at what the target actually holds (Hidden Mats lets
    the chooser switch bundles; here we transfer what is available).

    SMOKE-Inferno-047 (asset-key fidelity): the 'carts_prov' bundle uses the
    canonical singular asset key "Cart" (not "Carts"), so the transfer
    actually moves Carts off a real Lord instead of silently no-op'ing.
    """
    if side != "ghibelline":
        return {"applied": False, "reason": "S19 is a Ghibelline card."}
    target_lid = args.get("target_lord_id")
    receiver_lid = args.get("receiver_lord_id")
    if not target_lid or target_lid not in state["lords"]:
        return _manual("S19", "Provide target_lord_id (the Guelph Lord that Marched).")
    if receiver_lid not in ("giordano", "astimberg"):
        return _manual("S19", "Provide receiver_lord_id: 'giordano' or 'astimberg'.")
    target = state["lords"][target_lid]
    receiver = state["lords"].get(receiver_lid)
    if target.get("side") != "guelph":
        return {"applied": False, "reason": f"{target_lid} is not a Guelph Lord."}
    if not receiver or receiver.get("status") != "mustered":
        return {"applied": False, "reason": f"{receiver_lid} is not Mustered."}
    tloc, rloc = target.get("location"), receiver.get("location")
    if not tloc or not rloc or tloc not in _locales_within(state, rloc, 2):
        return {"applied": False,
                "reason": f"{target_lid} ({tloc}) not within 2 Locales of {receiver_lid} ({rloc})."}
    bundle = args.get("bundle", "coin")
    plans = {"coin": {"Coin": 2}, "loot": {"Loot": 2},
             "carts_prov": {"Cart": 4, "Provender": 4}}
    if bundle not in plans:
        return _manual("S19", "bundle must be 'coin', 'loot', or 'carts_prov'.")
    moved = {}
    for asset, n in plans[bundle].items():
        take = min(n, target.get("assets", {}).get(asset, 0))
        if take > 0:
            target["assets"][asset] -= take
            if target["assets"][asset] <= 0:
                target["assets"].pop(asset, None)
            receiver.setdefault("assets", {})
            receiver["assets"][asset] = receiver["assets"].get(asset, 0) + take
            moved[asset] = take
    return {"applied": True, "from": target_lid, "to": receiver_lid,
            "bundle": bundle, "transferred": moved}


@register_event("S20")
def S20_event(state, side, args, rng):
    """S20 HEAT & FROST (Ghib mirror).

    SMOKE-Inferno-019 (card-text fidelity): mirror of F20 with the
    Summer-side effect "remove 1 unit from Guido" (Guido Guerra
    specifically, not generic Ritter).
    """
    from . import static_data as sd
    season = sd.SEASON_BY_BOX.get(state["meta"]["turn"], "winter")
    if season not in ("summer", "winter"):
        return {"applied": False, "reason": "Heat & Frost requires Summer or Winter season."}
    log = {"wastage": [], "guido_unit_removed": None}
    for lid, lord in state["lords"].items():
        if lord["status"] != "mustered":
            continue
        loc = state["locales"].get(lord.get("location") or "")
        at_siege = bool(loc and loc.get("siege"))
        moved = bool(lord.get("flags", {}).get("moved_fought"))
        cycles = 2 if (at_siege or moved) else 1
        for _ in range(cycles):
            eligible = False
            for a, c in lord.get("assets", {}).items():
                if c > 1:
                    lord["assets"][a] -= 1
                    log["wastage"].append({"lord_id": lid, "asset": a})
                    eligible = True
                    break
            if not eligible and len(lord.get("capabilities", [])) > 1:
                cid = lord["capabilities"].pop()
                state["decks"][lord["side"]]["aow_deck"].append(cid)
                log["wastage"].append({"lord_id": lid, "capability": cid})
    # Summer: remove 1 unit from Guido Guerra (per card)
    if season == "summer":
        guido = state["lords"].get("guido_guerra")
        if guido and guido.get("forces"):
            for u, c in list(guido["forces"].items()):
                if c > 0:
                    guido["forces"][u] -= 1
                    if guido["forces"][u] <= 0:
                        guido["forces"].pop(u)
                    log["guido_unit_removed"] = u
                    break
    return {"applied": True, **log}


@register_event("S21")
def S21_event(state, side, args, rng):
    """S21 CONSTITUTO – City statute (Hold).

      mode = 'shift' (default): shift Siena or Pisa cylinder left or
            Service right by 2 boxes.
      mode = 'lordship':       +3 Lordship to one (one-shot).
    """
    target = args.get("target", "siena")
    if target not in ("siena", "pisa"):
        return {"applied": False, "reason": "target must be siena or pisa"}
    if args.get("mode") == "lordship":
        state["lords"][target].setdefault("flags", {})["lordship_bonus_pending"] = 3
        return {"applied": True, "lordship_bonus_for": target, "bonus": 3}
    if state["lords"][target].get("calendar_box") is not None:
        return {"applied": True, "cylinder_to": _shift_cylinder_left(state, target, 2)}
    elif state["lords"][target].get("service_box") is not None:
        return {"applied": True, "service_to": _shift_service_right(state, target, 2)}
    return {"applied": False, "reason": f"{target} has no Calendar marker"}


@register_event("S22")
def S22_event(state, side, args, rng):
    """S22 CLOSED GATES (Ghib mirror of F10).

    Remove 1 purple (Ghib-owned) Ruins, else remove 1 gold Ruins
    where Stronghold eligible for Revolt -> Revolts to Ghibelline.
    """
    purple_ruins = [n for n, l in state["locales"].items() if l.get("ruins") == "purple"]
    if purple_ruins:
        loc_name = args.get("locale") or purple_ruins[0]
        state["locales"][loc_name]["ruins"] = None
        state["vp"]["guelph"] = max(state["vp"].get("guelph", 0) - 0.5, 0)
        return {"applied": True, "removed_ruins_at": loc_name}
    gold_ruins = [n for n, l in state["locales"].items() if l.get("ruins") == "gold"]
    if gold_ruins:
        loc_name = args.get("locale") or gold_ruins[0]
        loc = state["locales"][loc_name]
        from . import static_data as sd
        size = sd.STRONGHOLDS.get(loc["type"], {}).get("size", 1)
        loc["ruins"] = None
        state["vp"]["ghibelline"] = max(state["vp"].get("ghibelline", 0) - 0.5, 0)
        loc["current_allegiance"] = [m for m in loc.get("current_allegiance", []) if m.get("side") != "guelph"]
        for _ in range(size):
            loc["current_allegiance"].append({"side": "ghibelline", "value": 1})
        state["vp"]["ghibelline"] = min(state["vp"].get("ghibelline", 0) + size, 17.5)
        return {"applied": True, "revolted_at": loc_name, "size": size}
    return {"applied": False, "reason": "no eligible Ruins"}


@register_event("S23")
def S23_event(state, side, args, rng):
    """S23 ECONOMIC SANCTIONS — This Campaign, no Guelph Tax.

    Per AoW Reference: 'This Campaign, no Guelph Tax.' The Capability
    on this card (Taglia) will not be available this Turn.
    Implemented by registering an active_event for this_campaign.
    """
    state.setdefault("active_events", {}).setdefault("this_campaign", []).append({
        "id": "S23", "side": "ghibelline", "name": "Economic Sanctions",
        "effect": "no_guelph_tax_this_campaign",
    })
    return {"applied": True, "flag_set": "no_guelph_tax_this_campaign"}


@register_event("S24")
def S24_event(state, side, args, rng):
    """S24 DOCTORS (Ghib): roll Protection for each Routed Ghib unit."""
    log = []
    for lid, lord in state["lords"].items():
        if lord["side"] != "ghibelline":
            continue
        routed = dict(lord.get("routed_units", {}))
        for unit, count in routed.items():
            if unit == "Villici":
                continue
            u = sd.UNITS.get(unit, {})
            prot = u.get("protection", [])
            for _ in range(count):
                r = rng.roll(f"doctors_{lid}_{unit}")
                if r.value in prot:
                    lord["routed_units"][unit] -= 1
                    if lord["routed_units"][unit] <= 0:
                        lord["routed_units"].pop(unit, None)
                    lord["forces"][unit] = lord["forces"].get(unit, 0) + 1
                    log.append({"lord": lid, "unit": unit, "recovered": True})
    return {"applied": True, "recoveries": log}


@register_event("S25")
def S25_event(state, side, args, rng):
    """S25 MAREMMA — Ghibelline War event."""
    state["war_declared_this_levy"] = list(set(state.get("war_declared_this_levy", [])) | {"ghibelline"})
    return {"applied": True, "war_event": "ghibelline"}


@register_event("S26")
def S26_event(state, side, args, rng):
    """S26 MONTEPULCIANO — Ghib War event."""
    state["war_declared_this_levy"] = list(set(state.get("war_declared_this_levy", [])) | {"ghibelline"})
    return {"applied": True, "war_event": "ghibelline"}


# =====================================================================
# Ghibelline Capabilities (S1-S26)
# =====================================================================
register_capability("S1", {"supply_max_from_seat": 4, "supply_while_besieged_at_own_seat": True,
                          "applies_to_side": "ghibelline"})
register_capability("S2", {"siege_extra_marker": 1, "this_lord": True})
register_capability("S3", {"storm_walls_minus": 1, "this_lord": True})
register_capability("S4", {"siege_extra_marker": 1, "this_lord": True})
register_capability("S5", {"siege_walls_minus_1_storm": True, "this_lord": True})
register_capability("S6", {"feditori": True, "this_lord": True})  # extra Cavalieri strike Battle
register_capability("S7", {"luceria": True, "this_lord": True})    # extra Militia archery
register_capability("S8", {"crossbow_for_units": ["Men-at-Arms"], "this_lord": True})
register_capability("S9", {})
register_capability("S10", {"this_lord": True})
register_capability("S11", {})  # Volterra Capability
register_capability("S12", {"army_reserve": True, "this_lord": True})
register_capability("S13", {})  # Gentle Usilia Capability
register_capability("S14", {})  # Friars
register_capability("S15", {})  # War Loans
register_capability("S16", {"this_lord": True})  # Bocca degli Abati
register_capability("S17", {})
register_capability("S18", {"ravage_extra_loot": True, "this_lord": True})  # La Cavallata (Ghib)
register_capability("S19", {"ravage_extra_provender": True, "this_lord": True})  # Gualdana (Ghib)
register_capability("S20", {"ravage_extra_loot": True, "this_lord": True})  # Masnadieri (Ghib)
register_capability("S21", {"sovrintendente": True, "applies_to_side": "ghibelline"})
register_capability("S22", {"manfredi": True, "applies_to_side": "ghibelline",
                            "vp_bonus_scenario_c": 3})
register_capability("S23", {"taglia": True, "applies_to_side": "ghibelline"})
register_capability("S24", {"astrologers": True, "this_lord": True})
register_capability("S25", {"walls_plus_one_for_seats": True, "this_lord": True})
register_capability("S26", {"repair_ruins": True, "this_lord": True})


def apply_event_effect(state, card_id: str, side: str, args: dict, rng) -> dict[str, Any]:
    """Call the registered Event effect for `card_id` (or no-op if no
    handler is registered)."""
    handler = EVENT_EFFECTS.get(card_id)
    if handler is None:
        return {"manual": True, "card_id": card_id, "note": "No effect handler registered."}
    return handler(state, side, args, rng)
