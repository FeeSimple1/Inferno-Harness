"""Separate combat mats share the Commander's post-Battle movement (1.5.1)."""

import json

import pytest

from inferno import actions
from inferno.invariants import check_all_invariants
from inferno.llm.interface import DecisionView, play_with_interface
from inferno.scenarios import load_scenario
from inferno.state import load_saved_state
from tests._helpers import _finish_pending_choices
from tests.test_cross_game_escape import place
from tests.test_phase3a import _skip_capability_discard

PAIR = ["firenze", "firenze_comune"]


def _act(state, kind, side, **args):
    return actions.dispatch(state, {"action": kind, "side": side, "args": args})


def _approach(companion, companion_first):
    state = load_scenario("D", seed=1)
    for step in ("levy_aow_draw", "levy_pay_done", "levy_disband_done", "levy_muster_done"):
        for side in ("guelph", "ghibelline"):
            _act(state, step, side)
    _act(state, "levy_cta_declare", "guelph")
    for side, commander in (("guelph", "firenze"), ("ghibelline", "siena")):
        _act(state, "cta_step_skip", side)
        mode = ("muster_only" if state["lords"][commander]["status"] == "on_calendar"
                else "disband_and_remuster")
        _act(state, "cta_commander_arms", side, mode=mode)
        step = "cta_comune_setup" if side == "guelph" and companion in PAIR else "cta_step_skip"
        _act(state, step, side)
        _act(state, "cta_step_skip", side)
    _skip_capability_discard(state)
    for side, first in (("guelph", ["PASS", "command_firenze"]), ("ghibelline", ["command_siena"])):
        for card in first + ["PASS"] * (6 - len(first)):
            _act(state, "plan_add_card", side, card_id=card)
        _act(state, "plan_done", side)

    # Stage the encounter with intact native mats and their original Forces.
    defenders = [companion, "firenze"] if companion_first else ["firenze", companion]
    for lid, destination in [(lid, "Figline") for lid in defenders] + [("siena", "San Giovanni")]:
        lord = state["lords"][lid]
        state["locales"][lord["location"]]["lords_present"].remove(lid)
        lord["location"] = destination
        state["locales"][destination]["lords_present"].append(lid)
    state["locales"]["San Giovanni"]["current_allegiance"] = [{"side": "ghibelline", "value": 1}]
    state["vp"]["ghibelline"] += 1
    check_all_invariants(state)
    _act(state, "command_reveal", "guelph")
    _finish_pending_choices(state)
    _act(state, "command_reveal", "ghibelline")
    _act(state, "cmd_march", "ghibelline", lord_id="siena", destination="Figline", way_type="road")
    return state


def _resolve_through_player_interface(state):
    fates = []

    def choose(view):
        overview = view.overview()
        if overview["can_yield"]:
            return {"yield": True, "state_version": view.version}
        if not isinstance(view, DecisionView):
            rows = view.query({"request": "actions", "category": "approach_response"})["records"]
            selected = next(row for row in rows if row["move"]["args"]["choice"] == "stand")
        else:
            rows = view.query({"request": "actions"})["records"]
            options = [row["move"]["args"]["choice"] for row in rows]
            kind, context = overview["decision"], overview["context"]
            choice = options[0]
            if kind == "initial_placement_defender":
                choice = "firenze"
            elif kind == "concede":
                choice = "yes" if view.side == "guelph" else "no"
            elif kind in ("post_battle_fate", "post_battle_withdraw"):
                assert view.side == "guelph"
                fates.append((context.get("lord_ids", [context["lord_id"]]), options))
                choice = "withdraw" if context["lord_id"] == "arezzo" else "retreat"
            elif kind == "retreat_destination":
                choice = "Firenze"
            selected = next(row for row in rows if row["move"]["args"]["choice"] == choice)
        return {"action_id": selected["action_id"], "state_version": view.version}

    while any(p["type"] == "approach_response" for p in state["pending"]):
        receipt = play_with_interface(state, choose, max_strikes=1).applied
    return receipt["state_changes"]["battle_result"], fates


