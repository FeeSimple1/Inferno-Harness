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


def enumerate_legal(state: dict[str, Any]) -> list[dict[str, Any]]:
    # Pending decisions take precedence over phase enumeration (per BRIEF
    # "Non-Combat Pending Decisions"). If an approach_response is pending
    # for the active side, only that response is legal.
    pendings = state.get("pending") or []
    for p in pendings:
        if p.get("type") == "approach_response" and p.get("side") == state["meta"].get("active_player"):
            return _enum_approach_response(state, p)
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
    levy_box = state["calendar"]["levy_box"]
    disbandable = [
        lid for lid, l in state["lords"].items()
        if l["side"] == side and l["status"] == "mustered"
        and (l.get("service_box") or 0) <= levy_box
    ]
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
        return [{
            "action": "<phase_3c_pending>",
            "description": "End-Campaign 4.9 steps (Grow/Ransom/Repair/Waste/Reset) implemented in Phase 3c.",
            "rule_citation": "4.9",
        }]
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
    forage_ok = False
    forage_reason = ""
    try:
        if loc and not loc.get("ravaged") and not loc.get("siege"):
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
                if way_type == info.get("approached_via"):
                    # Phase 3b conservative: same-Way ambiguity is rejected
                    # only if all routes are that Way; here we accept the
                    # candidate and let the handler validate.
                    pass
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
