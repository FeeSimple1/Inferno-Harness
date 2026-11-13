"""Stronghold arrival timing and Relief Sally decisions after an Approach."""

import json

import pytest

from inferno.actions import IllegalAction, dispatch
from inferno.invariants import check_all_invariants
from inferno.legal_moves import enumerate_legal
from inferno.llm.interface import DecisionView, play_with_interface
from inferno.state import load_saved_state
from tests._helpers import _finish_pending_choices, _place
from tests.test_cross_game_sally import give_card
from tests.test_round11_lieutenants import _act, _plan

PAIR = ["arezzo", "orvieto"]


def _before_march(*, independent=False, guelph_command="colle"):
    state = _plan()
    for lid, locale in [("arezzo", "Firenze"), ("orvieto", "Firenze"),
                        ("colle", "Prato"), ("astimberg", "Figline")]:
        _place(state, lid, locale)
    state["locales"]["Figline"]["bypass"] = [{"side": "ghibelline", "lord_id": "astimberg"}]
    state["lords"]["astimberg"]["flags"]["bypassing"] = "Figline"
    if independent:
        _place(state, "guido_guerra", "Firenze")
    _act(state, "plan_attach_lieutenant", "guelph", lieutenant=PAIR[0], lower_lord=PAIR[1])
    for side, cards in [("guelph", ["PASS", f"command_{guelph_command}"]),
                        ("ghibelline", ["command_astimberg"] * 2)]:
        for card in cards + ["PASS"] * (6 - len(cards)):
            _act(state, "plan_add_card", side, card_id=card)
        _act(state, "plan_done", side)
    _act(state, "command_reveal", "guelph")
    _finish_pending_choices(state)
    _act(state, "command_reveal", "ghibelline")
    return state


def _after_withdraw(*, last_action=False, independent=False):
    state = _before_march(independent=independent)
    if last_action:
        state["lords"]["astimberg"]["assets"]["Loot"] = 1
        state["actions_remaining"] = 2
    _act(state, "cmd_march", "ghibelline", destination="Firenze", way_type="road")
    _act(state, "approach_response", "guelph", lord_id=PAIR[0], choice="withdraw")
    if independent:
        assert not state.get("pending_besiege")
        _act(state, "approach_response", "guelph", lord_id="guido_guerra", choice="withdraw")
    check_all_invariants(state)
    return state


def _reload(state, tmp_path):
    path = tmp_path / "save.json"
    path.write_text(json.dumps(state))
    return load_saved_state(path)


def _choose_arrival(state, choice):
    move = next(m for m in enumerate_legal(state) if m["action"] == "besiege_or_bypass"
                and m["args"]["choice"] == choice)
    return dispatch(state, move)["state_changes"]


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("choice", ["besiege", "bypass"])
def test_withdrawal_requires_arrival_choice_even_on_last_action(legacy, choice, tmp_path):
    state = _after_withdraw(last_action=True)
    assert state["actions_remaining"] == 0
    assert state["pending_besiege"]["empty_on_arrival"] is False
    assert not state.get("pending_fpd")
    if legacy:
        state.pop("pending_besiege")
    state = _reload(state, tmp_path)
    before = json.dumps(state, sort_keys=True)
    assert {m["args"]["choice"] for m in enumerate_legal(state)
            if m["action"] == "besiege_or_bypass"} == {"besiege", "bypass"}
    for command in ("cmd_march", "cmd_end_card"):
        with pytest.raises(IllegalAction) as exc:
            _act(state, command, "ghibelline", destination="Figline")
        assert exc.value.code == "PENDING_DECISION"
        assert json.dumps(state, sort_keys=True) == before
    result = _choose_arrival(state, choice)
    assert result["card_finished"]
    marker = "siege" if choice == "besiege" else "bypass"
    assert state["locales"]["Firenze"][marker]
    assert state["current_lord_id"] is None
    assert "bypass_this_card" not in state


