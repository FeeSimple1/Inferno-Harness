"""Round 10 combat regressions using public actions and the original dice."""

import json

import pytest

from inferno.invariants import check_all_invariants
from inferno.llm.interface import DecisionView, play_with_interface
from tests.test_cross_game_sally import give_card
from tests.test_round7_combat import _besiege, _dispatch, _put, _tactical


def test_striking_player_orders_groups_through_live_decision_view():
    state = _tactical("firenze", "Firenze", seed=1)
    for lid, locale in (("firenze", "Firenze"), ("arezzo", "Firenze"),
                        ("siena", "Figline"), ("pisa", "Figline")):
        _put(state, lid, locale, {"Cavalieri": 1})
    _dispatch(state, "cmd_march", "guelph", lord_id="firenze", destination="Figline",
              way_type="road", with_lords=["arezzo"])
    _dispatch(state, "approach_response", "ghibelline", lord_id="siena", choice="stand")
    check_all_invariants(state)
    checkpoint = json.dumps(state)

    def resolve(first_target):
        position = json.loads(checkpoint)
        elections = []

        def choose(view):
            if view.can_yield:
                return {"yield": True, "state_version": view.version}
            if isinstance(view, DecisionView):
                overview = view.overview()
                rows = view.query({"request": "actions"})["records"]
                options = [row["move"]["args"]["choice"] for row in rows]
                choice = options[0]
                if overview["decision"] == "initial_placement_attacker" and "left" in options:
                    choice = "left"
                elif overview["decision"] == "initial_placement_defender" and "siena" in options:
                    choice = "siena"
                elif overview["decision"] == "concede":
                    choice = "yes" if view.side == "ghibelline" else "no"
                elif overview["decision"] == "strike_order":
                    info = overview["context"]
                    if info["step"] == "def_horse_melee":
                        assert view.side == "ghibelline"
                        assert options == ["arezzo", "firenze"]
                        assert info == {"round": 1, "step": "def_horse_melee",
                                        "strikers": {"arezzo": ["pisa"], "firenze": ["siena"]}}
                        choice = first_target
                        elections.append(choice)
                row = rows[options.index(choice)]
            else:
                rows = view.query({"request": "actions", "category": "approach_response"})["records"]
                row = next(r for r in rows if r["move"]["args"]["choice"] == "stand")
            return {"action_id": row["action_id"], "state_version": view.version}

        result = play_with_interface(position, choose).applied["state_changes"]["battle_result"]
        check_all_invariants(position)
        assert elections == [first_target]
        return result, position

    ordinary, _ = resolve("arezzo")
    reversed_order, final = resolve("firenze")
    assert (reversed_order, final) == resolve("firenze")
    for result, targets in ((ordinary, ["arezzo", "firenze"]),
                            (reversed_order, ["firenze", "arezzo"])):
        rolls = [r for r in result["rolls"] if r["context"].startswith("protect_")][:2]
        assert [r["context"] for r in rolls] == [f"protect_{lid}_Cavalieri" for lid in targets]


@pytest.mark.parametrize("sally, seed", [(False, 52814), (True, 276)])
@pytest.mark.parametrize("concede", [False, True])
def test_battle_and_sally_continue_after_round_twelve(sally, seed, concede):
    state = _tactical("firenze", "Firenze", seed=seed)
    _put(state, "firenze", "Firenze", {"Armigieri": 1}, inside=sally)
    _put(state, "pisa", "Firenze" if sally else "Figline", {"Armigieri": 1})
    give_card(state, "F13", state["lords"]["firenze"]["capabilities"])
    give_card(state, "S13", state["lords"]["pisa"]["capabilities"])
    if sally:
        _besiege(state, "Firenze", "ghibelline", 3)
    else:
        _dispatch(state, "cmd_march", "guelph", lord_id="firenze",
                  destination="Figline", way_type="road")

    conceding_side = "defender" if sally else "attacker"

    def choose(decision):
        if (concede and decision["type"] == "concede"
                and decision["side"] == conceding_side
                and decision["info"]["round"] == 13):
            return "yes"
        return decision["options"][0]

    def resolve(position):
        position["battle_callback"] = choose
        if sally:
            result = _dispatch(position, "cmd_sally", "guelph",
                               lord_id="firenze")["sally_result"]
        else:
            result = _dispatch(position, "approach_response", "ghibelline",
                               lord_id="pisa", choice="stand")["battle_result"]
        position.pop("battle_callback")
        check_all_invariants(position)
        return result

    restored = json.loads(json.dumps(state))
    result = resolve(state)
    assert result == resolve(restored)
    assert state == restored
    assert all(hit["survived"] for rnd in result["rounds"][:12] for hit in rnd["hit_log"])
    assert result["rounds"][12]["round"] == 13
    if concede:
        assert result["rounds_played"] == 13
        assert result["conceded"] == conceding_side
        assert result["winner"] == ("attacker" if sally else "defender")
    else:
        assert result["rounds_played"] == 15
        assert result["conceded"] is None
        assert result["routed_per_lord"] == {"firenze": ["Armigieri"]}
        assert result["winner"] == "defender"


def test_siege_towers_strikes_before_the_garrison_from_round_two():
    def storm(with_towers):
        position = _tactical("firenze", "Volterra", seed=1)
        lord = _put(position, "firenze", "Volterra", {
            "Cavalieri": 3, "Men-at-Arms": 3, "Light Horse": 1,
            "Militia": 3, "Armigieri": 1,
        })
        _besiege(position, "Volterra", "guelph", 2)
        give_card(position, "F16", lord["capabilities"])
        if with_towers:
            give_card(position, "F3", lord["capabilities"])
        result = _dispatch(position, "cmd_storm", "guelph",
                           lord_id="firenze")["storm_result"]
        check_all_invariants(position)
        return result

    towers, ordinary = storm(True), storm(False)
    assert towers["rounds_played"] == ordinary["rounds_played"] == 2
    assert towers["rounds"][0] == ordinary["rounds"][0]
    assert ordinary["rounds"][1]["hit_log"][0]["crossbow"]
    # The holder's early melee Routs both Garrison Crossbow units.
    garrison_hits = [
        (hit["garrison_unit"], hit["die"], hit["survived"])
        for hit in towers["rounds"][1]["hit_log"] if "garrison_unit" in hit
    ]
    assert garrison_hits == [("Armigieri", 4, False), ("Men-at-Arms", 6, False)]
    assert towers["rounds"][1]["hit_log"][0]["garrison_unit"] == "Armigieri"
    assert not any(hit["crossbow"] for hit in towers["rounds"][1]["hit_log"])
