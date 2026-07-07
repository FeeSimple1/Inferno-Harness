"""v3.8 — audit of the 52 AoW Capabilities, core Battle mechanics, and Call to
Arms. Most were conformant; two defects fixed: a latent capability-hook
mislabel (SMOKE-085) and the missing Scenario D CtA Escalation rule
(SMOKE-086). These tests lock the fixes + anchor the conformant findings.
"""
from __future__ import annotations

from inferno import card_effects as ce
from inferno import battle
from inferno.actions import _cta_trigger_met
from inferno.scenarios import load_scenario


# =====================================================================
# SMOKE-085 — Siege Towers no longer grants a spurious storm_walls_minus
# =====================================================================
class TestCapabilityHookMislabel:
    def test_siege_towers_in_play_does_not_reduce_walls(self):
        s = load_scenario("A", 1)
        s["capabilities_in_play"].append(
            {"id": "F3", "side": "guelph", "scope": "side_wide", "name": "Siege Towers"})
        # Siege Towers is a strike-FIRST effect, not a Walls reduction.
        assert ce.active_capabilities_for(s, "storm_walls_minus") == []

    def test_war_engineers_in_play_does_not_reduce_walls(self):
        s = load_scenario("A", 1)
        s["capabilities_in_play"].append(
            {"id": "F5", "side": "guelph", "scope": "side_wide", "name": "War Engineers"})
        assert ce.active_capabilities_for(s, "storm_walls_minus") == []

    def test_siege_towers_strike_first_still_works_by_name(self):
        s = load_scenario("A", 1)
        s["lords"]["firenze"].setdefault("capabilities", []).append("F3")  # Siege Towers
        positions = {"attacker": {"center": "firenze", "left": None, "right": None},
                     "defender": {"center": None, "left": None, "right": None}}
        # R2 attacker with Siege Towers -> strikes first; R1 -> not.
        assert battle._siege_towers_strike_first_in_storm(s, "attacker", 2, positions) == "firenze"
        assert battle._siege_towers_strike_first_in_storm(s, "attacker", 1, positions) is None

    def test_trebuchets_walls_minus_still_works_by_name(self):
        s = load_scenario("A", 1)
        s["lords"]["firenze"].setdefault("capabilities", []).append("F4")  # Trebuchets
        s["lords"]["firenze"]["forces"] = {"Cavalieri": 1}
        s["locales"]["Volterra"]["siege"] = [{"side": "guelph", "color": "purple", "count": 3}]
        red = battle._trebuchets_walls_reduction(s, "Volterra", [], ["firenze"], "storm")
        assert red == 1  # 3-4 Siege + Trebuchets -> Walls -1
        s["locales"]["Volterra"]["siege"] = [{"side": "guelph", "color": "purple", "count": 2}]
        assert battle._trebuchets_walls_reduction(s, "Volterra", [], ["firenze"], "storm") == 0


# =====================================================================
# Capability strike-modifier conformance anchors (Feditori cap 4 vs 3, etc.)
# =====================================================================
class TestCapabilityStrikeNumerics:
    def test_feditori_cap_4_guelph_3_ghibelline(self):
        s = load_scenario("A", 1)
        # Guelph Feditori on firenze: 6 Cavalieri capped at +4 in R1 Battle.
        s["lords"]["firenze"].setdefault("capabilities", []).append("F6")  # Feditori
        g = battle._capability_strike_modifier(
            s, "firenze", {"Cavalieri": 6}, "atk_horse_melee", 1, "battle")
        assert g == 4
        # Ghibelline Feditori on siena: capped at +3.
        s["lords"]["siena"].setdefault("capabilities", []).append("S6")
        h = battle._capability_strike_modifier(
            s, "siena", {"Cavalieri": 6}, "def_horse_melee", 1, "battle")
        assert h == 3

    def test_feditori_only_rounds_1_2(self):
        s = load_scenario("A", 1)
        s["lords"]["firenze"].setdefault("capabilities", []).append("F6")
        r3 = battle._capability_strike_modifier(
            s, "firenze", {"Cavalieri": 4}, "atk_horse_melee", 3, "battle")
        assert r3 == 0  # no Feditori bonus from Round 3

    def test_luceria_militia_x1_5_cap_3(self):
        s = load_scenario("A", 1)
        s["lords"]["siena"].setdefault("capabilities", []).append("S7")  # Luceria
        v = battle._capability_strike_modifier(
            s, "siena", {"Militia": 5}, "def_archery", 1, "battle")
        assert v == 3 * 1.5  # capped at 3 Militia, x1.5


# =====================================================================
# Battle initiative order conformance
# =====================================================================
def test_battle_initiative_six_step_order():
    assert battle.BATTLE_STRIKE_ORDER == [
        "def_archery", "atk_archery",
        "def_horse_melee", "atk_horse_melee",
        "def_foot_melee", "atk_foot_melee",
    ]


# =====================================================================
# SMOKE-086 — Scenario D Escalation: either side declares CtA in first Levy
# =====================================================================
class TestScenarioDEscalation:
    def test_first_levy_either_side_eligible(self):
        s = load_scenario("D", 1)  # starts at turn 9
        assert _cta_trigger_met(s, "guelph")[0] is True
        assert _cta_trigger_met(s, "ghibelline")[0] is True

    def test_after_first_levy_standard_rules(self):
        s = load_scenario("D", 1)
        s["meta"]["turn"] = 10  # past the first Levy
        # No VP lag / war event -> not eligible by the escalation rule.
        assert _cta_trigger_met(s, "guelph") == (False, "no_trigger")

    def test_scenario_A_and_E_never_cta(self):
        for sc in ("A", "E"):
            s = load_scenario(sc, 1)
            assert _cta_trigger_met(s, "guelph")[0] is False
            assert _cta_trigger_met(s, "ghibelline")[0] is False
