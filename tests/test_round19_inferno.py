"""Sortie and Sally legality and Retreat into Ruins through public actions."""

from copy import deepcopy
import json

import pytest

from inferno.actions import IllegalAction, dispatch
from inferno.cli import main as cli_main
from inferno.invariants import check_all_invariants
from inferno.legal_moves import enumerate_legal
from inferno.llm.interface import DecisionView, play_with_interface
from tests._helpers import _finish_pending_choices, _place
from tests.test_round11_lieutenants import _act
from tests.test_round16_approach import PAIR, _before_march, _choose_arrival, _reload


def _before_inside_command(marker, *, independent=False):
    state = _before_march(independent=independent, guelph_command="arezzo")
    _act(state, "cmd_march", "ghibelline", destination="Firenze", way_type="road")
    _act(state, "approach_response", "guelph", lord_id="arezzo", choice="withdraw")
    if independent:
        _act(state, "approach_response", "guelph", lord_id="guido_guerra", choice="withdraw")
    _choose_arrival(state, marker)
    if marker == "bypass":
        _act(state, "cmd_end_card", "ghibelline")
    _finish_pending_choices(state)
    _act(state, "command_reveal", "guelph")
    check_all_invariants(state)
    return state


def _fight(state, action, conceding_side, *, fate=None, destination=None):
    elections = []

    def choose(view):
        rows = view.query({"request": "actions", "page_size": 100})["records"]
        if isinstance(view, DecisionView):
            overview = view.overview()
            kind = overview["decision"]
            options = [row["move"]["args"]["choice"] for row in rows]
            choice = options[0]
            if kind == "concede":
                choice = "yes" if view.side == conceding_side else "no"
            elif kind in ("post_battle_withdraw", "post_battle_fate") and fate:
                choice = fate
            elif kind == "retreat_destination" and destination:
                choice = destination
            elections.append((kind, view.side, options, overview["context"]))
            selected = next(row for row in rows if row["move"]["args"]["choice"] == choice)
        else:
            selected = next(
                row for row in rows if row["move"]["action"] == action
                and (action != "approach_response" or row["move"]["args"]["choice"] == "stand")
            )
        return {"action_id": selected["action_id"], "state_version": view.version}

    result = play_with_interface(state, choose, max_strikes=1).applied["state_changes"]
    check_all_invariants(state)
    return result, elections


@pytest.mark.parametrize("fate", ["withdraw", "retreat", "remove"])
def test_losing_sortie_offers_linked_lords_their_fates(fate, tmp_path):
    state = _before_inside_command("bypass", independent=True)
    sortie = next(move for move in enumerate_legal(state)
                  if move["action"] == "cmd_sortie" and not move["args"].get("with_lords"))
    assert dispatch(state, sortie)["state_changes"]["group"] == PAIR
    assert any(move["args"].get("choice") == "avoid" for move in enumerate_legal(state))
    replay = _reload(state, tmp_path)

    choices = {"fate": fate, "destination": "Figline"}
    result, elections = _fight(state, "approach_response", "guelph", **choices)
    assert _fight(replay, "approach_response", "guelph", **choices) == (result, elections)
    assert replay == state
    assert not any(kind == "relief_sally_join" for kind, *_ in elections)

    battle = result["battle_result"]
    assert battle["loser"] == battle["conceded"] == "attacker"
    assert battle["routed_out_lords"] == []
    assert set(battle["pre_forces"]) == {*PAIR, "astimberg"}
    assert state["lords"]["guido_guerra"]["flags"]["in_stronghold"]
    fates = [(owner, options, context["lord_id"]) for kind, owner, options, context in elections
             if kind == "post_battle_withdraw"]
    assert fates[0] == ("guelph", ["retreat", "withdraw", "remove"], PAIR[0])
    partner_options = ["retreat", "withdraw", "remove"] if fate == "remove" else [fate, "remove"]
    assert fates[1:] == [("guelph", partner_options, PAIR[1])]

    if fate == "remove":
        assert set(battle["removed_lords"]) == set(PAIR)
        assert {row["loser_id"] for row in battle["spoils"]} == set(PAIR)
        assert all(state["lords"][lid]["location"] is None for lid in PAIR)
        return

    assert battle["removed_lords"] == []
    assert not battle.get("spoils")
    assert state["lords"][PAIR[0]]["flags"]["has_lower_lord"] == PAIR[1]
    for lid in PAIR:
        lord = state["lords"][lid]
        assert lord["status"] == "mustered"
        assert lord["assets"]["Cart"] == 2
        if fate == "withdraw":
            assert lord["location"] == "Firenze"
            assert lord["flags"]["in_stronghold"]
            assert lord["service_box"] == 11
        else:
            assert lord["location"] == "Figline"
            assert not lord["flags"].get("in_stronghold")
            assert lord["service_box"] < 11


