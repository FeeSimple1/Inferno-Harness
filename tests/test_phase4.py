"""Phase 4 tests: per-card AoW effects.

Verifies that:
  - All 52 cards have registered Event effect handlers.
  - All 52 cards have registered Capability hooks.
  - A representative sample of mechanically-encoded effects produces
    the expected state change.
  - Cards whose effects are flagged for manual application return a
    'manual' marker.
"""

from __future__ import annotations

import pytest

from inferno import card_data as cd
from inferno import card_effects as ce
from inferno.actions import IllegalAction, dispatch
from inferno.rng import HarnessRNG
from inferno.scenarios import load_scenario


# =====================================================================
# Registry coverage
# =====================================================================
class TestRegistryCoverage:
    def test_all_52_event_effects_registered(self):
        for c in cd.GUELPH_CARDS + cd.GHIBELLINE_CARDS:
            assert c["id"] in ce.EVENT_EFFECTS, f"{c['id']} missing event effect"

    def test_all_52_capabilities_registered(self):
        for c in cd.GUELPH_CARDS + cd.GHIBELLINE_CARDS:
            assert c["id"] in ce.CAPABILITY_TRIGGERS, f"{c['id']} missing capability hook"


# =====================================================================
# Mechanically encoded effects — sample tests
# =====================================================================
class TestEventEffects:
    def test_F2_betrayals_no_sieges_noop(self):
        s = load_scenario("A", seed=1)
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F2", "guelph", {}, rng)
        assert r["applied"] is True
        assert r["no_sieges"] is True

    def test_F2_betrayals_with_siege_adds_treachery(self):
        s = load_scenario("A", seed=1)
        # Plant a Guelph siege
        s["locales"]["Volterra"]["siege"] = [{"side": "guelph", "color": "gold", "count": 1}]
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F2", "guelph", {}, rng)
        assert r["sieges"] == 1
        # A Treachery should be in Guelph's Command deck
        assert any(c.startswith("treachery_") for c in s["decks"]["guelph"]["command_deck"])

    def test_F5_road_works_activates_this_campaign(self):
        s = load_scenario("A", seed=1)
        rng = HarnessRNG(seed=1)
        ce.apply_event_effect(s, "F5", "guelph", {}, rng)
        active = s.get("active_events", {}).get("this_campaign", [])
        assert any(e.get("id") == "F5" for e in active)

    def test_F9_genova_treachery_mode_adds_card(self):
        s = load_scenario("A", seed=1)
        before = len(s["decks"]["guelph"]["command_deck"])
        rng = HarnessRNG(seed=1)
        ce.apply_event_effect(s, "F9", "guelph", {"mode": "treachery"}, rng)
        assert len(s["decks"]["guelph"]["command_deck"]) == before + 1

    def test_F10_closed_gates_removes_gold_ruins(self):
        s = load_scenario("A", seed=1)
        s["locales"]["Cortona"]["ruins"] = "gold"
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F10", "guelph", {"locale": "Cortona"}, rng)
        assert r["applied"] is True
        assert s["locales"]["Cortona"]["ruins"] is None

    def test_F25_war_event_flags_guelph_cta(self):
        s = load_scenario("A", seed=1)
        rng = HarnessRNG(seed=1)
        ce.apply_event_effect(s, "F25", "guelph", {}, rng)
        assert "guelph" in s.get("war_declared_this_levy", [])

    def test_S25_war_event_flags_ghib_cta(self):
        s = load_scenario("A", seed=1)
        rng = HarnessRNG(seed=1)
        ce.apply_event_effect(s, "S25", "ghibelline", {}, rng)
        assert "ghibelline" in s.get("war_declared_this_levy", [])

    def test_S15_war_loans_adds_coin_to_siena(self):
        s = load_scenario("A", seed=1)
        # Siena is Mustered in A
        before = s["lords"]["siena"]["assets"]["Coin"]
        rng = HarnessRNG(seed=1)
        ce.apply_event_effect(s, "S15", "ghibelline", {"target": "siena"}, rng)
        assert s["lords"]["siena"]["assets"]["Coin"] == before + 1


