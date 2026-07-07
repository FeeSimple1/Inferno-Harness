"""Phase 3e tests: End-of-Campaign 4.9 substeps."""
from __future__ import annotations

import pytest

from inferno.actions import IllegalAction, dispatch
from inferno.scenarios import load_scenario


def _to_end_campaign(scenario="A", seed=1, turn_override=None):
    s = load_scenario(scenario, seed=seed)
    # Force turn to a Grow box for grow tests
    if turn_override is not None:
        s["meta"]["turn"] = turn_override
        s["calendar"]["levy_box"] = turn_override
    # Drive through Levy + Campaign skip
    for name, side in [
        ("levy_aow_draw","guelph"),("levy_aow_draw","ghibelline"),
        ("levy_pay_done","guelph"),("levy_pay_done","ghibelline"),
        ("levy_disband_done","guelph"),("levy_disband_done","ghibelline"),
        ("levy_muster_done","guelph"),("levy_muster_done","ghibelline"),
        ("levy_cta_skip","guelph"),("levy_cta_skip","ghibelline"),
    ]:
        dispatch(s, {"action": name, "side": side})
    from tests.test_phase3a import _skip_capability_discard, _build_pass_plan
    _skip_capability_discard(s)
    _build_pass_plan(s, "guelph")
    _build_pass_plan(s, "ghibelline")
    # Reveal all cards (every Lord card is Pass for now)
    safety = 30
    while s["meta"].get("campaign_step") == "command_phase" and safety > 0:
        dispatch(s, {"action": "command_reveal", "side": s["meta"]["active_player"]})
        safety -= 1
    return s


class TestGrow:
    def test_grow_skip_on_non_grow_turn(self):
        s = _to_end_campaign("A", seed=1)
        # Turn 1 is not a Grow turn -> only end_grow_skip
        dispatch(s, {"action": "end_grow_skip", "side": "guelph"})
        dispatch(s, {"action": "end_grow_skip", "side": "ghibelline"})
        # After both sides skip, "grow" is in done
        assert "grow" in s["meta"]["end_substep_done"]

    def test_grow_on_grow_turn_reduces_ravages(self):
        s = _to_end_campaign("A", seed=1, turn_override=2)  # Apr-May = Grow
        # Plant 4 enemy (purple = Guelph-owned, CONF-039) Ravage markers on
        # Ghibelline locales
        for loc_name in ("Volterra", "Asinalunga", "Cortona", "Montepulciano"):
            if loc_name in s["locales"]:
                s["locales"][loc_name]["ravaged"] = "purple"
        # Pre-set VP for Guelphs reflecting 4 Ravages
        s["vp"]["guelph"] = 2.0
        # Ghibelline's Grow removes Guelph (enemy) Ravage markers: ceil(4/2) = 2 kept, 2 removed
        # Force Ghibelline to go: dispatch Guelph-grow-skip first
        # Actually flow: Guelph goes first. For Guelph, enemy = ghibelline.
        # We planted purple = Guelph color, so for Guelph's grow, enemy_color = gold, n=0.
        # Better to test from Ghibelline's perspective.
        # Guelph has no enemy ravages -> no-op
        dispatch(s, {"action": "end_grow", "side": "guelph", "args": {"keep": []}})
        # Ghibelline now: enemy_color = "purple", n = 4. keep_count = ceil(4/2) = 2.
        kept = ["Volterra", "Asinalunga"]
        r = dispatch(s, {"action": "end_grow", "side": "ghibelline", "args": {"keep": kept}})
        assert sorted(r["state_changes"]["grow_kept"]) == sorted(kept)
        assert sorted(r["state_changes"]["grow_removed"]) == sorted(["Cortona", "Montepulciano"])


class TestRansom:
    def test_no_captures_auto_advance(self):
        s = _to_end_campaign("A", seed=1)
        dispatch(s, {"action": "end_grow_skip", "side": "guelph"})
        dispatch(s, {"action": "end_grow_skip", "side": "ghibelline"})
        # No captures recorded
        dispatch(s, {"action": "end_ransom", "side": "guelph", "args": {"pay": True}})
        dispatch(s, {"action": "end_ransom", "side": "ghibelline", "args": {"pay": True}})
        assert "ransom" in s["meta"]["end_substep_done"]


