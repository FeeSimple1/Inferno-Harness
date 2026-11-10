"""Phase 3d tests: Battle cleanup + Bypass-state March + Lieutenants."""
from __future__ import annotations

import copy
import inspect
import json

import pytest

from inferno import static_data as sd
from inferno.actions import IllegalAction, dispatch
from inferno.battle import (
    loss_roll_for_routed,
    service_shift_for_retreated,
    transfer_spoils,
)
from inferno.invariants import check_all_invariants
from inferno.legal_moves import enumerate_legal
from inferno.rng import HarnessRNG
from inferno.scenarios import load_scenario
from tests._helpers import _finish_pending_choices, _place
from tests.test_phase3a import _skip_capability_discard, _skip_levy


def _stand_battle_setup():
    """Build a state where a Battle has just resolved (manually constructed).
    Used to test the post-Battle helpers directly."""
    s = load_scenario("A", seed=1)
    # Force-place defender flags as if having Routed
    s["lords"]["siena"]["routed_units"] = {"Cavalieri": 1, "Men-at-Arms": 1}
    s["lords"]["siena"]["forces"] = {}  # all routed
    return s


# =====================================================================
# 4.4.4 Loss rolls + Knights' Quarter
# =====================================================================
class TestLossRolls:
    def test_villici_never_roll(self):
        s = _stand_battle_setup()
        s["lords"]["siena"]["routed_units"] = {"Villici": 3}
        rng = HarnessRNG(seed=1)
        r = loss_roll_for_routed(s, "siena", harsh_recovery=False, rng_caller=rng.roll)
        assert r["lost"] == {}
        assert r["recovered"] == {}
        assert r["captured"] == {}

    def test_harsh_recovery_only_recovers_on_1(self):
        """Harsh Recovery: unit fails unless roll == 1."""
        s = _stand_battle_setup()
        s["lords"]["siena"]["routed_units"] = {"Cavalieri": 6}
        rng = HarnessRNG(seed=1)
        r = loss_roll_for_routed(s, "siena", harsh_recovery=True, rng_caller=rng.roll)
        # Recovered count should equal number of dice that rolled 1.
        # With seed=1 we get some distribution; assert structural property.
        assert sum(r["recovered"].values()) + sum(r["lost"].values()) + sum(r["captured"].values()) == 6

    def test_knights_quarter_captures_cavalieri_lost_on_high_roll(self):
        """4.4.4: Cavalieri/Ritter lost on a 3-6 go to Owner's Captured Knights box."""
        # Force harsh recovery so anything not a 1 is lost or captured.
        s = _stand_battle_setup()
        s["lords"]["siena"]["routed_units"] = {"Cavalieri": 10}
        rng = HarnessRNG(seed=2)
        r = loss_roll_for_routed(s, "siena", harsh_recovery=True, rng_caller=rng.roll)
        # Lord's side is Ghibelline; captured knights stored under that side.
        assert s.get("captured_knights", {}).get("ghibelline", {}) != {}
        # Each die landing >= 3 captures; each 2 = lost; each 1 = recovered.
        # Total processed = 10.
        cap_total = sum(s["captured_knights"]["ghibelline"].values())
        assert cap_total + sum(r["lost"].values()) + sum(r["recovered"].values()) == 10


# =====================================================================
# 4.4.3 Service-shift dice
# =====================================================================
class TestServiceShift:
    def test_carroccio_concede_shifts_just_one(self):
        s = _stand_battle_setup()
        s["lords"]["firenze"]["service_box"] = 5
        s["calendar"]["boxes"].setdefault("5", {"cylinders": [], "services": [], "victory": [], "markers": []})
        s["calendar"]["boxes"]["5"]["services"].append("firenze")
        rng = HarnessRNG(seed=1)
        r = service_shift_for_retreated(s, "firenze", conceded_with_carroccio=True, rng_caller=rng.roll)
        assert r["shift_left"] == 1
        assert s["lords"]["firenze"]["service_box"] == 4

    def test_normal_retreat_die_drives_shift(self):
        s = _stand_battle_setup()
        s["lords"]["firenze"]["service_box"] = 10
        s["calendar"]["boxes"].setdefault("10", {"cylinders": [], "services": [], "victory": [], "markers": []})
        s["calendar"]["boxes"]["10"]["services"].append("firenze")
        rng = HarnessRNG(seed=1)
        r = service_shift_for_retreated(s, "firenze", conceded_with_carroccio=False, rng_caller=rng.roll)
        assert 1 <= r["die"] <= 6
        # 1-2 -> 1, 3-4 -> 2, 5-6 -> 3
        expected_shift = 1 if r["die"] <= 2 else (2 if r["die"] <= 4 else 3)
        assert r["shift_left"] == expected_shift
        assert s["lords"]["firenze"]["service_box"] == 10 - expected_shift