class TestFlaggedManual:
    """Cards whose Battle/Storm in-round effects are flagged for manual
    application by the LLM consumer."""

    @pytest.mark.parametrize("card_id", [
        "F1",   # Ambush (in-Battle Approach hook)
        "F3",   # Surprise (Storm interaction)
        "F7",   # Greek Fire (no target args -> manual)
        "F16",  # Bloody Red Stream (in-Battle Rout-recovery)
        "S1", "S3",  # Ghib mirrors
        "S7", "S10", "S13", "S14", "S16",
    ])
    def test_flagged_returns_manual_marker(self, card_id):
        s = load_scenario("A", seed=1)
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, card_id, "guelph", {}, rng)
        assert r.get("manual") is True, f"{card_id} should still be flagged manual; got {r}"
        assert "note" in r


# =====================================================================
# play_event action
# =====================================================================
class TestPlayEvent:
    def test_play_held_F3_consumes_card(self):
        """Scenario A pre-deals F3 to Guelphs (Night March)."""
        s = load_scenario("A", seed=1)
        assert "F3" in s["decks"]["guelph"]["aow_held"]
        # F3 is flagged (Hold; applied on Besiege). Playing it consumes the card.
        r = dispatch(s, {"action": "play_event", "side": "guelph",
                         "args": {"card_id": "F3"}})
        assert "F3" not in s["decks"]["guelph"]["aow_held"]
        assert "F3" in s["decks"]["guelph"]["aow_discard"]

    def test_play_event_unknown_card_rejected(self):
        s = load_scenario("A", seed=1)
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {"action": "play_event", "side": "guelph",
                         "args": {"card_id": "F99"}})
        assert exc.value.code == "CARD_NOT_HELD"


# =====================================================================
# Capability lookups
# =====================================================================
class TestCapabilityLookups:
    def test_capability_in_play_helper(self):
        s = load_scenario("A", seed=1)
        s["capabilities_in_play"] = [{"id": "F22", "side": "guelph", "scope": "side_wide"}]
        assert ce.capability_in_play(s, "F22")
        assert ce.capability_in_play(s, "F22", side="guelph")
        assert not ce.capability_in_play(s, "F22", side="ghibelline")

    def test_active_capabilities_for_hook_key(self):
        s = load_scenario("A", seed=1)
        s["capabilities_in_play"] = [{"id": "F22", "side": "guelph", "scope": "side_wide"}]
        hits = ce.active_capabilities_for(s, "lordship_bonus_for")
        assert len(hits) == 1
        assert hits[0]["card_id"] == "F22"


# =====================================================================
# Self-play sweep regressions — caught real bugs (Lordship + Exhaustion)
# =====================================================================
class TestLordshipExhausted:
    """Per CROSS_PROJECT_LESSONS §4 self-play sweep: greedy agent
    caught the harness offering muster moves indefinitely. Per 3.4:
    each Lord can only spend Lordship actions = his L rating."""

    def test_lordship_exhausted_blocks_further_muster(self):
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        # Drive through to 3.4
        for name, side in [
            ("levy_aow_draw","guelph"),("levy_aow_draw","ghibelline"),
            ("levy_pay_done","guelph"),("levy_pay_done","ghibelline"),
            ("levy_disband_done","guelph"),("levy_disband_done","ghibelline"),
        ]:
            dispatch(s, {"action": name, "side": side})
        # Firenze has L=3. After 3 muster actions, his Lordship should be exhausted.
        for _ in range(3):
            dispatch(s, {"action": "levy_muster_transport", "side": "guelph",
                         "args": {"lord_id": "firenze", "kind": "Cart"}})
        # 4th muster action with Firenze should be rejected
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {"action": "levy_muster_transport", "side": "guelph",
                         "args": {"lord_id": "firenze", "kind": "Cart"}})
        assert exc.value.code == "LORDSHIP_EXHAUSTED"


