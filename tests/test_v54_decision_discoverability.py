"""v5.4 — close two operator-interface gaps:

1. Sally parity: a losing-but-surviving Besieger's Retreat destination is now
   operator-controllable via post_battle_decisions (retreat_destination),
   matching the field-Battle path.
2. Discoverability: enumerate_legal advertises the optional decision channels
   (scripted_decisions / post_battle_decisions) on the Battle-triggering moves
   under an informational "accepts_decisions" key, so an operator driving off
   the legal-move list can find them.
3. Multi-stander field Battle: scripted_decisions accumulated across the
   response window reach resolve_battle in FIFO order.
"""
from __future__ import annotations

import inferno.actions as actions_mod
import inferno.battle as battle_mod
from inferno import actions as A
from inferno.actions import dispatch, IllegalAction, _h_cmd_sally
from inferno.legal_moves import enumerate_legal
from inferno.rng import HarnessRNG
from inferno.scenarios import load_scenario
from inferno.battle import resolve_sally
from tests.test_phase3b import _to_command_phase
from tests._helpers import _place


# --------------------------------------------------------------------------- #
# 1. Sally Besieger retreat destination is operator-controllable.
# --------------------------------------------------------------------------- #
class TestSallyRetreatDestinationChoice:
    def _setup(self, town="Lucca", seed=5):
        s = load_scenario("A", seed=seed)
        loc = s["locales"][town]
        loc["siege"] = [{"side": "ghibelline", "color": "purple", "count": 2}]
        _place(s, "firenze", town, inside=True,
               forces={"Ritter": 3, "Cavalieri": 3, "Men-at-Arms": 2})
        _place(s, "siena", town, inside=False,
               forces={"Militia": 6, "Men-at-Arms": 4, "Villici": 5, "Ritter": 2})
        return s, loc

    def _concede_trace(self, town):
        """Deterministic in-Battle script in which the Besiegers concede (so
        they survive to Retreat), captured via a callback."""
        sp, _ = self._setup(town)
        trace = []

        def cb(d):
            ch = "yes" if (d["type"] == "concede" and d["side"] == "defender") \
                else d["options"][0]
            trace.append({"type": d["type"], "choice": ch})
            return ch

        resolve_sally(sp, sallying=["firenze"], besiegers=["siena"],
                      active_id="firenze", locale_name=town, callback=cb)
        return trace

    def test_operator_picks_besieger_retreat_destination(self, monkeypatch):
        town = "Lucca"
        trace = self._concede_trace(town)
        s, loc = self._setup(town)
        s["meta"]["active_player"] = "guelph"
        s["current_lord_id"] = "firenze"
        s["actions_remaining"] = 2
        # Expose two legal targets so a non-default choice is meaningful.
        monkeypatch.setattr(A, "_retreat_candidates",
                            lambda *a, **k: ["Vecliano", "San Miniato"])
        r = _h_cmd_sally(
            s, "guelph",
            {"lord_id": "firenze", "scripted_decisions": trace,
             "post_battle_decisions": [
                 {"type": "retreat_destination", "choice": "San Miniato"}]},
            HarnessRNG(s["meta"]["rng_seed"]))
        res = r["state_changes"]["sally_result"]
        assert res["loser"] == "defender"
        si = s["lords"]["siena"]
        if si["status"] == "mustered":  # survived via concede
            assert si["location"] == "San Miniato"  # operator's pick, not leftmost
            assert "retreat_destination" in [
                d["type"] for d in res.get("post_battle_decisions", [])]

    def test_default_besieger_retreat_is_leftmost(self, monkeypatch):
        town = "Lucca"
        trace = self._concede_trace(town)
        s, loc = self._setup(town)
        s["meta"]["active_player"] = "guelph"
        s["current_lord_id"] = "firenze"
        s["actions_remaining"] = 2
        monkeypatch.setattr(A, "_retreat_candidates",
                            lambda *a, **k: ["Vecliano", "San Miniato"])
        _h_cmd_sally(s, "guelph",
                     {"lord_id": "firenze", "scripted_decisions": trace},
                     HarnessRNG(s["meta"]["rng_seed"]))
        si = s["lords"]["siena"]
        if si["status"] == "mustered":
            assert si["location"] == "Vecliano"  # deterministic leftmost default


