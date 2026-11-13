"""Greek Fire Disband and effective Pay through the player interface."""

from copy import deepcopy

import pytest

from inferno import actions as A
from inferno.invariants import check_all_invariants
from inferno.legal_moves import enumerate_legal
from inferno.llm.interface import PlayerView
from inferno.scenarios import load_scenario
from tests._helpers import _finish_pending_choices
from tests.test_round16_approach import _reload
from tests.test_selfplay_followup_fixes import hold
from tests.test_v614_audit_regressions import command, levy, muster


def _select(state, action, **args):
    view = PlayerView(state)
    page = view.query({"request": "actions", "category": action, "page_size": 100})
    row = next(row for row in page["records"]
               if all(row["move"]["args"].get(key) == value for key, value in args.items()))
    return view.resolve({"action_id": row["action_id"], "state_version": view.version})


@pytest.mark.parametrize("card,actor,target,locale,color,companion", [
    ("F7", "arezzo", "astimberg", "Firenze", "gold", "provenzano"),
    ("S7", "pisa", "guido_guerra", "Pisa", "purple", "orvieto"),
])
@pytest.mark.parametrize("survivor", ["none", "unit", "besieger"])
def test_greek_fire_disbands_empty_besieger_and_lifts_only_a_freed_siege(
        card, actor, target, locale, color, companion, survivor, tmp_path):
    state = command(actor, locale)
    side = state["lords"][actor]["side"]
    enemy_side = state["lords"][target]["side"]
    for lid in state["locales"][locale]["lords_present"]:
        if state["lords"][lid]["side"] == side:
            state["lords"][lid]["flags"]["in_stronghold"] = True
    forces = {"Ritter": 1}
    if survivor == "unit":
        forces["Men-at-Arms"] = 1
    muster(state, target, locale, forces=forces)
    if survivor == "besieger":
        muster(state, companion, locale, forces={"Ritter": 1})
    state["locales"][locale]["siege"] = [{"side": enemy_side, "color": color, "count": 3}]
    hold(state, side, card)
    check_all_invariants(state)
    action = _select(state, "play_event", card_id=card, effect_args={
        "enemy_lord_id": target, "unit_to_remove": "Ritter",
    })
    replay = _reload(state, tmp_path)
    result = A.dispatch(state, action)
    assert A.dispatch(replay, action) == result and replay == state
    assert state["decks"][side]["aow_discard"].count(card) == 1
    effect = result["state_changes"]["effect"]
    assert effect["removed_unit"] == "Ritter"
    assert effect["disbanded"] == (survivor != "unit")
    assert effect["siege_lifted"] == (survivor == "none")
    lord = state["lords"][target]
    if survivor != "unit":
        assert lord["status"] == "on_calendar"
        assert lord["calendar_box"] == state["calendar"]["levy_box"] + lord["ratings"]["S"] + 1
        assert lord["location"] is None and lord["service_box"] is None
        assert not lord["assets"] and not lord["forces"]
        assert target not in state["locales"][locale]["lords_present"]
    else:
        assert lord["status"] == "mustered" and lord["forces"] == {"Men-at-Arms": 1}
    if survivor == "none":
        assert not state["locales"][locale]["siege"]
        assert not state["lords"][actor]["flags"].get("in_stronghold")
    else:
        assert state["locales"][locale]["siege"] == [
            {"side": enemy_side, "color": color, "count": 1}]
        assert state["lords"][actor]["flags"]["in_stronghold"]
    check_all_invariants(state)


