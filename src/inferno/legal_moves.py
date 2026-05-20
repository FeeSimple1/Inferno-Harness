"""Legal-moves enumeration.

Per BRIEF: the primary interface an LLM uses to decide what to do.
Returns the valid actions for state.meta.active_player at the current
phase/step, each entry with action grammar, costs, prerequisites met,
and a brief description with rule citation.

Per CROSS_PROJECT_LESSONS.md §1 ("Legal-moves over-enumeration is
endemic — audit it systematically"):
  - Mirror each handler's pre-checks into the enumerator so the
    consumer never sees a phantom-legal move.
  - Wrap static-data lookups in try/except. Bias toward "miss a legal
    move" over "offer a phantom-legal move". The consumer (agent,
    LLM, UI) trusts the palette.
  - Source-marker comments (`# SMOKE-Inferno-NNN`) survive refactors,
    paired with one-line regression tests that assert the marker
    is still present.

Per §2 ("Arg-shape/semantic mismatch"): tests/test_round_trip.py runs
a sweep that replays every enumerated move through dispatch() and
asserts no IllegalAction codes come back.
"""

from __future__ import annotations

from typing import Any

from . import static_data as sd
from .flow import current_campaign_step, current_side, current_step


def _enum_pending_revolts(state):
    """If a Revolt-table choice (Submission / Rebellion fallback) or an Exiles
    slide is pending, return ONLY the resolution moves (they pause everything
    else, per 1.4.2/1.4.4). Returns None when nothing is pending."""
    for batch in state.get("pending_revolts", []):
        dec = batch.get("decision")
        if not dec:
            continue
        side = dec["side"]
        moves = [{
            "action": "cmd_resolve_revolt", "side": side,
            "args": {"choice": cand},
            "description": f"Revolt {dec['kind']}: flip {cand}.",
            "rule_citation": "1.4.2",
        } for cand in dec.get("candidates", [])]
        if moves:
            return moves
    pend_ex = state.get("pending_exiles", [])
    if pend_ex:
        head = pend_ex[0]
        side = head["side"]
        cands = head.get("candidates", [])
        moves = [{
            "action": "cmd_resolve_exiles", "side": side,
            "args": {"slides": [{"lord_id": c["lord_id"], "kind": c["kind"]}]},
            "description": f"Exiles: slide {c['lord_id']} ({c['kind']}).",
            "rule_citation": "1.4.4",
        } for c in cands]
        # Always allow slimming to zero slides (the side may decline if no marker
        # is worth moving / none available).
        moves.append({
            "action": "cmd_resolve_exiles", "side": side, "args": {"slides": []},
            "description": "Exiles: slide nothing.", "rule_citation": "1.4.4",
        })
        return moves
    return None


def _enum_pending_fpd(state):
    """SMOKE-Inferno-057: when the FPD Pay sub-step (4.8.2) is parked, surface
    ONLY its moves (deadlock guard) for the side whose segment is active: end
    the segment, plus the self-Coin Pays the handler will accept. `pay_done` is
    listed first so a greedy consumer cleanly declines and proceeds to Disband.
    Returns None when no FPD Pay is pending."""
    pend = state.get("pending_fpd")
    if not pend or pend.get("step") != "pay":
        return None
    side = pend["side"]
    from . import actions as _actions
    moves = [{
        "action": "cmd_fpd_pay_done", "side": side, "args": {},
        "description": f"{side} ends its FPD Pay sub-step.",
        "rule_citation": "4.8.2",
    }]
    for pay in _actions._fpd_legal_pays(state, side):
        moves.append({
            "action": "cmd_fpd_pay", "side": side, "args": pay,
            "description": f"FPD Pay: {pay['from_lord_id']} shifts Service +1 box (Coin).",
            "rule_citation": "4.8.2",
        })
    return moves


def enumerate_legal(state: dict[str, Any]) -> list[dict[str, Any]]:
    # Pending decisions take precedence over phase enumeration (per BRIEF
    # "Non-Combat Pending Decisions"). If an approach_response is pending
    # for the active side, only that response is legal.
    pendings = state.get("pending") or []
    for p in pendings:
        if p.get("type") == "approach_response" and p.get("side") == state["meta"].get("active_player"):
            return _enum_approach_response(state, p)
    # Revolt-table decisions (1.4.2) and Exiles (1.4.4) MUST be resolved before
    # anything else — they pause the triggering action. Surface only those.
    rev = _enum_pending_revolts(state)
    if rev is not None:
        return rev
    # FPD Pay sub-step (4.8.2) pauses everything else until both sides finish.
    fpd = _enum_pending_fpd(state)
    if fpd is not None:
        return fpd
    phase = state["meta"].get("phase")
    if phase == "levy":
        return _enum_levy(state)
    if phase == "campaign":
        return _enum_campaign(state)
    if phase == "victory":
        return []
    return [{
        "action": "<unknown_phase>",
        "description": f"Unknown phase: {phase}",
        "rule_citation": None,
    }]


