"""Independent component expectations from Inferno_1.0.vmod + RoP 3.4.2.

See VASSAL_AUDIT.md for the source hash, artwork and module discrepancies.
"""
import copy
import json

import pytest

from inferno import actions as A, battle as B, static_data as sd, vassals as V
from inferno.scenarios import load_scenario, _init_vassals_for
from inferno.legal_moves import enumerate_legal
from inferno.llm.filter import hide_for_side


def muster_state(scenario="F", side="guelph", advanced=False):
    s = load_scenario(scenario, 1, advanced_vassal_service=advanced)
    s["meta"].update(phase="levy", levy_step="3.4", active_player=side)
    s["pending"] = []
    return s


def do(s, lid, name):
    return A.dispatch(s, {"action": "levy_muster_vassal", "side": s["lords"][lid]["side"],
                          "args": {"lord_id": lid, "vassal": name}})


def add_tau(s):
    s["decks"]["guelph"]["aow_deck"].remove("F22")
    s["capabilities_in_play"].append({"id": "F22", "name": "Tau Company",
                                         "side": "guelph", "scope": "side_wide"})


@pytest.mark.parametrize("step", ["atk_foot_melee", "def_foot_melee"])
def test_militia_half_melee_battle(step):
    # Printed Forces chart: three Militia cause 1.5, not 3, before rounding.
    assert B._strike_hits({"Militia": 3}, step) == 1.5


@pytest.mark.parametrize("step", ["atk_all_melee", "def_all_melee"])
def test_militia_half_melee_storm(step):
    assert B._strike_hits_storm({"Militia": 3}, step) == 1.5
    assert B._garrison_strike({"Militia": 3}, step) == 1.5


def test_militia_archery_is_unchanged():
    s = load_scenario("A", 1)
    assert B._garrison_strike({"Militia": 3}, "def_archery") == 3
    s["lords"]["firenze"]["capabilities"] = ["F16"]
    assert B._capability_strike_modifier(s, "firenze", {"Militia": 3}, "atk_archery", 1, "battle") == 3


def test_printed_ratings_and_muster_allowance():
    s = muster_state("E", "ghibelline")
    pisa = s["lords"]["pisa"]
    pisa.update(status="mustered", location="Pisa")
    s["locales"]["Pisa"]["lords_present"].append("pisa")
    assert pisa["ratings"] == {"F": 3, "S": 3, "L": 2, "C": 2}
    for _ in range(2):
        A.dispatch(s, {"action": "levy_muster_transport", "side": "ghibelline",
                       "args": {"lord_id": "pisa", "kind": "Cart"}})
    before = copy.deepcopy(s)
    with pytest.raises(A.IllegalAction):
        A.dispatch(s, {"action": "levy_muster_transport", "side": "ghibelline",
                       "args": {"lord_id": "pisa", "kind": "Cart"}})
    assert s == before
    assert s["lords"]["lucca"]["ratings"]["S"] == 3
    # Orvieto's printed mat overrides Vassal's stale internal Command=2.
    assert s["lords"]["orvieto"]["ratings"]["C"] == 3


def test_lucca_disband_return_uses_three_turns():
    s = load_scenario("E", 1)
    A._disband_beyond_service_limit(s, "lucca")
    assert s["lords"]["lucca"]["calendar_box"] == 15  # turn 12 + S3


def test_enemy_vassal_seat_rejects_without_mutation_or_menu_entry():
    s = muster_state()
    s["locales"]["Prato"]["current_allegiance"] = [{"side": "ghibelline", "value": 1}] * 2
    before = copy.deepcopy(s)
    with pytest.raises(A.IllegalAction, match="VASSAL_SEAT_NOT_FRIENDLY"):
        do(s, "firenze", "Prato Comune")
    assert s == before
    assert not any(m["action"] == "levy_muster_vassal" and m.get("args", {}).get("vassal") == "Prato Comune"
                   for m in enumerate_legal(s))


