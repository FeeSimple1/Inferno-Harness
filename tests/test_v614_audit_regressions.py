"""Regression coverage for the 2026-10-09 Inferno audit (rules cited per test).

The fixtures deliberately set up minimal, explicit rule situations instead of
relying on whichever cards a particular random seed used to draw.
"""
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
import json
import sys

import pytest

from inferno import actions as A, battle as B, card_effects as CE, card_data as CD
from inferno import static_data as SD
from inferno.scenarios import load_scenario
from inferno.legal_moves import enumerate_legal
from inferno.rng import HarnessRNG, DieRoll
from inferno.llm.player import safe_fallback_for, play_with_callback
from inferno.llm.filter import hide_for_side
from inferno.llm.briefing import build_briefing
from tests._helpers import _place


def muster(s, lid, loc, service=12, forces=None):
    A._place_cylinder(s, lid, None)
    _place(s, lid, loc, forces=forces if forces is not None else {"Cavalieri": 2, "Armigieri": 2})
    A._place_service(s, lid, service)
    s["lords"][lid]["assets"] = {"Coin": 4, "Provender": 4, "Cart": 4}
    return s["lords"][lid]


def command(lid="firenze", loc="Firenze", turn=9):
    s = load_scenario("D", seed=11)
    s["meta"].update(phase="campaign", campaign_step="command_phase", levy_step=None,
                     active_player="guelph", turn=turn)
    muster(s, "firenze", "Firenze")
    muster(s, "siena", "Siena")
    if lid != "firenze" or loc != "Firenze":
        muster(s, lid, loc)
    s["meta"]["active_player"] = s["lords"][lid]["side"]
    s.update(current_card="command_" + lid, current_lord_id=lid, actions_remaining=2)
    return s


def levy(step="3.4"):
    s = command()
    s["meta"].update(phase="levy", levy_step=step, campaign_step=None)
    s.update(current_card=None, current_lord_id=None, actions_remaining=None)
    return s


def apply(s, name, args=None, side=None):
    return A.dispatch(s, {"action": name, "side": side or s["meta"]["active_player"],
                          "args": args or {}})


def rejected_unchanged(s, name, args=None, side=None):
    before = deepcopy(s)
    with pytest.raises(A.IllegalAction) as err:
        apply(s, name, args, side)
    assert s == before
    return err.value.code


def fixed_die(value):
    return lambda context: DieRoll(context=context, value=value)


def test_initial_draw_reaches_entire_deck_and_is_repeatable():
    """3.1.1-3: every one of 26 cards is reachable, not only sorted d6 slots."""
    seen = set()
    for seed in range(100):
        s = load_scenario("D", seed=seed)
        other = deepcopy(s)
        result = apply(s, "levy_aow_draw")
        assert apply(other, "levy_aow_draw") == result
        assert other == s
        seen.update(result["state_changes"]["drew"])
    assert seen == {c["id"] for c in CD.GUELPH_CARDS}


def test_index_rejection_sampling_and_replay(monkeypatch):
    """Reject excess base-six digits, rather than biasing the first positions."""
    rng = HarnessRNG(1)
    digits = iter([6, 6, 5, 2])  # 35 rejected for size 26, then index 25.
    monkeypatch.setattr(rng, "roll", lambda ctx: DieRoll(context=ctx, value=next(digits)))
    assert rng.randbelow(26, "index") == 25
    rng = HarnessRNG(1)
    for _ in range(20):
        rng.randbelow(26, "index")
    resumed = HarnessRNG(1, advance=rng.advance_count)
    assert [rng.roll("next").value for _ in range(20)] == [resumed.roll("next").value for _ in range(20)]


@pytest.mark.parametrize("name,args", [([], {}), ({}, {}), (None, {}), (7, {}),
                                      ("cmd_pass", []), ("cmd_pass", [1]),
                                      ("cmd_pass", "oops"), ("cmd_pass", None)])
def test_bad_json_field_types_are_atomic_illegal_actions(name, args):
    """Action envelope failures must enter the retry path, not throw TypeError."""
    s = command()
    before = deepcopy(s)
    with pytest.raises(A.IllegalAction):
        A.dispatch(s, {"action": name, "side": "guelph", "args": args})
    assert s == before
    result = play_with_callback(s, lambda *_: {"action": name, "side": "guelph", "args": args})
    assert result.fallback is not None
    assert len(result.rejected) == 3
    assert result.applied