# =====================================================================
# 4.4.3 Spoils transfer
# =====================================================================
class TestSpoilsTransfer:
    def test_withdrew_keeps_all_assets(self):
        s = _stand_battle_setup()
        s["lords"]["siena"]["assets"] = {"Coin": 2, "Cart": 2, "Provender": 2}
        r = transfer_spoils(s, "siena", winners=["firenze"],
                             retreated=False, conceded=False, withdrew=True)
        assert r["transferred"] == {}
        assert s["lords"]["siena"]["assets"]["Coin"] == 2

    def test_removed_loses_all_except_ships(self):
        s = _stand_battle_setup()
        s["lords"]["siena"]["assets"] = {"Coin": 2, "Cart": 2, "Provender": 2, "Ship": 0}
        r = transfer_spoils(s, "siena", winners=["firenze"],
                             retreated=False, conceded=False, withdrew=False)
        # All non-Ship assets transferred
        assert s["lords"]["siena"]["assets"]["Coin"] == 0
        assert s["lords"]["siena"]["assets"]["Cart"] == 0
        assert s["lords"]["siena"]["assets"]["Provender"] == 0
        # Winner received them
        assert s["lords"]["firenze"]["assets"]["Coin"] >= 2

    def test_conceded_retreat_keeps_carroccio_loses_only_loot_and_excess_prov(self):
        s = _stand_battle_setup()
        # Mount a Carroccio on firenze
        s["lords"]["firenze"]["vassals"].append({
            "name": "Carroccio", "special": True, "on_mat": True, "ready": True,
            "forces": {"Cavalieri": 1, "Villici": 1},
        })
        s["lords"]["firenze"]["assets"] = {"Cart": 1, "Provender": 4, "Loot": 2}
        r = transfer_spoils(s, "firenze", winners=["siena"],
                             retreated=True, conceded=True, withdrew=False)
        # SMOKE-Inferno-048: Concede+Retreat transfers Loot + Provender BEYOND the
        # Unladen carry, which is up to 2x Provender per Cart on Road (Commands
        # 4.3.2). With 1 Cart the loser carries 2 Provender Unladen, so excess =
        # 4 - 2*1 = 2 transferred, leaving 2 (was wrongly 4 - 1 = 3 / leaving 1).
        assert s["lords"]["firenze"]["assets"]["Loot"] == 0
        assert s["lords"]["firenze"]["assets"]["Provender"] == 2
        assert r["transferred"]["Provender"] == 2
        assert r["transferred"]["Loot"] == 2
        # Carroccio retained
        assert any(v.get("name") == "Carroccio" for v in s["lords"]["firenze"]["vassals"])


# =====================================================================
# 4.3.6 Encamp action
# =====================================================================
class TestEncamp:
    def test_encamp_replaces_bypass_with_siege_and_ends_card(self):
        from tests.test_phase3c import _to_command_with
        s = _to_command_with("A", seed=1, lord_id="firenze",
                             lord_location_override="Volterra")
        # Bypass first
        dispatch(s, {"action": "besiege_or_bypass", "side": "guelph",
                     "args": {"lord_id": "firenze", "choice": "bypass"}})
        assert s["locales"]["Volterra"]["bypass"]
        # Now Encamp
        dispatch(s, {"action": "cmd_encamp", "side": "guelph",
                     "args": {"lord_id": "firenze"}})
        assert s["locales"]["Volterra"]["siege"]
        assert s["locales"]["Volterra"]["bypass"] == []
        # Card ended
        assert s["current_lord_id"] is None


