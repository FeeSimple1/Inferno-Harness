"""v1.7 features: Approach/Besiege modifier consumption (Ambush, Surprise)."""
from __future__ import annotations

import pytest

from inferno.actions import IllegalAction, dispatch
from inferno.scenarios import load_scenario


def _to_command_phase(scenario, seed=1):
    s = load_scenario(scenario, seed=seed)
    for name, side in [
        ("levy_aow_draw","guelph"),("levy_aow_draw","ghibelline"),
        ("levy_pay_done","guelph"),("levy_pay_done","ghibelline"),
        ("levy_disband_done","guelph"),("levy_disband_done","ghibelline"),
        ("levy_muster_done","guelph"),("levy_muster_done","ghibelline"),
        ("levy_cta_skip","guelph"),("levy_cta_skip","ghibelline"),
    ]:
        try:
            dispatch(s, {"action": name, "side": side})
        except IllegalAction:
            pass
    from tests.test_phase3a import _skip_capability_discard, _build_pass_plan
    if s["meta"].get("campaign_step") == "capability_discard":
        _skip_capability_discard(s)
    if s["meta"].get("campaign_step") == "plan":
        _build_pass_plan(s, "guelph")
        _build_pass_plan(s, "ghibelline")
    return s


class TestSurpriseConsumption:
    def test_surprise_places_2_siege_and_auto_storms(self):
        """SMOKE-Inferno-041: F3 Surprise on lone Besiege -> 2 markers + auto-Storm."""
        s = _to_command_phase("A", seed=1)
        # Register a Surprise modifier for Guelph (as if F3 was played)
        s.setdefault("besiege_modifiers_pending", []).append({
            "id": "F3", "side": "guelph", "effect": "surprise_besiege_alone",
        })
        # Move firenze to Volterra (enemy Town, empty)
        s["lords"]["firenze"]["location"] = "Volterra"
        s["locales"]["Firenze"]["lords_present"].remove("firenze")
        s["locales"]["Volterra"]["lords_present"].append("firenze")
        s["plan_stacks"]["guelph"].insert(0, "command_firenze")
        dispatch(s, {"action": "command_reveal", "side": "guelph"})
        r = dispatch(s, {"action": "besiege_or_bypass", "side": "guelph",
                         "args": {"lord_id": "firenze", "choice": "besiege"}})
        # Surprise: 2 Siege markers placed (then auto-Storm may Sack/Ruin them)
        assert "surprise_besiege" in r["state_changes"]
        assert "auto_storm" in r["state_changes"]

    def test_normal_besiege_without_surprise_places_1(self):
        s = _to_command_phase("A", seed=1)
        s["lords"]["firenze"]["location"] = "Volterra"
        s["locales"]["Firenze"]["lords_present"].remove("firenze")
        s["locales"]["Volterra"]["lords_present"].append("firenze")
        s["plan_stacks"]["guelph"].insert(0, "command_firenze")
        dispatch(s, {"action": "command_reveal", "side": "guelph"})
        dispatch(s, {"action": "besiege_or_bypass", "side": "guelph",
                     "args": {"lord_id": "firenze", "choice": "besiege"}})
        assert s["locales"]["Volterra"]["siege"][0]["count"] == 1


class TestAmbushConsumption:
    def _setup_approach(self, seed=1):
        s = _to_command_phase("A", seed=seed)
        # Relocate Siena to Figline so a Firenze march triggers Approach.
        s["locales"]["Siena"]["lords_present"].remove("siena")
        s["locales"]["Figline"]["lords_present"].append("siena")
        s["lords"]["siena"]["location"] = "Figline"
        s["plan_stacks"]["guelph"].insert(0, "command_firenze")
        dispatch(s, {"action": "command_reveal", "side": "guelph"})
        dispatch(s, {"action": "cmd_march", "side": "guelph",
                     "args": {"lord_id": "firenze", "destination": "Figline", "way_type": "road"}})
        return s

    def test_play_ambush_pins_lord(self):
        """SMOKE-Inferno-042: Ambush forces an Avoiding Lord to not avoid."""
        s = self._setup_approach(seed=1)
        # Guelph (attacker) has a pending Ambush modifier
        s.setdefault("approach_modifiers_pending", []).append({
            "id": "F1", "side": "guelph", "effect": "ambush_force_one_stand",
        })
        # Guelph plays Ambush targeting Siena
        r = dispatch(s, {"action": "cmd_play_ambush", "side": "guelph",
                         "args": {"target_lord_id": "siena"}})
        assert r["state_changes"]["ambush_pinned"] == "siena"
        assert s["lords"]["siena"]["flags"]["ambush_forced"] is True
        # Now Siena cannot Avoid
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {"action": "approach_response", "side": "ghibelline",
                         "args": {"lord_id": "siena", "choice": "avoid",
                                  "destination": "San Giovanni"}})
        assert exc.value.code == "AMBUSH_FORCED"

    def test_play_ambush_without_pending_rejected(self):
        s = self._setup_approach(seed=1)
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {"action": "cmd_play_ambush", "side": "guelph",
                         "args": {"target_lord_id": "siena"}})
        assert exc.value.code == "NO_AMBUSH"


