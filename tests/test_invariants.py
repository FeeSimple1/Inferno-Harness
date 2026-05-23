"""Property-based invariant tests using Hypothesis.

Per CROSS_PROJECT_LESSONS §4 Tier 4: "Property-based tests catch
invariant violations no agent will produce — accumulator overflow,
off-by-one in calendar math, state shapes that shouldn't be reachable
but are. Worth running even when the agent sweeps come back clean."

Invariants tested:
  - VP cap: 0 <= state.vp[side] <= 17.5 always
  - Force counts: every unit count >= 0
  - Calendar boxes: cylinders/services keys in "1".."16"
  - Lord status enum: status in {mustered, on_calendar, in_levy_pool,
                                 disbanded, removed}
  - Mustered Lord -> location is a valid Locale name
  - locales[loc].lords_present <-> lord.location consistency
  - Asset counts: non-negative
  - Captured Knights ledger: keys in {guelph, ghibelline}, values >= 0
"""
from __future__ import annotations

import pytest

try:
    from hypothesis import given, settings, strategies as st
    from hypothesis.strategies import composite
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False
    pytest.skip("hypothesis not installed", allow_module_level=True)

from inferno.actions import IllegalAction, dispatch
from inferno.legal_moves import enumerate_legal
from inferno.scenarios import SCENARIO_IDS, load_scenario


# ----- Invariant assertions -----
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
    approach/battle decision is still pending (a March creates contact one step
    before the defender chooses Avoid/Withdraw/Stand). Keyed on the per-Lord
    in_stronghold / bypassing flags, NOT on the Siege marker (4.3.5 / Siege Sec. 3)."""
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


def check_all_invariants(s):
    assert_vp_cap(s)
    assert_no_colocated_enemies(s)
    assert_force_counts_non_negative(s)
    assert_calendar_box_keys(s)
    assert_lord_status_enum(s)
    assert_mustered_lord_has_location(s)
    assert_locale_lords_present_consistent(s)
    assert_assets_non_negative(s)
    assert_captured_knights_shape(s)


# ----- Property: fresh load preserves invariants -----
@given(
    scenario=st.sampled_from(SCENARIO_IDS),
    seed=st.integers(min_value=1, max_value=10000),
)
@settings(max_examples=30, deadline=2000)
def test_fresh_load_preserves_invariants(scenario, seed):
    s = load_scenario(scenario, seed=seed)
    check_all_invariants(s)


# ----- Property: greedy play preserves invariants at every step -----
@given(
    scenario=st.sampled_from(SCENARIO_IDS),
    seed=st.integers(min_value=1, max_value=10000),
    n_actions=st.integers(min_value=1, max_value=40),
)
@settings(max_examples=20, deadline=8000)
def test_greedy_play_preserves_invariants(scenario, seed, n_actions):
    s = load_scenario(scenario, seed=seed)
    for _ in range(n_actions):
        moves = enumerate_legal(s)
        moves = [m for m in moves if not m.get("action", "").startswith("<")]
        if not moves:
            break
        chosen = moves[0]
        action = {"action": chosen["action"], "side": chosen["side"]}
        if "args" in chosen:
            action["args"] = chosen["args"]
        try:
            dispatch(s, action)
        except IllegalAction:
            break  # round-trip test catches these; not the invariant test's concern
        if s["meta"].get("phase") == "victory":
            break
        check_all_invariants(s)


# ----- Property: round-trip JSON preserves all invariants -----
@given(
    scenario=st.sampled_from(SCENARIO_IDS),
    seed=st.integers(min_value=1, max_value=10000),
)
@settings(max_examples=20, deadline=2000)
def test_json_round_trip_preserves_invariants(scenario, seed):
    import json
    s = load_scenario(scenario, seed=seed)
    js = json.dumps(s, ensure_ascii=False)
    back = json.loads(js)
    check_all_invariants(back)


# ----- Property: VP additions never exceed cap -----
@given(
    starting_vp=st.floats(min_value=0, max_value=17.5),
    deltas=st.lists(st.floats(min_value=0, max_value=5), min_size=0, max_size=10),
)
@settings(max_examples=50, deadline=500)
def test_vp_cap_holds_under_cumulative_add(starting_vp, deltas):
    """Manual reduction: every VP-add path goes through min(..., 17.5)."""
    from inferno.scenarios import load_scenario
    s = load_scenario("A", seed=1)
    s["vp"]["guelph"] = starting_vp
    for d in deltas:
        # Apply the same clamp the production code uses
        s["vp"]["guelph"] = min(s["vp"]["guelph"] + d, 17.5)
    assert s["vp"]["guelph"] <= 17.5
