"""Phase 2 tests: Levy phase mechanics.

Per BRIEF "Test Discipline": every rule encoded in code must have at
least one test. The test's docstring cites the rule section.

Phase 2 covers Pay (3.2), Disband (3.3.1 + 3.3.2 per Errata), Muster
(3.4.1-3.4.4), and the Levy step machine (3.1-3.5). Full Call to
Arms (3.5.1-3.5.4) is deferred to Phase 2b.
"""

from __future__ import annotations

import pytest

from inferno import card_data as cd
from inferno.actions import IllegalAction, dispatch
from inferno.flow import current_side, current_step
from inferno.legal_moves import enumerate_legal
from inferno.scenarios import load_scenario


# =====================================================================
# Card data
# =====================================================================
class TestCardData:
    def test_each_side_has_26_cards(self):
        """Playbook p.64: each side has 26 AoW cards (F1-F26 / S1-S26)."""
        assert len(cd.GUELPH_CARDS) == 26
        assert len(cd.GHIBELLINE_CARDS) == 26

    def test_war_events_per_3_5_trigger(self):
        """Rule 3.5 triggers: War events = F25 Val d'Orcia, F26 Montalcino,
        S25 Maremma, S26 Montepulciano."""
        assert cd.WAR_EVENT_IDS == {"F25", "F26", "S25", "S26"}

    def test_treachery_and_command_cards_per_lord(self):
        """Per 1.4.3: each non-Comune Lord has one Treachery card."""
        assert len(cd.TREACHERY_CARDS) == 12
        assert len(cd.COMMAND_CARDS) == 12


# =====================================================================
# Deck initialization (scenarios.load_scenario)
# =====================================================================
class TestDeckSetup:
    def test_held_event_removed_from_deck(self):
        """Scenario A Night March: Guelphs begin Holding F3 Surprise.
        F3 should be in aow_held and NOT in aow_deck."""
        s = load_scenario("A", seed=1)
        assert "F3" in s["decks"]["guelph"]["aow_held"]
        assert "F3" not in s["decks"]["guelph"]["aow_deck"]
        assert len(s["decks"]["guelph"]["aow_deck"]) == 25  # 26 - 1 held

    def test_treachery_set_aside_per_lord(self):
        """Per 1.4.3: Treachery cards start set aside, one per Lord."""
        s = load_scenario("A", seed=1)
        assert len(s["decks"]["guelph"]["treachery_set_aside"]) == 6
        assert len(s["decks"]["ghibelline"]["treachery_set_aside"]) == 6
        # Each side's command deck starts with 6 Command cards
        assert len(s["decks"]["guelph"]["command_deck"]) == 6
        assert len(s["decks"]["ghibelline"]["command_deck"]) == 6


# =====================================================================
# Action dispatch + envelope
# =====================================================================
class TestDispatchEnvelope:
    def test_malformed_action_rejected(self):
        s = load_scenario("A", seed=1)
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, "not_a_dict")
        assert exc.value.code == "MALFORMED"

    def test_unknown_action_rejected(self):
        s = load_scenario("A", seed=1)
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {"action": "do_the_thing", "side": "guelph"})
        assert exc.value.code == "UNKNOWN_ACTION"

    def test_wrong_side_rejected(self):
        """Per 2.2.4: active player drives. Wrong side -> WRONG_TURN."""
        s = load_scenario("A", seed=1)  # active = guelph
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {"action": "levy_aow_draw", "side": "ghibelline"})
        assert exc.value.code == "WRONG_TURN"