# =====================================================================
# v1.7d — Property-based fuzz: one-shot modifier consumption never leaks
# =====================================================================
try:
    from hypothesis import given, settings, strategies as st
    _HYP = True
except ImportError:
    _HYP = False

from inferno.battle import resolve_storm


def _storm_setup(seed=1):
    s = load_scenario("A", seed=seed)
    s["locales"]["Volterra"]["siege"] = [{"side": "guelph", "color": "gold", "count": 3}]
    s["locales"]["Firenze"]["lords_present"].remove("firenze")
    s["locales"]["Volterra"]["lords_present"].append("firenze")
    s["lords"]["firenze"]["location"] = "Volterra"
    return s


if _HYP:  # guard: decorators below reference hypothesis names at class-body eval time
    @pytest.mark.skipif(not _HYP, reason="hypothesis not installed")
    class TestModifierConsumptionFuzz:
        @given(
            n_markers=st.integers(min_value=0, max_value=5),
            value=st.integers(min_value=1, max_value=4),
            seed=st.integers(min_value=1, max_value=500),
        )
        @settings(max_examples=60, deadline=4000)
        def test_storm_walls_minus_always_consumed(self, n_markers, value, seed):
            """SMOKE-Inferno-041 invariant: every one-shot storm_walls_minus
            marker in battle_modifiers_pending is consumed by a single Storm,
            regardless of count or value — the queue never leaks them."""
            s = _storm_setup(seed=seed)
            s["battle_modifiers_pending"] = [
                {"id": f"X{i}", "side": "guelph", "effect": "storm_walls_minus",
                 "value": value}
                for i in range(n_markers)
            ]
            # A non-storm marker must survive untouched.
            s["battle_modifiers_pending"].append(
                {"id": "KEEP", "side": "guelph", "effect": "some_other_effect"})
            result = resolve_storm(
                s, attackers=["firenze"], defenders=[],
                active_id="firenze", locale_name="Volterra",
            )
            leftover = [m for m in s["battle_modifiers_pending"]
                        if m.get("effect") == "storm_walls_minus"]
            assert leftover == [], f"storm_walls_minus leaked: {leftover}"
            assert any(m["id"] == "KEEP" for m in s["battle_modifiers_pending"]), \
                "unrelated modifier was wrongly consumed"
            assert result["mode"] == "storm"

        @given(seed=st.integers(min_value=1, max_value=500))
        @settings(max_examples=40, deadline=4000)
        def test_double_storm_does_not_reapply_consumed_marker(self, seed):
            """A one-shot marker consumed by the first Storm must not affect a
            second Storm (no resurrection from a stale queue)."""
            s = _storm_setup(seed=seed)
            s["battle_modifiers_pending"] = [
                {"id": "OS", "side": "guelph", "effect": "storm_walls_minus",
                 "value": 2}]
            resolve_storm(s, attackers=["firenze"], defenders=[],
                          active_id="firenze", locale_name="Volterra")
            assert not any(m.get("effect") == "storm_walls_minus"
                           for m in s.get("battle_modifiers_pending", []))
            # Rebuild a fresh siege and storm again — must run with no leftover.
            s["locales"]["Volterra"]["siege"] = [
                {"side": "guelph", "color": "gold", "count": 2}]
            r2 = resolve_storm(s, attackers=["firenze"], defenders=[],
                               active_id="firenze", locale_name="Volterra")
            assert r2["mode"] == "storm"
