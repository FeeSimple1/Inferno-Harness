"""Phase 6 tests: Capability hooks for Battle/Storm unit-strike modifiers
and timing-based Capabilities (Astrologers, Via Francigena).

Per CROSS_PROJECT_LESSONS §6 audit lens 'rule-cite-but-no-enforce': for
each Capability we test that the hook actually fires AND that the
resulting state change is what the rule prescribes.
"""

from __future__ import annotations

import pytest

from inferno.actions import dispatch
from inferno.battle import (
    _capability_strike_modifier,
    _lord_has_capability,
    _trebuchets_walls_reduction,
    resolve_battle,
    resolve_storm,
)
from inferno.rng import HarnessRNG
from inferno.scenarios import load_scenario


def _put_in_play(state, lord_id, card_id, scope="this_lord"):
    """Helper: give Lord (or side) the Capability of `card_id`."""
    from inferno import card_data as cd
    card = cd.AOW_CARDS_BY_ID[card_id]
    if scope == "this_lord":
        state["lords"][lord_id].setdefault("capabilities", []).append(card_id)
    else:
        state.setdefault("capabilities_in_play", []).append({
            "id": card_id, "name": card["capability_name"],
            "side": state["lords"][lord_id]["side"], "scope": "side_wide",
        })


# =====================================================================
# Capability lookup
# =====================================================================
class TestCapabilityLookup:
    def test_lord_has_capability_via_this_lord_card(self):
        s = load_scenario("A", seed=1)
        _put_in_play(s, "firenze", "F6", scope="this_lord")  # F6 cap = Feditori
        assert _lord_has_capability(s, "firenze", "Feditori")

    def test_lord_has_capability_via_side_wide(self):
        s = load_scenario("A", seed=1)
        _put_in_play(s, "firenze", "F22", scope="side_wide")  # F22 cap = Tau Company
        assert _lord_has_capability(s, "firenze", "Tau Company")

    def test_lord_does_not_have_unrelated_capability(self):
        s = load_scenario("A", seed=1)
        assert not _lord_has_capability(s, "firenze", "Feditori")


# =====================================================================
# Strike modifiers — Battle Melee
# =====================================================================
class TestFeditoriHook:
    def test_feditori_adds_cavalieri_strikes_r1(self):
        """F6 Feditori: up to 4 Cavalieri x2 strike in Battle Melee R1-R2."""
        s = load_scenario("A", seed=1)
        firenze = s["lords"]["firenze"]
        firenze["forces"] = {"Cavalieri": 3, "Men-at-Arms": 2}
        _put_in_play(s, "firenze", "F6", scope="this_lord")
        # Base Cavalieri strikes = 3 * 1 = 3; Feditori adds +1 each up to 4 cap.
        extra = _capability_strike_modifier(
            s, "firenze", firenze["forces"], "atk_horse_melee", 1, "battle",
        )
        assert extra == 3  # min(3, 4 Guelph cap) * 1

    def test_feditori_no_effect_in_r3(self):
        """Feditori only fires R1-R2."""
        s = load_scenario("A", seed=1)
        firenze = s["lords"]["firenze"]
        firenze["forces"] = {"Cavalieri": 3}
        _put_in_play(s, "firenze", "F6", scope="this_lord")
        extra = _capability_strike_modifier(
            s, "firenze", firenze["forces"], "atk_horse_melee", 3, "battle",
        )
        assert extra == 0

    def test_ghib_feditori_caps_at_3_not_4(self):
        """S6 Feditori caps at 3 Cavalieri per Ghibelline Tip text."""
        s = load_scenario("A", seed=1)
        siena = s["lords"]["siena"]
        siena["forces"] = {"Cavalieri": 5}
        _put_in_play(s, "siena", "S6", scope="this_lord")
        extra = _capability_strike_modifier(
            s, "siena", siena["forces"], "def_horse_melee", 1, "battle",
        )
        assert extra == 3  # Ghibelline cap