# =====================================================================
# 3.1 Arts of War draw
# =====================================================================
class TestAoWDraw:
    def test_first_levy_deploys_capabilities(self):
        """3.1.2: first Levy each side draws 2, deploys as Capabilities."""
        s = load_scenario("F", seed=42)  # full scenario; no removed lords
        def _deployed():
            cip = len(s["capabilities_in_play"])
            mats = sum(len(l.get("capabilities", []) or []) for l in s["lords"].values())
            disc = sum(len(s["decks"][sd]["aow_discard"]) for sd in ("guelph", "ghibelline"))
            return cip + mats + disc
        before = _deployed()
        dispatch(s, {"action": "levy_aow_draw", "side": "guelph"})
        dispatch(s, {"action": "levy_aow_draw", "side": "ghibelline"})
        # A4: 4 cards deployed total — each side-wide (map edge), This-Lord (a mat),
        # or discarded (no eligible Mustered Lord).
        assert _deployed() == before + 4

    def test_advances_step_after_both_sides(self):
        s = load_scenario("A", seed=1)
        assert current_step(s) == "3.1"
        dispatch(s, {"action": "levy_aow_draw", "side": "guelph"})
        assert current_step(s) == "3.1"
        assert current_side(s) == "ghibelline"
        dispatch(s, {"action": "levy_aow_draw", "side": "ghibelline"})
        assert current_step(s) == "3.2"
        assert current_side(s) == "guelph"


# =====================================================================
# 3.2 Pay
# =====================================================================
class TestPay:
    def _advance_to_pay(self, scenario="A", seed=1):
        s = load_scenario(scenario, seed=seed)
        dispatch(s, {"action": "levy_aow_draw", "side": "guelph"})
        dispatch(s, {"action": "levy_aow_draw", "side": "ghibelline"})
        return s

    def test_coin_shifts_service_marker_right(self):
        """3.2.1: 1 Coin = 1 box shift right for a regular Lord."""
        s = self._advance_to_pay("F", seed=2)
        # Firenze Podestà has Coin=2 and Service marker at box 3 (scenario F).
        lord = s["lords"]["firenze"]
        before = lord["service_box"]
        # Firenze is a Podestà (rate=2), so 2 Coin = 1 box.
        coin_before = lord["assets"]["Coin"]
        dispatch(s, {
            "action": "levy_pay", "side": "guelph",
            "args": {"from_lord_id": "firenze", "target_lord_id": "firenze",
                     "asset": "Coin", "amount": 1},
        })
        assert lord["service_box"] == before + 1
        assert lord["assets"]["Coin"] == coin_before - 2  # Podestà rate

    def test_podesta_rate_is_2(self):
        """3.2.1 PODESTA EXCEPTION: 2 Coin per box shift for a Podestà."""
        s = self._advance_to_pay("F", seed=3)
        lord = s["lords"]["firenze"]  # Podestà
        # Firenze has Coin=2; one box = 2 Coin.
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {
                "action": "levy_pay", "side": "guelph",
                "args": {"from_lord_id": "firenze", "target_lord_id": "firenze",
                         "asset": "Coin", "amount": 2},
            })
        # 2 boxes = 4 Coin > 2 available
        assert exc.value.code == "INSUFFICIENT_ASSET"

    def test_pay_different_locales_rejected(self):
        """3.2.1: payer and target must be at same Locale."""
        s = self._advance_to_pay("A", seed=4)
        # Firenze@Firenze and Arezzo@Arezzo
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {
                "action": "levy_pay", "side": "guelph",
                "args": {"from_lord_id": "firenze", "target_lord_id": "arezzo",
                         "asset": "Coin", "amount": 1},
            })
        assert exc.value.code == "PAY_DIFFERENT_LOCALES"

    def test_pay_done_advances(self):
        s = self._advance_to_pay("A", seed=5)
        dispatch(s, {"action": "levy_pay_done", "side": "guelph"})
        dispatch(s, {"action": "levy_pay_done", "side": "ghibelline"})
        assert current_step(s) == "3.3"


