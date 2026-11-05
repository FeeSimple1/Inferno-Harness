"""INF2-1/2/4: temporary Disband, phase timing and Calendar overflow."""

import copy
import json

import pytest

from inferno import actions as A
from inferno import static_data as sd
from inferno import vassals as V
from inferno.legal_moves import enumerate_legal
from inferno.scenarios import _init_vassals_for, load_scenario


def position(box=7, phase="levy", advanced=True):
    state = load_scenario("F", 1, advanced_vassal_service=advanced)
    for b in state["calendar"]["boxes"].values():
        b["markers"] = [x for x in b["markers"] if x != "levy"]
    state["calendar"]["levy_box"] = state["meta"]["turn"] = box
    A._box(state, box)["markers"].append("levy")
    state["meta"].update(phase=phase, levy_step="3.3", active_player="guelph")
    if phase == "campaign":
        state["meta"]["campaign_step"] = "command_phase"
        state.update(current_lord_id="firenze", current_card="command_firenze",
                     actions_remaining=1)
    for lid, lord in state["lords"].items():
        lord["assets"] = {}
        lord["flags"] = {}
        if lord["status"] == "mustered":
            A._place_service(state, lid, box + 1)
    return state


def place(state, lid, locale):
    lord = state["lords"][lid]
    for loc in state["locales"].values():
        loc["lords_present"] = [x for x in loc["lords_present"] if x != lid]
    A._place_cylinder(state, lid, None)
    lord.update(status="mustered", location=locale, flags={}, assets={},
                forces=copy.deepcopy(sd.LORDS[lord["name"]]["forces"]), routed_units={})
    lord["vassals"] = _init_vassals_for(sd.LORDS[lord["name"]])
    state["locales"][locale]["lords_present"].append(lid)
    A._place_service(state, lid, state["calendar"]["levy_box"] + 1)
    return lord


def end_disband(state):
    if state["meta"]["phase"] == "levy":
        return A.dispatch(state, {"action": "levy_disband", "side": "guelph"})
    return A.dispatch(state, {"action": "cmd_end_card", "side": "guelph",
                              "args": {"lord_id": "firenze"}})


@pytest.mark.parametrize("phase", ["levy", "campaign"])
@pytest.mark.parametrize("survivor", [None, "regular", "routed"])
def test_final_vassal_force_uses_temporary_disband_without_political_penalty(phase, survivor):
    state = position(phase=phase)
    lord = place(state, "guido_guerra", "Poppi")
    lord["forces"] = {"Militia": 1}
    lord["vassals"][0].update(on_mat=True, ready=False, service_box=7)
    if survivor == "regular":
        lord["forces"]["Cavalieri"] = 1
    elif survivor == "routed":
        lord["routed_units"] = {"Men-at-Arms": 1}
    commands = copy.deepcopy(state["decks"]["ghibelline"]["command_deck"])
    random_before = state["meta"].get("rng_advance", 0)
    result = end_disband(state)
    assert state["decks"]["ghibelline"]["command_deck"] == commands
    assert state["meta"].get("rng_advance", 0) == random_before
    assert not result.get("rolls") and not state.get("pending_revolts")
    if survivor:
        assert lord["status"] == "mustered" and lord["location"] == "Poppi"
        assert not lord["forces"].get("Militia")
    else:
        assert lord["status"] == "on_calendar"
        assert lord["calendar_box"] == 11 + int(phase == "campaign")
        assert lord["location"] is None and not lord["assets"] and not lord["vassals"]
        assert "guido_guerra" not in state["locales"]["Poppi"]["lords_present"]
        assert lord["service_box"] is None
        loaded = json.loads(json.dumps(state))
        assert loaded["lords"]["guido_guerra"] == lord
        assert loaded["calendar"] == state["calendar"]


