"""State rendering.

Per BRIEF "LLM-Consumer Interface": state command must support:
  - summary mode (~500 tokens, sufficient for routine LLM decisions)
  - verbose mode (full state)
  - focused views (single Lord mat, single Locale, Calendar, deck composition)
"""

from __future__ import annotations

import json
from typing import Any

from . import static_data as sd


# =====================================================================
# Helpers
# =====================================================================
def _effective_vp_render(state):
    try:
        from .actions import effective_vp
        return effective_vp(state)
    except Exception:
        vp = state.get("vp", {})
        return vp.get("guelph", 0), vp.get("ghibelline", 0)


def _fmt_forces(forces: dict[str, int]) -> str:
    if not forces:
        return "-"
    items = [f"{count} {unit}" for unit, count in sorted(forces.items()) if count]
    return ", ".join(items) if items else "-"


def _fmt_assets(assets: dict[str, int]) -> str:
    if not assets:
        return "-"
    parts = [f"{k}:{v}" for k, v in sorted(assets.items()) if v]
    return " ".join(parts) if parts else "-"


def _side_short(side: str) -> str:
    return "G" if side == "guelph" else "H" if side == "ghibelline" else "?"


# =====================================================================
# Summary (~500 tokens budget)
# =====================================================================
def render_summary(state: dict[str, Any]) -> str:
    meta = state.get("meta", {})
    lords = state.get("lords", {})
    locales = state.get("locales", {})
    vp = state.get("vp", {})
    calendar = state.get("calendar", {})

    lines: list[str] = []
    sc = meta.get("scenario", "?")
    sc_name = ""
    try:
        from .scenarios import SCENARIO_NAMES
        sc_name = f" ({SCENARIO_NAMES.get(sc, '?')})"
    except Exception:
        pass
    lines.append(f"Inferno — Scenario {sc}{sc_name}")
    lines.append(
        f"  Turn {meta.get('turn', '?')}  "
        f"Phase {meta.get('phase', '?')}"
        + (f" / {meta.get('levy_step')}" if meta.get('levy_step') else "")
        + f"  Active: {meta.get('active_player', '?')}  "
        f"VP G={_effective_vp_render(state)[0]} H={_effective_vp_render(state)[1]}"
    )
    end_box = calendar.get("end_box")
    levy_box = calendar.get("levy_box")
    if end_box is not None:
        lines.append(f"  Calendar: Levy@{levy_box} End@{end_box}")
    else:
        lines.append(f"  Calendar: Levy@{levy_box} End=variable")

    # Mustered Lords on the map, grouped by Locale
    mustered_by_loc: dict[str, list[str]] = {}
    for lid, lord in lords.items():
        if lord.get("status") == "mustered" and lord.get("location"):
            mustered_by_loc.setdefault(lord["location"], []).append(lid)
    lines.append("")
    lines.append("Mustered Lords (on map):")
    if not mustered_by_loc:
        lines.append("  (none)")
    else:
        for loc in sorted(mustered_by_loc):
            ids = mustered_by_loc[loc]
            for lid in ids:
                lord = lords[lid]
                lines.append(
                    f"  [{_side_short(lord['side'])}] {lord['name']} @ {loc}  "
                    f"[{_fmt_forces(lord.get('forces', {}))}]  "
                    f"({_fmt_assets(lord.get('assets', {}))})"
                )

    # Lords on Calendar
    on_cal = sorted(
        (lid for lid, l in lords.items() if l.get("status") == "on_calendar"),
        key=lambda x: (lords[x].get("calendar_box") or 999, x),
    )
    if on_cal:
        lines.append("")
        lines.append("Lords on Calendar (waiting):")
        for lid in on_cal:
            l = lords[lid]
            lines.append(
                f"  [{_side_short(l['side'])}] {l['name']} @ box {l.get('calendar_box')}"
            )

    removed = [l["name"] for l in lords.values() if l.get("status") == "removed"]
    if removed:
        lines.append("")
        lines.append(f"Removed from play: {', '.join(removed)}")

    # Locales with non-default state
    marked_locales = []
    for name, loc in locales.items():
        bits = []
        if loc.get("current_allegiance"):
            bits.append("+".join(
                f"{m['value']}{_side_short(m['side'])}" for m in loc["current_allegiance"]
            ))
        if loc.get("ravaged"):
            bits.append(f"Rav({loc['ravaged']})")
        if loc.get("ruins"):
            bits.append(f"Ruin({loc['ruins']})")
        if loc.get("siege"):
            for s in loc["siege"]:
                bits.append(f"Siege:{s.get('count', 1)}{_side_short(s['side'])}")
        if loc.get("bypass"):
            bits.append("Bypassed")
        if bits:
            marked_locales.append(f"  {name}: {' '.join(bits)}")
    if marked_locales:
        lines.append("")
        lines.append("Locales with markers:")
        lines.extend(marked_locales)

    if state.get("pending"):
        lines.append("")
        lines.append("Pending decisions:")
        for p in state["pending"]:
            lines.append(f"  - {p.get('type')} ({p.get('side')})")

    return "\n".join(lines)


