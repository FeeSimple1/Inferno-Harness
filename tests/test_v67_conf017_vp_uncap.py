"""v6.7 — CONF-017: end-game winner uses TRUE (uncapped) VP.

RoP 2.2.5 tracks VP with no upper cap (scores over 16½ go off-map past box 16);
5.3 decides the winner by who has MORE VP. _compute_final_vp previously clamped
both sides to 17.5, which could flatten a genuine blowout into a false DRAW.
Now it returns true totals (floor 0); the running track is still clamped by the
caller for the display bound / assert_vp_cap invariant.
"""
from __future__ import annotations

from inferno.actions import _compute_final_vp
from inferno.scenarios import load_scenario


def _clear(s):
    for loc in s["locales"].values():
        loc["current_allegiance"] = []
        loc["ruins"] = None
        loc["ravaged"] = None
    s["captured_carroccio_for_side"] = {}


def test_final_vp_uncapped_preserves_blowout_winner():
    s = load_scenario("A", 1)  # no scenario VP modifier
    _clear(s)
    locs = list(s["locales"])
    s["locales"][locs[0]]["current_allegiance"] = [{"side": "guelph", "value": 1} for _ in range(20)]
    s["locales"][locs[1]]["current_allegiance"] = [{"side": "ghibelline", "value": 1} for _ in range(18)]
    g, h = _compute_final_vp(s)
    assert g == 20.0 and h == 18.0          # uncapped (was clamped to 17.5/17.5)
    assert g > h                            # true winner preserved (old cap => false draw)


def test_final_vp_floor_at_zero():
    s = load_scenario("A", 1)
    _clear(s)
    g, h = _compute_final_vp(s)
    assert g == 0.0 and h == 0.0


def test_scenario_e_doubling_uncapped():
    s = load_scenario("E", 1)
    _clear(s)
    locs = list(s["locales"])
    # 10 Guelph markers -> doubled to 20 under Scenario E 'Resistance'.
    s["locales"][locs[0]]["current_allegiance"] = [{"side": "guelph", "value": 1} for _ in range(10)]
    g, h = _compute_final_vp(s)
    assert g == 20.0                        # doubled, not capped at 17.5
