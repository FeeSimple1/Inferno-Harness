"""Fourth-audit regressions through public combat and Held Event actions."""

from __future__ import annotations

import pytest

from inferno import actions
from inferno.card_data import AOW_CARDS_BY_ID
from inferno.invariants import check_all_invariants
from inferno.legal_moves import enumerate_legal
from inferno.llm.interface import DecisionView, play_with_interface
from tests.test_cross_game_escape import place
from tests.test_cross_game_sally import give_card, position, sally
from tests.test_phase3c import _to_command_with


def play_event(state, card, target=None):
    side = "guelph" if card.startswith("F") else "ghibelline"
    caps = state["capabilities_in_play"]
    caps[:] = [cap for cap in caps if cap["id"] != card]
    give_card(state, card, state["decks"][side]["aow_held"])
    action = next(move for move in enumerate_legal(state)
                  if move["action"] == "play_event" and move["args"]["card_id"] == card
                  and move["args"].get("effect_args", {}).get("target_lord_id") == target)
    actions.dispatch(state, action)
    assert card not in state["decks"][side]["aow_held"]
    check_all_invariants(state)


def approach(attacker="firenze", defender="siena", *, coins=4, seed=5, archery="Arcieri",
             relief=False):
    state = _to_command_with("A", seed=1, lord_id=attacker, lord_location_override="Firenze")
    for lid, locale, amount in ((attacker, "Firenze", 6), (defender, "Figline", coins)):
        lord = place(state, lid, locale, Coin=amount, Provender=6, Cart=3)
        lord["forces"] = {"Cavalieri": 2, "Armigieri": 2, "Militia": 2}
        lord["capabilities"] = []
    defender_mat = state["lords"][defender]
    if archery:
        prefix = "F" if defender == "firenze" else "S"
        card = next(card for card, data in AOW_CARDS_BY_ID.items()
                    if card.startswith(prefix) and data.get("capability_name") == archery)
        give_card(state, card, defender_mat["capabilities"])
    if relief:
        rear = place(state, "arezzo", "Figline", Provender=4)
        rear["forces"] = {"Cavalieri": 2}
        rear["flags"]["in_stronghold"] = True
        state["locales"]["Figline"]["siege"] = [
            {"side": "ghibelline", "color": "gold", "count": 1},
        ]
    state["meta"].update(rng_seed=seed, rng_advance=0)
    actions.dispatch(state, {"action": "cmd_march", "side": state["lords"][attacker]["side"],
                             "args": {"lord_id": attacker, "destination": "Figline",
                                      "way_type": "road"}})
    assert state["pending"][0]["type"] == "approach_response"
    check_all_invariants(state)
    return state


def stand(state, defender="siena", **kwargs):
    result = actions.dispatch(state, {
        "action": "approach_response", "side": state["lords"][defender]["side"],
        "args": {"lord_id": defender, "choice": "stand",
                 "scripted_decisions": [
                     {"type": "concede", "side": "attacker", "choice": "yes"},
                 ], **kwargs},
    })
    assert not state.get("battle_modifiers_pending")
    check_all_invariants(state)
    return result["state_changes"]["battle_result"]


@pytest.mark.parametrize(("attacker", "defender", "card"), [
    ("firenze", "siena", "S6"), ("siena", "firenze", "F6"),
])
def test_held_hills_doubles_defending_archery(attacker, defender, card):
    state = approach(attacker, defender)
    play_event(state, card)
    log = stand(state, defender)["rounds"][0]["hit_log"]
    assert log[0] == {"step": "def_archery", "hills_doubled": True}
    assert [row["lord_id"] for row in log[1:5]] == [attacker] * 4
    assert all(not row["crossbow"] for row in log[1:5])


def test_hills_bonus_hits_are_bowmen_even_when_original_hits_are_crossbows():
    state = approach(archery="Balestrieri")
    play_event(state, "S6")
    log = stand(state)["rounds"][0]["hit_log"]
    assert log[0]["hills_doubled"]
    assert [row["crossbow"] for row in log[1:5]] == [True, True, False, False]