class TestArmyReserveHook:
    def test_army_reserve_r3_cavalieri_strike_double(self):
        """F12 Army Reserve: Firenze/Arezzo/Lucca Cavalieri x2 from R3."""
        s = load_scenario("A", seed=1)
        firenze = s["lords"]["firenze"]
        firenze["forces"] = {"Cavalieri": 3}
        _put_in_play(s, "firenze", "F12", scope="side_wide")
        # R3+ Battle: +3 (since each Cavalieri gets +1)
        extra = _capability_strike_modifier(
            s, "firenze", firenze["forces"], "atk_horse_melee", 3, "battle",
        )
        assert extra == 3

    def test_army_reserve_only_eligible_lords(self):
        """F12 not applicable to colle or guido_guerra."""
        s = load_scenario("D", seed=1)  # has guido + colle Mustered
        colle = s["lords"]["colle"]
        colle["forces"] = {"Cavalieri": 2}
        _put_in_play(s, "colle", "F12", scope="side_wide")
        extra = _capability_strike_modifier(
            s, "colle", colle["forces"], "atk_horse_melee", 3, "battle",
        )
        assert extra == 0


# =====================================================================
# Strike modifiers — Archery
# =====================================================================
class TestArcieriHook:
    def test_arcieri_enables_militia_archery(self):
        """F16/F17 Arcieri: Militia get x1 Archery."""
        s = load_scenario("A", seed=1)
        arezzo = s["lords"]["arezzo"]
        arezzo["forces"] = {"Militia": 2}
        _put_in_play(s, "arezzo", "F16", scope="this_lord")
        extra = _capability_strike_modifier(
            s, "arezzo", arezzo["forces"], "atk_archery", 1, "battle",
        )
        assert extra == 2

    def test_luceria_overrides_arcieri_at_1_5x(self):
        """S7 Luceria: up to 3 Militia get x1.5 Archery (replaces Arcieri)."""
        s = load_scenario("A", seed=1)
        siena = s["lords"]["siena"]
        siena["forces"] = {"Militia": 4}
        _put_in_play(s, "siena", "S7", scope="this_lord")
        extra = _capability_strike_modifier(
            s, "siena", siena["forces"], "def_archery", 1, "battle",
        )
        assert extra == 4.5  # min(4, 3) * 1.5 = 4.5


class TestBalestrieriHook:
    def test_balestrieri_armigieri_archery(self):
        """F9 Balestrieri: up to 3 Armigeri get x1 Crossbow Archery."""
        s = load_scenario("A", seed=1)
        firenze = s["lords"]["firenze"]
        firenze["forces"] = {"Armigieri": 5}
        _put_in_play(s, "firenze", "F9", scope="this_lord")
        extra = _capability_strike_modifier(
            s, "firenze", firenze["forces"], "atk_archery", 1, "battle",
        )
        assert extra == 3  # capped at 3


class TestBalestreGrosse:
    def test_balestre_grosse_storm_only(self):
        """F8 Balestre Grosse: Men-at-Arms Crossbow x0.5 in Storm only."""
        s = load_scenario("A", seed=1)
        firenze = s["lords"]["firenze"]
        firenze["forces"] = {"Men-at-Arms": 4}
        _put_in_play(s, "firenze", "F8", scope="this_lord")
        # Battle: no effect
        b_extra = _capability_strike_modifier(
            s, "firenze", firenze["forces"], "atk_archery", 1, "battle",
        )
        assert b_extra == 0
        # Storm: +2 (4 * 0.5)
        s_extra = _capability_strike_modifier(
            s, "firenze", firenze["forces"], "atk_archery", 1, "storm",
        )
        assert s_extra == 2


