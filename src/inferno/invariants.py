"""Always-on state invariants for the Inferno harness.

SMOKE-Inferno-096: these live in the runtime package (stdlib-only, no test
dependencies) so any consumer -- the test suite, a fuzzer, or an external
LLM/agent doing a bug-hunt -- can assert them after every applied action without
installing pytest/hypothesis. `tests/test_invariants.py` re-exports these as the
single source of truth.
"""
from __future__ import annotations

import collections


def assert_vp_cap(s):
    for side in ("guelph", "ghibelline"):
        v = s["vp"].get(side, 0)
        assert 0 <= v <= 17.5, f"VP for {side} = {v} out of [0, 17.5]"


def assert_force_counts_non_negative(s):
    for lid, lord in s["lords"].items():
        for unit, count in (lord.get("forces") or {}).items():
            assert isinstance(count, int) and count >= 0, \
                f"{lid} forces[{unit}] = {count} (not non-negative int)"
        for unit, count in (lord.get("routed_units") or {}).items():
            assert isinstance(count, int) and count >= 0, \
                f"{lid} routed_units[{unit}] = {count}"


def assert_calendar_box_keys(s):
    for box_str in s["calendar"]["boxes"]:
        n = int(box_str)
        assert 1 <= n <= 16, f"Calendar box key {box_str} out of [1, 16]"


def assert_lord_status_enum(s):
    valid = {"mustered", "on_calendar", "in_levy_pool", "disbanded", "removed"}
    for lid, lord in s["lords"].items():
        assert lord.get("status") in valid, \
            f"{lid} has invalid status: {lord.get('status')!r}"


def assert_mustered_lord_has_location(s):
    for lid, lord in s["lords"].items():
        if lord.get("status") == "mustered":
            loc = lord.get("location")
            assert loc is not None and loc in s["locales"], \
                f"Mustered {lid} has location {loc!r} not in locales"


def assert_locale_lords_present_consistent(s):
    """Every Mustered Lord whose location = L must appear in
    s['locales'][L]['lords_present'], and vice versa."""
    for lid, lord in s["lords"].items():
        if lord.get("status") == "mustered":
            loc = s["locales"].get(lord["location"], {})
            assert lid in loc.get("lords_present", []), \
                f"{lid} at {lord['location']} but missing from lords_present"
    for loc_name, loc in s["locales"].items():
        for lid in loc.get("lords_present", []):
            lord = s["lords"].get(lid)
            assert lord is not None, f"lords_present at {loc_name} has unknown {lid}"
            assert lord.get("location") == loc_name, \
                f"{lid} in {loc_name}.lords_present but location={lord.get('location')}"


def assert_assets_non_negative(s):
    for lid, lord in s["lords"].items():
        for asset, count in (lord.get("assets") or {}).items():
            assert isinstance(count, int) and count >= 0, \
                f"{lid} assets[{asset}] = {count}"


def assert_captured_knights_shape(s):
    cap = s.get("captured_knights", {})
    for side, units in cap.items():
        assert side in ("guelph", "ghibelline"), f"bad captured side {side!r}"
        for unit, count in units.items():
            assert isinstance(count, int) and count >= 0


def assert_no_colocated_enemies(s):
    """SMOKE-Inferno-089: no two opposing MUSTERED Lords may share a Locale while
    BOTH are outside a Stronghold (besieged-inside vs besieger-outside is the only
    legal contested config). Excluded: the brief mid-Approach transient while an
    approach/battle decision is still pending. Keyed on the per-Lord in_stronghold
    / bypassing flags, NOT on the Siege marker (4.3.5 / Siege Sec. 3)."""
    pend = s.get("pending") or []
    if any(p.get("type") in ("approach_response", "battle") for p in pend):
        return
    for loc_name, loc in s["locales"].items():
        sides = {"guelph": [], "ghibelline": []}
        for lid in loc.get("lords_present", []):
            lo = s["lords"].get(lid)
            if (lo and lo.get("status") == "mustered"
                    and not lo.get("flags", {}).get("in_stronghold")
                    and not lo.get("flags", {}).get("bypassing")):
                sides[lo["side"]].append(lid)
        assert not (sides["guelph"] and sides["ghibelline"]), (
            f"co-located enemies at {loc_name}: {sides} "
            f"(both outside a Stronghold, no pending approach/battle)")


