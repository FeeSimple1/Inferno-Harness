"""INF3-01 to INF3-04: Sally uses Battle aftermath and its own Siegeworks."""

from __future__ import annotations

from copy import deepcopy

import pytest

from inferno import actions
from inferno.invariants import check_all_invariants
from inferno.legal_moves import enumerate_legal
from tests.test_cross_game_escape import place
from tests.test_phase3c import _to_command_with


def position(seed=1, *, sally_knights=2, besieger_knights=2, siege=1):
    state = _to_command_with("A", seed=1, lord_id="siena", lord_location_override="Siena")
    for lid, count in [("siena", sally_knights), ("firenze", besieger_knights)]:
        lord = place(state, lid, "Siena", Coin=4, Loot=2, Provender=8, Cart=1)
        lord["forces"] = {"Cavalieri": count}
        lord["capabilities"] = []
    state["lords"]["siena"]["flags"]["in_stronghold"] = True
    state["locales"]["Siena"]["siege"] = [{"side": "guelph", "color": "purple", "count": siege}]
    state["meta"].update(rng_seed=seed, rng_advance=0)
    check_all_invariants(state)
    return state


def sally(state, concede=None, **args):
    if concede == "attacker":
        args["scripted_decisions"] = [{"type": "concede", "side": "attacker", "choice": "yes"}]
    elif concede == "defender":
        args["scripted_decisions"] = [
            {"type": "concede", "side": "attacker", "choice": "no"},
            {"type": "concede", "side": "defender", "choice": "yes"},
        ]
    result = actions.dispatch(state, {
        "action": "cmd_sally", "side": "ghibelline", "args": {"lord_id": "siena", **args},
    })
    check_all_invariants(state)
    return result["state_changes"]["sally_result"]


def give_card(state, card, pile):
    side = "ghibelline" if card.startswith("S") else "guelph"
    for zone in state["decks"][side].values():
        if isinstance(zone, list) and card in zone:
            zone.remove(card)
    pile.append(card)
    check_all_invariants(state)


def test_fully_routed_sallying_lord_recovers_inside_after_raid():
    state = position(sally_knights=1, siege=3)
    result = sally(state)
    siena = state["lords"]["siena"]
    assert result["loser"] == "attacker"
    assert result["routed_out_lords"] == ["siena"] and result["removed_lords"] == []
    assert result["loss_results"]["siena"]["recovered"] == {"Cavalieri": 1}
    assert {"context": "loss_siena_Cavalieri", "value": 1} in result["rolls"]
    assert siena["status"] == "mustered" and siena["flags"]["in_stronghold"]
    assert siena["assets"] == {"Coin": 4, "Loot": 2, "Provender": 7, "Cart": 1}
    assert siena["service_box"] == 12 and not siena["routed_units"]
    assert state["locales"]["Siena"]["siege"][0]["count"] == 1
    assert not state.get("captured_knights", {}).get("ghibelline")


@pytest.mark.parametrize("seed,survives", [(7, True), (14, False)])
def test_routed_besieger_retreats_and_rolls_harsh_losses(seed, survives):
    state = position(seed, besieger_knights=1)
    result = sally(state)
    assert result["loser"] == "defender" and result["conceded"] is None
    assert result["routed_out_lords"] == ["firenze"]
    assert result["loss_results"]["firenze"]["harsh_recovery"]
    assert result["removed_lords"] == ([] if survives else ["firenze"])
    assert result["spoils"][0]["transferred"] == {"Coin": 4, "Loot": 2, "Provender": 8, "Cart": 1}
    assert not state["locales"]["Siena"]["siege"]
    assert not state["lords"]["siena"]["flags"].get("in_stronghold")
    assert {"context": "loss_firenze_Cavalieri", "value": 1 if survives else 2} in result["rolls"]


def test_conceding_besieger_surrenders_excess_on_track_and_shifts_service():
    state = position()
    state["meta"]["approach_breadcrumb"] = {
        "approached_from": "Montalcino", "approached_via": "track"}
    result = sally(state, "defender")
    firenze = state["lords"]["firenze"]
    assert firenze["location"] == "Montalcino" and firenze["status"] == "mustered"
    assert firenze["assets"] == {"Coin": 4, "Loot": 0, "Provender": 0, "Cart": 1}
    assert firenze["service_box"] == 11
    assert {"context": "retreat_shift_firenze", "value": 1} in result["rolls"]
    assert result["spoils"][0]["allocation"]["distributed"] == {"siena": {"Loot": 2, "Provender": 7}}
    assert not state["lords"]["siena"]["flags"].get("in_stronghold")


def test_retreat_destination_choice_uses_the_selected_road_capacity():
    state = position()
    state["locales"]["San Quirico"]["current_allegiance"] = [{"side": "guelph", "value": 1}]
    result = sally(state, "defender", post_battle_decisions=[{
        "type": "retreat_destination", "side": "guelph", "choice": "San Quirico"}])
    assert state["lords"]["firenze"]["location"] == "San Quirico"
    assert result["spoils"][0]["transferred"] == {"Loot": 2, "Provender": 6}
    assert state["lords"]["firenze"]["assets"]["Provender"] == 1