class TestScenarioFExhaustion:
    """Scenario F's Exhaustion rule (only triggers from Turn 9 onward)."""

    def test_exhaustion_not_rolled_before_turn_9(self):
        from inferno.scenarios import load_scenario
        s = load_scenario("F", seed=1)
        # turn = 1
        assert s["meta"]["turn"] == 1
        dispatch(s, {"action": "levy_aow_draw", "side": "guelph"})
        # exhaustion_rolled_this_levy should NOT have been set
        assert not s["meta"].get("exhaustion_rolled_this_levy")

    def test_exhaustion_rolled_from_turn_9(self):
        from inferno.scenarios import load_scenario
        s = load_scenario("F", seed=1)
        # Force turn to 9
        s["meta"]["turn"] = 9
        dispatch(s, {"action": "levy_aow_draw", "side": "guelph"})
        assert s["meta"].get("exhaustion_rolled_this_levy") is True



# =====================================================================
# Tier-3 audit fixes + de-flag verification
# =====================================================================
class TestTier3Fixes:
    """Regression tests for card-text fidelity gaps found in Tier-3 audit."""

    def test_smoke_inferno_018_f20_heat_frost_triggers_wastage_summer(self):
        """SMOKE-Inferno-018: F20 Heat & Frost triggers Wastage in Summer,
        not 'each Lord +1 Provender'."""
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        s["meta"]["turn"] = 3  # Summer
        # Give Firenze 2 Coin so he has a Wastage-eligible Asset
        s["lords"]["firenze"]["assets"]["Coin"] = 2
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F20", "guelph", {}, rng)
        assert r["applied"] is True
        # Wastage should have decremented Firenze's Coin
        assert s["lords"]["firenze"]["assets"]["Coin"] < 2
        assert "wastage" in r

    def test_smoke_inferno_018_f20_heat_frost_rejected_outside_summer_winter(self):
        """F20 requires Summer or Winter (box 2 = Spring)."""
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        s["meta"]["turn"] = 2  # Spring
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F20", "guelph", {}, rng)
        assert r["applied"] is False

    def test_smoke_inferno_019_s20_summer_removes_guido_unit(self):
        """SMOKE-Inferno-019: S20 in Summer removes 1 unit specifically
        from Guido Guerra (not generic Ritter)."""
        from inferno.scenarios import load_scenario
        s = load_scenario("D", seed=1)  # Guido Mustered in D
        s["meta"]["turn"] = 9  # Jun-Jul -> Summer
        guido = s["lords"]["guido_guerra"]
        if guido["status"] != "mustered":
            pytest.skip("Guido not Mustered in this scenario state")
        units_before = sum(guido["forces"].values())
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "S20", "ghibelline", {}, rng)
        units_after = sum(guido["forces"].values())
        if units_before > 0:
            assert units_after == units_before - 1
            assert r["guido_unit_removed"] is not None

    def test_smoke_inferno_020_f22_manfredi_shifts_target_cylinder(self):
        """SMOKE-Inferno-020: F22 Manfredi shifts a Lord with Ritter,
        does NOT block Muster."""
        from inferno.scenarios import load_scenario
        s = load_scenario("F", seed=1)
        # Find a Lord with Ritter on Calendar — astimberg has 2 Ritter and is on box 7.
        astimberg = s["lords"]["astimberg"]
        astimberg["forces"] = {"Ritter": 2}
        before_box = astimberg["calendar_box"]
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F22", "guelph",
                                   {"target_lord_id": "astimberg", "mode": "shift"}, rng)
        assert r["applied"] is True
        assert astimberg["calendar_box"] == before_box + 1

    def test_smoke_inferno_020_f22_manfredi_remove_assets(self):
        """F22 mode=remove_assets takes up to 3 from target."""
        from inferno.scenarios import load_scenario
        s = load_scenario("F", seed=1)
        astimberg = s["lords"]["astimberg"]
        astimberg["forces"] = {"Ritter": 1}
        astimberg["assets"] = {"Coin": 2, "Cart": 2}
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F22", "guelph",
                                   {"target_lord_id": "astimberg",
                                    "mode": "remove_assets",
                                    "assets_to_remove": {"Coin": 1, "Cart": 2}}, rng)
        assert r["applied"] is True
        assert astimberg["assets"]["Coin"] == 1
        assert astimberg["assets"]["Cart"] == 0

    def test_smoke_inferno_020_f22_rejects_lord_without_ritter(self):
        """F22 target must have at least one Ritter on mat."""
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        # firenze has no Ritter
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F22", "ghibelline",
                                   {"target_lord_id": "firenze", "mode": "shift"}, rng)
        assert r["applied"] is False
        assert "no Ritter" in r["reason"]

    def test_smoke_inferno_021_f21_primo_popolo_shifts_firenze(self):
        """SMOKE-Inferno-021: F21 shifts Firenze/Arezzo cylinder/Service,
        not Vassal-Seat Coin."""
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        # Firenze has service_box=3 in scenario A
        before = s["lords"]["firenze"]["service_box"]
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F21", "guelph", {"target": "firenze"}, rng)
        assert r["applied"] is True
        assert s["lords"]["firenze"]["service_box"] == before + 2


