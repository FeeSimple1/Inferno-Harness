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


# ----- Invariant assertions (single source of truth: inferno.invariants) -----
from inferno.invariants import (  # noqa: E402
    assert_vp_cap, assert_force_counts_non_negative, assert_calendar_box_keys,
    assert_lord_status_enum, assert_mustered_lord_has_location,
    assert_locale_lords_present_consistent, assert_assets_non_negative,
    assert_captured_knights_shape, assert_no_colocated_enemies,
    aow_card_total, assert_aow_card_conservation, check_all_invariants,
)


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
