"""v6.10 — CONF-037: Relief Sally two-front battle model (RoP 4.4.1).

"RELIEF SALLY: When a side Approaches (4.3.4) a Locale where it is also
Besieged, Besieged Lords may join any Attack for no added Command actions.
Array and Reposition Sallying Attackers per Sally (4.5.3) but behind the
Defenders; Array any Reserve Defenders as if Front Defenders, facing the
Sallying Attackers. Sallying Lords Attack Reserve Defenders or, if none,
Front Defenders as if Flanking them all of them equally closely (4.4.2).
Siegeworks benefits apply to Strikes by Sallying Attackers only (4.5.3). If
the Attackers lose, Withdraw Sallying Lords back into the Stronghold and
reduce Siege markers there to one (4.5.3)."
"""
from __future__ import annotations

import inferno.battle as battle_mod
from inferno.actions import dispatch
from inferno.battle import resolve_battle
from inferno.scenarios import load_scenario
from tests.test_phase3b import _to_command_phase


def _place(s, lid, locale, inside=False):
    lord = s["lords"][lid]
    old = lord.get("location")
    if old and lid in s["locales"][old].get("lords_present", []):
        s["locales"][old]["lords_present"].remove(lid)
    s["locales"][locale].setdefault("lords_present", []).append(lid)
    lord["location"] = locale
    lord["status"] = "mustered"
    if inside:
        lord.setdefault("flags", {})["in_stronghold"] = True


def _relief_battle_state(seed=5):
    """Firenze (main attacker) + arezzo (Besieged inside, relief) vs siena
    (front defender) + provenzano (Reserve Defender) at Firenze."""
    s = load_scenario("A", seed=seed)
    _place(s, "siena", "Firenze")
    _place(s, "provenzano", "Firenze")
    _place(s, "arezzo", "Firenze", inside=True)
    s["locales"]["Firenze"]["siege"] = [
        {"side": "ghibelline", "color": "purple", "count": 2}]
    # Deterministic-ish forces: keep the main front stable for 2+ rounds.
    s["lords"]["firenze"]["forces"] = {"Men-at-Arms": 4, "Cavalieri": 2}
    s["lords"]["siena"]["forces"] = {"Men-at-Arms": 4, "Cavalieri": 2}
    s["lords"]["arezzo"]["forces"] = {"Militia": 4}       # 4 Archery Hits
    s["lords"]["provenzano"]["forces"] = {"Militia": 2}
    return s


class TestReliefTheater:
    def _run(self, s, rounds_no_concede=30):
        script = ([{"type": "initial_placement_defender", "choice": "siena"}]
                  + [{"type": "concede", "choice": "no"}] * rounds_no_concede)
        return resolve_battle(
            s, ["firenze", "arezzo"], ["siena", "provenzano"],
            "firenze", "Firenze",
            scripted_decisions=script,
            relief_ids=["arezzo"])

    def test_relief_lord_not_in_main_array(self):
        s = _relief_battle_state()
        r = self._run(s)
        for rd in r["rounds"]:
            pos = rd.get("positions") or {}
            assert "arezzo" not in (pos.get("attacker") or {}).values(), \
                "Sallying Attackers array BEHIND the Defenders, not in the main Front"

    def test_reserve_defender_exchanges_hits_with_relief_lord(self):
        s = _relief_battle_state()
        r = self._run(s)
        touched = {h.get("lord_id") for rd in r["rounds"]
                   for h in rd.get("hit_log", [])}
        # The rear theater fought: the Reserve Defender and/or the relief Lord
        # absorbed Hits (previously Reserve Lords could never take Hits).
        assert "provenzano" in touched or "arezzo" in touched, \
            "Reserve Defenders face the Sallying Attackers (4.4.1)"

    def test_defender_reserve_frozen_out_of_main_front(self):
        s = _relief_battle_state()
        r = self._run(s)
        # While the relief theater is live, the Reserve Defender is committed
        # rearward: he must never Advance into the main-front slots.
        for rd in r["rounds"]:
            pos = rd.get("positions") or {}
            assert "provenzano" not in (pos.get("defender") or {}).values(), \
                "Reserve Defenders arrayed vs the Sallying Attackers may not " \
                "Advance to the main Front while the relief theater is live"


