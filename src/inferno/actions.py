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


# =====================================================================
# CAMPAIGN PHASE — Step A: Capability Discard (pre-Plan)
# =====================================================================
def _h_campaign_discard_capability(state, side, args, rng) -> dict[str, Any]:
    """Step A (pre-Plan): each side selects and discards side-wide
    Capability cards exceeding number of Mustered Lords (Comuni do NOT
    count as Mustered Lords for this).

    args:
      card_id:  the side-wide Capability to discard
    """
    _require_campaign_step(state, "capability_discard")
    cid = args.get("card_id")
    side_caps = [c for c in state["capabilities_in_play"]
                 if c.get("side") == side and c.get("scope") == "side_wide"]
    own_mustered_count = sum(
        1 for l in state["lords"].values()
        if l["side"] == side and l["status"] == "mustered" and not l.get("comune_of")
    )
    excess = len(side_caps) - own_mustered_count
    if excess <= 0:
        raise IllegalAction(
            "NO_EXCESS_CAPS",
            f"{side} has {len(side_caps)} side-wide Capabilities and "
            f"{own_mustered_count} Mustered Lords; no excess to discard.",
            "4.0 STEP A",
        )
    for i, c in enumerate(state["capabilities_in_play"]):
        if c.get("id") == cid and c.get("side") == side and c.get("scope") == "side_wide":
            state["capabilities_in_play"].pop(i)
            # Discard returns to AoW deck per 1.9.1 / Reset semantics; in-play -> aow_deck.
            state["decks"][side]["aow_deck"].append(cid)
            return {
                "state_changes": {"discarded": cid},
                "rule_citation": "4.0 STEP A",
            }
    raise IllegalAction(
        "CAP_NOT_FOUND",
        f"{side} has no side-wide Capability {cid!r} in play.",
        "4.0 STEP A",
    )


def _h_campaign_discard_done(state, side, args, rng) -> dict[str, Any]:
    """End this side's capability-discard segment."""
    _require_campaign_step(state, "capability_discard")
    # Validate: no remaining excess
    side_caps = [c for c in state["capabilities_in_play"]
                 if c.get("side") == side and c.get("scope") == "side_wide"]
    own_mustered_count = sum(
        1 for l in state["lords"].values()
        if l["side"] == side and l["status"] == "mustered" and not l.get("comune_of")
    )
    if len(side_caps) > own_mustered_count:
        raise IllegalAction(
            "EXCESS_REMAINS",
            f"{side} still has {len(side_caps)} side-wide Capabilities > {own_mustered_count} Mustered Lords; must discard more.",
            "4.0 STEP A",
        )
    from .flow import advance_campaign_side_or_step
    advance_campaign_side_or_step(state)
    return {"state_changes": {"step": "capability_discard_done"}, "rule_citation": "4.0 STEP A"}


# =====================================================================
# CAMPAIGN PHASE — Step B: Plan (4.1)
# =====================================================================
def _h_plan_add_card(state, side, args, rng) -> dict[str, Any]:
    """4.1.1/4.1.2: append a card to side's Plan stack (face down, order locked).

    args:
      card_id: command_<lord_id>, treachery_<lord_id>, or 'PASS'.
    """
    from .flow import current_campaign_step
    if current_campaign_step(state) != "plan":
        raise IllegalAction("WRONG_STEP", f"plan_add_card requires Campaign step plan; got {current_campaign_step(state)!r}.", "4.1")
    cid = args.get("card_id")
    stack = state["plan_stacks"][side]
    # Validate card type and availability.
    if cid == cd_PASS_CARD_ID():
        # Pass card — unlimited supply.
        stack.append(cid)
        return {"state_changes": {"appended": cid, "stack_size": len(stack)}, "rule_citation": "4.1.1"}
    if cid.startswith("command_"):
        if cid not in state["decks"][side]["command_deck"] or stack.count(cid) > 0:
            raise IllegalAction("CARD_NOT_AVAILABLE", f"{cid!r} not available in {side}'s Command deck or already in plan.", "4.1.1")
        stack.append(cid)
        return {"state_changes": {"appended": cid, "stack_size": len(stack)}, "rule_citation": "4.1.1"}
    if cid.startswith("treachery_"):
        if cid not in state["decks"][side]["command_deck"] or stack.count(cid) > 0:
            raise IllegalAction(
                "TREACHERY_NOT_AVAILABLE",
                f"{cid!r} not in {side}'s Command deck (Treachery cards enter via Revolt triggers, 1.4.3).",
                "4.1.1",
            )
        stack.append(cid)
        return {"state_changes": {"appended": cid, "stack_size": len(stack)}, "rule_citation": "4.1.1"}
    raise IllegalAction("UNKNOWN_CARD_TYPE", f"Card id {cid!r} not recognised.", "4.1.1")


