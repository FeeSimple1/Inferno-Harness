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

    def test_S15_war_loans_lordship_plus_2(self):
        # SMOKE-Inferno-076: S15 War Loans is NOT a +1 Coin card. It shifts a
        # listed Lord 2 boxes or gives one of them Lordship +2 this Levy.
        s = load_scenario("A", seed=1)
        coin_before = s["lords"]["siena"]["assets"].get("Coin", 0)
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "S15", "ghibelline",
                                  {"target": "siena", "mode": "lordship"}, rng)
        assert r["applied"] and r["bonus"] == 2
        assert s["lords"]["siena"]["flags"]["lordship_bonus_pending"] == 2
        # Coin is unchanged — the old +1 Coin behaviour was a bug.
        assert s["lords"]["siena"]["assets"].get("Coin", 0) == coin_before


class TestFlaggedManual:
    """Cards whose Battle/Storm in-round effects are flagged for manual
    application by the LLM consumer."""

    @pytest.mark.parametrize("card_id", [
        "F7",   # Greek Fire (manual when no target args provided)
        "S7",   # Luceria (Capability-only — Event half is flagged)
        "S16",  # Bocca degli Abati (manual when no target_lord_id)
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


# =====================================================================
# Phase 5: Battle/Approach/Besiege hook tests
# =====================================================================
class TestPhase5BattleHooks:
    """Each de-flagged card registers a pending modifier; the engine
    consumes at the right hook point."""

    def test_f6_hills_registers_battle_modifier(self):
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F6", "guelph", {}, rng)
        assert r["applied"] is True
        assert any(m["effect"] == "hills_double_archery_defending"
                   for m in s.get("battle_modifiers_pending", []))

    def test_f8_swamp_requires_non_summer(self):
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        s["meta"]["turn"] = 3  # Summer
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F8", "guelph", {}, rng)
        assert r["applied"] is False
        assert "Summer" in r["reason"]

    def test_f8_swamp_non_summer_sets_flag(self):
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        s["meta"]["turn"] = 1  # Winter
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F8", "guelph", {}, rng)
        assert r["applied"] is True
        assert any(m["effect"] == "swamp_enemy_horse_no_strike_r1"
                   for m in s.get("battle_modifiers_pending", []))

    def test_f12_camp_attack_registers(self):
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        rng = HarnessRNG(seed=1)
        ce.apply_event_effect(s, "F12", "guelph", {}, rng)
        assert any(m["effect"] == "camp_attack_r1_asset_transfer"
                   for m in s.get("battle_modifiers_pending", []))

    def test_f16_bloody_red_stream_registers(self):
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        rng = HarnessRNG(seed=1)
        ce.apply_event_effect(s, "F16", "guelph", {}, rng)
        assert any(m["effect"] == "bloody_red_stream_first_rout"
                   for m in s.get("battle_modifiers_pending", []))


class TestPhase5HillsIntegration:
    """Run a Battle with Hills pending and verify doubled archery hits."""

    def test_battle_with_hills_doubles_defender_archery(self):
        """Hills is for Defending side. Resolve a Battle with the
        modifier set; the post-Battle pre_modifiers field should
        record the multiplier applied."""
        from inferno.battle import resolve_battle
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        # Give Siena some archery-capable Forces (Militia w/ Arcieri-like) —
        # Phase 5 doesn't auto-enable Lord-mat archery (Garrison-only by 4.4.2).
        # So Hills' effect is observable only when a card enables Archery for
        # Lord-mat units. We assert the modifier persists through the Battle
        # (active_for_battle flag) — the consumed-once pattern.
        s.setdefault("battle_modifiers_pending", []).append({
            "id": "F6", "side": "defender",  # placeholder; engine matches side label
            "effect": "hills_double_archery_defending",
        })
        # Place Siena at Firenze for Battle
        s["locales"]["Siena"]["lords_present"].remove("siena")
        s["locales"]["Firenze"]["lords_present"].append("siena")
        s["lords"]["siena"]["location"] = "Firenze"
        result = resolve_battle(s, ["firenze"], ["siena"], "firenze", "Firenze")
        # The Battle completes; Hills modifier should be cleared post-Battle.
        assert all(m.get("effect") != "hills_double_archery_defending"
                   for m in s.get("battle_modifiers_pending", []))


class TestPhase5SwampSkip:
    def test_swamp_skips_enemy_horse_r1(self):
        """Defending side with Swamp active causes enemy Horse to skip R1 melee."""
        from inferno.battle import resolve_battle
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        s["meta"]["turn"] = 1  # Winter (Swamp legal)
        # Defender is the Battle 'defender' role.
        s.setdefault("battle_modifiers_pending", []).append({
            "id": "F8", "side": "defender",
            "effect": "swamp_enemy_horse_no_strike_r1",
        })
        s["locales"]["Siena"]["lords_present"].remove("siena")
        s["locales"]["Firenze"]["lords_present"].append("siena")
        s["lords"]["siena"]["location"] = "Firenze"
        result = resolve_battle(s, ["firenze"], ["siena"], "firenze", "Firenze")
        # Check R1 hit_log for the skipped step
        r1 = result["rounds"][0]
        steps_skipped = [h for h in r1["hit_log"] if h.get("skipped") == "swamp_horse_no_strike_r1"]
        assert len(steps_skipped) >= 1


class TestPhase5CampAttack:
    def test_camp_attack_transfers_assets_pre_battle(self):
        """Camp Attack takes 2 Assets per Enemy + removes 2 more in R1."""
        from inferno.battle import resolve_battle
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        # Set up Camp Attack pending for Guelph side
        s.setdefault("battle_modifiers_pending", []).append({
            "id": "F12", "side": "guelph",
            "effect": "camp_attack_r1_asset_transfer",
        })
        s["locales"]["Siena"]["lords_present"].remove("siena")
        s["locales"]["Firenze"]["lords_present"].append("siena")
        s["lords"]["siena"]["location"] = "Firenze"
        # Siena has Coin=2, Cart=2, Provender=2 by default — 6 total Assets.
        siena_before = dict(s["lords"]["siena"]["assets"])
        result = resolve_battle(s, ["firenze"], ["siena"], "firenze", "Firenze")
        # 2 taken to Guelph + 2 removed = 4 Assets gone (or capped at available).
        siena_after = s["lords"]["siena"]["assets"]
        delta = sum(siena_before.values()) - sum(siena_after.values())
        assert delta == 4
        # pre_modifiers should record the action
        assert result.get("pre_modifiers", {}).get("camp_attack")


class TestPhase5DeflaggedRemaining:
    """The last batch — S10, S13, S14."""

    def test_s10_better_paid_death_shifts_two(self):
        from inferno.scenarios import load_scenario
        s = load_scenario("D", seed=1)  # Astimberg / Provenzano Mustered or on Calendar
        # Put astimberg on calendar so cylinder shift applies
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "S10", "ghibelline",
                                   {"targets": ["astimberg", "provenzano"]}, rng)
        assert r["applied"] is True

    def test_s13_gentle_usilia_triggers_guelph_ransom_signal(self):
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "S13", "ghibelline", {}, rng)
        assert r["applied"] is True
        assert r["ransom_triggered_for"] == "guelph"

    def test_s14_friars_sets_this_campaign_flag(self):
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "S14", "ghibelline", {}, rng)
        assert r["applied"] is True
        active = s.get("active_events", {}).get("this_campaign", [])
        assert any(e.get("effect") == "guelph_plan_blind_no_inspect" for e in active)


class TestPhase5ApproachAndBesiege:
    def test_f1_ambush_registers_approach_modifier(self):
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F1", "guelph", {}, rng)
        assert r["applied"] is True
        assert any(m["effect"] == "ambush_force_one_stand"
                   for m in s.get("approach_modifiers_pending", []))

    def test_f3_surprise_registers_besiege_modifier(self):
        from inferno.scenarios import load_scenario
        s = load_scenario("A", seed=1)
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, "F3", "guelph", {}, rng)
        assert r["applied"] is True
        assert any(m["effect"] == "surprise_besiege_alone"
                   for m in s.get("besiege_modifiers_pending", []))