@pytest.mark.parametrize(("attacker", "defender", "card"), [
    ("firenze", "siena", "S8"), ("siena", "firenze", "F8"),
])
def test_held_swamp_stops_only_the_attacking_horse(attacker, defender, card):
    state = approach(attacker, defender)
    play_event(state, card)
    log = stand(state, defender)["rounds"][0]["hit_log"]
    skipped = [row for row in log if row.get("skipped")]
    assert skipped == [{"step": "atk_horse_melee", "skipped": "swamp_horse_no_strike_r1"}]


def test_held_sudden_clash_opens_with_both_named_lords_in_defender_first_order():
    state = approach()
    play_event(state, "F4", "firenze")
    play_event(state, "S4", "siena")
    log = stand(state)["rounds"][0]["hit_log"]
    # Each early strike selects a valuable Cavalieri at its full Armor.
    assert [row["unit"] for row in log if "unit" in row][:2] == ["Cavalieri", "Cavalieri"]
    assert log[0]["lord_id"] == "firenze" and not log[0]["crossbow"]
    assert [(row["side"], row["sudden_clash"]) for row in log if "sudden_clash" in row] == [
        ("defender", "siena"), ("attacker", "firenze"),
    ]


def test_defending_swamp_prevents_attacking_sudden_clash():
    state = approach()
    play_event(state, "F4", "firenze")
    play_event(state, "S8")
    log = stand(state)["rounds"][0]["hit_log"]
    assert {"step": "atk_horse_melee", "skipped": "swamp_horse_no_strike_r1"} in log
    assert not any("sudden_clash" in row for row in log)


def test_relief_sally_named_horse_strikes_once_before_archery():
    state = approach(relief=True)
    play_event(state, "F4", "arezzo")
    result = stand(state)
    log = result["rounds"][0]["hit_log"]
    assert log[0]["lord_id"] == "siena" and log[0]["unit"] == "Cavalieri"
    assert log[1] == {"sudden_clash": "arezzo", "side": "attacker"}
    assert sum(r["context"].startswith("relief_siegeworks_Figline_arezzo")
               for r in result["rolls"]) == 1


def test_sallying_sudden_clash_strikes_before_the_besiegers():
    state = position(seed=5)
    play_event(state, "S4", "siena")
    log = sally(state, "attacker")["rounds"][0]["hit_log"]
    assert log[0]["lord_id"] == "firenze"
    assert log[1] == {"sudden_clash": "siena", "side": "attacker"}
    assert not state.get("battle_modifiers_pending")


def test_camp_attack_uses_the_asset_cap_and_reports_the_overflow_in_battle():
    state = approach(coins=16)
    play_event(state, "S12")
    event, = stand(state)["pre_modifiers"]["camp_attack"]
    assert event["taken"] == event["removed"] == {"Coin": 2}
    assert event["allocation"] == {"distributed": {}, "lost_to_cap": {"Coin": 2}}
    assert state["lords"]["siena"]["assets"]["Coin"] == 16
    assert state["lords"]["firenze"]["assets"]["Coin"] == 2


def test_camp_attack_in_sally_distributes_to_a_mat_with_room():
    state = position()
    state["lords"]["siena"]["assets"]["Coin"] = 16
    place(state, "pisa", "Siena", Provender=3)["flags"]["in_stronghold"] = True
    play_event(state, "S12")
    event, = sally(state, "attacker")["pre_modifiers"]["camp_attack"]
    assert event["taken"] == event["removed"] == {"Coin": 2}
    assert event["allocation"] == {"distributed": {"pisa": {"Coin": 2}}, "lost_to_cap": {}}
    assert state["lords"]["siena"]["assets"]["Coin"] == 16
    assert state["lords"]["firenze"]["assets"]["Coin"] == 0
    assert not state.get("battle_modifiers_pending")


def flanking_approach():
    state = _to_command_with("A", seed=1, lord_id="firenze")
    for lid, locale, forces, coin in (
            ("firenze", "Firenze", {"Militia": 1}, 0),
            ("arezzo", "Firenze", {"Cavalieri": 1}, 0),
            ("siena", "Figline", {"Cavalieri": 1}, 2)):
        lord = place(state, lid, locale, Coin=coin, Provender=4, Cart=2)
        lord["forces"] = forces
        state["decks"][lord["side"]]["aow_deck"].extend(lord["capabilities"])
        lord["capabilities"] = []
    state["meta"].update(rng_seed=1, rng_advance=0)
    actions.dispatch(state, {"action": "cmd_march", "side": "guelph", "args": {
        "lord_id": "firenze", "destination": "Figline", "way_type": "road",
        "with_lords": ["arezzo"]}})
    check_all_invariants(state)
    return state