def _h_plan_done(state, side, args, rng) -> dict[str, Any]:
    """Declare this side's Plan complete. Validates size matches the
    Season's Plan size from PLAN_SIZE_BY_SEASON."""
    from .flow import current_campaign_step, advance_campaign_side_or_step
    if current_campaign_step(state) != "plan":
        raise IllegalAction("WRONG_STEP", f"plan_done requires Campaign step plan; got {current_campaign_step(state)!r}.", "4.1")
    season = sd.SEASON_BY_BOX.get(state["meta"]["turn"], "winter")
    target_size = sd.PLAN_SIZE_BY_SEASON[season]
    actual_size = len(state["plan_stacks"][side])
    if actual_size != target_size:
        raise IllegalAction(
            "PLAN_WRONG_SIZE",
            f"{side}'s Plan has {actual_size} cards; Season {season!r} requires {target_size} (turn {state['meta']['turn']}).",
            "4.1.2",
        )
    advance_campaign_side_or_step(state)
    return {
        "state_changes": {"plan_size": actual_size, "season": season},
        "rule_citation": "4.1.2",
    }


# =====================================================================
# CAMPAIGN PHASE — Step C: Command Phase (4.2)
# =====================================================================
def _h_command_reveal(state, side, args, rng) -> dict[str, Any]:
    """Flip the top card of the active side's Plan stack (4.2)."""
    from .flow import current_campaign_step
    if current_campaign_step(state) != "command_phase":
        raise IllegalAction("WRONG_STEP", "command_reveal valid only in command_phase.", "4.2")
    stack = state["plan_stacks"][side]
    if not stack:
        # Both stacks empty: advance to end_campaign.
        if all(len(state["plan_stacks"][s]) == 0 for s in ("guelph", "ghibelline")):
            from .flow import advance_campaign_step
            advance_campaign_step(state)
            return {"state_changes": {"both_plans_empty": True}, "rule_citation": "4.2"}
        # If only this side's is empty but other's isn't, pass.
        _flip_active_side(state)
        return {"state_changes": {"side_empty_passes": side}, "rule_citation": "4.2"}
    cid = stack.pop(0)
    state["current_card"] = cid

    # Decide if Lord acts (Command card with on-map Lord) or card lapses.
    if cid == "PASS":
        return _finish_card(state, side, reason="pass_card", citation="4.2.4")

    if cid.startswith("command_"):
        lord_id = cid.removeprefix("command_")
        lord = state["lords"].get(lord_id)
        if lord is None or lord["status"] != "mustered":
            return _finish_card(state, side, reason="lord_off_map", citation="4.2.4")
        # Set up action budget = Command rating
        rating = lord.get("ratings", {}).get("C", 0)
        state["current_lord_id"] = lord_id
        state["actions_remaining"] = rating
        state["card_action_consumed_by_entire_card"] = False
        return {
            "state_changes": {
                "card_revealed": cid, "lord_id": lord_id, "actions_remaining": rating,
            },
            "rule_citation": "4.2.1",
        }

    if cid.startswith("treachery_"):
        # 4.2.3 Treachery card — Lord takes Revolt/Bribe/Pass; Phase 3a does
        # not implement Revolt or Bribe (those are 4.7.5 / 4.7.6, Phase 3c).
        # For Phase 3a the only legal response to a Treachery card is to
        # let it lapse (treat as Pass).
        return _finish_card(state, side, reason="treachery_pass_phase_3a", citation="4.2.3")

    raise IllegalAction("UNKNOWN_CARD_ON_TOP", f"Unrecognized card on top: {cid!r}.", "4.2")


