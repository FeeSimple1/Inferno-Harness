"""Round 8: immediate F16 recovery and Hit categories through Walls."""

from copy import deepcopy

import pytest

from inferno import battle
from inferno.invariants import check_all_invariants
from inferno.rng import HarnessRNG
from tests.test_cross_game_combat_events import play_event
from tests.test_cross_game_sally import give_card
from tests.test_round7_combat import _besiege, _dispatch, _put, _tactical


@pytest.mark.parametrize("hits", [1, 2])
@pytest.mark.parametrize("event", [False, True])
def test_bloody_red_stream_recovers_before_the_lord_leaves_the_array(hits, event):
    state = _tactical("firenze", "Firenze", seed=1)
    _put(state, "firenze", "Firenze", {"Cavalieri": 1})
    _put(state, "siena", "Figline", {"Men-at-Arms": hits})
    _dispatch(state, "cmd_march", "guelph", lord_id="firenze",
              destination="Figline", way_type="road")
    if event:
        play_event(state, "F16")

    def choose(decision):
        if decision["type"] == "concede":
            return "no"
        return decision["options"][0]

    state["battle_callback"] = choose
    result = _dispatch(state, "approach_response", "ghibelline", lord_id="siena",
                       choice="stand")["battle_result"]
    state.pop("battle_callback")
    check_all_invariants(state)
    assert not state["battle_modifiers_pending"]
    assert result["rolls"][:2] == [
        {"context": "protect_siena_Men-at-Arms", "value": 2},
        {"context": "protect_firenze_Cavalieri", "value": 5},
    ]
    recoveries = [r for r in result["rolls"] if r["context"].startswith("bloody_red_stream_")]
    front = result["rounds"][0]["positions"]["attacker"]["center"]
    if event:
        assert recoveries == [{"context": "bloody_red_stream_firenze_Cavalieri", "value": 1}]
        assert result["rolls"][2] == recoveries[0]
        assert front == "firenze"
        if hits == 2:
            assert result["rolls"][3] == {"context": "protect_firenze_Cavalieri", "value": 3}
    else:
        assert recoveries == []
        assert front is None


def _blood_state(forces, routed=None):
    return {
        "lords": {"firenze": {
            "side": "guelph", "forces": dict(forces),
            "routed_units": dict(routed or {}), "capabilities": ["F13"],
        }},
        "battle_modifiers_pending": [
            {"id": "F16", "side": "guelph", "effect": "bloody_red_stream_first_rout"},
        ],
    }


def test_bloody_red_stream_rolls_every_routed_unit_at_unmodified_protection():
    state = _blood_state({"Cavalieri": 1}, {"Men-at-Arms": 1, "Armigieri": 1})
    rng = HarnessRNG(8)
    log = []
    battle._absorb_hits(state, "firenze", 1, rng.roll, log, {}, crossbow_hits=1)
    lord = state["lords"]["firenze"]
    # Crossbow Armor 1 routes the Cavalieri on 2. Recovery uses inherent Armor:
    # the Man-at-Arms recovers on 3, Palvesari does not save the Armigieri on 4,
    # and the just-Routed Cavalieri recovers on 2.
    assert [r.value for r in rng.drain_log()] == [2, 3, 4, 2]
    assert lord["forces"] == {"Men-at-Arms": 1, "Cavalieri": 1}
    assert lord["routed_units"] == {"Armigieri": 1}
    assert log[-1]["bloody_red_stream_recovered"] == {"Men-at-Arms": 1, "Cavalieri": 1}
    assert not state["battle_modifiers_pending"]


@pytest.mark.parametrize("seed,remaining", [(5, 0), (20, 1)])
def test_bloody_red_stream_is_consumed_even_if_recovery_fails_or_the_lord_routs_again(seed, remaining):
    state = _blood_state({"Cavalieri": 1})
    rng = HarnessRNG(seed)
    left = battle._absorb_hits(state, "firenze", 2, rng.roll, [], {}, crossbow_hits=2)
    rolls = rng.drain_log()
    assert sum(r.context.startswith("bloody_red_stream_") for r in rolls) == 1
    assert not state["lords"]["firenze"]["forces"]
    assert not state["battle_modifiers_pending"]
    assert left["n_hits"] == left["crossbow_hits"] == remaining


@pytest.mark.parametrize("hits", [0, 1])
def test_bloody_red_stream_does_not_trigger_without_a_hit_causing_rout(hits):
    state = _blood_state({}, {"Cavalieri": 1})
    rng = HarnessRNG(1)
    battle._absorb_hits(state, "firenze", hits, rng.roll, [], {})
    assert rng.drain_log() == []
    assert state["battle_modifiers_pending"]


def test_bloody_red_stream_can_recover_prior_routs_when_the_last_villici_is_removed():
    state = _blood_state({"Villici": 1}, {"Cavalieri": 1})
    rng = HarnessRNG(1)
    battle._absorb_hits(state, "firenze", 1, rng.roll, [], {})
    assert [(r.context, r.value) for r in rng.drain_log()] == [
        ("bloody_red_stream_firenze_Cavalieri", 2),
    ]
    assert state["lords"]["firenze"]["forces"] == {"Cavalieri": 1}
    assert state["lords"]["firenze"]["routed_units"] == {}