def test_discarding_last_tau_force_uses_same_temporary_campaign_disband():
    state = position(phase="campaign", advanced=False)
    state["meta"]["campaign_step"] = "capability_discard"
    lord = state["lords"]["firenze"]
    lord["forces"] = {"Cavalieri": 1}
    tau = V.new_tau()
    tau.update(on_mat=True, ready=False)
    lord["vassals"] = [tau]
    for cid in ("F22", "F1", "F21"):
        state["decks"]["guelph"]["aow_deck"] = [
            c for c in state["decks"]["guelph"]["aow_deck"] if c != cid]
        state["capabilities_in_play"].append({"id": cid, "side": "guelph",
                                              "scope": "side_wide"})
    commands = state["decks"]["ghibelline"]["command_deck"][:]
    result = A.dispatch(state, {"action": "campaign_discard_capability", "side": "guelph",
                                "args": {"card_id": "F22"}})
    assert lord["status"] == "on_calendar" and lord["calendar_box"] == 11
    assert result["state_changes"]["empty_lords_disbanded"] == ["firenze"]
    assert state["decks"]["ghibelline"]["command_deck"] == commands
    assert not result.get("rolls") and not state.get("pending_revolts")


@pytest.mark.parametrize("phase", ["levy", "campaign"])
@pytest.mark.parametrize("box", [7, 13, 14])
def test_at_limit_disband_counts_from_proper_phase_and_preserves_off_right(phase, box):
    state = position(box, phase, advanced=False)
    A._place_service(state, "firenze", box)
    end_disband(state)
    lord = state["lords"]["firenze"]
    target = box + 3 + int(phase == "campaign")
    assert lord["status"] == "on_calendar"
    assert lord["calendar_box"] == (target if target <= 16 else None)
    assert ("firenze" in state["calendar"]["off_right"]) == (target > 16)
    assert "17" not in state["calendar"]["boxes"]


def test_beyond_service_podesta_returns_off_right_and_still_has_political_consequences():
    state = position(14, advanced=False)
    A._place_service(state, "firenze", 13)
    result = end_disband(state)
    lord = state["lords"]["firenze"]
    assert lord["status"] == "on_calendar" and lord["calendar_box"] is None
    assert state["calendar"]["off_right"].count("firenze") == 1
    assert result["state_changes"]["treachery_added"]


@pytest.mark.parametrize("mode", ["ordinary", "commander", "allies"])
def test_late_muster_service_stays_off_right_then_shifts_back_one_box(mode):
    state = position(14, advanced=False)
    state["meta"]["active_player"] = "ghibelline"
    target = "siena" if mode == "commander" else "astimberg"
    if mode == "ordinary":
        state["meta"]["levy_step"] = "3.4"
        action = {"action": "levy_muster_lord", "args": {"muster_lord_id": "siena",
                  "target_lord_id": target, "target_seat": "Siena"}}
    else:
        state["meta"].update(levy_step="3.5", cta_substep="commander_arms" if mode ==
                             "commander" else "allies")
        if mode == "commander":
            A._disband_at_service_limit(state, target, 14)
            action = {"action": "cta_commander_arms", "args": {"mode": "muster_only"}}
        else:
            action = {"action": "cta_allies", "args": {"mode": "auto_muster",
                      "target_lord_id": target, "target_seat": "Siena"}}
    result = A.dispatch(state, {**action, "side": "ghibelline"})
    assert mode != "ordinary" or result["state_changes"]["success"]
    lord = state["lords"][target]
    assert lord["status"] == "mustered" and lord["service_box"] is None
    assert state["calendar"]["off_right_service"].count(target) == 1
    assert not any(target in b["services"] for b in state["calendar"]["boxes"].values())
    state = json.loads(json.dumps(state))
    V.shift_service(state, target, -1)
    assert state["lords"][target]["service_box"] == 16
    assert target not in state["calendar"]["off_right_service"]


@pytest.mark.parametrize("allies", [False, True])
def test_off_right_cylinder_is_not_ready_in_handler_or_menu(allies):
    state = position(14, advanced=False)
    state["meta"]["active_player"] = "ghibelline"
    A._place_cylinder(state, "astimberg", 17)
    if allies:
        state["meta"].update(levy_step="3.5", cta_substep="allies")
        action = {"action": "cta_allies", "args": {"mode": "auto_muster",
                   "target_lord_id": "astimberg", "target_seat": "Siena"}}
    else:
        state["meta"]["levy_step"] = "3.4"
        action = {"action": "levy_muster_lord", "args": {"muster_lord_id": "siena",
                  "target_lord_id": "astimberg", "target_seat": "Siena"}}
    assert not any(m.get("args", {}).get("target_lord_id") == "astimberg"
                   for m in enumerate_legal(state))
    before = copy.deepcopy(state)
    with pytest.raises(A.IllegalAction, match="TARGET_NOT_READY"):
        A.dispatch(state, {**action, "side": "ghibelline"})
    assert state == before
