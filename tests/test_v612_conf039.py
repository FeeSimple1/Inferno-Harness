"""v6.12 — CONF-039/039b/040/041 regressions.

Physical color convention (RoP 1.1): Guelph = PURPLE, Ghibelline = GOLD.
Every scenario must open with its tracked score exactly at the printed
Victory-marker Calendar boxes (setup illustrations / section 6).
"""
from __future__ import annotations

from inferno.actions import dispatch, effective_vp, _cta_trigger_met
from inferno.scenarios import load_scenario


# Printed Victory-marker start positions (purple box = Guelph score, gold box
# = Ghibelline score), from the scenario setups in rulebook section 6.
PRINTED_START = {
    "A": (4.0, 4.0),   # both markers in box 4
    "B": (6.0, 5.0),   # purple@6, gold@5
    "C": (10.0, 9.0),  # purple@10, gold@9 (6 markers + Alliance Treaty +3)
    "D": (7.0, 5.0),   # purple@7, gold@5
    "E": (6.0, 7.0),   # purple@6, gold@7 (Resistance doubling, Ravage exempt)
    "F": (6.0, 4.0),   # purple@6, gold@4
}


class TestPrintedOpeningScores:
    def test_all_scenarios_open_at_printed_victory_markers(self):
        for sc, want in PRINTED_START.items():
            s = load_scenario(sc, seed=1)
            got = effective_vp(s)
            assert got == want, f"scenario {sc}: tracked score {got} != printed {want}"


class TestConf039Colors:
    def test_ravage_marker_colors_are_physical(self):
        # 4.7.2: marker in OPPOSITE color to printed Allegiance.
        s = load_scenario("A", seed=1)
        from inferno import static_data as sd
        # From the setup data: Guelph-printed locales carry GOLD Ravage in B.
        b = load_scenario("B", seed=1)
        assert b["locales"]["Monte San Savino"]["ravaged"] == "gold"
        assert b["locales"]["Monte San Savino"]["allegiance"] == "guelph"

    def test_scenario_c_maremma_gate_not_pretriggered(self):
        # CONF-039: C's six setup GOLD Ravage markers are GHIBELLINE-scoring
        # and must NOT count as Guelph aggression — the dashed-line March
        # restriction holds at start.
        s = load_scenario("C", seed=1)
        assert not any(
            any(m.get("side") == "guelph" for m in (l.get("siege") or []))
            or l.get("ravaged") == "purple"
            for l in s["locales"].values()
        ), "no Guelph aggression may exist at Scenario C setup"

    def test_e_victory_marker_not_yellow(self):
        # CONF-040: the rulebook's literal "yellow" is the GOLD marker.
        s = load_scenario("E", seed=1)
        for box in s["calendar"]["boxes"].values():
            assert "yellow" not in box.get("victory", [])


class TestConf039bEffectiveScore:
    def test_scenario_e_doubling_is_live(self):
        s = load_scenario("E", seed=1)
        # Raw tracked components: Guelph 4.0 (2 Ruins-VP + 2 Ravage-VP);
        # effective doubles the non-Ravage part only.
        assert s["vp"]["guelph"] == 4.0
        assert effective_vp(s)[0] == 6.0

    def test_scenario_c_manfredi_plus3_is_live(self):
        s = load_scenario("C", seed=1)
        assert s["vp"]["ghibelline"] == 6.0
        assert effective_vp(s)[1] == 9.0

    def test_cta_vp_lag_uses_effective_score(self):
        # Construct a Scenario-B position where raw VP lag < 4 but effective
        # == raw (B has no modifiers): trigger matches effective arithmetic.
        s = load_scenario("B", seed=1)
        s["vp"]["guelph"] = 9.0
        s["vp"]["ghibelline"] = 5.0
        met, reason = _cta_trigger_met(s, "ghibelline")
        assert met and reason == "vp_lag"
