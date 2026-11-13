"""Round 21 regressions at the versioned player and action boundaries."""
from collections import Counter
from copy import deepcopy
import json

import pytest

from inferno import actions as A
from inferno.cli import main as cli_main
from inferno.invariants import check_all_invariants
from inferno.legal_moves import enumerate_legal
from inferno.llm.filter import hide_for_side
from inferno.llm.interface import PlayerView
from inferno.llm.menu import submit_selection
from inferno.scenarios import _init_vp_from_markers, load_scenario
from inferno.state import load_saved_state
from tests._helpers import _finish_pending_choices, _place
from tests.test_phase3a import _skip_capability_discard
from tests.test_phase3e import _to_end_campaign


def _next_levy(scenario, seed):
    state = _to_end_campaign(scenario, seed=seed)
    while state["meta"]["phase"] == "campaign":
        _finish_pending_choices(state)
        A.dispatch(state, enumerate_legal(state)[0])
    assert state["meta"]["levy_step"] == "3.1"
    check_all_invariants(state)
    return state


def _actions(view, category):
    return view.query({"request": "actions", "category": category, "page_size": 100})["records"]


def _selection(view, category, **args):
    entry = next(row for row in _actions(view, category)
                 if all(row["move"]["args"].get(key) == value for key, value in args.items()))
    return {"state_version": view.version, "action_id": entry["action_id"]}


def _apply(state, category, **args):
    view = PlayerView(state)
    return submit_selection(state, view.side, _selection(view, category, **args))


def _event(state, card, **effect):
    return _apply(state, "levy_resolve_event", card_id=card, effect_args=effect)


def _reject_event(state, card, effect, code="EVENT_UNRESOLVED"):
    before = deepcopy(state)
    with pytest.raises(A.IllegalAction) as err:
        A.dispatch(state, {"action": "levy_resolve_event", "side": state["meta"]["active_player"],
                           "args": {"card_id": card, "effect_args": effect}})
    assert err.value.code == code
    assert state == before


def _saved(state, tmp_path):
    source, dest = tmp_path / "source.json", tmp_path / "saved.json"
    source.write_text(json.dumps(state))
    assert cli_main(["save", str(source), str(dest)]) == 0
    loaded = load_saved_state(dest)
    assert state == loaded
    return loaded


def test_genova_waits_before_primo_popolo_and_each_choice_is_executable():
    state = _next_levy("D", 0)
    before = deepcopy(state["lords"])
    result = _apply(state, "levy_aow_draw")
    assert result["state_changes"]["drew"] == ["F9", "<unrevealed>"]
    assert all(roll["context"] != "aow_draw_index" for roll in result.get("rolls", []))
    assert hide_for_side(state, "guelph")["history"][-1]["state_changes"]["drew"] == ["F9", "<unrevealed>"]
    assert state["aow_resolution"]["remaining"][0]["card_id"] == "F21"
    assert state["lords"] == before
    view = PlayerView(state)
    other = deepcopy(state)
    other["decks"]["guelph"]["aow_deck"].remove("F7")
    other["decks"]["guelph"]["aow_deck"].append("F21")
    other["aow_resolution"]["remaining"][0]["card_id"] = "F7"
    other["history"][-1]["state_changes"]["drew"][-1] = "F7"
    assert view.version == PlayerView(other).version
    old_selection = _selection(view, "levy_resolve_event", effect_args={"mode": "shift"})
    _event(state, "F9", mode="treachery", treachery_card="treachery_colle")
    assert "treachery_colle" in state["decks"]["guelph"]["command_deck"]
    hidden = hide_for_side(state, "ghibelline")
    assert "treachery_colle" not in json.dumps(hidden["decks"]["guelph"])
    assert "treachery_colle" not in json.dumps(hidden["history"][-1])
    snapshot = deepcopy(state)
    with pytest.raises(A.IllegalAction, match="STALE_VIEW"):
        submit_selection(state, "guelph", old_selection)
    assert state == snapshot
    _reject_event(state, "F21", {"mode": "treachery", "treachery_card": "treachery_lucca"})
    _reject_event(state, "F21", {"mode": "shift"})
    _event(state, "F21", mode="shift", target="arezzo")
    _event(snapshot, "F21", mode="treachery", treachery_card="treachery_arezzo")
    assert state["lords"]["arezzo"]["service_box"] == before["arezzo"]["service_box"] + 2
    assert state["lords"]["firenze"] == before["firenze"]
    assert "treachery_arezzo" in snapshot["decks"]["guelph"]["command_deck"]
    for branch in (state, snapshot):
        assert not branch.get("aow_resolution")
        assert branch["meta"]["active_player"] == "ghibelline"
        assert branch["decks"]["guelph"]["aow_discard"].count("F21") == 1
        check_all_invariants(branch)