def test_storm_walls_cancels_the_crossbow_without_relabeling_the_normal_survivor():
    state = _tactical("firenze", "Volterra", seed=13)
    _put(state, "firenze", "Volterra", {"Cavalieri": 3, "Men-at-Arms": 1, "Militia": 1})
    _besiege(state, "Volterra", "guelph", 1)
    give_card(state, "F8", state["lords"]["firenze"]["capabilities"])
    give_card(state, "F16", state["lords"]["firenze"]["capabilities"])
    control = deepcopy(state)
    result = _dispatch(state, "cmd_storm", "guelph", lord_id="firenze")["storm_result"]
    replay = _dispatch(control, "cmd_storm", "guelph", lord_id="firenze")["storm_result"]
    check_all_invariants(state)
    assert result == replay and state == control
    garrison = next(h for h in result["rounds"][0]["hit_log"] if "garrison_unit" in h)
    assert garrison["garrison_unit"] == "Armigieri"
    assert garrison["die"] == 2 and garrison["survived"]
    assert garrison["protection"] == [1, 2] and not garrison["crossbow"]
    walls = [r for r in result["rolls"] if r["context"].startswith("walls_Volterra_")]
    assert walls[:2] == [
        {"context": "walls_Volterra_crossbow_0", "value": 2},
        {"context": "walls_Volterra_0", "value": 6},
    ]


@pytest.mark.parametrize("mode,selecting", [
    ("sally", False), ("sally", True), ("relief", False), ("relief", True),
    ("storm_attack", False), ("storm_attack", True), ("storm_defense", True),
])
@pytest.mark.parametrize("seed,crossbow_survives", [(1, False), (5, True)])
def test_walls_preserves_armor_and_chooser_for_each_surviving_hit(mode, selecting, seed, crossbow_survives):
    state = _tactical("firenze", "Volterra", seed=seed)
    _put(state, "firenze", "Volterra", {"Armigieri": 1, "Militia": 1},
         inside=mode != "storm_attack")
    _put(state, "siena", "Volterra", {"Cavalieri": 1, "Men-at-Arms": 1},
         inside=mode == "storm_attack")
    for card in ["F9", "F16"] + (["F13"] if selecting and mode != "storm_defense" else []):
        give_card(state, card, state["lords"]["firenze"]["capabilities"])
    positions = {
        "attacker": {"left": None, "center": "firenze", "right": None},
        "defender": {"left": None, "center": "siena", "right": None},
    }
    reserve = {"attacker": [], "defender": []}
    rng = HarnessRNG(seed)
    elections = []

    def choose(decision):
        elections.append(decision)
        return decision["options"][0]

    bdc = battle.BattleDecisionContext(callback=choose)
    log, removed, routed = [], set(), {}
    walls = [1, 2, 3, 4]
    if mode == "sally":
        battle._resolve_step(state, "atk_archery", positions, reserve, None, bdc,
                             rng.roll, log, removed, routed,
                             walls_by_side={"defender": walls}, locale_name="Volterra")
    elif mode == "relief":
        positions["attacker"]["center"] = positions["defender"]["center"] = None
        reserve["defender"] = ["siena"]
        battle._resolve_relief_substep(
            state, "atk_archery", ["firenze"], [], positions, reserve, None, bdc,
            rng.roll, log, removed, routed, 1, walls, "Volterra", "ghibelline")
    else:
        state["storm_garrison"] = {}
        defense = mode == "storm_defense"
        if defense:
            positions["attacker"]["center"], positions["defender"]["center"] = "siena", "firenze"
        battle._resolve_storm_step(
            state, "def_archery" if defense else "atk_archery", positions, reserve,
            None, bdc, rng.roll, log, removed, routed,
            "guelph" if defense else "ghibelline", None if defense else walls,
            walls if defense else None, "Volterra")
    check_all_invariants(state)
    # Seed 1 cancels the Crossbow (2) and leaves the Bow (5); seed 5 reverses
    # those outcomes (5, 3). The lone surviving Hit must retain its own flags.
    assert len(log) == 1
    assert log[0]["crossbow"] == crossbow_survives
    assert log[0]["protection"] == ([1] if crossbow_survives else [1, 2, 3])
    selected = crossbow_survives and selecting
    assert log[0]["unit"] == ("Cavalieri" if selected else "Men-at-Arms")
    assert [d["type"] for d in elections] == ["select_target_unit" if selected else "absorb_target"]
    assert elections[0]["side"] == ("guelph" if selected else "ghibelline")


def test_walls_keeps_selecting_and_nonselecting_crossbows_separate():
    rng = HarnessRNG(5)
    surviving = battle._apply_walls_to_hit_groups(3, 1, 1, [1, 2, 3, 4], rng.roll, "walls")
    # Selecting Crossbow survives on 5; non-selecting Crossbow cancels on 3;
    # normal Hit survives on 6. Neither survivor inherits the canceled flag.
    assert surviving == (2, 1, 0)
    assert [r.value for r in rng.drain_log()] == [5, 3, 6]
