"""INF-4/5 regressions for capped gains and owner-selected Spoils."""
from __future__ import annotations

import copy

import pytest

from inferno import actions as A
from inferno.legal_moves import enumerate_legal
from inferno.llm.interface import DecisionView, play_with_interface
from inferno.rng import HarnessRNG
from tests.test_cross_game_escape import approach, avoid, place


def instructions(recipient, amount, *, side="ghibelline"):
    return [{"type": "spoils_recipient", "side": side, "choice": recipient},
            {"type": "spoils_amount", "side": side, "choice": amount}]


def two_winners(**assets):
    state, destination = approach(**assets)
    place(state, "astimberg", "Firenze")
    return state, destination


def storm():
    state, _ = approach()
    state["pending"] = []
    for lid in ["firenze", "lucca", "pisa"]:
        place(state, lid, "Prato")
    state["locales"]["Prato"].update(
        current_allegiance=[{"side": "ghibelline", "value": 2}],
        siege=[{"side": "guelph", "color": "purple", "count": 4}])
    state["lords"]["pisa"]["flags"]["in_stronghold"] = True
    state["lords"]["pisa"]["assets"] = {"Coin": 4, "Cart": 1, "Ship": 1}
    state["lords"]["firenze"]["forces"] = {"Cavalieri": 8, "Armigieri": 12, "Balestrieri": 6}
    state["lords"]["lucca"]["forces"] = {"Cavalieri": 4, "Armigieri": 8}
    state["meta"].update(active_player="guelph", rng_seed=1, rng_advance=0)
    state.update(current_lord_id="firenze", current_card="command_firenze", actions_remaining=3)
    return state


@pytest.mark.parametrize("podesta", [False, True])
@pytest.mark.parametrize("coin", [0, 15, 16])
def test_public_tax_caps_actual_gain_and_reports_lost_coin(podesta, coin):
    state, _ = approach()
    state["pending"] = []
    place(state, "pisa", "Siena")
    lord = place(state, "firenze", "Firenze", Coin=coin)
    lord["podesta"] = podesta
    state["meta"]["active_player"] = "guelph"
    state.update(current_lord_id="firenze", current_card="command_firenze", actions_remaining=3)
    result = A.dispatch(state, {"action": "cmd_tax", "side": "guelph", "args": {"lord_id": "firenze"}})
    entitlement = 2 if podesta else 1
    gain = min(16 - coin, entitlement)
    assert lord["assets"]["Coin"] == coin + gain
    assert result["state_changes"]["coin_gained"] == gain
    assert result["state_changes"].get("coin_lost_to_cap", 0) == entitlement - gain


def test_sack_printed_and_captured_assets_spill_to_allies_and_obey_cap():
    state = storm()
    state["lords"]["firenze"]["assets"] = {"Coin": 16, "Loot": 16, "Provender": 16}
    state["lords"]["lucca"]["assets"] = {"Coin": 15, "Loot": 15, "Provender": 15}
    result = A._apply_sack(state, "Prato", "guelph", {"removed_lords": ["pisa"]}, HarnessRNG(seed=1))
    for lid in ["firenze", "lucca"]:
        assert all(state["lords"][lid]["assets"][a] == 16 for a in ["Coin", "Loot", "Provender"])
    assert result["allocation"]["Coin"]["lost_to_cap"] == {"Coin": 1}
    captured = result["from_inside"][0]
    assert captured["allocation"]["lost_to_cap"] == {"Coin": 4}
    assert captured["transferred"].get("Ship", 0) == 0


@pytest.mark.parametrize("split", [False, True])
def test_postbattle_owner_can_concentrate_or_split_captured_coin(split):
    state, _ = two_winners(Coin=4)
    state["pending"] = []
    choices = [{"type": "post_battle_withdraw", "choice": "retreat"},
               {"type": "retreat_destination", "choice": "Prato"}]
    choices += instructions("astimberg", 3 if split else 4)
    if split:
        choices += instructions("pisa", 1)
    result = {"loser": "defender", "conceded": None, "removed_lords": []}
    A._apply_post_battle(state, result, ["pisa", "astimberg"], ["arezzo"],
                         battle_locale="Firenze", decisions=choices)
    assert state["lords"]["astimberg"]["assets"]["Coin"] == (3 if split else 4)
    assert state["lords"]["pisa"]["assets"].get("Coin", 0) == (1 if split else 0)
    assert result["spoils"][0]["allocation"]["lost_to_cap"] == {}
    assert all(d["side"] == "ghibelline" for d in result["post_battle_decisions"]
               if d["type"].startswith("spoils_"))