@pytest.mark.parametrize("legacy", [False, True])
def test_new_bypass_allows_local_actions_and_departure_on_later_card(legacy, tmp_path):
    state = _after_withdraw()
    assert not _choose_arrival(state, "bypass").get("card_finished")
    if legacy:
        state.pop("bypass_this_card")
    state = _reload(state, tmp_path)
    before = json.dumps(state, sort_keys=True)
    moves = enumerate_legal(state)
    assert not any(m["action"] in ("cmd_march", "cmd_depart") for m in moves)
    for command in ("cmd_march", "cmd_depart"):
        with pytest.raises(IllegalAction) as exc:
            _act(state, command, "ghibelline", destination="Figline", way_type="road")
        assert exc.value.code == "BYPASS_THIS_CARD"
        assert json.dumps(state, sort_keys=True) == before
    dispatch(state, next(m for m in moves if m["action"] == "cmd_forage"))
    _act(state, "cmd_end_card", "ghibelline")
    _finish_pending_choices(state)
    _act(state, "command_reveal", "guelph")
    _act(state, "cmd_end_card", "guelph")
    _finish_pending_choices(state)
    _act(state, "command_reveal", "ghibelline")
    _act(state, "cmd_depart", "ghibelline", destination="Figline", way_type="road")
    assert state["lords"]["astimberg"]["location"] == "Figline"
    assert not state["locales"]["Firenze"]["bypass"]
    check_all_invariants(state)


@pytest.mark.parametrize("marker", ["siege", "bypass"])
def test_arrival_at_existing_marker_can_march_on(marker):
    state = _before_march()
    for lid in PAIR:
        state["lords"][lid]["flags"]["in_stronghold"] = True
    holder = "provenzano"
    _place(state, holder, "Firenze")
    if marker == "siege":
        state["locales"]["Firenze"]["siege"] = [{"side": "ghibelline", "color": "gold", "count": 1}]
    else:
        state["locales"]["Firenze"]["bypass"] = [{"side": "ghibelline", "lord_id": holder}]
        state["lords"][holder]["flags"]["bypassing"] = "Firenze"

    result = _act(state, "cmd_march", "ghibelline", destination="Firenze", way_type="road")
    assert not result["state_changes"]["approach_triggered"]
    assert not state.get("pending_besiege")
    move = next(m for m in enumerate_legal(state) if m["action"] == "cmd_march"
                and m["args"]["destination"] == "Figline")
    dispatch(state, move)
    assert state["locales"]["Firenze"][marker]
    check_all_invariants(state)


