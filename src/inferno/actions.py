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
from . import revolt as _revolt
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
    # cmd_play_ambush is played by the ATTACKER during the defender's
    # Approach-response window, so exempt it from the active-player check
    # when the side matches the recorded approach attacker.
    ambush_exempt = (
        name == "cmd_play_ambush"
        and side == state["meta"].get("approach_attacker_side")
    )
    # Revolt/Exiles resolutions (1.4.2/1.4.4) are owned by the benefitting or
    # losing side, which may not be the active player; exempt them when a
    # matching pending decision exists.
    revolt_exempt = (
        name == "cmd_resolve_revolt"
        and any(b.get("decision", {}).get("side") == side
                for b in state.get("pending_revolts", []))
    ) or (
        name == "cmd_resolve_exiles"
        and any(e.get("side") == side for e in state.get("pending_exiles", []))
    )
    if side != current_side(state) and not (ambush_exempt or revolt_exempt):
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

    SMOKE-Inferno-025 (Tier-2 sweep): per 3.1.1, the AoW deck is
    re-shuffled at the start of each Levy from the discard pile,
    excluding Held Events and Capabilities currently in play. The
    Guelph deck went empty in Scenario F long runs prior to this fix.
    """
    _require_step(state, "3.1")
    # Phase v1.5 SMOKE-025: reshuffle AoW deck once per Levy (idempotent
    # within the Levy via aow_deck_reshuffled_this_levy flag).
    _maybe_reshuffle_aow_deck(state, side)
    # Exhaustion rule (scenario F special): roll at start of each Levy
    # from Turn 9 onward.
    _maybe_exhaustion_roll(state, rng)
    deck = state["decks"][side]["aow_deck"]
    if len(deck) < 2:
        raise IllegalAction("EMPTY_DECK", f"AoW deck for {side} has < 2 cards.", "3.1")

    # Deterministic "shuffle and draw" — use rng to choose 2 cards by index.
    drawn = []
    for _ in range(2):
        idx = rng.roll("aow_draw_index").value
        idx = (idx - 1) % len(deck)
        drawn.append(deck.pop(idx))

    is_first = is_first_levy(state)
    # SMOKE-Inferno-035: Scenario A 'Sudden Campaign' — first Levy AoW
    # is 1 Capability + 1 Event (rather than 2 of either).
    sudden_campaign = (state["meta"]["scenario"] == "A" and is_first)
    # SMOKE-Inferno-036: Scenario B 'Reprisal War' — first Levy, Ghib
    # pre-assigns S18, S19, S20 as Capabilities (then draws 2 more normally).
    if (state["meta"]["scenario"] == "B" and is_first
            and side == "ghibelline"
            and not state["meta"].get("reprisal_war_assigned")):
        deck_g = state["decks"]["ghibelline"]["aow_deck"]
        for forced_id in ("S18", "S19", "S20"):
            if forced_id in deck_g:
                deck_g.remove(forced_id)
                card = cd.AOW_CARDS_BY_ID[forced_id]
                state.setdefault("capabilities_in_play", []).append({
                    "id": forced_id, "name": card["capability_name"],
                    "side": "ghibelline", "scope": "side_wide",
                })
        state["meta"]["reprisal_war_assigned"] = True
    capabilities_in_play = state.setdefault("capabilities_in_play", [])
    held = state["decks"][side]["aow_held"]
    notes = []
    for i, cid in enumerate(drawn):
        card = cd.AOW_CARDS_BY_ID.get(cid)
        if not card:
            raise IllegalAction("UNKNOWN_CARD", f"Card {cid} not in card_data.", "3.1")
        # Sudden Campaign override: i=0 deploys as Capability; i=1 as Event.
        treat_as_capability = (
            is_first if not sudden_campaign else (i == 0)
        )
        if treat_as_capability:
            # 3.1.2: deploy as Capability. Default to side_wide scope.
            capabilities_in_play.append({
                "id": cid,
                "name": card["capability_name"],
                "side": side,
                "scope": "side_wide",
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
                # Immediate event: apply effect immediately (Phase 4 wiring).
                from . import card_effects as ce
                effect_result = ce.apply_event_effect(state, cid, side, {}, rng)
                state["decks"][side]["aow_discard"].append(cid)
                notes.append({
                    "card_id": cid, "name": card["event_name"], "kind": "immediate",
                    "effect": effect_result,
                })

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
        # SMOKE-Inferno-052: 3.2.2 requires a FRIENDLY Locale to pay with Loot
        # (was unchecked). Uses the canonical _is_friendly_locale predicate.
        if not _is_friendly_locale(state, loc, side):
            raise IllegalAction("LOOT_NOT_FRIENDLY",
                                f"Loot pay requires a Friendly Locale; {loc['name']} is not Friendly to {side}.",
                                "3.2.2")

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

    off_left_set = set(state["calendar"].get("off_left_service") or [])
    advanced_vs = state["meta"].get("advanced_vassal_service", False)
    vassal_disbands = []
    for lid, lord in state["lords"].items():
        if lord["side"] != side:
            continue
        if lord["status"] != "mustered":
            continue
        svc = lord.get("service_box")
        if svc is None:
            if lid in off_left_set:
                disbanded_beyond.append(lid)
                if lid in state["calendar"]["off_left_service"]:
                    state["calendar"]["off_left_service"].remove(lid)
            continue
        if svc < levy_box:
            disbanded_beyond.append(lid)
        elif svc == levy_box:
            disbanded_at.append(lid)
        # SMOKE-Inferno-034: Advanced Vassal Service — per-Vassal Disband.
        if advanced_vs:
            for v in lord.get("vassals", []):
                if v.get("turncoat"):
                    continue  # Turncoats immune (4.7.6 Tip)
                vsvc = v.get("service_box")
                if vsvc is not None and vsvc <= levy_box and v.get("on_mat"):
                    vassal_disbands.append((lid, v["name"]))

    revolt_rolls = []
    treachery_added = []
    for lid in disbanded_beyond:
        _disband_beyond_service_limit(state, lid)
        # 3.3.1 Revolt & Treachery (Comune Disband adds none)
        lord = state["lords"][lid]
        if lord.get("comune_of"):
            continue
        revolt_count = 3 if lord.get("podesta") else 1
        # 1.4.2 Revolt Table rolls: the disbanding side (`side`) lost the Lord;
        # `enemy_side` benefits and rolls. Decisions (if any) park as pending.
        trig = _revolt.trigger_revolts(state, losing_side=side, count=revolt_count,
                                       rng=rng, context=f"disband_{lid}")
        revolt_rolls.extend(trig["revolt_rolls"])
        # 1.4.3 Treachery cards (# = revolt_count); enemy's choice, auto-picked.
        for _ in range(revolt_count):
            t = _add_treachery_to_enemy(state, lid, enemy_side)
            if t:
                treachery_added.append({"card": t, "to_side": enemy_side, "for_disband_of": lid})

    for lid in disbanded_at:
        _disband_at_service_limit(state, lid, levy_box)
    # Vassal Disbands (advanced vassal service)
    for lid, vname in vassal_disbands:
        lord = state["lords"][lid]
        # Remove vassal from mat, return Forces to pool, mark not on_mat.
        for v in lord["vassals"]:
            if v["name"] == vname:
                for u, c in v.get("forces", {}).items():
                    lord["forces"][u] = max(0, lord["forces"].get(u, 0) - c)
                    if lord["forces"][u] == 0:
                        lord["forces"].pop(u, None)
                v["on_mat"] = False
                v["ready"] = False
                v["service_box"] = None
                break

    return {
        "state_changes": {
            "beyond_service_limit_removed": disbanded_beyond,
            "at_service_limit_disbanded": disbanded_at,
            "treachery_added": treachery_added,
            "vassal_disbands": vassal_disbands,
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


def _h_cmd_resolve_revolt(state, side, args, rng) -> dict[str, Any]:
    """Resolve the head pending Revolt decision (SUBMISSION / fallback) with a
    player-chosen target Locale, then continue draining the batch."""
    batches = state.get("pending_revolts", [])
    head = next((b for b in batches if b.get("decision")), None)
    if head is None:
        raise IllegalAction("NO_PENDING_REVOLT", "No revolt decision awaiting a choice.", "1.4.2")
    if head["decision"]["side"] != side:
        raise IllegalAction("WRONG_SIDE",
                            f"Revolt choice belongs to {head['decision']['side']}.", "1.4.2")
    choice = args.get("choice")
    gold, purple = head["rolls"][0]
    res = _revolt.resolve_revolt(state, head["losing_side"], gold, purple, choice=choice)
    if res["status"] == "illegal_choice":
        raise IllegalAction("ILLEGAL_REVOLT_CHOICE", res["reason"], "1.4.2")
    if res["status"] == "decision_required":
        # choice was None and still ambiguous
        raise IllegalAction("CHOICE_REQUIRED",
                            f"Revolt requires a choice among {res['decision']['candidates']}.", "1.4.2")
    head["rolls"].pop(0)
    head.pop("decision", None)
    if res.get("exiles_required"):
        state.setdefault("pending_exiles", []).append(res["exiles_required"])
    drained = _revolt.drain_revolts(state)
    return {"state_changes": {"resolved_revolt": res.get("switch") or res.get("status"),
                              **drained}, "rule_citation": "1.4.2"}


def _h_cmd_resolve_exiles(state, side, args, rng) -> dict[str, Any]:
    """Apply the head pending Exiles slides (1.4.4) chosen by the losing side."""
    pend = state.get("pending_exiles", [])
    head = next((e for e in pend if e["side"] == side), None)
    if head is None:
        raise IllegalAction("NO_PENDING_EXILES", f"No Exiles awaiting {side}.", "1.4.4")
    slides = args.get("slides", [])
    if len(slides) > head["count"]:
        raise IllegalAction("TOO_MANY_SLIDES",
                            f"Exiles allows at most {head['count']} slides.", "1.4.4")
    result = _revolt.apply_exiles(state, side, slides)
    pend.remove(head)
    return {"state_changes": {"exiles": result}, "rule_citation": "1.4.4"}


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


def _trigger_combat_removal_revolts(state, removed_lids, rng, context):
    """1.4.2 / 1.4.3 / 4.4.5: every Lord REMOVED BY COMBAT triggers Revolt-table
    rolls benefitting the enemy (once for a regular Lord, 3x for a Podesta) and
    adds that many Treachery cards to the enemy's Command deck. This is the same
    Revolt & Treachery trigger as a Disband Beyond Service (3.3.1) — defined once
    here and reused by Battle, Storm-Sack, and Sally removals so the three combat
    paths can never drift apart.

    SMOKE-Inferno-050: a Lord removed in Battle/Storm/Sally now rolls on the
    Revolt table (it previously did not — only Disband/Surrender/Sack/Languish
    were wired). Comune Lords add no Revolt/Treachery (3.3.1), matching Disband.
    """
    revolt_rolls = []
    treachery_added = []
    for lid in removed_lids:
        lord = state["lords"].get(lid)
        if not lord:
            continue
        if lord.get("comune_of"):
            continue  # Comune Lords add no Revolt/Treachery (3.3.1)
        losing_side = lord["side"]
        enemy_side = "ghibelline" if losing_side == "guelph" else "guelph"
        revolt_count = 3 if lord.get("podesta") else 1
        trig = _revolt.trigger_revolts(state, losing_side=losing_side,
                                       count=revolt_count, rng=rng,
                                       context=f"{context}_{lid}")
        revolt_rolls.extend(trig["revolt_rolls"])
        for _ in range(revolt_count):
            t = _add_treachery_to_enemy(state, lid, enemy_side)
            if t:
                treachery_added.append({"card": t, "to_side": enemy_side,
                                        "for_removal_of": lid})
    return {"combat_removal_revolts": revolt_rolls,
            "combat_removal_treachery": treachery_added}


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
    _consume_lordship(state, mlid)
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
        # SMOKE-Inferno-028: mark newly Mustered for 3.4.1 same-segment block.
        target_lord.setdefault("flags", {})["just_mustered_this_segment"] = True
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
    _consume_lordship(state, lid)
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
    _consume_lordship(state, lid)
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
    _consume_lordship(state, lid)
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
        # 4.2.4: revealing a Lower Lord's card = Pass (Lieutenant carries).
        if _is_lower_lord(state, lord_id):
            return _finish_card(state, side, reason="lower_lord_pass", citation="4.2.4")
        # Set up action budget = Command rating
        rating = lord.get("ratings", {}).get("C", 0)
        # Phase 6: Astrologers (F24/S24 Capability) — first Command card
        # this Campaign for this Lord: roll 1d6; on 1-2, +1 Command.
        astrologers_bonus = 0
        astrologers_roll = None
        from .battle import _lord_has_capability
        if (_lord_has_capability(state, lord_id, "Astrologers")
                and not lord.get("flags", {}).get("astrologers_rolled_this_campaign")):
            r = rng.roll(f"astrologers_{lord_id}")
            astrologers_roll = r.value
            if r.value <= 2:
                astrologers_bonus = 1
            lord.setdefault("flags", {})["astrologers_rolled_this_campaign"] = True
        # Phase 6: Via Francigena (F23 Capability) — Friendly Lord Seat -> Command +1.
        via_francigena_bonus = 0
        if _lord_has_capability(state, lord_id, "Via Francigena"):
            if lord.get("location") in lord.get("seats", []):
                # SMOKE-Inferno-052: F23 grants +1 Command only at a FRIENDLY Lord
                # Seat; use the canonical _is_friendly_locale predicate.
                loc = state["locales"].get(lord.get("location"), {})
                if loc and _is_friendly_locale(state, loc, side):
                    via_francigena_bonus = 1
        state["current_lord_id"] = lord_id
        state["actions_remaining"] = rating + astrologers_bonus + via_francigena_bonus
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
    +1 Coin (Podestà: +2). Uses the ENTIRE Command card.

    SMOKE-Inferno-029: S23 Taglia ('This Campaign no Guelph Tax') blocks
    Guelph Tax actions per the card text.
    """
    lid = _require_active_lord(state, side, args.get("lord_id"))
    lord = state["lords"][lid]
    # S23 Taglia This Campaign block
    if side == "guelph":
        # S23 Economic Sanctions Event: 'This Campaign, no Guelph Tax.'
        # The Event is what triggers the Tax block (the Capability 'Taglia' is
        # a separate effect — Ghibelline mercenary army).
        for e in (state.get("active_events", {}).get("this_campaign", []) or []):
            if e.get("id") == "S23":
                raise IllegalAction(
                    "TAX_BLOCKED_S23",
                    "S23 Economic Sanctions in play: no Guelph Tax this Campaign.",
                    "S23 / 4.7.4",
                )
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
    # 4.7.1: a Lord may NOT Forage while Besieged by Enemy Lords whose count is
    # EQUAL TO OR MORE THAN the Stronghold's Size (SMOKE-Inferno-051). Predicate
    # defined once in static_data.forage_besieged_block (shared with enumerator).
    if sd.forage_besieged_block(state, loc, side):
        raise IllegalAction(
            "BESIEGED",
            f"{lid} is Besieged by Enemy Lords >= Stronghold Size; Forage blocked.",
            "4.7.1")

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

    Phase v1.5 full implementation:
      - Source = Active Lord's OWN SEAT at unruined Stronghold/Outpost
        (or Pisa-with-Ships at a Port).
      - Route = unbroken chain of Locales/Ways from Lord to Source. May
        not include any Locale with Enemy Stronghold/Lord UNLESS that
        Stronghold/Lord is Besieged or Bypassed. Ruins/Ravaged do not block.
      - Transport = >=1 Cart per Provender per intervening Way. At own
        Seat or via Ships at Port: no Carts needed.
      - Max from each Stronghold Seat = Stronghold Size; Outpost = 1;
        Ship-Port = 1 per Ship (Pisa only, non-Winter).
      - Stores & Well Water (F1/S1) Capability: up to 4 Provender per
        Seat; allows Supply while Besieged at own Seat.

    args:
      lord_id:     Active Lord
      source:      Locale name for Source (default: Active Lord's Locale
                   if his own Seat, else first eligible)
      provender:   Amount to add (default: max allowed by Source + Transport)
    """
    lid = _require_active_lord(state, side, args.get("lord_id"))
    lord = state["lords"][lid]
    loc_name = lord.get("location")
    if not loc_name:
        raise IllegalAction("NO_LOCATION", f"{lid} has no map Locale.", "4.6")
    # Determine Source: first try args.source, else Lord's Locale if his Seat
    source = args.get("source") or loc_name
    if source not in lord.get("seats", []):
        # Maybe Pisa via Ships at Port
        is_pisa_via_ships = (
            lord["name"] == "Pisa Podestà"
            and state["locales"].get(source, {}).get("port")
            and lord["assets"].get("Ship", 0) > 0
        )
        if not is_pisa_via_ships:
            raise IllegalAction(
                "BAD_SOURCE",
                f"Source {source!r} must be Lord's Seat (or Pisa-with-Ships at a Port).",
                "4.6.1",
            )
    source_loc = state["locales"].get(source)
    if not source_loc:
        raise IllegalAction("UNKNOWN_SOURCE", f"Source {source} not found.", "4.6.1")
    if source_loc.get("ruins") and source_loc["type"] != "outpost":
        raise IllegalAction("SOURCE_RUINED", f"Ruined Stronghold Seat cannot be a Source.", "4.6.1")

    # Find the route from lord_loc to source (BFS), with route restrictions
    from .battle import _lord_has_capability
    enemy = "ghibelline" if side == "guelph" else "guelph"
    way_count = _find_supply_route_distance(state, loc_name, source, side)
    if way_count is None:
        raise IllegalAction(
            "NO_SUPPLY_ROUTE",
            f"No valid Supply Route from {loc_name} to {source}.",
            "4.6.1",
        )

    # SMOKE-Inferno-026: Stores & Well Water allows Supply while Besieged at own Seat.
    at_own_seat = (loc_name == source) and (source in lord.get("seats", []))
    cur_loc = state["locales"][loc_name]
    if cur_loc.get("siege") and not (
        at_own_seat and _lord_has_capability(state, lid, "Stores & Well Water")
    ):
        raise IllegalAction(
            "SUPPLIER_BESIEGED",
            f"{lid} Besieged at {loc_name}; cannot Supply (unless Stores & Well Water at own Seat).",
            "4.6",
        )

    # Max Provender from this Source:
    #   Stores & Well Water: 4 per Seat
    #   Else: Castle=1, Town=2, City=3, Outpost=1
    size_map = {"castle": 1, "town": 2, "city": 3, "outpost": 1}
    if _lord_has_capability(state, lid, "Stores & Well Water"):
        max_from_source = 4
    else:
        max_from_source = size_map.get(source_loc["type"], 1)

    # Transport requirement: 1 Cart per Provender per Way (no Carts at own Seat or Pisa-Ships-Port)
    carts_avail = lord["assets"].get("Cart", 0)
    requested = int(args.get("provender", max_from_source))
    requested = max(1, min(requested, max_from_source))
    if way_count == 0:
        carts_needed = 0
    elif (lord["name"] == "Pisa Podestà"
          and source_loc.get("port")
          and lord["assets"].get("Ship", 0) > 0):
        # Pisa Sail-Supply via Ship-Port: no Carts but limited by Ships
        max_ship_supply = lord["assets"]["Ship"]
        requested = min(requested, max_ship_supply)
        carts_needed = 0
    else:
        carts_needed = way_count * requested
        if carts_avail < carts_needed:
            # Try shrinking requested
            requested = max(0, carts_avail // way_count) if way_count > 0 else 0
            carts_needed = way_count * requested
        if requested == 0:
            raise IllegalAction(
                "INSUFFICIENT_CARTS",
                f"Need {way_count} Carts per Provender; {lid} has {carts_avail}.",
                "4.6.1",
            )
    lord["assets"]["Provender"] = min(lord["assets"].get("Provender", 0) + requested, 16)
    state["actions_remaining"] -= 1
    return _maybe_end_card({
        "supply_added": requested, "from": source,
        "way_count": way_count, "carts_required": carts_needed,
    }, state, side, citation="4.6.2")


def _find_supply_route_distance(state, src: str, target: str, side: str) -> int | None:
    """BFS shortest path from src to target avoiding Locales with un-Besieged/
    un-Bypassed enemy Strongholds or enemy Lords. Returns # of Ways
    crossed (= len(path) - 1), or None if unreachable.
    """
    if src == target:
        return 0
    from collections import deque
    enemy = "ghibelline" if side == "guelph" else "guelph"

    def passable(loc_name: str) -> bool:
        loc = state["locales"].get(loc_name, {})
        # Enemy Lord present (un-Besieged)?
        for oid in loc.get("lords_present", []):
            olord = state["lords"].get(oid, {})
            if olord.get("side") == enemy and olord.get("status") == "mustered":
                # Allowed if Besieged or Bypassed
                if olord.get("flags", {}).get("in_stronghold"):
                    continue
                if loc.get("bypass"):
                    continue
                return False
        # Enemy Stronghold present? un-Ruined enemy stronghold blocks UNLESS Besieged/Bypassed.
        if (loc.get("type") != "outpost"
                and not loc.get("ruins")
                and not _is_friendly_locale(state, loc, side)):
            if not loc.get("siege") and not loc.get("bypass"):
                return False
        return True

    queue = deque([(src, 0)])
    seen = {src}
    while queue:
        cur, d = queue.popleft()
        for nbr, _w in sd.adjacent_to(cur):
            if nbr in seen:
                continue
            if nbr == target:
                # Target itself doesn't need passable (it's the Source).
                return d + 1
            if not passable(nbr):
                continue
            seen.add(nbr)
            queue.append((nbr, d + 1))
    return None


def _h_cmd_sail(state, side, args, rng) -> dict[str, Any]:
    """4.7.3 SAIL — Pisa Podestà only, entire-card, non-Winter, Port-to-Port.

    v1.6 full implementation:
      - Validates Ship transport: 1 Ship per Horse unit moving, 1 per
        Provender, 2 per Loot. May NOT Approach Enemy Lord (cannot
        start Battle by Sail). To Sail to an Unbesieged Enemy Stronghold,
        places a Siege marker (Besiege).
      - May NOT Sail to a Port with an Unbesieged Enemy Lord.
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
    # Cannot Sail to Approach Enemy Lord (no Battle via Sail).
    enemy = "ghibelline" if side == "guelph" else "guelph"
    for oid in dest.get("lords_present", []):
        olord = state["lords"][oid]
        if (olord["side"] == enemy and olord["status"] == "mustered"
                and not olord.get("flags", {}).get("in_stronghold")):
            raise IllegalAction(
                "SAIL_INTO_ENEMY_LORD",
                f"May NOT Sail into Locale with Unbesieged Enemy Lord {oid}.",
                "4.7.3",
            )
    # Ship transport validation per 4.7.3.
    ships = lord["assets"].get("Ship", 0)
    horse_units = sum(c for u, c in lord.get("forces", {}).items()
                      if sd.UNITS.get(u, {}).get("cat") == "horse")
    prov = lord["assets"].get("Provender", 0)
    loot = lord["assets"].get("Loot", 0)
    ships_needed = horse_units + prov + 2 * loot
    if ships_needed > ships:
        raise IllegalAction(
            "INSUFFICIENT_SHIPS",
            f"Sail needs {horse_units} (Horse) + {prov} (Provender) + 2x{loot} (Loot) = "
            f"{ships_needed} Ships; {lid} has {ships}. Per 1.7.2 Greed, must discard "
            f"excess before Sailing.",
            "4.7.3",
        )
    # Move
    if src_name and lid in src.get("lords_present", []):
        src["lords_present"].remove(lid)
    lord["location"] = dest_name
    dest.setdefault("lords_present", []).append(lid)
    lord["flags"]["moved_fought"] = True
    # SMOKE-Inferno-027: If destination is an unbesieged enemy Stronghold,
    # place a Siege marker (Besiege) per 4.7.3.
    besieged_via_sail = False
    if (not _is_friendly_locale(state, dest, side)
            and dest["type"] != "outpost"
            and not dest.get("ruins")
            and not dest.get("siege")):
        dest.setdefault("siege", []).append({
            "side": side, "color": "gold" if side == "guelph" else "purple", "count": 1,
        })
        besieged_via_sail = True
    state["actions_remaining"] = 0
    state["card_action_consumed_by_entire_card"] = True
    return _finish_card_with({
        "sailed_from": src_name, "to": dest_name,
        "ships_used": ships_needed, "besieged_via_sail": besieged_via_sail,
    }, state, side, reason="sail_entire_card", citation="4.7.3")


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
    """Canonical "Friendly Locale" predicate (SMOKE-Inferno-052), defined once
    and reused wherever a rule says "Friendly Locale". Current Allegiance
    markers override the printed Allegiance (1.3): a Locale is Friendly to
    `side` when it has `side` Allegiance markers, OR its printed Allegiance is
    `side` and it carries no Enemy markers. Enemy markers with no own markers
    make it Enemy regardless of the printed Allegiance.
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


# =====================================================================
# CAMPAIGN — March (4.3) and Approach decisions (4.3.4)
# =====================================================================
def _h_cmd_march(state, side, args, rng) -> dict[str, Any]:
    """4.3 March: move one or a group of Lords across one Way.

    Phase v1.5 supports Group March (4.3.1):
      - args.with_lords (optional): additional Lord IDs to move with the
        active Lord. All must be at the same starting Locale.
      - Lieutenant + Lower Lord MUST move together (4.1.3): if active or
        with_lords includes a Lieutenant, the Lower Lord auto-joins; if
        it includes a Lower Lord, the Lieutenant auto-joins.
      - Laden status computed across the group (shared Carts per 4.3.2).
      - Cost: max of per-Lord costs (typically 1; the group is bottlenecked
        by the slowest Lord's Laden/Speed status).

    Approach (4.3.4) detection considers the entire group.

    args:
      lord_id:      Active Marching Lord
      destination:  target Locale name
      way_type:     'road' or 'track'
      with_lords:   optional list of additional Lord IDs marching together
    """
    lid = _require_active_lord(state, side, args.get("lord_id"))
    lord = state["lords"][lid]
    dest_name = args.get("destination")
    if not dest_name:
        raise IllegalAction("MISSING_DEST", "March requires destination Locale.", "4.3")
    if dest_name not in state["locales"]:
        raise IllegalAction("UNKNOWN_LOCALE", f"Locale {dest_name!r} not found.", "4.3")
    cur_loc_name = lord.get("location")
    if cur_loc_name is None:
        raise IllegalAction("NO_LOCATION", f"{lid} has no map Locale.", "4.3")

    # SMOKE-Inferno-039: Scenario C 'Maremma War' — Ghibelline Lords
    # may not cross the dashed line until Guelphs place a Siege or Ravage marker.
    if (state["meta"]["scenario"] == "C" and side == "ghibelline"
            and not state["meta"].get("guelph_aggression_seen")):
        src_region = sd.LOCALES.get(cur_loc_name, {}).get("region")
        dest_region = sd.LOCALES.get(dest_name, {}).get("region")
        if src_region and dest_region and src_region != dest_region:
            # Crossing the dashed line. Check if Guelphs have placed any
            # Siege or Ravage marker.
            any_guelph_aggression = any(
                any(s.get("side") == "guelph" for s in (loc.get("siege") or []))
                or loc.get("ravaged") == "gold"
                for loc in state["locales"].values()
            )
            if any_guelph_aggression:
                state["meta"]["guelph_aggression_seen"] = True
            else:
                raise IllegalAction(
                    "MAREMMA_LINE_CROSS",
                    "Scenario C: Ghibelline Lords may not cross the dashed "
                    "line until Guelphs place a Siege or Ravage marker.",
                    "Scenario C / 1.3.1",
                )
    # Phase v1.5: resolve Group March participants (4.3.1) — include
    # explicit with_lords + auto-pair Lieutenant/Lower Lord.
    group = [lid]
    requested = list(args.get("with_lords", []) or [])
    for olid in requested:
        if olid != lid and olid in state["lords"]:
            ol = state["lords"][olid]
            if (ol["side"] == side
                    and ol["status"] == "mustered"
                    and ol.get("location") == cur_loc_name):
                if olid not in group:
                    group.append(olid)
            else:
                raise IllegalAction(
                    "GROUP_INVALID",
                    f"{olid} not eligible for Group March (not same Locale or not Mustered).",
                    "4.3.1",
                )
    # Auto-pair Lieutenant + Lower Lord (4.1.3)
    for member_id in list(group):
        m = state["lords"][member_id]
        lower = m.get("flags", {}).get("has_lower_lord")
        upper = m.get("flags", {}).get("lower_lord_of")
        if lower and lower not in group:
            ll = state["lords"].get(lower)
            if ll and ll.get("location") == cur_loc_name:
                group.append(lower)
        if upper and upper not in group:
            ul = state["lords"].get(upper)
            if ul and ul.get("location") == cur_loc_name:
                group.append(upper)
    # SMOKE-Inferno-008: validate way_type matches Lord's actual adjacency.
    adjacencies = sd.adjacent_to(cur_loc_name)
    way_type = args.get("way_type")
    if way_type:
        if (dest_name, way_type) not in adjacencies:
            raise IllegalAction(
                "BAD_WAY",
                f"No {way_type} from {cur_loc_name} to {dest_name}. "
                f"Adjacencies: {[a for a in adjacencies if a[0] == dest_name]}.",
                "4.3",
            )
    else:
        # Pick first matching adjacency (Phase 3b convenience for unambiguous cases)
        ways_to_dest = [w for n, w in adjacencies if n == dest_name]
        if not ways_to_dest:
            raise IllegalAction(
                "NOT_ADJACENT",
                f"{cur_loc_name} is not adjacent to {dest_name}.",
                "4.3",
            )
        way_type = ways_to_dest[0]

    # SMOKE-Inferno-030: F5/S5 Road Works This Campaign — treat Track as
    # Road AND move Laden as Unladen for the Lord's side.
    road_works_active = any(
        e.get("id") in ("F5", "S5") and e.get("side") == side
        for e in (state.get("active_events", {}).get("this_campaign", []) or [])
    )
    # 4.3.2 Laden status (Group March: sum across the group, per
    # 'SHARING: Lords moving as a group share Carts').
    carts = sum(state["lords"][m]["assets"].get("Cart", 0) for m in group)
    prov  = sum(state["lords"][m]["assets"].get("Provender", 0) for m in group)
    loot  = sum(state["lords"][m]["assets"].get("Loot", 0) for m in group)
    laden = False
    if road_works_active:
        laden = False  # Road Works: Laden treated as Unladen
    elif loot > 0:
        laden = True
    elif way_type == "track":
        laden = prov > carts
    else:  # road
        laden = (prov > carts) and (loot > 0)
    if prov > 2 * carts:
        raise IllegalAction(
            "EXCESS_PROVENDER",
            f"{lid} has Provender={prov} > 2*Carts={2*carts}; discard or stay (4.3.2 / 1.7.2).",
            "4.3.2",
        )

    # 4.3.3 Speed: standard 1 action; Unladen first-March-of-card on Road = 0;
    # Laden = 2 actions.
    flags = lord.setdefault("flags", {})
    first_march = not flags.get("first_march_used_this_card", False)
    effective_way = "road" if (road_works_active and way_type == "track") else way_type
    if laden:
        cost = 2
    elif first_march and effective_way == "road":
        cost = 0
    else:
        cost = 1
    if (state.get("actions_remaining") or 0) < cost:
        raise IllegalAction(
            "INSUFFICIENT_ACTIONS",
            f"March needs {cost} actions; {state.get('actions_remaining')} remaining.",
            "4.3.3",
        )
    # Mark first-March-used-this-card
    flags["first_march_used_this_card"] = True

    # Move all group members
    src = state["locales"][cur_loc_name]
    dest = state["locales"][dest_name]
    for member_id in group:
        ml = state["lords"][member_id]
        if member_id in src.get("lords_present", []):
            src["lords_present"].remove(member_id)
        dest.setdefault("lords_present", []).append(member_id)
        ml["location"] = dest_name
        ml.setdefault("flags", {})["moved_fought"] = True
    state["actions_remaining"] -= cost

    # 4.3.4 Approach? Inactive Lords on the other side at this Locale.
    enemy_side = "ghibelline" if side == "guelph" else "guelph"
    enemy_lords_here = [
        eid for eid in dest.get("lords_present", [])
        if state["lords"][eid]["side"] == enemy_side
        and state["lords"][eid]["status"] == "mustered"
    ]
    if enemy_lords_here:
        # Generate pending decisions for each Inactive Enemy Lord.
        pendings = []
        for eid in enemy_lords_here:
            pendings.append({
                "type": "approach_response",
                "side": enemy_side,
                "options": ["avoid", "withdraw", "stand"],
                "info": {
                    "lord_id": eid,
                    "approaching_lord": lid,
                    "locale": dest_name,
                    "approached_via": way_type,
                    # SMOKE-Inferno-055: the Locale the Active Lord approached
                    # FROM, so Avoid can forbid retreating back along that Way.
                    "approached_from": cur_loc_name,
                },
            })
        state.setdefault("pending", []).extend(pendings)
        # Active player swaps to enemy_side for response (per 4.3.4 / 2.2.4).
        # Restored to the original attacker side in _finalize_approach.
        state["meta"]["approach_attacker_side"] = side
        state["meta"]["active_player"] = enemy_side
        return {
            "state_changes": {
                "marched_from": cur_loc_name, "to": dest_name, "way_type": way_type,
                "cost": cost, "laden": laden, "approach_triggered": True,
                "pending_responses": [p["info"]["lord_id"] for p in pendings],
            },
            "rule_citation": "4.3 / 4.3.4",
        }

    # No approach — return action result and continue card.
    return _maybe_end_card({
        "marched_from": cur_loc_name, "to": dest_name, "way_type": way_type,
        "cost": cost, "laden": laden, "approach_triggered": False,
        "group": group,
    }, state, side, citation="4.3")


def _h_approach_response(state, side, args, rng) -> dict[str, Any]:
    """4.3.4: Inactive Lord chooses Avoid / Withdraw / Stand.

    args:
      lord_id:     responding Lord (must match a pending entry's info.lord_id)
      choice:      'avoid' | 'withdraw' | 'stand'
      destination: required if choice='avoid' (adjacent Locale)
    """
    lid = args.get("lord_id")
    choice = args.get("choice")
    if choice not in ("avoid", "withdraw", "stand"):
        raise IllegalAction("BAD_CHOICE", f"choice must be avoid/withdraw/stand; got {choice!r}.", "4.3.4")
    # SMOKE-Inferno-042: F1/S1 Ambush — a Lord the attacker forced via
    # Ambush may not Avoid; must Stand or Withdraw.
    if choice == "avoid" and state["lords"].get(lid, {}).get("flags", {}).get("ambush_forced"):
        raise IllegalAction(
            "AMBUSH_FORCED",
            f"{lid} was targeted by Ambush (F1/S1) and may not Avoid; must Stand or Withdraw.",
            "F1/S1 / 4.3.4",
        )

    # Find matching pending
    pending = state.get("pending", [])
    idx = None
    for i, p in enumerate(pending):
        if p.get("type") == "approach_response" and p["info"].get("lord_id") == lid and p.get("side") == side:
            idx = i
            break
    if idx is None:
        raise IllegalAction("NO_PENDING", f"No pending approach_response for {lid}.", "4.3.4")
    entry = pending.pop(idx)
    info = entry["info"]
    locale_name = info["locale"]
    approached_via = info["approached_via"]
    lord = state["lords"][lid]

    if choice == "avoid":
        # 4.3.4 AVOID BATTLE restrictions:
        #   - May NOT use the Way the Active Lord just used.
        #   - May NOT enter a Locale with another Unbesieged Enemy Lord.
        #   - Only UNLADEN Lords may Avoid.
        dest_name = args.get("destination")
        if not dest_name:
            raise IllegalAction("MISSING_DEST", "Avoid requires destination.", "4.3.4")
        # Unladen check
        loot = lord["assets"].get("Loot", 0)
        if loot > 0:
            raise IllegalAction("LADEN_CANNOT_AVOID", f"{lid} has Loot={loot}; only Unladen may Avoid.", "4.3.4")
        # Adjacency
        adj = sd.adjacent_to(locale_name)
        ways_to = [(n, w) for n, w in adj if n == dest_name]
        if not ways_to:
            raise IllegalAction("NOT_ADJACENT", f"{dest_name} not adjacent to {locale_name}.", "4.3.4")
        # SMOKE-Inferno-009 / SMOKE-Inferno-055: Avoid-Battle may NOT retreat back
        # along the Way the Active Lord just used to approach. Now enforced via
        # the recorded approached_from + the shared predicate (was a no-op).
        if sd.avoid_along_approach_way(dest_name, info.get("approached_from"),
                                       [w for _, w in ways_to], approached_via):
            raise IllegalAction(
                "AVOID_ALONG_APPROACH_WAY",
                f"{lid} may not Avoid back along the Way the Active Lord approached "
                f"({approached_via}) to {dest_name}.",
                "4.3.4")
        # Other enemy Lord at destination?
        target_loc = state["locales"][dest_name]
        for other_id in target_loc.get("lords_present", []):
            if state["lords"][other_id]["side"] != side:
                # Phase 3b: reject avoid into enemy-occupied
                raise IllegalAction(
                    "AVOID_INTO_ENEMY_LOCALE",
                    f"Cannot Avoid into {dest_name}; Enemy Lord {other_id} present.",
                    "4.3.4",
                )
        # Move the Lord
        src = state["locales"][locale_name]
        if lid in src.get("lords_present", []):
            src["lords_present"].remove(lid)
        target_loc.setdefault("lords_present", []).append(lid)
        lord["location"] = dest_name
        lord.setdefault("flags", {})["moved_fought"] = True

    elif choice == "withdraw":
        # 4.3.4 WITHDRAW: into a Friendly Stronghold at this Locale.
        loc = state["locales"][locale_name]
        if loc.get("ruins"):
            raise IllegalAction("WITHDRAW_INTO_RUINS", "Cannot withdraw into Ruins.", "4.3.4")
        if not _is_friendly_locale(state, loc, side):
            raise IllegalAction("WITHDRAW_NOT_FRIENDLY", f"{locale_name} not Friendly to {side}.", "4.3.4")
        # Stronghold Size limit (1/2/3)
        size_map = {"castle": 1, "town": 2, "city": 3, "outpost": 0}
        max_in = size_map.get(loc["type"], 0)
        if max_in == 0:
            raise IllegalAction("NO_WITHDRAW_HERE", f"{loc['type']} has no Stronghold for Withdraw.", "4.3.4")
        # Count already-withdrawn Lords (Phase 3b uses a flag)
        already_in = sum(
            1 for other_id in loc.get("lords_present", [])
            if state["lords"][other_id].get("flags", {}).get("in_stronghold")
            and state["lords"][other_id]["side"] == side
        )
        if already_in >= max_in:
            raise IllegalAction(
                "STRONGHOLD_FULL",
                f"{loc['type']} {locale_name} has {already_in} withdrawn; max {max_in}.",
                "4.3.4",
            )
        lord.setdefault("flags", {})["in_stronghold"] = True
        # Withdrawal does NOT mark Moved/Fought (per 4.3.4).

    else:  # stand
        # Stand for Battle — handled when all pending approach_responses resolved.
        pass

    # If any remaining approach_response pendings, return — we still wait.
    remaining = [p for p in state.get("pending", [])
                 if p.get("type") == "approach_response"
                 and p["info"]["locale"] == locale_name]
    if remaining:
        return {
            "state_changes": {"lord_id": lid, "choice": choice, "remaining_responses": len(remaining)},
            "rule_citation": "4.3.4",
        }

    # All responses gathered. Determine whether Battle resolves.
    return _finalize_approach(state, locale_name, info["approaching_lord"], side)


def _finalize_approach(state, locale_name, approaching_lord, defender_side) -> dict[str, Any]:
    """All Inactive Lords have responded. If any Stood, run Battle."""
    loc = state["locales"][locale_name]
    # Clear any ambush_forced flags now that responses are gathered.
    for _lid, _l in state["lords"].items():
        _l.get("flags", {}).pop("ambush_forced", None)
    attacker_side = "ghibelline" if defender_side == "guelph" else "guelph"
    # Standers: any Inactive Lord at this Locale not in_stronghold and not moved away
    standers = [lid for lid in loc.get("lords_present", [])
                if state["lords"][lid]["side"] == defender_side
                and not state["lords"][lid].get("flags", {}).get("in_stronghold")
                and state["lords"][lid]["status"] == "mustered"]
    if not standers:
        # No battle; restore active player to the marching side.
        atk_side = state["meta"].pop("approach_attacker_side", attacker_side)
        state["meta"]["active_player"] = atk_side
        return {
            "state_changes": {"approach_resolved": "no_battle", "locale": locale_name},
            "rule_citation": "4.3.4",
        }

    # SMOKE-Inferno-033: Relief Sally per 4.4.1 — if attacking side has
    # Lord(s) Besieged inside at this Locale, those Besieged Lords join
    # the attack for NO added Command actions.
    relief_sallying = [
        oid for oid in loc.get("lords_present", [])
        if state["lords"][oid]["side"] == attacker_side
        and state["lords"][oid].get("flags", {}).get("in_stronghold")
        and state["lords"][oid]["status"] == "mustered"
    ]
    # Run Battle
    from .battle import resolve_battle
    # Group March may have brought multiple Attackers; include them all.
    attackers = []
    approaching_lord_obj = state["lords"][approaching_lord]
    approaching_loc = approaching_lord_obj["location"]
    for oid in loc.get("lords_present", []):
        olord = state["lords"][oid]
        if (olord["side"] == attacker_side
                and olord["status"] == "mustered"
                and not olord.get("flags", {}).get("in_stronghold")
                and olord["location"] == locale_name):
            # Was the Lord part of the marching group? Phase v1.5 puts the
            # whole group at locale_name on march completion, so they all
            # count as attackers here.
            attackers.append(oid)
    if approaching_lord not in attackers:
        attackers.insert(0, approaching_lord)
    # Add Relief-Sallying Lords (mark them so Battle can apply Sally semantics).
    for rs in relief_sallying:
        if rs not in attackers:
            attackers.append(rs)
            state["lords"][rs].setdefault("flags", {})["relief_sallying"] = True
    defenders = standers
    result = resolve_battle(
        state, attackers, defenders, active_id=approaching_lord,
        locale_name=locale_name,
    )
    # Process post-Battle outcomes per 4.4.3 - 4.4.5.
    _apply_post_battle(state, result, attackers, defenders)
    atk_side = state["meta"].pop("approach_attacker_side", attacker_side)
    state["meta"]["active_player"] = atk_side
    state["current_card"] = None
    state["current_lord_id"] = None
    state["actions_remaining"] = None
    return {
        "state_changes": {
            "approach_resolved": "battle",
            "battle_result": result,
        },
        "rolls": result.get("rolls", []),
        "rule_citation": "4.4",
    }


def _apply_post_battle(state, result, attackers: list[str], defenders: list[str]) -> None:
    """4.4.3 - 4.4.5 post-Battle bookkeeping: Spoils + Service shifts +
    Loss rolls (with Knights' Quarter) + Lord removal.

    Conceded side gets the favourable Spoils + Service treatment.
    """
    from .battle import (
        loss_roll_for_routed,
        service_shift_for_retreated,
        transfer_spoils,
    )
    from .rng import HarnessRNG
    rng = HarnessRNG(state["meta"]["rng_seed"],
                     advance=state["meta"].get("rng_advance", 0))
    rolls_before = rng.advance_count

    winner = result["winner"]   # 'attacker' / 'defender'
    loser = result["loser"]
    conceded = result.get("conceded") == loser
    losers_ids = attackers if loser == "attacker" else defenders
    winners_ids = defenders if loser == "attacker" else attackers
    # Filter winners to surviving Mustered Lords
    winners_alive = [w for w in winners_ids
                     if w in state["lords"] and state["lords"][w]["status"] == "mustered"]

    combat_removed: list[str] = []
    for lid in losers_ids:
        if lid not in state["lords"]:
            continue
        # Determine fate: removed (zero forces) / retreated / withdrew
        lord = state["lords"][lid]
        if sum(lord.get("forces", {}).values()) == 0 or lid in result.get("removed_lords", []):
            # Removed per 4.4.5
            transfer_spoils(state, lid, winners_alive,
                            retreated=False, conceded=conceded, withdrew=False)
            _disband_beyond_service_limit(state, lid)
            combat_removed.append(lid)
        elif lord.get("flags", {}).get("in_stronghold"):
            # Withdrew into Stronghold: keep Assets, no Service shift.
            transfer_spoils(state, lid, winners_alive,
                            retreated=False, conceded=False, withdrew=True)
        else:
            # Retreated.
            transfer_spoils(state, lid, winners_alive,
                            retreated=True, conceded=conceded, withdrew=False)
            # Service shift
            has_carroccio = any(v.get("name") == "Carroccio" and v.get("on_mat")
                                for v in lord.get("vassals", []))
            service_shift_for_retreated(
                state, lid,
                conceded_with_carroccio=(conceded and has_carroccio),
                rng_caller=rng.roll,
            )
    # Loss rolls for ALL participants (winners + losers) with their Routed piles
    for lid in attackers + defenders:
        if lid not in state["lords"]:
            continue
        if not state["lords"][lid].get("routed_units"):
            continue
        # Harsh Recovery: side that Retreated without Conceding.
        retreated_no_concede = (
            lid in losers_ids
            and not state["lords"][lid].get("flags", {}).get("in_stronghold")
            and not conceded
        )
        loss_roll_for_routed(state, lid,
                             harsh_recovery=retreated_no_concede,
                             rng_caller=rng.roll)
    # 4.4.5 Revolt & Treachery for Lords removed in this Battle.
    _trigger_combat_removal_revolts(state, combat_removed, rng, context="battle")
    state["meta"]["rng_advance"] = state["meta"].get("rng_advance", 0) + (rng.advance_count - rolls_before)


# Register new handlers
_HANDLERS.update({
    "cmd_march":          _h_cmd_march,
    "approach_response":  _h_approach_response,
})


# =====================================================================
# CAMPAIGN — Besiege/Bypass, Siege, Storm, Sally, Treachery (Phase 3c)
# =====================================================================
def _h_besiege_or_bypass(state, side, args, rng) -> dict[str, Any]:
    """4.3.5: when active side has Lord(s) at an Enemy Stronghold (not
    Ruins) and no Enemy outside, choose Besiege or Bypass.

    args:
      lord_id:  the Lord at the Locale outside the Stronghold
      choice:   'besiege' or 'bypass'
    """
    lid = _require_active_lord(state, side, args.get("lord_id"))
    lord = state["lords"][lid]
    locale_name = lord.get("location")
    loc = state["locales"].get(locale_name)
    if not loc:
        raise IllegalAction("NO_LOCATION", f"{lid} has no Locale.", "4.3.5")
    if loc["allegiance"] == side and not loc.get("current_allegiance"):
        raise IllegalAction("FRIENDLY_LOCALE", f"{locale_name} is Friendly; no Besiege/Bypass.", "4.3.5")
    if loc.get("ruins"):
        raise IllegalAction("RUINS_NO_STRONGHOLD", f"{locale_name} is Ruins; no Stronghold to Besiege.", "4.3.5")
    if loc["type"] == "outpost":
        raise IllegalAction("OUTPOST", f"Outposts never Besieged.", "4.3.5")
    choice = args.get("choice")
    if choice not in ("besiege", "bypass"):
        raise IllegalAction("BAD_CHOICE", f"choice must be besiege/bypass; got {choice!r}.", "4.3.5")

    if choice == "besiege":
        # SMOKE-Inferno-041: F3/S3 Surprise — Besieging with no other Lord
        # consumes a pending surprise modifier: 2 Siege markers + mandatory
        # auto-Storm up to 3 Rounds at Walls -2.
        other_lords_here = [
            oid for oid in loc.get("lords_present", [])
            if oid != lid and not state["lords"][oid].get("flags", {}).get("in_stronghold")
        ]
        surprise = None
        if not other_lords_here:
            for i, m in enumerate(state.get("besiege_modifiers_pending", []) or []):
                if m.get("effect") == "surprise_besiege_alone" and m.get("side") == side:
                    surprise = state["besiege_modifiers_pending"].pop(i)
                    break
        if surprise:
            loc.setdefault("siege", []).append({
                "side": side, "color": "gold" if side == "guelph" else "purple", "count": 2,
            })
            state.setdefault("battle_modifiers_pending", []).append({
                "id": "F3/S3", "side": side, "effect": "storm_walls_minus", "value": 2,
            })
            enemy_side = "ghibelline" if side == "guelph" else "guelph"
            defenders = [oid for oid in loc.get("lords_present", [])
                         if state["lords"][oid].get("flags", {}).get("in_stronghold")
                         and state["lords"][oid]["side"] == enemy_side]
            from .battle import resolve_storm
            result = resolve_storm(state, attackers=[lid], defenders=defenders,
                                    active_id=lid, locale_name=locale_name)
            if result["outcome"] == "sack":
                _apply_sack(state, locale_name, side, result, rng)
            return _finish_card_with({
                "surprise_besiege": locale_name, "auto_storm": result,
            }, state, side, reason="surprise_besiege_storm", citation="F3/S3 / 4.3.5")
        loc.setdefault("siege", []).append({"side": side, "color": "gold" if side == "guelph" else "purple", "count": 1})
        return _finish_card_with({"besieged": locale_name}, state, side,
                                  reason="besiege_ends_card", citation="4.3.5")
    else:  # bypass
        loc.setdefault("bypass", []).append({"side": side, "lord_id": lid})
        lord.setdefault("flags", {})["bypassing"] = locale_name
        return _maybe_end_card({"bypassed": locale_name}, state, side, citation="4.3.5")


def _h_cmd_siege(state, side, args, rng) -> dict[str, Any]:
    """4.5.1 SIEGE (entire card). Roll Surrender (if no Besieged Lord
    inside), else add Siegeworks (1 Siege marker if side has Lords ≥
    Stronghold Size; max 4).

    SMOKE-Inferno-040: Scenario C 'Maremma War' — Grosseto with 2 Siege
    markers and no Besieged Lord inside Surrenders AT ONCE (no roll).
    """
    lid = _require_active_lord(state, side, args.get("lord_id"))
    lord = state["lords"][lid]
    locale_name = lord.get("location")
    loc = state["locales"][locale_name]
    if not loc.get("siege"):
        raise IllegalAction("NO_SIEGE_HERE", f"No Siege at {locale_name}.", "4.5.1")
    # Only the Besieging side may take Siege action.
    enemy_side = "ghibelline" if side == "guelph" else "guelph"
    # Besieged Lords inside (in_stronghold flag, same Locale)?
    inside = [oid for oid in loc.get("lords_present", [])
              if state["lords"][oid].get("flags", {}).get("in_stronghold")
              and state["lords"][oid]["side"] == enemy_side]
    siege_count = sum(s.get("count", 1) for s in loc["siege"])
    ravage_bonus = 1 if loc.get("ravaged") else 0
    # SMOKE-Inferno-040: Scenario C Grosseto auto-Surrender at 2+ markers.
    auto_surrender = (
        state["meta"]["scenario"] == "C"
        and locale_name == "Grosseto"
        and siege_count >= 2
        and not inside
    )
    surrender = None
    rolls = []
    if auto_surrender:
        surrender = True
        _apply_surrender(state, locale_name, side, rng, rolls)
    if not inside and not auto_surrender:
        # Roll Surrender dice
        size = sd.STRONGHOLDS[loc["type"]]["size"]
        threshold = siege_count + ravage_bonus
        dice = []
        for i in range(size):
            r = rng.roll(f"surrender_{locale_name}_{i}")
            dice.append(r.value)
            rolls.append({"context": r.context, "value": r.value})
        if all(d <= threshold for d in dice):
            surrender = True
            # Apply Surrender outcome
            _apply_surrender(state, locale_name, side, rng, rolls)
        else:
            surrender = False
    # Step 2 Siegeworks if no Surrender
    if surrender is not True:
        own_lords_here = [oid for oid in loc.get("lords_present", [])
                          if state["lords"][oid]["side"] == side
                          and not state["lords"][oid].get("flags", {}).get("in_stronghold")]
        if len(own_lords_here) >= sd.STRONGHOLDS[loc["type"]]["size"]:
            new_count = min(siege_count + 1, 4)
            loc["siege"] = [{"side": side, "color": "gold" if side == "guelph" else "purple", "count": new_count}]
    # All Lords here marked Fought
    for oid in loc.get("lords_present", []):
        state["lords"][oid].setdefault("flags", {})["moved_fought"] = True
    state["actions_remaining"] = 0
    state["card_action_consumed_by_entire_card"] = True
    return _finish_card_with({
        "siege_at": locale_name, "surrender": surrender,
        "siege_count_after": sum(s.get("count", 1) for s in loc.get("siege", [])),
        "ravage_bonus": ravage_bonus,
    }, state, side, reason="siege_entire_card", citation="4.5.1")


def _apply_surrender(state, locale_name, side, rng, rolls_log):
    """Per 4.5.1: Surrender flips Allegiance, removes Siege markers,
    triggers Revolt/Treachery # = Stronghold Value."""
    loc = state["locales"][locale_name]
    size = sd.STRONGHOLDS[loc["type"]]["size"]
    # Remove enemy Allegiance markers; add own
    enemy = "ghibelline" if side == "guelph" else "guelph"
    loc["current_allegiance"] = [m for m in loc.get("current_allegiance", []) if m.get("side") != enemy]
    for _ in range(size):
        loc["current_allegiance"].append({"side": side, "value": 1})
    state["vp"][side] = min(state["vp"].get(side, 0) + size, 17.5)
    state["vp"][enemy] = max(state["vp"].get(enemy, 0) - size, 0)
    # Remove all Siege markers
    loc["siege"] = []
    # Revolt + Treachery # = Size. `side` (besieger) benefits; `enemy` lost.
    trig = _revolt.trigger_revolts(state, losing_side=enemy, count=size,
                                   rng=rng, context=f"surrender_{locale_name}")
    rolls_log.extend(trig["revolt_rolls"])
    for _ in range(size):
        _add_treachery_to_enemy(state, "<surrender>", side)


def _h_cmd_storm(state, side, args, rng) -> dict[str, Any]:
    """4.5.2 STORM (1 action; ends card). Reuse resolve_storm."""
    lid = _require_active_lord(state, side, args.get("lord_id"))
    lord = state["lords"][lid]
    locale_name = lord.get("location")
    loc = state["locales"][locale_name]
    if not loc.get("siege"):
        raise IllegalAction("NO_SIEGE_HERE", f"No Siege at {locale_name}.", "4.5.2")
    enemy_side = "ghibelline" if side == "guelph" else "guelph"
    defenders = [oid for oid in loc.get("lords_present", [])
                 if state["lords"][oid].get("flags", {}).get("in_stronghold")
                 and state["lords"][oid]["side"] == enemy_side]
    from .battle import resolve_storm
    result = resolve_storm(
        state, attackers=[lid], defenders=defenders,
        active_id=lid, locale_name=locale_name,
        scripted_decisions=args.get("scripted_decisions"),
    )
    if result["outcome"] == "sack":
        _apply_sack(state, locale_name, side, result, rng)
    elif result["outcome"] == "attacker_loss":
        # Per 4.5.2: Attackers neither Retreat nor give Spoils. Siege markers stay.
        pass
    # Card ends (4.4.6)
    return _finish_card_with({
        "storm_result": result,
    }, state, side, reason="storm_ends_card", citation="4.5.2")


def _apply_sack(state, locale_name, side, storm_result, rng):
    """Per 4.5.2 SACK: full Spoils per 11.3 + Ruins + Revolt/Treachery + Knights' Quarter.

    Spoils awarded to Besiegers (size=Value):
      - Loot count = Value
      - Provender count = Value
      - Coin count = Value
      - All non-Ship Assets of losing inside Lords
      - Carroccio capture if losing Lords had one (+2 VP)
    """
    loc = state["locales"][locale_name]
    size = sd.STRONGHOLDS[loc["type"]]["size"]
    enemy = "ghibelline" if side == "guelph" else "guelph"

    # Identify inside-defeated Lords and Besieging Lords (winners)
    inside_losers = [
        oid for oid in loc.get("lords_present", [])
        if state["lords"][oid].get("flags", {}).get("in_stronghold")
        and state["lords"][oid]["side"] == enemy
    ]
    winners = [
        oid for oid in loc.get("lords_present", [])
        if state["lords"][oid]["side"] == side
        and not state["lords"][oid].get("flags", {}).get("in_stronghold")
    ]

    spoils_log: dict[str, Any] = {"loot": size, "provender": size, "coin": size,
                                   "from_inside": [], "carroccio_captured": 0}

    # Award Loot, Provender, Coin = Value each, distributed to winners
    for asset, count in (("Loot", size), ("Provender", size), ("Coin", size)):
        i = 0
        for _ in range(count):
            if not winners:
                break
            recv = state["lords"][winners[i % len(winners)]]
            recv["assets"][asset] = recv["assets"].get(asset, 0) + 1
            i += 1

    # Take all non-Ship Assets from inside Lords
    for ilid in inside_losers:
        ilord = state["lords"][ilid]
        transferred: dict[str, int] = {}
        for a, c in list(ilord.get("assets", {}).items()):
            if a == "Ship":
                continue
            if c > 0:
                transferred[a] = c
                ilord["assets"][a] = 0
        # Distribute to winners
        i = 0
        for a, n in transferred.items():
            for _ in range(n):
                if not winners:
                    break
                recv = state["lords"][winners[i % len(winners)]]
                recv["assets"][a] = recv["assets"].get(a, 0) + 1
                i += 1
        spoils_log["from_inside"].append({"lord_id": ilid, "transferred": transferred})

        # Carroccio capture (+2 VP)
        carroccio = next((v for v in ilord.get("vassals", [])
                          if v.get("name") == "Carroccio" and v.get("on_mat")), None)
        if carroccio:
            # +2 VP (running) AND persist for the end-game tally. SMOKE-Inferno-053.
            state["vp"][side] = min(state["vp"].get(side, 0) + 2, 17.5)
            ccfs = state.setdefault("captured_carroccio_for_side", {})
            ccfs[side] = ccfs.get(side, 0) + 1
            ilord["vassals"] = [v for v in ilord["vassals"] if v.get("name") != "Carroccio"]
            spoils_log["carroccio_captured"] += 1

    # Now do the Ruin/Allegiance/marker stuff
    loc["siege"] = []
    loc["current_allegiance"] = [m for m in loc.get("current_allegiance", []) if m.get("side") != enemy]
    loc["walls_plus_one"] = None
    ruins_color = "purple" if loc["allegiance"] == "guelph" else "gold"
    loc["ruins"] = ruins_color
    ruins_side = "guelph" if loc["allegiance"] == "ghibelline" else "ghibelline"
    state["vp"][ruins_side] = min(state["vp"].get(ruins_side, 0) + 0.5, 17.5)

    # Remove the removed Lords inside per 4.4.5 (Battle&Storm Sec.13 "REMOVE
    # LORDS: as if Disbanding Beyond Service, incl. Revolt and Treachery").
    storm_removed = [rl for rl in storm_result.get("removed_lords", [])
                     if rl in state["lords"]]
    for removed_lid in storm_removed:
        _disband_beyond_service_limit(state, removed_lid)
    # Per-Lord combat-removal Revolt & Treachery FIRST (Sec.13 lists this
    # before the separate Sack rolls below).
    _trigger_combat_removal_revolts(state, storm_removed, rng,
                                    context=f"storm_{locale_name}")

    # Revolt + Treachery # = Value (Sack rolls, SEPARATE from Lord removal).
    # `side` (attacker) benefits; `enemy` lost.
    _revolt.trigger_revolts(state, losing_side=enemy, count=size,
                            rng=rng, context=f"sack_{locale_name}")
    for _ in range(size):
        _add_treachery_to_enemy(state, "<sack>", side)

    return spoils_log


def _h_cmd_sally(state, side, args, rng) -> dict[str, Any]:
    """4.5.3 SALLY (1 action; ends card). Besieged Lord Sallies."""
    lid = _require_active_lord(state, side, args.get("lord_id"))
    lord = state["lords"][lid]
    if not lord.get("flags", {}).get("in_stronghold"):
        raise IllegalAction("NOT_BESIEGED", f"{lid} not Besieged.", "4.5.3")
    locale_name = lord.get("location")
    loc = state["locales"][locale_name]
    enemy_side = "ghibelline" if side == "guelph" else "guelph"
    besiegers = [oid for oid in loc.get("lords_present", [])
                 if state["lords"][oid]["side"] == enemy_side
                 and not state["lords"][oid].get("flags", {}).get("in_stronghold")]
    if not besiegers:
        raise IllegalAction("NO_BESIEGERS", f"No Besieging Lords at {locale_name}.", "4.5.3")
    # SMOKE-Inferno-056: Sally uses the Storm-style Array with Battle initiative
    # (Battle&Storm 2.3) — the Besiegers defend behind Siegeworks-as-Walls and
    # the Sallying side gets no Walls/Garrison (was a plain resolve_battle).
    from .battle import resolve_sally
    result = resolve_sally(
        state, sallying=[lid], besiegers=besiegers,
        active_id=lid, locale_name=locale_name,
        scripted_decisions=args.get("scripted_decisions"),
    )
    if result["loser"] == "defender":
        # Besiegers lose: Siege ends
        loc["siege"] = []
    else:
        # Sallying Lord loses: RAID — reduce Siege markers to 1
        if loc.get("siege"):
            loc["siege"] = [{"side": loc["siege"][0]["side"], "color": loc["siege"][0]["color"], "count": 1}]
        # Sallying Lord goes back inside (already in_stronghold)
        lord.setdefault("flags", {})["in_stronghold"] = True
    sally_removed = [rl for rl in result["removed_lords"] if rl in state["lords"]]
    for removed_lid in sally_removed:
        _disband_beyond_service_limit(state, removed_lid)
    # 4.4.5 Revolt & Treachery for Lords removed in this Sally.
    _trigger_combat_removal_revolts(state, sally_removed, rng, context="sally")
    return _finish_card_with({"sally_result": result}, state, side,
                              reason="sally_ends_card", citation="4.5.3")


def _peek_cortona_free(state, side: str):
    """S18 Cortona: return the one-shot 'cortona_treachery_free' modifier for
    `side` if present (without consuming). When set, a Revolt/Bribe targeting
    Cortona (or a target at Cortona) succeeds for 0 Coin and no roll
    (4.7.5/4.7.6 via AoW S18)."""
    for m in state.get("treachery_modifiers_pending", []):
        if m.get("effect") == "cortona_treachery_free" and m.get("side") == side:
            return m
    return None


def _consume_cortona_free(state, side: str) -> bool:
    """Pop the Cortona free-Treachery modifier for `side`; True if one was
    present. Call only once the Treachery is actually committed/succeeds."""
    m = _peek_cortona_free(state, side)
    if m is not None:
        state["treachery_modifiers_pending"].remove(m)
        return True
    return False


def _h_cmd_treachery_revolt(state, side, args, rng) -> dict[str, Any]:
    """4.7.5 Treachery-Revolt. Commit 1-4 Coin; roll dice = Stronghold
    Value; if each <= Coin, Stronghold flips Allegiance.

    S18 Cortona (AoW): if a 'cortona_treachery_free' modifier is pending for
    this side and the target is Cortona, the Revolt succeeds for 0 Coin with
    no roll. The modifier is consumed only on success.
    """
    lid = _require_active_lord(state, side, args.get("lord_id"))
    lord = state["lords"][lid]
    target_name = args.get("target_locale")
    # S18 Cortona free-Treachery is available only when target IS Cortona.
    cortona_free_available = (target_name == "Cortona"
                              and _peek_cortona_free(state, side) is not None)
    coin = int(args.get("coin", 0 if cortona_free_available else 1))
    if cortona_free_available:
        if not (0 <= coin <= 4):
            raise IllegalAction("BAD_COIN", "Revolt commits 0-4 Coin (Cortona free).", "4.7.5")
    else:
        if not (1 <= coin <= 4):
            raise IllegalAction("BAD_COIN", "Revolt commits 1-4 Coin.", "4.7.5")
        if lord["assets"].get("Coin", 0) < coin:
            raise IllegalAction("INSUFFICIENT_COIN", f"{lid} has {lord['assets'].get('Coin',0)} Coin; needs {coin}.", "4.7.5")
    target = state["locales"].get(target_name)
    if not target:
        raise IllegalAction("UNKNOWN_LOCALE", f"{target_name} not found.", "4.7.5")
    if target.get("ruins"):
        raise IllegalAction("RUINS", "Cannot Revolt Ruins.", "4.7.5/1.4.1")
    if target["type"] == "outpost":
        raise IllegalAction("OUTPOST", "Cannot Revolt Outposts.", "4.7.5/1.4.1")
    # Target must be Enemy + at or adjacent to Active Lord
    if _is_friendly_locale(state, target, side):
        raise IllegalAction("FRIENDLY_LOCALE", "Target must be Enemy aligned.", "4.7.5")
    # Adjacency
    cur = lord.get("location")
    if cur != target_name:
        adj_names = [n for n, _ in sd.adjacent_to(cur)]
        if target_name not in adj_names:
            raise IllegalAction("NOT_ADJACENT", f"{target_name} not at/adjacent to {cur}.", "4.7.5")
    # No Enemy Lord there or adjacent
    enemy = "ghibelline" if side == "guelph" else "guelph"
    danger_locales = [target_name] + [n for n, _ in sd.adjacent_to(target_name)]
    for loc_n in danger_locales:
        l = state["locales"].get(loc_n)
        if not l:
            continue
        for oid in l.get("lords_present", []):
            if state["lords"][oid]["side"] == enemy and state["lords"][oid]["status"] == "mustered":
                raise IllegalAction("ENEMY_LORD_NEARBY", f"Enemy Lord {oid} at or adjacent to {target_name}.", "4.7.5/1.4.1")
    # Roll dice (skipped when S18 Cortona free-Treachery applies)
    size = sd.STRONGHOLDS[target["type"]]["size"]
    rolls = []
    accepted = True
    cortona_free = False
    if cortona_free_available:
        cortona_free = _consume_cortona_free(state, side)  # commit now (all checks passed)
        coin = 0
    else:
        for i in range(size):
            r = rng.roll(f"revolt_treachery_{target_name}_{i}")
            rolls.append({"context": r.context, "value": r.value})
            if r.value > coin:
                accepted = False
    switch = None
    exiles_required = None
    if accepted:
        # Pay Coin (0 if Cortona free), then flip Allegiance THROUGH the shared
        # revolt machinery so VP adjustment and the 1.4.4 Exiles step match an
        # automatic revolt.
        # SMOKE-Inferno-049: a successful player-initiated Treachery-Revolt
        # (4.7.5) flips the Stronghold via revolt.apply_allegiance_switch and
        # surfaces the 1.4.4 Exiles decision (pending_exiles), exactly like
        # Disband/Surrender/Sack/Languish/automatic revolts; it no longer
        # hand-rolls the flip and skips Exiles.
        lord["assets"]["Coin"] = lord["assets"].get("Coin", 0) - coin
        switch = _revolt.apply_allegiance_switch(state, target_name, side)
        if switch["exiles_count"] > 0:
            exiles_required = {
                "side": switch["exiles_side"],
                "count": switch["exiles_count"],
                "candidates": _revolt.legal_exiles_targets(state, switch["exiles_side"]),
            }
            state.setdefault("pending_exiles", []).append(exiles_required)
    return _finish_card_with({
        "treachery_revolt": {"target": target_name, "coin": coin, "size": size,
                              "accepted": accepted, "rolls": [r["value"] for r in rolls],
                              "cortona_free": cortona_free,
                              "switch": switch, "exiles_required": exiles_required},
    }, state, side, reason="treachery_card_ends", citation="4.7.5")



def _h_cmd_treachery_bribe(state, side, args, rng) -> dict[str, Any]:
    """4.7.6 Treachery-Bribe. Roll 1d6 > Vassal's Service Rating = success.

    v1.6 full implementation:
      Path-A (Mustered): target an Enemy Vassal at the same/adjacent
        Locale, parent Lord Mustered. (Existing.)
      Path-B (Unmustered, SMOKE-Inferno-031): target an Unmustered Vassal
        whose Vassal Seat is at the same/adjacent Locale. Parent Lord may
        be removed (4.4.5) or not yet on the map. Vassals of REMOVED
        Lords count as Unmustered per Tip.

    Hidden Mats interaction (SMOKE-Inferno-032): if state.meta.hidden_mats
    is set, an invalid Path-A target falls through to Path-B silently
    rather than raising.

    Special Vassals (Carroccio/Sestiere/Terzo/Altopascio) cannot be Bribed.
    """
    lid = _require_active_lord(state, side, args.get("lord_id"))
    lord = state["lords"][lid]
    target_lord_id = args.get("target_lord_id")
    vassal_name = args.get("vassal")
    if not vassal_name:
        raise IllegalAction("MISSING_VASSAL", "Bribe requires vassal name.", "4.7.6")
    if lord["assets"].get("Coin", 0) < 1:
        raise IllegalAction("NO_COIN", "Bribe requires at least 1 Coin.", "4.7.6")
    enemy = "ghibelline" if side == "guelph" else "guelph"
    cur = lord.get("location")

    # PATH-A: Mustered target
    target_lord = state["lords"].get(target_lord_id) if target_lord_id else None
    target_vassal = None
    path = None
    if target_lord and target_lord["status"] == "mustered":
        if target_lord.get("side") == enemy:
            target_vassal = next((v for v in target_lord.get("vassals", [])
                                  if v["name"] == vassal_name and v.get("on_mat")), None)
            if target_vassal:
                # Adjacency check based on Mustered Vassal's parent Lord's Locale
                target_loc = target_lord.get("location")
                adj_names = [n for n, _ in sd.adjacent_to(cur)] if cur else []
                if target_loc == cur or target_loc in adj_names:
                    path = "A"

    # PATH-B: Unmustered Vassal via Seat (if Path-A didn't match)
    if path is None:
        # Find the Vassal in the static Lords data
        from . import card_data as cd  # noqa
        found_parent_canonical = None
        found_v = None
        for canonical, lord_data in sd.LORDS.items():
            for v in lord_data.get("vassals", []):
                if v.get("name") == vassal_name and not v.get("special"):
                    found_parent_canonical = canonical
                    found_v = v
                    break
            if found_v:
                break
        if found_v is None:
            raise IllegalAction("UNKNOWN_VASSAL",
                                f"No non-Special Vassal named {vassal_name!r} in any Lord roster.",
                                "4.7.6")
        # Check parent's current state — Vassal Unmustered iff parent's vassals
        # entry has on_mat=False OR parent is removed/in_levy_pool.
        parent_lid = sd.LORD_IDS.get(found_parent_canonical)
        if parent_lid is None:
            raise IllegalAction("UNKNOWN_LORD",
                                f"Parent of {vassal_name} not found.", "4.7.6")
        parent = state["lords"][parent_lid]
        if parent["side"] != enemy:
            raise IllegalAction("FRIENDLY_VASSAL",
                                f"{vassal_name} belongs to friendly side.", "4.7.6")
        # Vassal Seat at/adjacent to Active Lord
        seats = found_v.get("seats") or ([found_v.get("seat")] if found_v.get("seat") else [])
        seats = [s for s in seats if s]
        if not seats:
            raise IllegalAction("NO_VASSAL_SEAT",
                                f"{vassal_name} has no Vassal Seat (Special Vassals can't be Bribed).",
                                "4.7.6")
        adj_names = [n for n, _ in sd.adjacent_to(cur)] if cur else []
        eligible_seat = any((s == cur or s in adj_names) for s in seats)
        if not eligible_seat:
            raise IllegalAction(
                "NO_ELIGIBLE_SEAT",
                f"{vassal_name}'s Seats {seats} not at/adjacent to {cur}.",
                "4.7.6",
            )
        # If parent is Mustered, check that this Vassal is NOT already on mat
        if parent["status"] == "mustered":
            on_mat = next((v for v in parent.get("vassals", [])
                           if v.get("name") == vassal_name and v.get("on_mat")), None)
            if on_mat:
                # Mustered — Path-A applies instead; fall back to Path-A
                target_vassal = on_mat
                target_lord = parent
                target_lord_id = parent_lid
                path = "A"
            else:
                target_vassal = next((v for v in parent.get("vassals", [])
                                      if v["name"] == vassal_name), None)
                if target_vassal:
                    path = "B_mustered_parent"
        else:
            target_vassal = found_v
            path = "B_unmustered_parent"
        if target_vassal is None:
            raise IllegalAction("UNKNOWN_VASSAL",
                                f"Vassal {vassal_name} not found on parent {parent_lid}.",
                                "4.7.6")

    if target_vassal.get("special"):
        raise IllegalAction("SPECIAL_VASSAL",
                            "Special Vassals (Carroccio/Sestiere/Terzo/Altopascio) cannot be Bribed.",
                            "4.7.6")

    # Roll (S18 Cortona: auto-success for 0 Coin if target is/at Cortona)
    sr = target_vassal.get("service_rating", 0)
    target_loc = (target_lord.get("location") if path == "A" and target_lord else None)
    cortona_free = ((cur == "Cortona" or target_loc == "Cortona")
                    and _peek_cortona_free(state, side) is not None)
    if cortona_free:
        _consume_cortona_free(state, side)
        r = None
        success = True
        coin_paid = 0
    else:
        r = rng.roll(f"bribe_{target_vassal['name']}")
        success = r.value > sr
        coin_paid = 1
    if success:
        lord["assets"]["Coin"] -= coin_paid
        # Move Vassal forces (only if on_mat with surviving forces)
        if path == "A":
            target_lord["vassals"] = [v for v in target_lord["vassals"] if v["name"] != vassal_name]
            for unit, count in target_vassal.get("forces", {}).items():
                lord["forces"][unit] = lord["forces"].get(unit, 0) + count
            target_vassal["turncoat"] = True
            target_vassal["ready"] = False
            lord.setdefault("vassals", []).append(target_vassal)
            if sum(target_lord.get("forces", {}).values()) == 0:
                _disband_beyond_service_limit(state, target_lord_id)
        else:
            # Path-B: Move Vassal to active Lord's mat. Force values from static.
            v_copy = copy.deepcopy(target_vassal)
            v_copy["turncoat"] = True
            v_copy["on_mat"] = True
            v_copy["ready"] = False
            lord.setdefault("vassals", []).append(v_copy)
            for unit, count in v_copy.get("forces", {}).items():
                lord["forces"][unit] = lord["forces"].get(unit, 0) + count
    return _finish_card_with({
        "treachery_bribe": {
            "target_lord": target_lord_id, "vassal": vassal_name,
            "path": path, "service_rating": sr,
            "die": (r.value if r is not None else None), "success": success,
            "cortona_free": cortona_free,
        },
    }, state, side, reason="treachery_card_ends", citation="4.7.6")


# Register Phase 3c handlers
_HANDLERS.update({
    "besiege_or_bypass":         _h_besiege_or_bypass,
    "cmd_siege":                 _h_cmd_siege,
    "cmd_storm":                 _h_cmd_storm,
    "cmd_sally":                 _h_cmd_sally,
    "cmd_treachery_revolt":      _h_cmd_treachery_revolt,
    "cmd_treachery_bribe":       _h_cmd_treachery_bribe,
})


# =====================================================================
# Phase 3d: Bypass-state March (4.3.6) + Lieutenants (4.1.3) + 1.6 helper
# =====================================================================


def _consume_lordship(state, mustering_lord_id: str) -> None:
    """Each 3.4 sub-action consumes 1 Lordship from the Mustering Lord.
    Per 3.4.1: Newly Mustered Lords may NOT themselves take Levy actions
    this segment (SMOKE-Inferno-028)."""
    lord = state["lords"].get(mustering_lord_id)
    if lord is None:
        return
    if lord.get("flags", {}).get("just_mustered_this_segment"):
        raise IllegalAction(
            "NEWLY_MUSTERED",
            f"{mustering_lord_id} was just Mustered this Levy segment and may NOT take Levy actions (3.4.1).",
            "3.4.1",
        )
    rating = lord.get("ratings", {}).get("L", 0)
    used = lord.setdefault("flags", {}).get("lordship_used", 0)
    if used >= rating:
        raise IllegalAction(
            "LORDSHIP_EXHAUSTED",
            f"{mustering_lord_id} has used all {rating} Lordship actions this Muster segment.",
            "3.4",
        )
    # Apply Lordship bonus from F11 Poggio Bonizio / etc.
    bonus = lord.get("flags", {}).get("lordship_bonus_pending", 0)
    effective = rating + bonus
    if used >= effective:
        raise IllegalAction(
            "LORDSHIP_EXHAUSTED",
            f"{mustering_lord_id} has used all {effective} Lordship actions this segment.",
            "3.4",
        )
    lord["flags"]["lordship_used"] = used + 1

def _check_disband_on_zero_forces(state, lord_id: str) -> bool:
    """1.6: a Lord who loses his last unit outside combat Disbands.
    Returns True if Disbanded."""
    lord = state["lords"].get(lord_id)
    if not lord:
        return False
    if lord["status"] != "mustered":
        return False
    if sum((lord.get("forces") or {}).values()) > 0:
        return False
    _disband_beyond_service_limit(state, lord_id)
    return True


def _h_cmd_depart(state, side, args, rng) -> dict[str, Any]:
    """4.3.6 DEPART: a Lord at a Bypass marker Marches to adjacent normally."""
    lid = _require_active_lord(state, side, args.get("lord_id"))
    lord = state["lords"][lid]
    bypassing_loc = lord.get("flags", {}).get("bypassing")
    if not bypassing_loc or lord.get("location") != bypassing_loc:
        raise IllegalAction("NOT_AT_BYPASS", f"{lid} not at Bypass marker.", "4.3.6")
    # Delegate to standard March
    march_result = _h_cmd_march(state, side, args, rng)
    # If no Lord remains at the Bypassed Stronghold, remove Bypass markers (4.3.5)
    bypass_loc = state["locales"][bypassing_loc]
    remaining_bypassers = [
        oid for oid in bypass_loc.get("lords_present", [])
        if state["lords"][oid].get("flags", {}).get("bypassing") == bypassing_loc
    ]
    if not remaining_bypassers:
        bypass_loc["bypass"] = []
    lord["flags"].pop("bypassing", None)
    return march_result


def _h_cmd_encamp(state, side, args, rng) -> dict[str, Any]:
    """4.3.6 ENCAMP: 1 action regardless of Laden; replace Bypass with 1 Siege; end card."""
    lid = _require_active_lord(state, side, args.get("lord_id"))
    lord = state["lords"][lid]
    bypassing_loc = lord.get("flags", {}).get("bypassing")
    if not bypassing_loc or lord.get("location") != bypassing_loc:
        raise IllegalAction("NOT_AT_BYPASS", f"{lid} not at Bypass marker.", "4.3.6")
    if (state.get("actions_remaining") or 0) < 1:
        raise IllegalAction("INSUFFICIENT_ACTIONS", "Encamp costs 1 action.", "4.3.6")
    loc = state["locales"][bypassing_loc]
    loc["bypass"] = []
    loc.setdefault("siege", []).append({"side": side, "color": "gold" if side == "guelph" else "purple", "count": 1})
    # Clear bypassing flag on this Lord
    lord["flags"].pop("bypassing", None)
    lord.setdefault("flags", {})["moved_fought"] = True
    state["actions_remaining"] = 0
    state["card_action_consumed_by_entire_card"] = True
    return _finish_card_with({"encamped": bypassing_loc}, state, side,
                              reason="encamp_ends_card", citation="4.3.6")


def _h_cmd_sortie(state, side, args, rng) -> dict[str, Any]:
    """4.3.6 SORTIE: 1 action regardless of Laden for Lord inside a
    Bypassed Friendly Stronghold to Approach the Bypassing Enemy outside.

    Phase 3d: single-Lord Sortie; group Sortie (Commander/Lieutenant)
    deferred.
    """
    lid = _require_active_lord(state, side, args.get("lord_id"))
    lord = state["lords"][lid]
    if not lord.get("flags", {}).get("in_stronghold"):
        raise IllegalAction("NOT_INSIDE", f"{lid} not inside Stronghold.", "4.3.6")
    locale_name = lord.get("location")
    loc = state["locales"][locale_name]
    if not loc.get("bypass"):
        raise IllegalAction("NOT_BYPASSED", f"{locale_name} not Bypassed.", "4.3.6")
    enemy_side = "ghibelline" if side == "guelph" else "guelph"
    enemy_bypassers = [
        oid for oid in loc.get("lords_present", [])
        if state["lords"][oid]["side"] == enemy_side
        and state["lords"][oid].get("flags", {}).get("bypassing") == locale_name
    ]
    if not enemy_bypassers:
        raise IllegalAction("NO_BYPASSERS", f"No Bypassing Enemy at {locale_name}.", "4.3.6")
    # Sortie out of Stronghold, then Approach.
    lord["flags"].pop("in_stronghold", None)
    # Trigger Approach pending decisions for each Enemy Bypasser
    pendings = []
    for eid in enemy_bypassers:
        pendings.append({
            "type": "approach_response",
            "side": enemy_side,
            "options": ["stand"],  # Bypassing Lords typically can't Avoid/Withdraw
            "info": {"lord_id": eid, "approaching_lord": lid,
                     "locale": locale_name, "approached_via": "sortie",
                     "approached_from": None},
        })
    state.setdefault("pending", []).extend(pendings)
    state["meta"]["approach_attacker_side"] = side
    state["meta"]["active_player"] = enemy_side
    state["actions_remaining"] -= 1
    return {
        "state_changes": {"sortie_from": locale_name, "approach_triggered": True,
                          "pending_responses": [p["info"]["lord_id"] for p in pendings]},
        "rule_citation": "4.3.6",
    }


def _h_plan_attach_lieutenant(state, side, args, rng) -> dict[str, Any]:
    """4.1.3 During Plan step: stack one Lord's cylinder on another
    Friendly Lord at the same Locale. Upper = Lieutenant, lower = Lower
    Lord. Persists during Campaign.

    Constraints (4.1.3):
      - Same Locale.
      - Both Mustered.
      - Neither is Commander or Comune.
      - One Lower Lord max per Lieutenant; Lower Lord may not be a
        Lieutenant.

    args:
      lieutenant: Lord ID
      lower_lord: Lord ID
    """
    from .flow import current_campaign_step
    if current_campaign_step(state) != "plan":
        raise IllegalAction("WRONG_STEP", "attach_lieutenant only during plan step.", "4.1.3")
    lt = args.get("lieutenant")
    ll = args.get("lower_lord")
    lt_lord = state["lords"].get(lt)
    ll_lord = state["lords"].get(ll)
    if lt_lord is None or ll_lord is None:
        raise IllegalAction("UNKNOWN_LORD", "lieutenant or lower_lord not found.", "4.1.3")
    if lt_lord["side"] != side or ll_lord["side"] != side:
        raise IllegalAction("WRONG_SIDE", "Both Lords must be own-side.", "4.1.3")
    if lt_lord["status"] != "mustered" or ll_lord["status"] != "mustered":
        raise IllegalAction("NOT_MUSTERED", "Both Lords must be Mustered.", "4.1.3")
    if lt_lord.get("location") != ll_lord.get("location"):
        raise IllegalAction("DIFFERENT_LOCALES", "Both Lords must be at same Locale.", "4.1.3")
    if lt_lord.get("commander") or lt_lord.get("comune_of") or ll_lord.get("commander") or ll_lord.get("comune_of"):
        raise IllegalAction("COMMANDER_NOT_ELIGIBLE", "Commander/Comune cannot be Lieutenant/Lower Lord.", "4.1.3")
    # No nesting
    if lt_lord.get("flags", {}).get("lower_lord_of") or ll_lord.get("flags", {}).get("lieutenant_for"):
        raise IllegalAction("ALREADY_STACKED", "One Lord already in a Lieutenant relationship.", "4.1.3")
    if ll_lord.get("flags", {}).get("has_lower_lord"):
        raise IllegalAction("ALREADY_HAS_LOWER", f"{ll} already has a Lower Lord.", "4.1.3")
    lt_lord.setdefault("flags", {})["has_lower_lord"] = ll
    ll_lord.setdefault("flags", {})["lower_lord_of"] = lt
    return {
        "state_changes": {"lieutenant": lt, "lower_lord": ll},
        "rule_citation": "4.1.3",
    }


# Lower-Lord card reveal handling (4.2.4): revealing a Lower Lord's
# command card = Pass. The dispatcher routes via _h_command_reveal;
# we add the check there.
def _is_lower_lord(state, lord_id: str) -> bool:
    return bool(state["lords"].get(lord_id, {}).get("flags", {}).get("lower_lord_of"))


# Register Phase 3d handlers
_HANDLERS.update({
    "cmd_depart":            _h_cmd_depart,
    "cmd_encamp":            _h_cmd_encamp,
    "cmd_sortie":            _h_cmd_sortie,
    "plan_attach_lieutenant": _h_plan_attach_lieutenant,
})


# =====================================================================
# Phase 3e: End-of-Campaign 4.9 substeps
# =====================================================================
def _h_end_grow(state, side, args, rng) -> dict[str, Any]:
    """4.9.1 GROW (only on certain Turns).

    SMOKE-Inferno-037: Scenario B 'Reprisal War' — skip Grow on
    Autumn 1259 (Turn 5).

    At the end of late-Spring (Apr-May) and Autumn (Oct-Nov) Turns —
    Calendar boxes 2, 5, 8, 11, 14 — Guelph then Ghibelline each MUST
    select and reduce the ENEMY'S Ravage markers to 1/2 their total,
    rounded UP. Adjust VP accordingly.

    args:
      keep:  list of locale names to KEEP enemy Ravage markers on (the
             rest are removed). The count of kept = ceil(N/2).
    """
    from .flow import current_campaign_step, advance_campaign_side_or_step
    if current_campaign_step(state) != "end_campaign":
        raise IllegalAction("WRONG_STEP", "Grow runs in end_campaign step.", "4.9.1")
    if (state["meta"]["scenario"] == "B" and state["meta"]["turn"] == 5):
        # Reprisal War: skip Grow on Turn 5
        if side == "ghibelline":
            state["meta"]["end_substep_done"] = state["meta"].get("end_substep_done", []) + ["grow"]
        advance_campaign_side_or_step(state)
        return {"state_changes": {"grow": "skipped_reprisal_war"}, "rule_citation": "4.9.1"}
    if state["meta"]["turn"] not in sd.GROW_BOXES:
        raise IllegalAction("NOT_GROW_TURN", f"Box {state['meta']['turn']} is not a Grow turn.", "4.9.1")
    enemy = "ghibelline" if side == "guelph" else "guelph"
    # Side selects which OF THE ENEMY'S Ravage markers to REDUCE; we remove
    # ravaged markers of the enemy color (i.e., marked by side, since marker
    # color = opposite printed; side's Ravage adds to enemy's tally? No —
    # Ravage marker color = opposite printed, so Guelph Ravage of Ghib town
    # places a gold (Guelph) marker. The OWNER of the marker is the one who
    # benefits from VP. So "Enemy's Ravage markers" = markers benefiting
    # the enemy.
    # Phase 3e: simplified — "enemy Ravage markers" = ravaged Locales where
    # the marker color is enemy's color ("gold" for guelph, "purple" for ghibelline).
    enemy_color = "gold" if enemy == "guelph" else "purple"
    enemy_ravage_locales = [
        n for n, l in state["locales"].items()
        if l.get("ravaged") == enemy_color
    ]
    n = len(enemy_ravage_locales)
    if n == 0:
        from .flow import advance_campaign_side_or_step
        if side == "ghibelline":
            state["meta"]["end_substep_done"] = state["meta"].get("end_substep_done", []) + ["grow"]
        advance_campaign_side_or_step(state)
        return {"state_changes": {"grow": "no enemy ravages"}, "rule_citation": "4.9.1"}
    keep_count = (n + 1) // 2  # rounded UP (per 4.9.1, "halved rounded UP" means N - ceil(N/2) are removed? Re-read)
    # Re-read 4.9.1: "reduce the ENEMY'S Ravage markers on the map to 1/2
    # their total, rounded UP." So we REDUCE TO ceil(N/2). Keep = ceil(N/2).
    # That means side selects the (N - keep_count) to remove.
    keep = args.get("keep")
    if keep is None:
        # Default: keep the first keep_count locales (leftmost selection).
        keep = enemy_ravage_locales[:keep_count]
    if len(set(keep)) != keep_count or any(k not in enemy_ravage_locales for k in keep):
        raise IllegalAction("BAD_KEEP", f"Must specify exactly {keep_count} of {enemy_ravage_locales} to keep.", "4.9.1")
    removed = [n for n in enemy_ravage_locales if n not in keep]
    for loc_name in removed:
        state["locales"][loc_name]["ravaged"] = None
        # VP adjustment: enemy loses 1/2 VP per removed Ravage marker
        state["vp"][enemy] = max(state["vp"].get(enemy, 0) - 0.5, 0)
    # After Ghibelline grow, mark grow done
    if side == "ghibelline":
        state["meta"]["end_substep_done"] = state["meta"].get("end_substep_done", []) + ["grow"]
    from .flow import advance_campaign_side_or_step
    advance_campaign_side_or_step(state)
    return {
        "state_changes": {"grow_removed": removed, "grow_kept": keep},
        "rule_citation": "4.9.1",
    }


def _h_end_grow_skip(state, side, args, rng) -> dict[str, Any]:
    """Skip Grow when not a Grow turn or no enemy Ravage markers."""
    from .flow import current_campaign_step, advance_campaign_side_or_step
    if current_campaign_step(state) != "end_campaign":
        raise IllegalAction("WRONG_STEP", "Grow runs in end_campaign step.", "4.9.1")
    if side == "ghibelline":
        state["meta"]["end_substep_done"] = state["meta"].get("end_substep_done", []) + ["grow"]
    advance_campaign_side_or_step(state)
    return {"state_changes": {"grow": "skipped"}, "rule_citation": "4.9.1"}


def _h_end_ransom(state, side, args, rng) -> dict[str, Any]:
    """4.9.2 RANSOM: pay 1 Coin per 6 captured units (rounded UP),
    full amount to enemy pool. Recover HALF (rounded UP) of those units
    distributed to own Mustered Lords. Remainder returns to pool.

    args:
      pay:  bool — pay full Ransom and recover units, else Languish.
      coin_from: optional lord_id that pays the Coin (default: first
                 Mustered own Lord with enough Coin).
      distribute_to: optional list[lord_id] — distribution targets.
    """
    from .flow import current_campaign_step, advance_campaign_side_or_step
    if current_campaign_step(state) != "end_campaign":
        raise IllegalAction("WRONG_STEP", "Ransom runs in end_campaign.", "4.9.2")
    captured = state.get("captured_knights", {}).get(side, {})
    total_captured = sum(captured.values())
    if total_captured == 0:
        if side == "ghibelline":
            state["meta"]["end_substep_done"] = state["meta"].get("end_substep_done", []) + ["ransom"]
        advance_campaign_side_or_step(state)
        return {"state_changes": {"ransom": "no captures"}, "rule_citation": "4.9.2"}
    cost = (total_captured + 5) // 6   # ceil(N/6)
    pay = bool(args.get("pay", True))
    if pay:
        # Find a paying Lord with enough Coin
        coin_from = args.get("coin_from")
        candidates = ([state["lords"][coin_from]] if coin_from else
                      [l for l in state["lords"].values()
                       if l["side"] == side and l["status"] == "mustered"])
        payer = next((l for l in candidates if l["assets"].get("Coin", 0) >= cost), None)
        if payer is None:
            raise IllegalAction("INSUFFICIENT_COIN",
                                f"Ransom needs {cost} Coin total; no eligible Lord can pay.", "4.9.2")
        payer["assets"]["Coin"] -= cost
        # Coin goes to enemy pool — distribute to enemy Mustered Lords (first one)
        enemy = "ghibelline" if side == "guelph" else "guelph"
        enemy_lords = [l for l in state["lords"].values()
                       if l["side"] == enemy and l["status"] == "mustered"]
        if enemy_lords:
            enemy_lords[0]["assets"]["Coin"] = enemy_lords[0]["assets"].get("Coin", 0) + cost
        # Recover half (rounded UP) units, distribute to own Mustered
        recover_half = {u: (c + 1) // 2 for u, c in captured.items()}
        recovered_units = sum(recover_half.values())
        # Distribute
        targets_ids = args.get("distribute_to") or [
            lid for lid, l in state["lords"].items()
            if l["side"] == side and l["status"] == "mustered"
        ]
        if not targets_ids:
            advance_campaign_side_or_step(state)
            return {"state_changes": {"ransom": "paid but no Lords to receive"}, "rule_citation": "4.9.2"}
        i = 0
        for u, c in recover_half.items():
            for _ in range(c):
                t = state["lords"][targets_ids[i % len(targets_ids)]]
                t.setdefault("forces", {})[u] = t["forces"].get(u, 0) + 1
                i += 1
        # Remainder returns to pool (nothing to do — they're just not added back)
        # Clear captured ledger
        state["captured_knights"][side] = {}
        if side == "ghibelline":
            state["meta"]["end_substep_done"] = state["meta"].get("end_substep_done", []) + ["ransom"]
        advance_campaign_side_or_step(state)
        return {
            "state_changes": {"ransom_paid": cost, "recovered_total": recovered_units},
            "rule_citation": "4.9.2",
        }
    else:
        # LANGUISH: enemy rolls Revolt OR adds Treachery (their choice) per 6 captured
        n_rolls = (total_captured + 5) // 6
        enemy = "ghibelline" if side == "guelph" else "guelph"
        # 1.4.2 rolls: `side`'s captives Languish -> `enemy` benefits/rolls.
        _revolt.trigger_revolts(state, losing_side=side, count=n_rolls,
                                rng=rng, context=f"languish_{side}")
        results = []
        for _ in range(n_rolls):
            _add_treachery_to_enemy(state, "<languish>", enemy)
        # Captured units removed (Lost)
        state["captured_knights"][side] = {}
        if side == "ghibelline":
            state["meta"]["end_substep_done"] = state["meta"].get("end_substep_done", []) + ["ransom"]
        advance_campaign_side_or_step(state)
        return {
            "state_changes": {"languished": True, "rolls": n_rolls, "removed_units": total_captured},
            "rule_citation": "4.9.2",
        }


def _h_end_game_check(state, side, args, rng) -> dict[str, Any]:
    """4.9.3 Game End check: if this was the scenario's last 60-Day Turn,
    the game ends. Applies scenario-specific VP modifiers:
      - Scenario E 'Resistance': double Guelph VP except from Ravaged.
      - Scenario C 'Alliance Treaty' (S22 Manfredi in play): +3 Ghib VP.
    """
    from .flow import current_campaign_step, advance_campaign_step
    if current_campaign_step(state) != "end_campaign":
        raise IllegalAction("WRONG_STEP", "Game-end check in end_campaign.", "4.9.3")
    cal = state["calendar"]
    if cal.get("end_box") and state["meta"]["turn"] >= cal["end_box"] - 1:
        # Apply scenario-end VP modifiers per 5.1 + scenario rules.
        g, h = _compute_final_vp(state)
        winner = None
        if g > h:
            winner = "guelph"
        elif h > g:
            winner = "ghibelline"
        state["meta"]["phase"] = "victory"
        state["meta"]["game_over"] = True
        state["meta"]["winner"] = winner
        # Persist final VP to state.vp
        state["vp"]["guelph"] = g
        state["vp"]["ghibelline"] = h
        return {
            "state_changes": {"game_ended": True, "winner": winner, "vp_g": g, "vp_h": h},
            "rule_citation": "4.9.3 / 5.3",
        }
    state["meta"]["end_substep_done"] = state["meta"].get("end_substep_done", []) + ["game_check"]
    state["meta"]["active_player"] = "guelph"
    return {"state_changes": {"game_ended": False}, "rule_citation": "4.9.3"}


def _h_end_repair(state, side, args, rng) -> dict[str, Any]:
    """4.9.4 REPAIR (per Errata): Remove ONE Siege marker from each TOWN
    and CITY that has 3 or 4 Siege markers. Castles do NOT Repair."""
    from .flow import current_campaign_step
    if current_campaign_step(state) != "end_campaign":
        raise IllegalAction("WRONG_STEP", "Repair in end_campaign.", "4.9.4")
    repaired = []
    for name, loc in state["locales"].items():
        if loc["type"] not in ("town", "city"):
            continue
        total = sum(s.get("count", 1) for s in loc.get("siege", []))
        if 3 <= total <= 4:
            # Reduce by 1
            for s in loc["siege"]:
                if s.get("count", 1) >= 1:
                    s["count"] -= 1
                    if s["count"] <= 0:
                        loc["siege"].remove(s)
                    break
            repaired.append(name)
    state["meta"]["end_substep_done"] = state["meta"].get("end_substep_done", []) + ["repair"]
    # Repair is not per-side; reset active to Guelph for the next substep.
    state["meta"]["active_player"] = "guelph"
    return {"state_changes": {"repaired": repaired}, "rule_citation": "4.9.4 (Errata)"}


def _h_end_waste(state, side, args, rng) -> dict[str, Any]:
    """4.9.5 WASTE: each side selects and discards one Asset OR one
    'This Lord' Capability from each of its Lords who has MORE THAN ONE
    of any type of Asset or more than one such card.

    args:
      discards: dict {lord_id: {"asset": "Coin"} OR {"capability": "F12"}}
    """
    from .flow import current_campaign_step, advance_campaign_side_or_step
    if current_campaign_step(state) != "end_campaign":
        raise IllegalAction("WRONG_STEP", "Waste in end_campaign.", "4.9.5")
    discards = args.get("discards", {})
    own_lords = [(lid, l) for lid, l in state["lords"].items()
                 if l["side"] == side and l["status"] == "mustered"]
    waste_log = []
    for lid, lord in own_lords:
        # Eligible if has >1 of any Asset type or >1 'This Lord' Capability
        has_multi_asset = any(c > 1 for c in lord.get("assets", {}).values())
        has_multi_cap = len(lord.get("capabilities", [])) > 1
        if not (has_multi_asset or has_multi_cap):
            continue
        choice = discards.get(lid)
        if choice is None:
            # Default: discard the first Asset with count > 1
            for a, c in lord["assets"].items():
                if c > 1:
                    lord["assets"][a] -= 1
                    waste_log.append({"lord_id": lid, "discarded_asset": a})
                    break
            else:
                # Fall back to discarding a Capability
                if lord.get("capabilities"):
                    cap_id = lord["capabilities"].pop()
                    state["decks"][side]["aow_deck"].append(cap_id)
                    waste_log.append({"lord_id": lid, "discarded_capability": cap_id})
        else:
            if "asset" in choice:
                a = choice["asset"]
                if lord["assets"].get(a, 0) <= 0:
                    raise IllegalAction("BAD_DISCARD", f"{lid} has no {a} to discard.", "4.9.5")
                lord["assets"][a] -= 1
                waste_log.append({"lord_id": lid, "discarded_asset": a})
            elif "capability" in choice:
                cap_id = choice["capability"]
                if cap_id not in lord.get("capabilities", []):
                    raise IllegalAction("BAD_DISCARD", f"{lid} has no '{cap_id}' Capability.", "4.9.5")
                lord["capabilities"].remove(cap_id)
                state["decks"][side]["aow_deck"].append(cap_id)
                waste_log.append({"lord_id": lid, "discarded_capability": cap_id})
    if side == "ghibelline":
        state["meta"]["end_substep_done"] = state["meta"].get("end_substep_done", []) + ["waste"]
    advance_campaign_side_or_step(state)
    return {"state_changes": {"waste": waste_log}, "rule_citation": "4.9.5"}


def _h_end_reset(state, side, args, rng) -> dict[str, Any]:
    """4.9.6 RESET: set aside used Treachery cards; unstack Lieutenants;
    discard 'This Campaign' Events; advance Calendar Levy marker; flip
    to Levy phase."""
    from .flow import current_campaign_step
    if current_campaign_step(state) != "end_campaign":
        raise IllegalAction("WRONG_STEP", "Reset in end_campaign.", "4.9.6")
    # Set aside used Treachery cards (Phase 3e: all Treachery cards in any side's plan this Campaign return to set-aside)
    for s in ("guelph", "ghibelline"):
        deck = state["decks"][s]
        treach_in_command = [c for c in deck["command_deck"] if c.startswith("treachery_")]
        for c in treach_in_command:
            deck["command_deck"].remove(c)
            deck["treachery_set_aside"].append(c)
    # Unstack Lieutenants
    for lord in state["lords"].values():
        lord.get("flags", {}).pop("has_lower_lord", None)
        lord.get("flags", {}).pop("lower_lord_of", None)
        lord.get("flags", {}).pop("astrologers_rolled_this_campaign", None)
    # Discard 'This Campaign' Events
    state.pop("active_events", None)
    # Advance Calendar
    cal = state["calendar"]
    cur_box = cal["levy_box"]
    if str(cur_box) in cal["boxes"] and "levy" in cal["boxes"][str(cur_box)]["markers"]:
        cal["boxes"][str(cur_box)]["markers"].remove("levy")
    new_box = cur_box + 1
    if new_box <= 16 and (cal.get("end_box") is None or new_box < cal["end_box"]):
        cal["levy_box"] = new_box
        cal["boxes"].setdefault(str(new_box),
            {"cylinders": [], "services": [], "victory": [], "markers": []})
        cal["boxes"][str(new_box)]["markers"].append("levy")
        state["meta"]["turn"] = new_box
        state["meta"]["phase"] = "levy"
        state["meta"]["levy_step"] = "3.1"
        state["meta"]["campaign_step"] = None
        state["meta"]["active_player"] = "guelph"
        state["meta"]["end_substep_done"] = []
        state["meta"]["exhaustion_rolled_this_levy"] = False
        state["meta"].pop("aow_reshuffled_this_levy_guelph", None)
        state["meta"].pop("aow_reshuffled_this_levy_ghibelline", None)
        # Plan stacks reset for next Campaign
        state["plan_stacks"] = {"guelph": [], "ghibelline": []}
    else:
        state["meta"]["phase"] = "victory"
        state["meta"]["game_over"] = True
        g, h = state["vp"].get("guelph", 0), state["vp"].get("ghibelline", 0)
        state["meta"]["winner"] = "guelph" if g > h else ("ghibelline" if h > g else None)
    return {"state_changes": {"reset_done": True}, "rule_citation": "4.9.6"}


_HANDLERS.update({
    "end_grow":          _h_end_grow,
    "end_grow_skip":     _h_end_grow_skip,
    "end_ransom":        _h_end_ransom,
    "end_game_check":    _h_end_game_check,
    "end_repair":        _h_end_repair,
    "end_waste":         _h_end_waste,
    "end_reset":         _h_end_reset,
})


# =====================================================================
# Phase 4: Card effects integration
# =====================================================================
def _h_play_event(state, side, args, rng) -> dict[str, Any]:
    """Play a Held Event card from this side's aow_held list.

    args:
      card_id:  Held Event card to play
      effect_args: dict of card-specific args (target Lord/Locale/etc.)
    """
    cid = args.get("card_id")
    if not cid:
        raise IllegalAction("MISSING_CARD", "play_event requires card_id.", "3.1.3")
    held = state["decks"][side]["aow_held"]
    if cid not in held:
        raise IllegalAction("CARD_NOT_HELD", f"{cid!r} not in {side}'s Held Events.", "3.1.3")
    held.remove(cid)
    state["decks"][side]["aow_discard"].append(cid)
    from . import card_effects as ce
    effect_args = args.get("effect_args", {})
    effect_result = ce.apply_event_effect(state, cid, side, effect_args, rng)
    return {
        "state_changes": {"played": cid, "effect": effect_result},
        "rule_citation": "3.1.3 / per-card",
    }


_HANDLERS["play_event"] = _h_play_event


# =====================================================================
# Phase 4: Capability hooks into existing handlers
# =====================================================================

def _capability_bonus_lordship(state, lord_id: str) -> int:
    """F22 / S22 Tau Company-style Lordship bonus: adds to a Lord's Lordship."""
    from . import card_effects as ce
    bonus = 0
    lord = state["lords"].get(lord_id, {})
    side = lord.get("side")
    for cap in state.get("capabilities_in_play", []):
        hook = ce.CAPABILITY_TRIGGERS.get(cap.get("id"), {})
        if "lordship_bonus_for" in hook and cap.get("side") == side:
            lord_slug = sd.LORD_IDS.get(lord.get("name", ""), "")
            if lord_slug in hook["lordship_bonus_for"]:
                bonus += hook.get("lordship_value", 0)
    return bonus



def _maybe_exhaustion_roll(state, rng) -> None:
    """Scenario F Exhaustion: from Turn 9 onward, roll 1d6 at start of
    each Levy. On 1-3: place End marker in box 16, or slide existing
    End marker 1 box LEFT (lower).
    """
    if state["meta"].get("exhaustion_rolled_this_levy"):
        return
    # Only F has this rule; check scenario.
    if state["meta"]["scenario"] != "F":
        return
    if state["meta"]["turn"] < 9:
        return
    r = rng.roll("exhaustion_F")
    state["meta"]["exhaustion_rolled_this_levy"] = True
    cal = state["calendar"]
    if r.value <= 3:
        if cal.get("end_box") is None:
            cal["end_box"] = 16
        else:
            cal["end_box"] = max(cal["end_box"] - 1, state["meta"]["turn"] + 1)


# =====================================================================
# Levy 3.5 — Full Call to Arms implementation (replaces skip-only stub)
# =====================================================================
LEADING_CITY = {"guelph": "Firenze", "ghibelline": "Siena"}
COMUNE_LORD = {"guelph": "firenze_comune", "ghibelline": "siena_comune"}
COMMANDER_LORD = {"guelph": "firenze", "ghibelline": "siena"}

CTA_SUBSTEPS = ["gather", "commander_arms", "comune", "allies"]


def _cta_trigger_met(state, side: str) -> tuple[bool, str]:
    """Per 3.5: a side may declare CtA if any of:
      (1) VP score ≥ 4 below the other (2.2.5, 5.1)
      (2) Drew a War Event this Levy (3.1.3)
      (3) F23 Treasurers + 2 Coin (Guelphs only)

    SMOKE-Inferno-038: Scenario A 'Preamble' + Scenario E 'Exhaustion'
    skip all CtA. Scenario C 'Maremma War' — only Ghibellines may
    declare in first Levy; skip all other CtA.
    """
    scenario = state["meta"].get("scenario", "")
    # Scenario A and E: no CtA at all
    if scenario in ("A", "E"):
        return False, "scenario_no_cta"
    # Scenario C: only Ghib + only first Levy
    if scenario == "C":
        first_levy = (state["meta"]["turn"] == 6
                      and not state["meta"].get("c_cta_done"))
        if side != "ghibelline" or not first_levy:
            return False, "scenario_c_maremma_war_restriction"
        # Ghib first-Levy: auto-eligible
        return True, "maremma_war_ghib_only"
    own_vp = state["vp"].get(side, 0)
    other = "ghibelline" if side == "guelph" else "guelph"
    other_vp = state["vp"].get(other, 0)
    if other_vp - own_vp >= 4:
        return True, "vp_lag"
    if side in state.get("war_declared_this_levy", []):
        return True, "war_event"
    # Treasurers: F23 in held + Guelph has 2 Coin
    if side == "guelph":
        held = state["decks"]["guelph"]["aow_held"]
        if "F23" in held:
            total_coin = sum(
                l["assets"].get("Coin", 0) for l in state["lords"].values()
                if l["side"] == "guelph" and l["status"] == "mustered"
            )
            if total_coin >= 2:
                return True, "treasurers_available"
    return False, "no_trigger"


def _h_levy_cta_declare(state, side, args, rng) -> dict[str, Any]:
    """3.5: declare Call to Arms for this side. If accepted, both sides
    will go through the 4 sub-steps (Guelph first, then Ghibelline).
    """
    _require_step(state, "3.5")
    eligible, reason = _cta_trigger_met(state, side)
    if not eligible:
        raise IllegalAction(
            "CTA_NOT_ELIGIBLE",
            f"{side} has no CtA trigger: VP={state['vp'].get(side)}, "
            f"other VP={state['vp'].get('ghibelline' if side == 'guelph' else 'guelph')}, "
            f"war_declared={state.get('war_declared_this_levy', [])}.",
            "3.5",
        )
    # Mark CtA active; both sides will run through the 4 substeps.
    state["meta"]["cta_active"] = True
    if state["meta"]["scenario"] == "C" and side == "ghibelline":
        state["meta"]["c_cta_done"] = True
    state["meta"]["cta_substep"] = "gather"
    state["meta"]["cta_sides_done"] = []
    state["meta"]["active_player"] = "guelph"  # Guelphs always go first
    return {
        "state_changes": {"cta_declared_by": side, "trigger": reason},
        "rule_citation": "3.5",
    }


def _advance_cta(state) -> None:
    """Move to next CtA substep or next side, or exit 3.5."""
    side = state["meta"]["active_player"]
    cur_substep = state["meta"].get("cta_substep")
    if cur_substep is None:
        return
    idx = CTA_SUBSTEPS.index(cur_substep)
    if idx + 1 < len(CTA_SUBSTEPS):
        state["meta"]["cta_substep"] = CTA_SUBSTEPS[idx + 1]
        return
    # Done with this side's CtA
    done = set(state["meta"].get("cta_sides_done", []))
    done.add(side)
    state["meta"]["cta_sides_done"] = list(done)
    other = "ghibelline" if side == "guelph" else "guelph"
    if other not in done:
        state["meta"]["active_player"] = other
        state["meta"]["cta_substep"] = "gather"
        return
    # Both sides done — exit CtA and 3.5.
    state["meta"]["cta_active"] = False
    state["meta"]["cta_substep"] = None
    state["meta"]["cta_sides_done"] = []
    from .flow import advance_to_next_side_or_step
    # Force advance past 3.5 → Campaign
    state["meta"]["active_player"] = "ghibelline"  # so advance closes the step
    advance_to_next_side_or_step(state)


def _h_cta_step_skip(state, side, args, rng) -> dict[str, Any]:
    """Skip the current CtA substep for this side."""
    if not state["meta"].get("cta_active"):
        raise IllegalAction("NO_CTA", "CtA not active.", "3.5")
    sub = state["meta"].get("cta_substep")
    _advance_cta(state)
    return {"state_changes": {"skipped_cta_substep": sub}, "rule_citation": "3.5"}


def _h_cta_gather_march(state, side, args, rng) -> dict[str, Any]:
    """3.5.1 GATHER — free March (no Moved/Fought, no Feed). Each Lord
    must end CLOSER to his Leading City. Phase 5: single-Lord per call.

    args:
      lord_id:    Lord doing the free march
      destination: Locale name
      way_type:   road/track
    """
    if state["meta"].get("cta_substep") != "gather":
        raise IllegalAction("WRONG_CTA_STEP", "gather substep only.", "3.5.1")
    lid = args.get("lord_id")
    lord = _require_lord(state, lid, side)
    if lord["status"] != "mustered":
        raise IllegalAction("LORD_NOT_ON_MAP", f"{lid} not on map.", "3.5.1")
    dest_name = args.get("destination")
    if not dest_name or dest_name not in state["locales"]:
        raise IllegalAction("BAD_DEST", f"Unknown destination {dest_name!r}.", "3.5.1")
    cur_loc = lord.get("location")
    if cur_loc is None:
        raise IllegalAction("NO_LOCATION", f"{lid} has no Locale.", "3.5.1")
    # Adjacency check
    way_type = args.get("way_type")
    adj = sd.adjacent_to(cur_loc)
    if way_type:
        if (dest_name, way_type) not in adj:
            raise IllegalAction("BAD_WAY", f"No {way_type} from {cur_loc} to {dest_name}.", "3.5.1")
    else:
        ways = [w for n, w in adj if n == dest_name]
        if not ways:
            raise IllegalAction("NOT_ADJACENT", f"{cur_loc} not adjacent to {dest_name}.", "3.5.1")
        way_type = ways[0]
    # Closer-to-Leading-City check
    leading = LEADING_CITY[side]
    dist_before = _bfs_distance(cur_loc, leading)
    dist_after = _bfs_distance(dest_name, leading)
    if dist_after >= dist_before:
        raise IllegalAction(
            "NOT_CLOSER",
            f"Gather March must end closer to {leading}; "
            f"{cur_loc}->{dest_name} doesn't reduce distance ({dist_before}->{dist_after}).",
            "3.5.1",
        )
    # May NOT enter Locale with Unbesieged/Unbypassed Enemy Lord or un-Ruined Enemy Stronghold
    enemy = "ghibelline" if side == "guelph" else "guelph"
    dest = state["locales"][dest_name]
    for oid in dest.get("lords_present", []):
        olord = state["lords"][oid]
        if olord["side"] == enemy and not olord.get("flags", {}).get("in_stronghold"):
            raise IllegalAction("ENEMY_LORD_AT_DEST", f"{oid} blocks Gather to {dest_name}.", "3.5.1")
    # Enemy Stronghold check: friendly or Ruined OK
    if dest["type"] != "outpost" and not dest.get("ruins"):
        if not _is_friendly_locale(state, dest, side):
            # If a Siege/Bypass already there, OK
            if not dest.get("siege") and not dest.get("bypass"):
                raise IllegalAction("ENEMY_STRONGHOLD", f"{dest_name} un-Ruined enemy stronghold.", "3.5.1")
    # Move (NOT marked Moved/Fought; NO Feed)
    src = state["locales"][cur_loc]
    if lid in src.get("lords_present", []):
        src["lords_present"].remove(lid)
    dest.setdefault("lords_present", []).append(lid)
    lord["location"] = dest_name
    return {
        "state_changes": {"gather_march_from": cur_loc, "to": dest_name,
                          "distance_to_leading_city": dist_after},
        "rule_citation": "3.5.1",
    }


def _bfs_distance(src: str, target: str) -> int:
    """Locale-to-Locale shortest path (any way_type). Returns inf if no path."""
    if src == target:
        return 0
    from collections import deque
    seen = {src}
    queue = deque([(src, 0)])
    while queue:
        cur, d = queue.popleft()
        for nbr, _w in sd.adjacent_to(cur):
            if nbr in seen:
                continue
            if nbr == target:
                return d + 1
            seen.add(nbr)
            queue.append((nbr, d + 1))
    return 999  # unreachable


def _h_cta_commander_arms(state, side, args, rng) -> dict[str, Any]:
    """3.5.2 COMMANDER TO ARMS: optionally Disband Commander (at Service
    Limit semantics, with Comune if on map). Then optionally Muster
    Commander inside Leading City from ANY Calendar box.

    args:
      mode: 'disband_and_remuster' | 'disband_only' | 'muster_only' | 'skip'
    """
    if state["meta"].get("cta_substep") != "commander_arms":
        raise IllegalAction("WRONG_CTA_STEP", "commander_arms substep only.", "3.5.2")
    commander_id = COMMANDER_LORD[side]
    commander = state["lords"][commander_id]
    mode = args.get("mode", "skip")
    log = {"mode": mode}

    if mode in ("disband_and_remuster", "disband_only"):
        if commander["status"] == "mustered":
            # Disband at Service Limit semantics
            levy_box = state["calendar"]["levy_box"]
            _disband_at_service_limit(state, commander_id, levy_box)
            log["disbanded"] = True

    if mode in ("disband_and_remuster", "muster_only"):
        # Muster Commander at Leading City from ANY Calendar box
        if commander["status"] == "on_calendar":
            cur_box = commander.get("calendar_box")
            cal_boxes = state["calendar"]["boxes"]
            if cur_box and str(cur_box) in cal_boxes:
                if commander_id in cal_boxes[str(cur_box)]["cylinders"]:
                    cal_boxes[str(cur_box)]["cylinders"].remove(commander_id)
            commander["status"] = "mustered"
            commander["location"] = LEADING_CITY[side]
            commander["calendar_box"] = None
            sr = commander.get("ratings", {}).get("S", 0)
            new_svc = min(state["meta"]["turn"] + sr, 16)
            commander["service_box"] = new_svc
            cal_boxes.setdefault(str(new_svc),
                {"cylinders": [], "services": [], "victory": [], "markers": []})
            cal_boxes[str(new_svc)]["services"].append(commander_id)
            # Starting Forces/Assets/Vassals
            canonical = commander["name"]
            if canonical in sd.LORDS:
                base = sd.LORDS[canonical]
                commander["forces"] = copy.deepcopy(base.get("forces", {}))
                commander["assets"] = copy.deepcopy(base.get("assets", {}))
                # Vassals re-initialized
                from .scenarios import _init_vassals_for
                commander["vassals"] = _init_vassals_for(base)
            # Wire into Locale
            loc = state["locales"][LEADING_CITY[side]]
            if commander_id not in loc["lords_present"]:
                loc["lords_present"].append(commander_id)
            log["mustered_at"] = LEADING_CITY[side]
    _advance_cta(state)
    return {"state_changes": log, "rule_citation": "3.5.2"}


def _h_cta_comune_setup(state, side, args, rng) -> dict[str, Any]:
    """3.5.3 COMUNE: bring out the Comune mat with its Assets and Special
    Vassals; stack the Comune cylinder under the Commander. Comune must
    end up with at least Carroccio + 1 Sestiere/Terzo.

    args:
      muster_special_vassals: list of vassal names (e.g. ["Carroccio",
                              "Sixth of Porta San Piero"])
    """
    if state["meta"].get("cta_substep") != "comune":
        raise IllegalAction("WRONG_CTA_STEP", "comune substep only.", "3.5.3")
    commander_id = COMMANDER_LORD[side]
    commander = state["lords"][commander_id]
    if (commander["status"] != "mustered"
            or commander.get("location") != LEADING_CITY[side]):
        # Comune step skipped — Commander must be inside Leading City
        _advance_cta(state)
        return {"state_changes": {"comune": "skipped_no_commander_in_leading"},
                "rule_citation": "3.5.3"}
    comune_id = COMUNE_LORD[side]
    comune = state["lords"][comune_id]
    if comune["status"] == "removed":
        _advance_cta(state)
        return {"state_changes": {"comune": "skipped_removed"}, "rule_citation": "3.5.3"}
    # Bring out Comune mat with starting Assets
    canonical = comune["name"]
    base = sd.LORDS.get(canonical, {})
    comune["status"] = "mustered"
    comune["location"] = LEADING_CITY[side]
    comune["assets"] = copy.deepcopy(base.get("assets", {}))
    # Wire into Locale
    loc = state["locales"][LEADING_CITY[side]]
    if comune_id not in loc["lords_present"]:
        loc["lords_present"].append(comune_id)
    # Initialize Vassal list (all Special Vassals, all not on_mat yet)
    from .scenarios import _init_vassals_for
    comune["vassals"] = _init_vassals_for(base)
    # Mark Special Vassals from arg list as on_mat (auto-muster path).
    requested = set(args.get("muster_special_vassals", []) or [])
    if not requested:
        # Default: Carroccio + one Sestiere/Terzo (the minimum)
        requested = {"Carroccio"}
        for v in comune["vassals"]:
            if v.get("special") and "Sixth" in v.get("name", "") or "Terzo" in v.get("name", ""):
                requested.add(v["name"])
                break
    mustered_vassals = []
    for v in comune["vassals"]:
        if v["name"] in requested and v.get("special"):
            v["on_mat"] = True
            v["ready"] = True
            # Add Forces
            for u, c in v.get("forces", {}).items():
                comune["forces"][u] = comune["forces"].get(u, 0) + c
            mustered_vassals.append(v["name"])
    # Validate: must include Carroccio + at least one Sestiere/Terzo
    has_carroccio = "Carroccio" in mustered_vassals
    has_sub = any(("Sixth" in n) or ("Terzo" in n) for n in mustered_vassals)
    if not (has_carroccio and has_sub):
        # Roll back — Comune cannot be set with insufficient Special Vassals
        comune["status"] = "in_levy_pool"
        comune["location"] = None
        comune["vassals"] = []
        comune["forces"] = {}
        comune["assets"] = {}
        if comune_id in loc["lords_present"]:
            loc["lords_present"].remove(comune_id)
        raise IllegalAction(
            "COMUNE_MIN_NOT_MET",
            "Comune must include Carroccio + at least one Sestiere/Terzo.",
            "3.5.3",
        )
    _advance_cta(state)
    return {
        "state_changes": {"comune_setup": True, "mustered_vassals": mustered_vassals},
        "rule_citation": "3.5.3",
    }


def _h_cta_allies(state, side, args, rng) -> dict[str, Any]:
    """3.5.4 ALLIES: EITHER (not both):
      mode='extra_muster': conduct extra Muster segment for one Lord
                           (= his Lordship in Levy actions, per 3.4).
      mode='auto_muster':  Muster any one non-Commander Lord automatically
                           (no Fealty roll, no Levy action).

    args:
      mode:            "extra_muster" | "auto_muster"
      target_lord_id:  Lord ID (for auto_muster) or the Mustered Lord
                       getting the extra segment.
      target_seat:     for auto_muster, which Seat to place at.
    """
    if state["meta"].get("cta_substep") != "allies":
        raise IllegalAction("WRONG_CTA_STEP", "allies substep only.", "3.5.4")
    mode = args.get("mode", "skip")
    target = args.get("target_lord_id")
    log = {"mode": mode}
    if mode == "auto_muster":
        if not target or target not in state["lords"]:
            raise IllegalAction("MISSING_TARGET", "auto_muster needs target_lord_id.", "3.5.4")
        tlord = state["lords"][target]
        if tlord["side"] != side:
            raise IllegalAction("WRONG_SIDE", f"{target} not on {side}.", "3.5.4")
        if tlord.get("commander"):
            raise IllegalAction("COMMANDER_NOT_ELIGIBLE", "Auto-Muster excludes Commander.", "3.5.4")
        if tlord["status"] != "on_calendar":
            raise IllegalAction("NOT_ON_CALENDAR", f"{target} not on Calendar.", "3.5.4")
        seat = args.get("target_seat")
        if seat not in tlord.get("seats", []):
            raise IllegalAction("BAD_SEAT", f"{target}'s seats: {tlord.get('seats')}.", "3.5.4")
        # Auto-Muster (no Fealty roll, no action cost)
        cur_box = tlord.get("calendar_box")
        cal_boxes = state["calendar"]["boxes"]
        if cur_box and str(cur_box) in cal_boxes:
            if target in cal_boxes[str(cur_box)]["cylinders"]:
                cal_boxes[str(cur_box)]["cylinders"].remove(target)
        tlord["status"] = "mustered"
        tlord["location"] = seat
        tlord["calendar_box"] = None
        sr = tlord.get("ratings", {}).get("S", 0)
        new_svc = min(state["meta"]["turn"] + sr, 16)
        tlord["service_box"] = new_svc
        cal_boxes.setdefault(str(new_svc),
            {"cylinders": [], "services": [], "victory": [], "markers": []})
        cal_boxes[str(new_svc)]["services"].append(target)
        canonical = tlord["name"]
        base = sd.LORDS.get(canonical, {})
        tlord["forces"] = copy.deepcopy(base.get("forces", {}))
        tlord["assets"] = copy.deepcopy(base.get("assets", {}))
        from .scenarios import _init_vassals_for
        tlord["vassals"] = _init_vassals_for(base)
        loc = state["locales"][seat]
        if target not in loc["lords_present"]:
            loc["lords_present"].append(target)
        log["auto_mustered"] = target
    elif mode == "extra_muster":
        # Grant the named Lord an extra Lordship segment by resetting
        # his lordship_used counter (Phase 5 will respect this).
        if not target or target not in state["lords"]:
            raise IllegalAction("MISSING_TARGET", "extra_muster needs target_lord_id.", "3.5.4")
        tlord = state["lords"][target]
        if tlord["side"] != side:
            raise IllegalAction("WRONG_SIDE", f"{target} not on {side}.", "3.5.4")
        if tlord["status"] != "mustered":
            raise IllegalAction("NOT_MUSTERED", f"{target} not Mustered.", "3.5.4")
        tlord.setdefault("flags", {})["lordship_used"] = 0
        log["extra_segment_for"] = target
    # else: skip
    _advance_cta(state)
    return {"state_changes": log, "rule_citation": "3.5.4"}


# Register CtA handlers
_HANDLERS.update({
    "levy_cta_declare":     _h_levy_cta_declare,
    "cta_step_skip":        _h_cta_step_skip,
    "cta_gather_march":     _h_cta_gather_march,
    "cta_commander_arms":   _h_cta_commander_arms,
    "cta_comune_setup":     _h_cta_comune_setup,
    "cta_allies":           _h_cta_allies,
})



def _compute_final_vp(state) -> tuple[float, float]:
    """Recompute end-game VP from map markers per 5.1, applying:
      - Scenario E 'Resistance': double Guelph VP except Ravaged.
      - Scenario C 'Alliance Treaty' if S22 Manfredi Capability in play:
        +3 Ghibelline VP.
    """
    scenario = state["meta"].get("scenario", "")
    # 5.0 VP sources: Allegiance markers (+1 each), Ruins (+1/2), Captured enemy
    # Carroccio (+2). Ravaged (+1/2) is bucketed SEPARATELY because Scenario E
    # doubles every Guelph VP EXCEPT Ravaged.
    # SMOKE-Inferno-053: Captured Carroccio is now tallied here. It is NOT a map
    # marker, so it is read from state["captured_carroccio_for_side"], which the
    # Battle and Storm-Sack Spoils steps now persist (previously never written,
    # so every Carroccio's +2 VP was silently dropped at the end-game recompute).
    vp = {"guelph": 0.0, "ghibelline": 0.0}
    ravaged_vp = {"guelph": 0.0, "ghibelline": 0.0}
    for loc in state["locales"].values():
        for m in loc.get("current_allegiance", []) or []:
            mside = m.get("side")
            if mside in vp:
                vp[mside] += m.get("value", 1)
        if loc.get("ruins"):
            # Marker color is the OPPOSITE of printed Allegiance; that color's
            # side scores it.
            vp["guelph" if loc["ruins"] == "gold" else "ghibelline"] += 0.5
        if loc.get("ravaged"):
            ravaged_vp["guelph" if loc["ravaged"] == "gold" else "ghibelline"] += 0.5
    # Captured Carroccio +2 each (5.0).
    for sd_side in ("guelph", "ghibelline"):
        cc = state.get("captured_carroccio_for_side", {}).get(sd_side, 0)
        vp[sd_side] += cc * 2
    # Scenario E 'Resistance': double Guelph VP except Ravaged.
    if scenario == "E":
        vp["guelph"] *= 2
    # Add Ravaged (not doubled).
    for sd_side in vp:
        vp[sd_side] += ravaged_vp[sd_side]
    # Scenario C 'Alliance Treaty': +3 Ghib if S22 Manfredi Capability in play.
    if scenario == "C":
        if any(c.get("id") == "S22" for c in state.get("capabilities_in_play", [])):
            vp["ghibelline"] += 3
    # Clamp.
    vp["guelph"] = max(0, min(vp["guelph"], 17.5))
    vp["ghibelline"] = max(0, min(vp["ghibelline"], 17.5))
    return vp["guelph"], vp["ghibelline"]



def _maybe_reshuffle_aow_deck(state, side: str) -> None:
    """3.1.1: at start of each Levy, shuffle unused AoW cards into a
    fresh draw deck for this side. Exclude Held Events and Capabilities
    in play. The flag is per-side-per-Levy and cleared on next Levy entry.
    """
    flag = f"aow_reshuffled_this_levy_{side}"
    if state["meta"].get(flag):
        return
    deck = state["decks"][side]
    held = set(deck.get("aow_held") or [])
    in_play = {c["id"] for c in state.get("capabilities_in_play", [])
               if c.get("side") == side}
    from . import card_data as cd
    all_side_cards = {c["id"] for c in
                      (cd.GUELPH_CARDS if side == "guelph" else cd.GHIBELLINE_CARDS)}
    available = sorted(all_side_cards - held - in_play)
    deck["aow_deck"] = available
    deck["aow_discard"] = []
    state["meta"][flag] = True



def _h_cmd_play_ambush(state, side, args, rng) -> dict[str, Any]:
    """F1/S1 Ambush consumption — during an Approach where the Enemy is
    declaring responses, the side with a pending Ambush modifier forces
    one Inactive Enemy Lord to NOT Avoid (must Stand or Withdraw).

    SMOKE-Inferno-042. The attacking side plays this BEFORE the targeted
    Lord submits an Avoid; it sets ambush_forced on that Lord.

    args:
      target_lord_id: the Inactive Enemy Lord to pin.
    """
    # Find a pending Ambush modifier for this side.
    pend = None
    for i, m in enumerate(state.get("approach_modifiers_pending", []) or []):
        if m.get("effect") == "ambush_force_one_stand" and m.get("side") == side:
            pend = i
            break
    if pend is None:
        raise IllegalAction("NO_AMBUSH", f"No pending Ambush modifier for {side}.", "F1/S1")
    target = args.get("target_lord_id")
    if not target or target not in state["lords"]:
        raise IllegalAction("BAD_TARGET", "Ambush needs a target_lord_id.", "F1/S1")
    # Target must have an open approach_response pending owed by the enemy.
    enemy = "ghibelline" if side == "guelph" else "guelph"
    open_pending = [pp for pp in state.get("pending", [])
                    if pp.get("type") == "approach_response"
                    and pp["info"].get("lord_id") == target
                    and pp.get("side") == enemy]
    if not open_pending:
        raise IllegalAction(
            "NO_OPEN_RESPONSE",
            f"{target} has no open approach_response to pin with Ambush.",
            "F1/S1",
        )
    state["lords"][target].setdefault("flags", {})["ambush_forced"] = True
    state["approach_modifiers_pending"].pop(pend)
    return {
        "state_changes": {"ambush_pinned": target},
        "rule_citation": "F1/S1 / 4.3.4",
    }


_HANDLERS["cmd_play_ambush"] = _h_cmd_play_ambush


# Revolt-resolution actions (1.4.2 / 1.4.4) — registered last.
_HANDLERS.update({
    "cmd_resolve_revolt": _h_cmd_resolve_revolt,
    "cmd_resolve_exiles": _h_cmd_resolve_exiles,
})