def test_sally_rejects_bypass_in_menu_dispatch_and_cli(tmp_path, capsys):
    state = _before_inside_command("bypass")
    assert not any(move["action"] == "cmd_sally" for move in enumerate_legal(state))
    action = {"action": "cmd_sally", "side": "guelph", "args": {"lord_id": "arezzo"}}
    before = deepcopy(state)
    with pytest.raises(IllegalAction) as rejected:
        dispatch(state, action)
    assert rejected.value.code == "NOT_BESIEGED"
    assert state == before

    source = tmp_path / "bypass.json"
    output = tmp_path / "after.json"
    saved = json.dumps(state)
    source.write_text(saved)
    assert cli_main(["do", str(source), json.dumps(action), "--out", str(output)]) == 1
    assert "IllegalAction[NOT_BESIEGED]" in capsys.readouterr().out
    assert source.read_text() == saved
    assert not output.exists()


def test_sally_under_siege_returns_survivors_inside_and_reduces_siege():
    state = _before_inside_command("besiege")
    city = state["locales"]["Firenze"]
    city["siege"][0]["count"] = 2
    result, elections = _fight(state, "cmd_sally", "guelph")
    battle = result["sally_result"]
    assert battle["loser"] == battle["conceded"] == "attacker"
    assert battle["siege_count"] == 2
    assert state["locales"]["Firenze"]["siege"] == [
        {"side": "ghibelline", "color": "gold", "count": 1},
    ]
    assert battle["removed_lords"] == []
    assert all(state["lords"][lid]["flags"]["in_stronghold"] for lid in PAIR)
    assert not any(kind.startswith("post_battle_") for kind, *_ in elections)


@pytest.mark.parametrize("origin", ["ruins", "intact_enemy", "occupied_ruins"])
def test_marching_attacker_retreat_checks_origin_after_ruin(origin, tmp_path):
    state = _before_march()
    figline = state["locales"]["Figline"]
    if origin != "intact_enemy":
        # Stage a previous Sack at the printed Guelph Castle.
        figline["bypass"] = []
        figline["ruins"] = "gold"
        state["lords"]["astimberg"]["flags"].pop("bypassing")
        state["vp"]["ghibelline"] += 0.5
    _act(state, "cmd_march", "ghibelline", destination="Firenze", way_type="road")
    _act(state, "approach_response", "guelph", lord_id="arezzo", choice="stand")
    if origin == "occupied_ruins":
        _place(state, "colle", "Figline")
    state = _reload(state, tmp_path)

    result, elections = _fight(state, "approach_response", "ghibelline")
    battle = result["battle_result"]
    assert battle["loser"] == battle["conceded"] == "attacker"
    assert battle["routed_out_lords"] == []
    assert not any(kind.startswith("post_battle_") for kind, *_ in elections)
    astimberg = state["lords"]["astimberg"]
    if origin == "ruins":
        assert battle["removed_lords"] == []
        assert astimberg["status"] == "mustered"
        assert astimberg["location"] == "Figline"
        assert astimberg["service_box"] == 8
        assert astimberg["forces"]["Ritter"] == 2
        assert not astimberg["flags"].get("in_stronghold")
    else:
        assert battle["removed_lords"] == ["astimberg"]
        assert astimberg["status"] == "removed"
        assert astimberg["location"] is None


@pytest.mark.parametrize("destination", ["Altopascio", "Vicopisano"])
def test_linked_defenders_retreat_to_friendly_or_enemy_ruins(destination):
    state = _before_march()
    state["locales"]["Figline"]["bypass"] = []
    state["lords"]["astimberg"]["flags"].pop("bypassing")
    _place(state, "astimberg", "Vecliano")
    for lid in PAIR:
        _place(state, lid, "Lucca")
    for name in ("Altopascio", "Vicopisano", "Vecliano", "Lucca"):
        loc = state["locales"][name]
        ruined_by = "guelph" if loc["allegiance"] == "ghibelline" else "ghibelline"
        loc["ruins"] = "purple" if ruined_by == "guelph" else "gold"
        state["vp"][ruined_by] += 0.5

    _act(state, "cmd_march", "ghibelline", destination="Lucca", way_type="road")
    _act(state, "approach_response", "guelph", lord_id="arezzo", choice="stand")
    result, elections = _fight(
        state, "approach_response", "guelph", fate="retreat", destination=destination,
    )

    battle = result["battle_result"]
    assert battle["loser"] == battle["conceded"] == "defender"
    assert battle["removed_lords"] == []
    assert not any(kind == "post_battle_withdraw" for kind, *_ in elections)
    routes = [(owner, options, context["lord_ids"]) for kind, owner, options, context in elections
              if kind == "retreat_destination"]
    # Vecliano is open Ruins, but the March from there used its only Approach Way.
    assert routes == [("guelph", ["Altopascio", "San Miniato", "Vicopisano"], PAIR)]
    assert all(state["lords"][lid]["location"] == destination for lid in PAIR)
    assert state["lords"][PAIR[0]]["flags"]["has_lower_lord"] == PAIR[1]
