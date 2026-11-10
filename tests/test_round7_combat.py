"""Round 7 combat regressions using the dispatcher and seeded dice."""

from copy import deepcopy

import pytest

from inferno import actions
from inferno.invariants import check_all_invariants
from inferno.legal_moves import enumerate_legal
from inferno.llm.interface import PlayerView, play_with_interface
from tests.test_cross_game_escape import place
from tests.test_cross_game_sally import give_card
from tests.test_phase3c import _to_command_with


def _tactical(lord_id, locale, seed):
    state = _to_command_with("F", 1, lord_id, locale)
    state["meta"].update(turn=9, rng_seed=seed, rng_advance=0)
    for box in state["calendar"]["boxes"].values():
        if "levy" in box["markers"]:
            box["markers"].remove("levy")
    state["calendar"]["boxes"]["9"]["markers"].append("levy")
    state["calendar"]["levy_box"] = 9
    for lid, lord in state["lords"].items():
        if lord["status"] == "mustered":
            actions._place_service(state, lid, 12)
    return state


def _put(state, lid, locale, forces, *, inside=False):
    lord = place(state, lid, locale, Provender=4, Cart=2, Coin=2)
    state["decks"][lord["side"]]["aow_deck"].extend(lord["capabilities"])
    lord.update(forces=forces, capabilities=[])
    lord["flags"]["in_stronghold"] = inside
    for vassal in lord["vassals"]:
        if not vassal.get("special"):
            vassal.update(on_mat=True, ready=False, service_box=None)
    return lord


def _dispatch(state, action, side, **args):
    return actions.dispatch(state, {"action": action, "side": side, "args": args})["state_changes"]


def _besiege(state, locale, side, count):
    color = "purple" if side == "guelph" else "gold"
    state["locales"][locale]["siege"] = [{"side": side, "color": color, "count": count}]


def test_relief_trebuchets_expires_when_the_bearer_routs():
    state = _tactical("firenze", "Figline", seed=4)
    _put(state, "firenze", "Figline", {"Cavalieri": 2, "Men-at-Arms": 2})
    _put(state, "siena", "Firenze", {"Cavalieri": 1, "Men-at-Arms": 2})
    _put(state, "pisa", "Firenze", {"Cavalieri": 3, "Men-at-Arms": 3})
    _put(state, "arezzo", "Firenze", {"Militia": 1}, inside=True)
    _put(state, "orvieto", "Firenze", {"Cavalieri": 2, "Men-at-Arms": 2}, inside=True)
    _besiege(state, "Firenze", "ghibelline", 3)

    def choose(decision):
        if decision["type"] == "concede":
            return "yes" if decision["info"]["round"] == 3 else "no"
        if decision["type"] == "relief_reserve_add":
            return "yes"
        return decision["options"][0]

    def resolve(position):
        position["battle_callback"] = choose
        _dispatch(position, "cmd_march", "guelph", lord_id="firenze",
                  destination="Firenze", way_type="road")
        _dispatch(position, "approach_response", "ghibelline", lord_id="siena", choice="stand")
        result = _dispatch(position, "approach_response", "ghibelline", lord_id="pisa", choice="stand")
        position.pop("battle_callback")
        check_all_invariants(position)
        return result["battle_result"]

    control = deepcopy(state)
    give_card(state, "F4", state["lords"]["arezzo"]["capabilities"])
    result = resolve(state)
    assert any(hit.get("relief_routed") == "arezzo" for hit in result["rounds"][0]["hit_log"])
    assert any(hit.get("lord_id") == "pisa" for hit in result["rounds"][1]["hit_log"])
    assert result["rounds"] == resolve(control)["rounds"]


@pytest.mark.parametrize("forced", [False, True])
def test_sally_owner_selects_the_reserve_lord(forced):
    state = _tactical("siena", "Siena", seed=1)
    _put(state, "siena", "Siena", {"Cavalieri": 1, "Men-at-Arms": 3, "Militia": 2}, inside=True)
    _put(state, "firenze", "Siena", {"Men-at-Arms": 1} if forced else {
        "Cavalieri": 2, "Men-at-Arms": 3})
    _put(state, "arezzo", "Siena", {"Cavalieri": 1, "Armigieri": 3})
    _put(state, "orvieto", "Siena", {"Cavalieri": 2, "Men-at-Arms": 2})
    _besiege(state, "Siena", "guelph", 3)
    election = "sally_forced_front" if forced else "sally_reserve_lord"

    def choose(decision):
        if decision["type"] == "concede":
            return "yes" if decision["info"]["round"] == 2 else "no"
        if decision["type"] == "sally_defender_front":
            return "firenze"
        if decision["type"] == "sally_reserve_add":
            return "no" if forced else "yes"
        if decision["type"] == election:
            assert decision["side"] == "defender"
            assert decision["options"] == ["arezzo", "orvieto"]
            return "orvieto"
        return decision["options"][0]

    state["battle_callback"] = choose
    result = _dispatch(state, "cmd_sally", "ghibelline", lord_id="siena")["sally_result"]
    state.pop("battle_callback")
    check_all_invariants(state)
    slot = "center" if forced else "left"
    assert result["rounds"][1]["positions"]["defender"][slot] == "orvieto"
    assert any(d["type"] == election and d["choice"] == "orvieto" for d in result["decisions"])