def _finish_card(state, side, reason: str, citation: str) -> dict[str, Any]:
    """Conclude the current revealed card. Runs FPD (4.8) then flips active side."""
    state["current_card"] = None
    state["current_lord_id"] = None
    state["actions_remaining"] = None
    fpd_result = _run_fpd(state)
    _flip_active_side(state)
    return {
        "state_changes": {"card_finished": True, "reason": reason, "fpd": fpd_result},
        "rule_citation": citation,
    }


def _flip_active_side(state) -> None:
    cur = state["meta"]["active_player"]
    state["meta"]["active_player"] = "ghibelline" if cur == "guelph" else "guelph"


def _h_cmd_end_card(state, side, args, rng) -> dict[str, Any]:
    """Active Lord declares end of card's actions. Triggers FPD then flips side."""
    _require_active_lord(state, side, args.get("lord_id"))
    return _finish_card(state, side, reason="end_card", citation="4.2.6")


# =====================================================================
# Simple Command actions (4.6, 4.7.1, 4.7.2, 4.7.3, 4.7.4, 4.7.7)
# =====================================================================
def _h_cmd_tax(state, side, args, rng) -> dict[str, Any]:
    """4.7.4 TAX (entire-card): Unbesieged Lord at one of his Seats gains
    +1 Coin (Podestà: +2). Uses the ENTIRE Command card."""
    lid = _require_active_lord(state, side, args.get("lord_id"))
    lord = state["lords"][lid]
    loc = state["locales"].get(lord.get("location") or "")
    if not loc:
        raise IllegalAction("NO_LOCATION", f"{lid} has no map Locale.", "4.7.4")
    if loc.get("siege"):
        raise IllegalAction("BESIEGED", f"{lid} is Besieged at {loc['name']} and cannot Tax.", "4.7.4")
    if lord["location"] not in lord.get("seats", []):
        raise IllegalAction(
            "NOT_AT_OWN_SEAT",
            f"Tax requires Lord at one of his Seats. {lid} is at {lord['location']!r}; seats={lord.get('seats')}.",
            "4.7.4",
        )
    gain = 2 if lord.get("podesta") else 1
    lord["assets"]["Coin"] = lord["assets"].get("Coin", 0) + gain
    # Tax uses the entire card — consume all remaining actions.
    state["actions_remaining"] = 0
    state["card_action_consumed_by_entire_card"] = True
    # Mark Moved/Fought? Tax doesn't mark per rules — but the card ends.
    return _finish_card_with({"taxed": lid, "coin_gained": gain}, state, side,
                              reason="tax_entire_card", citation="4.7.4")


def _h_cmd_forage(state, side, args, rng) -> dict[str, Any]:
    """4.7.1 FORAGE (1 action): +1 Provender at Friendly Unbesieged
    Stronghold (auto, not Ruins); elsewhere depends on Season."""
    lid = _require_active_lord(state, side, args.get("lord_id"))
    lord = state["lords"][lid]
    loc = state["locales"].get(lord.get("location") or "")
    if not loc:
        raise IllegalAction("NO_LOCATION", f"{lid} has no map Locale.", "4.7.1")
    if loc.get("ravaged"):
        raise IllegalAction("LOCALE_RAVAGED", f"{loc['name']} is Ravaged; cannot Forage.", "4.7.1")
    # 4.7.1: may NOT be Besieged by Enemy Lords >= Stronghold Size.
    # Simplified Phase 3a: any Siege marker blocks Forage (refined later).
    if loc.get("siege"):
        raise IllegalAction("BESIEGED", f"{lid} is Besieged; Forage blocked (Phase 3a simplified).", "4.7.1")

    season = sd.SEASON_BY_BOX.get(state["meta"]["turn"], "winter")
    friendly_stronghold = _is_friendly_stronghold(state, loc, side)
    if friendly_stronghold:
        # Automatic +1, any Season (4.7.1).
        lord["forces"]  # touch
        lord["assets"]["Provender"] = min(lord["assets"].get("Provender", 0) + 1, 16)
        result = {"forage_method": "friendly_stronghold_auto", "season": season}
    else:
        # Elsewhere: Summer auto; Spring/Autumn 1d6 1-3; Winter no Forage.
        if season == "summer":
            lord["assets"]["Provender"] = min(lord["assets"].get("Provender", 0) + 1, 16)
            result = {"forage_method": "summer_auto", "season": season}
        elif season == "winter":
            raise IllegalAction(
                "NO_WINTER_FORAGE",
                "No Forage outside Friendly Strongholds in Winter.",
                "4.7.1",
            )
        else:
            r = rng.roll(f"forage_{lid}_{season}")
            got_one = r.value <= 3
            if got_one:
                lord["assets"]["Provender"] = min(lord["assets"].get("Provender", 0) + 1, 16)
            result = {"forage_method": f"{season}_die_roll", "die": r.value, "gained": int(got_one), "season": season}
    state["actions_remaining"] -= 1
    lord["flags"]["moved_fought"] = True
    return _maybe_end_card({"forage": result, "lord_id": lid}, state, side, citation="4.7.1")