# =====================================================================
# Verbose
# =====================================================================
def render_verbose(state: dict[str, Any]) -> str:
    return json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False)


# =====================================================================
# Focused views
# =====================================================================
def render_lord(state: dict[str, Any], lord_id: str) -> str:
    lords = state.get("lords", {})
    if lord_id not in lords:
        # accept canonical names too
        for lid, l in lords.items():
            if l.get("name") == lord_id:
                lord_id = lid
                break
        else:
            return f"Lord {lord_id!r} not found. Valid ids: {sorted(lords)}"
    l = lords[lord_id]
    lines = [
        f"Lord {lord_id}: {l['name']} ({l['side']})",
        f"  Status:    {l.get('status')}",
        f"  Location:  {l.get('location') or '-'}",
        f"  Calendar:  cylinder@{l.get('calendar_box') or '-'} service@{l.get('service_box') or '-'}",
    ]
    if l.get("podesta"):
        lines.append("  Podestà:   yes")
    if l.get("commander"):
        lines.append("  Commander: yes")
    r = l.get("ratings", {})
    if r:
        lines.append(f"  Ratings:   F:{r.get('F','-')} S:{r.get('S','-')} L:{r.get('L','-')} C:{r.get('C','-')}")
    lines.append(f"  Seats:     {', '.join(l.get('seats', [])) or '-'}")
    lines.append(f"  Forces:    {_fmt_forces(l.get('forces', {}))}")
    lines.append(f"  Assets:    {_fmt_assets(l.get('assets', {}))}")
    vassals = l.get("vassals", [])
    if vassals:
        lines.append("  Vassals:")
        for v in vassals:
            mark = "+" if v.get("ready") else ("-" if v.get("on_mat") else "x")
            seats = v.get("seats") or [v.get("seat") or ""]
            seat_str = "/".join(s for s in seats if s)
            lines.append(
                f"    [{mark}] {v['name']:30s} @ {seat_str:30s} SR:{v.get('service_rating','-')} "
                f"[{_fmt_forces(v.get('forces', {}))}]"
            )
    capabilities = l.get("capabilities", [])
    if capabilities:
        lines.append(f"  Capabilities: {', '.join(capabilities)}")
    if l.get("notes"):
        lines.append(f"  Notes: {l['notes']}")
    return "\n".join(lines)