@pytest.mark.parametrize("companion, companion_first", [
    ("firenze_comune", False), ("firenze_comune", True), ("arezzo", False),
])
def test_player_fate_choices_keep_comune_attached_through_save_and_march(
        tmp_path, companion, companion_first):
    state = _approach(companion, companion_first)
    saved = tmp_path / "approach.json"
    saved.write_text(json.dumps(state))
    restored = load_saved_state(saved)
    result, fates = _resolve_through_player_interface(state)
    assert _resolve_through_player_interface(restored) == (result, fates)
    assert restored == state
    assert result["loser"] == result["conceded"] == "defender"
    assert state["lords"]["firenze"]["location"] == "Firenze"
    if companion == "arezzo":
        assert len(fates) == 2
        assert state["lords"][companion]["location"] == "Figline"
        assert state["lords"][companion]["flags"]["in_stronghold"]
    else:
        assert fates == [(PAIR, ["retreat", "remove"])]  # Figline has one space.
        assert state["lords"][companion]["location"] == "Firenze"
        assert state["lords"]["firenze"]["service_box"] == 11  # Retained Carroccio.
        saved.write_text(json.dumps(state))
        restored = load_saved_state(saved)
        _finish_pending_choices(restored)
        _act(restored, "besiege_or_bypass", "ghibelline", choice="besiege")
        _finish_pending_choices(restored)
        _act(restored, "command_reveal", "guelph")
        march = _act(restored, "cmd_march", "guelph", lord_id="firenze",
                     destination="Prato", way_type="track")
        assert march["state_changes"]["group"] == PAIR
        check_all_invariants(restored)
    check_all_invariants(state)


def _post_battle(locale, already_inside=()):
    state = load_scenario("D", seed=1)
    for lid in [*PAIR, "siena", *already_inside]:
        lord = place(state, lid, locale)
        if lid in already_inside:
            lord["flags"]["in_stronghold"] = True
    actions._place_service(state, "firenze_comune", None)
    state["meta"]["approach_breadcrumb"] = {
        "approached_from": "Figline" if locale == "Firenze" else "San Giovanni",
        "approached_via": "road",
    }
    return state, {"loser": "defender", "conceded": None, "removed_lords": []}


@pytest.mark.parametrize("locale, already_inside, withdraws", [
    ("Figline", (), False),
    ("Firenze", ("arezzo",), True),
    ("Firenze", ("arezzo", "orvieto"), False),
])
def test_scripted_comune_withdrawal_requires_two_free_spaces(locale, already_inside, withdraws):
    state, result = _post_battle(locale, already_inside)
    actions._apply_post_battle(state, result, ["siena"], PAIR[::-1], battle_locale=locale,
                               decisions=[{"type": "post_battle_withdraw", "choice": "withdraw"}])
    first, second = (state["lords"][lid] for lid in PAIR)
    assert first["location"] == second["location"]
    assert (first["location"] == locale) == withdraws
    assert all(bool(lord["flags"].get("in_stronghold")) == withdraws for lord in (first, second))
    check_all_invariants(state)


def test_comune_shares_the_retreat_route_and_keeps_separate_loss_rolls():
    state, result = _post_battle("Firenze")
    for lid in PAIR:
        state["lords"][lid].update(forces={"Armigieri": 1}, routed_units={"Armigieri": 1})
    actions._apply_post_battle(
        state, result, ["siena"], PAIR, battle_locale="Firenze",
        decisions=[{"type": "retreat_destination", "choice": "Prato"}],
    )
    assert all(state["lords"][lid]["location"] == "Prato" for lid in PAIR)
    assert set(result["loss_results"]) == set(PAIR)
    assert [r["context"] for r in result["rolls"] if r["context"].startswith("retreat_shift_")] == [
        "retreat_shift_firenze"]
    check_all_invariants(state)


@pytest.mark.parametrize("empty_mat", PAIR)
def test_only_surviving_mats_count_toward_withdrawal_capacity(empty_mat):
    state, result = _post_battle("Figline")
    state["lords"][empty_mat]["forces"] = {}
    actions._apply_post_battle(state, result, ["siena"], PAIR[::-1], battle_locale="Figline",
                               decisions=[{"type": "post_battle_withdraw", "choice": "withdraw"}])
    assert state["lords"]["firenze_comune"]["status"] == "in_levy_pool"
    if empty_mat == "firenze":
        assert set(result["removed_lords"]) == set(PAIR)
    else:
        assert result["removed_lords"] == [empty_mat]
        assert state["lords"]["firenze"]["flags"]["in_stronghold"]
    check_all_invariants(state)
