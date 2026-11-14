"""Before-Feed Heat & Frost elections through the versioned player menu."""

from copy import deepcopy

import pytest

from inferno import actions as A
from inferno.invariants import check_all_invariants
from inferno.llm.interface import PlayerView
from inferno.llm.menu import submit_selection
from inferno.scenarios import load_scenario
from tests._helpers import _finish_pending_choices, _place
from tests.test_phase3a import _skip_capability_discard
from tests.test_round21_inferno import _actions, _apply, _next_levy, _saved, _selection

CASES = (("F20", "guelph", "astimberg", "Ritter"),
         ("S20", "ghibelline", "guido_guerra", "Cavalieri"))


def _reject(state, side, action, code, **args):
    before = deepcopy(state)
    with pytest.raises(A.IllegalAction) as exc:
        A.dispatch(state, {"action": action, "side": side, "args": args})
    assert exc.value.code == code and state == before


def _held_in_levy(card):
    state = _next_levy("D", 6 if card == "F20" else 4)
    for _ in range(2):
        _apply(state, "levy_aow_draw")
        _finish_pending_choices(state)
    return state


def _activation(card):
    state = _held_in_levy(card)
    for action in ("levy_pay_done", "levy_disband_done", "levy_muster_done", "levy_cta_skip"):
        for _ in range(2):
            _apply(state, action)
            _finish_pending_choices(state)
    _skip_capability_discard(state)
    guelph = ["command_colle"] if card == "F20" else ["PASS", "command_guido_guerra"]
    for cards in (guelph, ["command_astimberg"]):
        for cid in cards + ["PASS"] * (6 - len(cards)):
            _apply(state, "plan_add_card", card_id=cid)
        _apply(state, "plan_done")
    _apply(state, "command_reveal")
    if card == "S20":
        _finish_pending_choices(state)
        _apply(state, "command_reveal")
    return state


def _march(state, card):
    destination = "San Gimignano" if card == "F20" else "Monteriggioni"
    return _apply(state, "cmd_march", destination=destination, way_type="road")


def _waste(state, *, arezzo=None):
    owners = []
    while (rows := _actions(PlayerView(state), "cmd_heat_frost_waste")):
        options = [row["move"]["args"] for row in rows]
        choice = options[0]
        if arezzo is not None and choice["lord_id"] == "arezzo":
            choice = {"lord_id": "arezzo", "discard": arezzo}
            assert choice in options
        owners.append(rows[0]["move"]["side"])
        _apply(state, "cmd_heat_frost_waste", **choice)
    return owners


def _pass_before_feed(state, *, until=None):
    while PlayerView(state).side != until and _actions(PlayerView(state), "cmd_before_feed_pass"):
        _apply(state, "cmd_before_feed_pass")


@pytest.mark.parametrize("card,side,target,unit", CASES)
def test_native_heat_frost_timing_waste_and_loss_replay(tmp_path, card, side, target, unit):
    levy = _held_in_levy(card)
    if side == "ghibelline":
        _apply(levy, "levy_pay_done")
    assert card in levy["decks"][side]["aow_held"]
    assert not any(row["move"]["args"]["card_id"] == card
                   for row in _actions(PlayerView(levy), "play_event"))
    _reject(levy, side, "play_event", "NO_PLAY_WINDOW", card_id=card)

    state = _activation(card)
    _reject(state, side, "play_event", "NO_PLAY_WINDOW", card_id=card)
    _march(state, card)
    _reject(state, side, "play_event", "NO_PLAY_WINDOW", card_id=card)
    before_feed = deepcopy(state["lords"])
    assert _apply(state, "cmd_end_card")["state_changes"]["before_feed_pending"]
    _pass_before_feed(state, until=side)
    assert state["lords"] == before_feed and PlayerView(state).side == side
    state = _saved(state, tmp_path)
    _apply(state, "play_event", card_id=card)
    assert PlayerView(state).side == "guelph"
    first = _actions(PlayerView(state), "cmd_heat_frost_waste")
    assert {row["move"]["args"]["discard"]["asset"] for row in first} >= {"Coin", "Cart", "Provender"}
    assert all(row["move"]["args"]["lord_id"] == "arezzo" for row in first)
    _reject(state, "ghibelline", "cmd_heat_frost_waste", "WRONG_BEFORE_FEED_SIDE",
            lord_id="arezzo", discard={"asset": "Coin"})
    _reject(state, "guelph", "cmd_heat_frost_waste", "BAD_DISCARD",
            lord_id="arezzo", discard={"asset": "Ship"})
    restored = _saved(state, tmp_path)
    for candidate in (state, restored):
        owners = _waste(candidate, arezzo={"asset": "Coin"})
        assert owners == sorted(owners, key=lambda owner: owner != "guelph")
        assert card in candidate["decks"][side]["aow_held"]
        assert candidate["lords"]["arezzo"]["assets"] == {"Coin": 0, "Cart": 1, "Provender": 2}
    assert restored == state and PlayerView(state).side == side
    choices = [row["move"]["args"] for row in _actions(PlayerView(state), "cmd_heat_frost_loss")]
    if card == "F20":
        assert {"astimberg", "giordano", "provenzano"} <= {c["lord_id"] for c in choices}
        target = "giordano"
    else:
        assert {c["unit"] for c in choices} >= {"Armigieri", "Cavalieri", "Militia"}
        target, unit = "guido_guerra", "Militia"
    _reject(state, side, "cmd_heat_frost_loss", "BAD_HEAT_FROST_CHOICE", lord_id=target, unit="Ship")
    before = state["lords"][target]["forces"][unit]
    captured = deepcopy(state.get("captured_knights"))
    restored = _saved(state, tmp_path)
    for candidate in (state, restored):
        receipt = _apply(candidate, "cmd_heat_frost_loss", lord_id=target, unit=unit)
        assert receipt["state_changes"]["played"] == card
        assert candidate["lords"][target]["forces"].get(unit, 0) == before - 1
        assert candidate.get("captured_knights") == captured
        assert card not in candidate["decks"][side]["aow_held"]
        assert candidate["decks"][side]["aow_discard"].count(card) == 1
        _pass_before_feed(candidate)
        fpd = _apply(candidate, "cmd_resume_feed")["state_changes"]["fpd"]
        assert fpd["feed"] and not candidate.get("pending_before_feed")
        check_all_invariants(candidate)
        _finish_pending_choices(candidate)
        _reject(candidate, candidate["meta"]["active_player"], "cmd_resume_feed", "NO_FEED_WINDOW")
    assert restored == state
    replay = load_scenario("D", state["meta"]["rng_seed"])
    for entry in state["history"]:
        A.dispatch(replay, entry)
    assert replay == state


