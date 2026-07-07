"""v3.6 — subsystem audit of End-of-Campaign 4.9 + Scoring, economic Commands,
Naval and Pursuit. Most were already conformant; the two real defects were in
Ransom/Languish (SMOKE-083/084). These tests lock in the corrected numerics and
anchor the conformant areas.
"""
from __future__ import annotations

from inferno.actions import dispatch, _compute_final_vp, _apply_ravage_gains
from inferno.rng import HarnessRNG
from inferno.scenarios import load_scenario


def _at_end_campaign(s):
    s["meta"]["phase"] = "campaign"
    s["meta"]["campaign_step"] = "end_campaign"
    s["meta"]["active_player"] = "guelph"
    return s


# =====================================================================
# SMOKE-083 — Ransom recovers HALF of TOTAL captured (round up), not per-type
# =====================================================================
class TestRansomRecovery:
    def test_recovers_half_of_total_not_per_type(self):
        s = _at_end_campaign(load_scenario("A", 1))
        s["captured_knights"] = {"guelph": {"Cavalieri": 1, "Ritter": 1}}  # total 2
        s["lords"]["firenze"]["assets"]["Coin"] = 5
        def _knights():
            return sum(l["forces"].get("Ritter", 0) + l["forces"].get("Cavalieri", 0)
                       for l in s["lords"].values() if l["side"] == "guelph")
        before = _knights()
        r = dispatch(s, {"action": "end_ransom", "side": "guelph", "args": {"pay": True}})
        # ceil(2/2) = 1 recovered (most valuable = Ritter); cost ceil(2/6) = 1 Coin.
        assert r["state_changes"]["recovered_total"] == 1
        assert r["state_changes"]["ransom_paid"] == 1
        assert _knights() - before == 1   # exactly 1 unit returned, not 2

    def test_odd_total_rounds_up(self):
        s = _at_end_campaign(load_scenario("A", 1))
        s["captured_knights"] = {"guelph": {"Cavalieri": 5}}  # total 5
        s["lords"]["firenze"]["assets"]["Coin"] = 5
        r = dispatch(s, {"action": "end_ransom", "side": "guelph", "args": {"pay": True}})
        assert r["state_changes"]["recovered_total"] == 3  # ceil(5/2)


# =====================================================================
# SMOKE-084 — Languish gives ONE of Revolt OR Treachery per 6 (not both)
# =====================================================================
class TestLanguish:
    def test_default_all_revolt_no_treachery(self):
        s = _at_end_campaign(load_scenario("A", 1))
        s["captured_knights"] = {"guelph": {"Cavalieri": 7}}  # ceil(7/6) = 2 events
        r = dispatch(s, {"action": "end_ransom", "side": "guelph", "args": {"pay": False}})
        sc = r["state_changes"]
        assert sc["events"] == 2
        assert sc["revolt_rolls"] == 2
        assert sc["treachery_added"] == 0          # NOT 2 revolts + 2 treachery
        assert s["captured_knights"]["guelph"] == {}

    def test_split_revolt_and_treachery(self):
        s = _at_end_campaign(load_scenario("A", 1))
        s["captured_knights"] = {"guelph": {"Cavalieri": 7}}
        before = len(s["decks"]["ghibelline"]["command_deck"])
        r = dispatch(s, {"action": "end_ransom", "side": "guelph",
                         "args": {"pay": False, "languish_treachery": 1}})
        sc = r["state_changes"]
        assert sc["revolt_rolls"] == 1 and sc["treachery_added"] == 1


# =====================================================================
# Conformance anchors for the audited (already-correct) areas
# =====================================================================
class TestConformanceAnchors:
    def test_repair_excludes_castles(self):
        s = _at_end_campaign(load_scenario("A", 1))
        castle = next(n for n, l in s["locales"].items() if l["type"] == "castle")
        town = next(n for n, l in s["locales"].items() if l["type"] == "town")
        s["locales"][castle]["siege"] = [{"side": "guelph", "color": "purple", "count": 4}]
        s["locales"][town]["siege"] = [{"side": "guelph", "color": "purple", "count": 3}]
        dispatch(s, {"action": "end_repair", "side": "guelph", "args": {}})
        # Castle keeps all 4; Town drops to 2.
        assert sum(x["count"] for x in s["locales"][castle]["siege"]) == 4
        assert sum(x["count"] for x in s["locales"][town]["siege"]) == 2

    def test_scenario_E_doubles_guelph_except_ravaged(self):
        s = load_scenario("E", 1)
        for l in s["locales"].values():
            l["current_allegiance"] = []
            l["ruins"] = None
            l["ravaged"] = None
        town = next(n for n, l in s["locales"].items() if l["type"] == "town")
        s["locales"][town]["current_allegiance"] = [{"side": "guelph", "value": 1}]
        ruin = next(n for n, l in s["locales"].items()
                    if l["type"] == "castle" and n != town)
        s["locales"][ruin]["ruins"] = "purple"        # +0.5 Guelph (CONF-039)
        rav = next(n for n, l in s["locales"].items() if l.get("ravaged") is None and n not in (town, ruin))
        s["locales"][rav]["ravaged"] = "purple"        # +0.5 Guelph, NOT doubled (CONF-039)
        g, h = _compute_final_vp(s)
        # (1 marker + 0.5 ruins) doubled = 3.0, + 0.5 ravaged (not doubled) = 3.5
        assert g == 3.5

    def test_scenario_C_manfredi_plus_3(self):
        s = load_scenario("C", 1)
        for l in s["locales"].values():
            l["current_allegiance"] = []
            l["ruins"] = None
            l["ravaged"] = None
        s.setdefault("capabilities_in_play", [])
        if not any(c.get("id") == "S22" for c in s["capabilities_in_play"]):
            s["capabilities_in_play"].append({"id": "S22", "side": "ghibelline", "scope": "side_wide"})
        g, h = _compute_final_vp(s)
        assert h == 3.0  # +3 from Manfredi, nothing else on the board

    def test_ravage_berrovieri_doubles(self):
        s = load_scenario("A", 1)
        lid = "firenze"
        s["lords"][lid]["forces"] = {"Berrovieri": 1}
        s["lords"][lid]["assets"] = {}
        gains = _apply_ravage_gains(s, lid, "town")
        assert gains == {"Provender": 2, "Loot": 2}  # doubled town gains