@pytest.mark.parametrize("marker,value", [("ruins", "gold"), ("ravaged", "gold"),
                                          ("siege", [{"side": "ghibelline", "count": 1}]),
                                          ("bypass", [{"side": "ghibelline"}])])
def test_friendly_seat_damage_and_siege_do_not_block_vassal(marker, value):
    s = muster_state()
    s["locales"]["Prato"][marker] = value
    do(s, "firenze", "Prato Comune")
    assert s["lords"]["firenze"]["forces"]["Militia"] == 1


def test_tau_free_discoverable_unique_and_replayable():
    s = muster_state(advanced=True)
    add_tau(s)
    s["lords"]["firenze"]["flags"]["lordship_used"] = 4
    moves = enumerate_legal(s)
    assert any(m.get("args", {}).get("vassal") == "Altopascio" for m in moves)
    do(s, "firenze", "Altopascio")
    lord = s["lords"]["firenze"]
    assert lord["forces"]["Cavalieri"] == 3
    assert lord["flags"]["lordship_used"] == 4
    v = next(v for v in lord["vassals"] if v["name"] == "Altopascio")
    assert v["service_box"] == 3
    assert not V.tau_available(s, "lucca")
    before = copy.deepcopy(s)
    with pytest.raises(A.IllegalAction):
        do(s, "firenze", "Altopascio")
    assert s == before
    loaded = json.loads(json.dumps(s))
    V.shift_service(s, "firenze", 1)
    V.shift_service(loaded, "firenze", 1)
    assert loaded == s


@pytest.mark.parametrize("condition", ["no_card", "enemy_seat", "wrong_lord"])
def test_tau_rejects_illegal_muster(condition):
    s = muster_state()
    if condition != "no_card":
        add_tau(s)
    if condition == "enemy_seat":
        s["locales"]["Altopascio"]["current_allegiance"] = [{"side": "ghibelline", "value": 1}] * 2
    before = copy.deepcopy(s)
    with pytest.raises(A.IllegalAction):
        do(s, "arezzo" if condition == "wrong_lord" else "firenze", "Altopascio")
    assert s == before


def test_tau_discard_disbands_only_remaining_tau_force():
    s = muster_state()
    add_tau(s)
    do(s, "firenze", "Altopascio")
    # Force a legitimate excess-capability discard window.
    s["capabilities_in_play"].extend({"id": c, "side": "guelph", "scope": "side_wide"}
                                     for c in ("F1", "F21"))
    s["meta"].update(phase="campaign", campaign_step="capability_discard")
    A.dispatch(s, {"action": "campaign_discard_capability", "side": "guelph", "args": {"card_id": "F22"}})
    assert s["lords"]["firenze"]["forces"]["Cavalieri"] == 2
    assert not any(v["name"] == "Altopascio" for v in s["lords"]["firenze"]["vassals"])


def test_advanced_muster_shift_expiry_and_ready_after_levy():
    s = muster_state(advanced=True)
    do(s, "firenze", "Prato Comune")
    v = next(v for v in s["lords"]["firenze"]["vassals"] if v["name"] == "Prato Comune")
    assert v["service_box"] == 3
    A._shift_service_right(s, "firenze", 1)
    assert v["service_box"] == 4
    from inferno.card_effects import _shift_service_left
    _shift_service_left(s, "firenze", 3)
    assert v["service_box"] == 1
    # Keep the Lord in service while the Vassal expires.
    A._place_service(s, "firenze", 6)
    s["meta"]["levy_step"] = "3.3"
    assert not any(m["action"] == "levy_disband_done" for m in enumerate_legal(s))
    before = copy.deepcopy(s)
    with pytest.raises(A.IllegalAction, match="VASSAL_DISBAND_REQUIRED"):
        A.dispatch(s, {"action": "levy_disband_done", "side": "guelph"})
    assert s == before
    A.dispatch(s, {"action": "levy_disband", "side": "guelph"})
    v = next(v for v in s["lords"]["firenze"]["vassals"] if v["name"] == "Prato Comune")
    assert v["service_box"] is None and not v["ready"] and not v["on_mat"]
    s["meta"]["levy_step"] = "3.4"
    with pytest.raises(A.IllegalAction, match="VASSAL_NOT_READY"):
        do(s, "firenze", "Prato Comune")
    from inferno.flow import advance_to_next_side_or_step
    s["meta"].update(levy_step="3.5", active_player="ghibelline")
    advance_to_next_side_or_step(s)
    assert next(v for v in s["lords"]["firenze"]["vassals"] if v["name"] == "Prato Comune")["ready"]