def test_blocked_besieger_retreat_has_full_removal_aftermath():
    state = position()
    state["locales"]["Montalcino"]["current_allegiance"] = []
    state["lords"]["firenze"]["assets"]["Ship"] = 1
    winner_deck = state["decks"]["ghibelline"]
    before_treachery = list(winner_deck["treachery_set_aside"])
    assert before_treachery
    result = sally(state, "defender")
    assert result["removed_lords"] == ["firenze"]
    assert result["spoils"][0]["transferred"] == {"Coin": 4, "Loot": 2, "Provender": 8, "Cart": 1}
    assert state["captured_knights"]["guelph"] == {"Cavalieri": 2}
    assert sum(r["context"].startswith("revolt_sally_firenze_") for r in result["rolls"]) == 6
    assert winner_deck["treachery_set_aside"] == before_treachery[3:]
    assert set(before_treachery[:3]) <= set(winner_deck["command_deck"])
    assert not state["locales"]["Siena"]["siege"]
    assert not state["lords"]["siena"]["flags"].get("in_stronghold")


def test_losing_besieger_can_elect_removal_despite_legal_retreat():
    state = position()
    move = next(m for m in enumerate_legal(state) if m["action"] == "cmd_sally")
    assert "post_battle_fate" in move["accepts_decisions"]["post_battle_decisions"]
    result = sally(state, "defender", post_battle_decisions=[
        {"type": "post_battle_fate", "side": "guelph", "choice": "remove"},
    ])
    assert result["removed_lords"] == ["firenze"]
    assert result["post_battle_decisions"][0]["options"] == ["retreat", "remove"]
    assert state["captured_knights"]["guelph"] == {"Cavalieri": 2}
    assert not state["locales"]["Siena"]["siege"]
    assert not state["lords"]["siena"]["flags"].get("in_stronghold")


def test_conceding_co_retreaters_share_carts_and_winner_selects_spoils_recipient():
    state = position()
    place(state, "arezzo", "Siena", Cart=2)
    reserve = place(state, "pisa", "Siena", Provender=2)
    reserve["flags"]["in_stronghold"] = True
    move = next(m for m in enumerate_legal(state) if m["action"] == "cmd_sally")
    assert "spoils_recipient" in move["accepts_decisions"]["post_battle_decisions"]
    choices = [
        {"type": "retreat_destination", "side": "guelph", "choice": "Montalcino"},
        {"type": "retreat_destination", "side": "guelph", "choice": "Montalcino"},
        {"type": "spoils_recipient", "side": "ghibelline", "choice": "pisa"},
        {"type": "spoils_amount", "side": "ghibelline", "choice": 2},
        {"type": "spoils_recipient", "side": "ghibelline", "choice": "pisa"},
        {"type": "spoils_amount", "side": "ghibelline", "choice": 5},
    ]
    result = sally(state, "defender", post_battle_decisions=choices)
    assert result["spoils"][0]["allocation"]["distributed"] == {"pisa": {"Loot": 2, "Provender": 5}}
    assert state["lords"]["arezzo"]["location"] == state["lords"]["firenze"]["location"] == "Montalcino"
    assert state["lords"]["arezzo"]["assets"]["Cart"] == 2
    assert state["lords"]["firenze"]["assets"]["Cart"] == 1
    assert all(row["side"] == "ghibelline" for row in result["post_battle_decisions"]
               if row["type"].startswith("spoils_"))


def test_bad_spoils_choice_rolls_back_sally_combat_retreat_and_dice():
    state = position()
    before = deepcopy(state)
    invalid = [{"type": "spoils_recipient", "side": "ghibelline", "choice": "firenze"}]
    with pytest.raises(actions.IllegalAction, match="BAD_DECISION"):
        sally(state, "defender", post_battle_decisions=invalid)
    assert state == before
    assert sally(state, "defender") == sally(before, "defender")
    assert state == before


@pytest.mark.parametrize("siege,trebuchets,remaining", [(3, False, 2), (3, True, 1), (2, True, 1)])
def test_trebuchets_reduces_three_siege_markers_for_sally(siege, trebuchets, remaining):
    state = position(4, siege=siege)
    if trebuchets:
        give_card(state, "S4", state["lords"]["siena"]["capabilities"])
    result = sally(state, "defender")
    assert state["lords"]["firenze"]["forces"] == {"Cavalieri": remaining}
    assert {"context": "siegeworks_Siena_center_0", "value": 3} in result["rolls"]


def test_trebuchets_stops_reducing_siegeworks_when_its_lord_routes():
    state = position(sally_knights=1, siege=3)
    reserve = place(state, "pisa", "Siena", Provender=2)
    reserve["forces"] = {"Cavalieri": 4}
    reserve["flags"]["in_stronghold"] = True
    control = deepcopy(state)
    give_card(state, "S4", state["lords"]["siena"]["capabilities"])
    result = sally(state)
    ordinary = sally(control)
    assert "siena" in result["routed_out_lords"]
    assert any(r["context"].startswith("siegeworks_") for r in result["rolls"])
    assert result["rolls"] == ordinary["rolls"]


def test_doctors_restores_sally_losses_and_clears_its_modifier():
    state = position(5)
    give_card(state, "S24", state["decks"]["ghibelline"]["aow_held"])
    event = next(m for m in enumerate_legal(state)
                 if m["action"] == "play_event" and m["args"].get("card_id") == "S24")
    actions.dispatch(state, event)
    result = sally(state, "attacker")
    assert result["loss_results"]["siena"]["captured"] == {"Cavalieri": 1}
    assert result["doctors"][0]["restored_for"] == {"siena": ["Cavalieri"]}
    assert state["lords"]["siena"]["forces"] == {"Cavalieri": 2}
    assert not state.get("captured_knights", {}).get("ghibelline")
    assert not any(m.get("id") == "S24" for m in state.get("battle_modifiers_pending", []))