def _enum_levy(state) -> list[dict[str, Any]]:
    step = current_step(state)
    side = current_side(state)
    if step == "3.1":
        return _enum_aow(state, side)
    if step == "3.2":
        return _enum_pay(state, side)
    if step == "3.3":
        return _enum_disband(state, side)
    if step == "3.4":
        return _enum_muster(state, side)
    if step == "3.5":
        return _enum_cta(state, side)
    return [{
        "action": "<unknown_step>",
        "description": f"Unknown Levy step: {step}",
        "rule_citation": None,
    }]


def _enum_aow(state, side) -> list[dict[str, Any]]:
    return [{
        "action": "levy_aow_draw",
        "side": side,
        "description": "Draw 2 AoW cards; first Levy deploys as Capabilities, later Levies implement Events.",
        "rule_citation": "3.1.2 / 3.1.3",
    }]


def _enum_pay(state, side) -> list[dict[str, Any]]:
    moves: list[dict[str, Any]] = []
    own_mustered = _own_lords(state, side, status="mustered")
    for from_lid, from_lord in own_mustered.items():
        if from_lord["assets"].get("Coin", 0) > 0:
            same_loc = [
                (tlid, t) for tlid, t in own_mustered.items()
                if t.get("location") == from_lord.get("location")
            ]
            for tlid, t in same_loc:
                rate = 2 if t.get("podesta") else 1
                max_boxes = from_lord["assets"]["Coin"] // rate
                if max_boxes >= 1 and t.get("service_box") is not None:
                    moves.append({
                        "action": "levy_pay",
                        "side": side,
                        "args": {"from_lord_id": from_lid, "target_lord_id": tlid,
                                 "asset": "Coin", "amount": 1},
                        "description": f"{from_lid} pays {rate} Coin to shift {tlid}'s Service marker right 1 box.",
                        "rule_citation": "3.2.1",
                    })
        if from_lord["assets"].get("Loot", 0) > 0:
            loc = state["locales"].get(from_lord.get("location") or "")
            if loc and not loc.get("siege"):
                for tlid, t in own_mustered.items():
                    if t.get("location") == from_lord.get("location") and t.get("service_box") is not None:
                        rate = 2 if t.get("podesta") else 1
                        if from_lord["assets"]["Loot"] >= rate:
                            moves.append({
                                "action": "levy_pay",
                                "side": side,
                                "args": {"from_lord_id": from_lid, "target_lord_id": tlid,
                                         "asset": "Loot", "amount": 1},
                                "description": f"{from_lid} pays {rate} Loot to shift {tlid}'s Service marker right 1 box.",
                                "rule_citation": "3.2.2",
                            })
    moves.append({
        "action": "levy_pay_done", "side": side,
        "description": "End Pay segment for this side.",
        "rule_citation": "3.2",
    })
    return moves


def _enum_disband(state, side) -> list[dict[str, Any]]:
    """SMOKE-Inferno-026 (Tier-2 sweep): a Lord with service_box=None
    is either off-left (Beyond Service Limit; disbandable) or off-right
    (well-served, NOT disbandable). The check disambiguates via the
    off_*_service lists rather than treating None == 0."""
    levy_box = state["calendar"]["levy_box"]
    off_left_set = set(state["calendar"].get("off_left_service") or [])
    disbandable = []
    for lid, l in state["lords"].items():
        if l["side"] != side or l["status"] != "mustered":
            continue
        svc = l.get("service_box")
        if svc is None:
            if lid in off_left_set:
                disbandable.append(lid)  # off-left = Beyond Service
            # off-right or simply unset: not disbandable
        elif svc <= levy_box:
            disbandable.append(lid)
    moves: list[dict[str, Any]] = []
    if disbandable:
        moves.append({
            "action": "levy_disband", "side": side,
            "description": f"Auto-process all Disbandable Lords for {side}: {disbandable}",
            "rule_citation": "3.3.1 / 3.3.2 (Errata)",
        })
    moves.append({
        "action": "levy_disband_done", "side": side,
        "description": "End Disband segment for this side.",
        "rule_citation": "3.3",
    })
    return moves