class TestReliefJoinChoice:
    def _setup_approach(self, seed=99):
        s = _to_command_phase("A", seed=seed, lord_for_active="firenze")
        siena_loc = s["lords"]["siena"]["location"]
        s["locales"][siena_loc]["lords_present"].remove("siena")
        s["locales"]["Figline"]["lords_present"].append("siena")
        s["lords"]["siena"]["location"] = "Figline"
        # A Besieged Guelph Lord inside Figline (the Approaching side is
        # "also Besieged" there): eligible to Relief-Sally.
        _place(s, "arezzo", "Figline", inside=True)
        s["locales"]["Figline"]["siege"] = [
            {"side": "ghibelline", "color": "purple", "count": 2}]
        dispatch(s, {"action": "cmd_march", "side": "guelph",
                     "args": {"lord_id": "firenze",
                              "destination": "Figline", "way_type": "road"}})
        return s

    def test_besieged_lord_joins_by_default_as_relief(self, monkeypatch):
        s = self._setup_approach()
        captured = {}
        real = battle_mod.resolve_battle

        def spy(*a, **kw):
            captured["relief"] = kw.get("relief_ids")
            captured["attackers"] = a[1]
            return real(*a, **kw)
        monkeypatch.setattr(battle_mod, "resolve_battle", spy)
        dispatch(s, {"action": "approach_response", "side": "ghibelline",
                     "args": {"lord_id": "siena", "choice": "stand"}})
        assert captured["relief"] == ["arezzo"]
        assert "arezzo" in captured["attackers"]
        assert s["lords"]["arezzo"]["flags"].get("moved_fought")

    def test_besieged_lord_may_decline_to_join(self, monkeypatch):
        s = self._setup_approach()
        captured = {}
        real = battle_mod.resolve_battle

        def spy(*a, **kw):
            captured["relief"] = kw.get("relief_ids")
            captured["attackers"] = a[1]
            return real(*a, **kw)
        monkeypatch.setattr(battle_mod, "resolve_battle", spy)
        script = [{"type": "relief_sally_join", "choice": "no"}] + \
                 [{"type": "concede", "choice": "no"}] * 20
        dispatch(s, {"action": "approach_response", "side": "ghibelline",
                     "args": {"lord_id": "siena", "choice": "stand",
                              "scripted_decisions": script}})
        assert captured["relief"] == []
        assert "arezzo" not in captured["attackers"]
        assert not s["lords"]["arezzo"].get("flags", {}).get("relief_sallying")


class TestConf038StormMeleeCap:
    """RoP 4.5.2: 'Each Lord of each side in Storm adds no more than six Hits
    in Melee. (Archery is unlimited.)'"""

    def test_lord_melee_capped_at_six_in_storm(self, monkeypatch):
        s = load_scenario("A", seed=1)
        _place(s, "firenze", "Volterra")
        s["locales"]["Volterra"]["siege"] = [
            {"side": "guelph", "color": "gold", "count": 1}]
        # 16 Men-at-Arms: even after the Garrison's Round-1 strikes rout a
        # few, the Lord retains far more than 6 — uncapped he would add
        # ~10+ Melee Hits (storm attacker x1); 4.5.2 caps him at six.
        s["lords"]["firenze"]["forces"] = {"Men-at-Arms": 16}
        # Determinism: disable Walls cancellation so the applied-Hit count in
        # Round 1's attacker Melee step equals the (capped) Hits generated.
        monkeypatch.setattr(battle_mod, "_apply_walls",
                            lambda n, rng_range, rng_roll, ctx: n)
        from inferno.battle import resolve_storm
        r = resolve_storm(s, attackers=["firenze"], defenders=[],
                          active_id="firenze", locale_name="Volterra")
        # Round 1, atk_all_melee: garrison hit-log entries = applied Hits.
        rd1 = r["rounds"][0]
        melee_entries = [h for h in rd1.get("hit_log", [])
                         if h.get("garrison_unit") and not h.get("crossbow")]
        assert len(melee_entries) == 6,             f"4.5.2 caps each Lord at six Melee Hits in Storm; applied "             f"{len(melee_entries)}"