def aow_card_total(s, side):
    """SMOKE-Inferno-096: count a side's own AoW cards across every pool (deck,
    discard, held, capabilities-in-play, Lord mats, active events). Always 26;
    drift means a card was lost or duplicated. Mirrors test_v39_conservation."""
    c = collections.Counter()
    d = s["decks"][side]
    for cid in d.get("aow_deck", []) + d.get("aow_discard", []) + d.get("aow_held", []):
        c[cid] += 1
    for cap in s.get("capabilities_in_play", []):
        if cap.get("side") == side:
            c[cap["id"]] += 1
    for lid, l in s["lords"].items():
        if l.get("side") == side:
            for cid in l.get("capabilities", []) or []:
                c[cid] += 1
    for kind in ("immediate", "this_levy", "this_campaign"):
        for e in (s.get("active_events", {}).get(kind, []) or []):
            cid = e.get("id")
            if e.get("side") == side and isinstance(cid, str) and cid[:1] in ("F", "S"):
                c[cid] += 1
    # A4: a This-Lord Capability awaiting its placement choice is still in play.
    for pnd in (s.get("pending", []) or []):
        if pnd.get("type") == "capability_placement" and pnd.get("side") == side:
            cid = pnd.get("card_id")
            if isinstance(cid, str):
                c[cid] += 1
    pfx = "F" if side == "guelph" else "S"
    return sum(n for x, n in c.items()
               if isinstance(x, str) and x[:1] == pfx and x[1:].isdigit())


def assert_aow_card_conservation(s):
    for side in ("guelph", "ghibelline"):
        total = aow_card_total(s, side)
        assert total == 26, f"AoW card drift: {side} total = {total} (expected 26)"


def assert_lord_side_enum(s):
    for lid, lord in s["lords"].items():
        assert lord.get("side") in ("guelph", "ghibelline"), \
            f"{lid} has invalid side {lord.get('side')!r}"


def assert_no_duplicate_lords_present(s):
    for loc_name, loc in s["locales"].items():
        lp = loc.get("lords_present", [])
        assert len(lp) == len(set(lp)), \
            f"duplicate lord ids in {loc_name}.lords_present: {lp}"


def assert_calendar_cylinder_consistency(s):
    """v6.12 (injection-fuzz round): the Calendar's per-box cylinder lists and
    each Lord's status/calendar_box are redundant encodings — they must agree.
    - A Lord appears in AT MOST ONE box's cylinders list.
    - status == 'on_calendar' => his calendar_box is a box that lists him.
    - A Mustered/removed Lord appears in NO box's cylinders list."""
    seen: dict[str, str] = {}
    for box_str, box in s["calendar"]["boxes"].items():
        for lid in box.get("cylinders", []):
            assert lid not in seen, \
                f"cylinder for {lid} in two Calendar boxes: {seen[lid]} and {box_str}"
            seen[lid] = box_str
    # Cylinders pushed off the track (Exiles shifts, card effects) live in the
    # off_left / off_right lists with calendar_box=None — legal, but a Lord may
    # hold only ONE cylinder position across boxes + off-lists.
    for off_key in ("off_left", "off_right"):
        for lid in s["calendar"].get(off_key, []) or []:
            assert lid not in seen, \
                f"cylinder for {lid} both in box {seen[lid]} and {off_key}"
            seen[lid] = off_key
    for lid, lord in s["lords"].items():
        st = lord.get("status")
        if st == "on_calendar":
            cb = lord.get("calendar_box")
            if cb is None:
                assert seen.get(lid) in ("off_left", "off_right"), \
                    (f"{lid} on_calendar with no calendar_box and no off-track "
                     f"cylinder (found: {seen.get(lid)!r})")
            else:
                assert seen.get(lid) == str(cb), \
                    (f"{lid} on_calendar with calendar_box={cb!r} but cylinder "
                     f"found in {seen.get(lid)!r}")
        elif st == "mustered":
            assert lid not in seen, \
                f"Mustered {lid} still has a cylinder in {seen[lid]}"


