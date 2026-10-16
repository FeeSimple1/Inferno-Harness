"""Lossless, versioned action discovery. No rankings or execution probes.

Open-mat pages partition enumerate_legal exactly. Hidden-mat targeting uses
explicit parameterized templates where listing valid targets would itself
reveal an unrevealed mat. Those templates retain every legal instantiation;
the authoritative dispatcher still validates the submitted arguments.
"""
from __future__ import annotations

import copy
import hashlib
from typing import Any

from ..actions import IllegalAction, dispatch
from ..legal_moves import enumerate_legal
from .protocol import (compact, page_records, query_position, require_version,
                       visible_state, view_version)


def acting_side(state: dict, moves: list | None = None) -> str:
    """Mandatory decision owner, not necessarily meta.active_player."""
    moves = enumerate_legal(state) if moves is None else moves
    for move in moves:
        if move.get("side") in ("guelph", "ghibelline"):
            return move["side"]
    return state.get("meta", {}).get("active_player", "guelph")


def _hidden_target_templates(state: dict, side: str, moves: list) -> list:
    """Do not turn hidden Asset/Force/Vassal contents into a legal-menu oracle."""
    from ..actions import _hold_event_window_ok
    from ..held_events import _candidate_in_context
    if (state.get("pending_fpd") or state.get("pending_revolts") or state.get("pending_exiles")
            or (state.get("meta", {}).get("phase") == "levy" and state.get("meta", {}).get("levy_step") == "3.1")):
        return moves
    approach = any(p.get("type") == "approach_response" for p in state.get("pending", []))
    eligible_side = (side == state.get("meta", {}).get("active_player")
                     or (approach and side == state.get("meta", {}).get("approach_attacker_side")))
    if not eligible_side:
        return moves
    sensitive = {"F7", "S7", "S16", "S19"}
    held = state.get("decks", {}).get(side, {}).get("aow_held", [])
    out = [m for m in moves if not (
        m.get("action") == "play_event" and m.get("args", {}).get("card_id") in sensitive)]
    enemy = sorted(lid for lid, l in state.get("lords", {}).items()
                   if l.get("side") != side and l.get("status") == "mustered")
    for cid in sorted(set(held) & sensitive):
        if not _hold_event_window_ok(state, side, cid) or not _candidate_in_context(state, side, cid, {}):
            continue
        if cid in ("F7", "S7"):
            fields = {"enemy_lord_id": "<enemy Lord>", "unit_to_remove": "<unit type>",
                      "capability_to_discard": "<Capability ID when applicable>"}
        elif cid == "S16":
            fields = {"target_lord_id": "<enemy Lord>"}
        else:
            fields = {"target_lord_id": "<enemy Lord>",
                      "receiver_lord_id": "<giordano or astimberg>",
                      "bundle": "<coin, loot, or carts_prov>"}
        out.append({"action": "play_event", "side": side,
                    "args": {"card_id": cid, "effect_args": fields},
                    "parameterized": True, "conditional": True,
                    "parameters": {"effect_args": {"fields": fields, "public_enemy_lords": enemy}},
                    "description": f"Play {cid}; supply effect_args. Target validity is checked at submission, not disclosed from hidden mats. All legal target/selection combinations remain available.",
                    "rule_citation": f"{cid} / 1.5.2 / 3.1.3"})
    # Hidden Vassal readiness cannot be inferred by listing only valid Bribes.
    bribes = [m for m in out if m.get("action") == "cmd_treachery_bribe"]
    out = [m for m in out if m.get("action") != "cmd_treachery_bribe"]
    lid = state.get("current_lord_id")
    lord = state.get("lords", {}).get(lid, {})
    possible_bribe = (state.get("meta", {}).get("phase") == "campaign"
                      and state.get("meta", {}).get("campaign_step") == "command_phase"
                      and lord.get("side") == side and state.get("current_card", "")
                      and str(state.get("current_card")).startswith("treachery_")
                      and state.get("actions_remaining", 0) > 0
                      and lord.get("assets", {}).get("Coin", 0) >= 1)
    if bribes or possible_bribe:
        # Public roster, not a filtered list of secretly Mustered targets.
        from .. import static_data as sd
        roster = sorted({v['name'] for l in sd.LORDS.values() for v in l.get('vassals', [])
                         if not v.get('special')})
        out.append({"action": "cmd_treachery_bribe", "side": side,
                    "args": {"lord_id": lid, "target_lord_id": "<Vassal's Lord>",
                             "vassal": "<regular Vassal name>"},
                    "parameterized": True, "conditional": True,
                    "parameters": {"public_regular_vassals": roster},
                    "description": "Bribe a regular Vassal. Supply the target arguments; hidden Muster eligibility is checked on submission. An invalid hidden target may be changed without spending the action.",
                    "rule_citation": "4.7.6 / 1.5.2"})
    return out