def _deploy_distringitores(state):
    state["decks"]["guelph"]["aow_deck"].remove("F21")
    state["capabilities_in_play"].append({
        "id": "F21", "side": "guelph", "scope": "side_wide", "name": "Distringitores",
    })


@pytest.mark.parametrize("recover,palvesari", [(False, False), (True, False), (True, True)])
def test_distringitores_resolves_after_archery_before_melee(recover, palvesari):
    state = _tactical("firenze", "Firenze", seed=1)
    _put(state, "firenze", "Firenze", {"Cavalieri": 2, "Men-at-Arms": 3, "Armigieri": 1})
    _put(state, "siena", "Figline", {"Cavalieri": 1, "Men-at-Arms": 3, "Militia": 2})
    give_card(state, "S16", state["lords"]["siena"]["capabilities"])
    if palvesari:
        give_card(state, "F13", state["lords"]["firenze"]["capabilities"])
    _deploy_distringitores(state)
    elections = []

    def choose(decision):
        if decision["type"] == "concede":
            return "yes"
        if decision["type"].startswith("distringitores_"):
            elections.append(decision)
            return decision["options"][1 if recover else 0]
        return decision["options"][0]

    state["battle_callback"] = choose
    _dispatch(state, "cmd_march", "guelph", lord_id="firenze", destination="Figline", way_type="road")
    result = _dispatch(state, "approach_response", "ghibelline", lord_id="siena",
                       choice="stand")["battle_result"]
    state.pop("battle_callback")
    check_all_invariants(state)

    assert elections[0]["options"] == ["pass", "firenze"]
    assert all(election["side"] == "guelph" for election in elections)
    assert result["rolls"][:2] == [
        {"context": "protect_firenze_Armigieri", "value": 2},
        {"context": "protect_firenze_Armigieri", "value": 5},
    ]
    if recover:
        assert len(elections) == 2
        assert elections[1]["options"] == ["pass", "Armigieri"]
        assert result["rolls"][2] == {"context": "distringitores_firenze_Armigieri", "value": 1}
        assert result["rolls"][3]["context"] == "protect_firenze_Armigieri"
        restored, = [h["distringitores"] for h in result["rounds"][0]["hit_log"] if "distringitores" in h]
        assert restored["recovered"]
        assert restored["protection"] == ([1, 2, 3, 4] if palvesari else [1, 2])
    else:
        assert len(elections) == 1
        assert result["rolls"][2] == {"context": "protect_firenze_Men-at-Arms", "value": 1}


def test_distringitores_storm_can_select_two_pieces_of_one_type():
    state = _tactical("firenze", "Volterra", seed=4)
    _put(state, "firenze", "Volterra", {"Cavalieri": 2, "Men-at-Arms": 3, "Armigieri": 1})
    _besiege(state, "Volterra", "guelph", 1)
    _deploy_distringitores(state)

    storm = next(move for move in enumerate_legal(state) if move["action"] == "cmd_storm")
    assert {"distringitores_lord", "distringitores_unit"} <= set(
        storm["accepts_decisions"]["scripted_decisions"])

    def choose(view):
        if isinstance(view, PlayerView):
            entry = view.query({"request": "actions", "category": "cmd_storm"})["records"][0]
        else:
            entries = view.query({"request": "actions"})["records"]
            entry = entries[0]
            if view.overview()["decision"].startswith("distringitores_"):
                assert view.side == "guelph"
                entry = entries[1]
        return {"action_id": entry["action_id"], "state_version": view.version}

    result = play_with_interface(state, choose).applied["state_changes"]["storm_result"]
    check_all_invariants(state)
    restored = [hit["distringitores"] for hit in result["rounds"][0]["hit_log"] if "distringitores" in hit]
    assert [(h["unit"], h["die"], h["recovered"]) for h in restored] == [
        ("Cavalieri", 4, False), ("Cavalieri", 2, True),
    ]