def _h_cmd_ravage(state, side, args, rng) -> dict[str, Any]:
    """4.7.2 RAVAGE: 1 action at Castle, 2 actions at Town/City.
    Locale must be Enemy aligned and not already Ravaged."""
    lid = _require_active_lord(state, side, args.get("lord_id"))
    lord = state["lords"][lid]
    target_name = args.get("target_locale", lord.get("location"))
    target = state["locales"].get(target_name)
    if not target:
        raise IllegalAction("UNKNOWN_LOCALE", f"Locale {target_name!r} not found.", "4.7.2")

    # SMOKE-Inferno-001: Ravage pre-checks — own-territory, ravaged, friendly. See CROSS_PROJECT_LESSONS §1.
    if target.get("ravaged"):
        raise IllegalAction("ALREADY_RAVAGED", f"{target_name} is already Ravaged.", "4.7.2")
    if _is_friendly_locale(state, target, side):
        raise IllegalAction("FRIENDLY_LOCALE", f"Cannot Ravage Friendly {target_name}.", "4.7.2")

    cost = 2 if target["type"] in ("town", "city") else 1
    if state["actions_remaining"] < cost:
        raise IllegalAction(
            "INSUFFICIENT_ACTIONS",
            f"Ravage costs {cost} actions at {target['type']}; {state['actions_remaining']} remaining.",
            "4.7.2",
        )
    # Mark Ravaged (color = OPPOSITE printed Allegiance).
    target["ravaged"] = "purple" if target["allegiance"] == "guelph" else "gold"
    # Gains:
    if target["type"] == "castle":
        lord["assets"]["Provender"] = min(lord["assets"].get("Provender", 0) + 1, 16)
        gains = {"Provender": 1}
    else:
        lord["assets"]["Provender"] = min(lord["assets"].get("Provender", 0) + 1, 16)
        lord["assets"]["Loot"] = min(lord["assets"].get("Loot", 0) + 1, 8)
        gains = {"Provender": 1, "Loot": 1}
    # VP: 1/2 to side opposite of printed
    ravager_side = "guelph" if target["allegiance"] == "ghibelline" else "ghibelline"
    state["vp"][ravager_side] = min(state["vp"].get(ravager_side, 0.0) + 0.5, 17.5)
    state["actions_remaining"] -= cost
    lord["flags"]["moved_fought"] = True
    return _maybe_end_card({
        "ravaged_locale": target_name, "marker_color": target["ravaged"],
        "gains": gains, "vp_to_side": ravager_side, "actions_spent": cost,
    }, state, side, citation="4.7.2")