def _enum_muster(state, side) -> list[dict[str, Any]]:
    moves: list[dict[str, Any]] = []
    own_mustered = _own_lords(state, side, status="mustered")
    own_on_calendar = _own_lords(state, side, status="on_calendar")
    levy_box = state["calendar"]["levy_box"]

    for lid, lord in own_mustered.items():
        # SMOKE-Inferno-028: newly-Mustered Lords cannot act this segment (3.4.1).
        if lord.get("flags", {}).get("just_mustered_this_segment"):
            continue
        # Lordship gate (3.4): skip Lords who have used all their Lordship.
        rating = lord.get("ratings", {}).get("L", 0)
        used = lord.get("flags", {}).get("lordship_used", 0)
        bonus = lord.get("flags", {}).get("lordship_bonus_pending", 0)
        if used >= rating + bonus:
            continue
        for tlid, tlord in own_on_calendar.items():
            if (tlord.get("calendar_box") or 0) <= levy_box:
                for seat in tlord.get("seats", []):
                    moves.append({
                        "action": "levy_muster_lord", "side": side,
                        "args": {"muster_lord_id": lid, "target_lord_id": tlid,
                                 "target_seat": seat},
                        "description": f"{lid} attempts Fealty roll on {tlid} (F:{tlord['ratings'].get('F','-')}) at {seat}.",
                        "rule_citation": "3.4.1",
                    })
        for v in lord.get("vassals", []):
            if v.get("ready") and not v.get("special"):
                moves.append({
                    "action": "levy_muster_vassal", "side": side,
                    "args": {"lord_id": lid, "vassal": v["name"]},
                    "description": f"{lid} Musters {v['name']}.",
                    "rule_citation": "3.4.2",
                })
        moves.append({
            "action": "levy_muster_transport", "side": side,
            "args": {"lord_id": lid, "kind": "Cart"},
            "description": f"{lid} levies 1 Cart.",
            "rule_citation": "3.4.3",
        })
        if lord["name"] == "Pisa Podestà":
            moves.append({
                "action": "levy_muster_transport", "side": side,
                "args": {"lord_id": lid, "kind": "Ship"},
                "description": f"{lid} levies 1 Ship (Pisa only).",
                "rule_citation": "3.4.3 / 4.7.3",
            })
        if state["decks"][side]["aow_deck"]:
            moves.append({
                "action": "levy_muster_capability", "side": side,
                "args": {"lord_id": lid, "scope": "side_wide"},
                "description": f"{lid} levies 1 Capability for the side.",
                "rule_citation": "3.4.4",
            })
            if len(lord.get("capabilities", [])) < 2:
                moves.append({
                    "action": "levy_muster_capability", "side": side,
                    "args": {"lord_id": lid, "scope": "this_lord"},
                    "description": f"{lid} levies 1 'This Lord' Capability (max 2).",
                    "rule_citation": "3.4.4",
                })
    moves.append({
        "action": "levy_muster_done", "side": side,
        "description": "End Muster segment for this side.",
        "rule_citation": "3.4",
    })
    return moves


def _enum_cta(state, side) -> list[dict[str, Any]]:
    return [{
        "action": "levy_cta_skip", "side": side,
        "description": "Decline Call to Arms (Phase 2 stub; full CtA in Phase 2b).",
        "rule_citation": "3.5",
    }]


# =====================================================================
# CAMPAIGN PHASE
# =====================================================================
def _enum_campaign(state) -> list[dict[str, Any]]:
    step = current_campaign_step(state)
    side = current_side(state)
    if step == "capability_discard":
        return _enum_capability_discard(state, side)
    if step == "plan":
        return _enum_plan(state, side)
    if step == "command_phase":
        return _enum_command_phase(state, side)
    if step == "end_campaign":
        return _enum_end_campaign(state, side)
    return [{
        "action": "<unknown_campaign_step>",
        "description": f"Unknown campaign step: {step}",
        "rule_citation": None,
    }]