def stand_with_player_choices(state, decide):
    def choose(view):
        if isinstance(view, DecisionView):
            rows = view.query({"request": "actions"})["records"]
            options = [row["move"]["args"]["choice"] for row in rows]
            value = decide(view, view.overview(), options)
            row = rows[options.index(value)]
        elif view.can_yield:
            return {"yield": True, "state_version": view.version}
        else:
            rows = view.query({"request": "actions", "category": "approach_response"})["records"]
            row = next(r for r in rows if r["move"]["args"].get("choice") == "stand")
        return {"action_id": row["action_id"], "state_version": view.version}

    result = play_with_interface(state, choose).applied["state_changes"]["battle_result"]
    check_all_invariants(state)
    return result


@pytest.mark.parametrize("absorber", ["firenze", "arezzo"])
def test_flanking_lord_can_absorb_the_opposed_lords_hits(absorber):
    state = flanking_approach()
    elections = []

    def decide(view, overview, options):
        kind = overview["decision"]
        if kind == "concede":
            return "yes" if view.side == "ghibelline" else "no"
        if kind == "flanker_absorb":
            assert view.side == "guelph"
            assert options == ["firenze", "arezzo"]
            assert overview["context"]["striking_lords"] == ["siena"]
            elections.append(kind)
            return absorber
        return options[0]

    result = stand_with_player_choices(state, decide)
    hit = result["rounds"][0]["hit_log"][0]
    assert elections == ["flanker_absorb"]
    assert hit["lord_id"] == absorber and hit["die"] == 2
    assert hit["survived"] == (absorber == "arezzo")


def test_two_striking_lords_prevent_flanking_absorption():
    from inferno.battle import BattleDecisionContext, _resolve_step
    from inferno.rng import HarnessRNG

    state = flanking_approach()
    place(state, "pisa", "Figline")["forces"] = {"Cavalieri": 1}
    positions = {"attacker": {"left": "arezzo", "center": "firenze", "right": None},
                 "defender": {"left": None, "center": "siena", "right": "pisa"}}
    elections = []

    def choose(decision):
        elections.append(decision["type"])
        return decision["options"][0]

    bdc = BattleDecisionContext(callback=choose)
    log = []
    _resolve_step(state, "def_horse_melee", positions, {}, "defender",
                  bdc, HarnessRNG(seed=1).roll, log, set(), {})
    assert log[0]["lord_id"] == "firenze"
    assert "flanker_absorb" not in elections


def test_camp_attack_owner_can_wait_take_carts_and_concentrate_spoils():
    state = flanking_approach()
    play_event(state, "F12")
    timing = []
    choices = []

    def decide(view, overview, options):
        kind = overview["decision"]
        context = overview["context"]
        if kind == "concede":
            assert overview["participating_mats"]["siena"]["assets"]["Cart"] == 2
            return "yes" if view.side == "ghibelline" else "no"
        if kind == "camp_attack_timing":
            assert view.side == "guelph"
            timing.append(context["after"])
            if context["after"] == "def_horse_melee":
                assert context["hits"][0]["die"] == 2
                return "now"
            return "wait"
        if kind in {"camp_attack_take", "camp_attack_remove"}:
            assert view.side == "guelph" and context["enemy"] == "siena"
            choices.append(kind)
            return "Cart" if kind == "camp_attack_take" else "Provender"
        if kind == "spoils_recipient" and context["asset"] == "Cart":
            assert view.side == "guelph"
            return "arezzo"
        if kind == "spoils_amount":
            return max(options)
        if kind == "flanker_absorb":
            return "arezzo"
        return options[0]

    result = stand_with_player_choices(state, decide)
    assert timing == ["concede", "def_archery", "atk_archery", "def_horse_melee"]
    assert choices == ["camp_attack_take"] * 2 + ["camp_attack_remove"] * 2
    event, = result["pre_modifiers"]["camp_attack"]
    assert event["after"] == "def_horse_melee"
    assert event["taken"] == {"Cart": 2} and event["removed"] == {"Provender": 2}
    assert event["allocation"]["distributed"] == {"arezzo": {"Cart": 2}}
    assert not state.get("battle_modifiers_pending")


