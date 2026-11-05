"""INF-6 and IF-5 regressions through Commands and the player interface."""

from __future__ import annotations

import copy
import json
from collections import Counter

import pytest

from inferno import actions as A
from inferno import card_data as cd
from inferno.invariants import assert_aow_card_conservation
from inferno.legal_moves import enumerate_legal
from inferno.llm.filter import hide_for_side
from inferno.llm.interface import (
    DecisionView,
    PlayerView,
    play_with_interface,
    selection_session,
)
from inferno.llm.menu import submit_selection
from inferno.llm.protocol import state_version
from inferno.scenarios import load_scenario
from tests.test_cross_game_escape import approach, place
from tests.test_phase3a import _build_pass_plan


def feed_state(*, units=2, prov=1, loot=1):
    state, _ = approach()
    state["pending"] = []
    state["meta"].pop("approach_attacker_side", None)
    lord = place(state, "arezzo", "Firenze", Provender=prov, Loot=loot)
    lord["forces"] = {"Armigieri": units}
    lord["flags"]["moved_fought"] = True
    state.update(
        current_card="command_arezzo", current_lord_id="arezzo", actions_remaining=1
    )
    return state


def feed_choice(lid, asset, *, side="guelph"):
    return {
        "type": "feed_asset",
        "side": side,
        "choice": {"from_lord_id": lid, "asset": asset},
    }


def finish(state, choices=None, *, action="cmd_end_card"):
    args = {"lord_id": state["current_lord_id"]}
    if choices is not None:
        args["feed_decisions"] = choices
    return A.dispatch(state, {"action": action, "side": "guelph", "args": args})


@pytest.mark.parametrize("action", ["cmd_end_card", "cmd_pass"])
def test_feed_can_spend_loot_on_explicit_or_automatic_card_end(action):
    state = feed_state()
    move = next(m for m in enumerate_legal(state) if m["action"] == action)
    assert move["accepts_decisions"]["feed_decisions"] == ["feed_asset"]
    result = finish(state, [feed_choice("arezzo", "Loot")], action=action)
    assert state["lords"]["arezzo"]["assets"] == {"Provender": 1, "Loot": 0}
    assert result["state_changes"]["fpd"]["feed"][0]["spent"] == [
        {"from_lord_id": "arezzo", "asset": "Loot"}
    ]


def test_feed_can_mix_resources_without_spending_beyond_requirement():
    state = feed_state(units=13, prov=2, loot=2)
    finish(state, [feed_choice("arezzo", a) for a in ["Loot", "Provender", "Loot"]])
    assert state["lords"]["arezzo"]["assets"] == {"Provender": 1, "Loot": 0}


def test_sharing_can_choose_donor_and_resource():
    state = feed_state(prov=0, loot=0)
    for lid in ["firenze", "lucca"]:
        place(state, lid, "Firenze", Provender=1, Loot=1)
    result = finish(state, [feed_choice("lucca", "Loot")])
    assert state["lords"]["lucca"]["assets"] == {"Provender": 1, "Loot": 0}
    assert state["lords"]["firenze"]["assets"] == {"Provender": 1, "Loot": 1}
    assert result["state_changes"]["fpd"]["feed_decisions"][0]["info"]["sharing"]


def test_each_lord_feeds_own_forces_before_sharing_surplus():
    state = feed_state(units=8, prov=0, loot=0)
    donor = place(state, "lucca", "Firenze", Provender=2)
    donor["forces"] = {"Armigieri": 8}
    donor["flags"]["moved_fought"] = True
    place(state, "firenze", "Firenze", Provender=1)
    service = state["lords"]["arezzo"]["service_box"]
    result = finish(state)["state_changes"]["fpd"]
    fed = {entry["lord_id"]: entry for entry in result["feed"]}
    assert fed["lucca"]["fed"] and not fed["arezzo"]["fed"]
    assert state["lords"]["lucca"]["assets"]["Provender"] == 0
    assert state["lords"]["firenze"]["assets"]["Provender"] == 0
    assert state["lords"]["arezzo"]["service_box"] == service - 1


