"""v3.3 — F24/S24 Doctors: restore half (round up) of Lost units for named Lords.

The exact set of Lost units after a real Battle is RNG-dependent, so the
numeric heart of the card — ceil(L/2) where L includes Knights who received
Quarter, restoring the most valuable units first and pulling Captured Knights
back out of the ledger — is verified directly on the post-combat restoration
routine. The event-registration test confirms the handler now registers a
battle modifier (the at-outset contract) rather than the old per-Routed-unit
Protection re-roll.
"""
from __future__ import annotations

from inferno import card_effects as ce
from inferno.actions import _apply_doctors_restoration
from inferno.rng import HarnessRNG
from inferno.scenarios import load_scenario


def _doctors_mod(side, lord_ids):
    return [{"id": "F24" if side == "guelph" else "S24", "side": side,
             "effect": "doctors_restore_half_lost", "lord_ids": lord_ids}]


class TestEventRegistersModifier:
    def test_F24_registers_doctors_modifier_for_named_lords(self):
        s = load_scenario("A", 1)
        r = ce.apply_event_effect(s, "F24", "guelph", {}, HarnessRNG(seed=1))
        assert r["applied"] is True
        mods = [m for m in s["battle_modifiers_pending"]
                if m.get("effect") == "doctors_restore_half_lost"]
        assert len(mods) == 1
        assert mods[0]["lord_ids"] == ["firenze", "firenze_comune", "arezzo"]

    def test_S24_names_siena_and_pisa(self):
        s = load_scenario("A", 1)
        ce.apply_event_effect(s, "S24", "ghibelline", {}, HarnessRNG(seed=1))
        mods = [m for m in s["battle_modifiers_pending"]
                if m.get("effect") == "doctors_restore_half_lost"]
        assert mods[0]["lord_ids"] == ["siena", "siena_comune", "pisa"]


class TestRestorationMath:
    def test_four_lost_restores_two_most_valuable(self):
        s = load_scenario("A", 1)
        s["lords"]["firenze"]["forces"] = {}
        loss = {"firenze": {"lost": {"Cavalieri": 2, "Men-at-Arms": 2},
                            "captured": {}, "recovered": {}}}
        _apply_doctors_restoration(s, _doctors_mod("guelph", ["firenze"]), loss)
        # ceil(4/2) = 2, restored most-valuable-first => 2 Cavalieri.
        assert s["lords"]["firenze"]["forces"].get("Cavalieri", 0) == 2
        assert s["lords"]["firenze"]["forces"].get("Men-at-Arms", 0) == 0

    def test_odd_total_rounds_up(self):
        s = load_scenario("A", 1)
        s["lords"]["arezzo"]["forces"] = {}
        loss = {"arezzo": {"lost": {"Men-at-Arms": 3}, "captured": {}, "recovered": {}}}
        _apply_doctors_restoration(s, _doctors_mod("guelph", ["arezzo"]), loss)
        assert s["lords"]["arezzo"]["forces"].get("Men-at-Arms", 0) == 2  # ceil(3/2)

    def test_captured_knights_count_and_are_pulled_from_ledger(self):
        s = load_scenario("A", 1)
        s["lords"]["firenze"]["forces"] = {}
        s["captured_knights"] = {"guelph": {"Cavalieri": 1}}
        # 1 lost MaA + 1 captured Cavalieri => total 2 => restore 1 (Cavalieri first).
        loss = {"firenze": {"lost": {"Men-at-Arms": 1}, "captured": {"Cavalieri": 1},
                            "recovered": {}}}
        _apply_doctors_restoration(s, _doctors_mod("guelph", ["firenze"]), loss)
        assert s["lords"]["firenze"]["forces"].get("Cavalieri", 0) == 1
        # The restored Knight left the owner's Captured Knights box.
        assert s["captured_knights"]["guelph"].get("Cavalieri", 0) == 0

    def test_only_named_lords_restored(self):
        s = load_scenario("A", 1)
        s["lords"]["lucca"]["forces"] = {}
        loss = {"lucca": {"lost": {"Cavalieri": 2}, "captured": {}, "recovered": {}}}
        _apply_doctors_restoration(s, _doctors_mod("guelph", ["firenze", "arezzo"]), loss)
        assert s["lords"]["lucca"]["forces"].get("Cavalieri", 0) == 0  # Lucca not named

    def test_removed_lord_not_restored(self):
        s = load_scenario("A", 1)
        s["lords"]["firenze"]["forces"] = {}
        s["lords"]["firenze"]["status"] = "removed"
        loss = {"firenze": {"lost": {"Cavalieri": 2}, "captured": {}, "recovered": {}}}
        _apply_doctors_restoration(s, _doctors_mod("guelph", ["firenze"]), loss)
        assert s["lords"]["firenze"]["forces"].get("Cavalieri", 0) == 0

    def test_no_losses_no_restore(self):
        s = load_scenario("A", 1)
        before = dict(s["lords"]["firenze"]["forces"])
        loss = {"firenze": {"lost": {}, "captured": {}, "recovered": {"Cavalieri": 1}}}
        _apply_doctors_restoration(s, _doctors_mod("guelph", ["firenze"]), loss)
        assert s["lords"]["firenze"]["forces"] == before


class TestModifierSurvivesBattleCleanup:
    def test_resolve_battle_stashes_doctors_then_clears_pending(self):
        from inferno.battle import resolve_battle
        s = load_scenario("A", seed=5)
        # Put Siena adjacent for a Battle at Firenze.
        s["locales"]["Siena"]["lords_present"].remove("siena")
        s["locales"]["Firenze"]["lords_present"].append("siena")
        s["lords"]["siena"]["location"] = "Firenze"
        # Register a Doctors modifier as the Event would at 4.4.1 outset.
        s.setdefault("battle_modifiers_pending", []).append({
            "id": "F24", "side": "guelph", "effect": "doctors_restore_half_lost",
            "lord_ids": ["firenze", "firenze_comune", "arezzo"]})
        result = resolve_battle(s, ["firenze"], ["siena"], "firenze", "Firenze")
        # The 4.4.6 cleanup removed it from pending, but resolve_battle preserved
        # it on the result so the post-Battle loss step can consume it.
        assert any(m.get("effect") == "doctors_restore_half_lost"
                   for m in result["doctors"])
        assert not any(m.get("effect") == "doctors_restore_half_lost"
                       for m in s.get("battle_modifiers_pending", []))