@pytest.mark.parametrize("choice", ["besiege", "bypass"])
def test_post_battle_withdrawal_requires_arrival_choice_before_feed(choice, tmp_path):
    state = _before_march(guelph_command="arezzo")
    _act(state, "cmd_march", "ghibelline", destination="Firenze", way_type="road")
    assert state["actions_remaining"] > 0
    _act(state, "approach_response", "guelph", lord_id=PAIR[0], choice="stand")

    def choose(view):
        rows = view.query({"request": "actions"})["records"]
        if isinstance(view, DecisionView):
            options = [row["move"]["args"]["choice"] for row in rows]
            kind = view.overview()["decision"]
            election = options[0]
            if kind == "concede":
                election = "yes" if view.side == "guelph" else "no"
            elif kind == "post_battle_withdraw":
                election = "withdraw"
            row = next(row for row in rows if row["move"]["args"]["choice"] == election)
        else:
            row = next(row for row in rows if row["move"]["args"]["choice"] == "stand")
        return {"action_id": row["action_id"], "state_version": view.version}

    battle = play_with_interface(state, choose, max_strikes=1).applied["state_changes"]
    assert battle["battle_result"]["loser"] == "defender"
    assert all(state["lords"][lid]["flags"]["in_stronghold"] for lid in PAIR)
    assert not battle.get("card_finished")
    assert not state.get("pending_fpd")
    assert state["actions_remaining"] == 0

    restored = _reload(state, tmp_path)
    offered = enumerate_legal(restored)
    assert {move["args"]["choice"] for move in offered
            if move["action"] == "besiege_or_bypass"} == {"besiege", "bypass"}
    assert all(move["side"] == "ghibelline" for move in offered)
    assert {move["action"] for move in offered} <= {"besiege_or_bypass", "play_event"}
    before = json.dumps(restored, sort_keys=True)
    for command in ("cmd_march", "cmd_end_card", "command_reveal"):
        with pytest.raises(IllegalAction, match="PENDING_DECISION"):
            _act(restored, command, "ghibelline", destination="Figline")
        assert json.dumps(restored, sort_keys=True) == before
    with pytest.raises(IllegalAction, match="WRONG_TURN"):
        _act(restored, "besiege_or_bypass", "guelph", choice=choice)
    assert json.dumps(restored, sort_keys=True) == before

    finish = _choose_arrival(restored, choice)
    assert finish == _choose_arrival(state, choice)
    assert state == restored
    assert finish["card_finished"]
    assert {row["lord_id"] for row in finish["fpd"]["feed"]} == {*PAIR, "astimberg"}
    assert state["current_lord_id"] is None
    assert not state.get("pending_besiege")
    assert not state.get("bypass_this_card")
    _finish_pending_choices(state)
    _act(state, "command_reveal", "guelph")
    if choice == "besiege":
        assert state["locales"]["Firenze"]["siege"]
        assert not any(move["action"] == "cmd_march" for move in enumerate_legal(state))
        with pytest.raises(IllegalAction, match="BESIEGED"):
            _act(state, "cmd_march", "guelph", destination="Prato", way_type="track")
    else:
        assert state["locales"]["Firenze"]["bypass"]
        _act(state, "cmd_march", "guelph", destination="Prato", way_type="track")
        assert all(state["lords"][lid]["location"] == "Prato" for lid in PAIR)
    check_all_invariants(state)


def test_post_battle_revolt_can_make_arrival_friendly(tmp_path):
    state = _before_march()
    state["meta"].update(rng_seed=40, rng_advance=0)
    # Keep Guelphs on the map, away from Firenze, after its defenders are removed.
    _place(state, "colle", "Lucca")
    _place(state, "guido_guerra", "Lucca")
    state["locales"]["Cortona"]["current_allegiance"] = [{"side": "ghibelline", "value": 1}]
    give_card(state, "S18", state["decks"]["ghibelline"]["aow_held"])
    _act(state, "cmd_march", "ghibelline", destination="Firenze", way_type="road")
    _act(state, "approach_response", "guelph", lord_id=PAIR[0], choice="stand")

    def choose(decision):
        if decision["type"] == "concede":
            return "yes" if decision["side"] == "defender" else "no"
        if decision["type"] == "post_battle_withdraw":
            return "remove"
        return decision["options"][0]

    state["battle_callback"] = choose
    battle = _act(state, "approach_response", "guelph", lord_id=PAIR[1], choice="stand")
    del state["battle_callback"]
    assert set(battle["state_changes"]["battle_result"]["removed_lords"]) == set(PAIR)
    assert state.get("pending_exiles") or state.get("pending_revolts")
    with pytest.raises(IllegalAction, match="Resolve Revolt and Exiles first"):
        _act(state, "besiege_or_bypass", "ghibelline", choice="besiege")
    _finish_pending_choices(state)
    assert state["pending_besiege"]["locale"] == "Firenze"

    # Cortona's seeded Revolt flips Firenze before the attacker must encircle it.
    move = next(move for move in enumerate_legal(state) if move["action"] == "play_event"
                and move["args"] == {"card_id": "S18", "effect_args": {"mode": "revolt_roll"}})
    played = dispatch(state, move)["state_changes"]
    assert any(roll.get("revolted") == "Firenze" for roll in played["effect"]["revolt_rolls"])
    assert not played.get("card_finished")
    state = _reload(state, tmp_path)
    assert {move["action"] for move in enumerate_legal(state)} == {"cmd_resolve_exiles"}
    finish = _act(state, "cmd_resolve_exiles", "guelph", slides=[])["state_changes"]
    assert finish["card_finished"]
    assert {row["lord_id"] for row in finish["fpd"]["feed"]} == {"astimberg"}
    assert not state.get("pending_besiege")
    assert not state["locales"]["Firenze"]["siege"] and not state["locales"]["Firenze"]["bypass"]
    _finish_pending_choices(state)
    assert state["meta"]["active_player"] == "guelph"
    check_all_invariants(state)


