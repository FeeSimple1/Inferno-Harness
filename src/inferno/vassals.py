"""Vassal muster and Service bookkeeping (3.4.2, including the advanced rule).

Vassal service_box uses 0/17 for the off-Calendar positions. None means no
Service marker on the Calendar. Ordinary Ready Vassals already have on_mat=True
in older saves; only on_mat and not ready denotes a Mustered Vassal.
"""
from __future__ import annotations

import copy

from . import static_data as sd

OFF_RIGHT = 17

REGULAR_VASSALS = {
    v["name"]: (sd.LORD_IDS[name], v)
    for name, lord in sd.LORDS.items() for v in lord.get("vassals", [])
    if not v.get("special")
}


def is_mustered(v):
    return bool(v.get("on_mat") and not v.get("ready"))


def bribe_targets(state, lid):
    """4.7.6: locate a regular Vassal by its live mat or its printed Seats."""
    lord = state["lords"][lid]
    location = lord.get("location")
    if not location:
        return {}
    nearby = {location, *(name for name, _ in sd.adjacent_to(location))}
    live = {}
    for holder_id, holder in state["lords"].items():
        if holder["status"] == "mustered":
            for v in holder.get("vassals", []):
                if is_mustered(v):
                    live.setdefault(v["name"], []).append((holder_id, v))
    targets = {}
    for name, (parent_id, printed) in sorted(REGULAR_VASSALS.items()):
        if name in live:
            if len(live[name]) == 1:
                holder_id, v = live[name][0]
                holder = state["lords"][holder_id]
                if (not v.get("special") and holder["side"] != lord["side"]
                        and holder.get("location") in nearby):
                    targets[name] = (holder_id, v, "A")
            continue
        parent = state["lords"][parent_id]
        seats = printed.get("seats") or [printed.get("seat")]
        if parent["side"] == lord["side"] or nearby.isdisjoint(seats):
            continue
        if parent["status"] == "mustered":
            v = next((v for v in parent.get("vassals", []) if v["name"] == name), printed)
            if v.get("service_box") is None:
                targets[name] = (parent_id, v, "B_mustered_parent")
        else:
            targets[name] = (parent_id, printed, "B_unmustered_parent")
    return targets


def muster_roster(state, lid):
    """Keep a regular Vassal with its current Turncoat holder when its Lord Musters."""
    from .scenarios import _init_vassals_for

    away = {v["name"] for oid, lord in state["lords"].items()
            if oid != lid and lord["status"] == "mustered"
            for v in lord.get("vassals", []) if v.get("turncoat")}
    return [v for v in _init_vassals_for(sd.LORDS.get(state["lords"][lid]["name"], {}))
            if v["name"] not in away]


def return_turncoats(state, lid):
    """When the holder leaves play, restore Turncoats to their original side."""
    for v in state["lords"][lid].get("vassals", []):
        if not v.get("turncoat") or v["name"] not in REGULAR_VASSALS:
            continue
        parent_id, _ = REGULAR_VASSALS[v["name"]]
        parent = state["lords"][parent_id]
        if parent_id != lid and parent["status"] == "mustered":
            ready = copy.deepcopy(v)
            ready.update(ready=True, on_mat=True, service_box=None)
            ready.pop("turncoat", None)
            roster = parent.setdefault("vassals", [])
            roster[:] = [other for other in roster if other["name"] != v["name"]]
            roster.append(ready)


def friendly_seat(state, v, side):
    from .revolt import _effective_allegiance
    seats = v.get("seats") or [v.get("seat")]
    for seat in seats:
        loc = state["locales"].get(seat)
        if loc and _effective_allegiance(loc) == side:
            return True
    return False


def tau_available(state, lid):
    if lid not in ("firenze", "lucca"):
        return False
    if not any(c.get("id") == "F22" and c.get("side") == "guelph"
               for c in state.get("capabilities_in_play", [])):
        return False
    return not any(v.get("name") == "Altopascio"
                   for lord in state["lords"].values() for v in lord.get("vassals", []))


def new_tau():
    v = copy.deepcopy(sd.ALTOPASCIO_VASSAL)
    v.update(ready=True, on_mat=False, service_box=None)
    return v


def start_service(state, v):
    if (state["meta"].get("advanced_vassal_service")
            and v.get("name") != "Carroccio" and not v.get("turncoat")):
        v["service_box"] = min(OFF_RIGHT, state["calendar"]["levy_box"] + v["service_rating"])
    else:
        v["service_box"] = None