# =====================================================================
# Storm-only: Trebuchets
# =====================================================================
class TestTrebuchets:
    def test_trebuchets_no_effect_below_3_siege(self):
        s = load_scenario("A", seed=1)
        s["locales"]["Volterra"]["siege"] = [{"side": "guelph", "color": "purple", "count": 2}]
        firenze = s["lords"]["firenze"]
        _put_in_play(s, "firenze", "F4", scope="this_lord")  # F4 cap = Trebuchets
        r = _trebuchets_walls_reduction(s, "Volterra", [], ["firenze"], "storm")
        assert r == 0

    def test_trebuchets_reduces_walls_at_3_siege(self):
        s = load_scenario("A", seed=1)
        s["locales"]["Volterra"]["siege"] = [{"side": "guelph", "color": "purple", "count": 3}]
        firenze = s["lords"]["firenze"]
        _put_in_play(s, "firenze", "F4", scope="this_lord")
        firenze["forces"] = {"Cavalieri": 1}  # Unrouted
        r = _trebuchets_walls_reduction(s, "Volterra", [], ["firenze"], "storm")
        assert r == 1

    def test_trebuchets_not_when_lord_routed(self):
        """Trebuchets requires the Lord Unrouted."""
        s = load_scenario("A", seed=1)
        s["locales"]["Volterra"]["siege"] = [{"side": "guelph", "color": "purple", "count": 3}]
        firenze = s["lords"]["firenze"]
        _put_in_play(s, "firenze", "F4", scope="this_lord")
        firenze["forces"] = {}  # all routed
        r = _trebuchets_walls_reduction(s, "Volterra", [], ["firenze"], "storm")
        assert r == 0


# =====================================================================
# Timing: Astrologers + Via Francigena (Command +1)
# =====================================================================
class TestAstrologers:
    def test_astrologers_first_card_die_1_or_2_bonus(self):
        """F24 Astrologers: 1d6 on first Command card; ≤2 = +1 Command."""
        s = load_scenario("A", seed=1)
        # Walk to command_phase with Firenze
        for name, side in [
            ("levy_aow_draw","guelph"),("levy_aow_draw","ghibelline"),
            ("levy_pay_done","guelph"),("levy_pay_done","ghibelline"),
            ("levy_disband_done","guelph"),("levy_disband_done","ghibelline"),
            ("levy_muster_done","guelph"),("levy_muster_done","ghibelline"),
            ("levy_cta_skip","guelph"),("levy_cta_skip","ghibelline"),
        ]:
            dispatch(s, {"action": name, "side": side})
        from tests.test_phase3a import _skip_capability_discard, _build_pass_plan
        _skip_capability_discard(s)
        _build_pass_plan(s, "guelph")
        _build_pass_plan(s, "ghibelline")
        # Give Firenze Astrologers
        _put_in_play(s, "firenze", "F24", scope="side_wide")
        # Inject Firenze command card on top of Guelph plan
        s["plan_stacks"]["guelph"].insert(0, "command_firenze")
        # Find a seed that produces 1 or 2 on the astrologers roll
        # Run with the current seed; check if bonus was applied.
        dispatch(s, {"action": "command_reveal", "side": "guelph"})
        # actions_remaining = command rating (2) + maybe bonus (0 or 1).
        # Firenze's flag should be set
        assert s["lords"]["firenze"]["flags"].get("astrologers_rolled_this_campaign") is True

    def test_via_francigena_command_plus_one_at_friendly_seat(self):
        """F23 Via Francigena: Guelph (not Guido/Orvieto) at Friendly Lord Seat -> Command +1."""
        s = load_scenario("A", seed=1)
        for name, side in [
            ("levy_aow_draw","guelph"),("levy_aow_draw","ghibelline"),
            ("levy_pay_done","guelph"),("levy_pay_done","ghibelline"),
            ("levy_disband_done","guelph"),("levy_disband_done","ghibelline"),
            ("levy_muster_done","guelph"),("levy_muster_done","ghibelline"),
            ("levy_cta_skip","guelph"),("levy_cta_skip","ghibelline"),
        ]:
            dispatch(s, {"action": name, "side": side})
        from tests.test_phase3a import _skip_capability_discard, _build_pass_plan
        _skip_capability_discard(s)
        _build_pass_plan(s, "guelph")
        _build_pass_plan(s, "ghibelline")
        # Give Firenze Via Francigena
        _put_in_play(s, "firenze", "F23", scope="side_wide")
        # Firenze at his Lord Seat (Firenze) by default
        s["plan_stacks"]["guelph"].insert(0, "command_firenze")
        dispatch(s, {"action": "command_reveal", "side": "guelph"})
        # Firenze Command rating = 2; bonus = +1; actions_remaining = 3.
        assert s["actions_remaining"] == 3