# --------------------------------------------------------------------------- #
# 2. enumerate_legal advertises the optional decision channels.
# --------------------------------------------------------------------------- #
class TestDecisionDiscoverability:
    def _approach_pending(self, seed=99):
        s = _to_command_phase("A", seed=seed, lord_for_active="firenze")
        siena_loc = s["lords"]["siena"]["location"]
        s["locales"][siena_loc]["lords_present"].remove("siena")
        s["locales"]["Figline"]["lords_present"].append("siena")
        s["lords"]["siena"]["location"] = "Figline"
        dispatch(s, {"action": "cmd_march", "side": "guelph",
                     "args": {"lord_id": "firenze",
                              "destination": "Figline", "way_type": "road"}})
        return s

    def test_stand_move_advertises_both_channels(self):
        s = self._approach_pending()
        stand = next(m for m in enumerate_legal(s)
                     if m["action"] == "approach_response"
                     and m["args"].get("choice") == "stand")
        acc = stand["accepts_decisions"]
        assert "concede" in acc["scripted_decisions"]
        assert acc["post_battle_decisions"] == ["post_battle_withdraw",
                                                "retreat_destination"]

    def test_avoid_move_has_no_decision_channel(self):
        s = self._approach_pending()
        avoids = [m for m in enumerate_legal(s)
                  if m["action"] == "approach_response"
                  and m["args"].get("choice") == "avoid"]
        assert all("accepts_decisions" not in m for m in avoids)

    def test_advertised_move_still_dispatches(self):
        """The informational key is a sibling of args; replaying the move the
        way the sweep does (action/side/args only) must still work."""
        s = self._approach_pending()
        stand = next(m for m in enumerate_legal(s)
                     if m["action"] == "approach_response"
                     and m["args"].get("choice") == "stand")
        # Reconstruct exactly as the invariants/round-trip sweep does.
        act = {"action": stand["action"], "side": stand["side"],
               "args": stand["args"]}
        r = dispatch(s, act)
        assert r["state_changes"]["approach_resolved"] == "battle"


# --------------------------------------------------------------------------- #
# 3. Multi-stander field Battle: decisions accumulate FIFO across responses.
# --------------------------------------------------------------------------- #
class TestMultiStanderAccumulation:
    def _setup_two_standers(self, seed=99):
        s = _to_command_phase("A", seed=seed, lord_for_active="firenze")
        # Move Siena to Figline.
        siena_loc = s["lords"]["siena"]["location"]
        s["locales"][siena_loc]["lords_present"].remove("siena")
        s["locales"]["Figline"]["lords_present"].append("siena")
        s["lords"]["siena"]["location"] = "Figline"
        # Synthesize a second mustered Ghibelline Stander at Figline.
        prov = s["lords"]["provenzano"]
        prov["status"] = "mustered"
        prov["location"] = "Figline"
        prov["forces"] = {"Militia": 2}
        prov["flags"] = {}
        prov.setdefault("assets", {})
        prov.setdefault("routed_units", {})
        s["locales"]["Figline"]["lords_present"].append("provenzano")
        dispatch(s, {"action": "cmd_march", "side": "guelph",
                     "args": {"lord_id": "firenze",
                              "destination": "Figline", "way_type": "road"}})
        return s

    def test_scripted_decisions_accumulate_across_responses(self, monkeypatch):
        s = self._setup_two_standers()
        # Two pending responders.
        pend = [p for p in s["pending"] if p["type"] == "approach_response"]
        assert len(pend) == 2

        captured = {}

        def stub_resolve(*a, **kw):
            captured["scripted"] = kw.get("scripted_decisions")
            return {}  # minimal result; post-battle is stubbed out below

        monkeypatch.setattr(battle_mod, "resolve_battle", stub_resolve)
        monkeypatch.setattr(actions_mod, "_apply_post_battle",
                            lambda *a, **k: None)

        part_a = [{"type": "concede", "choice": "no"}]
        part_b = [{"type": "concede", "choice": "yes"}]
        # First Stander supplies the first slice; battle not yet triggered.
        r1 = dispatch(s, {"action": "approach_response", "side": "ghibelline",
                          "args": {"lord_id": "siena", "choice": "stand",
                                   "scripted_decisions": part_a}})
        assert "remaining_responses" in r1["state_changes"]
        # Second Stander supplies the next slice and triggers the Battle.
        dispatch(s, {"action": "approach_response", "side": "ghibelline",
                     "args": {"lord_id": "provenzano", "choice": "stand",
                              "scripted_decisions": part_b}})
        assert captured["scripted"] == part_a + part_b  # FIFO accumulation
        assert not s.get("approach_battle_decisions")    # drained