def _h_cmd_supply(state, side, args, rng) -> dict[str, Any]:
    """4.6 SUPPLY (1 action): add Provender from a Source via Transport.

    Phase 3a simplification: Source = the Lord's OWN Seat at a Stronghold
    he occupies (covers the trivial in-Seat case). Routed Supply via a
    chain of Locales + Carts is Phase 3b work (depends on path-finding).
    """
    lid = _require_active_lord(state, side, args.get("lord_id"))
    lord = state["lords"][lid]
    loc_name = lord.get("location")
    if loc_name not in lord.get("seats", []):
        raise IllegalAction(
            "SUPPLY_PATH_NOT_PHASE_3A",
            f"Phase 3a Supply requires Lord at his own Seat (no routed Supply yet); {lid} is at {loc_name!r}.",
            "4.6.1",
        )
    loc = state["locales"].get(loc_name)
    if not loc:
        raise IllegalAction("NO_LOCATION", f"{lid} has no map Locale.", "4.6")
    if loc.get("ruins"):
        raise IllegalAction("SOURCE_RUINED", f"Ruined Seat cannot be a Source.", "4.6.1")
    # Size determines max Provender from this Source:
    #   Castle=1, Town=2, City=3, Outpost=1.
    size_map = {"castle": 1, "town": 2, "city": 3, "outpost": 1}
    add = size_map.get(loc["type"], 1)
    lord["assets"]["Provender"] = min(lord["assets"].get("Provender", 0) + add, 16)
    state["actions_remaining"] -= 1
    return _maybe_end_card({"supply_added": add, "from": loc_name}, state, side, citation="4.6.2")


def _h_cmd_sail(state, side, args, rng) -> dict[str, Any]:
    """4.7.3 SAIL — Pisa Podestà only, entire-card, any Season except Winter.

    Phase 3a notes:
      - Movement validation (Ship count vs Forces/Provender/Loot) deferred
        to Phase 3b/3c (depends on March's transport accounting).
      - Sailing to an Enemy Stronghold places a Siege marker (4.7.3) —
        Siege subsystem is Phase 3c. Phase 3a rejects sail-to-Enemy.
    """
    lid = _require_active_lord(state, side, args.get("lord_id"))
    lord = state["lords"][lid]
    if lord["name"] != "Pisa Podestà":
        raise IllegalAction("SAIL_PISA_ONLY", "Only Pisa Podestà may Sail.", "4.7.3")
    season = sd.SEASON_BY_BOX.get(state["meta"]["turn"], "winter")
    if season == "winter":
        raise IllegalAction("NO_WINTER_SAIL", "Sail is unavailable in Winter.", "4.7.3")
    src_name = lord.get("location")
    src = state["locales"].get(src_name)
    if not src or not src.get("port"):
        raise IllegalAction("NOT_AT_PORT", f"Sail requires a Port; {lid} is at {src_name!r}.", "4.7.3")
    if src.get("siege"):
        raise IllegalAction("BESIEGED", f"{lid} is Besieged at {src_name}.", "4.7.3")
    dest_name = args.get("dest_locale")
    dest = state["locales"].get(dest_name)
    if not dest:
        raise IllegalAction("UNKNOWN_DEST", f"Destination {dest_name!r} not found.", "4.7.3")
    if not dest.get("port"):
        raise IllegalAction("DEST_NOT_PORT", f"{dest_name} is not a Port.", "4.7.3")
    # Phase 3a: reject Sail to an Enemy Stronghold (Siege subsystem is Phase 3c).
    if not _is_friendly_locale(state, dest, side):
        raise IllegalAction(
            "SAIL_TO_ENEMY_PHASE_3C",
            f"Sail to Enemy Stronghold places a Siege marker (4.7.3); Siege is Phase 3c. "
            f"Sail to a Friendly or already-Bypassed Enemy Port until then.",
            "4.7.3",
        )
    # Move
    if src_name and lid in src.get("lords_present", []):
        src["lords_present"].remove(lid)
    lord["location"] = dest_name
    dest.setdefault("lords_present", []).append(lid)
    lord["flags"]["moved_fought"] = True
    # Sail uses entire card.
    state["actions_remaining"] = 0
    state["card_action_consumed_by_entire_card"] = True
    return _finish_card_with({"sailed_from": src_name, "to": dest_name}, state, side,
                              reason="sail_entire_card", citation="4.7.3")


