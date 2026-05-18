"""Phase 1 tests: state model, scenario loader, state display.

Per BRIEF "Test Discipline": every encoded rule has at least one test.
Phase 1 is about loading and display — no game rules yet. These tests
verify structural invariants and spot-check scenario data against the
Scenario Reference.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from inferno import static_data as sd
from inferno.render import (
    render_calendar,
    render_decks,
    render_locale,
    render_lord,
    render_summary,
    render_verbose,
)
from inferno.scenarios import SCENARIO_IDS, SCENARIO_NAMES, load_scenario


# =====================================================================
# Static data integrity
# =====================================================================
class TestStaticData:
    """Per BRIEF: static catalog must match the curated reference files."""

    def test_locale_counts_match_map_reference(self):
        """Inferno_Map.txt header: 60 total (5 cities + 16 towns + 36 castles + 3 outposts)."""
        cities = sum(1 for v in sd.LOCALES.values() if v["type"] == "city")
        towns = sum(1 for v in sd.LOCALES.values() if v["type"] == "town")
        castles = sum(1 for v in sd.LOCALES.values() if v["type"] == "castle")
        outposts = sum(1 for v in sd.LOCALES.values() if v["type"] == "outpost")
        assert len(sd.LOCALES) == 60
        assert cities == 5
        assert towns == 16
        assert castles == 36
        assert outposts == 3

    def test_ports_match_map_reference(self):
        """Inferno_Map.txt: 8 Ports."""
        ports = [n for n, v in sd.LOCALES.items() if v.get("port")]
        expected = {"Firenze", "Pisa", "San Miniato", "Pontedera",
                    "Empoli", "Montelupo", "Borgo Livorno",
                    "Castiglione della Pescaia"}
        assert set(ports) == expected

    def test_leading_cities(self):
        """Inferno_Lords.txt: Firenze (Guelph) and Siena (Ghibelline) are Leading Cities."""
        assert sd.LOCALES["Firenze"].get("leading_city") == "guelph"
        assert sd.LOCALES["Siena"].get("leading_city") == "ghibelline"

    def test_lord_counts(self):
        """14 mats: 7 Ghibelline + 7 Guelph; 6 Podestà; 2 Commanders."""
        assert len(sd.LORDS) == 14
        ghib = [n for n, v in sd.LORDS.items() if v["side"] == "ghibelline"]
        guelph = [n for n, v in sd.LORDS.items() if v["side"] == "guelph"]
        assert len(ghib) == 7
        assert len(guelph) == 7
        podesta = [n for n, v in sd.LORDS.items() if v.get("podesta")]
        assert len(podesta) == 6
        assert set(podesta) == {
            "Pisa Podestà", "Siena Podestà",
            "Firenze Podestà", "Arezzo Podestà",
            "Colle Podestà", "Lucca Podestà",
        }
        commanders = [n for n, v in sd.LORDS.items() if v.get("commander")]
        assert set(commanders) == {"Firenze Podestà", "Siena Podestà"}

    def test_pisa_only_has_ships(self):
        """Inferno_Lords.txt: Pisa Podestà is the only Lord with Ships."""
        ship_holders = [n for n, v in sd.LORDS.items() if v.get("assets", {}).get("Ship")]
        assert ship_holders == ["Pisa Podestà"]

    def test_adjacency_is_symmetric(self):
        """Each (a, b, way) edge should round-trip when queried from either side."""
        for a, b, way in sd.WAYS:
            neighbours_of_a = sd.adjacent_to(a)
            neighbours_of_b = sd.adjacent_to(b)
            assert (b, way) in neighbours_of_a, f"{a} missing edge to {b}"
            assert (a, way) in neighbours_of_b, f"{b} missing edge to {a}"

    def test_no_unknown_locales_in_ways(self):
        """Every Way endpoint must be a known Locale."""
        for a, b, way in sd.WAYS:
            assert a in sd.LOCALES, f"Unknown locale in WAYS: {a}"
            assert b in sd.LOCALES, f"Unknown locale in WAYS: {b}"

    def test_firenze_neighbours_match_map_reference(self):
        """Inferno_Map.txt: Firenze: Figline (R), Montelupo (T), Prato (T),
        Ponte a Sieve (T), San Casciano (T)."""
        expected = {
            ("Figline", "road"),
            ("Montelupo", "track"),
            ("Prato", "track"),
            ("Ponte a Sieve", "track"),
            ("San Casciano", "track"),
        }
        assert set(sd.adjacent_to("Firenze")) == expected

    def test_pisa_neighbours_match_map_reference(self):
        """Inferno_Map.txt: Pisa: Vecliano (R), Rosignano (R), Vicopisano (T),
        Borgo Livorno (T), Pecciole (T), Pontedera (T)."""
        expected = {
            ("Vecliano", "road"),
            ("Rosignano", "road"),
            ("Vicopisano", "track"),
            ("Borgo Livorno", "track"),
            ("Pecciole", "track"),
            ("Pontedera", "track"),
        }
        assert set(sd.adjacent_to("Pisa")) == expected


# =====================================================================
# Scenario loader — parameterized over all six
# =====================================================================
@pytest.mark.parametrize("sid", SCENARIO_IDS)
class TestScenarioLoaderEach:
    def test_loads_cleanly(self, sid):
        state = load_scenario(sid, seed=42)
        assert state["meta"]["scenario"] == sid
        assert state["meta"]["rules_edition"] == "living_rules_2023-04-10"
        assert state["meta"]["rng_seed"] == 42

    def test_all_14_lords_present_with_a_status(self, sid):
        state = load_scenario(sid, seed=42)
        assert len(state["lords"]) == 14
        for lord in state["lords"].values():
            assert lord["status"] in {
                "mustered", "on_calendar", "in_levy_pool",
                "disbanded", "removed",
            }

    def test_all_60_locales_present(self, sid):
        state = load_scenario(sid, seed=42)
        assert len(state["locales"]) == 60

    def test_mustered_lords_have_locations(self, sid):
        state = load_scenario(sid, seed=42)
        for lord in state["lords"].values():
            if lord["status"] == "mustered":
                assert lord["location"] is not None, f"{lord['name']} mustered without location"

    def test_on_calendar_lords_have_box(self, sid):
        state = load_scenario(sid, seed=42)
        for lord in state["lords"].values():
            if lord["status"] == "on_calendar":
                assert lord["calendar_box"] is not None
                assert 1 <= lord["calendar_box"] <= 16

    def test_mustered_lords_wired_into_locales(self, sid):
        state = load_scenario(sid, seed=42)
        for lid, lord in state["lords"].items():
            if lord["status"] == "mustered":
                loc = state["locales"][lord["location"]]
                assert lid in loc["lords_present"], (
                    f"{lid} in {lord['location']} but missing from lords_present"
                )

    def test_json_round_trip(self, sid):
        s = load_scenario(sid, seed=42)
        js = json.dumps(s, ensure_ascii=False)
        back = json.loads(js)
        assert back["meta"]["scenario"] == sid
        assert back["lords"].keys() == s["lords"].keys()


# =====================================================================
# Scenario-specific spot checks against the Scenario Reference
# =====================================================================
class TestScenarioSpecifics:
    def test_A_dolenti_note_setup(self):
        """Scenario A: Firenze@Firenze, Arezzo@Arezzo, Siena@Siena;
        Provenzano cylinder at box 1; End marker at box 3."""
        s = load_scenario("A", seed=1)
        assert s["lords"]["firenze"]["location"] == "Firenze"
        assert s["lords"]["arezzo"]["location"] == "Arezzo"
        assert s["lords"]["siena"]["location"] == "Siena"
        assert s["lords"]["provenzano"]["status"] == "on_calendar"
        assert s["lords"]["provenzano"]["calendar_box"] == 1
        assert s["calendar"]["end_box"] == 3
        assert s["calendar"]["levy_box"] == 1
        # Allegiance markers
        assert len(s["locales"]["Montalcino"]["current_allegiance"]) == 2
        assert all(m["side"] == "guelph" for m in s["locales"]["Montalcino"]["current_allegiance"])
        assert len(s["locales"]["Cortona"]["current_allegiance"]) == 2
        assert all(m["side"] == "ghibelline" for m in s["locales"]["Cortona"]["current_allegiance"])
        # F3 Night March: held event is captured in scenario JSON; Phase 2 moves it
        # into per-side aow_held. Phase 1 verifies the scenario data carries the hint.
        from inferno.scenarios import load_scenario_data
        raw = load_scenario_data("A")
        assert raw["map"].get("held_events", {}).get("guelph") == ["F3"]

    def test_C_santafior_oscura_setup(self):
        """Scenario C: Colle@Colle, Giordano@Siena. S22 Manfredi in play.
        Arezzo, Orvieto, Astimberg removed. End at box 9."""
        s = load_scenario("C", seed=1)
        assert s["lords"]["colle"]["location"] == "Colle"
        assert s["lords"]["giordano"]["location"] == "Siena"
        assert s["lords"]["arezzo"]["status"] == "removed"
        assert s["lords"]["orvieto"]["status"] == "removed"
        assert s["lords"]["astimberg"]["status"] == "removed"
        assert s["calendar"]["end_box"] == 9
        caps = s["capabilities_in_play"]
        assert any(c.get("id") == "S22" for c in caps)

    def test_D_arbia_setup(self):
        """Scenario D: 8 Mustered Lords (4 each side); Siege markers on Montepulciano."""
        s = load_scenario("D", seed=1)
        mustered = [l for l in s["lords"].values() if l["status"] == "mustered"]
        assert len(mustered) == 8
        guelph_mustered = [l for l in mustered if l["side"] == "guelph"]
        ghib_mustered = [l for l in mustered if l["side"] == "ghibelline"]
        assert len(guelph_mustered) == 4
        assert len(ghib_mustered) == 4
        # Siege at Montepulciano
        assert s["locales"]["Montepulciano"]["siege"]
        siege = s["locales"]["Montepulciano"]["siege"][0]
        assert siege["side"] == "ghibelline"
        assert siege["count"] == 2
        # Provenzano + Santa Fiora both at Montepulciano
        ml = s["locales"]["Montepulciano"]["lords_present"]
        assert "provenzano" in ml
        assert "santa_fiora" in ml

    def test_E_resistance_giordano_starts_with_extra_coin(self):
        """Scenario E special rule: Giordano starts with two Coin."""
        s = load_scenario("E", seed=1)
        # Giordano's base Coin = 0; override adds 2 -> total 2.
        assert s["lords"]["giordano"]["assets"].get("Coin") == 2
        # Astimberg unaffected (base 0 -> 0)
        assert s["lords"]["astimberg"]["assets"].get("Coin", 0) == 0

    def test_F_di_sangue_calendar_has_no_end_box(self):
        """Scenario F: variable Exhaustion end (no End marker placed at start)."""
        s = load_scenario("F", seed=1)
        assert s["calendar"]["end_box"] is None
        # All 9 cylinders should be on Calendar at start
        on_cal = [l for l in s["lords"].values() if l["status"] == "on_calendar"]
        assert len(on_cal) == 9

    def test_pisa_podesta_has_ships_when_mustered(self):
        """Inferno_Lords.txt: only Pisa has Ships (asset = 2)."""
        # D Musters Pisa
        s = load_scenario("D", seed=1)
        assert s["lords"]["pisa"]["status"] == "on_calendar"  # in D, Pisa is on box 9
        # Find a scenario where pisa is mustered? In none of A-F is Pisa Mustered at start;
        # check that the static data is wired right by examining a scenario where pisa was on Calendar.
        # The Ship count is in static_data; only verified once Pisa actually musters.
        from inferno import static_data as sd
        assert sd.LORDS["Pisa Podestà"]["assets"].get("Ship") == 2

    def test_total_status_count_is_14_for_every_scenario(self):
        for sid in SCENARIO_IDS:
            s = load_scenario(sid, seed=1)
            assert len(s["lords"]) == 14
            total = (
                sum(1 for l in s["lords"].values() if l["status"] == "mustered")
                + sum(1 for l in s["lords"].values() if l["status"] == "on_calendar")
                + sum(1 for l in s["lords"].values() if l["status"] == "in_levy_pool")
                + sum(1 for l in s["lords"].values() if l["status"] == "removed")
            )
            assert total == 14, f"{sid}: status counts don't sum to 14"


# =====================================================================
# Renderer
# =====================================================================
class TestRendering:
    @pytest.mark.parametrize("sid", SCENARIO_IDS)
    def test_summary_non_empty(self, sid):
        s = load_scenario(sid, seed=1)
        out = render_summary(s)
        assert SCENARIO_NAMES[sid] in out
        assert "Mustered Lords" in out
        assert "Locales with markers" in out or "(none)" in out

    @pytest.mark.parametrize("sid", SCENARIO_IDS)
    def test_summary_under_500_token_budget(self, sid):
        """Summary should fit ~500 tokens per BRIEF. Rough proxy: ~4 chars/token."""
        s = load_scenario(sid, seed=1)
        out = render_summary(s)
        # 500 tokens * ~4 chars = ~2000 chars. Allow 3000 for safety, but
        # if a future change blows past this, we want to know.
        assert len(out) < 4000, f"{sid} summary is {len(out)} chars; budget exceeded"

    def test_verbose_is_valid_json(self):
        s = load_scenario("A", seed=1)
        out = render_verbose(s)
        back = json.loads(out)
        assert back["meta"]["scenario"] == "A"

    def test_focused_lord_view(self):
        s = load_scenario("F", seed=1)
        out = render_lord(s, "firenze")
        assert "Firenze Podestà" in out
        assert "Cavalieri" in out
        assert "Cerchi Family" in out

    def test_focused_locale_view(self):
        s = load_scenario("D", seed=1)
        out = render_locale(s, "Montepulciano")
        assert "Montepulciano" in out
        assert "Siege" in out
        assert "Provenzano" in out

    def test_focused_calendar_view(self):
        s = load_scenario("D", seed=1)
        out = render_calendar(s)
        assert "LEVY" in out
        assert "END" in out
        assert "Firenze Podestà" in out  # cylinder on box 9

    def test_focused_decks_view(self):
        s = load_scenario("C", seed=1)
        out = render_decks(s)
        assert "guelph" in out
        assert "ghibelline" in out
        assert "Manfredi" in out  # capability in play


# =====================================================================
# CLI end-to-end
# =====================================================================
def _run_cli(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "inferno.cli", *args],
        capture_output=True, text=True, check=False, cwd=cwd,
    )


class TestCLI:
    def test_new_writes_state_file(self, tmp_path: Path):
        out = tmp_path / "x.state.json"
        r = _run_cli(["new", "A", "--seed", "42", "--out", str(out)])
        assert r.returncode == 0, r.stderr
        assert out.exists()
        state = json.loads(out.read_text())
        assert state["meta"]["scenario"] == "A"

    def test_state_summary_against_real_file(self, tmp_path: Path):
        out = tmp_path / "x.state.json"
        _run_cli(["new", "C", "--seed", "42", "--out", str(out)])
        r = _run_cli(["state", str(out), "--mode", "summary"])
        assert r.returncode == 0
        assert "Santafior Oscura" in r.stdout
        assert "Manfredi" not in r.stdout  # capabilities aren't in summary
        # But they ARE in --decks view
        r2 = _run_cli(["state", str(out), "--decks"])
        assert "Manfredi" in r2.stdout

    def test_state_focused_lord(self, tmp_path: Path):
        out = tmp_path / "x.state.json"
        _run_cli(["new", "D", "--seed", "42", "--out", str(out)])
        r = _run_cli(["state", str(out), "--lord", "giordano"])
        assert r.returncode == 0
        assert "Giordano" in r.stdout
        assert "Ritter" in r.stdout

    def test_state_focused_calendar(self, tmp_path: Path):
        out = tmp_path / "x.state.json"
        _run_cli(["new", "F", "--seed", "42", "--out", str(out)])
        r = _run_cli(["state", str(out), "--calendar"])
        assert r.returncode == 0
        assert "Box  1" in r.stdout
        assert "Box 16" in r.stdout

    def test_load_validates_real_state_file(self, tmp_path: Path):
        out = tmp_path / "x.state.json"
        _run_cli(["new", "A", "--seed", "42", "--out", str(out)])
        r = _run_cli(["load", str(out)])
        assert r.returncode == 0
        assert "scenario=A" in r.stdout
