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
