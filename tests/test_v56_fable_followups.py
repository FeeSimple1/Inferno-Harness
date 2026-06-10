"""v5.6 — fixes for the independent (Fable) bug-hunt findings #2–#8.

#2 approach_response validated before mutating (rejected response no longer
   strands the Approach window).
#3 handler/enumerator symmetry: Avoid into a Locale whose only Enemy is
   Besieged inside is allowed.
#4 post-Battle Retreat off the Battle Locale sweeps a freed Siege/Bypass.
#5 post-Battle Withdraw counts Lords already inside against Stronghold capacity.
#6 Withdraw eligibility uses the canonical Friendly predicate (markers).
#7 Disband clears a Lord's transient flags.
#8 BattleDecisionContext enforces a scripted entry's `side` when it pins one.
"""
from __future__ import annotations

import pytest

from inferno import actions as A
from inferno.actions import dispatch, IllegalAction
from inferno.battle import BattleDecisionContext
from inferno.legal_moves import enumerate_legal
from inferno.scenarios import load_scenario
from tests.test_phase3b import _to_command_phase


def _approach(seed=99):
    s = _to_command_phase("A", seed=seed, lord_for_active="firenze")
    sl = s["lords"]["siena"]["location"]
    s["locales"][sl]["lords_present"].remove("siena")
    s["locales"]["Figline"]["lords_present"].append("siena")
    s["lords"]["siena"]["location"] = "Figline"
    dispatch(s, {"action": "cmd_march", "side": "guelph",
                 "args": {"lord_id": "firenze",
                          "destination": "Figline", "way_type": "road"}})
    return s


# ----------------------------- #2 -----------------------------
class TestRejectedResponseKeepsWindow:
    def test_rejected_avoid_leaves_pending_intact(self):
        s = _approach()
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {"action": "approach_response", "side": "ghibelline",
                         "args": {"lord_id": "siena", "choice": "avoid",
                                  "destination": "NOT_A_PLACE"}})
        assert exc.value.code == "NOT_ADJACENT"
        # Window survived: the Lord can still respond.
        pend = [p for p in s["pending"] if p["type"] == "approach_response"]
        assert [p["info"]["lord_id"] for p in pend] == ["siena"]
        r = dispatch(s, {"action": "approach_response", "side": "ghibelline",
                         "args": {"lord_id": "siena", "choice": "stand"}})
        assert r["state_changes"]["approach_resolved"] in ("battle", "no_battle")

    def test_rejected_response_does_not_leak_decisions(self):
        s = _approach()
        with pytest.raises(IllegalAction):
            dispatch(s, {"action": "approach_response", "side": "ghibelline",
                         "args": {"lord_id": "siena", "choice": "avoid",
                                  "destination": "NOT_A_PLACE",
                                  "scripted_decisions": [{"type": "concede",
                                                          "choice": "no"}]}})
        assert "approach_battle_decisions" not in s


# ----------------------------- #3 -----------------------------
class TestAvoidIntoBesiegedEnemyLocale:
    def _besieged_enemy_at(self, s, locale="San Giovanni"):
        victim = next(lid for lid, l in s["lords"].items()
                      if l["side"] == "guelph" and lid != "firenze")
        s["lords"][victim]["status"] = "mustered"
        s["lords"][victim]["location"] = locale
        s["lords"][victim].setdefault("flags", {})["in_stronghold"] = True
        s["locales"][locale].setdefault("lords_present", []).append(victim)
        return victim

    def test_handler_allows_avoid_past_besieged_enemy(self):
        s = _approach()
        self._besieged_enemy_at(s, "San Giovanni")
        r = dispatch(s, {"action": "approach_response", "side": "ghibelline",
                         "args": {"lord_id": "siena", "choice": "avoid",
                                  "destination": "San Giovanni"}})
        assert r["state_changes"]["approach_resolved"] == "no_battle"
        assert s["lords"]["siena"]["location"] == "San Giovanni"

    def test_unbesieged_enemy_still_blocks_avoid(self):
        s = _approach()
        victim = self._besieged_enemy_at(s, "San Giovanni")
        s["lords"][victim]["flags"]["in_stronghold"] = False  # now Unbesieged
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {"action": "approach_response", "side": "ghibelline",
                         "args": {"lord_id": "siena", "choice": "avoid",
                                  "destination": "San Giovanni"}})
        assert exc.value.code == "AVOID_INTO_ENEMY_LOCALE"