def assert_service_marker_consistency(s):
    """Service markers: each Lord in at most one box's services list, and the
    lists must agree with lord.service_box (for Mustered Lords)."""
    seen: dict[str, str] = {}
    for box_str, box in s["calendar"]["boxes"].items():
        for lid in box.get("services", []):
            assert lid not in seen, \
                f"Service marker for {lid} in two boxes: {seen[lid]} and {box_str}"
            seen[lid] = box_str
    for lid, lord in s["lords"].items():
        if lord.get("status") == "mustered":
            sb = lord.get("service_box")
            if sb is not None:
                assert seen.get(lid) == str(sb), \
                    (f"Mustered {lid} service_box={sb} but Service marker in "
                     f"box {seen.get(lid)!r}")


def assert_locale_marker_sanity(s):
    """Map-marker structural rules (1.3.1 / 1.4.4 / 4.3.5 / 4.5.2):
    - Ruins eliminate the Stronghold: no Siege, Bypass, or Allegiance markers
      may remain there (Sack removes them; Lords never Besiege Ruins).
    - Outposts are never Besieged/Ruined (only the owning Lord may enter).
    - Siege markers: 1..4 total, color matches side (purple=Guelph, gold=Ghibelline; RoP 1.1).
    - Allegiance markers: all one side, OPPOSITE the printed Allegiance
      (1.4.4 adds markers only to a Stronghold of the opposite printed
      Allegiance, else removes), at most Stronghold Value markers."""
    from . import static_data as sd
    color_of = {"guelph": "purple", "ghibelline": "gold"}
    for name, loc in s["locales"].items():
        siege = loc.get("siege") or []
        if loc.get("ruins"):
            assert not siege, f"Ruins {name} has Siege markers"
            assert not (loc.get("bypass") or []), f"Ruins {name} has Bypass markers"
            assert not (loc.get("current_allegiance") or []), \
                f"Ruins {name} has Allegiance markers"
        if loc.get("type") == "outpost":
            assert not siege, f"Outpost {name} has Siege markers"
            assert not loc.get("ruins"), f"Outpost {name} is Ruined"
        total = sum(m.get("count", 1) for m in siege)
        assert 0 <= total <= 4, f"{name} Siege marker count {total} out of [0,4]"
        for m in siege:
            assert m.get("side") in ("guelph", "ghibelline"), \
                f"{name} Siege marker with bad side {m.get('side')!r}"
            assert m.get("count", 1) >= 1, f"{name} Siege marker count < 1"
            if m.get("color"):
                assert m["color"] == color_of[m["side"]], \
                    f"{name} Siege color {m['color']!r} != side {m['side']}"
        markers = loc.get("current_allegiance") or []
        if markers:
            sides = {m.get("side") for m in markers}
            assert len(sides) == 1, f"{name} mixed Allegiance markers: {sides}"
            mside = next(iter(sides))
            assert mside in ("guelph", "ghibelline"), \
                f"{name} Allegiance marker bad side {mside!r}"
            assert mside != loc.get("allegiance"), \
                (f"{name} has Allegiance markers of its own printed side "
                 f"({mside}) — 1.4.4 removes rather than stacks")
            size = sd.STRONGHOLDS.get(loc.get("type"), {}).get("size", 0)
            assert len(markers) <= max(size, 0), \
                f"{name} has {len(markers)} Allegiance markers > Value {size}"