def _enum_capability_discard(state, side) -> list[dict[str, Any]]:
    moves: list[dict[str, Any]] = []
    side_caps = [c for c in state["capabilities_in_play"]
                 if c.get("side") == side and c.get("scope") == "side_wide"]
    own_mustered_count = sum(
        1 for l in state["lords"].values()
        if l["side"] == side and l["status"] == "mustered" and not l.get("comune_of")
    )
    excess = len(side_caps) - own_mustered_count
    if excess > 0:
        for c in side_caps:
            moves.append({
                "action": "campaign_discard_capability", "side": side,
                "args": {"card_id": c["id"]},
                "description": f"Discard side-wide Capability {c['id']} ({c.get('name', '')}). Excess remaining: {excess}.",
                "rule_citation": "4.0 STEP A",
            })
    else:
        moves.append({
            "action": "campaign_discard_done", "side": side,
            "description": f"No excess Capabilities; advance.",
            "rule_citation": "4.0 STEP A",
        })
    return moves


def _enum_plan(state, side) -> list[dict[str, Any]]:
    moves: list[dict[str, Any]] = []
    stack = state["plan_stacks"][side]
    # Determine target Plan size from Season; allow add until size reached.
    # SMOKE-Inferno-002: Plan size gate from SEASON_BY_BOX/PLAN_SIZE_BY_SEASON.
    try:
        turn = state["meta"]["turn"]
        season = sd.SEASON_BY_BOX.get(turn, "winter")
        target_size = sd.PLAN_SIZE_BY_SEASON.get(season, 4)
    except (KeyError, AttributeError):
        target_size = 4
    if len(stack) < target_size:
        # Offer Pass card always
        moves.append({
            "action": "plan_add_card", "side": side,
            "args": {"card_id": "PASS"},
            "description": "Add Pass card to Plan.",
            "rule_citation": "4.1.1",
        })
        # Offer each Command card in deck not already in plan
        for cid in state["decks"][side]["command_deck"]:
            if stack.count(cid) == 0:
                kind = "Treachery" if cid.startswith("treachery_") else "Command"
                moves.append({
                    "action": "plan_add_card", "side": side,
                    "args": {"card_id": cid},
                    "description": f"Add {kind} card {cid} to Plan.",
                    "rule_citation": "4.1.1",
                })
    elif len(stack) == target_size:
        moves.append({
            "action": "plan_done", "side": side,
            "description": f"Declare Plan complete ({target_size} cards for {sd.SEASON_BY_BOX.get(state['meta']['turn'])!r}).",
            "rule_citation": "4.1.2",
        })
    # SMOKE-Inferno-017: Lieutenants (4.1.3) — pair eligible Lords at same Locale.
    try:
        own_mustered = _own_lords(state, side, status="mustered")
        by_loc = {}
        for lid_l, l_ in own_mustered.items():
            if l_.get("commander") or l_.get("comune_of"):
                continue
            if l_.get("flags", {}).get("has_lower_lord") or l_.get("flags", {}).get("lower_lord_of"):
                continue
            by_loc.setdefault(l_.get("location"), []).append(lid_l)
        for loc_name, lords in by_loc.items():
            if len(lords) < 2:
                continue
            for i, lt in enumerate(lords):
                for ll in lords[i+1:]:
                    moves.append({
                        "action": "plan_attach_lieutenant", "side": side,
                        "args": {"lieutenant": lt, "lower_lord": ll},
                        "description": f"Stack {ll} under {lt} at {loc_name} (Lieutenant/Lower Lord).",
                        "rule_citation": "4.1.3",
                    })
    except (KeyError, AttributeError, TypeError):
        pass
    return moves


