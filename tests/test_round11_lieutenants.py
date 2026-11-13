"""Round 11: Lieutenant groups travel and Feed together after Sail and Sortie."""

import copy
import json

import pytest

from inferno import actions, static_data
from inferno.invariants import check_all_invariants
from inferno.legal_moves import enumerate_legal
from inferno.scenarios import load_scenario
from inferno.state import load_saved_state
from tests._helpers import _finish_pending_choices, _place
from tests.test_cross_game_escape import place
from tests.test_phase3a import _skip_capability_discard, _skip_levy


def _act(state, kind, side, **args):
    return actions.dispatch(state, {"action": kind, "side": side, "args": args})


def _plan():
    state = load_scenario("D", seed=1)
    _skip_levy(state)
    _skip_capability_discard(state)
    return state


def _finish_plan(state, side, lord=None):
    size = static_data.PLAN_SIZE_BY_SEASON[static_data.SEASON_BY_BOX[state["meta"]["turn"]]]
    first = [f"command_{lord}"] if lord else []
    for card in first + ["PASS"] * (size - len(first)):
        _act(state, "plan_add_card", side, card_id=card)
    _act(state, "plan_done", side)


def _at_pisa(*, ships, prov=0, lower_prov=0, lower_loot=0):
    state = _plan()
    place(state, "pisa", "Pisa", Ship=ships, Provender=prov)["forces"] = {"Cavalieri": 1}
    place(state, "giordano", "Pisa", Provender=lower_prov, Loot=lower_loot)["forces"] = {"Ritter": 1}
    return state


def _activate_ghibelline(state, command):
    _finish_plan(state, "ghibelline", command)
    _act(state, "command_reveal", "guelph")
    _finish_pending_choices(state)
    _act(state, "command_reveal", "ghibelline")
    assert state["current_lord_id"] == command
    return state


def _paired_sail(*, ships, prov=0, lower_prov=0, lower_loot=0):
    state = _at_pisa(ships=ships, prov=prov, lower_prov=lower_prov, lower_loot=lower_loot)
    # The Guelph player must finish Plan before the Ghibelline player can pair.
    _finish_plan(state, "guelph")
    _act(state, "plan_attach_lieutenant", "ghibelline", lieutenant="pisa", lower_lord="giordano")
    return _activate_ghibelline(state, "pisa")


def _pontedera_sail(state):
    return next(m for m in enumerate_legal(state)
                if m["action"] == "cmd_sail" and m["args"]["dest_locale"] == "Pontedera")


def test_generated_sail_moves_both_lords_and_charges_their_horses_and_cargo():
    state = _paired_sail(ships=5, lower_prov=1, lower_loot=1)
    check_all_invariants(state)
    state = json.loads(json.dumps(state))
    result = actions.dispatch(state, _pontedera_sail(state))["state_changes"]
    assert result["ships_used"] == 5
    assert result["group"] == ["pisa", "giordano"]
    assert {row["lord_id"] for row in result["fpd"]["feed"]} == {"pisa", "giordano"}
    for lord_id in result["group"]:
        assert state["lords"][lord_id]["location"] == "Pontedera"
        assert lord_id in state["locales"]["Pontedera"]["lords_present"]
        assert lord_id not in state["locales"]["Pisa"]["lords_present"]
    assert state["lords"]["giordano"]["flags"]["lower_lord_of"] == "pisa"
    check_all_invariants(state)