def test_rejected_pay_restores_coin_and_service():
    """3.2: no Service marker to move -> no payment, history, or RNG changes."""
    s = levy("3.2")
    A._place_service(s, "firenze", None)
    assert rejected_unchanged(s, "levy_pay", {"from_lord_id": "firenze"}) == "SHIFT_OFF_CAL"


def test_rejected_capability_restores_card_lordship_and_rng():
    """3.4.4: validation errors after random selection are transactional."""
    s = levy()
    s["decks"]["guelph"]["aow_deck"] = ["F6"]
    assert rejected_unchanged(s, "levy_muster_capability", {"lord_id": "firenze", "scope": "side_wide"}) == "CAPABILITY_SCOPE"
    s["lords"]["firenze"]["capabilities"] = ["F3", "F8"]
    assert rejected_unchanged(s, "levy_muster_capability", {"lord_id": "firenze"}) == "THIS_LORD_LIMIT"


def test_f6_default_levy_is_single_lord_and_not_hills():
    s = levy()
    s["decks"]["guelph"]["aow_deck"] = ["F6"]
    apply(s, "levy_muster_capability", {"lord_id": "firenze"})
    assert s["lords"]["firenze"]["capabilities"] == ["F6"]
    assert B._lord_has_capability(s, "firenze", "Feditori")
    assert not B._lord_has_capability(s, "arezzo", "Feditori")
    assert not any(c["id"] == "F6" for c in s["capabilities_in_play"])


@pytest.mark.parametrize("side,prefix", [("guelph", "F"), ("ghibelline", "S")])
@pytest.mark.parametrize("number", range(1, 27))
def test_capability_scope_uses_printed_bottom_half(side, prefix, number):
    """Arts of War: all copies of a named Capability use the same mat scope."""
    expected = number in (set(range(2, 12)) | set(range(13, 21)))
    assert A._capability_is_this_lord(f"{prefix}{number}") is expected


def test_service_paid_off_right_is_not_expired():
    s = levy("3.2")
    A._place_service(s, "firenze", 16)
    apply(s, "levy_pay", {"from_lord_id": "firenze"})
    assert s["lords"]["firenze"]["service_box"] is None
    assert "firenze" in s["calendar"]["off_right_service"]
    A._fpd_run_disband(s, {"disband": []})
    assert s["lords"]["firenze"]["status"] == "mustered"


@pytest.mark.parametrize("asset,payer", [("Loot", "firenze"), ("Coin", "arezzo"), ("Loot", "arezzo")])
def test_fpd_offers_loot_and_colocated_payer_before_disband(asset, payer):
    """4.8.2 / 3.2: the complete Pay opportunity precedes Service expiry."""
    s = command()
    muster(s, "arezzo", "Firenze")
    for lord in s["lords"].values():
        lord["assets"]["Coin"] = lord["assets"]["Loot"] = 0
    A._place_service(s, "firenze", s["meta"]["turn"])
    s["lords"][payer]["assets"][asset] = 2
    A._run_fpd(s)
    assert s.get("pending_fpd")
    pays = [m for m in enumerate_legal(s) if m["action"] == "cmd_fpd_pay"
            and m["args"]["from_lord_id"] == payer and m["args"]["target_lord_id"] == "firenze"
            and m["args"]["asset"] == asset]
    assert pays
    A.dispatch(s, pays[0])
    while s.get("pending_fpd"):
        apply(s, "cmd_fpd_pay_done", side=s["pending_fpd"]["side"])
    assert s["lords"]["firenze"]["status"] == "mustered"
    assert s["lords"]["firenze"]["service_box"] == s["meta"]["turn"] + 1


def test_hidden_plan_is_removed_from_history_and_briefing():
    s = command()
    s["meta"]["campaign_step"] = "plan"
    s.update(current_card=None, current_lord_id=None, actions_remaining=None)
    apply(s, "plan_add_card", {"card_id": "command_firenze"})
    before = deepcopy(s)
    assert "command_firenze" in json.dumps(hide_for_side(s, "guelph")["history"])
    assert "command_firenze" not in json.dumps(hide_for_side(s, "ghibelline")["history"])
    assert "command_firenze" not in build_briefing(s, "ghibelline", max_chars=100000)
    assert "rng_seed" not in hide_for_side(s, "ghibelline")["meta"]
    assert s == before