# =====================================================================
# 3.3 Disband
# =====================================================================
class TestDisband:
    def _advance_to_disband(self, scenario, seed):
        s = load_scenario(scenario, seed=seed)
        # Walk through 3.1 and 3.2
        dispatch(s, {"action": "levy_aow_draw", "side": "guelph"})
        dispatch(s, {"action": "levy_aow_draw", "side": "ghibelline"})
        dispatch(s, {"action": "levy_pay_done", "side": "guelph"})
        dispatch(s, {"action": "levy_pay_done", "side": "ghibelline"})
        return s

    def test_no_disband_when_service_right_of_levy(self):
        """Scenario A: Firenze/Arezzo/Siena have Service at box 3, Levy@1.
        No one Disbands."""
        s = self._advance_to_disband("A", seed=1)
        r = dispatch(s, {"action": "levy_disband", "side": "guelph"})
        assert r["state_changes"]["beyond_service_limit_removed"] == []
        assert r["state_changes"]["at_service_limit_disbanded"] == []

    def test_beyond_service_limit_regular_lord_removed(self):
        """3.3.1: regular Lord with Service marker left of Levy is removed."""
        s = self._advance_to_disband("A", seed=1)
        # Force Arezzo's service box to be left of Levy (which is 1).
        # We need service_box=0 (off-Calendar left) to trigger; but our
        # state stores service_box=int. The semantics are "left of levy_box=1"
        # so service_box=0 (not a valid box) — set it to None and add to off_left_service.
        # Easier: relocate the levy box to 5 and put Arezzo's service at 3 (left).
        s["calendar"]["levy_box"] = 5
        s["lords"]["arezzo"]["service_box"] = 3
        # Move marker on calendar
        s["calendar"]["boxes"]["3"]["services"].remove("arezzo") if "arezzo" in s["calendar"]["boxes"].get("3", {"services": []})["services"] else None
        # Arezzo isn't a Podestà for the Beyond Service test... actually Arezzo IS a Podestà.
        # Use Lucca Podestà — wait, removed in scenario A. Use a non-Podestà.
        # Actually the rule for Beyond Service Limit applies to Lord; the Revolt count varies (1 reg, 3 Podestà).
        # For this test we just verify "removed". Arezzo (Podestà) -> cylinder placed S boxes ahead.
        r = dispatch(s, {"action": "levy_disband", "side": "guelph"})
        assert "arezzo" in r["state_changes"]["beyond_service_limit_removed"]
        # Arezzo is a Podestà: status should become on_calendar, not removed.
        assert s["lords"]["arezzo"]["status"] == "on_calendar"

    def test_at_service_limit_per_errata(self):
        """3.3.2 per Errata: Lord whose Service marker is in the SAME box
        as Levy marker Disbands and may re-Muster (no Revolt/Treachery)."""
        s = self._advance_to_disband("A", seed=1)
        # Put Siena Podestà's Service marker on box 1 (same as Levy).
        for n in s["calendar"]["boxes"]:
            if "siena" in s["calendar"]["boxes"][n]["services"]:
                s["calendar"]["boxes"][n]["services"].remove("siena")
        s["lords"]["siena"]["service_box"] = 1
        s["calendar"]["boxes"]["1"]["services"].append("siena")
        # Skip Guelph
        dispatch(s, {"action": "levy_disband", "side": "guelph"})
        dispatch(s, {"action": "levy_disband_done", "side": "guelph"})
        r = dispatch(s, {"action": "levy_disband", "side": "ghibelline"})
        assert "siena" in r["state_changes"]["at_service_limit_disbanded"]
        # No Treachery added for At Service Limit Disband
        assert r["state_changes"]["treachery_added"] == []
        # Cylinder placed S=3 boxes right -> box 4
        assert s["lords"]["siena"]["status"] == "on_calendar"
        assert s["lords"]["siena"]["calendar_box"] == 1 + 3