@pytest.mark.parametrize("already_besieged", [False, True])
def test_sail_to_enemy_port_leaves_only_sally(already_besieged, tmp_path):
    state = _at_pisa(ships=4, prov=1, lower_prov=1)
    _place(state, "arezzo", "Firenze", inside=True)
    bystanders = ("astimberg", "provenzano")
    for lid in bystanders:
        _place(state, lid, "Firenze")
    loc = state["locales"]["Firenze"]
    bypass = [{"side": "ghibelline", "lord_id": "astimberg"}]
    if already_besieged:
        loc["siege"] = [{"side": "ghibelline", "color": "gold", "count": 2}]
    else:
        loc["bypass"] = bypass
        for lid in bystanders:
            state["lords"][lid]["flags"]["bypassing"] = "Firenze"

    for card in ["PASS", "command_arezzo"] + ["PASS"] * 4:
        _act(state, "plan_add_card", "guelph", card_id=card)
    _act(state, "plan_done", "guelph")
    _act(state, "plan_attach_lieutenant", "ghibelline", lieutenant="pisa", lower_lord="giordano")
    _activate_ghibelline(state, "pisa")
    move = next(move for move in enumerate_legal(state) if move["action"] == "cmd_sail"
                and move["args"]["dest_locale"] == "Firenze")
    result = actions.dispatch(state, move)["state_changes"]
    assert result["card_finished"]
    assert result["besieged_via_sail"] is not already_besieged
    assert {row["lord_id"] for row in result["fpd"]["feed"]} == {"pisa", "giordano"}
    assert all(state["lords"][lid]["location"] == "Firenze" for lid in result["group"])
    assert loc["siege"] == [{"side": "ghibelline", "color": "gold",
                             "count": 2 if already_besieged else 1}]
    assert not loc["bypass"]
    assert all("bypassing" not in state["lords"][lid]["flags"] for lid in bystanders)

    path = tmp_path / "sail.json"
    saved = copy.deepcopy(state)
    if not already_besieged:
        # Before this fix, Sail saved the new Siege alongside the old Bypass.
        saved["locales"]["Firenze"]["bypass"] = bypass
        for lid in bystanders:
            saved["lords"][lid]["flags"]["bypassing"] = "Firenze"
    path.write_text(json.dumps(saved))
    restored = load_saved_state(path)
    assert restored == state

    _finish_pending_choices(restored)
    _act(restored, "command_reveal", "guelph")
    combat = {move["action"] for move in enumerate_legal(restored)
              if move["action"] in {"cmd_sally", "cmd_sortie"}}
    assert combat == {"cmd_sally"}
    before = copy.deepcopy(restored)
    with pytest.raises(actions.IllegalAction, match="NOT_BYPASSED"):
        _act(restored, "cmd_sortie", "guelph")
    assert restored == before
    check_all_invariants(restored)


def test_paired_sail_cannot_leave_a_horse_or_lower_lord_behind():
    state = _paired_sail(ships=1)
    assert not any(m["action"] == "cmd_sail" for m in enumerate_legal(state))
    before = copy.deepcopy(state)
    with pytest.raises(actions.IllegalAction) as rejected:
        _act(state, "cmd_sail", "ghibelline", dest_locale="Pontedera")
    assert rejected.value.code == "INSUFFICIENT_SHIPS"
    assert state == before


def test_sail_can_discard_cargo_from_either_mat_with_validated_menu_and_custom_choice():
    state = _paired_sail(ships=4, prov=1, lower_prov=1, lower_loot=1)
    move = _pontedera_sail(state)
    assert move["args"]["discard_by_lord"] == {"pisa": {"Provender": 1},
                                               "giordano": {"Provender": 1}}
    assert move["parameters"]["ship_shortfall"] == 2
    default = copy.deepcopy(state)
    result = actions.dispatch(default, move)["state_changes"]
    assert result["ships_used"] == 4
    assert result["discarded_by_lord"] == move["args"]["discard_by_lord"]

    with pytest.raises(actions.IllegalAction) as rejected:
        _act(state, "cmd_sail", "ghibelline", dest_locale="Pontedera",
             discard_by_lord={"giordano": {"Provender": 1, "Loot": 1}})
    assert rejected.value.code == "BAD_DISCARD"
    result = _act(state, "cmd_sail", "ghibelline", dest_locale="Pontedera",
                  discard_by_lord={"giordano": {"Loot": 1}})["state_changes"]
    assert result["ships_used"] == 4
    assert result["discarded_by_lord"] == {"giordano": {"Loot": 1}}
    assert state["lords"]["giordano"]["assets"]["Loot"] == 0