def test_advanced_campaign_expiry_and_zero_force_disband():
    s = muster_state(advanced=True)
    do(s, "firenze", "Prato Comune")
    lord = s["lords"]["firenze"]
    v = next(v for v in lord["vassals"] if v["name"] == "Prato Comune")
    v["service_box"] = 1
    lord["forces"] = {"Militia": 1}  # only a remaining Vassal unit
    A._place_service(s, "firenze", 6)
    s["meta"].update(phase="campaign", campaign_step="command_phase")
    result = {"disband": []}
    A._fpd_run_disband(s, result)
    assert ("firenze", "Prato Comune") in result["vassal_disbands"]
    assert lord["status"] != "mustered"
    assert "disband_revolts" in result


def test_off_calendar_lord_still_shifts_vassals_and_reenters():
    s = muster_state(advanced=True)
    do(s, "firenze", "Prato Comune")
    v = next(v for v in s["lords"]["firenze"]["vassals"] if v["name"] == "Prato Comune")
    A._place_service(s, "firenze", None)
    s["calendar"]["off_right_service"].append("firenze")
    V.shift_service(s, "firenze", 2)
    assert v["service_box"] == 5
    assert s["lords"]["firenze"]["service_box"] is None
    V.shift_service(s, "firenze", -1)
    assert s["lords"]["firenze"]["service_box"] == 16
    assert v["service_box"] == 4


def test_off_calendar_service_pay_and_event_are_discoverable():
    """2.2.3 / 3.2 / 3.4.2: an edge marker still participates in shifts."""
    from inferno import card_effects as CE
    from inferno.rng import HarnessRNG
    s = muster_state(advanced=True)
    do(s, "firenze", "Prato Comune")
    v = next(v for v in s["lords"]["firenze"]["vassals"] if v["name"] == "Prato Comune")
    A._place_service(s, "firenze", None)
    s["calendar"]["off_right_service"].append("firenze")
    s["lords"]["firenze"]["assets"]["Coin"] = 2
    s["meta"]["levy_step"] = "3.2"
    assert any(m["action"] == "levy_pay" and m["args"]["target_lord_id"] == "firenze"
               for m in enumerate_legal(s))
    assert any(m["target_lord_id"] == "firenze" for m in A._fpd_legal_pays(s, "guelph"))
    A.dispatch(s, {"action": "levy_pay", "side": "guelph",
                   "args": {"from_lord_id": "firenze", "target_lord_id": "firenze",
                            "asset": "Coin", "amount": 1}})
    assert v["service_box"] == 4
    CE.F9_event(s, "guelph", {"mode": "shift"}, HarnessRNG(1))
    assert v["service_box"] == 5
    s["lords"]["firenze"]["forces"]["Ritter"] = 1
    choice = {"target_lord_id": "firenze", "mode": "shift"}
    assert choice in CE.immediate_event_options(s, "F22", "guelph")
    CE.F22_event(s, "guelph", choice, HarnessRNG(1))
    assert s["lords"]["firenze"]["service_box"] == 16
    assert v["service_box"] == 4


