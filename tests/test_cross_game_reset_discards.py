"""INF2-3: both players may return any owned Arts of War cards at Reset."""
import copy
import json

import pytest

from inferno import actions as A
from inferno import vassals as V
from inferno.invariants import check_all_invariants
from inferno.legal_moves import enumerate_legal, enumerate_legal_validated
from inferno.llm.filter import hide_for_side
from inferno.scenarios import load_scenario


def position():
    state = load_scenario("F", 1)
    state["meta"].update(phase="campaign", campaign_step="end_campaign",
                          active_player="guelph", turn=1,
                          end_substep_done=["grow", "ransom", "game_check", "repair", "waste"])
    for lord in state["lords"].values():
        lord["assets"] = {}
        lord["flags"] = {}
    for deck in state["decks"].values():
        deck["aow_deck"].extend(deck["aow_held"])
        deck["aow_held"] = []
    return state


def take(state, side, cid):
    deck = state["decks"][side]
    for key in ("aow_deck", "aow_discard", "aow_held"):
        deck[key] = [c for c in deck.get(key, []) if c != cid]
    state["capabilities_in_play"] = [c for c in state["capabilities_in_play"]
                                      if c["id"] != cid]
    for lord in state["lords"].values():
        lord["capabilities"] = [c for c in lord.get("capabilities", []) if c != cid]


def hold(state, side, cid):
    take(state, side, cid)
    state["decks"][side]["aow_held"].append(cid)


def capability(state, side, cid, lord_id=None):
    take(state, side, cid)
    if lord_id:
        state["lords"][lord_id]["capabilities"].append(cid)
    else:
        state["capabilities_in_play"].append({"id": cid, "side": side,
                                              "scope": "side_wide"})


def reset(state, cards=(), *, done=True, side=None):
    return A.dispatch(state, {"action": "end_reset", "side": side or state["meta"]["active_player"],
                               "args": {"reset_discard": list(cards), "done": done}})


def reject(state, action, code=None):
    before = copy.deepcopy(state)
    with pytest.raises(A.IllegalAction) as error:
        A.dispatch(state, action)
    if code:
        assert error.value.code == code
    assert state == before


@pytest.mark.parametrize("with_cards", [False, True])
def test_both_sides_elect_before_calendar_advance_and_may_keep_everything(with_cards):
    state = position()
    if with_cards:
        hold(state, "guelph", "F4")
        hold(state, "ghibelline", "S4")
    initial_decks = copy.deepcopy(state["decks"])
    first = reset(state)
    assert first["state_changes"]["reset_done"] is False
    assert state["meta"]["phase"] == "campaign" and state["meta"]["active_player"] == "ghibelline"
    assert state["calendar"]["levy_box"] == state["meta"]["turn"] == 1
    state = json.loads(json.dumps(state))
    last = reset(state)
    assert last["state_changes"]["reset_done"] is True
    assert state["meta"]["phase"] == "levy" and state["meta"]["active_player"] == "guelph"
    assert state["calendar"]["levy_box"] == state["meta"]["turn"] == 2
    assert not state["meta"].get("reset_started")
    for side in ("guelph", "ghibelline"):
        assert state["decks"][side]["aow_held"] == initial_decks[side]["aow_held"]
    assert sum(b["markers"].count("levy") for b in state["calendar"]["boxes"].values()) == 1
    check_all_invariants(state)


@pytest.mark.parametrize("side,held,personal,edge,lid", [
    ("guelph", "F4", "F12", "F22", "firenze"),
    ("ghibelline", "S4", "S6", "S21", "siena")])
def test_holds_and_both_capability_scopes_return_to_the_owning_deck(
        side, held, personal, edge, lid):
    state = position()
    hold(state, side, held)
    capability(state, side, personal, lid)
    capability(state, side, edge)
    kept = "F3" if side == "guelph" else "S3"
    hold(state, side, kept)
    if side == "ghibelline":
        reset(state)
    result = reset(state, [held, personal, edge])
    assert [c["card_id"] for c in result["state_changes"]["reset_discards"]] == [held, personal, edge]
    assert kept in state["decks"][side]["aow_held"]
    assert held not in state["decks"][side]["aow_held"]
    assert personal not in state["lords"][lid]["capabilities"]
    assert not any(c["id"] == edge for c in state["capabilities_in_play"])
    assert all(state["decks"][side]["aow_deck"].count(c) == 1 for c in (held, personal, edge))
    check_all_invariants(state)