def _has_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return value.startswith("<") and value.endswith(">")
    if isinstance(value, dict):
        return any(_has_placeholder(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_placeholder(v) for v in value)
    return False


def _contains(value: Any, target: str) -> bool:
    if isinstance(value, dict):
        return any(_contains(v, target) for v in value.values())
    if isinstance(value, list):
        return any(_contains(v, target) for v in value)
    return value == target


class ActionCatalog:
    """A read-only snapshot of all choices for exactly one perspective."""
    def __init__(self, state: dict, side: str, hidden_mats: bool | None = None):
        self.side = side
        self.view = visible_state(state, side, hidden_mats)
        self.version = view_version(self.view)
        self.hidden_mats = self.view['_hidden_mats']
        all_moves = enumerate_legal(state)
        self.acting_player = acting_side(state, all_moves)
        moves = [copy.deepcopy(m) for m in all_moves
                 if m.get("side") == side or m.get("action", "").startswith("<")]
        if self.hidden_mats:
            moves = _hidden_target_templates(state, side, moves)
        self.entries = []
        seen: dict[str, int] = {}
        for move in sorted(moves, key=compact):
            signature = hashlib.sha256((self.version + '/' + compact(move)).encode()).hexdigest()[:16]
            occurrence = seen.get(signature, 0)
            seen[signature] = occurrence + 1
            ident = f"a-{signature}-{occurrence}"
            self.entries.append({"action_id": ident, "move": move,
                                 "parameterized": bool(move.get("parameterized") or _has_placeholder(move.get("args")))})
        self._by_id = {entry['action_id']: entry for entry in self.entries}

    def overview(self) -> dict:
        categories = {}
        for entry in self.entries:
            move = entry['move']; name = move.get('action', '<unknown>')
            cat = categories.setdefault(name, {"category": name, "count": 0, "parameterized": 0,
                                               "argument_fields": set(), "decision_channels": {}})
            cat['count'] += 1
            cat['parameterized'] += int(entry['parameterized'])
            cat['argument_fields'].update(move.get('args', {}))
            for channel, choices in move.get('accepts_decisions', {}).items():
                cat['decision_channels'].setdefault(channel, set()).update(choices)
        for cat in categories.values():
            cat['argument_fields'] = sorted(cat['argument_fields'])
            cat['decision_channels'] = {k: sorted(v) for k, v in sorted(cat['decision_channels'].items())}
        return {"state_version": self.version, "perspective": self.side,
                "acting_player": self.acting_player, "total": len(self.entries),
                "categories": [categories[k] for k in sorted(categories)],
                "retrieval": {"request": "actions", "category": "<any category or omit for all>",
                              "page_size": 12},
                "parameters": "Each page includes complete move metadata. Supply args to fill a template or choose optional parameters; dispatch remains authoritative."}

    def page(self, *, category: str | None = None, lord: str | None = None,
             card: str | None = None, where: dict | None = None,
             cursor: str | None = None, page_size: int = 12,
             max_chars: int | None = None) -> dict:
        for value in (category, lord, card):
            if value is not None and not isinstance(value, str):
                raise IllegalAction("BAD_FILTER", "category, lord and card must be strings.")
        if where is not None and (not isinstance(where, dict) or not all(isinstance(k, str) for k in where)):
            raise IllegalAction("BAD_FILTER", "where must map dotted field paths to exact values.")
        specified = {k: v for k, v in {"category": category, "lord": lord, "card": card,
                                      "where": where}.items() if v is not None}
        offset, filters = query_position(cursor, self.version, "actions", specified if specified or cursor is None else None)
        if set(filters) - {"category", "lord", "card", "where"}:
            raise IllegalAction("BAD_FILTER", "Unknown action filter.")
        if any(k in filters and not isinstance(filters[k], str) for k in ("category", "lord", "card")):
            raise IllegalAction("BAD_FILTER", "Cursor filters must be strings.")
        if 'where' in filters and (not isinstance(filters['where'], dict)
                                  or not all(isinstance(k, str) for k in filters['where'])):
            raise IllegalAction("BAD_FILTER", "Cursor where filter must be an object.")
        def matches(entry):
            m = entry['move']
            if 'category' in filters and m.get('action') != filters['category']:
                return False
            if any(k in filters and not _contains(m.get('args', {}), filters[k]) for k in ('lord','card')):
                return False
            for path, target in filters.get('where', {}).items():
                value = m
                for field in path.split('.'):
                    if not isinstance(value, dict) or field not in value:
                        return False
                    value = value[field]
                if value != target:
                    return False
            return True
        records = [e for e in self.entries if matches(e)]
        return page_records(records, self.version, "actions", filters, offset, page_size, max_chars)

    def resolve(self, selection: dict) -> dict:
        if not isinstance(selection, dict):
            raise IllegalAction("BAD_SELECTION", "Selection must be a JSON object.")
        if set(selection) - {'action_id', 'state_version', 'args'}:
            raise IllegalAction("BAD_SELECTION", "Select an action_id with state_version and optional args; action and side cannot be replaced.")
        require_version(selection.get('state_version'), self.version)
        ident = selection.get('action_id')
        if not isinstance(ident, str) or ident not in self._by_id:
            raise IllegalAction("STALE_ACTION", "Unknown action identifier for this position and perspective.")
        move = self._by_id[ident]['move']
        if move.get('action', '').startswith('<'):
            raise IllegalAction("NOT_EXECUTABLE", "This is an engine diagnostic, not an executable action.")
        action = {k: copy.deepcopy(move[k]) for k in ('action','side','args') if k in move}
        if 'args' in selection:
            if not isinstance(selection['args'], dict):
                raise IllegalAction("BAD_SELECTION", "args must be a complete JSON object.")
            action['args'] = copy.deepcopy(selection['args'])
        if _has_placeholder(action.get('args', {})):
            raise IllegalAction("MISSING_PARAMETERS", "Fill every required template argument before selecting it. The action was not applied.")
        return action


def submit_selection(state: dict, side: str, selection: dict,
                     hidden_mats: bool | None = None) -> dict:
    """Reject stale IDs BEFORE dispatch: no dice, resources or history change."""
    catalog = ActionCatalog(state, side, hidden_mats)
    return dispatch(state, catalog.resolve(selection))