def test_winner_removed_by_losses_cannot_receive_spoils(monkeypatch):
    state, _ = two_winners(Coin=4)
    state["pending"] = []
    state["lords"]["pisa"]["routed_units"] = {"Armigieri": 1}
    from inferno import battle
    def lose_all(s, lid, **kwargs):
        s["lords"][lid]["forces"] = {}
        s["lords"][lid]["routed_units"] = {}
        return {"lord_id": lid, "recovered": {}, "lost": {"Armigieri": 1}, "captured": {}}
    monkeypatch.setattr(battle, "loss_roll_for_routed", lose_all)
    result = {"loser": "defender", "conceded": None, "removed_lords": []}
    A._apply_post_battle(state, result, ["pisa", "astimberg"], ["arezzo"],
                         battle_locale="Firenze", decisions=[
                             {"type": "post_battle_withdraw", "choice": "retreat"},
                             {"type": "retreat_destination", "choice": "Prato"}])
    assert state["lords"]["pisa"]["status"] != "mustered"
    assert state["lords"]["astimberg"]["assets"]["Coin"] == 4


def test_public_avoid_uses_approaching_owners_script_and_consumes_forced_amounts():
    state, destination = two_winners(Loot=4, Provender=2)
    choices = instructions("astimberg", 4) + instructions("pisa", 2)
    result = avoid(state, destination, post_battle_decisions=choices)
    assert state["lords"]["astimberg"]["assets"] == {"Loot": 4}
    assert state["lords"]["pisa"]["assets"] == {"Provender": 2}
    assert len(result["state_changes"]["spoils_decisions"]) == 4
    assert not state.get("approach_post_battle_decisions")


@pytest.mark.parametrize("choices", [
    instructions("arezzo", 4), instructions("astimberg", 5),
    instructions("astimberg", 4, side="guelph"),
])
def test_bad_spoils_script_rejects_without_losing_assets_or_pending(choices):
    state, destination = two_winners(Loot=4)
    before = copy.deepcopy(state)
    with pytest.raises(A.IllegalAction, match="BAD_DECISION"):
        avoid(state, destination, post_battle_decisions=choices)
    assert state == before


def test_public_storm_allocates_printed_and_captured_spoils_to_chosen_survivors():
    state = storm()
    choices = []
    for _ in range(3):
        choices += instructions("lucca", 2, side="guelph")
    choices += instructions("lucca", 4, side="guelph")
    choices += instructions("firenze", 1, side="guelph")
    move = next(m for m in enumerate_legal(state) if m["action"] == "cmd_storm")
    assert move["accepts_decisions"]["post_battle_decisions"] == ["spoils_recipient", "spoils_amount"]
    move["args"]["post_battle_decisions"] = choices
    result = A.dispatch(state, move)["state_changes"]["storm_result"]
    assert result["outcome"] == "sack"
    assert state["lords"]["lucca"]["assets"]["Coin"] == 6
    assert state["lords"]["firenze"]["assets"]["Cart"] == 1
    assert result["spoils"]["allocation"]["Coin"]["distributed"] == {"lucca": {"Coin": 2}}
    assert result["spoils"]["from_inside"][0]["allocation"]["distributed"] == {
        "lucca": {"Coin": 4}, "firenze": {"Cart": 1}}


def test_player_interface_routes_avoid_spoils_to_the_approaching_faction():
    state, destination = two_winners(Loot=4)
    for side in ["guelph", "ghibelline"]:
        state["decks"][side]["aow_held"] = []
    owners = []
    def callback(view):
        if isinstance(view, DecisionView):
            overview = view.overview()
            owners.append(view.side)
            wanted = "astimberg" if overview["decision"] == "spoils_recipient" else 4
            records = view.query({"request": "actions"})["records"]
            entry = next(e for e in records if e["move"]["args"]["choice"] == wanted)
        else:
            records = view.query({"request": "actions", "category": "approach_response"})["records"]
            entry = next(e for e in records if e["move"]["args"].get("destination") == destination)
        return {"action_id": entry["action_id"], "state_version": view.version}
    play_with_interface(state, callback)
    assert owners == ["ghibelline", "ghibelline"]
    assert state["lords"]["astimberg"]["assets"]["Loot"] == 4


def test_interrupted_owner_allocation_rolls_back_the_whole_action():
    state, destination = two_winners(Loot=4)
    for side in ["guelph", "ghibelline"]:
        state["decks"][side]["aow_held"] = []
    before = copy.deepcopy(state)
    def callback(view):
        if isinstance(view, DecisionView):
            return {"action_id": "bad", "state_version": view.version}
        records = view.query({"request": "actions", "category": "approach_response"})["records"]
        entry = next(e for e in records if e["move"]["args"].get("destination") == destination)
        return {"action_id": entry["action_id"], "state_version": view.version}
    with pytest.raises(A.IllegalAction, match="BAD_DECISION"):
        play_with_interface(state, callback, max_strikes=1)
    assert state == before
