import copy
import json

import pytest

from inferno.actions import IllegalAction
from inferno.cli import _load_state
from inferno.invariants import check_all_invariants
from inferno.legal_moves import enumerate_legal
from tests._helpers import _place
from tests.test_round11_lieutenants import _act, _finish_plan, _plan


def _pair(state, upper, lower):
    return _act(state, "plan_attach_lieutenant", "guelph", lieutenant=upper, lower_lord=lower)


def _choices(state):
    return {(move["args"]["lieutenant"], move["args"]["lower_lord"])
            for move in enumerate_legal(state) if move["action"] == "plan_attach_lieutenant"}


def _reload(state, tmp_path):
    saved = tmp_path / "game.json"
    saved.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    return _load_state(saved)


def _plan_with_pair():
    state = _plan()
    for lord_id in ("colle", "guido_guerra"):
        _place(state, lord_id, "Arezzo")
    _pair(state, "arezzo", "orvieto")
    return state


@pytest.mark.parametrize(("upper", "lower", "code"), [
    ("arezzo", "colle", "ALREADY_HAS_LOWER"),
    ("colle", "orvieto", "ALREADY_STACKED"),
    ("orvieto", "colle", "ALREADY_STACKED"),
    ("colle", "arezzo", "ALREADY_HAS_LOWER"),
    ("colle", "colle", "SELF_STACK"),
])
def test_plan_rejects_conflicting_assignments_without_changing_the_lower_card(upper, lower, code):
    state = _plan_with_pair()
    before = copy.deepcopy(state)
    assert (upper, lower) not in _choices(state)
    with pytest.raises(IllegalAction) as rejected:
        _pair(state, upper, lower)
    assert rejected.value.code == code
    assert state == before

    _finish_plan(state, "guelph", "orvieto")
    _finish_plan(state, "ghibelline")
    _act(state, "command_reveal", "guelph")
    assert state["current_lord_id"] is None
    check_all_invariants(state)


@pytest.mark.parametrize(("upper", "lower"), [("arezzo", "orvieto"), ("orvieto", "arezzo")])
def test_plan_advertises_both_orientations_and_valid_pairs_survive_reload(upper, lower, tmp_path):
    state = _plan()
    assert (upper, lower) in _choices(state)
    _pair(state, upper, lower)
    restored = _reload(state, tmp_path)
    assert restored == state
    assert restored["lords"][upper]["flags"]["has_lower_lord"] == lower
    assert restored["lords"][lower]["flags"]["lower_lord_of"] == upper
    check_all_invariants(restored)


def test_old_save_cleans_dangling_and_self_links_but_preserves_the_reciprocal_pair(tmp_path):
    state = _plan_with_pair()
    state["lords"]["arezzo"]["flags"]["has_lower_lord"] = "colle"
    state["lords"]["colle"]["flags"]["lower_lord_of"] = "arezzo"
    state["lords"]["guido_guerra"]["flags"].update(
        has_lower_lord="guido_guerra", lower_lord_of="guido_guerra")
    restored = _reload(state, tmp_path)
    check_all_invariants(restored)
    assert restored["lords"]["arezzo"]["flags"]["has_lower_lord"] == "colle"
    assert restored["lords"]["colle"]["flags"]["lower_lord_of"] == "arezzo"
    assert ("orvieto", "guido_guerra") in _choices(restored)
    assert {lid: lord["location"] for lid, lord in restored["lords"].items()} == {
        lid: lord["location"] for lid, lord in state["lords"].items()
    }


def test_pair_cannot_span_inside_and_outside_the_stronghold():
    state = _plan()
    state["lords"]["arezzo"]["flags"]["in_stronghold"] = True
    assert ("arezzo", "orvieto") not in _choices(state)
    before = copy.deepcopy(state)
    with pytest.raises(IllegalAction) as rejected:
        _pair(state, "arezzo", "orvieto")
    assert rejected.value.code == "DIFFERENT_LOCALES"
    assert state == before