@pytest.mark.parametrize("card,side,target,unit", CASES)
@pytest.mark.parametrize("foot_survives", [True, False])
def test_heat_frost_disbands_only_after_the_last_force(tmp_path, card, side, target, unit, foot_survives):
    state = _activation(card)
    lord = state["lords"][target]
    lord["forces"] = {unit: 1, **({"Militia": 1} if foot_survives else {})}
    _march(state, card)
    _apply(state, "cmd_end_card")
    _pass_before_feed(state, until=side)
    _apply(state, "play_event", card_id=card)
    _waste(state)
    state = _saved(state, tmp_path)
    lord = state["lords"][target]
    locale, service = lord["location"], lord["service_box"]
    result = _apply(state, "cmd_heat_frost_loss", lord_id=target, unit=unit)
    assert result["state_changes"]["summer_loss"]["disbanded"] is not foot_survives
    if foot_survives:
        assert lord["status"] == "mustered" and lord["forces"] == {"Militia": 1}
        assert lord["location"] == locale and lord["service_box"] == service
    else:
        calendar_box = 11 + lord["ratings"]["S"]
        assert lord["status"] == "on_calendar" and lord["calendar_box"] == calendar_box
        assert lord["location"] is None and lord["service_box"] is None
        assert not any(lord[key] for key in ("assets", "capabilities", "vassals", "forces", "flags"))
        assert target not in state["locales"][locale]["lords_present"]
        assert target in state["calendar"]["boxes"][str(calendar_box)]["cylinders"]
    _pass_before_feed(state)
    _apply(state, "cmd_resume_feed")
    _finish_pending_choices(state)
    _apply(state, "command_reveal")
    assert (state.get("current_lord_id") == target) is foot_survives
    check_all_invariants(state)


def _give_card(state, side, card, zone):
    for pile in ("aow_deck", "aow_discard", "aow_held"):
        if card in state["decks"][side][pile]:
            state["decks"][side][pile].remove(card)
            break
    zone.append(card)


def _fixture_before_feed(card="F20", season_box=10, moved=True):
    state = load_scenario("D", seed=2)
    state["meta"].update(phase="campaign", campaign_step="command_phase", turn=season_box)
    state["current_card"] = "command_colle"
    state["current_lord_id"] = "colle"
    state["actions_remaining"] = 1
    state["lords"]["colle"]["flags"]["moved_fought"] = moved
    side = "guelph" if card == "F20" else "ghibelline"
    _give_card(state, side, card, state["decks"][side]["aow_held"])
    return state


@pytest.mark.parametrize("turn,moved", [(10, False), (11, True)])
def test_heat_frost_requires_moved_fought_in_summer_or_winter(turn, moved):
    state = _fixture_before_feed(season_box=turn, moved=moved)
    _apply(state, "cmd_end_card")
    assert not state.get("pending_before_feed")