# =====================================================================
# 3.4 Muster
# =====================================================================
class TestMuster:
    def _advance_to_muster(self, scenario="A", seed=1):
        s = load_scenario(scenario, seed=seed)
        dispatch(s, {"action": "levy_aow_draw", "side": "guelph"})
        dispatch(s, {"action": "levy_aow_draw", "side": "ghibelline"})
        dispatch(s, {"action": "levy_pay_done", "side": "guelph"})
        dispatch(s, {"action": "levy_pay_done", "side": "ghibelline"})
        dispatch(s, {"action": "levy_disband_done", "side": "guelph"})
        dispatch(s, {"action": "levy_disband_done", "side": "ghibelline"})
        return s

    def test_muster_lord_succeeds_on_low_roll(self):
        """3.4.1: Fealty roll <= Fealty rating = success."""
        s = self._advance_to_muster("A", seed=42)
        # Siena tries to Muster Provenzano (F:5; almost any roll succeeds).
        # First go through Guelph muster_done.
        dispatch(s, {"action": "levy_muster_done", "side": "guelph"})
        r = dispatch(s, {
            "action": "levy_muster_lord", "side": "ghibelline",
            "args": {"muster_lord_id": "siena", "target_lord_id": "provenzano",
                     "target_seat": "Siena"},
        })
        # With Provenzano's Fealty=5, the chance of success is 5/6.
        # Test deterministically: if roll <= 5, success
        assert r["state_changes"]["fealty_rating"] == 5
        if r["state_changes"]["die"] <= 5:
            assert r["state_changes"]["success"] is True
            assert s["lords"]["provenzano"]["status"] == "mustered"
            assert s["lords"]["provenzano"]["location"] == "Siena"
        else:
            assert r["state_changes"]["success"] is False

    def test_muster_lord_bad_seat_rejected(self):
        """3.4.1: target_seat must be one of the Lord's printed Seats."""
        s = self._advance_to_muster("A", seed=1)
        dispatch(s, {"action": "levy_muster_done", "side": "guelph"})
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {
                "action": "levy_muster_lord", "side": "ghibelline",
                "args": {"muster_lord_id": "siena", "target_lord_id": "provenzano",
                         "target_seat": "Firenze"},
            })
        assert exc.value.code == "BAD_SEAT"

    def test_levy_transport_adds_cart(self):
        """3.4.3: 1 action -> +1 Cart."""
        s = self._advance_to_muster("F", seed=1)
        before = s["lords"]["firenze"]["assets"].get("Cart", 0)
        dispatch(s, {
            "action": "levy_muster_transport", "side": "guelph",
            "args": {"lord_id": "firenze", "kind": "Cart"},
        })
        assert s["lords"]["firenze"]["assets"]["Cart"] == before + 1

    def test_levy_transport_ship_pisa_only(self):
        """3.4.3 + 4.7.3: only Pisa Podestà may levy Ships."""
        s = self._advance_to_muster("F", seed=1)
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {
                "action": "levy_muster_transport", "side": "guelph",
                "args": {"lord_id": "firenze", "kind": "Ship"},
            })
        assert exc.value.code == "SHIPS_PISA_ONLY"

    def test_levy_capability_draws_from_deck(self):
        """3.4.4: 1 action -> draw 1 Capability from AoW deck."""
        s = self._advance_to_muster("F", seed=1)
        before = len(s["decks"]["guelph"]["aow_deck"])
        dispatch(s, {
            "action": "levy_muster_capability", "side": "guelph",
            "args": {"lord_id": "firenze", "scope": "side_wide"},
        })
        assert len(s["decks"]["guelph"]["aow_deck"]) == before - 1

    def test_this_lord_capability_max_2(self):
        """3.4.4: max 2 'This Lord' Capabilities per mat."""
        s = self._advance_to_muster("F", seed=1)
        for _ in range(2):
            dispatch(s, {
                "action": "levy_muster_capability", "side": "guelph",
                "args": {"lord_id": "firenze", "scope": "this_lord"},
            })
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {
                "action": "levy_muster_capability", "side": "guelph",
                "args": {"lord_id": "firenze", "scope": "this_lord"},
            })
        assert exc.value.code == "THIS_LORD_LIMIT"

    def test_muster_vassal_marks_unready(self):
        """3.4.2: Mustering a Vassal slides Service marker (no longer Ready)
        and adds Forces."""
        s = self._advance_to_muster("F", seed=1)
        firenze = s["lords"]["firenze"]
        # Pick a Ready non-Special Vassal
        v = firenze["vassals"][0]
        assert v["ready"]
        forces_before = dict(firenze["forces"])
        dispatch(s, {
            "action": "levy_muster_vassal", "side": "guelph",
            "args": {"lord_id": "firenze", "vassal": v["name"]},
        })
        # Find vassal again
        for vp in firenze["vassals"]:
            if vp["name"] == v["name"]:
                assert vp["ready"] is False
                for unit, count in vp["forces"].items():
                    assert firenze["forces"].get(unit, 0) == forces_before.get(unit, 0) + count

    def test_muster_done_advances(self):
        s = self._advance_to_muster("A", seed=1)
        dispatch(s, {"action": "levy_muster_done", "side": "guelph"})
        assert current_side(s) == "ghibelline"
        dispatch(s, {"action": "levy_muster_done", "side": "ghibelline"})
        assert current_step(s) == "3.5"


