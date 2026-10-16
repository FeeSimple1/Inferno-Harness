"""Read-only, perspective-bound versions and whole-record pagination.

A version describes the visible position plus the accepted-action revision. It
never hashes a secret hand or RNG seed into a player-visible guessing oracle.
Every accepted dispatch adds history, including passes and hidden actions.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from typing import Any

from ..actions import IllegalAction
from .filter import hide_for_side


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def visible_state(state: dict, side: str, hidden_mats: bool | None = None) -> dict:
    # A caller may strengthen, but never switch off the game's visibility rule.
    hidden = bool(hidden_mats or state.get("meta", {}).get("hidden_mats")
                  or state.get("_hidden_mats"))
    return hide_for_side(state, side, hidden_mats=hidden)


def view_version(view: dict, *, accepted_revision: int | None = None) -> str:
    material = {k: v for k, v in view.items() if k != "history"}
    revision = len(view.get("history", [])) if accepted_revision is None else accepted_revision
    material["accepted_action_revision"] = revision
    # The most recent public record is part of the visible position, too.
    material["last_public_action"] = view.get("history", [])[-1:]
    digest = hashlib.sha256(compact(material).encode()).hexdigest()[:24]
    return f"{view['_filtered_for'][0:2]}-{revision}-{digest}"


def state_version(state: dict, side: str, hidden_mats: bool | None = None) -> str:
    # Earlier history contributes only its revision count to the version. Do
    # not copy/filter thousands of old records on every page freshness check.
    from ..visibility import combat_visibility
    if combat_visibility(state):
        # Combat reveal scope is bound to this exact authoritative object. A
        # shallow replacement would hide the participating enemy mats again.
        return view_version(visible_state(state, side, hidden_mats))
    history = state.get("history", [])
    recent = {**state, "history": history[-1:]}
    return view_version(visible_state(recent, side, hidden_mats), accepted_revision=len(history))


def require_version(supplied: Any, expected: str) -> None:
    if not isinstance(supplied, str) or supplied != expected:
        raise IllegalAction("STALE_VIEW", "The position or perspective changed. Request a new overview; no action was applied.")


def _decode(cursor: Any, version: str, domain: str) -> dict:
    try:
        if not isinstance(cursor, str) or not cursor:
            raise ValueError("cursor must be a nonempty string")
        data = json.loads(base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True))
        if not isinstance(data, dict) or set(data) != {"v", "d", "f", "o"}:
            raise ValueError("unexpected cursor shape")
        require_version(data["v"], version)
        if data["d"] != domain or not isinstance(data["f"], dict):
            raise ValueError("cursor belongs to a different query")
        if type(data["o"]) is not int or data["o"] < 0:
            raise ValueError("invalid page offset")
        return data
    except IllegalAction:
        raise
    except (ValueError, TypeError, UnicodeError) as exc:
        raise IllegalAction("BAD_CURSOR", "Invalid pagination cursor; request the first page again.") from exc


def query_position(cursor: str | None, version: str, domain: str,
                   filters: dict | None) -> tuple[int, dict]:
    if cursor is None:
        return 0, copy.deepcopy(filters or {})
    data = _decode(cursor, version, domain)
    if filters is not None and filters != data["f"]:
        raise IllegalAction("BAD_CURSOR", "Cursor filters do not match this request.")
    return data["o"], data["f"]


def page_records(records: list, version: str, domain: str, filters: dict,
                 offset: int = 0, page_size: int = 12,
                 max_chars: int | None = None) -> dict:
    if type(page_size) is not int or page_size < 1:
        raise IllegalAction("BAD_PAGE_SIZE", "page_size must be a positive integer.")
    if max_chars is not None and (type(max_chars) is not int or max_chars < 1):
        raise IllegalAction("BAD_BUDGET", "max_chars must be a positive integer or null.")
    if offset > len(records):
        raise IllegalAction("BAD_CURSOR", "Page offset is outside this result set.")
    selected = []
    used = 0
    for record in records[offset:offset + page_size]:
        size = len(compact(record))
        if selected and max_chars is not None and used + size > max_chars:
            break
        selected.append(copy.deepcopy(record))
        used += size
    end = offset + len(selected)
    next_cursor = None
    if end < len(records):
        payload = {"v": version, "d": domain, "f": filters, "o": end}
        next_cursor = base64.urlsafe_b64encode(compact(payload).encode()).decode().rstrip("=")
    return {"state_version": version, "total": len(records), "offset": offset,
            "returned": len(selected), "records": selected, "next_cursor": next_cursor,
            "complete": end == len(records),
            "soft_target_exceeded": max_chars is not None and used > max_chars}