def _enum_command_phase(state, side) -> list[dict[str, Any]]:
    # If no Lord is currently active, the only legal action is to reveal the next card.
    if state.get("current_lord_id") is None:
        # Determine whether this side has more cards to flip.
        if state["plan_stacks"][side]:
            return [{
                "action": "command_reveal", "side": side,
                "description": f"Reveal top card of {side}'s Plan stack ({len(state['plan_stacks'][side])} remaining).",
                "rule_citation": "4.2",
            }]
        # This side's stack is empty; the other side may still have cards.
        other = "ghibelline" if side == "guelph" else "guelph"
        if state["plan_stacks"][other]:
            # Phase 3a's command_reveal handles the "skip empty side" advance.
            return [{
                "action": "command_reveal", "side": side,
                "description": f"{side}'s stack empty; pass turn (other side has {len(state['plan_stacks'][other])} cards).",
                "rule_citation": "4.2",
            }]
        # Both stacks empty.
        return [{
            "action": "command_reveal", "side": side,
            "description": "Both Plan stacks empty; advance to end_campaign.",
            "rule_citation": "4.2",
        }]

    # A Lord is active; enumerate the action menu.
    lid = state["current_lord_id"]
    lord = state["lords"].get(lid)
    if lord is None or lord["side"] != side:
        # Shouldn't happen, but be defensive.
        return [{"action": "cmd_end_card", "side": side, "args": {"lord_id": lid},
                 "description": "End card (inconsistent state).", "rule_citation": "4.2"}]
    actions_remaining = state.get("actions_remaining") or 0
    moves: list[dict[str, Any]] = []
    loc = state["locales"].get(lord.get("location") or "")
    # SMOKE-Inferno-003: pre-check Tax — Lord at Seat, Unbesieged. See CROSS_PROJECT_LESSONS §1.
    tax_ok = False
    try:
        if loc and not loc.get("siege") and lord.get("location") in lord.get("seats", []):
            tax_ok = True
    except (KeyError, AttributeError):
        tax_ok = False
    if tax_ok:
        moves.append({
            "action": "cmd_tax", "side": side, "args": {"lord_id": lid},
            "description": f"{lid} Taxes at {lord['location']} (+{2 if lord.get('podesta') else 1} Coin; entire card).",
            "rule_citation": "4.7.4",
        })
    # SMOKE-Inferno-004: pre-check Forage — Locale not Ravaged, not Besieged, Season check.
    # SMOKE-Inferno-051: "Besieged" uses the Size-threshold predicate (besieging
    # Enemy Lords >= Stronghold Size), shared with the handler.
    forage_ok = False
    forage_reason = ""
    try:
        if loc and not loc.get("ravaged") and not sd.forage_besieged_block(state, loc, side):
            season = sd.SEASON_BY_BOX.get(state["meta"]["turn"], "winter")
            friendly_stronghold = _is_friendly_stronghold_quiet(state, loc, side)
            if friendly_stronghold or season != "winter":
                forage_ok = True
                forage_reason = "auto" if friendly_stronghold or season == "summer" else "die"
    except (KeyError, AttributeError):
        forage_ok = False
    if forage_ok and actions_remaining >= 1:
        moves.append({
            "action": "cmd_forage", "side": side, "args": {"lord_id": lid},
            "description": f"{lid} Forages at {lord.get('location')} ({forage_reason}).",
            "rule_citation": "4.7.1",
        })
    # SMOKE-Inferno-005: pre-check Ravage — Enemy-aligned, not Ravaged, not Friendly. (CROSS_PROJECT_LESSONS §1 cites SMOKE-122 in Nevsky.)
    for target_name in _ravage_candidates(state, lord, side):
        target = state["locales"][target_name]
        cost = 2 if target["type"] in ("town", "city") else 1
        if actions_remaining >= cost:
            moves.append({
                "action": "cmd_ravage", "side": side,
                "args": {"lord_id": lid, "target_locale": target_name},
                "description": f"{lid} Ravages {target_name} ({target['type']}; costs {cost} actions).",
                "rule_citation": "4.7.2",
            })
    # SMOKE-Inferno-006: Supply pre-check — at own Seat (Phase 3a simplified).
    try:
        if (lord.get("location") in lord.get("seats", []) and
                loc and not loc.get("ruins") and actions_remaining >= 1):
            moves.append({
                "action": "cmd_supply", "side": side, "args": {"lord_id": lid},
                "description": f"{lid} Supplies at own Seat {lord['location']}.",
                "rule_citation": "4.6",
            })
    except (KeyError, AttributeError):
        pass
    # SMOKE-Inferno-007: Sail pre-check — Pisa, Port, non-Winter, dest is friendly Port.
    if lord["name"] == "Pisa Podestà":
        try:
            season = sd.SEASON_BY_BOX.get(state["meta"]["turn"], "winter")
            if (season != "winter" and loc and loc.get("port") and not loc.get("siege")):
                for dest_name, dest in state["locales"].items():
                    if dest_name == lord.get("location"):
                        continue
                    if dest.get("port") and _is_friendly_locale_quiet(state, dest, side):
                        moves.append({
                            "action": "cmd_sail", "side": side,
                            "args": {"lord_id": lid, "dest_locale": dest_name},
                            "description": f"{lid} Sails from {lord['location']} to {dest_name} (entire card).",
                            "rule_citation": "4.7.3",
                        })
        except (KeyError, AttributeError):
            pass
    # SMOKE-Inferno-010: cmd_march pre-checks — adjacency, action cost, Laden.
    try:
        cur_loc = lord.get("location")
        if cur_loc:
            for neighbour, way_type in sd.adjacent_to(cur_loc):
                # Skip Outposts unless this Lord has it as a Seat (1.3.1).
                dest = state["locales"].get(neighbour, {})
                if dest.get("type") == "outpost" and neighbour not in lord.get("seats", []):
                    continue
                # Cost estimation: 0 if Unladen first-March on road, 1 normal, 2 Laden.
                carts = lord["assets"].get("Cart", 0)
                prov = lord["assets"].get("Provender", 0)
                loot = lord["assets"].get("Loot", 0)
                laden = loot > 0 or (way_type == "track" and prov > carts) or (way_type == "road" and prov > carts and loot > 0)
                first_march = not lord.get("flags", {}).get("first_march_used_this_card", False)
                cost = 2 if laden else (0 if (first_march and way_type == "road") else 1)
                if cost <= actions_remaining:
                    moves.append({
                        "action": "cmd_march", "side": side,
                        "args": {"lord_id": lid, "destination": neighbour, "way_type": way_type},
                        "description": f"{lid} Marches to {neighbour} via {way_type} ({cost} actions).",
                        "rule_citation": "4.3",
                    })
    except (KeyError, AttributeError, TypeError):
        pass

    # SMOKE-Inferno-013: Besiege/Bypass mandatory at Enemy Stronghold (4.3.5).
    try:
        if loc and not loc.get("ruins") and loc["type"] != "outpost":
            # Need: side has Lord here outside, enemy Stronghold (not currently friendly),
            # no Siege/Bypass markers yet (otherwise an arrived-later branch applies).
            is_enemy = not _is_friendly_locale_quiet(state, loc, side)
            outside = not lord.get("flags", {}).get("in_stronghold")
            if (is_enemy and outside and not loc.get("siege") and not loc.get("bypass")
                    and actions_remaining >= 0):
                for choice in ("besiege", "bypass"):
                    moves.append({
                        "action": "besiege_or_bypass", "side": side,
                        "args": {"lord_id": lid, "choice": choice},
                        "description": f"{lid} {choice}s Enemy {loc['type']} at {lord['location']}.",
                        "rule_citation": "4.3.5",
                    })
    except (KeyError, AttributeError, TypeError):
        pass
    # SMOKE-Inferno-014: cmd_siege when own side has Siege at this Locale (4.5.1).
    try:
        own_sieges = [s for s in (loc.get("siege") or []) if s.get("side") == side]
        if (own_sieges and not lord.get("flags", {}).get("in_stronghold")
                and actions_remaining >= 1):
            moves.append({
                "action": "cmd_siege", "side": side, "args": {"lord_id": lid},
                "description": f"{lid} pursues Siege at {lord['location']} (entire card).",
                "rule_citation": "4.5.1",
            })
            # Storm if at least 1 Siege marker
            moves.append({
                "action": "cmd_storm", "side": side, "args": {"lord_id": lid},
                "description": f"{lid} Storms {lord['location']} ({sum(s.get('count',1) for s in own_sieges)} Siege markers).",
                "rule_citation": "4.5.2",
            })
    except (KeyError, AttributeError, TypeError):
        pass
    # SMOKE-Inferno-015: cmd_sally when Besieged inside (4.5.3).
    try:
        if lord.get("flags", {}).get("in_stronghold") and loc and loc.get("siege"):
            moves.append({
                "action": "cmd_sally", "side": side, "args": {"lord_id": lid},
                "description": f"{lid} Sallies from {lord['location']}.",
                "rule_citation": "4.5.3",
            })
    except (KeyError, AttributeError, TypeError):
        pass

    # SMOKE-Inferno-016: Bypass-state moves (4.3.6) — Depart/Encamp; Sortie if inside.
    try:
        if lord.get("flags", {}).get("bypassing") and actions_remaining >= 1:
            # Encamp is always available with 1 action
            moves.append({
                "action": "cmd_encamp", "side": side, "args": {"lord_id": lid},
                "description": f"{lid} Encamps at {lord['flags']['bypassing']} (1 action; ends card).",
                "rule_citation": "4.3.6",
            })
            # Depart: enumerated via cmd_march above (with bypassing flag)
        if lord.get("flags", {}).get("in_stronghold") and loc and loc.get("bypass") and actions_remaining >= 1:
            moves.append({
                "action": "cmd_sortie", "side": side, "args": {"lord_id": lid},
                "description": f"{lid} Sorties from {lord['location']}.",
                "rule_citation": "4.3.6",
            })
    except (KeyError, AttributeError, TypeError):
        pass

    # Pass is always available
    if actions_remaining >= 1:
        moves.append({
            "action": "cmd_pass", "side": side,
            "args": {"lord_id": lid, "count": 1},
            "description": f"{lid} Passes 1 action.",
            "rule_citation": "4.7.7",
        })
    # End card is always available (active Lord may stop early)
    moves.append({
        "action": "cmd_end_card", "side": side, "args": {"lord_id": lid},
        "description": f"{lid} ends this card's actions; trigger Feed/Pay/Disband.",
        "rule_citation": "4.2.6 / 4.8",
    })
    return moves


