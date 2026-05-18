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
    """F1 AMBUSH (Hold): Enemy Avoid -> force one Avoider to Battle/Withdraw."""
    return _manual("F1", "On Enemy Avoid: choose one Avoiding Lord to Battle/Withdraw instead.")


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
    """F3 SURPRISE (Hold): on Besiege a Stronghold w/ no other Lord; place 2 Siege markers + Storm 3 rounds Walls-2."""
    return _manual("F3", "On Besiege alone: place 2 Siege markers; immediately Storm up to 3 rounds, Walls -2.")


@register_event("F4")
def F4_event(state, side, args, rng):
    """F4 SUDDEN CLASH (Hold): Round 1, named Lord's Horse Melee precedes all Archery and selects targets."""
    return _manual("F4", "In Battle Round 1: target Lord's Horse Melee precedes all Archery; Select Target.")


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
    """F6 HILLS (Hold): in Battle Defending, double Guelph Archery Hits (added Hits as Bowmen)."""
    return _manual("F6", "Defending in Battle: double all your Archery Hits this Battle; added Hits as Bowmen.")


@register_event("F7")
def F7_event(state, side, args, rng):
    """F7 GREEK FIRE (Hold): on Besieging Enemy Lord, reduce to 1 Siege marker, remove 1 unit, discard 1 This Lord cap.
    Target args: enemy_lord_id, unit_to_remove, capability_to_discard?
    """
    enemy_lid = args.get("enemy_lord_id")
    unit = args.get("unit_to_remove")
    if not enemy_lid or enemy_lid not in state["lords"]:
        return _manual("F7", "Specify enemy_lord_id + unit_to_remove to apply.")
    enemy = state["lords"][enemy_lid]
    locale = state["locales"].get(enemy.get("location"))
    if not locale or not locale.get("siege"):
        return {"applied": False, "reason": "target not at a Besieged Locale"}
    # Reduce to 1 marker
    if locale["siege"]:
        locale["siege"] = [{"side": locale["siege"][0]["side"], "color": locale["siege"][0]["color"], "count": 1}]
    # Remove one unit
    if unit and enemy["forces"].get(unit, 0) > 0:
        enemy["forces"][unit] -= 1
        if enemy["forces"][unit] <= 0:
            enemy["forces"].pop(unit, None)
    # Discard first This Lord Capability if any
    if enemy.get("capabilities"):
        cap_id = enemy["capabilities"].pop()
        state["decks"][enemy["side"]]["aow_deck"].append(cap_id)
    return {"applied": True, "target": enemy_lid, "removed_unit": unit}


@register_event("F8")
def F8_event(state, side, args, rng):
    """F8 SWAMP (Hold): non-Summer Battle Defending, Ghibelline Horse don't Strike R1."""
    return _manual("F8", "Defending in non-Summer Battle: Enemy Horse units skip Round 1.")


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
    """F11 POGGIO BONIZIO (Hold): if PB free of Ghib markers, +3 Lordship to a Lord OR add 1 Treachery."""
    return _manual("F11", "During Muster or CtA Allies, +3 Lordship to one Guelph Lord, OR add 1 Treachery.")


@register_event("F12")
def F12_event(state, side, args, rng):
    """F12 CAMP ATTACK (Hold): in Battle R1, take 2 Assets from each Enemy + remove 2 more."""
    return _manual("F12", "In Battle R1: take 2 Assets per Enemy Lord; remove 2 more.")


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
    """F15 CASOLE (Hold): Firenze Treachery at Castle auto-succeeds w/ 0 Coin, or add Firenze Treachery."""
    return _manual("F15", "On Firenze Treachery at a Castle: auto-succeed 0 Coin; OR add Firenze Treachery.")


@register_event("F16")
def F16_event(state, side, args, rng):
    """F16 BLOODY RED STREAM (Hold): first Guelph Routs, roll Protection now for each Routed unit."""
    return _manual("F16", "First Guelph Lord to Rout in Battle: roll Protection per Routed unit; recoveries unrout.")


@register_event("F17")
def F17_event(state, side, args, rng):
    """F17 FOREIGN HELP: shift Guido or Orvieto Service 2, or set aside 1 Treachery to shift cylinder to current Levy."""
    target = args.get("target", "guido_guerra")
    if target not in ("guido_guerra", "orvieto"):
        target = "guido_guerra"
    # Service shift 2 right (which is right for service)
    if state["lords"][target].get("service_box") is not None:
        new = _shift_service_right(state, target, boxes=2)
        return {"applied": True, "target": target, "service_to": new}
    # Otherwise: try cylinder shift to current Levy if a Treachery is sacrificed
    # Phase 4 simplified: just shift cylinder left to current Levy box if on Calendar
    return {"applied": False, "reason": "no service marker on Calendar"}


@register_event("F18")
def F18_event(state, side, args, rng):
    """F18 GROSSETO (Hold): Treachery at Grosseto 0 Coin OR if Grosseto Guelph, shift Santa Fiora 2."""
    return _manual("F18", "Treachery at Grosseto: succeed 0 Coin; OR if Grosseto Guelph, shift Santa Fiora 2.")


