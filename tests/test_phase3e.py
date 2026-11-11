"""Phase 3e tests: End-of-Campaign 4.9 substeps."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from inferno.actions import IllegalAction, dispatch
from inferno.legal_moves import enumerate_legal_validated
from inferno.llm.interface import PlayerView, selection_session
from inferno.scenarios import _init_vp_from_markers, load_scenario
from inferno.state import load_saved_state


def _to_end_campaign(scenario="A", seed=1, turn_override=None):
    s = load_scenario(scenario, seed=seed)
    # Force turn to a Grow box for grow tests
    if turn_override is not None:
        old_box = str(s["calendar"]["levy_box"])
        s["calendar"]["boxes"][old_box]["markers"].remove("levy")
        s["calendar"]["boxes"][str(turn_override)]["markers"].append("levy")
        s["meta"]["turn"] = turn_override
        s["calendar"]["levy_box"] = turn_override
    # Drive through Levy + Campaign skip
    for name, side in [
        ("levy_aow_draw","guelph"),("levy_aow_draw","ghibelline"),
        ("levy_pay_done","guelph"),("levy_pay_done","ghibelline"),
        ("levy_disband_done","guelph"),("levy_disband_done","ghibelline"),
        ("levy_muster_done","guelph"),("levy_muster_done","ghibelline"),
        ("levy_cta_skip","guelph"),("levy_cta_skip","ghibelline"),
    ]:
        dispatch(s, {"action": name, "side": side})
    from tests.test_phase3a import _skip_capability_discard, _build_pass_plan
    _skip_capability_discard(s)
    _build_pass_plan(s, "guelph")
    _build_pass_plan(s, "ghibelline")
    # Reveal all cards (every Lord card is Pass for now)
    safety = 30
    while s["meta"].get("campaign_step") == "command_phase" and safety > 0:
        from tests._helpers import _finish_pending_choices
        _finish_pending_choices(s)
        dispatch(s, {"action": "command_reveal", "side": s["meta"]["active_player"]})
        safety -= 1
    return s


class TestGrow:
    def test_grow_skip_on_non_grow_turn(self):
        s = _to_end_campaign("A", seed=1)
        # Turn 1 is not a Grow turn -> only end_grow_skip
        dispatch(s, {"action": "end_grow_skip", "side": "guelph"})
        dispatch(s, {"action": "end_grow_skip", "side": "ghibelline"})
        # After both sides skip, "grow" is in done
        assert "grow" in s["meta"]["end_substep_done"]

    def test_grow_on_grow_turn_reduces_ravages(self):
        s = _to_end_campaign("A", seed=1, turn_override=2)  # Apr-May = Grow
        # Plant 4 enemy (purple = Guelph-owned, CONF-039) Ravage markers on
        # Ghibelline locales
        for loc_name in ("Volterra", "Asinalunga", "Cortona", "Montepulciano"):
            if loc_name in s["locales"]:
                s["locales"][loc_name]["ravaged"] = "purple"
        # Pre-set VP for Guelphs reflecting 4 Ravages
        s["vp"]["guelph"] = 2.0
        # Ghibelline's Grow removes Guelph (enemy) Ravage markers: ceil(4/2) = 2 kept, 2 removed
        # Force Ghibelline to go: dispatch Guelph-grow-skip first
        # Actually flow: Guelph goes first. For Guelph, enemy = ghibelline.
        # We planted purple = Guelph color, so for Guelph's grow, enemy_color = gold, n=0.
        # Better to test from Ghibelline's perspective.
        # Guelph has no enemy ravages -> no-op
        dispatch(s, {"action": "end_grow", "side": "guelph", "args": {"keep": []}})
        # Ghibelline now: enemy_color = "purple", n = 4. keep_count = ceil(4/2) = 2.
        kept = ["Volterra", "Asinalunga"]
        r = dispatch(s, {"action": "end_grow", "side": "ghibelline", "args": {"keep": kept}})
        assert sorted(r["state_changes"]["grow_kept"]) == sorted(kept)
        assert sorted(r["state_changes"]["grow_removed"]) == sorted(["Cortona", "Montepulciano"])


class TestRansom:
    def test_no_captures_auto_advance(self):
        s = _to_end_campaign("A", seed=1)
        dispatch(s, {"action": "end_grow_skip", "side": "guelph"})
        dispatch(s, {"action": "end_grow_skip", "side": "ghibelline"})
        # No captures recorded
        dispatch(s, {"action": "end_ransom", "side": "guelph", "args": {"pay": True}})
        dispatch(s, {"action": "end_ransom", "side": "ghibelline", "args": {"pay": True}})
        assert "ransom" in s["meta"]["end_substep_done"]


class TestGameCheck:
    def test_game_end_on_last_turn(self):
        # Scenario A: end_box = 3, so last Turn is 2. Place turn at 2.
        s = _to_end_campaign("A", seed=1, turn_override=2)
        dispatch(s, {"action": "end_grow", "side": "guelph", "args": {"keep": []}})
        dispatch(s, {"action": "end_grow", "side": "ghibelline", "args": {"keep": []}})
        dispatch(s, {"action": "end_ransom", "side": "guelph", "args": {"pay": True}})
        dispatch(s, {"action": "end_ransom", "side": "ghibelline", "args": {"pay": True}})
        # Game-end check triggers Victory since 2 >= end_box(3)-1 = 2
        dispatch(s, {"action": "end_game_check", "side": "guelph"})
        assert s["meta"]["phase"] == "victory"


def test_final_scoring_requires_both_grow_and_ransom_elections():
    state = _to_end_campaign("A", turn_override=2)
    gold = ["Prato", "Empoli", "Cortona"]
    purple = ["Volterra", "Asinalunga", "Montalcino", "Montepulciano"]
    for color, names in (("gold", gold), ("purple", purple)):
        for name in names:
            state["locales"][name]["ravaged"] = color
    state["vp"] = _init_vp_from_markers(state)
    assert state["vp"] == {"guelph": 6, "ghibelline": 5.5}

    def act(name, **args):
        return dispatch(state, {"action": name, "side": state["meta"]["active_player"],
                                "args": args})

    def reject(name, code):
        before = deepcopy(state)
        with pytest.raises(IllegalAction) as error:
            act(name)
        assert error.value.code == code
        assert state == before

    for name in ("end_game_check", "end_ransom", "end_repair", "end_waste", "end_reset"):
        reject(name, "WRONG_STEP")
    for keep in (gold[1:], purple[2:]):
        menu = enumerate_legal_validated(state)
        assert not menu["dropped"]
        assert "end_grow_skip" not in {m["action"] for m in menu["moves"]}
        reject("end_grow_skip", "GROW_REQUIRED")
        assert act("end_grow", keep=keep)["state_changes"]["grow_kept"] == keep

    reject("end_grow", "WRONG_STEP")
    reject("end_game_check", "WRONG_STEP")
    act("end_ransom")
    reject("end_game_check", "WRONG_STEP")
    act("end_ransom")
    assert act("end_game_check")["state_changes"] == {
        "game_ended": True, "winner": None, "vp_g": 5, "vp_h": 5,
    }


def test_final_scoring_waits_for_saved_languish_revolt(tmp_path):
    state = _to_end_campaign("A", seed=2, turn_override=2)
    for side in ("guelph", "ghibelline"):
        dispatch(state, {"action": "end_grow_skip", "side": side})
    state["lords"]["siena"]["forces"]["Cavalieri"] -= 1
    state.setdefault("captured_knights", {})["ghibelline"] = {"Cavalieri": 1}
    dispatch(state, {"action": "end_ransom", "side": "guelph"})
    dispatch(state, {"action": "end_ransom", "side": "ghibelline", "args": {"pay": False}})

    save = tmp_path / "languish.json"
    save.write_text(json.dumps(state), encoding="utf-8")
    restored = load_saved_state(save)
    check = {"action": "end_game_check", "side": "guelph"}
    resolutions = (
        {"action": "cmd_resolve_revolt", "side": "guelph", "args": {"choice": "Asinalunga"}},
        {"action": "cmd_resolve_exiles", "side": "ghibelline",
         "args": {"slides": [{"lord_id": "siena", "kind": "service"}]}},
        {"action": "cmd_resolve_exiles", "side": "ghibelline", "args": {"slides": []}},
    )
    for candidate in (state, restored):
        assert "ransom" in candidate["meta"]["end_substep_done"]
        for resolution in resolutions:
            before = deepcopy(candidate)
            with pytest.raises(IllegalAction) as error:
                dispatch(candidate, check)
            assert error.value.code == "PENDING_DECISION"
            assert candidate == before
            menu = enumerate_legal_validated(candidate)["moves"]
            assert {move["action"] for move in menu} == {resolution["action"]}
            dispatch(candidate, resolution)
        assert dispatch(candidate, check)["state_changes"]["game_ended"]
    assert restored == state


@pytest.mark.parametrize("scenario,turn,n", [("A", 2, 1), ("B", 5, 2)])
def test_grow_skip_preserves_single_marker_and_reprisal_war(scenario, turn, n):
    state = _to_end_campaign(scenario, turn_override=turn)
    markers = ["Prato", "Empoli"][:n]
    for loc in markers:
        state["locales"][loc]["ravaged"] = "gold"
    state["vp"] = _init_vp_from_markers(state)
    before = dict(state["vp"])
    menu = enumerate_legal_validated(state)
    assert any(m["action"] == "end_grow_skip" for m in menu["moves"])
    dispatch(state, {"action": "end_grow_skip", "side": "guelph"})
    assert state["meta"]["active_player"] == "ghibelline"
    assert state["vp"] == before
    assert all(state["locales"][loc]["ravaged"] == "gold" for loc in markers)


class TestRepair:
    def test_repair_removes_one_from_3_4_marker_town_or_city(self):
        s = _to_end_campaign("A", seed=1)
        # Plant a 4-marker Siege at Volterra (Town)
        s["locales"]["Volterra"]["siege"] = [
            {"side": "guelph", "color": "purple", "count": 4}
        ]
        # Walk through Grow/Ransom skips
        dispatch(s, {"action": "end_grow_skip", "side": "guelph"})
        dispatch(s, {"action": "end_grow_skip", "side": "ghibelline"})
        dispatch(s, {"action": "end_ransom", "side": "guelph", "args": {"pay": True}})
        dispatch(s, {"action": "end_ransom", "side": "ghibelline", "args": {"pay": True}})
        dispatch(s, {"action": "end_game_check", "side": "guelph"})
        # Now Repair (not per-side)
        r = dispatch(s, {"action": "end_repair", "side": "guelph"})
        # Volterra was 4 markers -> reduced to 3
        new_total = sum(s_["count"] for s_ in s["locales"]["Volterra"]["siege"])
        assert new_total == 3
        assert "Volterra" in r["state_changes"]["repaired"]

    def test_repair_skips_castle(self):
        s = _to_end_campaign("A", seed=1)
        # Plant a 4-marker Siege at Vicopisano (Castle)
        s["locales"]["Vicopisano"]["siege"] = [
            {"side": "guelph", "color": "purple", "count": 4}
        ]
        dispatch(s, {"action": "end_grow_skip", "side": "guelph"})
        dispatch(s, {"action": "end_grow_skip", "side": "ghibelline"})
        dispatch(s, {"action": "end_ransom", "side": "guelph", "args": {"pay": True}})
        dispatch(s, {"action": "end_ransom", "side": "ghibelline", "args": {"pay": True}})
        dispatch(s, {"action": "end_game_check", "side": "guelph"})
        r = dispatch(s, {"action": "end_repair", "side": "guelph"})
        # Castle does NOT erode
        new_total = sum(s_["count"] for s_ in s["locales"]["Vicopisano"]["siege"])
        assert new_total == 4
        assert "Vicopisano" not in r["state_changes"]["repaired"]


def _to_waste():
    state = _to_end_campaign("A", seed=1)
    for action in ("end_grow_skip", "end_ransom"):
        for side in ("guelph", "ghibelline"):
            dispatch(state, {"action": action, "side": side})
    for action in ("end_game_check", "end_repair"):
        dispatch(state, {"action": action, "side": "guelph"})
    return state


@pytest.mark.parametrize("choice", [
    {},
    None,
    "Cart",
    {"discard": "Cart"},
    {"asset": "Cart", "capability": "F13"},
    {"asset": []},
    {"asset": "Ship"},
    {"capability": "F13"},
])
def test_waste_rejects_malformed_or_unowned_choice_atomically(choice):
    state = _to_waste()
    before = deepcopy(state)
    # Arezzo precedes Firenze in Waste order and would otherwise lose a Cart.
    with pytest.raises(IllegalAction) as exc:
        dispatch(state, {"action": "end_waste", "side": "guelph", "args": {
            "discards": {"arezzo": {"asset": "Cart"}, "firenze": choice},
        }})
    assert exc.value.code == "BAD_DISCARD"
    assert state == before


@pytest.mark.parametrize("discards", [None, [], {"siena": {"asset": "Cart"}}])
def test_waste_requires_a_mapping_of_eligible_lords(discards):
    state = _to_waste()
    before = deepcopy(state)
    with pytest.raises(IllegalAction) as exc:
        dispatch(state, {"action": "end_waste", "side": "guelph", "args": {"discards": discards}})
    assert exc.value.code == "BAD_DISCARD"
    assert state == before


def test_waste_rejects_empty_versioned_selection_after_reload(tmp_path):
    state = _to_waste()
    save = tmp_path / "waste.json"
    save.write_text(json.dumps(state), encoding="utf-8")

    for position in (state, load_saved_state(save)):
        before = deepcopy(position)
        view = PlayerView(position, "guelph")
        entry = next(row for row in view.query({"request": "actions"})["records"]
                     if row["move"]["action"] == "end_waste")
        selection = {"action_id": entry["action_id"], "state_version": view.version}
        with pytest.raises(IllegalAction) as exc:
            selection_session(position, "guelph", {
                **selection, "args": {"discards": {"arezzo": {}, "firenze": {}}},
            })
        assert exc.value.code == "BAD_DISCARD"
        assert position == before

        # The same selection can now spend a singleton Coin and default Firenze's Cart.
        result = selection_session(position, "guelph", {
            **selection, "args": {"discards": {"arezzo": {"asset": "Coin"}}},
        })
        assert result["status"] == "accepted"
        assert position["lords"]["arezzo"]["assets"]["Coin"] == 0
        assert position["lords"]["firenze"]["assets"]["Cart"] == 1
        assert position["meta"]["active_player"] == "ghibelline"


def test_waste_can_discard_a_single_personal_capability():
    from tests.test_cross_game_sally import give_card

    state = _to_waste()
    firenze = state["lords"]["firenze"]
    assert not firenze["capabilities"]
    give_card(state, "F13", firenze["capabilities"])
    assets = dict(firenze["assets"])
    result = dispatch(state, {"action": "end_waste", "side": "guelph", "args": {
        "discards": {"firenze": {"capability": "F13"}},
    }})
    assert {"lord_id": "firenze", "discarded_capability": "F13"} in result["state_changes"]["waste"]
    assert firenze["assets"] == assets and not firenze["capabilities"]
    assert "F13" in state["decks"]["guelph"]["aow_deck"]


class TestReset:
    def test_reset_advances_calendar_and_re_enters_levy(self):
        s = _to_end_campaign("A", seed=1)
        # Walk through skip-everything to Reset
        dispatch(s, {"action": "end_grow_skip", "side": "guelph"})
        dispatch(s, {"action": "end_grow_skip", "side": "ghibelline"})
        dispatch(s, {"action": "end_ransom", "side": "guelph", "args": {"pay": True}})
        dispatch(s, {"action": "end_ransom", "side": "ghibelline", "args": {"pay": True}})
        dispatch(s, {"action": "end_game_check", "side": "guelph"})
        dispatch(s, {"action": "end_repair", "side": "guelph"})
        dispatch(s, {"action": "end_waste", "side": "guelph"})
        dispatch(s, {"action": "end_waste", "side": "ghibelline"})
        before = s["meta"]["turn"]
        dispatch(s, {"action": "end_reset", "side": "guelph"})
        assert s["meta"]["turn"] == before
        assert s["meta"]["active_player"] == "ghibelline"
        dispatch(s, {"action": "end_reset", "side": "ghibelline"})
        # Scenario A ends at box 3 -> Reset from turn 1 -> turn 2 (still pre-end)
        # turn 2 < end_box 3 so Levy resumes.
        if before == 1 and s["calendar"].get("end_box") == 3:
            assert s["meta"]["turn"] == 2
            assert s["meta"]["phase"] == "levy"