# ----------------------------------------------------------------- helpers
def _own_lords(state, side, status: str | None = None) -> dict[str, dict]:
    out = {}
    for lid, l in state["lords"].items():
        if l["side"] != side:
            continue
        if status is None or l["status"] == status:
            out[lid] = l
    return out


def _ravage_candidates(state, lord, side) -> list[str]:
    """Pre-filter Locales eligible for Ravage by `lord`. See SMOKE-Inferno-005."""
    out: list[str] = []
    try:
        cur_loc_name = lord.get("location")
        if not cur_loc_name:
            return out
        cur_loc = state["locales"].get(cur_loc_name)
        if not cur_loc:
            return out
        # Ravage at the Lord's current Locale (the most common case in Phase 3a).
        if (not cur_loc.get("ravaged")
                and not _is_friendly_locale_quiet(state, cur_loc, side)):
            out.append(cur_loc_name)
    except (KeyError, AttributeError):
        return []
    return out


def _is_friendly_locale_quiet(state, locale: dict, side: str) -> bool:
    """Defensive variant of actions._is_friendly_locale — never raises."""
    try:
        enemy = "ghibelline" if side == "guelph" else "guelph"
        markers = locale.get("current_allegiance", []) or []
        enemy_m = sum(1 for m in markers if m.get("side") == enemy)
        own_m = sum(1 for m in markers if m.get("side") == side)
        if enemy_m > 0 and own_m == 0:
            return False
        if locale.get("allegiance") == side:
            return True
        return own_m > 0
    except (KeyError, AttributeError, TypeError):
        return False


