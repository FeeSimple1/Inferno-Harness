"""Round 10 combat regressions using public actions and the original dice."""

import json

import pytest

from inferno.invariants import check_all_invariants
from tests.test_cross_game_sally import give_card
from tests.test_round7_combat import _besiege, _dispatch, _put, _tactical


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
