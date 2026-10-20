"""Vassal muster and Service bookkeeping (3.4.2, including the advanced rule).

Vassal service_box uses 0/17 for the off-Calendar positions. None means no
Service marker on the Calendar. Ordinary Ready Vassals already have on_mat=True
in older saves; only on_mat and not ready denotes a Mustered Vassal.
"""
from __future__ import annotations

import copy

from . import static_data as sd


def is_mustered(v):
    return bool(v.get("on_mat") and not v.get("ready"))


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
        v["service_box"] = min(17, state["calendar"]["levy_box"] + v["service_rating"])
    else:
        v["service_box"] = None


def shifted_box(cur, delta):
    # 2.2.3: one box per shift; excess movement off an edge is ignored.
    return max(0, min(17, cur + delta))


def has_service(state, lid):
    cal = state.get("calendar", {})
    return (state["lords"].get(lid, {}).get("service_box") is not None
            or lid in cal.get("off_left_service", [])
            or lid in cal.get("off_right_service", []))


def shift_service(state, lid, delta):
    """Shift a Lord AND his Vassals, even if the Lord is off the Calendar."""
    lord = state["lords"][lid]
    cal = state.get("calendar", {})
    cur = lord.get("service_box")
    if cur is None:
        if lid in cal.get("off_left_service", []):
            cur = 0
        elif lid in cal.get("off_right_service", []):
            cur = 17
    # A Comune has no separate Lord Service marker. Its Vassals already
    # follow the Commander; processing its Retreat must not shift them twice.
    if cur is None:
        return None
    if state.get("meta", {}).get("advanced_vassal_service"):
        # A Comune's Vassals follow the Commander's Service shifts (1.5.1).
        owners = [lord] + [l for l in state["lords"].values()
                           if l.get("comune_of") and l["comune_of"] in (lid, lord.get("name"))]
        for owner in owners:
            for v in owner.get("vassals", []):
                if (is_mustered(v) and v.get("service_box") is not None
                        and not v.get("turncoat") and v.get("name") != "Carroccio"):
                    v["service_box"] = shifted_box(v["service_box"], delta)
    new = shifted_box(cur, delta)
    from .actions import _place_service
    _place_service(state, lid, new if 1 <= new <= 16 else None)
    if new in (0, 17):
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