def _is_friendly_stronghold_quiet(state, locale, side) -> bool:
    try:
        if locale.get("type") == "outpost":
            return locale.get("allegiance") == side
        if locale.get("ruins"):
            return False
        return _is_friendly_locale_quiet(state, locale, side)
    except (KeyError, AttributeError, TypeError):
        return False



def _enum_approach_response(state, pending) -> list[dict[str, Any]]:
    """Per 4.3.4: each Inactive Lord chooses avoid / withdraw / stand.

    Defensive enumeration: only emit options the handler would accept.
    """
    info = pending["info"]
    lid = info["lord_id"]
    locale_name = info["locale"]
    side = pending["side"]
    lord = state["lords"].get(lid)
    loc = state["locales"].get(locale_name, {})
    out: list[dict[str, Any]] = []

    # Stand is always available
    out.append({
        "action": "approach_response", "side": side,
        "args": {"lord_id": lid, "choice": "stand"},
        "description": f"{lid} stands for Battle at {locale_name}.",
        "rule_citation": "4.3.4",
    })

    # SMOKE-Inferno-011: Avoid Battle pre-check — Unladen + adjacent + not into enemy.
    try:
        if (lord and lord["assets"].get("Loot", 0) == 0):
            for neighbour, way_type in sd.adjacent_to(locale_name):
                # SMOKE-Inferno-055: do not offer an Avoid that retreats back
                # along the Way the Active Lord approached (shared predicate).
                ways_to_n = [w for n, w in sd.adjacent_to(locale_name) if n == neighbour]
                if sd.avoid_along_approach_way(neighbour, info.get("approached_from"),
                                               ways_to_n, info.get("approached_via")):
                    continue
                target = state["locales"].get(neighbour, {})
                # No Avoiding into an enemy-occupied Locale
                has_enemy = any(
                    state["lords"][oid]["side"] != side
                    and state["lords"][oid].get("flags", {}).get("in_stronghold", False) is False
                    for oid in target.get("lords_present", [])
                )
                if has_enemy:
                    continue
                # Outpost gate: only owning Lord may enter
                if target.get("type") == "outpost" and neighbour not in lord.get("seats", []):
                    continue
                out.append({
                    "action": "approach_response", "side": side,
                    "args": {"lord_id": lid, "choice": "avoid",
                             "destination": neighbour},
                    "description": f"{lid} Avoids Battle to {neighbour} ({way_type}).",
                    "rule_citation": "4.3.4",
                })
    except (KeyError, AttributeError, TypeError):
        pass

    # SMOKE-Inferno-012: Withdraw pre-check — friendly Stronghold, room.
    try:
        if (lord and loc and not loc.get("ruins")
                and _is_friendly_locale_quiet(state, loc, side)):
            size_map = {"castle": 1, "town": 2, "city": 3, "outpost": 0}
            cap = size_map.get(loc.get("type"), 0)
            if cap > 0:
                in_count = sum(
                    1 for oid in loc.get("lords_present", [])
                    if state["lords"][oid]["side"] == side
                    and state["lords"][oid].get("flags", {}).get("in_stronghold")
                )
                if in_count < cap:
                    out.append({
                        "action": "approach_response", "side": side,
                        "args": {"lord_id": lid, "choice": "withdraw"},
                        "description": f"{lid} Withdraws into {locale_name} ({loc.get('type')}, cap {cap}).",
                        "rule_citation": "4.3.4",
                    })
    except (KeyError, AttributeError, TypeError):
        pass
    return out



