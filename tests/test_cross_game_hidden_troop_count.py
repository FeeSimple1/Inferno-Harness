"""Cross-game IF-4: hidden troop totals must not depend on army size."""
from copy import deepcopy

import pytest

from inferno.llm import build_briefing, hide_for_side
from inferno.scenarios import load_scenario
from inferno.visibility import combat_view_scope


@pytest.mark.parametrize("side,enemy", [("guelph", "siena"), ("ghibelline", "firenze")])
@pytest.mark.parametrize("option", ["saved", "argument"])
def test_hidden_army_changes_do_not_change_player_snapshot_or_briefing(side, enemy, option):
    state = load_scenario("A", seed=1, hidden_mats=option == "saved")
    other = deepcopy(state)
    other["lords"][enemy]["forces"] = {"Militia": 7, "Men-at-Arms": 2}
    kwargs = {"hidden_mats": True} if option == "argument" else {}
    before = deepcopy(state)
    view = hide_for_side(state, side, **kwargs)
    assert view == hide_for_side(other, side, **kwargs)
    assert view["lords"][enemy]["forces"] == {"<hidden>": True}
    assert hide_for_side(view, side) == view  # repeated filtering remains safe
    assert build_briefing(state, side, **kwargs) == build_briefing(other, side, **kwargs)
    assert state == before


@pytest.mark.parametrize("side,enemy", [("guelph", "siena"), ("ghibelline", "firenze")])
def test_open_mats_still_show_exact_forces(side, enemy):
    state = load_scenario("A", seed=1)
    assert hide_for_side(state, side)["lords"][enemy]["forces"] == state["lords"][enemy]["forces"]


def test_combat_reveals_only_participating_mats_then_hides_them_again():
    state = load_scenario("A", seed=1, hidden_mats=True)
    @combat_view_scope("attackers", "defenders")
    def inspect_combat(state, attackers, defenders):
        return hide_for_side(state, "guelph")
    view = inspect_combat(state, ["firenze"], ["siena"])
    assert view["lords"]["siena"]["forces"] == state["lords"]["siena"]["forces"]
    assert view["lords"]["provenzano"]["forces"] == {"<hidden>": True}
    assert hide_for_side(state, "guelph")["lords"]["siena"]["forces"] == {"<hidden>": True}