@pytest.mark.parametrize("count", [0, 1, 2])
def test_closed_gates_choice_survives_sorted_save(count, tmp_path):
    state = _next_levy("D", 20)
    sites = ["Monte San Savino", "Castelnuovo Berardenga"]
    for name in sites[count:]:
        state["locales"][name]["ruins"] = None
    state["vp"] = _init_vp_from_markers(state)
    loaded = _saved(state, tmp_path)
    assert _apply(state, "levy_aow_draw") == _apply(loaded, "levy_aow_draw")
    assert state == loaded
    if count == 2:
        view, restored_view = PlayerView(state), PlayerView(loaded)
        choices = _actions(view, "levy_resolve_event")
        assert choices == _actions(restored_view, "levy_resolve_event")
        assert {row["move"]["args"]["effect_args"]["locale"] for row in choices} == set(sites)
        assert all(state["locales"][name]["ruins"] == "gold" for name in sites)
        _reject_event(state, "F10", {"locale": "Arezzo"})
        loaded = _saved(state, tmp_path)
        assert choices == _actions(PlayerView(loaded), "levy_resolve_event")
        assert _event(state, "F10", locale=sites[0]) == _event(loaded, "F10", locale=sites[0])
        assert state["locales"][sites[1]]["ruins"] == "gold"
    assert state == loaded
    assert state["locales"][sites[0]]["ruins"] is None
    assert state["decks"]["guelph"]["aow_discard"].count("F10") == 1
    check_all_invariants(state)


def test_betrayals_waits_for_revolt_and_exiles_before_next_choice(tmp_path):
    state = _next_levy("D", 15)
    # Stage prior travel and Sieges, preserving native Forces and Assets.
    for lid, name in (("arezzo", "Volterra"), ("colle", "Asinalunga")):
        _place(state, lid, name)
        state["locales"][name]["siege"] = [{"side": "guelph", "color": "purple", "count": 1}]
    _apply(state, "levy_aow_draw")
    assert state["pending"][0]["remaining_choices"] == 2
    assert state["aow_resolution"]["remaining"][0]["card_id"] == "F22"
    _reject_event(state, "F2", {})
    result = _event(state, "F2", mode="revolt")
    assert len(result["rolls"]) == 2
    assert result["state_changes"]["remaining_choices"] == 1
    assert state["pending_revolts"][0]["decision"]["candidates"] == ["Rocca Sillana", "Rosignano"]
    treachery = {"mode": "treachery", "treachery_card": "treachery_arezzo"}
    _reject_event(state, "F2", treachery, "PENDING_DECISION")
    saved = _saved(state, tmp_path)
    for branch in (state, saved):
        _apply(branch, "cmd_resolve_revolt", choice="Rocca Sillana")
        assert branch["pending_exiles"][0]["side"] == "ghibelline"
        _reject_event(branch, "F2", treachery, "PENDING_DECISION")
        _apply(branch, "cmd_resolve_exiles", slides=[{"lord_id": "astimberg", "kind": "service"}])
        assert branch["pending"][0]["card_id"] == "F2"
        assert "F2" not in branch["decks"]["guelph"]["aow_discard"]
        result = _event(branch, "F2", **treachery)
        assert not result.get("rolls")
        assert branch["decks"]["guelph"]["command_deck"].count("treachery_arezzo") == 1
        assert branch["decks"]["guelph"]["aow_discard"].count("F2") == 1
        assert branch["pending"][0]["card_id"] == "F22"
        check_all_invariants(branch)
    assert state == saved


def _ghibelline_draw(seed):
    state = _next_levy("D", seed)
    _apply(state, "levy_aow_draw")
    _finish_pending_choices(state)
    return state