def _before_relief(*, independent=False):
    state = _after_withdraw(independent=independent)
    _choose_arrival(state, "besiege")
    _finish_pending_choices(state)
    _act(state, "command_reveal", "guelph")
    _act(state, "cmd_march", "guelph", destination="Firenze", way_type="track")
    return state


@pytest.mark.parametrize("pair_joins", [False, True])
def test_player_elects_whole_pair_and_independent_lord_separately(pair_joins, tmp_path):
    state = _reload(_before_relief(independent=True), tmp_path)
    elections = []

    def choose(view):
        overview = view.overview()
        if overview["can_yield"]:
            return {"yield": True, "state_version": view.version}
        rows = view.query({"request": "actions"})["records"]
        if not isinstance(view, DecisionView):
            selected = next(row for row in rows if row["move"]["action"] == "approach_response"
                            and row["move"]["args"]["choice"] == "stand")
        else:
            choice = rows[0]["move"]["args"]["choice"]
            if overview["decision"] == "relief_sally_join":
                info = overview["context"]
                elections.append(info)
                join = pair_joins if info["lord_id"] in PAIR else not pair_joins
                choice = "yes" if join else "no"
            elif overview["decision"] == "concede":
                choice = "yes" if view.side == "ghibelline" else "no"
            selected = next(row for row in rows if row["move"]["args"]["choice"] == choice)
        return {"action_id": selected["action_id"], "state_version": view.version}

    result = play_with_interface(state, choose, max_strikes=1).applied["state_changes"]
    assert len(elections) == 2
    assert next(info["group"] for info in elections if info["lord_id"] in PAIR) == PAIR
    assert any(info["lord_id"] == "guido_guerra" for info in elections)
    joiners = set(PAIR) if pair_joins else {"guido_guerra"}
    candidates = {*PAIR, "guido_guerra"}
    assert set(result["battle_result"]["pre_forces"]) & candidates == joiners
    assert {row["lord_id"] for row in result["fpd"]["feed"]} & candidates == joiners
    assert state["lords"][PAIR[0]]["flags"]["has_lower_lord"] == PAIR[1]
    check_all_invariants(state)


@pytest.mark.parametrize("second_choice", ["yes", "no"])
def test_saved_script_must_give_linked_lords_equivalent_choices(second_choice, tmp_path):
    state = _reload(_before_relief(), tmp_path)
    script = [{"type": "relief_sally_join", "choice": choice} for choice in ("no", second_choice)]
    if second_choice == "no":
        result = _act(state, "approach_response", "ghibelline", lord_id="astimberg",
                      choice="stand", scripted_decisions=script)
        assert set(result["state_changes"]["battle_result"]["pre_forces"]).isdisjoint(PAIR)
    else:
        before = json.dumps(state, sort_keys=True)
        with pytest.raises(IllegalAction) as exc:
            _act(state, "approach_response", "ghibelline", lord_id="astimberg",
                 choice="stand", scripted_decisions=script)
        assert exc.value.code == "BAD_DECISION"
        assert json.dumps(state, sort_keys=True) == before
