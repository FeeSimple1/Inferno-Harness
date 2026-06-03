"""v5.3 — post-Battle player elections are operator-controllable.

Battle&Storm 11.2 / RoP 4.4.3 / 4.4.5: a losing-but-surviving Lord may either
Withdraw into a Friendly Stronghold at the Battle Locale or Retreat, and when
Retreating chooses among the legal target Locales. Previously the withdraw
election was only settable by mutating meta.post_battle_withdraw and the
Retreat destination was always the deterministic leftmost Locale, so a
pure-dispatch operator (LLM) could not make either choice. These tests lock in
that _apply_post_battle now resolves both through a BattleDecisionContext fed
by `decisions` / `callback`, and that approach_response threads a
`post_battle_decisions` arg into it. Defaults are unchanged when no operator
input is supplied.
"""
from __future__ import annotations

from inferno import actions as A
import inferno.actions as actions_mod
from inferno.actions import dispatch
from tests.test_phase3b import _to_command_phase


def _state(loser_side="guelph", alleg="guelph", typ="town"):
    return {
        "lords": {
            "DEF": {"side": loser_side, "status": "mustered", "location": "Town1",
                    "forces": {"Militia": 1}, "routed_units": {}, "flags": {},
                    "vassals": [], "assets": {}},
            "ATK": {"side": "ghibelline", "status": "mustered", "location": "Town1",
                    "forces": {"Ritter": 2}, "routed_units": {}, "flags": {},
                    "vassals": [], "assets": {}},
        },
        "locales": {"Town1": {"type": typ, "allegiance": alleg,
                              "lords_present": ["DEF", "ATK"]}},
        "meta": {"rng_seed": 1, "rng_advance": 0},
    }


def _result():
    return {"loser": "defender", "conceded": None, "removed_lords": []}


class TestWithdrawElectionViaDecisions:
    def test_scripted_withdraw_goes_inside_without_meta(self):
        """A scripted post_battle_withdraw='withdraw' makes an eligible loser
        Withdraw inside — no meta.post_battle_withdraw needed."""
        s = _state()  # Town1 is DEF's (guelph) Friendly Town -> eligible
        A._apply_post_battle(
            s, _result(), ["ATK"], ["DEF"], battle_locale="Town1",
            decisions=[{"type": "post_battle_withdraw", "choice": "withdraw"}])
        assert s["lords"]["DEF"]["flags"].get("in_stronghold") is True
        assert s["lords"]["DEF"]["location"] == "Town1"

    def test_scripted_retreat_overrides_meta_withdraw(self, monkeypatch):
        """A scripted 'retreat' overrides a meta.post_battle_withdraw default."""
        s = _state()
        s["meta"]["post_battle_withdraw"] = ["DEF"]  # legacy default = withdraw
        monkeypatch.setattr(A, "_retreat_candidates", lambda *a, **k: ["Adj"])
        s["locales"]["Adj"] = {"type": "castle", "allegiance": "guelph",
                               "lords_present": []}
        A._apply_post_battle(
            s, _result(), ["ATK"], ["DEF"], battle_locale="Town1",
            decisions=[{"type": "post_battle_withdraw", "choice": "retreat"}])
        assert s["lords"]["DEF"]["flags"].get("in_stronghold") is not True
        assert s["lords"]["DEF"]["location"] == "Adj"

    def test_default_unchanged_when_no_decisions(self, monkeypatch):
        """Byte-identical default: no decisions + no meta -> Retreat leftmost."""
        s = _state()
        monkeypatch.setattr(A, "_retreat_candidates", lambda *a, **k: ["Adj"])
        s["locales"]["Adj"] = {"type": "castle", "allegiance": "guelph",
                               "lords_present": []}
        A._apply_post_battle(s, _result(), ["ATK"], ["DEF"], battle_locale="Town1")
        assert s["lords"]["DEF"]["flags"].get("in_stronghold") is not True
        assert s["lords"]["DEF"]["location"] == "Adj"


class TestRetreatDestinationChoice:
    def test_operator_picks_non_default_destination(self, monkeypatch):
        """With two legal targets, a scripted retreat_destination is honored
        over the deterministic leftmost default."""
        # Town1 is enemy-held so DEF is NOT withdraw-eligible -> must Retreat.
        s = _state(loser_side="guelph", alleg="ghibelline")
        monkeypatch.setattr(A, "_retreat_candidates",
                            lambda *a, **k: ["AdjA", "AdjB"])
        s["locales"]["AdjA"] = {"type": "castle", "allegiance": "guelph",
                                "lords_present": []}
        s["locales"]["AdjB"] = {"type": "castle", "allegiance": "guelph",
                                "lords_present": []}
        result = _result()
        A._apply_post_battle(
            s, result, ["ATK"], ["DEF"], battle_locale="Town1",
            decisions=[{"type": "retreat_destination", "choice": "AdjB"}])
        assert s["lords"]["DEF"]["location"] == "AdjB"
        assert "DEF" in s["locales"]["AdjB"]["lords_present"]
        # The decision is recorded on the result trace for observability.
        types = [d["type"] for d in result.get("post_battle_decisions", [])]
        assert "retreat_destination" in types

    def test_default_destination_is_leftmost(self, monkeypatch):
        s = _state(loser_side="guelph", alleg="ghibelline")
        monkeypatch.setattr(A, "_retreat_candidates",
                            lambda *a, **k: ["AdjA", "AdjB"])
        s["locales"]["AdjA"] = {"type": "castle", "allegiance": "guelph",
                                "lords_present": []}
        s["locales"]["AdjB"] = {"type": "castle", "allegiance": "guelph",
                                "lords_present": []}
        A._apply_post_battle(s, _result(), ["ATK"], ["DEF"], battle_locale="Town1")
        assert s["lords"]["DEF"]["location"] == "AdjA"


class TestApproachThreadsPostBattleDecisions:
    def _setup_approach(self, seed=99):
        s = _to_command_phase("A", seed=seed, lord_for_active="firenze")
        siena_loc = s["lords"]["siena"]["location"]
        s["locales"][siena_loc]["lords_present"].remove("siena")
        s["locales"]["Figline"]["lords_present"].append("siena")
        s["lords"]["siena"]["location"] = "Figline"
        return s

    def test_post_battle_decisions_reach_apply_post_battle(self, monkeypatch):
        s = self._setup_approach()
        dispatch(s, {"action": "cmd_march", "side": "guelph",
                     "args": {"lord_id": "firenze",
                              "destination": "Figline", "way_type": "road"}})
        captured = {}
        real = actions_mod._apply_post_battle

        def spy(*a, **kw):
            captured["decisions"] = kw.get("decisions")
            captured["callback"] = kw.get("callback")
            return real(*a, **kw)

        monkeypatch.setattr(actions_mod, "_apply_post_battle", spy)
        pbd = [{"type": "post_battle_withdraw", "choice": "retreat"}]
        dispatch(s, {"action": "approach_response", "side": "ghibelline",
                     "args": {"lord_id": "siena", "choice": "stand",
                              "post_battle_decisions": pbd}})
        assert captured["decisions"] == pbd
        # Transient queue is drained, not leaked.
        assert not s.get("approach_post_battle_decisions")