def test_before_feed_pass_does_not_expose_whether_the_enemy_holds_heat_frost():
    has_card = _fixture_before_feed(card="S20")
    no_card = deepcopy(has_card)
    _give_card(no_card, "ghibelline", "S20", no_card["decks"]["ghibelline"]["aow_deck"])
    _give_card(no_card, "ghibelline", "S19", no_card["decks"]["ghibelline"]["aow_held"])
    for state in (has_card, no_card):
        _apply(state, "cmd_end_card")
        _apply(state, "cmd_before_feed_pass")
        assert PlayerView(state).side == "ghibelline"
        assert not _actions(PlayerView(state, "guelph"), "play_event")
    assert PlayerView(has_card, "guelph").version == PlayerView(no_card, "guelph").version
    assert _actions(PlayerView(has_card), "play_event")
    assert not _actions(PlayerView(no_card), "play_event")


def test_both_winter_offers_waste_cycles_and_automatic_card_end(tmp_path):
    state = _fixture_before_feed(season_box=12)
    _give_card(state, "ghibelline", "S20", state["decks"]["ghibelline"]["aow_held"])
    for lord in state["lords"].values():
        lord["assets"] = {}
    colle = state["lords"]["colle"]
    colle["assets"] = {"Coin": 2, "Provender": 2}
    _give_card(state, "guelph", "F3", colle["capabilities"])
    assert _apply(state, "cmd_pass")["state_changes"]["before_feed_pending"]
    assert PlayerView(state).side == "guelph"
    _apply(state, "cmd_before_feed_pass")
    assert PlayerView(state).side == "ghibelline"
    _apply(state, "play_event", card_id="S20")
    assert PlayerView(state).side == "guelph"
    _apply(state, "cmd_heat_frost_waste", lord_id="colle", discard={"capability": "F3"})
    state = _saved(state, tmp_path)
    _apply(state, "cmd_heat_frost_waste", lord_id="colle", discard={"asset": "Coin"})
    assert state["lords"]["colle"]["assets"] == {"Coin": 1, "Provender": 2}
    assert "F3" in state["decks"]["guelph"]["aow_deck"]
    assert not _actions(PlayerView(state), "cmd_heat_frost_loss")
    assert state["decks"]["ghibelline"]["aow_discard"].count("S20") == 1
    assert "F20" in state["decks"]["guelph"]["aow_held"]
    view = PlayerView(state)
    before = deepcopy(state)
    with pytest.raises(A.IllegalAction, match="OWNER_DECISION_REQUIRED"):
        submit_selection(state, view.side, {
            **_selection(view, "cmd_resume_feed"), "args": {"feed_decisions": []},
        })
    assert state == before
    _apply(state, "cmd_resume_feed")
    assert state["lords"]["colle"]["assets"]["Provender"] == 1


def test_heat_frost_hidden_mat_view_and_immediate_victory():
    state = _fixture_before_feed(card="S20")
    state["meta"]["hidden_mats"] = True
    for lid, lord in state["lords"].items():
        if lord["side"] == "guelph" and lid != "guido_guerra" and lord["status"] == "mustered":
            A._disband_at_service_limit(state, lid, state["calendar"]["levy_box"])
    _place(state, "guido_guerra", "Arezzo", forces={"Militia": 1})
    state["lords"]["guido_guerra"]["flags"]["moved_fought"] = True
    state.update(current_lord_id="guido_guerra", current_card="command_guido_guerra")
    state["lords"]["guido_guerra"]["assets"] = {"Coin": 2}
    _apply(state, "cmd_end_card")
    _apply(state, "cmd_before_feed_pass")
    inspect = PlayerView(state, "guelph").query({"request": "inspect", "section": "pending",
                                               "keys": ["pending_before_feed"]})
    assert "card_id" not in inspect["records"][0]["value"]
    _apply(state, "play_event", card_id="S20")
    assert not _actions(PlayerView(state, "ghibelline"), "cmd_heat_frost_waste")
    _waste(state)
    view = PlayerView(state)
    rows = _actions(view, "cmd_heat_frost_loss")
    assert len(rows) == 1 and rows[0]["parameterized"]
    assert rows[0]["move"]["args"]["unit"] == "<unit type>"
    result = submit_selection(state, view.side, {"state_version": view.version,
                              "action_id": rows[0]["action_id"],
                              "args": {"lord_id": "guido_guerra", "unit": "Militia"}})
    assert result["state_changes"]["summer_loss"]["disbanded"]
    assert state["meta"]["game_over"] and state["meta"]["winner"] == "ghibelline"
    assert not state.get("pending_before_feed") and not state.get("pending_fpd")
    assert not _actions(PlayerView(state), "cmd_resume_feed")
    check_all_invariants(state)