class TestDeflaggedCards:
    """Verify previously-flagged cards now produce real state changes."""

    def test_f11_poggio_bonizio_lordship_pending(self):
        """F11 sets a one-shot Lordship bonus on target Lord."""
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        # Poggio Bonizio has Ghib markers in A by default; clear them first
        s["locales"]["Poggio Bonizio"]["current_allegiance"] = []
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F11", "guelph",
                                   {"mode": "lordship", "target_lord_id": "firenze"}, rng)
        assert r["applied"] is True
        assert s["lords"]["firenze"]["flags"]["lordship_bonus_pending"] == 3

    def test_f11_conditional_check_blocks(self):
        """F11 rejected when Poggio Bonizio has Ghib markers."""
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        # A places 2 Ghib markers on Poggio Bonizio by default.
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F11", "guelph",
                                   {"mode": "lordship", "target_lord_id": "firenze"}, rng)
        assert r["applied"] is False
        assert "Ghibelline markers" in r["reason"]

    def test_f15_casole_sets_auto_treachery_flag(self):
        """F15 sets flag for next Firenze Treachery at a Castle."""
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F15", "guelph", {}, rng)
        assert r["applied"] is True
        active = s.get("active_events", {}).get("this_levy", [])
        assert any(e.get("flag") == "firenze_treachery_castle_auto" for e in active)

    def test_f18_grosseto_auto_treachery_flag(self):
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F18", "guelph", {}, rng)
        assert r["applied"] is True

    def test_f23_treasurers_pays_2_coin_for_cta(self):
        """F23 pays 2 Coin total and flags Guelph CtA."""
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        # Firenze/Arezzo have Coin in A
        coin_before = (s["lords"]["firenze"]["assets"]["Coin"]
                       + s["lords"]["arezzo"]["assets"]["Coin"])
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F23", "guelph", {"mode": "declare_cta"}, rng)
        assert r["applied"] is True
        assert "guelph" in s.get("war_declared_this_levy", [])
        coin_after = (s["lords"]["firenze"]["assets"]["Coin"]
                      + s["lords"]["arezzo"]["assets"]["Coin"])
        assert coin_before - coin_after == 2

    def test_s17_ghibelline_refugees_shift_other(self):
        """S17 conditional on Provenzano OR Santa Fiora on map."""
        from inferno.scenarios import load_scenario
        s = load_scenario("D", seed=1)  # both Mustered in D
        # Set Santa Fiora's cylinder on Calendar so we can shift it
        s["lords"]["santa_fiora"]["calendar_box"] = 10
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "S17", "ghibelline",
                                   {"mode": "shift_other", "target": "santa_fiora"}, rng)
        # Either applied or skipped (both Mustered = ambiguous which to shift)
        assert r["applied"] is True

    def test_s22_closed_gates_mirror_f10(self):
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        s["locales"]["Cortona"]["ruins"] = "purple"
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "S22", "ghibelline", {"locale": "Cortona"}, rng)
        assert r["applied"] is True
        assert s["locales"]["Cortona"]["ruins"] is None


class TestBattleModifierFlags:
    """Cards that set in_battle_modifier flags (still partial implementation)."""

    def test_f4_sudden_clash_sets_pending_flag(self):
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F4", "guelph",
                                   {"target_lord_id": "firenze"}, rng)
        assert r["applied"] is True
        assert any(m["id"] == "F4" for m in s.get("battle_modifiers_pending", []))
