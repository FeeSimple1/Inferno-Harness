"""v4.8 — Surface owner choices the harness used to auto-resolve (CPL 8.4).

A) Non-select-target Hit assignment: Battle&Storm 10.2 — "the owner chooses
   units for any other (non-Select-Target) Hits." Default stays cheapest-first;
   a consumer may opt in via bdc.decide_optional("absorb_target", ...).
B) Post-battle Withdraw: Battle&Storm 11.2 — a losing Lord Defending at a
   Friendly Stronghold MAY Withdraw into it instead of Retreating. Default
   Retreat; opt-in via meta.post_battle_withdraw.
"""
import inferno.battle as B
from inferno.battle import BattleDecisionContext


class _RNG:
    def __init__(self, vals): self.vals = list(vals); self.i = 0
    def __call__(self, ctx):
        v = self.vals[self.i % len(self.vals)]; self.i += 1
        r = type("R", (), {})(); r.value = v; r.context = ctx; return r


def _lord(forces):
    return {"lords": {"L": {"side": "guelph", "forces": dict(forces), "routed_units": {}}}}


class TestDecideOptional:
    def test_default_when_no_scripted_or_callback(self):
        bdc = BattleDecisionContext()
        assert bdc.decide_optional("absorb_target", "guelph", ["Militia", "Ritter"],
                                   default="Militia") == "Militia"
        assert bdc.trace == []  # no trace churn when default is used

    def test_unrelated_scripted_decision_not_consumed(self):
        bdc = BattleDecisionContext(scripted=[{"type": "concede", "choice": "no"}])
        out = bdc.decide_optional("absorb_target", "guelph", ["Militia", "Ritter"],
                                  default="Militia")
        assert out == "Militia"
        assert bdc.scripted == [{"type": "concede", "choice": "no"}]  # untouched

    def test_matching_scripted_decision_is_honored(self):
        bdc = BattleDecisionContext(scripted=[{"type": "absorb_target", "choice": "Ritter"}])
        out = bdc.decide_optional("absorb_target", "guelph", ["Militia", "Ritter"],
                                  default="Militia")
        assert out == "Ritter" and bdc.scripted == []


class TestHitAssignmentOptIn:
    def test_default_hits_cheapest_first(self):
        # No bdc: a normal Hit hits the Villici (cheapest), Ritter shielded.
        s = _lord({"Ritter": 1, "Villici": 1})
        B._absorb_hits(s, "L", 1, _RNG([5]), [], {})
        assert s["lords"]["L"]["forces"].get("Villici", 0) == 0
        assert s["lords"]["L"]["forces"].get("Ritter", 0) == 1

    def test_owner_can_choose_to_absorb_on_valuable_unit(self):
        # Owner elects the Ritter to absorb (e.g. to keep the Villici screen).
        bdc = BattleDecisionContext(scripted=[{"type": "absorb_target", "choice": "Ritter"}])
        s = _lord({"Ritter": 1, "Villici": 1})
        # Ritter armor 1-4; die 5 routs it. Villici untouched.
        B._absorb_hits(s, "L", 1, _RNG([5]), [], {}, bdc=bdc)
        assert s["lords"]["L"]["forces"].get("Ritter", 0) == 0
        assert s["lords"]["L"]["forces"].get("Villici", 0) == 1


class TestPostBattleWithdraw:
    def _state(self, loser_side="guelph", alleg="guelph", typ="town"):
        return {
            "lords": {
                "DEF": {"side": loser_side, "status": "mustered", "location": "Town1",
                        "forces": {"Militia": 1}, "routed_units": {}, "flags": {}, "vassals": [],
                        "assets": {}},
                "ATK": {"side": "ghibelline", "status": "mustered", "location": "Town1",
                        "forces": {"Ritter": 2}, "routed_units": {}, "flags": {}, "vassals": [],
                        "assets": {}},
            },
            "locales": {"Town1": {"type": typ, "allegiance": alleg, "lords_present": ["DEF", "ATK"]}},
            "meta": {"rng_seed": 1, "rng_advance": 0},
        }

    def _result(self):
        return {"loser": "defender", "conceded": None, "removed_lords": []}

    def test_default_retreats_not_withdraws(self):
        from inferno import actions as A
        s = self._state()
        # Give an adjacent retreat target.
        s["locales"]["Adj"] = {"type": "castle", "allegiance": "guelph", "lords_present": []}
        s.setdefault("ways", [])
        # Patch a retreat destination by monkeypatching the helper to return Adj.
        orig = A._retreat_destination
        A._retreat_destination = lambda *a, **k: "Adj"
        try:
            A._apply_post_battle(s, self._result(), ["ATK"], ["DEF"], battle_locale="Town1")
        finally:
            A._retreat_destination = orig
        # Default: DEF retreated (not in_stronghold), moved to Adj.
        assert s["lords"]["DEF"].get("flags", {}).get("in_stronghold") is not True
        assert s["lords"]["DEF"]["location"] == "Adj"

    def test_elected_withdraw_goes_inside(self):
        from inferno import actions as A
        s = self._state()
        s["meta"]["post_battle_withdraw"] = ["DEF"]
        A._apply_post_battle(s, self._result(), ["ATK"], ["DEF"], battle_locale="Town1")
        # Withdrew: inside the Stronghold, stays at Town1.
        assert s["lords"]["DEF"]["flags"].get("in_stronghold") is True
        assert s["lords"]["DEF"]["location"] == "Town1"

    def test_withdraw_ineligible_when_locale_is_enemy_held(self):
        from inferno import actions as A
        s = self._state(loser_side="guelph", alleg="ghibelline")  # Stronghold not DEF's
        s["meta"]["post_battle_withdraw"] = ["DEF"]
        s["locales"]["Adj"] = {"type": "castle", "allegiance": "guelph", "lords_present": []}
        orig = A._retreat_destination
        A._retreat_destination = lambda *a, **k: "Adj"
        try:
            A._apply_post_battle(s, self._result(), ["ATK"], ["DEF"], battle_locale="Town1")
        finally:
            A._retreat_destination = orig
        # Not eligible -> falls through to Retreat.
        assert s["lords"]["DEF"]["flags"].get("in_stronghold") is not True
        assert s["lords"]["DEF"]["location"] == "Adj"
