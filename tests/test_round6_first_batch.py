import copy
import json

import pytest

from inferno import actions, static_data
from inferno.invariants import check_all_invariants
from inferno.legal_moves import enumerate_legal
from inferno.llm.filter import hide_for_side
from inferno.llm.interface import PlayerView, selection_session
from inferno.scenarios import load_scenario
from inferno.state import load_saved_state
from tests._helpers import _finish_pending_choices, _place
from tests.test_phase3a import _skip_capability_discard, _skip_levy
from tests.test_phase3e import _to_end_campaign


def _act(state, name, side="guelph", **args):
    return actions.dispatch(state, {"action": name, "side": side, "args": args})


@pytest.mark.parametrize(("expired", "offset", "legacy_save"), [
    ("arezzo", 0, False),
    ("orvieto", -1, False),
    ("arezzo", 0, True),
])
def test_surviving_lord_activates_after_either_lieutenant_partner_disbands(
        expired, offset, legacy_save, tmp_path):
    state = load_scenario("D", seed=1)
    _skip_levy(state)
    _skip_capability_discard(state)
    _act(state, "plan_attach_lieutenant", lieutenant="arezzo", lower_lord="orvieto")
    survivor = "orvieto" if expired == "arezzo" else "arezzo"
    size = static_data.PLAN_SIZE_BY_SEASON[static_data.SEASON_BY_BOX[state["meta"]["turn"]]]
    for side in ("guelph", "ghibelline"):
        cards = ["command_colle", f"command_{survivor}"] if side == "guelph" else []
        for card in cards + ["PASS"] * (size - len(cards)):
            _act(state, "plan_add_card", side, card_id=card)
        _act(state, "plan_done", side)
    _act(state, "command_reveal")
    actions._place_service(state, expired, state["calendar"]["levy_box"] + offset)
    _act(state, "cmd_pass", lord_id="colle", count=99)
    _finish_pending_choices(state)
    assert state["lords"][expired]["status"] != "mustered"
    link = "lower_lord_of" if survivor == "orvieto" else "has_lower_lord"
    assert link not in state["lords"][survivor]["flags"]
    if legacy_save:
        state["lords"][survivor]["flags"][link] = expired
    saved = tmp_path / "game.json"
    saved.write_text(json.dumps(state), encoding="utf-8")
    state = load_saved_state(saved)
    assert link not in state["lords"][survivor]["flags"]
    _act(state, "command_reveal", "ghibelline")
    _finish_pending_choices(state)
    result = _act(state, "command_reveal")
    assert result["state_changes"]["lord_id"] == state["current_lord_id"] == survivor
    assert state["actions_remaining"] > 0
    check_all_invariants(state)


def _ransom_position():
    state = _to_end_campaign("A", seed=1)
    for side in ("guelph", "ghibelline"):
        _act(state, "end_grow_skip", side)
    _place(state, "pisa", "Pisa", forces={"Cavalieri": 1})
    actions._place_cylinder(state, "pisa", None)
    actions._place_service(state, "pisa", 4)
    state["lords"]["pisa"]["assets"]["Coin"] = 1
    state["lords"]["firenze"]["assets"]["Coin"] = 1
    state["lords"]["arezzo"]["assets"]["Coin"] = 1
    state["captured_knights"] = {"guelph": {"Cavalieri": 7}}
    check_all_invariants(state)
    return state


def _pay_move(state):
    return next(move for move in enumerate_legal(state)
                if move["action"] == "end_ransom" and move["args"]["pay"])


def test_ransom_offers_combined_coin_and_respects_the_receiving_mat_limit():
    state = _ransom_position()
    state["lords"]["pisa"]["assets"]["Coin"] = 16
    state["lords"]["siena"]["assets"]["Coin"] = 15
    result = actions.dispatch(state, _pay_move(state))["state_changes"]
    assert result == {"ransom_paid": 2, "recovered_total": 4, "coin_lost_to_cap": 1}
    assert all(state["lords"][lid]["assets"]["Coin"] == 0 for lid in ("firenze", "arezzo"))
    assert all(state["lords"][lid]["assets"]["Coin"] == 16 for lid in ("pisa", "siena"))
    assert not state["captured_knights"]["guelph"]