def shifted_box(cur, delta):
    # 2.2.3: one box per shift; excess movement off an edge is ignored.
    return max(0, min(OFF_RIGHT, cur + delta))


def service_position(state, lid) -> int | None:
    """Return the Lord's Service position, including 0/17 for the edges."""
    cur = state["lords"].get(lid, {}).get("service_box")
    if cur is not None:
        return cur
    cal = state.get("calendar", {})
    if lid in cal.get("off_left_service", []):
        return 0
    if lid in cal.get("off_right_service", []):
        return OFF_RIGHT
    return None


def has_service(state, lid) -> bool:
    return service_position(state, lid) is not None


def _following_vassal_markers(state, lid):
    """Yield the advanced Vassal markers that follow this Lord's Service."""
    if not state.get("meta", {}).get("advanced_vassal_service"):
        return
    lord = state["lords"][lid]
    # A Comune's Vassals follow the Commander's Service shifts (1.5.1).
    owners = [lord] + [other for other in state["lords"].values()
                       if other.get("comune_of")
                       and other["comune_of"] in (lid, lord.get("name"))]
    for owner in owners:
        for v in owner.get("vassals", []):
            if (is_mustered(v) and v.get("service_box") is not None
                    and not v.get("turncoat") and v.get("name") != "Carroccio"):
                yield v


def payable_service_steps(state, lid) -> int:
    """Count rightward steps that would move at least one affected marker."""
    cur = service_position(state, lid)
    if cur is None:
        return 0
    for v in _following_vassal_markers(state, lid):
        cur = min(cur, v["service_box"])
    return max(0, OFF_RIGHT - cur)


def shift_service(state, lid, delta):
    """Shift a Lord AND his Vassals, even if the Lord is off the Calendar."""
    lord = state["lords"][lid]
    cal = state.get("calendar", {})
    cur = service_position(state, lid)
    # A Comune has no separate Lord Service marker. Its Vassals already
    # follow the Commander; processing its Retreat must not shift them twice.
    if cur is None:
        return None
    for v in _following_vassal_markers(state, lid):
        v["service_box"] = shifted_box(v["service_box"], delta)
    new = shifted_box(cur, delta)
    from .actions import _place_service
    _place_service(state, lid, new if 0 < new < OFF_RIGHT else None)
    if new in (0, OFF_RIGHT):
        edge = "off_left_service" if new == 0 else "off_right_service"
        cal.setdefault(edge, []).append(lid)
    return lord["service_box"]


def disband_vassal(lord, v):
    for unit, count in v.get("forces", {}).items():
        left = max(0, lord["forces"].get(unit, 0) - count)
        if left:
            lord["forces"][unit] = left
        else:
            lord["forces"].pop(unit, None)
    v.update(on_mat=False, ready=False, service_box=None, unready=True)


def disband_expired(state, side):
    if not state["meta"].get("advanced_vassal_service"):
        return [], []
    removed, empty_lords = [], []
    for lid, lord in list(state["lords"].items()):
        if lord.get("status") != "mustered" or lord.get("side") != side:
            continue
        removed_here = False
        for v in lord.get("vassals", []):
            svc = v.get("service_box")
            if (is_mustered(v) and svc is not None and svc <= state["calendar"]["levy_box"]
                    and not v.get("turncoat") and v.get("name") != "Carroccio"):
                disband_vassal(lord, v)
                removed.append((lid, v["name"]))
                removed_here = True
        if removed_here and not sum(lord.get("forces", {}).values()):
            from .actions import _check_disband_on_zero_forces
            if _check_disband_on_zero_forces(state, lid):
                empty_lords.append(lid)
    return removed, empty_lords


def ready_after_levy(state):
    for lord in state["lords"].values():
        for v in lord.get("vassals", []):
            if v.pop("unready", False):
                v["ready"] = True
                v["on_mat"] = not v.get("special", False)


def discard_tau(state):
    removed, empty = [], []
    for lid, lord in state["lords"].items():
        for v in list(lord.get("vassals", [])):
            if v.get("name") == "Altopascio":
                if is_mustered(v):
                    disband_vassal(lord, v)
                lord["vassals"].remove(v)
                removed.append(lid)
                from .actions import _check_disband_on_zero_forces
                if _check_disband_on_zero_forces(state, lid):
                    empty.append(lid)
    return removed, empty
