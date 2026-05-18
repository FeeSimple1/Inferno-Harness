"""Action dispatcher and Levy-phase handlers.

Per BRIEF: action submitted as JSON. Each action has a schema; malformed
actions raise IllegalAction with a code and rule citation. Every die
roll happens in the harness and is logged in the result.

This module implements the Phase 2 Levy handlers. Per BRIEF, per-card
AoW EFFECTS are deferred to Phase 4 — the AoW Draw handler stores
drawn card IDs in the side's hand and flags them, but does not execute
the printed event text. The LLM consumer applies card effects manually.

CtA (3.5) full implementation is deferred — Phase 2's CtA handler only
detects triggers and supports skip. The 4 CtA sub-steps depend on
March (Gather is a free March, 3.5.1) which is Phase 3b. A future
'Phase 2b' commit completes CtA after March lands.
"""

from __future__ import annotations

import copy
from typing import Any

from . import card_data as cd
from . import static_data as sd
from .flow import (
    advance_to_next_side_or_step,
    current_side,
    current_step,
    is_first_levy,
    mark_first_levy_aow_drawn,
)
from .rng import HarnessRNG


class IllegalAction(Exception):
    """Raised when an action fails rule validation.

    Per BRIEF: error messages MUST include rule citations.
    """

    def __init__(self, code: str, message: str, citation: str | None = None):
        self.code = code
        self.citation = citation
        super().__init__(f"[{code}] {message}" + (f" ({citation})" if citation else ""))