def test_camp_attack_default_ignores_asset_dict_insertion_order():
    from copy import deepcopy

    state = flanking_approach()
    play_event(state, "F12")
    alternate = deepcopy(state)
    assets = alternate["lords"]["siena"]["assets"]
    alternate["lords"]["siena"]["assets"] = dict(reversed(list(assets.items())))
    assert alternate == state
    script = [{"type": "initial_placement_attacker", "choice": "left"},
              {"type": "initial_placement_attacker", "choice": "arezzo"},
              {"type": "concede", "choice": "yes"}]
    first = stand(state, scripted_decisions=script)
    second = stand(alternate, scripted_decisions=deepcopy(script))
    assert first["pre_modifiers"] == second["pre_modifiers"]
    assert state == alternate


def test_waiting_camp_attack_can_follow_the_opponents_event_before_the_first_strike():
    state = flanking_approach()
    play_event(state, "F12")
    play_event(state, "S12")
    timing = []

    def decide(view, overview, options):
        kind = overview["decision"]
        if kind == "concede":
            return "yes"
        if kind == "camp_attack_timing":
            assert overview["context"]["hits"] == []
            timing.append((view.side, overview["context"]["after"]))
            if len(timing) == 1:
                return "wait"
            if view.side == "guelph":
                assert overview["participating_mats"]["siena"]["assets"]["Provender"] == 8
            return "now"
        return options[0]

    result = stand_with_player_choices(state, decide)
    assert timing == [("guelph", "concede"), ("ghibelline", "concede"), ("guelph", "concede")]
    assert [event["enemy"] for event in result["pre_modifiers"]["camp_attack"]] == [
        "firenze", "arezzo", "siena"]


def test_bocca_in_sally_rolls_each_cavalieri_and_transfers_one_routed_knight():
    state = position(seed=5)
    play_event(state, "S16", "firenze")
    result = sally(state, "attacker")
    assert result["pre_modifiers"]["bocca"] == {"target": "firenze", "routed_cavs": 1}
    assert result["rolls"][:2] == [
        {"context": "bocca_firenze_Cavalieri", "value": 5},
        {"context": "bocca_firenze_Cavalieri", "value": 3},
    ]
    assert result["loss_results"]["siena"]["captured"] == {"Cavalieri": 1}
    assert state["lords"]["siena"]["forces"]["Cavalieri"] == 2
    assert not state.get("battle_modifiers_pending")


@pytest.mark.parametrize(("doctors", "survives"), [(True, True), (False, False)])
def test_storm_doctors_can_restore_the_last_force(doctors, survives):
    state = _to_command_with("A", seed=1, lord_id="firenze", lord_location_override="Volterra")
    firenze = place(state, "firenze", "Volterra", Coin=1, Provender=4)
    firenze.update(forces={"Armigieri": 1}, capabilities=[])
    state["locales"]["Volterra"]["siege"] = [{"side": "guelph", "color": "purple", "count": 1}]
    state["meta"].update(rng_seed=2, rng_advance=0)
    if doctors:
        play_event(state, "F24")
    result = actions.dispatch(state, {"action": "cmd_storm", "side": "guelph",
                                      "args": {"lord_id": "firenze"}})
    storm = result["state_changes"]["storm_result"]
    assert storm["outcome"] == "attacker_loss"
    assert (state["lords"]["firenze"]["status"] == "mustered") == survives
    if survives:
        assert storm["doctors"][0]["restored_for"] == {"firenze": ["Armigieri"]}
        assert state["lords"]["firenze"]["forces"] == {"Armigieri": 1}
        assert state["locales"]["Volterra"]["siege"][0]["count"] == 1
    assert not state.get("battle_modifiers_pending")
    check_all_invariants(state)