def test_menu_reaches_every_subset_via_repeatable_single_card_choices():
    state = position()
    for cid in ("F3", "F4", "F6"):
        hold(state, "guelph", cid)
    for cid in ("F3", "F6"):
        menu = enumerate_legal_validated(state)
        assert not menu["dropped"]
        move = next(m for m in menu["moves"]
                    if m.get("args", {}).get("reset_discard") == [cid])
        assert move["args"]["done"] is False
        A.dispatch(state, move)
        assert state["meta"]["active_player"] == "guelph"
        assert state["meta"]["turn"] == 1
    reset(state)
    reset(state)
    assert state["decks"]["guelph"]["aow_held"] == ["F4"]
    check_all_invariants(state)


@pytest.mark.parametrize("survivor", [None, "regular", "routed"])
def test_tau_company_discard_cleans_troops_and_disbands_only_an_empty_lord(survivor):
    state = position()
    capability(state, "guelph", "F22")
    lord = state["lords"]["firenze"]
    lord["forces"] = {"Cavalieri": 1}
    lord["routed_units"] = {}
    tau = V.new_tau()
    tau.update(on_mat=True, ready=False)
    lord["vassals"] = [tau]
    if survivor == "regular":
        lord["forces"]["Militia"] = 1
    elif survivor == "routed":
        lord["routed_units"] = {"Men-at-Arms": 1}
    commands = copy.deepcopy(state["decks"]["ghibelline"]["command_deck"])
    result = reset(state, ["F22"])
    assert not any(v["name"] == "Altopascio" for v in lord["vassals"])
    assert not lord["forces"].get("Cavalieri")
    assert result["state_changes"]["reset_discards"][0]["altopascio_disbanded"] == ["firenze"]
    if survivor:
        assert lord["status"] == "mustered"
    else:
        assert lord["status"] == "on_calendar" and lord["calendar_box"] == 5
        assert lord["location"] is None and not lord["capabilities"]
    assert state["decks"]["ghibelline"]["command_deck"] == commands
    assert not state.get("pending_revolts")
    assert not result.get("rolls")
    check_all_invariants(state)


def test_held_f22_does_not_remove_tau_or_apply_its_event():
    state = position()
    hold(state, "guelph", "F22")
    before = copy.deepcopy(state["lords"])
    reset(state, ["F22"])
    assert state["lords"] == before
    assert state["decks"]["guelph"]["aow_deck"].count("F22") == 1


def test_disbanded_mat_does_not_return_another_selected_capability_twice():
    state = position()
    capability(state, "guelph", "F22")
    capability(state, "guelph", "F12", "firenze")
    lord = state["lords"]["firenze"]
    lord["forces"] = {"Cavalieri": 1}
    tau = V.new_tau()
    tau.update(on_mat=True, ready=False)
    lord["vassals"] = [tau]
    reset(state, ["F22", "F12"])
    assert lord["status"] == "on_calendar"
    assert state["decks"]["guelph"]["aow_deck"].count("F12") == 1
    check_all_invariants(state)


def test_tau_final_lord_loss_ends_game_before_remaining_choices_and_calendar_advance():
    state = position()
    for lid, lord in state["lords"].items():
        if lord["side"] == "guelph" and lid != "firenze":
            A._disband_at_service_limit(state, lid, 1)
    capability(state, "guelph", "F22")
    hold(state, "guelph", "F4")
    lord = state["lords"]["firenze"]
    lord["forces"] = {"Cavalieri": 1}
    tau = V.new_tau()
    tau.update(on_mat=True, ready=False)
    lord["vassals"] = [tau]
    result = reset(state, ["F22", "F4"])
    assert result["state_changes"]["game_ended"] is True
    assert state["meta"]["winner"] == "ghibelline" and state["meta"]["game_over"] is True
    assert state["meta"]["phase"] == "victory" and state["calendar"]["levy_box"] == 1
    assert state["decks"]["guelph"]["aow_held"] == ["F4"]
    assert enumerate_legal(state) == []
    public = hide_for_side(state, "ghibelline")
    assert "F4" not in str(public["history"][-1])
    assert "F22" in str(public["history"][-1])
    assert not state["meta"].get("reset_started")


def test_compulsory_cleanup_runs_once_and_precedes_optional_discards_after_reload():
    state = position()
    for cid in ("F3", "F4"):
        hold(state, "guelph", cid)
    take(state, "ghibelline", "S14")
    state["active_events"] = {"this_campaign": [{"id": "S14", "side": "ghibelline"}]}
    state["meta"]["friars_plan_shuffled_turn"] = 1
    state["war_declared_this_levy"] = ["guelph"]
    state["decks"]["guelph"]["command_deck"].append("treachery_1")
    state["lords"]["firenze"]["flags"]["has_lower_lord"] = "arezzo"
    first = reset(state, ["F4"], done=False)
    assert first["state_changes"]["reset_done"] is False
    assert not state.get("active_events") and not state.get("war_declared_this_levy")
    assert "has_lower_lord" not in state["lords"]["firenze"]["flags"]
    assert state["decks"]["ghibelline"]["aow_discard"].count("S14") == 1
    assert state["decks"]["guelph"]["treachery_set_aside"].count("treachery_1") == 1
    state = json.loads(json.dumps(state))
    reset(state)
    reset(state)
    assert state["decks"]["ghibelline"]["aow_discard"].count("S14") == 1
    assert state["decks"]["guelph"]["treachery_set_aside"].count("treachery_1") == 1
    assert state["decks"]["guelph"]["aow_held"] == ["F3"]
    assert state["calendar"]["levy_box"] == 2


