"""v3.5 — SMOKE-Inferno-081: Storm and Sally now perform the 4.4.4 Loss rolls
that Battle does (routed units recover-or-are-lost instead of lingering), with
Storm Knights' Quarter on a Sack, and Storm-Doctors wired through the new Storm
loss step.
"""
from __future__ import annotations

from inferno import card_effects as ce
from inferno.battle import loss_roll_for_routed, resolve_storm
from inferno.actions import _roll_routed_losses, _apply_sack
from inferno.rng import HarnessRNG
from inferno.scenarios import load_scenario


class _FakeRoll:
    def __init__(self, v): self.value = v


def _caller(values):
    it = iter(values)
    return lambda ctx: _FakeRoll(next(it))


# =====================================================================
# loss_roll_for_routed capture_knights gate
# =====================================================================
class TestCaptureKnightsGate:
    def test_battle_captures_failed_knight(self):
        s = load_scenario("A", 1)
        lid = "firenze"
        s["lords"][lid]["routed_units"] = {"Cavalieri": 1}
        s["lords"][lid]["forces"] = {}
        # roll 5 -> outside Cavalieri Protection (1-3) -> fails; >=3 -> Captured.
        r = loss_roll_for_routed(s, lid, harsh_recovery=False,
                                 rng_caller=_caller([5]), capture_knights=True)
        assert r["captured"].get("Cavalieri") == 1
        assert s["captured_knights"]["guelph"].get("Cavalieri") == 1

    def test_storm_does_not_capture_failed_knight(self):
        s = load_scenario("A", 1)
        lid = "firenze"
        s["lords"][lid]["routed_units"] = {"Cavalieri": 1}
        s["lords"][lid]["forces"] = {}
        s["captured_knights"] = {}
        r = loss_roll_for_routed(s, lid, harsh_recovery=True,
                                 rng_caller=_caller([5]), capture_knights=False)
        # Failed Knight is LOST, never Captured (Attackers in Storm).
        assert r["lost"].get("Cavalieri") == 1
        assert r["captured"] == {}
        assert s.get("captured_knights", {}).get("guelph", {}) == {}


# =====================================================================
# _roll_routed_losses clears the routed pile + conserves units
# =====================================================================
class TestRollRoutedLosses:
    def test_routed_resolved_and_conserved(self):
        s = load_scenario("A", 1)
        lid = "firenze"
        s["lords"][lid]["routed_units"] = {"Men-at-Arms": 2}
        s["lords"][lid]["forces"] = {}
        res = _roll_routed_losses(s, [(lid, False)], capture_knights=True)
        # routed pile is emptied (no lingering routed units after the roll).
        assert s["lords"][lid].get("routed_units") == {}
        r = res[lid]
        recovered = sum(r["recovered"].values())
        lost = sum(r["lost"].values()) + sum(r["captured"].values())
        assert recovered + lost == 2
        assert s["lords"][lid]["forces"].get("Men-at-Arms", 0) == recovered


# =====================================================================
# resolve_storm stashes Doctors modifiers (for the post-Storm loss step)
# =====================================================================
class TestStormStashesDoctors:
    def _storm_setup(self, seed=5):
        s = load_scenario("A", seed=seed)
        s["locales"]["Volterra"]["siege"] = [{"side": "guelph", "color": "gold", "count": 3}]
        s["locales"]["Firenze"]["lords_present"].remove("firenze")
        s["locales"]["Volterra"]["lords_present"].append("firenze")
        s["lords"]["firenze"]["location"] = "Volterra"
        return s

    def test_doctors_stashed_and_consumed_from_pending(self):
        s = self._storm_setup()
        s.setdefault("battle_modifiers_pending", []).append({
            "id": "F24", "side": "guelph", "effect": "doctors_restore_half_lost",
            "lord_ids": ["firenze", "firenze_comune", "arezzo"]})
        result = resolve_storm(s, attackers=["firenze"], defenders=[],
                               active_id="firenze", locale_name="Volterra")
        assert any(m.get("effect") == "doctors_restore_half_lost"
                   for m in result["doctors"])
        assert not any(m.get("effect") == "doctors_restore_half_lost"
                       for m in s.get("battle_modifiers_pending", []))


# =====================================================================
# Sack Knights' Quarter (Sec. 13)
# =====================================================================
class TestSackKnightsQuarter:
    def test_inside_knights_and_garrison_cavalieri_captured(self):
        s = load_scenario("A", 1)
        # Build a Town under Guelph Siege with a Ghibelline Lord inside holding
        # Knights, and a Guelph besieger present.
        town = next(n for n, l in s["locales"].items() if l.get("type") == "town")
        loc = s["locales"][town]
        loc["siege"] = [{"side": "guelph", "color": "gold", "count": 2}]
        loc["lords_present"] = ["siena", "firenze"]
        s["lords"]["siena"]["location"] = town
        s["lords"]["siena"].setdefault("flags", {})["in_stronghold"] = True
        s["lords"]["siena"]["forces"] = {"Cavalieri": 2, "Ritter": 1}
        s["lords"]["firenze"]["location"] = town
        s["lords"]["firenze"].setdefault("flags", {})["in_stronghold"] = False
        s["captured_knights"] = {}
        size = 2  # Town
        _apply_sack(s, town, "guelph", {"removed_lords": ["siena"]}, HarnessRNG(seed=1))
        cap = s["captured_knights"]["ghibelline"]
        # 2 inside Cavalieri + 2 garrison Cavalieri = 4; 1 inside Ritter.
        assert cap.get("Cavalieri") == 2 + size
        assert cap.get("Ritter") == 1


# =====================================================================
# Storm-Doctors end to end via the modifier + loss results
# =====================================================================
class TestStormDoctorsRestoration:
    def test_restoration_applies_in_storm_path(self):
        # Mirror what _h_cmd_storm does: doctors mod from a storm result plus a
        # loss_results dict -> _apply_doctors_restoration restores ceil(L/2).
        from inferno.actions import _apply_doctors_restoration
        s = load_scenario("A", 1)
        s["lords"]["firenze"]["forces"] = {}
        doctors = [{"id": "F24", "side": "guelph", "effect": "doctors_restore_half_lost",
                    "lord_ids": ["firenze", "firenze_comune", "arezzo"]}]
        loss = {"firenze": {"lost": {"Cavalieri": 2, "Men-at-Arms": 2}, "captured": {},
                            "recovered": {}}}
        _apply_doctors_restoration(s, doctors, loss)
        assert s["lords"]["firenze"]["forces"].get("Cavalieri", 0) == 2  # ceil(4/2), best first