def assert_stronghold_inside_capacity(s):
    """4.3.4 / 4.5.1: at most Stronghold-Size Lords may be INSIDE a Stronghold
    (Withdrawal, Urban-Army Muster and Bypassed Muster all respect the cap);
    nobody can be 'inside' at Ruins or an Outpost."""
    from . import static_data as sd
    for name, loc in s["locales"].items():
        inside = [lid for lid in loc.get("lords_present", [])
                  if s["lords"].get(lid, {}).get("status") == "mustered"
                  and s["lords"][lid].get("flags", {}).get("in_stronghold")]
        if not inside:
            continue
        assert not loc.get("ruins"), f"{name} is Ruins but {inside} are inside"
        size = sd.STRONGHOLDS.get(loc.get("type"), {}).get("size", 0)
        assert len(inside) <= size, \
            f"{name} (Size {size}) has {len(inside)} Lords inside: {inside}"


def assert_bypassing_flag_consistency(s):
    """A Lord flagged `bypassing = L` must actually be a Mustered Lord AT L,
    and L must bear a Bypass marker. A stale flag (e.g. left behind by a
    March-out) silently exempts its Lord from the co-location invariant."""
    for lid, lord in s["lords"].items():
        bl = (lord.get("flags") or {}).get("bypassing")
        if not bl:
            continue
        assert lord.get("status") == "mustered" and lord.get("location") == bl, \
            (f"{lid} flagged bypassing={bl!r} but status="
             f"{lord.get('status')!r} location={lord.get('location')!r}")
        loc = s["locales"].get(bl) or {}
        assert loc.get("bypass"), f"{lid} bypassing {bl} but no Bypass marker there"


def assert_meta_sanity(s):
    meta = s.get("meta", {})
    ra = meta.get("rng_advance", 0)
    assert isinstance(ra, int) and ra >= 0, f"rng_advance = {ra!r}"
    turn = meta.get("turn")
    assert isinstance(turn, int) and 1 <= turn <= 16, f"meta.turn = {turn!r}"
    assert meta.get("active_player") in ("guelph", "ghibelline", None), \
        f"active_player = {meta.get('active_player')!r}"


def check_all_invariants(s):
    """Run the full always-on battery. Cheap; call after every applied action."""
    assert_vp_cap(s)
    assert_no_colocated_enemies(s)
    assert_force_counts_non_negative(s)
    assert_calendar_box_keys(s)
    assert_lord_status_enum(s)
    assert_mustered_lord_has_location(s)
    assert_locale_lords_present_consistent(s)
    assert_assets_non_negative(s)
    assert_captured_knights_shape(s)
    assert_aow_card_conservation(s)
    assert_lord_side_enum(s)
    assert_no_duplicate_lords_present(s)
    assert_calendar_cylinder_consistency(s)
    assert_service_marker_consistency(s)
    assert_locale_marker_sanity(s)
    assert_stronghold_inside_capacity(s)
    assert_bypassing_flag_consistency(s)
    assert_meta_sanity(s)


def assert_combat_engaged(result):
    """SMOKE-Inferno-098 tripwire for the SMOKE-097 class: a combat in which BOTH
    sides brought fighting units must resolve at least one Strike/roll. A Storm
    that returns `both_sides_armed=True` but `engaged=False` means the attacker
    dealt zero hits despite a defended target (the Garrison-only-Storm no-op bug).
    No-ops on combat results that don't carry the tripwire keys (e.g. battles)."""
    if result is None or not isinstance(result, dict):
        return
    if result.get("both_sides_armed") and result.get("engaged") is False:
        raise AssertionError(
            f"combat at {result.get('locale')!r} had forces on both sides but "
            f"resolved ZERO strikes (mode={result.get('mode')}, outcome="
            f"{result.get('outcome') or result.get('winner')}) — SMOKE-097 class")