def test_commander_and_comune_choose_food_across_both_own_mats():
    state = feed_state()
    state["lords"]["arezzo"]["flags"] = {}
    for lid in ["firenze", "firenze_comune"]:
        lord = place(state, lid, "Firenze", Provender=1, Loot=1)
        lord["forces"] = {"Armigieri": 4}
        lord["flags"]["moved_fought"] = True
    state.update(current_lord_id="firenze", current_card="command_firenze")
    result = finish(
        state, [feed_choice("firenze_comune", "Loot"), feed_choice("firenze", "Loot")]
    )["state_changes"]["fpd"]
    assert len(result["feed"]) == 1 and result["feed"][0]["need"] == 2
    for lid in ["firenze", "firenze_comune"]:
        assert state["lords"][lid]["assets"] == {"Provender": 1, "Loot": 0}


@pytest.mark.parametrize(
    "choices",
    [
        [feed_choice("pisa", "Provender")],
        [feed_choice("arezzo", "Coin")],
        [feed_choice("arezzo", "Loot", side="ghibelline")],
        [feed_choice("arezzo", "Loot"), feed_choice("arezzo", "Provender")],
        [{"type": "spoils_amount", "choice": 1}],
        None,
    ],
)
def test_invalid_feed_scripts_are_atomic(choices):
    state = feed_state()
    before = copy.deepcopy(state)
    with pytest.raises(A.IllegalAction, match="BAD_DECISION"):
        A.dispatch(
            state,
            {
                "action": "cmd_pass",
                "side": "guelph",
                "args": {"lord_id": "arezzo", "feed_decisions": choices},
            },
        )
    assert state == before
    # The failed action's scoped decision queue must not affect a retry.
    finish(state, [feed_choice("arezzo", "Loot")])
    assert state["lords"]["arezzo"]["assets"]["Loot"] == 0


def test_script_cannot_use_shared_food_before_own_food():
    state = feed_state()
    place(state, "lucca", "Firenze", Loot=1)
    before = copy.deepcopy(state)
    with pytest.raises(A.IllegalAction, match="BAD_DECISION"):
        finish(state, [feed_choice("lucca", "Loot")])
    assert state == before


def select(view, action):
    page = view.query({"request": "actions", "page_size": 1000})
    entry = next(r for r in page["records"] if r["move"]["action"] == action)
    return {"action_id": entry["action_id"], "state_version": view.version}


@pytest.mark.parametrize("hidden", [False, True])
def test_live_feed_decisions_use_each_factions_perspective(hidden):
    state = feed_state()
    state["meta"]["hidden_mats"] = hidden
    enemy = state["lords"]["pisa"]
    enemy["assets"] = {"Provender": 1, "Loot": 1}
    enemy["flags"]["moved_fought"] = True
    owners = []

    def callback(view):
        if not isinstance(view, DecisionView):
            return select(view, "cmd_end_card")
        overview = view.overview()
        owners.append(view.side)
        assert overview["decision"] == "feed_asset"
        page = view.query({"request": "actions"})
        entry = next(
            r for r in page["records"] if r["move"]["args"]["choice"]["asset"] == "Loot"
        )
        return {"action_id": entry["action_id"], "state_version": view.version}

    play_with_interface(state, callback)
    assert owners == ["guelph", "ghibelline"]
    for lid in ["arezzo", "pisa"]:
        assert state["lords"][lid]["assets"] == {"Provender": 1, "Loot": 0}


def test_feed_session_pauses_and_resumes_without_partial_mutation():
    state = feed_state()
    before = copy.deepcopy(state)
    selected = select(PlayerView(state), "cmd_end_card")
    waiting = selection_session(state, "guelph", selected)
    assert waiting["status"] == "awaiting_decision" and state == before
    page = selection_session(
        state, "guelph", selected, decision_request={"request": "actions"}
    )
    entry = next(
        r
        for r in page["response"]["records"]
        if r["move"]["args"]["choice"]["asset"] == "Loot"
    )
    decision = {
        "action_id": entry["action_id"],
        "state_version": page["response"]["state_version"],
    }
    result = selection_session(state, "guelph", selected, decisions=[decision])
    assert result["status"] == "accepted"
    assert state["lords"]["arezzo"]["assets"] == {"Provender": 1, "Loot": 0}