def _h_cmd_pass(state, side, args, rng) -> dict[str, Any]:
    """4.7.7 PASS — burn 1 (or all remaining) actions doing nothing."""
    lid = _require_active_lord(state, side, args.get("lord_id"))
    n = int(args.get("count", 1))
    n = min(n, state["actions_remaining"] or 0)
    state["actions_remaining"] = max(0, (state["actions_remaining"] or 0) - n)
    return _maybe_end_card({"passed_actions": n}, state, side, citation="4.7.7")


# =====================================================================
# FPD cycle (4.8)
# =====================================================================
def _run_fpd(state) -> dict[str, Any]:
    """4.8 Feed/Pay/Disband. Phase 3a auto-processes the cycle.

    4.8.1 FEED: Lords marked Moved/Fought feed (1/2/3 Provender per
                1-6/7-12/13+ units). Sharing at same Locale. Unfed:
                Service shifts 1 box left.
    4.8.2 PAY:  Both sides may Pay (3.2 rules).
    4.8.2 DISBAND: Lords at/past Service limit Disband per 3.3.
    4.8.3 Remove Moved/Fought markers.

    Phase 3a: Pay step is auto-skipped (LLM Pay decisions during FPD are
    a separate sub-step; skip for now — players who want to Pay during
    Campaign should do so explicitly when implemented in Phase 3b). The
    Errata-modified Disband (Beyond Service Limit Revolt/Treachery
    applies, Podestà cylinder placed on next box + Service Rating) is
    delegated to the same handlers as Levy Disband.
    """
    summary: dict[str, Any] = {"feed": [], "disband": []}
    # 4.8.1 FEED
    for lid, lord in state["lords"].items():
        if not lord.get("flags", {}).get("moved_fought"):
            continue
        units = sum(lord.get("forces", {}).values())
        need = 0 if units == 0 else (1 if units <= 6 else 2 if units <= 12 else 3)
        # Lord feeds himself first; Sharing deferred.
        available = lord["assets"].get("Provender", 0) + lord["assets"].get("Loot", 0)
        if available >= need:
            paid_prov = min(need, lord["assets"].get("Provender", 0))
            lord["assets"]["Provender"] = lord["assets"].get("Provender", 0) - paid_prov
            need_after_prov = need - paid_prov
            lord["assets"]["Loot"] = max(0, lord["assets"].get("Loot", 0) - need_after_prov)
            summary["feed"].append({"lord_id": lid, "units": units, "need": need, "fed": True})
        else:
            # UNFED: Service marker shifts 1 box left.
            cur = lord.get("service_box")
            if cur is not None:
                new = cur - 1
                boxes = state["calendar"]["boxes"]
                if str(cur) in boxes and lid in boxes[str(cur)]["services"]:
                    boxes[str(cur)]["services"].remove(lid)
                if new < 1:
                    state["calendar"]["off_left_service"].append(lid)
                    lord["service_box"] = None
                else:
                    lord["service_box"] = new
                    boxes.setdefault(str(new), {"cylinders": [], "services": [], "victory": [], "markers": []})
                    boxes[str(new)]["services"].append(lid)
            summary["feed"].append({"lord_id": lid, "units": units, "need": need, "fed": False, "service_shift": -1})

    # 4.8.2 DISBAND (per 3.3.1 + 3.3.2, with Errata for Campaign timing)
    levy_box = state["calendar"]["levy_box"]
    for side in ("guelph", "ghibelline"):
        for lid, lord in list(state["lords"].items()):
            if lord["side"] != side or lord["status"] != "mustered":
                continue
            svc = lord.get("service_box")
            if svc is None:
                # Off-Calendar (e.g., off_left_service): treat as Beyond Service Limit.
                _disband_beyond_service_limit(state, lid)
                summary["disband"].append({"lord_id": lid, "kind": "beyond_via_off_left"})
                continue
            if svc < levy_box:
                _disband_beyond_service_limit(state, lid)
                summary["disband"].append({"lord_id": lid, "kind": "beyond"})
            elif svc == levy_box:
                _disband_at_service_limit(state, lid, levy_box)
                summary["disband"].append({"lord_id": lid, "kind": "at"})

    # 4.8.3 remove Moved/Fought
    for lord in state["lords"].values():
        lord["flags"].pop("moved_fought", None)

    return summary