def test_ghibelline_betrayals_hides_the_following_hold_until_the_choice():
    state = _ghibelline_draw(6)
    draw = _apply(state, "levy_aow_draw")
    assert draw["state_changes"]["drew"] == ["S2", "<unrevealed>"]
    assert state["pending"][0]["remaining_choices"] == 1
    _event(state, "S2", mode="treachery", treachery_card="treachery_santa_fiora")
    deck = state["decks"]["ghibelline"]
    assert "treachery_santa_fiora" in deck["command_deck"]
    assert deck["aow_discard"].count("S2") == deck["aow_held"].count("S7") == 1
    assert not state.get("aow_resolution")
    check_all_invariants(state)


def test_ghibelline_closed_gates_offers_denial_sites_before_revolt():
    state = _ghibelline_draw(14)
    sites = ("Vicopisano", "Pontedera")
    for name in sites:
        state["locales"][name]["ruins"] = "purple"
    state["vp"] = _init_vp_from_markers(state)
    _apply(state, "levy_aow_draw")
    choices = _actions(PlayerView(state), "levy_resolve_event")
    assert {row["move"]["args"]["effect_args"]["locale"] for row in choices} == set(sites)
    _reject_event(state, "S22", {"locale": "Castelnuovo Berardenga"})
    before = state["vp"]["guelph"]
    _event(state, "S22", locale=sites[1])
    assert state["locales"][sites[0]]["ruins"] == "purple"
    assert state["locales"][sites[1]]["ruins"] is None
    assert state["vp"]["guelph"] == before - 0.5
    assert not state.get("pending_exiles")
    check_all_invariants(state)


def test_closed_gates_exiles_receipt_keeps_the_next_hold_private():
    state = _ghibelline_draw(14)
    A._maybe_reshuffle_aow_deck(state, "ghibelline")
    deck = state["decks"]["ghibelline"]["aow_deck"]
    # Replace the second card of the draw with a Hold for this fixture.
    i, j = deck.index("S23"), deck.index("S7")
    deck[i], deck[j] = deck[j], deck[i]
    _apply(state, "levy_aow_draw")
    assert state["pending_exiles"][0]["side"] == "guelph"
    assert state["aow_resolution"]["remaining"][0]["card_id"] == "S7"
    result = _apply(state, "cmd_resolve_exiles", slides=[])
    assert "S7" not in json.dumps(result)
    assert "S7" not in json.dumps(hide_for_side(state, "guelph")["history"][-1])
    assert state["decks"]["ghibelline"]["aow_held"].count("S7") == 1
    check_all_invariants(state)


def test_paid_death_accepts_either_order_for_the_same_two_lords():
    state = _ghibelline_draw(10)
    _apply(state, "levy_aow_draw")
    normal = deepcopy(state)
    _event(normal, "S10", mode="shift", targets=["giordano", "astimberg"])
    A.dispatch(state, {"action": "levy_resolve_event", "side": "ghibelline",
                       "args": {"card_id": "S10", "effect_args": {
                           "mode": "shift", "targets": ["astimberg", "giordano"]}}})
    assert state["lords"] == normal["lords"]
    assert state["decks"] == normal["decks"]
    check_all_invariants(state)


def test_manfredi_shifts_native_printed_ritter_cylinder(tmp_path):
    state = _next_levy("F", 15)
    draw = _apply(state, "levy_aow_draw")["state_changes"]
    assert draw["deployment"][0]["effect"]["no_sieges"]
    assert state["lords"]["astimberg"]["forces"] == {}
    shifts = _actions(PlayerView(state), "levy_resolve_event")
    assert {row["move"]["args"]["effect_args"]["target_lord_id"] for row in shifts} >= {
        "astimberg", "giordano"}
    _reject_event(state, "F22", {"target_lord_id": "siena", "mode": "shift"})
    loaded = _saved(state, tmp_path)
    shift = {"target_lord_id": "astimberg", "mode": "shift"}
    assert _event(state, "F22", **shift) == _event(loaded, "F22", **shift)
    assert state == loaded
    assert state["lords"]["astimberg"]["calendar_box"] == 8
    check_all_invariants(state)


