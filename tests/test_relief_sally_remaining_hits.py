"""Remaining Relief Sally Hits follow the living target row after Rout."""

import json

import pytest

from inferno import battle
from inferno.invariants import check_all_invariants
from inferno.rng import HarnessRNG
from tests.test_cross_game_sally import give_card
from tests.test_round7_combat import _besiege, _dispatch, _put, _tactical


@pytest.mark.parametrize("pisa_militia,selecting", [(1, None), (2, None), (1, False), (1, True)])
def test_relief_sally_continues_a_strike_after_the_rearguard_routs(pisa_militia, selecting):
    state = _tactical("firenze", "Figline", seed=3)
    _put(state, "firenze", "Figline", {"Militia": 1})
    front = {"Militia": 1} if selecting is None else {"Cavalieri": 1, "Men-at-Arms": 1}
    _put(state, "siena", "Firenze", front)
    _put(state, "pisa", "Firenze", {"Militia": pisa_militia})
    sallying = {"Cavalieri": 1, "Berrovieri": 1} if selecting is None else {"Armigieri": 2}
    lord = _put(state, "arezzo", "Firenze", sallying, inside=True)
    if selecting is not None:
        give_card(state, "F9", lord["capabilities"])
        if selecting:
            give_card(state, "F13", lord["capabilities"])
    _besiege(state, "Firenze", "ghibelline", 1)
    check_all_invariants(state)
    _dispatch(state, "cmd_march", "guelph", lord_id="firenze",
              destination="Firenze", way_type="road")
    _dispatch(state, "approach_response", "ghibelline", lord_id="siena", choice="stand")
    restored = json.loads(json.dumps(state))
    elections = []

    def choose(decision):
        if decision["type"] == "concede":
            return "yes" if decision["side"] == "defender" else "no"
        if decision["type"] in ("select_target_unit", "absorb_target"):
            elections.append(decision)
        return decision["options"][0]

    def resolve(position):
        position["battle_callback"] = choose
        result = _dispatch(position, "approach_response", "ghibelline", lord_id="pisa",
                           choice="stand")["battle_result"]
        position.pop("battle_callback")
        check_all_invariants(position)
        return result

    result = resolve(state)
    first_elections = list(elections)
    assert resolve(restored) == result and restored == state
    recipient = "siena" if pisa_militia == 1 else "pisa"
    unit = {None: "Militia", False: "Men-at-Arms", True: "Cavalieri"}[selecting]
    walls_suffix = {None: "", False: "_crossbow", True: "_crossbow_select"}[selecting]
    walls = f"relief_siegeworks_Firenze_arezzo{walls_suffix}"
    # Both Hits clear Siegeworks. The second hits the Front only if Pisa
    # ran out of units on the first Hit, and Walls are not rolled again.
    assert result["rolls"][:4] == [
        {"context": f"{walls}_0", "value": 2},
        {"context": f"{walls}_1", "value": 5},
        {"context": "protect_pisa_Militia", "value": 5},
        {"context": f"protect_{recipient}_{unit}", "value": 2},
    ]
    if selecting is not None:
        hit = next(h for h in result["rounds"][0]["hit_log"] if h.get("lord_id") == "siena")
        assert hit["crossbow"] and hit["protection"] == [1] and not hit["survived"]
        choice = first_elections[0]
        assert choice["info"]["lord_id"] == "siena"
        assert (choice["type"], choice["side"]) == (
            ("select_target_unit", "guelph") if selecting else ("absorb_target", "ghibelline"))


def test_rearguard_strike_continues_within_the_sally_row():
    state = _tactical("firenze", "Firenze", seed=1)
    _put(state, "firenze", "Firenze", {"Militia": 1})
    _put(state, "siena", "Firenze", {"Militia": 1})
    _put(state, "pisa", "Firenze", {"Cavalieri": 2})
    _put(state, "arezzo", "Firenze", {"Militia": 1}, inside=True)
    _put(state, "orvieto", "Firenze", {"Militia": 1}, inside=True)
    _besiege(state, "Firenze", "ghibelline", 1)
    positions = {"attacker": {"left": None, "center": "firenze", "right": None},
                 "defender": {"left": None, "center": "siena", "right": None}}
    reserve = {"attacker": [], "defender": ["pisa"]}
    # After Round 2 Reposition, both Sallying Lords are in their Front.
    relief_front = ["arezzo", "orvieto"]
    rng = HarnessRNG(1)
    log, removed = [], set()
    battle._resolve_relief_substep(
        state, "def_horse_melee", relief_front, [], positions, reserve, None,
        battle.BattleDecisionContext(), rng.roll, log, removed, {},
        2, [1], "Firenze", "ghibelline")
    assert [r.context for r in rng.drain_log()] == [
        "protect_arezzo_Militia", "protect_orvieto_Militia"]
    assert removed == {"arezzo", "orvieto"} and not relief_front
    assert state["lords"]["firenze"]["forces"] == {"Militia": 1}