def test_failed_player_feed_reply_rolls_back_command():
    state = feed_state()
    before = copy.deepcopy(state)

    def callback(view):
        if isinstance(view, DecisionView):
            return {"action_id": "invalid", "state_version": view.version}
        return select(view, "cmd_pass")

    with pytest.raises(A.IllegalAction, match="BAD_DECISION"):
        play_with_interface(state, callback, max_strikes=1)
    assert state == before


def plan_state(seed=11, *, friars=True):
    state = load_scenario("D", seed=seed)
    state["meta"].update(
        phase="campaign", levy_step=None, campaign_step="plan", active_player="guelph"
    )
    if friars:
        state["decks"]["ghibelline"]["aow_deck"].remove("S14")
        state["active_events"] = {
            "this_campaign": [{"id": "S14", "side": "ghibelline"}]
        }
    chosen = ["command_arezzo", "command_firenze", "PASS", "PASS", "PASS", "PASS"]
    for card in chosen:
        A.dispatch(
            state,
            {"action": "plan_add_card", "side": "guelph", "args": {"card_id": card}},
        )
    return state, chosen


@pytest.mark.parametrize("seed", [1, 7, 11])
def test_friars_shuffles_completed_plan_deterministically_and_conceals_it(seed):
    state, chosen = plan_state(seed)
    assert hide_for_side(state, "guelph")["plan_stacks"]["guelph"] == chosen
    reloaded = json.loads(json.dumps(state))
    move = {"action": "plan_done", "side": "guelph"}
    result = A.dispatch(state, move)
    assert result["state_changes"]["plan_shuffled"]
    assert state["meta"]["rng_advance"] > 0
    assert Counter(state["plan_stacks"]["guelph"]) == Counter(chosen)
    assert state["plan_stacks"]["guelph"] != chosen
    A.dispatch(reloaded, move)
    assert reloaded == state
    assert_aow_card_conservation(state)
    for side in ["guelph", "ghibelline"]:
        visible = hide_for_side(state, side)
        assert visible["plan_stacks"]["guelph"] == [
            f"<facedown:{i + 1}>" for i in range(len(chosen))
        ]
        assert visible["history"][-1]["rolls"] == []
        assert hide_for_side(visible, side) == visible
        snapshot = PlayerView(state, side).query(
            {"request": "inspect", "section": "snapshot"}
        )
        assert (
            snapshot["records"][0]["value"]["plan_stacks"]["guelph"]
            == visible["plan_stacks"]["guelph"]
        )


def test_friars_permutation_and_private_shuffle_rolls_do_not_change_player_versions():
    state, _ = plan_state()
    A.dispatch(state, {"action": "plan_done", "side": "guelph"})
    other = copy.deepcopy(state)
    other["plan_stacks"]["guelph"].reverse()
    for roll in other["history"][-1]["rolls"]:
        roll["value"] = roll["value"] % 6 + 1
    for side in ["guelph", "ghibelline"]:
        assert hide_for_side(state, side) == hide_for_side(other, side)
        assert state_version(state, side) == state_version(other, side)


@pytest.mark.parametrize("transport", ["live", "selection", "session"])
def test_player_plan_done_result_does_not_disclose_shuffle_indices(transport):
    state, _ = plan_state()
    selected = select(PlayerView(state), "plan_done")
    if transport == "live":
        result = play_with_interface(
            state, lambda view: select(view, "plan_done")
        ).applied
    elif transport == "selection":
        result = submit_selection(state, "guelph", selected)
    else:
        result = selection_session(state, "guelph", selected)["latest_action"][0]
    assert result["rolls"] == []
    assert state["history"][-1]["rolls"]


def test_friars_commands_reveal_normally_while_remaining_stack_stays_concealed():
    state, _ = plan_state()
    for lid in ["arezzo", "firenze"]:
        place(state, lid, state["lords"][lid]["seats"][0])
    A.dispatch(state, {"action": "plan_done", "side": "guelph"})
    _build_pass_plan(state, "ghibelline")
    actual = list(state["plan_stacks"]["guelph"])
    advance = state["meta"]["rng_advance"]
    result = A.dispatch(state, {"action": "command_reveal", "side": "guelph"})
    assert state["meta"]["rng_advance"] == advance
    assert state["plan_stacks"]["guelph"] == actual[1:]
    if actual[0] == "PASS":
        assert result["state_changes"]["reason"] == "pass_card"
    else:
        assert result["state_changes"]["card_revealed"] == actual[0]
    for side in ["guelph", "ghibelline"]:
        assert all(
            c.startswith("<facedown:")
            for c in hide_for_side(state, side)["plan_stacks"]["guelph"]
        )