class TestGameCheck:
    def test_game_end_on_last_turn(self):
        # Scenario A: end_box = 3, so last Turn is 2. Place turn at 2.
        s = _to_end_campaign("A", seed=1, turn_override=2)
        dispatch(s, {"action": "end_grow", "side": "guelph", "args": {"keep": []}})
        dispatch(s, {"action": "end_grow", "side": "ghibelline", "args": {"keep": []}})
        dispatch(s, {"action": "end_ransom", "side": "guelph", "args": {"pay": True}})
        dispatch(s, {"action": "end_ransom", "side": "ghibelline", "args": {"pay": True}})
        # Game-end check triggers Victory since 2 >= end_box(3)-1 = 2
        dispatch(s, {"action": "end_game_check", "side": "guelph"})
        assert s["meta"]["phase"] == "victory"


class TestRepair:
    def test_repair_removes_one_from_3_4_marker_town_or_city(self):
        s = _to_end_campaign("A", seed=1)
        # Plant a 4-marker Siege at Volterra (Town)
        s["locales"]["Volterra"]["siege"] = [
            {"side": "guelph", "color": "purple", "count": 4}
        ]
        # Walk through Grow/Ransom skips
        dispatch(s, {"action": "end_grow_skip", "side": "guelph"})
        dispatch(s, {"action": "end_grow_skip", "side": "ghibelline"})
        dispatch(s, {"action": "end_ransom", "side": "guelph", "args": {"pay": True}})
        dispatch(s, {"action": "end_ransom", "side": "ghibelline", "args": {"pay": True}})
        dispatch(s, {"action": "end_game_check", "side": "guelph"})
        # Now Repair (not per-side)
        r = dispatch(s, {"action": "end_repair", "side": "guelph"})
        # Volterra was 4 markers -> reduced to 3
        new_total = sum(s_["count"] for s_ in s["locales"]["Volterra"]["siege"])
        assert new_total == 3
        assert "Volterra" in r["state_changes"]["repaired"]

    def test_repair_skips_castle(self):
        s = _to_end_campaign("A", seed=1)
        # Plant a 4-marker Siege at Vicopisano (Castle)
        s["locales"]["Vicopisano"]["siege"] = [
            {"side": "guelph", "color": "purple", "count": 4}
        ]
        dispatch(s, {"action": "end_grow_skip", "side": "guelph"})
        dispatch(s, {"action": "end_grow_skip", "side": "ghibelline"})
        dispatch(s, {"action": "end_ransom", "side": "guelph", "args": {"pay": True}})
        dispatch(s, {"action": "end_ransom", "side": "ghibelline", "args": {"pay": True}})
        dispatch(s, {"action": "end_game_check", "side": "guelph"})
        r = dispatch(s, {"action": "end_repair", "side": "guelph"})
        # Castle does NOT erode
        new_total = sum(s_["count"] for s_ in s["locales"]["Vicopisano"]["siege"])
        assert new_total == 4
        assert "Vicopisano" not in r["state_changes"]["repaired"]


class TestReset:
    def test_reset_advances_calendar_and_re_enters_levy(self):
        s = _to_end_campaign("A", seed=1)
        # Walk through skip-everything to Reset
        dispatch(s, {"action": "end_grow_skip", "side": "guelph"})
        dispatch(s, {"action": "end_grow_skip", "side": "ghibelline"})
        dispatch(s, {"action": "end_ransom", "side": "guelph", "args": {"pay": True}})
        dispatch(s, {"action": "end_ransom", "side": "ghibelline", "args": {"pay": True}})
        dispatch(s, {"action": "end_game_check", "side": "guelph"})
        dispatch(s, {"action": "end_repair", "side": "guelph"})
        dispatch(s, {"action": "end_waste", "side": "guelph"})
        dispatch(s, {"action": "end_waste", "side": "ghibelline"})
        before = s["meta"]["turn"]
        dispatch(s, {"action": "end_reset", "side": "guelph"})
        # Scenario A ends at box 3 -> Reset from turn 1 -> turn 2 (still pre-end)
        # turn 2 < end_box 3 so Levy resumes.
        if before == 1 and s["calendar"].get("end_box") == 3:
            assert s["meta"]["turn"] == 2
            assert s["meta"]["phase"] == "levy"