def test_manfredi_hidden_mats_advertise_one_conditional_template():
    state = _next_levy("D", 15)
    # Stage an acquired Ritter on each side. Only the Ghibelline mat qualifies.
    state["meta"]["hidden_mats"] = True
    state["lords"]["arezzo"]["forces"]["Ritter"] = 1
    state["lords"]["provenzano"]["forces"]["Ritter"] = 1
    _apply(state, "levy_aow_draw")
    _reject_event(state, "F22", {"target_lord_id": "arezzo", "mode": "shift"})
    other = deepcopy(state)
    other["lords"]["provenzano"]["forces"].pop("Ritter")
    view, other_view = PlayerView(state), PlayerView(other)
    assert view.version == other_view.version
    choices = _actions(view, "levy_resolve_event")
    assert choices == _actions(other_view, "levy_resolve_event")
    template, = [row for row in choices if row["parameterized"]]
    before = state["lords"]["provenzano"]["assets"]["Cart"]
    choice = {"card_id": "F22", "effect_args": {"target_lord_id": "provenzano",
              "mode": "remove_assets", "assets_to_remove": {"Cart": 1}}}
    selection = {"state_version": view.version, "action_id": template["action_id"], "args": choice}
    _reject_event(other, "F22", choice["effect_args"])
    submit_selection(state, "guelph", selection)
    assert state["lords"]["provenzano"]["assets"]["Cart"] == before - 1
    check_all_invariants(state)


def test_manfredi_advances_an_off_left_cylinder_into_box_one():
    state = _next_levy("F", 15)
    A._place_cylinder(state, "astimberg", None)
    state["calendar"]["off_left"].append("astimberg")
    _apply(state, "levy_aow_draw")
    _event(state, "F22", mode="shift", target_lord_id="astimberg")
    assert state["lords"]["astimberg"]["calendar_box"] == 1
    assert "astimberg" not in state["calendar"]["off_left"]
    check_all_invariants(state)


def test_manfredi_hidden_no_effect_requires_verification():
    state = _next_levy("D", 15)
    state["meta"]["hidden_mats"] = True
    for lord in state["lords"].values():
        if lord["side"] == "ghibelline":
            lord["forces"].pop("Ritter", None)
    other = deepcopy(state)
    other["lords"]["astimberg"]["forces"]["Ritter"] = 1
    assert _apply(state, "levy_aow_draw") == _apply(other, "levy_aow_draw")
    assert _actions(PlayerView(state), "levy_resolve_event") == _actions(
        PlayerView(other), "levy_resolve_event")
    _reject_event(other, "F22", {})
    assert not _event(state, "F22")["state_changes"]["effect"]["applied"]
    assert state["decks"]["guelph"]["aow_discard"].count("F22") == 1
    check_all_invariants(state)


def _bribe_position(seed, muster=True):
    state = load_scenario("D", seed, advanced_vassal_service=True)
    for name in ("levy_aow_draw", "levy_pay_done", "levy_disband_done", "levy_muster_done"):
        for side in ("guelph", "ghibelline"):
            if name == "levy_muster_done" and side == "ghibelline" and muster:
                _apply(state, "levy_muster_vassal", lord_id="astimberg", vassal="Berchtold von Arras")
            A.dispatch(state, {"action": name, "side": side})
    for side in ("guelph", "ghibelline"):
        A.dispatch(state, {"action": "levy_cta_skip", "side": side})
    _skip_capability_discard(state)
    # Stage earlier travel and Treachery acquisition. Reveal through the Plan.
    _place(state, "arezzo", "Montalcino")
    deck = state["decks"]["guelph"]
    deck["treachery_set_aside"].remove("treachery_arezzo")
    deck["command_deck"].append("treachery_arezzo")
    for side in ("guelph", "ghibelline"):
        cards = ["treachery_arezzo"] + ["PASS"] * 5 if side == "guelph" else ["PASS"] * 6
        for card in cards:
            A.dispatch(state, {"action": "plan_add_card", "side": side, "args": {"card_id": card}})
        A.dispatch(state, {"action": "plan_done", "side": side})
    _apply(state, "command_reveal")
    check_all_invariants(state)
    return state


@pytest.mark.parametrize("seed,losses", [(1, None), (1, {"Ritter": 1, "Militia": 1, "Cavalieri": 1}),
                                        (1, {"Militia": 1}), (2, None)])