def _enum_end_campaign(state, side) -> list[dict[str, Any]]:
    """Per 4.9, end-of-Campaign substeps run in order:
       Grow -> Ransom -> Game-end check -> Repair -> Waste -> Reset.

    The state.meta.end_substep_done list tracks per-side progress. Phase 3e
    presents the next eligible action.
    """
    done = state["meta"].get("end_substep_done", [])
    turn = state["meta"]["turn"]
    # 4.9.1 Grow — only on Grow turns
    if "grow" not in done:
        if turn in sd.GROW_BOXES:
            return [{
                "action": "end_grow", "side": side,
                "description": f"4.9.1 Grow at Box {turn}: reduce enemy Ravage to ceil(N/2).",
                "rule_citation": "4.9.1",
            }, {
                "action": "end_grow_skip", "side": side,
                "description": "Skip Grow (no enemy Ravages or default).",
                "rule_citation": "4.9.1",
            }]
        else:
            return [{
                "action": "end_grow_skip", "side": side,
                "description": "Skip Grow (not a Grow turn).",
                "rule_citation": "4.9.1",
            }]
    # 4.9.2 Ransom
    if "ransom" not in done:
        captured = state.get("captured_knights", {}).get(side, {})
        total = sum(captured.values())
        if total > 0:
            cost = (total + 5) // 6
            return [
                {"action": "end_ransom", "side": side, "args": {"pay": True},
                 "description": f"Ransom {total} captured units for {cost} Coin; recover ceil(N/2).",
                 "rule_citation": "4.9.2"},
                {"action": "end_ransom", "side": side, "args": {"pay": False},
                 "description": f"Languish: skip Ransom; enemy adds {cost} Treachery/Revolt.",
                 "rule_citation": "4.9.2"},
            ]
        else:
            return [{"action": "end_ransom", "side": side, "args": {"pay": True},
                     "description": "No captures; auto-advance.", "rule_citation": "4.9.2"}]
    # 4.9.3 Game-end check (run once for the campaign, not per-side)
    if "game_check" not in done:
        return [{
            "action": "end_game_check", "side": side,
            "description": "Check if last Turn — game end if so.",
            "rule_citation": "4.9.3",
        }]
    # 4.9.4 Repair (auto-applied via action call)
    if "repair" not in done:
        return [{
            "action": "end_repair", "side": side,
            "description": "Repair: remove 1 Siege marker from any Town/City with 3-4 markers.",
            "rule_citation": "4.9.4",
        }]
    # 4.9.5 Waste — per-side; presents the action
    if "waste" not in done:
        return [{
            "action": "end_waste", "side": side,
            "description": "Waste: each Lord with multi-Assets discards one.",
            "rule_citation": "4.9.5",
        }]
    # 4.9.6 Reset — finalizes the Campaign
    return [{
        "action": "end_reset", "side": side,
        "description": "Reset: set aside Treachery, unstack Lieutenants, advance Calendar.",
        "rule_citation": "4.9.6",
    }]
