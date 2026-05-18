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

    def test_F20_heat_and_frost_adds_provender_to_guelph_mustered(self):
        s = load_scenario("A", seed=1)
        before = {lid: s["lords"][lid]["assets"].get("Provender", 0)
                  for lid in s["lords"] if s["lords"][lid]["side"] == "guelph"
                  and s["lords"][lid]["status"] == "mustered"}
        rng = HarnessRNG(seed=1)
        ce.apply_event_effect(s, "F20", "guelph", {}, rng)
        for lid, p_before in before.items():
            assert s["lords"][lid]["assets"]["Provender"] == p_before + 1

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
        "F4", "F6", "F8", "F12", "F16",   # Guelph battle modifiers
        "F11", "F15", "F18", "F22", "F23",  # Guelph conditional/situational
        "S4", "S6", "S8", "S12", "S16",   # Ghib mirrors
    ])
    def test_flagged_returns_manual_marker(self, card_id):
        s = load_scenario("A", seed=1)
        rng = HarnessRNG(seed=1)
        r = ce.apply_event_effect(s, card_id, "guelph", {}, rng)
        assert r.get("manual") is True
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