def test_mustered_bribe_conserves_surviving_forces(seed, losses, tmp_path):
    state = _bribe_position(seed)
    if losses is not None:
        state["lords"]["astimberg"]["forces"] = dict(losses)
    before = deepcopy(state["lords"])
    loaded = _saved(state, tmp_path)
    args = {"target_lord_id": "astimberg", "vassal": "Berchtold von Arras"}
    result = _apply(state, "cmd_treachery_bribe", **args)
    assert result == _apply(loaded, "cmd_treachery_bribe", **args)
    assert state == loaded
    effect = result["state_changes"]["treachery_bribe"]
    donor, receiver = (state["lords"][lid] for lid in ("astimberg", "arezzo"))
    total_before = Counter(before["astimberg"]["forces"]) + Counter(before["arezzo"]["forces"])
    assert Counter(donor["forces"]) + Counter(receiver["forces"]) == total_before
    if seed == 2:
        assert effect["die"] == 2 and not effect["success"]
        assert effect["forces_transferred"] == {}
        assert donor == before["astimberg"]
        assert receiver["assets"] == before["arezzo"]["assets"]
    else:
        transferred = {"Ritter": 1, "Men-at-Arms": 1, "Militia": 1}
        if losses is not None:
            transferred = {unit: count for unit, count in transferred.items() if unit in losses}
        assert effect["die"] == 6 and effect["success"]
        assert effect["forces_transferred"] == transferred
        assert Counter(receiver["forces"]) == Counter(before["arezzo"]["forces"]) + Counter(transferred)
        assert receiver["assets"]["Coin"] == before["arezzo"]["assets"]["Coin"] - 1
        marker, = [v for lord in state["lords"].values() for v in lord["vassals"]
                   if v["name"] == args["vassal"]]
        assert marker in receiver["vassals"] and marker["turncoat"] and not marker["ready"]
        assert marker["service_box"] is None
        if losses == {"Militia": 1}:
            assert effect["disbanded"] == "astimberg"
            assert donor["status"] == "on_calendar" and donor["location"] is None
            assert donor["calendar_box"] == state["calendar"]["levy_box"] + donor["ratings"]["S"] + 1
            assert not state.get("pending_revolts")
        else:
            assert effect["disbanded"] is None and donor["status"] == "mustered"
    check_all_invariants(state)


@pytest.mark.parametrize("parent_mustered", [True, False])
def test_seat_bribe_preserves_pool_forces_and_turncoat_availability(parent_mustered):
    state = _bribe_position(3, muster=False)
    name = "Berchtold von Arras"
    _place(state, "arezzo", "Siena")
    donor = state["lords"]["astimberg"]
    if not parent_mustered:
        A._disband_at_service_limit(state, "astimberg", state["calendar"]["levy_box"])
    before = deepcopy(state["lords"])
    result = _apply(state, "cmd_treachery_bribe", target_lord_id="astimberg", vassal=name)
    effect = result["state_changes"]["treachery_bribe"]
    path = "B_mustered_parent" if parent_mustered else "B_unmustered_parent"
    assert effect["path"] == path and effect["success"]
    assert donor["forces"] == before["astimberg"]["forces"]
    receiver = state["lords"]["arezzo"]
    added = Counter({"Ritter": 1, "Men-at-Arms": 1, "Militia": 1})
    assert Counter(receiver["forces"]) == Counter(before["arezzo"]["forces"]) + added
    assert all(v["name"] != name for v in donor["vassals"])
    if not parent_mustered:
        # Bring Astimberg's cylinder forward for a legal Levy re-Muster.
        _finish_pending_choices(state)
        state["meta"].update(phase="levy", levy_step="3.4", active_player="ghibelline")
        A._place_cylinder(state, "astimberg", state["calendar"]["levy_box"])
        _place(state, "arezzo", "Montalcino")
        result = _apply(state, "levy_muster_lord", muster_lord_id="giordano",
                        target_lord_id="astimberg", target_seat="Siena")
        assert result["state_changes"]["success"]
        assert all(v["name"] != name for v in donor["vassals"])
    A._disband_at_service_limit(state, "arezzo", state["calendar"]["levy_box"])
    returned, = [v for v in donor["vassals"] if v["name"] == name]
    assert returned["ready"] and not returned.get("turncoat") and returned["service_box"] is None
    check_all_invariants(state)