def test_fallback_finishes_four_card_plan_instead_of_overfilling():
    s = command(turn=1)
    s["meta"]["campaign_step"] = "plan"
    s.update(current_card=None, current_lord_id=None, actions_remaining=None)
    for _ in range(4):
        fb = safe_fallback_for(s)
        assert fb["args"]["card_id"] == "PASS"
        A.dispatch(s, fb)
    assert rejected_unchanged(s, "plan_add_card", {"card_id": "PASS"}) == "PLAN_FULL"
    fb = safe_fallback_for(s)
    assert fb["action"] == "plan_done"
    A.dispatch(s, fb)
    assert len(s["plan_stacks"]["guelph"]) == 4
    assert s["meta"]["active_player"] == "ghibelline"


def test_reveal_cannot_replace_active_lord_or_skip_pay():
    s = command()
    s["plan_stacks"]["guelph"] = ["command_arezzo"]
    assert rejected_unchanged(s, "command_reveal") == "CARD_IN_PROGRESS"
    apply(s, "cmd_end_card")
    assert s.get("pending_fpd")
    assert rejected_unchanged(s, "command_reveal") == "PENDING_DECISION"


def test_f22_draw_waits_for_choice_and_does_not_consume_next_event():
    s = levy("3.1")
    s["meta"].update(first_levy_aow_drawn=True, aow_reshuffled_this_levy_guelph=True)
    s["decks"]["guelph"]["aow_deck"] = ["F22"]
    muster(s, "giordano", "Siena", forces={"Ritter": 1})
    apply(s, "levy_aow_draw")
    assert s["meta"]["active_player"] == "guelph"
    assert s["pending"][0]["card_id"] == "F22"
    assert "F22" not in s["decks"]["guelph"]["aow_discard"]
    rejected_unchanged(s, "levy_resolve_event", {"card_id": "F22"})
    rejected_unchanged(s, "levy_aow_draw")
    choices = [m for m in enumerate_legal(s) if m["action"] == "levy_resolve_event"]
    assert choices
    move = next(m for m in choices if m["args"]["effect_args"] == {"target_lord_id": "giordano", "mode": "shift"})
    A.dispatch(s, move)
    assert s["lords"]["giordano"]["service_box"] == 11
    assert s["decks"]["guelph"]["aow_discard"].count("F22") == 1
    assert not s.get("aow_resolution")
    assert s["meta"]["active_player"] == "ghibelline"


def test_incomplete_greek_fire_does_not_consume_or_partly_apply_event():
    s = command()
    muster(s, "siena", "Firenze", forces={"Armigieri": 2})
    s["locales"]["Firenze"]["siege"] = [{"side": "ghibelline", "color": "gold", "count": 3}]
    s["decks"]["guelph"]["aow_held"].append("F7")
    for args in ({}, {"enemy_lord_id": "siena"}, {"enemy_lord_id": "siena", "unit_to_remove": "Ritter"}):
        rejected_unchanged(s, "play_event", {"card_id": "F7", "effect_args": args})
    apply(s, "play_event", {"card_id": "F7", "effect_args": {"enemy_lord_id": "siena", "unit_to_remove": "Armigieri"}})
    assert s["lords"]["siena"]["forces"]["Armigieri"] == 1
    assert "F7" not in s["decks"]["guelph"]["aow_held"]


@pytest.mark.parametrize("cid,lid", [("F9", "firenze"), ("F13", "firenze"), ("F13", "lucca")])
def test_f9_f13_shift_mustered_service_instead_of_missing_cylinder(cid, lid):
    s = command()
    muster(s, lid, "Firenze", service=16)
    if cid == "F9":
        s["locales"]["Pisa"]["siege"] = []
    before = s["lords"][lid]["service_box"]
    CE.apply_event_effect(s, cid, "guelph", {}, HarnessRNG(1))
    assert before == 16
    assert s["lords"][lid]["service_box"] is None
    assert lid in s["calendar"]["off_right_service"]


@pytest.mark.parametrize("count", [-8, -1, 0])
def test_pass_cannot_create_actions(count):
    s = command()
    rejected_unchanged(s, "cmd_pass", {"count": count})