# =====================================================================
# Helpers (Campaign)
# =====================================================================
def _require_campaign_step(state, expected: str) -> None:
    from .flow import current_campaign_step
    cur = current_campaign_step(state)
    if cur != expected:
        raise IllegalAction(
            "WRONG_CAMPAIGN_STEP",
            f"Expected Campaign step {expected!r}; got {cur!r}.",
            citation="4.0",
        )


def _require_active_lord(state, side, lord_id: str | None) -> str:
    cur_lid = state.get("current_lord_id")
    if cur_lid is None:
        raise IllegalAction("NO_ACTIVE_LORD", "No Lord is currently activated.", "4.2")
    if lord_id and lord_id != cur_lid:
        raise IllegalAction(
            "WRONG_LORD",
            f"Active Lord is {cur_lid}; action targeted {lord_id!r}.",
            "4.2",
        )
    lord = state["lords"].get(cur_lid)
    if lord is None or lord["side"] != side:
        raise IllegalAction("WRONG_LORD_SIDE", f"Active lord {cur_lid!r} not on {side}.", "2.2.4")
    if state.get("actions_remaining", 0) is None or state.get("actions_remaining", 0) <= 0:
        raise IllegalAction("NO_ACTIONS_LEFT", "Active Lord has no actions remaining.", "4.2")
    return cur_lid


def _is_friendly_locale(state, locale: dict, side: str) -> bool:
    """A Locale is Friendly to `side` if the printed allegiance is `side`
    AND there are no enemy Allegiance markers, OR there are `side`
    Allegiance markers on top. Phase 3a's simplified check uses the
    printed allegiance plus any current allegiance markers.
    """
    enemy = "ghibelline" if side == "guelph" else "guelph"
    markers = locale.get("current_allegiance", []) or []
    enemy_markers = sum(1 for m in markers if m.get("side") == enemy)
    own_markers = sum(1 for m in markers if m.get("side") == side)
    if enemy_markers > 0 and own_markers == 0:
        return False
    if locale["allegiance"] == side:
        return True
    return own_markers > 0


def _is_friendly_stronghold(state, locale, side) -> bool:
    if locale["type"] == "outpost":
        return locale["allegiance"] == side
    if locale.get("ruins"):
        return False
    return _is_friendly_locale(state, locale, side)


def _maybe_end_card(payload: dict, state, side, citation: str) -> dict[str, Any]:
    """If actions_remaining <= 0 (or entire-card consumed), finish; else
    return the action result without ending the card."""
    if state.get("card_action_consumed_by_entire_card") or (state.get("actions_remaining") or 0) <= 0:
        return _finish_card_with(payload, state, side, reason="actions_exhausted", citation=citation)
    return {"state_changes": payload, "rule_citation": citation}


def _finish_card_with(payload: dict, state, side, reason: str, citation: str) -> dict[str, Any]:
    state["current_card"] = None
    state["current_lord_id"] = None
    state["actions_remaining"] = None
    state["card_action_consumed_by_entire_card"] = False
    fpd = _run_fpd(state)
    _flip_active_side(state)
    return {
        "state_changes": {**payload, "card_finished": True, "reason": reason, "fpd": fpd},
        "rule_citation": citation,
    }


def cd_PASS_CARD_ID():
    """Late-bound import so card_data is loaded after this module."""
    from . import card_data as cd
    return cd.PASS_CARD_ID


# =====================================================================
# Register Campaign handlers
# =====================================================================
_HANDLERS.update({
    "campaign_discard_capability":   _h_campaign_discard_capability,
    "campaign_discard_done":         _h_campaign_discard_done,
    "plan_add_card":                 _h_plan_add_card,
    "plan_done":                     _h_plan_done,
    "command_reveal":                _h_command_reveal,
    "cmd_tax":                       _h_cmd_tax,
    "cmd_forage":                    _h_cmd_forage,
    "cmd_ravage":                    _h_cmd_ravage,
    "cmd_supply":                    _h_cmd_supply,
    "cmd_sail":                      _h_cmd_sail,
    "cmd_pass":                      _h_cmd_pass,
    "cmd_end_card":                  _h_cmd_end_card,
})