@pytest.mark.parametrize(("args", "code"), [
    ({"coin_from": "siena"}, "BAD_RANSOM_LORD"),
    ({"coin_from": "orvieto"}, "BAD_RANSOM_LORD"),
    ({"coin_payments": {"arezzo": 2}}, "INSUFFICIENT_COIN"),
    ({"coin_payments": {"arezzo": 1}}, "BAD_RANSOM_PAYMENT"),
    ({"distribute_to": ["firenze", "siena"]}, "BAD_RANSOM_LORD"),
    ({"recover": {"siena": {"Cavalieri": 4}}}, "BAD_RANSOM_LORD"),
    ({"recover": {"firenze": {"Cavalieri": 5}}}, "BAD_RANSOM_RECOVERY"),
    ({"recover": {"firenze": {"Ritter": 4}}}, "BAD_RANSOM_RECOVERY"),
])
def test_ransom_rejects_bad_payers_or_recovery_without_mutation(args, code):
    state = _ransom_position()
    before = copy.deepcopy(state)
    with pytest.raises(actions.IllegalAction) as error:
        _act(state, "end_ransom", **args)
    assert error.value.code == code
    assert state == before


def test_ransom_owner_can_choose_the_recovered_type_and_its_destination():
    state = _ransom_position()
    state["captured_knights"] = {"ghibelline": {"Cavalieri": 1, "Ritter": 1}}
    _act(state, "end_ransom")
    before = dict(state["lords"]["pisa"]["forces"])
    result = _act(state, "end_ransom", "ghibelline", coin_from="siena",
                  recover={"pisa": {"Cavalieri": 1}})
    assert result["state_changes"] == {"ransom_paid": 1, "recovered_total": 1}
    assert state["lords"]["pisa"]["forces"] == {**before, "Cavalieri": before["Cavalieri"] + 1}
    assert "ransom" in state["meta"]["end_substep_done"]


def test_captor_allocates_coin_through_owner_views_and_can_replay_after_reload():
    state = _ransom_position()
    state["meta"]["hidden_mats"] = True
    before = copy.deepcopy(state)
    view = PlayerView(state, "guelph")
    entry = next(entry for entry in view.query({"request": "actions", "category": "end_ransom"})["records"]
                 if entry["move"]["args"]["pay"])
    selection = {"action_id": entry["action_id"], "state_version": view.version,
                 "args": {"pay": True, "coin_payments": {"firenze": 1, "arezzo": 1},
                          "recover": {"firenze": {"Cavalieri": 3}, "arezzo": {"Cavalieri": 1}}}}
    # The initiating player cannot script an allocation on the enemy's behalf.
    forged = {**selection, "args": {**selection["args"], "ransom_decisions": [
        {"type": "ransom_coin_recipient", "side": "ghibelline", "choice": "pisa"}]}}
    with pytest.raises(actions.IllegalAction, match="OWNER_DECISION_REQUIRED"):
        selection_session(state, "guelph", forged)
    assert state == before

    prefix = []
    for choice in ("siena", 1, "pisa"):
        state = json.loads(json.dumps(state))
        pending = selection_session(state, "guelph", selection, decisions=prefix,
                                    decision_request={"request": "actions"})
        assert pending["status"] == "awaiting_decision" and pending["perspective"] == "ghibelline"
        assert state == before
        page = pending["response"]
        option = next(record for record in page["records"] if record["move"]["args"]["choice"] == choice)
        prefix.append({"action_id": option["action_id"], "state_version": page["state_version"]})

    result = selection_session(state, "guelph", selection, decisions=prefix)
    assert result["status"] == "accepted" and result["decisions_applied"] == 3
    for lid in ("siena", "pisa"):
        assert state["lords"][lid]["assets"]["Coin"] == before["lords"][lid]["assets"]["Coin"] + 1
    for lid, count in (("firenze", 3), ("arezzo", 1)):
        assert state["lords"][lid]["forces"]["Cavalieri"] == before["lords"][lid]["forces"]["Cavalieri"] + count
    assert "ransom_decisions" not in hide_for_side(state, "guelph")["history"][-1]["args"]
    replay = copy.deepcopy(before)
    actions.dispatch(replay, state["history"][-1])
    assert replay == state