# =====================================================================
# 4.1.3 Lieutenants
# =====================================================================
class TestLieutenants:
    def test_lieutenant_attach_during_plan(self):
        from tests.test_phase3a import _skip_capability_discard
        s = load_scenario("D", seed=1)
        for name, side in [
            ("levy_aow_draw","guelph"),("levy_aow_draw","ghibelline"),
            ("levy_pay_done","guelph"),("levy_pay_done","ghibelline"),
            ("levy_disband_done","guelph"),("levy_disband_done","ghibelline"),
            ("levy_muster_done","guelph"),("levy_muster_done","ghibelline"),
            ("levy_cta_skip","guelph"),("levy_cta_skip","ghibelline"),
        ]:
            dispatch(s, {"action": name, "side": side})
        _skip_capability_discard(s)
        # In scenario D, Arezzo + Orvieto are both Mustered at Arezzo.
        # Neither is a Commander/Comune. Attach Lieutenant.
        # Note: Arezzo Podestà — is he a Commander? Per static_data: Firenze + Siena are Commanders. Arezzo is not.
        # However Arezzo IS a Podestà; that's fine for Lieutenant per 4.1.3 (only Commander+Comune excluded).
        r = dispatch(s, {"action": "plan_attach_lieutenant", "side": "guelph",
                         "args": {"lieutenant": "arezzo", "lower_lord": "orvieto"}})
        assert s["lords"]["arezzo"]["flags"]["has_lower_lord"] == "orvieto"
        assert s["lords"]["orvieto"]["flags"]["lower_lord_of"] == "arezzo"

    def test_commander_cannot_be_lieutenant(self):
        from tests.test_phase3a import _skip_capability_discard
        s = load_scenario("F", seed=1)
        for name, side in [
            ("levy_aow_draw","guelph"),("levy_aow_draw","ghibelline"),
            ("levy_pay_done","guelph"),("levy_pay_done","ghibelline"),
            ("levy_disband_done","guelph"),("levy_disband_done","ghibelline"),
            ("levy_muster_done","guelph"),("levy_muster_done","ghibelline"),
            ("levy_cta_skip","guelph"),("levy_cta_skip","ghibelline"),
        ]:
            dispatch(s, {"action": name, "side": side})
        _skip_capability_discard(s)
        # Firenze is Commander. Trying to pair firenze with arezzo should be rejected.
        # Need them at same Locale first. Move arezzo to Firenze.
        s["lords"]["arezzo"]["location"] = "Firenze"
        s["locales"]["Arezzo"]["lords_present"].remove("arezzo")
        s["locales"]["Firenze"]["lords_present"].append("arezzo")
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {"action": "plan_attach_lieutenant", "side": "guelph",
                         "args": {"lieutenant": "firenze", "lower_lord": "arezzo"}})
        assert exc.value.code == "COMMANDER_NOT_ELIGIBLE"


def _paired_approach(locale="Firenze"):
    state = load_scenario("D", seed=5)
    _skip_levy(state)
    _skip_capability_discard(state)
    origin = "Figline" if locale == "Firenze" else "Firenze"
    for lid in ("arezzo", "orvieto"):
        _place(state, lid, locale)
    _place(state, "astimberg", origin)
    dispatch(state, {"action": "plan_attach_lieutenant", "side": "guelph",
                     "args": {"lieutenant": "arezzo", "lower_lord": "orvieto"}})
    size = sd.PLAN_SIZE_BY_SEASON[sd.SEASON_BY_BOX[state["meta"]["turn"]]]
    for side in ("guelph", "ghibelline"):
        cards = ["command_astimberg"] if side == "ghibelline" else []
        for card in cards + ["PASS"] * (size - len(cards)):
            dispatch(state, {"action": "plan_add_card", "side": side, "args": {"card_id": card}})
        dispatch(state, {"action": "plan_done", "side": side})
    dispatch(state, {"action": "command_reveal", "side": "guelph"})
    _finish_pending_choices(state)
    dispatch(state, {"action": "command_reveal", "side": "ghibelline"})
    state["meta"].update(rng_seed=5, rng_advance=0)
    dispatch(state, {"action": "cmd_march", "side": "ghibelline",
                     "args": {"lord_id": "astimberg", "destination": locale, "way_type": "road"}})
    return state


def _respond(state, lid, choice, **args):
    return dispatch(state, {"action": "approach_response", "side": "guelph",
                            "args": {"lord_id": lid, "choice": choice, **args}})["state_changes"]


@pytest.mark.parametrize("from_menu", [False, True])
def test_lieutenant_avoid_moves_both_and_shares_carts(from_menu):
    state = _paired_approach()
    state["lords"]["arezzo"]["assets"]["Cart"] = 0
    state = json.loads(json.dumps(state))
    moves = [move for move in enumerate_legal(state)
             if move["action"] == "approach_response" and move["args"].get("destination") == "Prato"]
    assert len(moves) == 1 and moves[0]["args"]["with_lords"] == ["orvieto"]
    if from_menu:
        result = dispatch(state, moves[0])["state_changes"]
    else:
        result = _respond(state, "orvieto", "avoid", destination="Prato")
    assert set(result["avoided"]) == {"arezzo", "orvieto"}
    assert result["approach_resolved"] == "no_battle"
    assert state["lords"]["arezzo"]["assets"]["Provender"] == 2
    assert all(state["lords"][lid]["location"] == "Prato" for lid in result["avoided"])
    check_all_invariants(state)


