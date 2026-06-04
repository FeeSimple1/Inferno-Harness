"""v5.5 — the transient Approach breadcrumb (meta.approach_breadcrumb) must be
cleared on every resolution path, not just after a Battle.

cmd_march records meta.approach_breadcrumb = {approached_from, approached_via}
so post-Battle Retreat handling can honour 4.4.3 constraints. The Stand path
clears it after the Battle, but an all-Avoid / all-Withdraw resolution (no
Battle) previously left the stale origin/route in the serialized state, where it
could mislead external consumers or a later code path that consults it.
"""
from __future__ import annotations

from inferno.actions import dispatch
from tests.test_phase3b import _to_command_phase


def _approach(seed=99):
    s = _to_command_phase("A", seed=seed, lord_for_active="firenze")
    siena_loc = s["lords"]["siena"]["location"]
    s["locales"][siena_loc]["lords_present"].remove("siena")
    s["locales"]["Figline"]["lords_present"].append("siena")
    s["lords"]["siena"]["location"] = "Figline"
    dispatch(s, {"action": "cmd_march", "side": "guelph",
                 "args": {"lord_id": "firenze",
                          "destination": "Figline", "way_type": "road"}})
    return s


def test_breadcrumb_set_on_march():
    s = _approach()
    assert s["meta"].get("approach_breadcrumb") == {
        "approached_from": "Firenze", "approached_via": "road"}


def test_breadcrumb_cleared_after_avoid_no_battle():
    s = _approach()
    r = dispatch(s, {"action": "approach_response", "side": "ghibelline",
                     "args": {"lord_id": "siena", "choice": "avoid",
                              "destination": "San Giovanni"}})
    assert r["state_changes"]["approach_resolved"] == "no_battle"
    assert "approach_breadcrumb" not in s["meta"]


def test_breadcrumb_cleared_after_withdraw_no_battle():
    s = _approach()
    # Make Figline a Ghibelline-held Town so Siena may Withdraw into it.
    s["locales"]["Figline"]["allegiance"] = "ghibelline"
    s["locales"]["Figline"]["type"] = "town"
    r = dispatch(s, {"action": "approach_response", "side": "ghibelline",
                     "args": {"lord_id": "siena", "choice": "withdraw"}})
    assert r["state_changes"]["approach_resolved"] == "no_battle"
    assert "approach_breadcrumb" not in s["meta"]


def test_breadcrumb_cleared_after_stand_battle():
    """Control: the Stand path already clears it after the Battle."""
    s = _approach()
    r = dispatch(s, {"action": "approach_response", "side": "ghibelline",
                     "args": {"lord_id": "siena", "choice": "stand"}})
    assert r["state_changes"]["approach_resolved"] == "battle"
    assert "approach_breadcrumb" not in s["meta"]