def test_unrestricted_hold_can_be_played_during_reset_and_still_expires():
    state = position()
    hold(state, "ghibelline", "S14")
    reset(state)
    move = next(m for m in enumerate_legal(state)
                if m["action"] == "play_event" and m["args"]["card_id"] == "S14")
    A.dispatch(state, move)
    assert state.get("active_events")
    reset(state)
    assert not state.get("active_events")
    assert state["decks"]["ghibelline"]["aow_discard"].count("S14") == 1
    check_all_invariants(state)


@pytest.mark.parametrize("args", [
    {"reset_discard": ["S4"]}, {"reset_discard": ["F4", "F4"]},
    {"reset_discard": ["F4", "unknown"]}, {"reset_discard": "F4"},
    {"reset_discard": [1]}, {"reset_discard": None},
    {"done": False}, {"reset_discard": ["F4"], "done": "yes"},
])
def test_invalid_selections_are_atomic(args):
    state = position()
    hold(state, "guelph", "F4")
    reject(state, {"action": "end_reset", "side": "guelph", "args": args}, "BAD_DISCARD")


def test_other_side_cannot_start_reset_or_discard_guelph_cards():
    state = position()
    hold(state, "guelph", "F4")
    reject(state, {"action": "end_reset", "side": "ghibelline"}, "WRONG_TURN")
    reset(state)
    reject(state, {"action": "end_reset", "side": "ghibelline",
                   "args": {"reset_discard": ["F4"]}}, "BAD_DISCARD")


@pytest.mark.parametrize("pending", ["pending_revolts", "pending_exiles"])
def test_reset_waits_for_preceding_political_decisions(pending):
    state = position()
    state[pending] = [{"side": "guelph"}]
    reject(state, {"action": "end_reset", "side": "guelph"}, "PENDING_DECISION")


@pytest.mark.parametrize("action", ["end_grow_skip", "end_repair", "end_waste", "end_game_check"])
def test_past_substeps_cannot_be_repeated_during_reset(action):
    state = position()
    reset(state)
    reject(state, {"action": action, "side": "ghibelline"}, "PENDING_DECISION")


@pytest.mark.parametrize("phase,step,done", [
    ("levy", None, ["waste"]), ("campaign", "command_phase", ["waste"]),
    ("campaign", "end_campaign", [])])
def test_reset_cannot_skip_prior_steps_or_run_in_another_phase(phase, step, done):
    state = position()
    state["meta"].update(phase=phase, campaign_step=step, end_substep_done=done)
    reject(state, {"action": "end_reset", "side": "guelph"}, "WRONG_STEP")


def test_unplayed_card_identity_does_not_appear_in_opponents_reset_view():
    held, empty = position(), position()
    hold(held, "guelph", "F4")
    # Transfer the other copy into the equally private draw pile.
    before_held = copy.deepcopy(hide_for_side(held, "ghibelline"))
    before_empty = copy.deepcopy(hide_for_side(empty, "ghibelline"))
    assert "F4" not in str(before_held["decks"]["guelph"]["aow_held"])
    assert reset(held) == reset(empty)
    assert held["meta"]["active_player"] == empty["meta"]["active_player"] == "ghibelline"
    assert "F4" not in str(hide_for_side(held, "ghibelline")["history"][-1])
    assert before_held["meta"] == before_empty["meta"]


def test_final_game_check_still_precedes_reset_and_leaves_cards_alone():
    state = position()
    state["meta"]["end_substep_done"] = ["grow", "ransom"]
    hold(state, "guelph", "F4")
    capability(state, "guelph", "F22")
    state["calendar"]["end_box"] = 2
    result = A.dispatch(state, {"action": "end_game_check", "side": "guelph"})
    assert result["state_changes"]["game_ended"] is True
    assert state["decks"]["guelph"]["aow_held"] == ["F4"]
    assert any(c["id"] == "F22" for c in state["capabilities_in_play"])
    reject(state, {"action": "end_reset", "side": "guelph"}, "WRONG_STEP")