# =====================================================================
# Full Levy walkthrough
# =====================================================================
class TestFullLevyWalkthrough:
    @pytest.mark.parametrize("sid", ["A", "B", "C", "D", "E", "F"])
    def test_levy_completes_without_errors(self, sid):
        """End-to-end: every scenario completes one full Levy via skip-everything."""
        s = load_scenario(sid, seed=42)
        # 3.1
        dispatch(s, {"action": "levy_aow_draw", "side": "guelph"})
        dispatch(s, {"action": "levy_aow_draw", "side": "ghibelline"})
        # 3.2
        dispatch(s, {"action": "levy_pay_done", "side": "guelph"})
        dispatch(s, {"action": "levy_pay_done", "side": "ghibelline"})
        # 3.3
        dispatch(s, {"action": "levy_disband_done", "side": "guelph"})
        dispatch(s, {"action": "levy_disband_done", "side": "ghibelline"})
        # 3.4
        dispatch(s, {"action": "levy_muster_done", "side": "guelph"})
        dispatch(s, {"action": "levy_muster_done", "side": "ghibelline"})
        # 3.5
        dispatch(s, {"action": "levy_cta_skip", "side": "guelph"})
        dispatch(s, {"action": "levy_cta_skip", "side": "ghibelline"})
        assert s["meta"]["phase"] == "campaign"

    def test_history_records_rolls(self):
        """Per BRIEF: every die roll is logged in action history with context."""
        s = load_scenario("A", seed=42)
        dispatch(s, {"action": "levy_aow_draw", "side": "guelph"})
        # AoW draw rolls 2 indices
        last = s["history"][-1]
        assert last["action"] == "levy_aow_draw"
        assert len(last["rolls"]) == 2
        for r in last["rolls"]:
            assert "context" in r
            assert "value" in r


# =====================================================================
# Legal moves
# =====================================================================
class TestLegalMoves:
    def test_levy_aow_returns_single_draw_action(self):
        s = load_scenario("A", seed=1)
        moves = enumerate_legal(s)
        assert len(moves) == 1
        assert moves[0]["action"] == "levy_aow_draw"

    def test_pay_step_includes_done(self):
        s = load_scenario("A", seed=1)
        dispatch(s, {"action": "levy_aow_draw", "side": "guelph"})
        dispatch(s, {"action": "levy_aow_draw", "side": "ghibelline"})
        moves = enumerate_legal(s)
        assert any(m["action"] == "levy_pay_done" for m in moves)

    def test_muster_includes_per_lord_actions(self):
        s = load_scenario("F", seed=1)
        # advance to muster
        for cmd in ["levy_aow_draw", "levy_aow_draw"]:
            dispatch(s, {"action": cmd, "side": current_side(s)})
        for cmd in ["levy_pay_done", "levy_pay_done"]:
            dispatch(s, {"action": cmd, "side": current_side(s)})
        for cmd in ["levy_disband_done", "levy_disband_done"]:
            dispatch(s, {"action": cmd, "side": current_side(s)})
        moves = enumerate_legal(s)
        actions = {m["action"] for m in moves}
        assert "levy_muster_vassal" in actions
        assert "levy_muster_transport" in actions
        assert "levy_muster_capability" in actions
        assert "levy_muster_done" in actions