# ----------------------------- #4 -----------------------------
def test_retreat_off_sweeps_freed_siege(monkeypatch):
    s = {
        "lords": {
            "BES": {"side": "guelph", "status": "mustered", "location": "Town1",
                    "forces": {"Militia": 1}, "routed_units": {}, "flags": {},
                    "vassals": [], "assets": {}},
            "ATK": {"side": "ghibelline", "status": "mustered", "location": "Town1",
                    "forces": {"Ritter": 3}, "routed_units": {}, "flags": {},
                    "vassals": [], "assets": {}},
            "IN": {"side": "ghibelline", "status": "mustered", "location": "Town1",
                   "forces": {"Militia": 1}, "routed_units": {},
                   "flags": {"in_stronghold": True}, "vassals": [], "assets": {}},
        },
        "locales": {
            "Town1": {"type": "town", "allegiance": "ghibelline",
                      "lords_present": ["BES", "ATK", "IN"],
                      "siege": [{"side": "guelph", "color": "gold", "count": 2}]},
            "Adj": {"type": "castle", "allegiance": "guelph", "lords_present": []},
        },
        "meta": {"rng_seed": 1, "rng_advance": 0},
    }
    monkeypatch.setattr(A, "_retreat_candidates", lambda *a, **k: ["Adj"])
    A._apply_post_battle(s, {"loser": "defender", "conceded": None,
                             "removed_lords": []},
                         attackers=["ATK"], defenders=["BES"], battle_locale="Town1")
    assert s["lords"]["BES"]["location"] == "Adj"          # besieger departed
    assert s["locales"]["Town1"].get("siege") == []        # stale siege swept
    assert not s["lords"]["IN"]["flags"].get("in_stronghold")  # no longer besieged


# ----------------------------- #5 -----------------------------
def test_withdraw_capacity_counts_already_inside(monkeypatch):
    def lord(side, inside=False):
        return {"side": side, "status": "mustered", "location": "Town1",
                "forces": {"Militia": 1}, "routed_units": {},
                "flags": {"in_stronghold": True} if inside else {},
                "vassals": [], "assets": {}}
    s = {
        "lords": {"IN1": lord("guelph", True), "IN2": lord("guelph", True),
                  "D1": lord("guelph"), "D2": lord("guelph"),
                  "ATK": lord("ghibelline")},
        "locales": {"Town1": {"type": "town", "allegiance": "guelph",
                              "lords_present": ["IN1", "IN2", "D1", "D2", "ATK"]},
                    "Adj": {"type": "castle", "allegiance": "guelph",
                            "lords_present": []}},
        "meta": {"rng_seed": 1, "rng_advance": 0},
    }
    monkeypatch.setattr(A, "_retreat_candidates", lambda *a, **k: ["Adj"])
    A._apply_post_battle(
        s, {"loser": "defender", "conceded": None, "removed_lords": []},
        attackers=["ATK"], defenders=["D1", "D2"], battle_locale="Town1",
        decisions=[{"type": "post_battle_withdraw", "choice": "withdraw"},
                   {"type": "post_battle_withdraw", "choice": "withdraw"}])
    inside = [l for l in ("IN1", "IN2", "D1", "D2")
              if s["lords"][l]["flags"].get("in_stronghold")]
    assert len(inside) == 2                       # Size-2 Town not overfilled
    assert s["lords"]["D1"]["location"] == "Adj"  # excess electors Retreat
    assert s["lords"]["D2"]["location"] == "Adj"


# ----------------------------- #6 -----------------------------
class TestWithdrawEligibilityUsesMarkers:
    def _loc(self, printed, markers_side=None):
        loc = {"type": "town", "allegiance": printed, "lords_present": [],
               "current_allegiance": ([{"side": markers_side}] if markers_side else [])}
        return loc

    def test_marker_seized_friendly_is_eligible(self):
        s = {"lords": {"L": {"side": "guelph"}},
             "locales": {"T": self._loc("ghibelline", markers_side="guelph")}}
        assert A._can_withdraw_into_stronghold(s, "L", "T") is True

    def test_marker_seized_enemy_is_not_eligible(self):
        s = {"lords": {"L": {"side": "guelph"}},
             "locales": {"T": self._loc("guelph", markers_side="ghibelline")}}
        assert A._can_withdraw_into_stronghold(s, "L", "T") is False


# ----------------------------- #7 -----------------------------
def test_disband_clears_flags():
    s = load_scenario("A", seed=1)
    pod = next(lid for lid, l in s["lords"].items()
               if l.get("podesta") and l["status"] == "mustered")
    s["lords"][pod].setdefault("flags", {})
    s["lords"][pod]["flags"]["in_stronghold"] = True
    s["lords"][pod]["flags"]["moved_fought"] = True
    A._disband_beyond_service_limit(s, pod)
    assert s["lords"][pod]["flags"] == {}


# ----------------------------- #8 -----------------------------
class TestScriptedSideEnforced:
    def test_decide_rejects_wrong_side_entry(self):
        bdc = BattleDecisionContext(
            scripted=[{"type": "concede", "side": "defender", "choice": "yes"}])
        with pytest.raises(ValueError):
            bdc.decide("concede", "attacker", ["no", "yes"])

    def test_decide_accepts_matching_side(self):
        bdc = BattleDecisionContext(
            scripted=[{"type": "concede", "side": "attacker", "choice": "yes"}])
        assert bdc.decide("concede", "attacker", ["no", "yes"]) == "yes"

    def test_sideless_entry_still_valid_for_any_side(self):
        bdc = BattleDecisionContext(scripted=[{"type": "concede", "choice": "yes"}])
        assert bdc.decide("concede", "defender", ["no", "yes"]) == "yes"

    def test_decide_optional_skips_wrong_side_entry(self):
        bdc = BattleDecisionContext(
            scripted=[{"type": "retreat_destination", "side": "guelph",
                       "choice": "X"}])
        out = bdc.decide_optional("retreat_destination", "ghibelline",
                                  ["A", "B"], default="A")
        assert out == "A" and len(bdc.scripted) == 1  # left unconsumed