def test_legacy_completed_friars_plan_is_shuffled_once_before_reveal():
    state, chosen = plan_state()
    state["meta"].update(campaign_step="command_phase", active_player="guelph")
    for lid in ["arezzo", "firenze"]:
        place(state, lid, state["lords"][lid]["seats"][0])
    state = json.loads(json.dumps(state))
    result = A.dispatch(state, {"action": "command_reveal", "side": "guelph"})
    assert state["meta"]["rng_advance"] > 0
    assert state["meta"]["friars_plan_shuffled_turn"] == state["meta"]["turn"]
    assert state["plan_stacks"]["guelph"] != chosen[1:]
    revealed = result["state_changes"]["card_revealed"]
    assert Counter(state["plan_stacks"]["guelph"] + [revealed]) == Counter(chosen)
    assert revealed == "command_firenze"
    for side in ["guelph", "ghibelline"]:
        assert hide_for_side(state, side)["history"][-1]["rolls"] == []


def test_friars_is_drawn_as_duration_event_instead_of_held():
    state = load_scenario("D", seed=11)
    state["meta"].update(active_player="ghibelline", first_levy_aow_drawn=True)
    deck = state["decks"]["ghibelline"]
    deck["aow_discard"] = [c for c in deck["aow_deck"] if c != "S14"]
    deck["aow_deck"] = ["S14"]
    state["meta"]["aow_reshuffled_this_levy_ghibelline"] = True
    A.dispatch(state, {"action": "levy_aow_draw", "side": "ghibelline"})
    assert cd.AOW_CARDS_BY_ID["S14"]["event_kind"] == "this_campaign"
    assert any(e["id"] == "S14" for e in state["active_events"]["this_campaign"])
    assert "S14" not in deck["aow_held"]
    assert_aow_card_conservation(state)


def test_legacy_held_friars_remains_playable_and_shuffles_an_existing_plan():
    state, chosen = plan_state(friars=False)
    A.dispatch(state, {"action": "plan_done", "side": "guelph"})
    deck = state["decks"]["ghibelline"]
    deck["aow_deck"].remove("S14")
    deck["aow_held"].append("S14")
    move = next(
        m
        for m in enumerate_legal(state)
        if m["action"] == "play_event" and m["args"]["card_id"] == "S14"
    )
    A.dispatch(state, move)
    assert state["meta"]["rng_advance"] > 0
    assert Counter(state["plan_stacks"]["guelph"]) == Counter(chosen)
    assert "S14" not in deck["aow_held"] and "S14" not in deck["aow_discard"]
    assert all(
        c.startswith("<facedown:")
        for c in hide_for_side(state, "guelph")["plan_stacks"]["guelph"]
    )
    assert_aow_card_conservation(state)


def test_friars_expires_at_reset_and_ordinary_plans_keep_their_order():
    state, chosen = plan_state(friars=False)
    A.dispatch(state, {"action": "plan_done", "side": "guelph"})
    assert (
        state["plan_stacks"]["guelph"] == chosen and state["meta"]["rng_advance"] == 0
    )
    assert hide_for_side(state, "guelph")["plan_stacks"]["guelph"] == chosen
    state["active_events"] = {"this_campaign": [{"id": "S14", "side": "ghibelline"}]}
    state["decks"]["ghibelline"]["aow_deck"].remove("S14")
    state["meta"].update(campaign_step="end_campaign", active_player="guelph")
    state["meta"]["end_substep_done"] = ["grow", "ransom", "game_check", "repair", "waste"]
    A.dispatch(state, {"action": "end_reset", "side": "guelph"})
    A.dispatch(state, {"action": "end_reset", "side": "ghibelline"})
    assert not state.get("active_events")
    assert "S14" in state["decks"]["ghibelline"]["aow_discard"]
    state["meta"].update(phase="campaign", campaign_step="plan", active_player="guelph")
    state["plan_stacks"]["guelph"] = list(chosen)
    assert hide_for_side(state, "guelph")["plan_stacks"]["guelph"] == chosen