@pytest.mark.parametrize("locale, fits", [("Firenze", True), ("Figline", False)])
def test_lieutenant_approach_withdrawal_requires_room_for_both(locale, fits):
    state = _paired_approach(locale)
    moves = [move for move in enumerate_legal(state)
             if move["action"] == "approach_response" and move["args"].get("choice") == "withdraw"]
    if fits:
        result = dispatch(state, moves[0])["state_changes"]
        assert set(result["withdrawn"]) == {"arezzo", "orvieto"}
        assert result["approach_resolved"] == "no_battle"
        for lid in result["withdrawn"]:
            flags = state["lords"][lid]["flags"]
            assert flags["in_stronghold"] and not flags.get("moved_fought")
    else:
        assert moves == []
        before = copy.deepcopy(state)
        with pytest.raises(IllegalAction, match="STRONGHOLD_FULL"):
            _respond(state, "arezzo", "withdraw")
        assert state == before
    check_all_invariants(state)


def test_standing_lieutenant_prevents_partner_from_leaving_the_battle():
    state = _paired_approach()
    _respond(state, "arezzo", "stand")
    choices = [move["args"]["choice"] for move in enumerate_legal(state)
               if move["action"] == "approach_response"]
    assert choices == ["stand"]
    before = copy.deepcopy(state)
    with pytest.raises(IllegalAction, match="BAD_AVOID_GROUP"):
        _respond(state, "orvieto", "avoid", destination="Prato")
    with pytest.raises(IllegalAction, match="BAD_WITHDRAW_GROUP"):
        _respond(state, "orvieto", "withdraw")
    assert state == before


@pytest.mark.parametrize("remove_companion", [False, True])
def test_lieutenant_battle_retreat_uses_one_route_and_allows_removal(remove_companion):
    state = _paired_approach()
    routes = []

    def choose(decision):
        kind = decision["type"]
        if kind == "concede":
            return "yes" if decision["side"] == "defender" else "no"
        if kind == "retreat_destination":
            routes.append(decision["info"])
            return "Prato"
        return decision["options"][0]

    state["battle_callback"] = choose
    _respond(state, "arezzo", "stand")
    script = []
    if remove_companion:
        script = [{"type": "retreat_destination", "choice": "Prato"},
                  {"type": "post_battle_withdraw", "choice": "remove"}]
    battle = _respond(state, "orvieto", "stand", post_battle_decisions=script)["battle_result"]
    state.pop("battle_callback")
    assert battle["loser"] == battle["conceded"] == "defender"
    assert state["lords"]["arezzo"]["location"] == "Prato"
    if remove_companion:
        assert "orvieto" in battle["removed_lords"]
        assert "has_lower_lord" not in state["lords"]["arezzo"]["flags"]
    else:
        assert routes == [{"lord_id": "arezzo", "lord_ids": ["arezzo", "orvieto"]}]
        assert state["lords"]["orvieto"]["location"] == "Prato"
        assert state["lords"]["orvieto"]["flags"]["lower_lord_of"] == "arezzo"
    check_all_invariants(state)


@pytest.mark.parametrize("locale, fits", [("Firenze", True), ("Figline", False)])
def test_lieutenant_battle_withdrawal_respects_capacity(locale, fits):
    state = _paired_approach(locale)
    offered = {}

    def choose(decision):
        if decision["type"] == "concede":
            return "yes" if decision["side"] == "defender" else "no"
        if decision["type"] == "post_battle_withdraw":
            offered[decision["info"]["lord_id"]] = decision
            return "withdraw" if "withdraw" in decision["options"] else "remove"
        return decision["options"][0]

    state["battle_callback"] = choose
    _respond(state, "arezzo", "stand")
    battle = _respond(state, "orvieto", "stand")["battle_result"]
    state.pop("battle_callback")
    assert state["lords"]["arezzo"]["flags"]["in_stronghold"]
    if fits:
        assert state["lords"]["orvieto"]["flags"]["in_stronghold"]
        assert "orvieto" not in battle["removed_lords"]
    else:
        assert offered["arezzo"]["info"]["requires_partner_removal"] == ["withdraw"]
        assert offered["orvieto"]["options"] == ["remove"]
        assert "orvieto" in battle["removed_lords"]
    check_all_invariants(state)


# =====================================================================
# Source markers
# =====================================================================
class TestSourceMarkers:
    @pytest.mark.parametrize("marker", ["SMOKE-Inferno-016", "SMOKE-Inferno-017"])
    def test_marker_present(self, marker):
        import inferno.legal_moves as m
        assert marker in inspect.getsource(m)