def test_entire_card_tax_rejected_after_forage_in_menu_and_handler():
    s = command()
    apply(s, "cmd_forage")
    assert s["actions_remaining"] == 1
    rejected_unchanged(s, "cmd_tax")
    assert not any(m["action"] == "cmd_tax" for m in enumerate_legal(s))


def test_free_road_march_also_uses_part_of_entire_card():
    s = command()
    apply(s, "cmd_march", {"destination": "Figline", "way_type": "road"})
    assert s["actions_remaining"] == 2
    assert s["card_actions_started"] is True
    s["lords"]["firenze"]["seats"].append("Figline")
    rejected_unchanged(s, "cmd_tax")


def test_besieged_lord_cannot_take_even_free_road_march():
    s = command()
    s["lords"]["firenze"]["flags"]["in_stronghold"] = True
    s["locales"]["Firenze"]["siege"] = [{"side": "ghibelline", "count": 1, "color": "gold"}]
    rejected_unchanged(s, "cmd_march", {"destination": "Figline", "way_type": "road"})
    assert not any(m["action"] == "cmd_march" for m in enumerate_legal(s))


def test_group_march_requires_commander_or_own_lower_lord():
    s = command("arezzo", "Arezzo")
    muster(s, "firenze", "Arezzo")
    assert rejected_unchanged(s, "cmd_march", {"destination": "Bibbiena", "with_lords": ["firenze"]}) == "GROUP_AUTHORITY"
    # A valid Lieutenant pairing is legal; unrelated companions are not.
    s["lords"]["arezzo"]["flags"]["has_lower_lord"] = "firenze"
    s["lords"]["firenze"]["flags"]["lower_lord_of"] = "arezzo"
    apply(s, "cmd_march", {"destination": "Bibbiena", "with_lords": ["firenze"]})
    assert s["lords"]["firenze"]["location"] == "Bibbiena"


@pytest.mark.parametrize("source", ["Firenze", "Prato"])
def test_supply_rejects_enemy_at_source_including_zero_length_route(source):
    s = command()
    muster(s, "siena", source)
    assert rejected_unchanged(s, "cmd_supply", {"source": source}) == "NO_SUPPLY_ROUTE"
    s["locales"][source]["bypass"] = "guelph"
    apply(s, "cmd_supply", {"source": source, "provender": 1})


def test_supply_menu_includes_remote_source_and_shared_carts():
    s = command()
    muster(s, "arezzo", "Firenze")
    s["lords"]["firenze"]["assets"]["Cart"] = 0
    s["lords"]["arezzo"]["assets"]["Cart"] = 2
    candidates = [m for m in enumerate_legal(s) if m["action"] == "cmd_supply" and m["args"].get("source") == "Prato"]
    assert candidates
    for m in candidates:
        result = A.dispatch(deepcopy(s), m)
        assert result["state_changes"]["supply_added"] >= 1
    result = apply(s, "cmd_supply", {"source": "Prato", "provender": 2})
    assert result["state_changes"]["supply_added"] == 2


def test_storm_concession_has_no_extra_strikes(monkeypatch):
    s = command()
    s["locales"]["Siena"]["siege"] = [{"side": "guelph", "color": "purple", "count": 3}]
    calls = []
    monkeypatch.setattr(B, "_resolve_storm_step", lambda *args, **kwargs: calls.append(args[1]))
    result = B.resolve_storm(s, ["firenze"], ["siena"], "firenze", "Siena",
                             scripted_decisions=[{"type": "concede", "side": "attacker", "choice": "yes"}])
    assert len(calls) == len(B.STORM_STRIKE_ORDER)
    assert result["rounds_played"] == 1
    assert result["conceded"] == "attacker"


def test_six_hits_continue_after_one_villici_routs():
    s = command()
    s["lords"]["firenze"]["forces"] = {"Ritter": 3}
    s["lords"]["siena"]["forces"] = {"Villici": 1}
    s["lords"]["pisa"]["forces"] = {"Villici": 5}
    positions = {"attacker": {"left": None, "center": "firenze", "right": None},
                 "defender": {"left": "pisa", "center": "siena", "right": None}}
    removed, log = set(), []
    B._resolve_step(s, "atk_horse_melee", positions, {"attacker": [], "defender": []},
                    None, None, fixed_die(6), log, removed, {})
    assert removed == {"siena", "pisa"}
    assert sum(s["lords"]["pisa"]["forces"].values()) == 0
    assert len(log) == 6