def test_service_markers_return_from_off_left():
    """2.2.3 / 3.4.2: the first shift toward the Calendar enters box 1."""
    from inferno.card_effects import _shift_service_left
    s = muster_state(advanced=True)
    do(s, "firenze", "Prato Comune")
    v = next(v for v in s["lords"]["firenze"]["vassals"] if v["name"] == "Prato Comune")
    # Exercise both Calendar edges before the next expiry check.
    _shift_service_left(s, "firenze", 10)
    assert v["service_box"] == 0
    V.shift_service(s, "firenze", 1)
    assert v["service_box"] == 1
    assert s["lords"]["firenze"]["service_box"] == 1


def test_feed_shortage_shifts_vassal_service():
    """4.8.1 / 3.4.2: unfed Service penalties also apply to Vassals."""
    s = muster_state(advanced=True)
    do(s, "firenze", "Prato Comune")
    for lord in s["lords"].values():
        lord["assets"] = {}
        lord["flags"].pop("moved_fought", None)
    s["lords"]["firenze"]["flags"]["moved_fought"] = True
    A._place_service(s, "firenze", 6)
    v = next(v for v in s["lords"]["firenze"]["vassals"] if v["name"] == "Prato Comune")
    A._run_fpd(s)
    assert s["lords"]["firenze"]["service_box"] == 5
    assert v["service_box"] == 2


@pytest.mark.parametrize("comune_units,fed", [(3, True), (4, False)])
def test_commander_comune_feed_as_one_army(comune_units, fed):
    """1.5.1 / 4.8.1: six combined units need one provision, seven need two."""
    s = muster_state(advanced=True)
    do(s, "firenze", "Prato Comune")
    for lord in s["lords"].values():
        lord["assets"] = {}
        lord["flags"].pop("moved_fought", None)
    lord = s["lords"]["firenze"]
    lord["forces"] = {"Militia": 3}
    comune = s["lords"]["firenze_comune"]
    comune.update(status="mustered", location="Firenze", forces={"Militia": comune_units},
                  assets={"Provender": 1}, vassals=_init_vassals_for(sd.LORDS["Firenze Comune"]))
    comune["flags"]["moved_fought"] = True
    v = comune["vassals"][1]
    v.update(on_mat=True, ready=False)
    V.start_service(s, v)
    A._place_service(s, "firenze", 6)
    result = A._run_fpd(s)
    assert len(result["feed"]) == 1
    assert result["feed"][0]["units"] == 3 + comune_units
    assert result["feed"][0]["fed"] == fed
    assert lord["service_box"] == (6 if fed else 5)
    assert v["service_box"] == (3 if fed else 2)


def test_advanced_public_service_and_standard_rules_no_clock():
    s = muster_state(advanced=True)
    do(s, "firenze", "Prato Comune")
    view = hide_for_side(s, "ghibelline", hidden_mats=True)
    assert view["lords"]["firenze"]["public_vassal_service"] == [{"name": "Prato Comune", "service_box": 3}]
    from inferno.llm.briefing import build_briefing
    assert "Prato Comune — public Service=3" in build_briefing(s, "ghibelline", max_chars=None, hidden_mats=True)
    assert "<hidden>" in view["lords"]["firenze"]["assets"]
    standard = muster_state()
    do(standard, "firenze", "Prato Comune")
    assert all(v["service_box"] is None for v in standard["lords"]["firenze"]["vassals"])


def test_advanced_comune_vassals_follow_commander_except_carroccio():
    s = muster_state(advanced=True)
    comune = s["lords"]["firenze_comune"]
    comune.update(status="mustered", location="Firenze", forces={},
                  vassals=_init_vassals_for(sd.LORDS["Firenze Comune"]))
    for v in comune["vassals"][:2]:
        v.update(on_mat=True, ready=False)
        V.start_service(s, v)
    V.shift_service(s, "firenze", -1)
    assert comune["vassals"][0]["service_box"] is None
    assert comune["vassals"][1]["service_box"] == 2
