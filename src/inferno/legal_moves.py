"""Legal-moves enumeration.

Per BRIEF: the primary interface an LLM uses to decide what to do.
Returns the valid actions for state.meta.active_player at the current
phase/step, each entry with action grammar, costs, prerequisites met,
and a brief description with rule citation.
"""

from __future__ import annotations

from typing import Any

from .flow import LEVY_STEPS, current_side, current_step


def enumerate_legal(state: dict[str, Any]) -> list[dict[str, Any]]:
    phase = state["meta"].get("phase")
    if phase == "levy":
        return _enum_levy(state)
    if phase == "campaign":
        return [{
            "action": "<phase_3_pending>",
            "description": "Campaign phase actions are implemented in Phase 3.",
            "rule_citation": "4.0",
        }]
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


# 3.1 Arts of War — single mandatory action
def _enum_aow(state, side) -> list[dict[str, Any]]:
    return [{
        "action": "levy_aow_draw",
        "args": {"side": side},
        "description": "Draw 2 AoW cards; first Levy deploys as Capabilities, later Levies implement Events.",
        "rule_citation": "3.1.2 / 3.1.3",
    }]


# 3.2 Pay — pay actions + done
def _enum_pay(state, side) -> list[dict[str, Any]]:
    moves: list[dict[str, Any]] = []
    own_mustered = _own_lords(state, side, status="mustered")
    for from_lid, from_lord in own_mustered.items():
        if from_lord["assets"].get("Coin", 0) > 0:
            # Pay can target self or another Lord at same Locale.
            same_loc = [
                (tlid, t) for tlid, t in own_mustered.items()
                if t.get("location") == from_lord.get("location")
            ]
            for tlid, t in same_loc:
                rate = 2 if t.get("podesta") else 1
                max_boxes = from_lord["assets"]["Coin"] // rate
                if max_boxes >= 1:
                    moves.append({
                        "action": "levy_pay",
                        "args": {"side": side, "from_lord_id": from_lid,
                                 "target_lord_id": tlid, "asset": "Coin", "amount": 1},
                        "description": f"{from_lid} pays {rate} Coin to shift {tlid}'s Service marker right by 1 box.",
                        "rule_citation": "3.2.1",
                    })
        if from_lord["assets"].get("Loot", 0) > 0:
            # Loot path: payer at Friendly Locale free of Siege.
            loc = state["locales"].get(from_lord.get("location") or "")
            if loc and not loc.get("siege"):
                for tlid, t in own_mustered.items():
                    if t.get("location") == from_lord.get("location"):
                        rate = 2 if t.get("podesta") else 1
                        if from_lord["assets"]["Loot"] >= rate:
                            moves.append({
                                "action": "levy_pay",
                                "args": {"side": side, "from_lord_id": from_lid,
                                         "target_lord_id": tlid, "asset": "Loot", "amount": 1},
                                "description": f"{from_lid} pays {rate} Loot to shift {tlid}'s Service marker right by 1 box.",
                                "rule_citation": "3.2.2",
                            })
    moves.append({
        "action": "levy_pay_done",
        "args": {"side": side},
        "description": "End Pay segment for this side.",
        "rule_citation": "3.2",
    })
    return moves


# 3.3 Disband — single (auto-process) + done
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
            "action": "levy_disband",
            "args": {"side": side},
            "description": f"Auto-process all Disbandable Lords for {side}: {disbandable}",
            "rule_citation": "3.3.1 / 3.3.2 (Errata)",
        })
    moves.append({
        "action": "levy_disband_done",
        "args": {"side": side},
        "description": "End Disband segment for this side.",
        "rule_citation": "3.3",
    })
    return moves


# 3.4 Muster — per-Lord Lordship actions + done
def _enum_muster(state, side) -> list[dict[str, Any]]:
    moves: list[dict[str, Any]] = []
    own_mustered = _own_lords(state, side, status="mustered")
    own_on_calendar = _own_lords(state, side, status="on_calendar")
    levy_box = state["calendar"]["levy_box"]

    for lid, lord in own_mustered.items():
        # 3.4.1 Muster Lord (Fealty)
        for tlid, tlord in own_on_calendar.items():
            if (tlord.get("calendar_box") or 0) <= levy_box:
                for seat in tlord.get("seats", []):
                    moves.append({
                        "action": "levy_muster_lord",
                        "args": {"side": side, "muster_lord_id": lid,
                                 "target_lord_id": tlid, "target_seat": seat},
                        "description": f"{lid} attempts Fealty roll on {tlid} (F:{tlord['ratings'].get('F','-')}) at {seat}.",
                        "rule_citation": "3.4.1",
                    })
        # 3.4.2 Muster Vassal
        for v in lord.get("vassals", []):
            if v.get("ready") and not v.get("special"):
                moves.append({
                    "action": "levy_muster_vassal",
                    "args": {"side": side, "lord_id": lid, "vassal": v["name"]},
                    "description": f"{lid} Musters {v['name']} ({_force_summary(v.get('forces', {}))}).",
                    "rule_citation": "3.4.2",
                })
        # 3.4.3 Levy Transport
        moves.append({
            "action": "levy_muster_transport",
            "args": {"side": side, "lord_id": lid, "kind": "Cart"},
            "description": f"{lid} levies 1 Cart.",
            "rule_citation": "3.4.3",
        })
        if lord["name"] == "Pisa Podestà":
            moves.append({
                "action": "levy_muster_transport",
                "args": {"side": side, "lord_id": lid, "kind": "Ship"},
                "description": f"{lid} levies 1 Ship (Pisa only).",
                "rule_citation": "3.4.3 / 4.7.3",
            })
        # 3.4.4 Levy Capability
        if state["decks"][side]["aow_deck"]:
            moves.append({
                "action": "levy_muster_capability",
                "args": {"side": side, "lord_id": lid, "scope": "side_wide"},
                "description": f"{lid} levies 1 Capability for the side.",
                "rule_citation": "3.4.4",
            })
            if len(lord.get("capabilities", [])) < 2:
                moves.append({
                    "action": "levy_muster_capability",
                    "args": {"side": side, "lord_id": lid, "scope": "this_lord"},
                    "description": f"{lid} levies 1 'This Lord' Capability (max 2).",
                    "rule_citation": "3.4.4",
                })
    moves.append({
        "action": "levy_muster_done",
        "args": {"side": side},
        "description": "End Muster segment for this side.",
        "rule_citation": "3.4",
    })
    return moves


# 3.5 Call to Arms — Phase 2 stub
def _enum_cta(state, side) -> list[dict[str, Any]]:
    return [{
        "action": "levy_cta_skip",
        "args": {"side": side},
        "description": "Decline Call to Arms (Phase 2: full CtA implementation deferred to Phase 2b).",
        "rule_citation": "3.5",
    }]


# ----------------------------------------------------------------- helpers
def _own_lords(state, side, status: str | None = None) -> dict[str, dict]:
    out = {}
    for lid, l in state["lords"].items():
        if l["side"] != side:
            continue
        if status is None or l["status"] == status:
            out[lid] = l
    return out


def _force_summary(forces: dict[str, int]) -> str:
    if not forces:
        return "no forces"
    return ", ".join(f"{c} {u}" for u, c in sorted(forces.items()) if c)