def test_unused_hits_keep_crossbow_and_select_categories():
    s = command()
    s["lords"]["siena"]["forces"] = {"Villici": 1}
    remaining = B._absorb_hits(s, "siena", 6, fixed_die(6), [], {},
                               crossbow_hits=2, select_hits=1, crossbow_noselect_hits=2)
    assert remaining == {"n_hits": 5, "crossbow_hits": 1, "select_hits": 1, "crossbow_noselect_hits": 2}


@pytest.mark.parametrize("cid", ["F13", "F14", "F15", "S13", "S14", "S15"])
@pytest.mark.parametrize("roll,crossbow,routed_before,survives", [(3, False, 0, True), (4, False, 0, True),
        (5, False, 0, False), (2, True, 0, True), (3, True, 0, False), (3, False, 3, False)])
def test_palvesari_armor_and_third_rout_cutoff(cid, roll, crossbow, routed_before, survives):
    s = command()
    lid = "firenze" if cid[0] == "F" else "siena"
    s["lords"][lid].update(forces={"Armigieri": 1}, capabilities=[cid], routed_units={"Armigieri": routed_before})
    B._absorb_hits(s, lid, 1, fixed_die(roll), [], {}, crossbow_hits=int(crossbow))
    assert bool(s["lords"][lid]["forces"].get("Armigieri")) is survives
    assert SD.UNITS["Armigieri"]["protection"] == [1, 2]


def test_exiles_preserves_all_three_shifts_and_allows_edge():
    s = command()
    A._place_service(s, "firenze", 14)
    s["pending_exiles"] = [{"side": "guelph", "count": 3, "candidates": []}]
    for expected_remaining in (2, 1, 0):
        moves = enumerate_legal(s)
        move = next(m for m in moves if m["args"].get("slides") == [{"lord_id": "firenze", "kind": "service"}])
        result = A.dispatch(s, move)
        assert result["state_changes"]["remaining_shifts"] == expected_remaining
    assert "firenze" in s["calendar"]["off_right_service"]
    assert not s["pending_exiles"]


def test_exiles_cylinder_can_leave_box_one_and_bad_batch_is_atomic():
    s = command()
    A._place_cylinder(s, "lucca", 1)
    s["pending_exiles"] = [{"side": "guelph", "count": 3}]
    rejected_unchanged(s, "cmd_resolve_exiles", {"slides": [
        {"lord_id": "firenze", "kind": "service"}, {"lord_id": "siena", "kind": "service"}]})
    apply(s, "cmd_resolve_exiles", {"slides": [{"lord_id": "lucca", "kind": "cylinder"}]})
    assert "lucca" in s["calendar"]["off_left"]
    assert s["pending_exiles"][0]["count"] == 2
    apply(s, "cmd_resolve_exiles", {"slides": []})
    assert not s["pending_exiles"]


