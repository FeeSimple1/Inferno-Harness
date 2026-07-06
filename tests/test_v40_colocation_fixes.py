"""v4.0 regression tests for the illegal co-location bug class:
  - SMOKE-Inferno-087: Muster Seat eligibility + Besieged-Podesta inside placement
  - SMOKE-Inferno-088: stale Siege/Bypass marker sweep on departure (4.3.5)
  - SMOKE-Inferno-089: co-located-enemies invariant
  - SMOKE-Inferno-090: post-Battle Retreat relocates the loser (4.4.3 / 11.2)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest
from inferno.scenarios import load_scenario
from inferno.actions import dispatch, _h_cmd_march, _apply_post_battle, IllegalAction
from inferno.battle import resolve_battle
from inferno import static_data as sd
from inferno.rng import HarnessRNG
from inferno.invariants import assert_no_colocated_enemies
from tests._helpers import _place


# ---- SMOKE-Inferno-087: muster eligibility + placement ----
class TestMusterEligibility:
    def test_predicate_normal_seat_ok_outside(self):
        s = load_scenario("B", seed=1)
        tl = s["lords"]["colle"]
        ok, inside, _ = sd.muster_seat_status(s, tl, "Colle")
        assert ok and not inside  # no enemy present -> ordinary placement

    def test_predicate_nonpodesta_blocked_at_besieged_seat(self):
        s = load_scenario("B", seed=1)
        seat = "Orvieto"
        s["locales"][seat]["siege"] = [{"side": "ghibelline", "color": "purple", "count": 1}]
        _place(s, "siena", seat)  # enemy besieger present
        tl = s["lords"]["orvieto"]
        assert tl.get("podesta") is False
        ok, inside, why = sd.muster_seat_status(s, tl, seat)
        assert not ok and "Besieged" in why

    def test_predicate_podesta_main_seat_besieged_placed_inside(self):
        s = load_scenario("B", seed=1)
        seat = "Colle"  # colle Podesta Main Seat
        s["locales"][seat]["siege"] = [{"side": "ghibelline", "color": "purple", "count": 1}]
        _place(s, "siena", seat)
        tl = s["lords"]["colle"]
        assert tl.get("podesta") and tl["seats"][0] == seat
        ok, inside, _ = sd.muster_seat_status(s, tl, seat)
        assert ok and inside  # Urban Army -> inside

    def test_predicate_podesta_nonmain_besieged_blocked(self):
        s = load_scenario("B", seed=1)
        seat = "San Gimignano"  # colle's NON-main seat
        s["locales"][seat]["siege"] = [{"side": "ghibelline", "color": "purple", "count": 1}]
        _place(s, "siena", seat)
        ok, inside, _ = sd.muster_seat_status(s, s["lords"]["colle"], seat)
        assert not ok  # Urban Army applies only at Main Seat


# ---- SMOKE-Inferno-088: marker lifecycle sweep ----
class TestMarkerLifecycle:
    def test_siege_cleared_when_besieger_marches_out(self):
        s = load_scenario("A", seed=1)
        town = next(n for n, l in s["locales"].items()
                    if l.get("type") in ("town", "city") and l.get("allegiance") == "guelph")
        loc = s["locales"][town]
        loc["siege"] = [{"side": "ghibelline", "color": "purple", "count": 1}]
        _place(s, "siena", town, inside=False)          # besieger outside
        _place(s, "firenze", town, inside=True)         # besieged defender inside
        dest, way = next((b, w) for (a, b, w) in
                         [(a, b, w) for a, b, w in sd.WAYS if a == town] +
                         [(b, a, w) for a, b, w in sd.WAYS if b == town])
        s["meta"]["active_player"] = "ghibelline"
        s["current_lord_id"] = "siena"; s["actions_remaining"] = 2
        _h_cmd_march(s, "ghibelline",
                     {"lord_id": "siena", "destination": dest, "way_type": way},
                     HarnessRNG(1))
        assert loc["siege"] == []                       # siege lifted (4.3.5)
        assert not s["lords"]["firenze"]["flags"].get("in_stronghold")  # no longer besieged
        assert_no_colocated_enemies(s)


# ---- SMOKE-Inferno-090: retreat relocation ----
class TestRetreatRelocation:
    def _battle(self, attacker, defender, approached_from):
        s = load_scenario("A", seed=7)
        for lid in (attacker, defender):
            _place(s, lid, "Figline")
        s["lords"][attacker]["forces"] = {"Ritter": 3, "Cavalieri": 3, "Men-at-Arms": 3}
        s["lords"][defender]["forces"] = {"Militia": 4, "Men-at-Arms": 3, "Ritter": 2}
        s["meta"]["approach_breadcrumb"] = {"approached_from": approached_from, "approached_via": "road"}

        def cb(d):
            if d["type"] == "concede" and d["side"] == "defender":
                return "yes"
            return d["options"][0]
        res = resolve_battle(s, [attacker], [defender], active_id=attacker,
                             locale_name="Figline", callback=cb)
        _apply_post_battle(s, res, [attacker], [defender], battle_locale="Figline")
        return s, res

    def test_conceding_defender_relocated_off_battle_locale(self):
        # firenze (guelph) defends, concedes; Figline neighbors: Firenze, San Giovanni.
        # Attacker approached from San Giovanni (forbidden) -> must retreat to Firenze.
        s, res = self._battle("siena", "firenze", approached_from="San Giovanni")
        fl = s["lords"]["firenze"]
        assert res["loser"] == "defender"
        if fl["status"] == "mustered":
            assert fl["location"] != "Figline"            # relocated off the battle Locale
            assert fl["location"] != "San Giovanni"       # not back along the Approach Way
            assert "firenze" not in s["locales"]["Figline"]["lords_present"]
        assert_no_colocated_enemies(s)                    # never illegal either way

    def test_no_legal_target_means_removed(self):
        # siena (ghibelline) defends; both Figline neighbors are un-besieged Guelph
        # strongholds -> no legal Retreat -> Removed (4.4.5), not left co-located.
        s, res = self._battle("firenze", "siena", approached_from="Firenze")
        sien = s["lords"]["siena"]
        assert sien["status"] in ("on_calendar", "removed")  # Removed/recycled, not stranded
        assert "siena" not in s["locales"]["Figline"]["lords_present"]
        assert_no_colocated_enemies(s)


# ---- SMOKE-Inferno-089: invariant itself ----
class TestCoLocationInvariant:
    def test_catches_planted_violation(self):
        s = load_scenario("A", seed=1)
        loc = "Figline"
        _place(s, "firenze", loc, inside=False)
        _place(s, "siena", loc, inside=False)
        s["pending"] = []
        with pytest.raises(AssertionError):
            assert_no_colocated_enemies(s)

    def test_passes_when_one_is_inside(self):
        s = load_scenario("A", seed=1)
        loc = "Figline"
        _place(s, "firenze", loc, inside=False)
        _place(s, "siena", loc, inside=True)   # besieged inside -> legal
        s["pending"] = []
        assert_no_colocated_enemies(s)


# ---- SMOKE-Inferno-091: Commander-to-Arms / Comune into a Besieged Leading City ----
class TestCommanderArmsPlacement:
    def _besiege_leading_city(self, side="guelph"):
        from inferno.actions import COMMANDER_LORD, LEADING_CITY
        s = load_scenario("B", seed=1)
        cmd = COMMANDER_LORD[side]; city = LEADING_CITY[side]
        s["lords"][cmd]["status"] = "on_calendar"
        s["locales"][city]["siege"] = [{"side": "ghibelline", "color": "purple", "count": 1}]
        _place(s, "siena", city, inside=False)   # enemy besieger outside
        s["meta"]["cta_substep"] = "commander_arms"
        return s, cmd, city

    def test_commander_mustered_inside_besieged_leading_city(self):
        from inferno.actions import _h_cta_commander_arms
        s, cmd, city = self._besiege_leading_city()
        _h_cta_commander_arms(s, "guelph", {"mode": "muster_only"}, HarnessRNG(1))
        assert s["lords"][cmd]["status"] == "mustered"
        assert s["lords"][cmd]["location"] == city
        assert s["lords"][cmd]["flags"].get("in_stronghold") is True
        assert_no_colocated_enemies(s)

    def test_commander_mustered_outside_when_city_free(self):
        from inferno.actions import _h_cta_commander_arms, COMMANDER_LORD, LEADING_CITY
        s = load_scenario("B", seed=1)
        cmd = COMMANDER_LORD["guelph"]; city = LEADING_CITY["guelph"]
        s["lords"][cmd]["status"] = "on_calendar"
        s["meta"]["cta_substep"] = "commander_arms"
        _h_cta_commander_arms(s, "guelph", {"mode": "muster_only"}, HarnessRNG(1))
        # No enemy at the Leading City -> ordinary (open) placement, not flagged inside.
        assert not s["lords"][cmd]["flags"].get("in_stronghold")
        assert_no_colocated_enemies(s)

    def test_comune_inherits_besieged_inside_flag(self):
        from inferno.actions import _h_cta_commander_arms, _h_cta_comune_setup, COMUNE_LORD
        s, cmd, city = self._besiege_leading_city()
        _h_cta_commander_arms(s, "guelph", {"mode": "muster_only"}, HarnessRNG(1))
        s["meta"]["cta_substep"] = "comune"
        _h_cta_comune_setup(s, "guelph", {"muster_special_vassals": ["Carroccio", "Sixth of Porta San Piero"]}, HarnessRNG(1))
        comune = s["lords"][COMUNE_LORD["guelph"]]
        if comune["status"] == "mustered":
            assert comune["flags"].get("in_stronghold") is True
        assert_no_colocated_enemies(s)


# ---- SMOKE-Inferno-093: Sally besieger-loss relocation ----
class TestSallyBesiegerRetreat:
    def _setup(self, town="Lucca", seed=5):
        s = load_scenario("A", seed=seed)
        loc = s["locales"][town]
        loc["siege"] = [{"side": "ghibelline", "color": "purple", "count": 2}]
        _place(s, "firenze", town, inside=True,
               forces={"Ritter": 3, "Cavalieri": 3, "Men-at-Arms": 2})   # sallying (wins)
        _place(s, "siena", town, inside=False,
               forces={"Militia": 6, "Men-at-Arms": 4, "Villici": 5, "Ritter": 2})  # besieger (loses, survives)
        return s, loc

    def test_surviving_losing_besieger_retreats_off_locale(self):
        from inferno.actions import _h_cmd_sally
        from inferno.battle import resolve_sally
        town = "Lucca"
        # Capture the deterministic decision sequence with the besieger conceding.
        sp, _ = self._setup(town)
        trace = []

        def cb(d):
            ch = "yes" if (d["type"] == "concede" and d["side"] == "defender") else d["options"][0]
            trace.append({"type": d["type"], "choice": ch})
            return ch
        resolve_sally(sp, sallying=["firenze"], besiegers=["siena"],
                      active_id="firenze", locale_name=town, callback=cb)
        # Replay through the real handler (deterministic RNG -> same sequence).
        s, loc = self._setup(town)
        s["meta"]["active_player"] = "guelph"; s["current_lord_id"] = "firenze"
        s["actions_remaining"] = 2
        r = _h_cmd_sally(s, "guelph", {"lord_id": "firenze", "scripted_decisions": trace},
                         HarnessRNG(s["meta"]["rng_seed"]))
        res = r["state_changes"]["sally_result"]
        assert res["loser"] == "defender"            # besiegers lost
        si = s["lords"]["siena"]
        if si["status"] == "mustered":               # survived (conceded with units)
            assert si["location"] != town            # relocated off the siege Locale
            assert "siena" not in loc["lords_present"]
        assert loc["siege"] == []                     # siege ended (4.5.3)
        assert_no_colocated_enemies(s)
