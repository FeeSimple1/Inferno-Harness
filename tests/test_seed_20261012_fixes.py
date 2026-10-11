"""Regressions found by the second full Scenario F endurance game (seed 20261012)."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from inferno import actions as A
from inferno.battle import BattleDecisionContext
from inferno.invariants import check_all_invariants
from inferno.legal_moves import enumerate_legal
from inferno.revolt import legal_exiles_targets
from inferno.scenarios import load_scenario


def act(name, side="guelph", **args):
    return {"action": name, "side": side, "args": args}


def rejected_unchanged(state, action, code):
    before = deepcopy(state)
    with pytest.raises(A.IllegalAction) as exc:
        A.dispatch(state, action)
    assert exc.value.code == code
    assert state == before


def relocate(state, lid, locale):
    old = state["lords"][lid].get("location")
    if old and lid in state["locales"][old].get("lords_present", []):
        state["locales"][old]["lords_present"].remove(lid)
    A._place_cylinder(state, lid, None)
    state["lords"][lid].update(status="mustered", location=locale)
    if lid not in state["locales"][locale].setdefault("lords_present", []):
        state["locales"][locale]["lords_present"].append(lid)


def cta_gather_state():
    state = load_scenario("F", seed=20261012)
    state["meta"].update(
        phase="levy", levy_step="3.5", active_player="guelph",
        cta_active=True, cta_substep="gather", cta_sides_done=[],
    )
    relocate(state, "arezzo", "Cortona")
    state["lords"]["arezzo"]["assets"] = {"Cart": 2, "Provender": 2}
    return state


def test_gather_tracks_command_allowance_across_multiple_legs_and_menu():
    state = cta_gather_state()
    route = [
        ("Castiglione", "road", 0),
        ("Arezzo", "road", 1),
        ("Montevarchi", "road", 1),
    ]
    for destination, way, expected_cost in route:
        action = act("cta_gather_march", lord_id="arezzo",
                     destination=destination, way_type=way)
        assert any(m["action"] == action["action"] and m["args"] == action["args"]
                   for m in enumerate_legal(state))
        result = A.dispatch(state, action)
        assert result["state_changes"]["command_cost"] == expected_cost
    assert state["meta"]["cta_gather_usage"]["guelph"]["arezzo"] == {
        "allowance": 2, "spent": 2, "first_march_used": True,
    }
    fourth = act("cta_gather_march", lord_id="arezzo",
                 destination="San Giovanni", way_type="road")
    assert not any(m["action"] == fourth["action"] and m.get("args") == fourth["args"]
                   for m in enumerate_legal(state))
    rejected_unchanged(state, fourth, "INSUFFICIENT_COMMAND")


def test_gather_usage_is_cleared_when_the_side_finishes_gather():
    state = cta_gather_state()
    A.dispatch(state, act("cta_gather_march", lord_id="arezzo",
                          destination="Castiglione", way_type="road"))
    assert state["meta"].get("cta_gather_usage")
    A.dispatch(state, act("cta_step_skip"))
    assert state["meta"]["cta_substep"] == "commander_arms"
    assert not state["meta"].get("cta_gather_usage")


def test_holding_treasurers_is_not_free_call_to_arms_trigger():
    state = load_scenario("F", seed=17)
    state["meta"].update(phase="levy", levy_step="3.5", active_player="guelph",
                         cta_active=False, cta_substep=None)
    state["vp"] = {"guelph": 8.0, "ghibelline": 6.0}
    state["war_declared_this_levy"] = []
    deck = state["decks"]["guelph"]
    for zone in ("aow_deck", "aow_discard"):
        while "F23" in deck[zone]:
            deck[zone].remove("F23")
    if "F23" not in deck["aow_held"]:
        deck["aow_held"].append("F23")
    state["lords"]["firenze"]["assets"]["Coin"] = 2

    assert A._cta_trigger_met(state, "guelph") == (False, "no_trigger")
    rejected_unchanged(state, act("levy_cta_declare"), "CTA_NOT_ELIGIBLE")
    assert not any(m["action"] == "levy_cta_declare" for m in enumerate_legal(state))

    play = act("play_event", card_id="F23", effect_args={
        "mode": "declare_cta", "coin_sources": {"firenze": 2},
    })
    assert any(m["action"] == "play_event" and m.get("args") == play["args"]
               for m in enumerate_legal(state))
    A.dispatch(state, play)
    assert state["lords"]["firenze"]["assets"]["Coin"] == 0
    assert "F23" not in state["decks"]["guelph"]["aow_held"]
    assert A._cta_trigger_met(state, "guelph") == (True, "war_event")
    A.dispatch(state, act("levy_cta_declare"))
    assert state["meta"]["cta_active"]


def _battle_state():
    state = load_scenario("F", seed=1)
    for lid in ("firenze", "siena", "siena_comune"):
        relocate(state, lid, "Siena")
        state["lords"][lid].setdefault("flags", {}).pop("in_stronghold", None)
    state["locales"]["Siena"]["siege"] = []
    return state


def test_fully_routed_lord_withdraws_and_rolls_before_removal():
    state = _battle_state()
    state["lords"]["firenze"]["forces"] = {"Militia": 1}
    state["lords"]["siena"]["forces"] = {}
    state["lords"]["siena"]["routed_units"] = {"Cavalieri": 1}
    result = {"loser": "defender", "conceded": None,
              "removed_lords": ["siena"], "rolls": []}
    A._apply_post_battle(
        state, result, ["firenze"], ["siena"], battle_locale="Siena",
        decisions=[{"type": "post_battle_withdraw", "choice": "withdraw"}],
    )
    assert result["routed_out_lords"] == ["siena"]
    assert result["removed_lords"] == []
    assert result["loss_results"]["siena"]["recovered"] == {"Cavalieri": 1}
    assert any(r["context"] == "loss_siena_Cavalieri" for r in result["rolls"])
    assert state["lords"]["siena"]["status"] == "mustered"
    assert state["lords"]["siena"]["flags"]["in_stronghold"] is True
    assert state["lords"]["siena"]["forces"] == {"Cavalieri": 1}


def test_commander_removal_processes_comune_spoils_and_carroccio_first():
    state = _battle_state()
    winner = state["lords"]["firenze"]
    winner["forces"] = {"Militia": 1}
    winner["assets"] = {}
    for lid in ("siena", "siena_comune"):
        state["lords"][lid]["forces"] = {}
        state["lords"][lid]["routed_units"] = {}
    state["lords"]["siena"]["assets"] = {}
    comune = state["lords"]["siena_comune"]
    comune["assets"] = {"Cart": 2, "Coin": 2}
    comune["vassals"] = [{"name": "Carroccio", "special": True, "on_mat": True}]
    assert any(v.get("name") == "Carroccio" and v.get("on_mat")
               for v in comune["vassals"])
    result = {"loser": "defender", "conceded": None,
              "removed_lords": [], "rolls": []}
    A._apply_post_battle(state, result, ["firenze"],
                         ["siena", "siena_comune"], battle_locale=None)
    assert set(result["removed_lords"]) == {"siena", "siena_comune"}
    assert state["captured_carroccio_for_side"]["guelph"] == 1
    assert winner["assets"]["Cart"] == 2
    assert winner["assets"]["Coin"] == 2
    assert state["lords"]["siena_comune"]["status"] == "in_levy_pool"
    assert state["lords"]["siena_comune"]["assets"] == {}


def test_battle_decision_trace_snapshots_mutable_positions():
    positions = {
        "attacker": {"left": "A", "center": None, "right": None},
        "defender": {"left": None, "center": "D", "right": None},
    }
    bdc = BattleDecisionContext()
    assert bdc.decide("concede", "attacker", ["no", "yes"],
                      {"round": 1, "positions": positions}) == "no"
    positions["defender"]["center"] = None
    assert bdc.trace[0]["info"]["positions"]["defender"]["center"] == "D"


def test_dispatch_does_not_duplicate_a_handler_reported_fealty_roll():
    state = load_scenario("F", seed=20261012)
    state["meta"].update(phase="levy", levy_step="3.4", active_player="ghibelline")
    state["lords"]["siena"].setdefault("flags", {})["lordship_used"] = 0
    result = A.dispatch(state, act(
        "levy_muster_lord", "ghibelline", muster_lord_id="siena",
        target_lord_id="provenzano", target_seat="Siena",
    ))
    fealty = [r for r in result["rolls"] if r["context"] == "fealty_provenzano"]
    assert len(fealty) == 1


def test_save_reload_order_cannot_change_exiles_feed_or_waste_defaults():
    state = load_scenario("F", seed=23)
    state["meta"].update(phase="campaign", campaign_step="end_campaign",
                         active_player="guelph", end_substep="waste")
    relocate(state, "colle", "Colle")
    state["lords"]["colle"]["assets"] = {"Coin": 5, "Cart": 3}
    state["lords"]["firenze"]["assets"] = {"Coin": 3, "Cart": 4}
    restored = json.loads(json.dumps(state, sort_keys=True))
    result_a = A.dispatch(state, act("end_waste"))
    result_b = A.dispatch(restored, act("end_waste"))
    assert result_a == result_b
    assert state == restored
    assert state["lords"]["colle"]["assets"] == {"Coin": 5, "Cart": 2}
    assert state["lords"]["firenze"]["assets"] == {"Coin": 3, "Cart": 3}

    a = load_scenario("F", seed=23)
    b = json.loads(json.dumps(a, sort_keys=True))
    assert legal_exiles_targets(a, "ghibelline") == legal_exiles_targets(b, "ghibelline")


def test_feed_result_and_state_are_save_reload_deterministic():
    state = load_scenario("F", seed=31)
    state["meta"].update(phase="campaign", campaign_step="command_phase",
                         active_player="guelph")
    for lid in ("firenze", "arezzo"):
        relocate(state, lid, "Firenze")
        state["lords"][lid].setdefault("flags", {})["moved_fought"] = True
        state["lords"][lid]["forces"] = {"Militia": 1}
        state["lords"][lid]["assets"] = {"Provender": 1}
    restored = json.loads(json.dumps(state, sort_keys=True))
    result_a = A._run_fpd(state)
    result_b = A._run_fpd(restored)
    assert result_a == result_b
    assert state == restored