def test_claude_driver_uses_pending_pay_owner(monkeypatch):
    from inferno.llm import PlayerView
    captured = {}
    s = command()
    s["pending_fpd"] = {"step": "pay", "side": "ghibelline", "summary": {"feed": [], "disband": []}}
    view = PlayerView(s)
    entry = view.query({"request": "actions", "category": "cmd_fpd_pay_done"})["records"][0]
    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(
            {"action_id": entry["action_id"], "state_version": view.version}))])
    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=lambda: SimpleNamespace(messages=SimpleNamespace(create=create))))
    spec = spec_from_file_location("inferno_example_audit", Path(__file__).resolve().parents[1] / "examples/play_with_claude.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    callback = module.make_claude_callback("test-no-network")
    selection = callback(view)
    assert view.resolve(selection)["side"] == "ghibelline"
    assert "ghibelline" in captured["system"]
    overview = json.loads(captured["messages"][0]["content"])
    assert overview["perspective"] == overview["acting_player"] == "ghibelline"
    assert "Inferno — GHIBELLINE" in overview["briefing"]
    assert "legal_moves" not in overview


@pytest.mark.parametrize("box", [None, 10])
def test_moving_cylinder_clears_old_off_calendar_pool(box):
    s = command()
    A._place_cylinder(s, "provenzano", 1)
    CE._shift_cylinder_left(s, "provenzano")
    assert "provenzano" in s["calendar"]["off_left"]
    A._place_cylinder(s, "provenzano", box)
    assert "provenzano" not in s["calendar"]["off_left"]
    assert s["lords"]["provenzano"]["calendar_box"] == box


def test_capability_menu_restricted_map_edge_cards_roundtrip():
    s = levy()
    s["decks"]["guelph"]["aow_deck"] = ["F12", "F21"]
    for move in enumerate_legal(s):
        if move["action"] == "levy_muster_capability":
            assert move["args"]["lord_id"] in A._CAP_PLACEMENT_ELIGIBLE[move["args"]["card_id"]]
            A.dispatch(deepcopy(s), move)


def test_two_card_draw_pauses_and_survives_json_save_load(monkeypatch):
    """F22's choice precedes the next card; a saved pending queue resumes identically."""
    s = levy("3.1")
    s["meta"].update(first_levy_aow_drawn=True, aow_reshuffled_this_levy_guelph=True)
    s["decks"]["guelph"]["aow_deck"] = ["F22", "F7"]
    muster(s, "giordano", "Siena", forces={"Ritter": 1})
    monkeypatch.setattr(HarnessRNG, "randbelow", lambda self, size, context: 0)
    apply(s, "levy_aow_draw")
    assert s["aow_resolution"]["remaining"] == [{"card_id": "F7", "as_capability": False}]
    assert "F7" not in s["decks"]["guelph"]["aow_held"]
    restored = json.loads(json.dumps(s))
    choice = {"card_id": "F22", "effect_args": {"target_lord_id": "giordano", "mode": "shift"}}
    assert apply(s, "levy_resolve_event", choice) == apply(restored, "levy_resolve_event", choice)
    assert s == restored
    assert s["decks"]["guelph"]["aow_held"].count("F7") == 1
    assert not s.get("aow_resolution")


def test_draw_waits_for_exiles_before_next_card(monkeypatch):
    """Even Event consequences must resolve before the next queued Event."""
    s = levy("3.1")
    s["meta"].update(first_levy_aow_drawn=True, aow_reshuffled_this_levy_guelph=True)
    s["decks"]["guelph"]["aow_deck"] = ["F2", "F7"]
    monkeypatch.setattr(HarnessRNG, "randbelow", lambda self, size, context: 0)
    real_effect = CE.apply_event_effect
    def with_exiles(state, cid, side, args, rng):
        if cid == "F2":
            state.setdefault("pending_exiles", []).append({"side": "ghibelline", "count": 1})
            return {"applied": True}
        return real_effect(state, cid, side, args, rng)
    monkeypatch.setattr(CE, "apply_event_effect", with_exiles)
    apply(s, "levy_aow_draw")
    assert "F7" not in s["decks"]["guelph"]["aow_held"]
    rejected_unchanged(s, "levy_aow_draw")
    assert enumerate_legal(s)[0]["side"] == "ghibelline"
    apply(s, "cmd_resolve_exiles", {"slides": []}, "ghibelline")
    assert "F7" in s["decks"]["guelph"]["aow_held"]
    assert not s.get("aow_resolution")
    assert s["meta"]["active_player"] == "ghibelline"


def test_cardfx_fixture_moves_duration_event_instead_of_duplicating_it():
    """Scenario A seed 6 now reaches F5 as an Event: fixture must move that copy."""
    from cardfx_fuzz import _stage_battle
    from inferno.invariants import check_all_invariants
    s, _, _ = _stage_battle(6, "F5", "guelph")
    check_all_invariants(s)
    assert s["lords"]["firenze"]["capabilities"].count("F5") == 1
    assert all(e.get("id") != "F5" for events in s.get("active_events", {}).values() for e in events)


@pytest.mark.parametrize("actor", ["guelph", "ghibelline"])
def test_draw_continuation_history_does_not_expose_a_held_card(actor):
    s = command()
    s["decks"]["guelph"]["aow_held"] = ["F7"]
    s["history"] = [{"side": actor, "action": "cmd_resolve_exiles", "args": {},
                     "state_changes": {"exiles": {"applied_exiles": []},
                                       "aow_deployment": ["F7 -> Held (Greek Fire)"]}}]
    view = hide_for_side(s, "ghibelline")
    assert "F7" not in json.dumps(view["history"])
    assert "exiles" in view["history"][0]["state_changes"]
    assert s["history"][0]["state_changes"]["aow_deployment"]