@register_event("F19")
def F19_event(state, side, args, rng):
    """F19 VOLTERRA: shift Colle or Lucca Service 2 OR add 1 Treachery."""
    if args.get("mode") == "treachery":
        return {"applied": True, "added": _add_treachery_from_set_aside(state, "guelph")}
    target = args.get("target", "colle")
    new = _shift_service_right(state, target, boxes=2)
    return {"applied": True, "target": target, "service_to": new}


@register_event("F20")
def F20_event(state, side, args, rng):
    """F20 HEAT & FROST (This Levy): each Lord may have 1 Provender added to mat."""
    state.setdefault("active_events", {}).setdefault("this_levy", []).append({
        "id": "F20", "side": side, "name": "Heat & Frost",
    })
    # Add 1 Provender to each Guelph Mustered Lord
    for lord in state["lords"].values():
        if lord["side"] == "guelph" and lord["status"] == "mustered":
            lord["assets"]["Provender"] = min(lord["assets"].get("Provender", 0) + 1, 16)
    return {"applied": True, "provender_added_to": [l for l in state["lords"] if state["lords"][l]["side"] == "guelph" and state["lords"][l]["status"] == "mustered"]}


@register_event("F21")
def F21_event(state, side, args, rng):
    """F21 PRIMO POPOLO: name a Guelph Vassal-Seat Locale; if Friendly, +1 Coin to Lord there."""
    return _manual("F21", "Name a Vassal-Seat at Friendly Locale: +1 Coin to Lord there.")


@register_event("F22")
def F22_event(state, side, args, rng):
    """F22 MANFREDI holds back: if Ghibelline Lord with Ritter Unmustered, do not Muster."""
    return _manual("F22", "Choose any Ghibelline Lord with Ritter shown on mat: he may not Muster this Levy.")


@register_event("F23")
def F23_event(state, side, args, rng):
    """F23 TREASURERS (Hold): pay 2 Coin to declare CtA OR add 1 Treachery."""
    return _manual("F23", "Pay 2 Coin from any Guelph Lord(s) to declare Call to Arms; OR pay 2 Coin to add 1 Treachery.")


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
    return _manual("S1", "See F1 Ambush — enemy Avoid forced-stand mechanic.")


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
    return _manual("S3", "See F3 Surprise.")


@register_event("S4")
def S4_event(state, side, args, rng):
    return _manual("S4", "See F4 Sudden Clash (Ghibelline version).")


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
    return _manual("S6", "See F6 Hills (Ghibelline Feditori-like effect).")


@register_event("S7")
def S7_event(state, side, args, rng):
    return _manual("S7", "See F7 Greek Fire (Ghibelline version).")


@register_event("S8")
def S8_event(state, side, args, rng):
    return _manual("S8", "See F8 Swamp (Ghibelline version).")


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
    return _manual("S10", "A Better Paid Death: Ghib mercenary bribe — flagged.")


@register_event("S11")
def S11_event(state, side, args, rng):
    """S11 VOLTERRA — Ghib mirror; shift Astimberg or Santa Fiora Service 2 OR add 1 Treachery."""
    if args.get("mode") == "treachery":
        return {"applied": True, "added": _add_treachery_from_set_aside(state, "ghibelline")}
    target = args.get("target", "astimberg")
    return {"applied": True, "target": target, "service_to": _shift_service_right(state, target, boxes=2)}


@register_event("S12")
def S12_event(state, side, args, rng):
    return _manual("S12", "See F12 Camp Attack (Ghibelline version).")


@register_event("S13")
def S13_event(state, side, args, rng):
    return _manual("S13", "Gentle Usilia ransoms prisoners — Ghib special Ransom.")


@register_event("S14")
def S14_event(state, side, args, rng):
    return _manual("S14", "Friars sent to deceive Florentines — flagged.")


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
    return _manual("S16", "Bocca degli Abati — Florentine betrays Guelphs (in-Battle effect).")


@register_event("S17")
def S17_event(state, side, args, rng):
    return _manual("S17", "Ghibelline Refugees — refugee influx, situational.")


@register_event("S18")
def S18_event(state, side, args, rng):
    return _manual("S18", "Cortona — Ghibelline shift / Treachery.")


@register_event("S19")
def S19_event(state, side, args, rng):
    return _manual("S19", "Brigands — Ghibelline harassment.")


@register_event("S20")
def S20_event(state, side, args, rng):
    """S20 HEAT & FROST: each Ghibelline Mustered Lord gains 1 Provender."""
    state.setdefault("active_events", {}).setdefault("this_levy", []).append({
        "id": "S20", "side": side, "name": "Heat & Frost",
    })
    for lord in state["lords"].values():
        if lord["side"] == "ghibelline" and lord["status"] == "mustered":
            lord["assets"]["Provender"] = min(lord["assets"].get("Provender", 0) + 1, 16)
    return {"applied": True}


@register_event("S21")
def S21_event(state, side, args, rng):
    return _manual("S21", "Constituto: This Campaign Tax modifier.")


@register_event("S22")
def S22_event(state, side, args, rng):
    return _manual("S22", "Closed Gates (Ghibelline); see F10.")


@register_event("S23")
def S23_event(state, side, args, rng):
    return _manual("S23", "Economic Sanctions — flagged.")


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