def test_greek_fire_releases_the_approach_response_of_a_disbanded_besieger():
    state = command("arezzo", "Figline")
    muster(state, "astimberg", "Firenze", forces={"Ritter": 1})
    muster(state, "orvieto", "Firenze")
    state["lords"]["orvieto"]["flags"]["in_stronghold"] = True
    state["locales"]["Firenze"]["siege"] = [{"side": "ghibelline", "color": "gold", "count": 2}]
    hold(state, "guelph", "F7")
    A.dispatch(state, _select(state, "cmd_march", destination="Firenze"))
    assert state["meta"]["active_player"] == "ghibelline"
    view = PlayerView(state, side="guelph")
    row = next(row for row in view.query({"request": "actions"})["records"]
               if row["move"]["args"].get("card_id") == "F7")
    result = A.dispatch(state, view.resolve({"action_id": row["action_id"], "state_version": view.version}))
    assert result["state_changes"]["approach_resolved"] == "no_battle"
    assert not state["pending"] and not state.get("pending_besiege")
    assert not state["locales"]["Firenze"]["siege"]
    assert state["lords"]["astimberg"]["location"] is None
    assert not state["lords"]["orvieto"]["flags"].get("in_stronghold")
    check_all_invariants(state)


def _assert_atomic_pay_rejection(state, move, amount):
    before = deepcopy(state)
    with pytest.raises(A.IllegalAction) as exc:
        A.dispatch(state, {**move, "args": {**move["args"], "amount": amount}})
    assert exc.value.code == "PAY_NO_SERVICE_SHIFT"
    assert state == before


def test_native_pay_moves_box_16_to_off_right_and_preserves_remaining_coin(tmp_path):
    state = load_scenario("E", seed=1)
    for side in ("guelph", "ghibelline"):
        A.dispatch(state, {"action": "levy_aow_draw", "side": side})
        _finish_pending_choices(state)
    A.dispatch(state, {"action": "levy_pay_done", "side": "guelph"})
    # Stage prior Service extension. Giordano keeps his native two Coin.
    A._place_service(state, "giordano", 16)
    move = _select(state, "levy_pay", from_lord_id="giordano", target_lord_id="giordano", asset="Coin")
    _assert_atomic_pay_rejection(state, move, 2)
    replay = _reload(state, tmp_path)
    result = A.dispatch(state, move)
    assert A.dispatch(replay, move) == result and replay == state
    assert result["state_changes"]["new_service_box"] == "off_right_service"
    assert state["lords"]["giordano"]["assets"]["Coin"] == 1
    assert all(m.get("args", {}).get("target_lord_id") != "giordano"
               for m in enumerate_legal(state) if m["action"] == "levy_pay")
    _assert_atomic_pay_rejection(state, move, 1)
    check_all_invariants(state)


@pytest.mark.parametrize("pay", ["levy_pay", "cmd_fpd_pay"])
@pytest.mark.parametrize("asset", ["Coin", "Loot"])
def test_pay_can_advance_an_advanced_vassal_when_the_lord_is_off_right(pay, asset):
    state = levy("3.2") if pay == "levy_pay" else command()
    state["meta"]["advanced_vassal_service"] = True
    if pay == "cmd_fpd_pay":
        state["pending_fpd"] = {"step": "pay", "side": "guelph",
                                "levy_box": state["calendar"]["levy_box"]}
    lord = state["lords"]["firenze"]
    lord["vassals"] = [{"name": "Prato Comune", "on_mat": True, "ready": False, "service_box": 16}]
    lord["assets"][asset] = 4
    A._place_service(state, "firenze", 17)
    move = _select(state, pay, from_lord_id="firenze", target_lord_id="firenze", asset=asset)
    _assert_atomic_pay_rejection(state, move, 2)
    result = A.dispatch(state, move)["state_changes"]
    assert result["amount_paid"] == 2
    assert result["new_service_box"] == "off_right_service"
    assert state["lords"]["firenze"]["vassals"][0]["service_box"] == 17
    assert state["lords"]["firenze"]["assets"][asset] == 2
    assert all(m.get("args", {}).get("target_lord_id") != "firenze"
               for m in enumerate_legal(state) if m["action"] == pay)
    _assert_atomic_pay_rejection(state, move, 1)