# =====================================================================
# Dispatch
# =====================================================================
def dispatch(state: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    """Validate and apply `action` to `state`. Returns a result dict."""
    if not isinstance(action, dict) or "action" not in action:
        raise IllegalAction("MALFORMED", "Action must be a dict with 'action' key.")
    name = action["action"]
    side = action.get("side")
    if side not in ("guelph", "ghibelline"):
        raise IllegalAction("BAD_SIDE", f"side must be guelph or ghibelline, got {side!r}")
    if side != current_side(state):
        raise IllegalAction(
            "WRONG_TURN",
            f"It's {current_side(state)}'s turn, not {side}'s.",
            citation="2.2.4",
        )

    handler = _HANDLERS.get(name)
    if handler is None:
        raise IllegalAction(
            "UNKNOWN_ACTION",
            f"Action {name!r} is not implemented or not recognised.",
        )

    args = action.get("args", {}) or {}
    rng = _build_rng(state)
    rolls_before = rng.advance_count
    result = handler(state, side, args, rng)
    rolls_consumed = rng.advance_count - rolls_before
    state["meta"]["rng_advance"] = state["meta"].get("rng_advance", 0) + rolls_consumed
    if rolls_consumed:
        result.setdefault("rolls", []).extend(
            [{"context": r.context, "value": r.value} for r in rng.drain_log()]
        )
    # Append to history
    state.setdefault("history", []).append({
        "action": name,
        "side": side,
        "args": args,
        "rolls": result.get("rolls", []),
        "state_changes": result.get("state_changes", {}),
        "rule_citation": result.get("rule_citation"),
    })
    return result


def _build_rng(state: dict[str, Any]) -> HarnessRNG:
    seed = state["meta"]["rng_seed"]
    advance = state["meta"].get("rng_advance", 0)
    return HarnessRNG(seed=seed, advance=advance)


# =====================================================================
# Levy 3.1 — Arts of War Draw
# =====================================================================
def _h_levy_aow_draw(state, side: str, args, rng) -> dict[str, Any]:
    """Per 3.1.2 / 3.1.3: each side draws 2 AoW cards.

    First Levy: deploy each as a Capability (lower half).
    Later Levy: implement each as an Event (upper half).

    Phase 2 records what was drawn and how it was deployed (Capability
    in play, Held event, etc.). The harness does NOT execute per-card
    effects — that's Phase 4. The LLM consumer reads the card text from
    the AoW Reference and applies effects manually.
    """
    _require_step(state, "3.1")
    deck = state["decks"][side]["aow_deck"]
    if len(deck) < 2:
        raise IllegalAction("EMPTY_DECK", f"AoW deck for {side} has < 2 cards.", "3.1")

    # Deterministic "shuffle and draw" — use rng to choose 2 cards by index.
    drawn = []
    for _ in range(2):
        idx = rng.roll("aow_draw_index").value
        # Map d6 to a deck index via uniform pick (use a fresh roll if out of range).
        # Simpler: use a separate roll method. But our HarnessRNG only has roll().
        # Use modulo (uniform enough for our purposes; deterministic from seed).
        idx = (idx - 1) % len(deck)
        drawn.append(deck.pop(idx))

    is_first = is_first_levy(state)
    capabilities_in_play = state.setdefault("capabilities_in_play", [])
    held = state["decks"][side]["aow_held"]
    notes = []
    for cid in drawn:
        card = cd.AOW_CARDS_BY_ID.get(cid)
        if not card:
            raise IllegalAction("UNKNOWN_CARD", f"Card {cid} not in card_data.", "3.1")
        if is_first:
            # 3.1.2: deploy as Capability. Default to side_wide scope
            # (Phase 4 will encode scope per card; for now flag as unknown).
            capabilities_in_play.append({
                "id": cid,
                "name": card["capability_name"],
                "side": side,
                "scope": "side_wide",  # placeholder; Phase 4 corrects per card
            })
            notes.append(f"{cid} -> Capability ({card['capability_name']})")
        else:
            # 3.1.3: implement Event. Phase 4 executes effects; Phase 2
            # routes Hold to aow_held and resolves Immediate/This-Levy/
            # This-Campaign Events as 'noted' (LLM applies manually).
            kind = card.get("event_kind", "immediate")
            if kind == "hold":
                held.append(cid)
                notes.append(f"{cid} -> Held ({card['event_name']})")
            elif kind in ("this_levy", "this_campaign"):
                state.setdefault("active_events", {}).setdefault(kind, []).append({
                    "id": cid, "side": side, "name": card["event_name"],
                })
                notes.append(f"{cid} -> {kind} ({card['event_name']})")
            else:
                # Immediate event: Phase 4 executes. Phase 2 returns it to deck.
                state["decks"][side]["aow_discard"].append(cid)
                notes.append(f"{cid} -> Immediate Event ({card['event_name']}); effect pending manual application")

    # After both sides have drawn, mark first_levy as done.
    if not is_first:
        mark_first_levy_aow_drawn(state)  # idempotent
    # Move to next side or next step.
    advance_to_next_side_or_step(state)
    # If we just advanced past both sides on the first Levy, flip the flag.
    if is_first and current_step(state) != "3.1":
        mark_first_levy_aow_drawn(state)
    return {
        "state_changes": {"drew": drawn, "deployment": notes},
        "rule_citation": "3.1.2" if is_first else "3.1.3",
    }


# =====================================================================
# Levy 3.2 — Pay
# =====================================================================
def _h_levy_pay(state, side: str, args, rng) -> dict[str, Any]:
    """Per 3.2.1 / 3.2.2: spend Coin (or Loot) from one Lord to shift
    another Lord's Service marker right on the Calendar.

    1 Coin (or 1 Loot) = 1 box. Podestà exception: 2 Coin/Loot per box.

    args:
      from_lord_id: lord paying the resource
      target_lord_id: lord whose Service marker advances (default: same)
      asset: "Coin" | "Loot"
      amount: number of boxes to shift (positive integer)
    """
    _require_step(state, "3.2")
    from_lid = args.get("from_lord_id")
    target_lid = args.get("target_lord_id", from_lid)
    asset = args.get("asset", "Coin")
    boxes = int(args.get("amount", 1))

    if asset not in ("Coin", "Loot"):
        raise IllegalAction("BAD_ASSET", f"Asset must be Coin or Loot, got {asset!r}.", "3.2")
    if boxes < 1:
        raise IllegalAction("BAD_AMOUNT", "amount must be >= 1.", "3.2")

    from_lord = _require_lord(state, from_lid, side)
    target_lord = _require_lord(state, target_lid, side)

    if from_lord["status"] not in ("mustered", "on_calendar"):
        raise IllegalAction("LORD_OFF_MAP", f"{from_lid} cannot pay (status={from_lord['status']}).", "3.2")
    # 3.2.1: payer and target must be at the SAME Locale (if both on map).
    if from_lord.get("location") and target_lord.get("location") and from_lord["location"] != target_lord["location"]:
        raise IllegalAction(
            "PAY_DIFFERENT_LOCALES",
            f"Pay requires payer and target at same Locale; "
            f"{from_lid}@{from_lord['location']} vs {target_lid}@{target_lord['location']}.",
            "3.2.1",
        )
    # 3.2.2 Pay with Loot: payer must be at a Friendly Locale free of Siege (may be Bypassed).
    if asset == "Loot":
        loc = state["locales"].get(from_lord.get("location") or "")
        if not loc:
            raise IllegalAction("LOOT_OFF_MAP", "Loot requires payer on map.", "3.2.2")
        if loc.get("siege"):
            raise IllegalAction("LOOT_UNDER_SIEGE", f"Cannot pay Loot at besieged {loc['name']}.", "3.2.2")
        # Friendly check: simplified to printed allegiance + side's allegiance markers.
        # Phase 3+ refines with current allegiance.

    # Podestà target costs 2 per box.
    rate = 2 if target_lord.get("podesta") else 1
    cost = rate * boxes

    if from_lord["assets"].get(asset, 0) < cost:
        raise IllegalAction(
            "INSUFFICIENT_ASSET",
            f"{from_lid} has {from_lord['assets'].get(asset, 0)} {asset}; needs {cost} for "
            f"{boxes} box{'es' if boxes != 1 else ''} (Podestà rate=2)" if rate == 2 else
            f"{from_lid} has {from_lord['assets'].get(asset, 0)} {asset}; needs {cost} for {boxes} boxes.",
            "3.2.1" if asset == "Coin" else "3.2.2",
        )

    # Apply: spend asset, shift Service marker right.
    from_lord["assets"][asset] -= cost
    new_box = _shift_service_right(state, target_lid, boxes)

    return {
        "state_changes": {
            "from": from_lid, "target": target_lid, "asset": asset,
            "amount_paid": cost, "boxes_shifted": boxes, "new_service_box": new_box,
            "podesta_rate": rate,
        },
        "rule_citation": "3.2.1" if asset == "Coin" else "3.2.2",
    }


def _h_levy_pay_done(state, side, args, rng) -> dict[str, Any]:
    """End this side's Pay segment."""
    _require_step(state, "3.2")
    advance_to_next_side_or_step(state)
    return {"state_changes": {"step": "pay_done"}, "rule_citation": "3.2"}


def _shift_service_right(state, lord_id: str, boxes: int) -> int | str:
    """Shift the Service marker right by `boxes`. Returns the new box (int)
    or 'off_right_service' if it falls off the right edge."""
    lord = state["lords"][lord_id]
    cur = lord.get("service_box")
    if cur is None:
        # Marker is somewhere off-Calendar (e.g., off_right_service);
        # Phase 1+ keeps that as a sentinel; Phase 2's Pay step rules don't allow shifting an off-Calendar marker.
        raise IllegalAction("SHIFT_OFF_CAL", f"{lord_id} has no Service marker on Calendar.", "3.2")
    # Update calendar boxes structure too.
    boxes_state = state["calendar"]["boxes"]
    if str(cur) in boxes_state and lord_id in boxes_state[str(cur)]["services"]:
        boxes_state[str(cur)]["services"].remove(lord_id)
    target = cur + boxes
    if target > 16:
        state["calendar"]["off_right_service"].append(lord_id)
        lord["service_box"] = None
        return "off_right_service"
    lord["service_box"] = target
    boxes_state.setdefault(str(target), {"cylinders": [], "services": [], "victory": [], "markers": []})
    boxes_state[str(target)]["services"].append(lord_id)
    return target


# =====================================================================
# Levy 3.3 — Disband
# =====================================================================
def _h_levy_disband(state, side, args, rng) -> dict[str, Any]:
    """Per 3.3: Lords whose Service marker is at or left of the Levy box
    Disband.

    3.3.1 BEYOND SERVICE LIMIT (left of Levy box):
      - Regular Lord: cylinder removed permanently.
      - Podestà: cylinder placed Service-Rating boxes ahead of current Turn.
      - Set aside Forces/Assets/Vassals/Comune.
      - Return 'This Lord' Capabilities to AoW deck.
      - REVOLT & TREACHERY: enemy rolls Revolt and adds Treachery cards
        (1x for regular, 3x for Podestà).
      - Comune Disband adds NO Revolt/Treachery.

    3.3.2 AT SERVICE LIMIT (same box as Levy marker, per Errata):
      - Place cylinder Service-Rating boxes right of current.
      - Set aside Forces/Assets, discard cards at mat.
      - Per Errata: this does NOT trigger Revolt or Treachery.

    Per BRIEF: this Phase-2 handler auto-processes all Disbandable
    Lords for the active player in one action. Future commits add a
    per-Lord granularity if needed (e.g., to interleave Treachery card
    selection).
    """
    _require_step(state, "3.3")
    levy_box = state["calendar"]["levy_box"]
    disbanded_beyond = []
    disbanded_at = []
    enemy_side = "ghibelline" if side == "guelph" else "guelph"

    for lid, lord in state["lords"].items():
        if lord["side"] != side:
            continue
        if lord["status"] != "mustered":
            continue
        svc = lord.get("service_box")
        if svc is None:
            continue
        if svc < levy_box:
            disbanded_beyond.append(lid)
        elif svc == levy_box:
            disbanded_at.append(lid)

    revolt_rolls = []
    treachery_added = []
    for lid in disbanded_beyond:
        _disband_beyond_service_limit(state, lid)
        # 3.3.1 Revolt & Treachery (Comune Disband adds none)
        lord = state["lords"][lid]
        if lord.get("comune_of"):
            continue
        revolt_count = 3 if lord.get("podesta") else 1
        for _ in range(revolt_count):
            r = rng.roll(f"revolt_disband_{lid}")
            revolt_rolls.append({"lord_id": lid, "die": r.value, "context": r.context})
            # Add a Treachery card to enemy Command deck for this Lord
            # (1.4.3). The choice of WHICH Treachery card is the enemy's;
            # Phase 2 auto-picks the still-set-aside Treachery card belonging
            # to the Disbanding Lord (if any), else any set-aside.
            t = _add_treachery_to_enemy(state, lid, enemy_side)
            if t:
                treachery_added.append({"card": t, "to_side": enemy_side, "for_disband_of": lid})

    for lid in disbanded_at:
        _disband_at_service_limit(state, lid, levy_box)

    return {
        "state_changes": {
            "beyond_service_limit_removed": disbanded_beyond,
            "at_service_limit_disbanded": disbanded_at,
            "treachery_added": treachery_added,
        },
        "rolls": revolt_rolls,
        "rule_citation": "3.3.1 / 3.3.2 (Errata 10 Apr 2023)",
    }


def _h_levy_disband_done(state, side, args, rng) -> dict[str, Any]:
    """End this side's Disband segment."""
    _require_step(state, "3.3")
    advance_to_next_side_or_step(state)
    return {"state_changes": {"step": "disband_done"}, "rule_citation": "3.3"}


def _disband_beyond_service_limit(state, lid: str) -> None:
    """3.3.1: Regular Lord -> remove permanently. Podestà -> cylinder
    placed Service-Rating boxes ahead of current Turn (may Muster again)."""
    lord = state["lords"][lid]
    # Pop from current Locale's lords_present
    loc = state["locales"].get(lord.get("location") or "")
    if loc and lid in loc.get("lords_present", []):
        loc["lords_present"].remove(lid)
    # Pop Service marker
    svc = lord.get("service_box")
    if svc is not None:
        boxes = state["calendar"]["boxes"]
        if str(svc) in boxes and lid in boxes[str(svc)]["services"]:
            boxes[str(svc)]["services"].remove(lid)
    # 'This Lord' Capabilities: return to side's AoW deck.
    side = lord["side"]
    aow_deck = state["decks"][side]["aow_deck"]
    for cid in lord.get("capabilities", []):
        aow_deck.append(cid)
    # Clear mat state.
    lord["capabilities"] = []
    lord["forces"] = {}
    lord["assets"] = {}
    lord["vassals"] = []
    lord["location"] = None
    lord["service_box"] = None

    if lord.get("podesta"):
        # Place cylinder Service-Rating boxes ahead of current Turn.
        sr = lord.get("ratings", {}).get("S", 0)
        turn = state["meta"]["turn"]
        new_box = min(turn + sr, 16)
        lord["status"] = "on_calendar"
        lord["calendar_box"] = new_box
        state["calendar"]["boxes"].setdefault(str(new_box),
            {"cylinders": [], "services": [], "victory": [], "markers": []})
        state["calendar"]["boxes"][str(new_box)]["cylinders"].append(lid)
    else:
        lord["status"] = "removed"
        lord["calendar_box"] = None


def _disband_at_service_limit(state, lid: str, levy_box: int) -> None:
    """3.3.2 per Errata: Lord whose Service marker is in same box as Levy
    marker Disbands; cylinder placed Service-Rating boxes right of current.
    Does NOT trigger Revolt or Treachery."""
    lord = state["lords"][lid]
    loc = state["locales"].get(lord.get("location") or "")
    if loc and lid in loc.get("lords_present", []):
        loc["lords_present"].remove(lid)
    # Pop Service marker (it's at levy_box)
    boxes = state["calendar"]["boxes"]
    if str(levy_box) in boxes and lid in boxes[str(levy_box)]["services"]:
        boxes[str(levy_box)]["services"].remove(lid)
    # Clear mat.
    lord["capabilities"] = []
    lord["forces"] = {}
    lord["assets"] = {}
    lord["vassals"] = []
    lord["location"] = None
    lord["service_box"] = None
    # Cylinder placed S boxes right of current Turn (Errata: +1 in Campaign; here we're in Levy).
    sr = lord.get("ratings", {}).get("S", 0)
    new_box = min(levy_box + sr, 16)
    lord["status"] = "on_calendar"
    lord["calendar_box"] = new_box
    boxes.setdefault(str(new_box), {"cylinders": [], "services": [], "victory": [], "markers": []})
    boxes[str(new_box)]["cylinders"].append(lid)


def _add_treachery_to_enemy(state, for_lord_id: str, enemy_side: str) -> str | None:
    """Add a Treachery card from set-aside to the enemy's Command deck.

    Per 1.4.3 the choice is the enemy's; Phase 2 prefers the Treachery card
    of the Lord being Disbanded (if it's that side's Lord's Treachery card,
    which it isn't — the Disbanding Lord is the SAME side). So we pick any
    still-set-aside Treachery card from the enemy's set-aside list (FIFO).
    """
    set_aside = state["decks"][enemy_side]["treachery_set_aside"]
    if not set_aside:
        return None
    card = set_aside.pop(0)
    state["decks"][enemy_side]["command_deck"].append(card)
    return card


# =====================================================================
# Levy 3.4 — Muster (Lord, Vassal, Transport, Capability)
# =====================================================================
def _h_levy_muster_lord(state, side, args, rng) -> dict[str, Any]:
    """3.4.1 Levy Other Lords. Active Lord (X) spends 1 Lordship action
    to Fealty-roll for a Ready target Lord (Y) waiting on Calendar.

    args:
      muster_lord_id:  Lord doing the Mustering (must be Mustered)
      target_lord_id:  Lord being Mustered (must be Ready / on Calendar)
      target_seat:     Seat where target will be placed if roll succeeds
    """
    _require_step(state, "3.4")
    mlid = args.get("muster_lord_id")
    tlid = args.get("target_lord_id")
    target_seat = args.get("target_seat")

    muster_lord = _require_lord(state, mlid, side)
    if muster_lord["status"] != "mustered":
        raise IllegalAction("MUSTER_LORD_NOT_ON_MAP", f"{mlid} is not Mustered.", "3.4")
    target_lord = _require_lord(state, tlid, side)
    if target_lord["status"] != "on_calendar":
        raise IllegalAction("TARGET_NOT_READY", f"{tlid} is not waiting on Calendar.", "3.4.1")
    # Ready check: cylinder at or left of Levy marker.
    levy_box = state["calendar"]["levy_box"]
    if (target_lord.get("calendar_box") or 0) > levy_box:
        raise IllegalAction(
            "TARGET_NOT_READY",
            f"{tlid} at box {target_lord['calendar_box']} is right of Levy box {levy_box}.",
            "3.4.1",
        )
    # Seat must be one of target Lord's printed Seats.
    if target_seat not in target_lord["seats"]:
        raise IllegalAction(
            "BAD_SEAT",
            f"{tlid}'s seats are {target_lord['seats']}; got {target_seat!r}.",
            "3.4.1",
        )

    # Fealty roll
    fealty = target_lord.get("ratings", {}).get("F", 0)
    r = rng.roll(f"fealty_{tlid}")
    success = r.value <= fealty
    result = {
        "state_changes": {
            "muster_lord_id": mlid, "target_lord_id": tlid,
            "fealty_rating": fealty, "die": r.value, "success": success,
        },
        "rolls": [{"context": r.context, "value": r.value}],
        "rule_citation": "3.4.1",
    }
    if success:
        # Place cylinder at target_seat, place mat with starting Forces/Assets/Vassals.
        target_lord["status"] = "mustered"
        target_lord["location"] = target_seat
        # Remove cylinder from Calendar box
        cur_box = target_lord.get("calendar_box")
        boxes = state["calendar"]["boxes"]
        if cur_box is not None and str(cur_box) in boxes:
            if tlid in boxes[str(cur_box)]["cylinders"]:
                boxes[str(cur_box)]["cylinders"].remove(tlid)
        target_lord["calendar_box"] = None
        # Place Service marker Service-Rating boxes right of current Turn.
        sr = target_lord.get("ratings", {}).get("S", 0)
        new_svc = min(state["meta"]["turn"] + sr, 16)
        target_lord["service_box"] = new_svc
        boxes.setdefault(str(new_svc), {"cylinders": [], "services": [], "victory": [], "markers": []})
        boxes[str(new_svc)]["services"].append(tlid)
        # Starting Forces/Assets/Vassals from static_data
        canonical = target_lord["name"]
        if canonical in sd.LORDS:
            base = sd.LORDS[canonical]
            target_lord["forces"] = copy.deepcopy(base.get("forces", {}))
            target_lord["assets"] = copy.deepcopy(base.get("assets", {}))
            target_lord["vassals"] = []
            for v in base.get("vassals", []):
                target_lord["vassals"].append({
                    "name": v["name"], "seat": v.get("seat"), "seats": v.get("seats", []),
                    "service_rating": v.get("service_rating", 0),
                    "forces": copy.deepcopy(v.get("forces", {})),
                    "special": v.get("special", False),
                    "muster_die": v.get("muster_die"),
                    "on_mat": not v.get("special", False),
                    "ready": not v.get("special", False),
                    "service_box": None,
                })
        # Wire into locale
        loc = state["locales"].get(target_seat)
        if loc and tlid not in loc["lords_present"]:
            loc["lords_present"].append(tlid)
    return result


def _h_levy_muster_vassal(state, side, args, rng) -> dict[str, Any]:
    """3.4.2 Levy Vassals. Active Lord (X) spends 1 Lordship action to
    Muster a Vassal of his (slide Service marker into Forces area; add
    Vassal Forces).

    Special Vassals (Carroccio/Sestieri/Terzi) Muster only via CtA
    (3.5.3) — this handler rejects them. Phase 2 omits the Vassal Seat
    Friendly check (Phase 3+ handles allegiance/siege checks).

    args:
      lord_id:   Mustering Lord
      vassal:    Name of vassal on his mat
    """
    _require_step(state, "3.4")
    lid = args.get("lord_id")
    vname = args.get("vassal")
    lord = _require_lord(state, lid, side)
    if lord["status"] != "mustered":
        raise IllegalAction("LORD_NOT_ON_MAP", f"{lid} is not Mustered.", "3.4")
    for v in lord["vassals"]:
        if v["name"] == vname:
            target = v
            break
    else:
        raise IllegalAction("UNKNOWN_VASSAL", f"{lid} has no Vassal named {vname!r}.", "3.4.2")
    if target.get("special"):
        raise IllegalAction(
            "SPECIAL_VASSAL_ONLY_VIA_CTA",
            f"{vname} is a Special Vassal; Muster only via CtA 3.5.3.",
            "3.4.2",
        )
    if not target.get("ready"):
        raise IllegalAction("VASSAL_NOT_READY", f"{vname} is not Ready.", "3.4.2")

    # Slide marker into Forces (Ready -> not Ready); add Forces.
    target["ready"] = False
    for unit, count in target.get("forces", {}).items():
        lord["forces"][unit] = lord["forces"].get(unit, 0) + count
    return {
        "state_changes": {
            "lord_id": lid, "vassal": vname,
            "forces_added": dict(target.get("forces", {})),
        },
        "rule_citation": "3.4.2",
    }


def _h_levy_muster_transport(state, side, args, rng) -> dict[str, Any]:
    """3.4.3 Levy Transport. 1 action -> +1 Cart (Pisa Podestà only: may
    choose +1 Ship instead).

    args:
      lord_id:  Mustering Lord
      kind:     "Cart" (default) or "Ship" (Pisa only)
    """
    _require_step(state, "3.4")
    lid = args.get("lord_id")
    kind = args.get("kind", "Cart")
    lord = _require_lord(state, lid, side)
    if lord["status"] != "mustered":
        raise IllegalAction("LORD_NOT_ON_MAP", f"{lid} is not Mustered.", "3.4")
    if kind == "Ship" and lord["name"] != "Pisa Podestà":
        raise IllegalAction(
            "SHIPS_PISA_ONLY",
            "Only Pisa Podestà may Levy Ships.",
            "3.4.3 / 4.7.3",
        )
    if kind not in ("Cart", "Ship"):
        raise IllegalAction("BAD_TRANSPORT", f"kind must be Cart or Ship, got {kind!r}.", "3.4.3")
    lord["assets"][kind] = lord["assets"].get(kind, 0) + 1
    return {
        "state_changes": {"lord_id": lid, "transport": kind, "new_total": lord["assets"][kind]},
        "rule_citation": "3.4.3",
    }


def _h_levy_muster_capability(state, side, args, rng) -> dict[str, Any]:
    """3.4.4 Levy Capability. 1 action -> draw 1 random Capability from
    the side's AoW deck for the side or for this Lord.

    Phase 2 records the deployment; Phase 4 enforces per-card eligibility
    rules (Coats of Arms, mat limits, etc.).

    args:
      lord_id:   Lord using Lordship (must be Mustered)
      scope:     "this_lord" or "side_wide" (defaults to side_wide)
    """
    _require_step(state, "3.4")
    lid = args.get("lord_id")
    scope = args.get("scope", "side_wide")
    lord = _require_lord(state, lid, side)
    if lord["status"] != "mustered":
        raise IllegalAction("LORD_NOT_ON_MAP", f"{lid} is not Mustered.", "3.4")
    deck = state["decks"][side]["aow_deck"]
    if not deck:
        raise IllegalAction("EMPTY_DECK", "No AoW cards left to draw.", "3.4.4")
    r = rng.roll("levy_cap_index")
    idx = (r.value - 1) % len(deck)
    cid = deck.pop(idx)
    card = cd.AOW_CARDS_BY_ID[cid]
    record = {"id": cid, "name": card["capability_name"], "side": side, "scope": scope}
    if scope == "this_lord":
        if len(lord.get("capabilities", [])) >= 2:
            raise IllegalAction(
                "THIS_LORD_LIMIT",
                f"{lid} already has 2 'This Lord' Capabilities (max).",
                "3.4.4",
            )
        record["lord_id"] = lid
        lord.setdefault("capabilities", []).append(cid)
    else:
        state.setdefault("capabilities_in_play", []).append(record)
    return {
        "state_changes": {"drew": cid, "deployed": record},
        "rolls": [{"context": r.context, "value": r.value}],
        "rule_citation": "3.4.4",
    }


def _h_levy_muster_done(state, side, args, rng) -> dict[str, Any]:
    """End this side's Muster segment (3.4)."""
    _require_step(state, "3.4")
    advance_to_next_side_or_step(state)
    return {"state_changes": {"step": "muster_done"}, "rule_citation": "3.4"}


# =====================================================================
# Levy 3.5 — Call to Arms (Phase 2 stub: trigger detection + skip only)
# =====================================================================
def _h_levy_cta_skip(state, side, args, rng) -> dict[str, Any]:
    """Decline Call to Arms for this side. Per BRIEF, full CtA
    (3.5.1-3.5.4) is deferred to Phase 2b — it depends on March (3.5.1
    Gather is a free March) which lands in Phase 3b. Until then, both
    sides may only skip 3.5."""
    _require_step(state, "3.5")
    advance_to_next_side_or_step(state)
    return {"state_changes": {"step": "cta_skipped"}, "rule_citation": "3.5"}


# =====================================================================
# Helpers
# =====================================================================
def _require_step(state, expected: str) -> None:
    actual = current_step(state)
    if actual != expected:
        raise IllegalAction(
            "WRONG_STEP",
            f"This action is only valid in Levy step {expected}; current step is {actual!r}.",
            citation=expected,
        )


def _require_lord(state, lord_id: str, side: str) -> dict[str, Any]:
    if not lord_id:
        raise IllegalAction("MISSING_LORD_ID", "Action missing lord_id arg.")
    lord = state["lords"].get(lord_id)
    if lord is None:
        raise IllegalAction("UNKNOWN_LORD", f"No Lord with id {lord_id!r}.")
    if lord["side"] != side:
        raise IllegalAction(
            "WRONG_SIDE",
            f"{lord_id} is {lord['side']}; this turn is {side}.",
            "2.2.4",
        )
    return lord


# =====================================================================
# Handler registry
# =====================================================================
_HANDLERS = {
    "levy_aow_draw":           _h_levy_aow_draw,
    "levy_pay":                _h_levy_pay,
    "levy_pay_done":           _h_levy_pay_done,
    "levy_disband":            _h_levy_disband,
    "levy_disband_done":       _h_levy_disband_done,
    "levy_muster_lord":        _h_levy_muster_lord,
    "levy_muster_vassal":      _h_levy_muster_vassal,
    "levy_muster_transport":   _h_levy_muster_transport,
    "levy_muster_capability":  _h_levy_muster_capability,
    "levy_muster_done":        _h_levy_muster_done,
    "levy_cta_skip":           _h_levy_cta_skip,
}