def test_old_sail_save_does_not_skip_the_separated_lower_lord():
    state = _at_pisa(ships=2)
    _finish_plan(state, "guelph")
    _act(state, "plan_attach_lieutenant", "ghibelline", lieutenant="pisa", lower_lord="giordano")
    state["locales"]["Pisa"]["lords_present"].remove("pisa")
    state["locales"]["Pontedera"]["lords_present"].append("pisa")
    state["lords"]["pisa"]["location"] = "Pontedera"
    state = json.loads(json.dumps(state))
    _activate_ghibelline(state, "giordano")
    assert state["lords"]["giordano"]["location"] == "Pisa"


def _bypassed_firenze(state):
    pisa = place(state, "pisa", "Firenze", Provender=1, Cart=1)
    pisa["forces"] = {"Cavalieri": 1}
    pisa["flags"]["bypassing"] = "Firenze"
    state["locales"]["Firenze"]["bypass"] = [{"side": "ghibelline"}]


def test_paired_sortie_brings_and_feeds_both_lords_even_if_the_enemy_avoids():
    state = _plan()
    for lid in ("arezzo", "orvieto"):
        lord = place(state, lid, "Firenze", Provender=1)
        lord["flags"]["in_stronghold"] = True
        lord["forces"] = {"Cavalieri": 1}
    _bypassed_firenze(state)
    _act(state, "plan_attach_lieutenant", "guelph", lieutenant="arezzo", lower_lord="orvieto")
    _finish_plan(state, "guelph", "arezzo")
    _finish_plan(state, "ghibelline")
    _act(state, "command_reveal", "guelph")
    check_all_invariants(state)

    sortie = next(m for m in enumerate_legal(state) if m["action"] == "cmd_sortie")
    result = actions.dispatch(state, sortie)["state_changes"]
    assert result["group"] == ["arezzo", "orvieto"]
    for lid in result["group"]:
        assert not state["lords"][lid]["flags"].get("in_stronghold")
        assert state["lords"][lid]["flags"]["moved_fought"]

    avoid = next(m for m in enumerate_legal(state)
                 if m.get("args", {}).get("choice") == "avoid"
                 and m["args"].get("destination") == "Figline")
    actions.dispatch(state, avoid)
    fpd = _act(state, "cmd_end_card", "guelph")["state_changes"]["fpd"]
    feed = {row["lord_id"]: row for row in fpd["feed"]}
    assert set(feed) == {"arezzo", "orvieto", "pisa"}
    assert all(row["fed"] for row in feed.values())
    check_all_invariants(state)


@pytest.mark.parametrize("take_companion", [False, True])
def test_commander_can_sortie_with_optional_lord_and_must_take_comune(take_companion):
    state = _plan()
    for lid in ("firenze", "firenze_comune", "arezzo"):
        place(state, lid, "Firenze")["flags"]["in_stronghold"] = True
    actions._place_service(state, "firenze_comune", None)
    _bypassed_firenze(state)
    _finish_plan(state, "guelph", "firenze")
    _finish_plan(state, "ghibelline")
    _act(state, "command_reveal", "guelph")
    check_all_invariants(state)

    moves = [m for m in enumerate_legal(state) if m["action"] == "cmd_sortie"]
    assert [m["args"].get("with_lords", []) for m in moves] == [[], ["arezzo"]]
    result = actions.dispatch(state, moves[1] if take_companion else moves[0])["state_changes"]
    expected = {"firenze", "firenze_comune", *({"arezzo"} if take_companion else set())}
    assert set(result["group"]) == expected
    assert all(not state["lords"][lid]["flags"].get("in_stronghold") for lid in expected)
    assert state["lords"]["arezzo"]["flags"].get("in_stronghold", False) != take_companion
    check_all_invariants(state)