def render_locale(state: dict[str, Any], locale_name: str) -> str:
    locales = state.get("locales", {})
    if locale_name not in locales:
        return f"Locale {locale_name!r} not found. Valid names: {sorted(locales)[:10]}..."
    loc = locales[locale_name]
    lines = [
        f"{locale_name} [{loc['type']}, {loc['allegiance']}, {loc['region']}]"
        + (" Port" if loc.get("port") else "")
        + (f" Leading City ({loc['leading_city']})" if loc.get("leading_city") else ""),
    ]
    if loc.get("current_allegiance"):
        lines.append("  Allegiance markers: " + ", ".join(
            f"{m['value']} VP {m['side']}" for m in loc["current_allegiance"]
        ))
    for f in ("ravaged", "ruins"):
        if loc.get(f):
            lines.append(f"  {f.title()}: {loc[f]}")
    if loc.get("siege"):
        lines.append("  Siege: " + ", ".join(
            f"{s.get('count', 1)} {s['side']} ({s.get('color', '?')})" for s in loc["siege"]
        ))
    if loc.get("bypass"):
        lines.append("  Bypass: " + ", ".join(s.get("side", "?") for s in loc["bypass"]))
    if loc.get("siegeworks"):
        lines.append(f"  Siegeworks: {loc['siegeworks']}")
    lords_here = loc.get("lords_present", [])
    if lords_here:
        lines.append("  Lords present:")
        for lid in lords_here:
            l = state["lords"].get(lid, {"name": lid})
            lines.append(f"    - {l.get('name', lid)} ({l.get('side', '?')})")
    adj = sd.adjacent_to(locale_name)
    if adj:
        lines.append("  Adjacent: " + ", ".join(f"{n} ({w})" for n, w in adj))
    return "\n".join(lines)


def render_calendar(state: dict[str, Any]) -> str:
    cal = state.get("calendar", {})
    lords = state.get("lords", {})
    lines = [
        f"Calendar — Levy@{cal.get('levy_box')} End@{cal.get('end_box') or 'variable'}",
        ""
    ]
    boxes = cal.get("boxes", {})
    for n in sd.CALENDAR_BOXES:
        box = boxes.get(str(n), {})
        bits = []
        if box.get("markers"):
            bits.append("[" + ",".join(box["markers"]).upper() + "]")
        if box.get("victory"):
            bits.append("VP:" + "/".join(box["victory"]))
        if box.get("cylinders"):
            names = [lords.get(lid, {"name": lid})["name"] for lid in box["cylinders"]]
            bits.append("Cyl: " + ", ".join(names))
        if box.get("services"):
            names = [lords.get(lid, {"name": lid})["name"] for lid in box["services"]]
            bits.append("Svc: " + ", ".join(names))
        marker = " ".join(bits) if bits else "(empty)"
        lines.append(f"  Box {n:>2}: {marker}")
    for edge in ("off_left", "off_right", "off_left_service", "off_right_service"):
        items = cal.get(edge, [])
        if items:
            names = [lords.get(lid, {"name": lid})["name"] for lid in items]
            lines.append(f"  {edge}: " + ", ".join(names))
    return "\n".join(lines)


def render_decks(state: dict[str, Any]) -> str:
    decks = state.get("decks", {})
    lines = ["Deck composition"]
    for side in ("guelph", "ghibelline"):
        d = decks.get(side, {})
        lines.append(f"  {side}:")
        lines.append(f"    AoW deck:    {len(d.get('aow_deck', []))} cards")
        lines.append(f"    AoW discard: {len(d.get('aow_discard', []))} cards")
        lines.append(f"    Held events: {len(d.get('aow_held', []))} cards")
        lines.append(f"    Command:     {len(d.get('command_deck', []))} cards")
        lines.append(f"    Treachery set-aside: {len(d.get('treachery_set_aside', []))} cards")
    caps = state.get("capabilities_in_play", [])
    if caps:
        lines.append("")
        lines.append("Capabilities in play:")
        for c in caps:
            scope = c.get("scope", "?")
            lord = f" on {c['lord_id']}" if c.get("lord_id") else ""
            lines.append(f"  - [{c.get('side', '?')}] {c.get('id', '?')} {c.get('name', '')} ({scope}{lord})")
    return "\n".join(lines)
