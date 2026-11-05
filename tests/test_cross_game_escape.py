"""INF-1/2/3: Avoid discards, destination Bypass and route-aware Retreat."""
from __future__ import annotations

import copy
import json

import pytest

from inferno import actions as A
from inferno import static_data as sd
from inferno.legal_moves import enumerate_legal
from inferno.scenarios import load_scenario


def place(state, lid, locale, **assets):
    lord = state["lords"][lid]
    old = lord.get("location")
    if old and lid in state["locales"][old]["lords_present"]:
        state["locales"][old]["lords_present"].remove(lid)
    A._place_cylinder(state, lid, None)
    lord.update(status="mustered", location=locale, forces={"Armigieri": 2},
                routed_units={}, assets=assets, flags={})
    state["locales"][locale].setdefault("lords_present", []).append(lid)
    A._place_service(state, lid, 12)
    return lord


def approach(way="track", **assets):
    state = load_scenario("D", seed=11)
    for locale in state["locales"].values():
        locale["lords_present"] = []
    for lid, lord in state["lords"].items():
        A._place_cylinder(state, lid, 1)
        lord.update(status="ready", location=None, assets={}, flags={}, forces={}, routed_units={})
    source, origin, destination = (("Firenze", "Figline", "Prato") if way == "track"
                                   else ("Figline", "Firenze", "San Giovanni"))
    place(state, "pisa", source)
    place(state, "arezzo", source, **assets)
    state["meta"].update(phase="campaign", campaign_step="command_phase", levy_step=None,
                         active_player="guelph", turn=9, approach_attacker_side="ghibelline",
                         approach_breadcrumb={"approached_from": origin, "approached_via": "road"})
    state.update(current_card="command_pisa", current_lord_id="pisa", actions_remaining=3)
    state["pending"] = [pending("arezzo", source, origin)]
    return state, destination


def pending(lid, source, origin="Figline"):
    return {"type": "approach_response", "side": "guelph", "info": {
        "lord_id": lid, "locale": source, "approaching_lord": "pisa",
        "approached_from": origin, "approached_via": "road"}}


def avoid(state, destination, **kwargs):
    return A.dispatch(state, {"action": "approach_response", "side": "guelph", "args": {
        "lord_id": "arezzo", "choice": "avoid", "destination": destination, **kwargs}})


@pytest.mark.parametrize("way,prov,carts,loot,kept", [
    ("track", 16, 0, 0, 0), ("track", 2, 1, 0, 1), ("road", 2, 1, 0, 2),
    ("road", 4, 1, 0, 2), ("track", 1, 1, 3, 1), ("road", 0, 0, 1, 0),
])
def test_public_avoid_discards_exact_route_excess_and_loot_to_approaching_lords(
        way, prov, carts, loot, kept):
    state, destination = approach(way, Provender=prov, Cart=carts, Loot=loot, Coin=2, Ship=1)
    move = next(m for m in enumerate_legal(state) if m["args"].get("choice") == "avoid"
                and m["args"].get("destination") == destination)
    result = A.dispatch(state, move)
    lord = state["lords"]["arezzo"]
    assert lord["location"] == destination and lord["flags"]["moved_fought"]
    assert lord["assets"]["Provender"] == kept and lord["assets"].get("Loot", 0) == 0
    assert lord["assets"]["Coin"] == 2 and lord["assets"]["Ship"] == 1
    winner = state["lords"]["pisa"]["assets"]
    assert winner.get("Provender", 0) == prov - kept and winner.get("Loot", 0) == loot
    assert result["state_changes"]["discarded_as_spoils"] == {
        "Loot": loot, "Provender": prov - kept}


@pytest.mark.parametrize("way,kept", [("road", 4), ("track", 2)])
def test_group_avoid_shares_carts_but_food_stays_on_its_own_mat(way, kept):
    state, destination = approach(way, Provender=4)
    source = state["lords"]["arezzo"]["location"]
    origin = state["pending"][0]["info"]["approached_from"]
    place(state, "firenze", source, Cart=2)
    state["pending"].append(pending("firenze", source, origin))
    move = next(m for m in enumerate_legal(state)
                if m["args"].get("with_lords") == ["firenze"]
                and m["args"].get("destination") == destination)
    A.dispatch(state, move)
    assert state["lords"]["arezzo"]["assets"]["Provender"] == kept
    assert state["lords"]["firenze"]["assets"].get("Provender", 0) == 0
    assert all(state["lords"][m]["location"] == destination for m in ["arezzo", "firenze"])
    assert not state["pending"]


def test_every_coavoid_subset_is_discoverable_and_cannot_borrow_from_a_stayer():
    state, destination = approach(Provender=2)
    for lid in ["firenze", "lucca"]:
        place(state, lid, "Firenze", Cart=2)
        state["pending"].append(pending(lid, "Firenze"))
    choices = {tuple(m["args"].get("with_lords", [])) for m in enumerate_legal(state)
               if m["args"].get("choice") == "avoid" and m["args"].get("destination") == destination}
    assert choices == {(), ("firenze",), ("lucca",), ("firenze", "lucca")}
    avoid(state, destination)
    assert state["lords"]["arezzo"]["assets"]["Provender"] == 0
    assert state["lords"]["firenze"]["location"] == "Firenze"
    assert len(state["pending"]) == 2


@pytest.mark.parametrize("condition,bypassing", [
    ("enemy", True), ("friendly", False), ("ruins", False), ("besieged", False),
    ("already_bypassed", True),
])
def test_avoid_destination_establishes_bypass_only_when_required(condition, bypassing):
    state, destination = approach()
    target = state["locales"][destination]
    target["current_allegiance"] = [{"side": "guelph" if condition == "friendly" else "ghibelline",
                                     "value": 2}]
    if condition == "ruins":
        target["ruins"] = "purple"
    if condition == "besieged":
        target["siege"] = [{"side": "guelph", "color": "purple", "count": 1}]
    if condition == "already_bypassed":
        target["bypass"] = [{"side": "guelph", "lord_id": "firenze"}]
    avoid(state, destination)
    assert bool(state["lords"]["arezzo"]["flags"].get("bypassing")) == bypassing
    assert bool(target.get("bypass")) == bypassing
    if bypassing:
        assert len(target["bypass"]) == 1
        assert state["lords"]["arezzo"]["flags"]["bypassing"] == destination


def test_avoider_can_encamp_on_a_later_command():
    state, destination = approach()
    target = state["locales"][destination]
    target["current_allegiance"] = [{"side": "ghibelline", "value": 2}]
    avoid(state, destination)
    state["meta"]["active_player"] = "guelph"
    state.update(current_card="command_arezzo", current_lord_id="arezzo", actions_remaining=3)
    move = next(m for m in enumerate_legal(state) if m["action"] == "cmd_encamp")
    A.dispatch(state, move)
    assert target["siege"] and not target["bypass"]
    assert not state["lords"]["arezzo"]["flags"].get("bypassing")


@pytest.mark.parametrize("with_lords", [["firenze"], ["pisa"], ["firenze", "firenze"], "firenze", None])
def test_invalid_or_ambushed_group_rejects_atomically(with_lords):
    state, destination = approach(Provender=4, Loot=2)
    place(state, "firenze", "Firenze", Cart=4)
    state["lords"]["firenze"]["flags"]["ambush_forced"] = True
    state["pending"].append(pending("firenze", "Firenze"))
    before = copy.deepcopy(state)
    with pytest.raises(A.IllegalAction):
        avoid(state, destination, with_lords=with_lords)
    assert state == before
    assert not [m for m in enumerate_legal(state) if m["args"].get("with_lords")]


@pytest.mark.parametrize("bad", ["approach", "enemy", "bad_way"])
def test_rejected_route_does_not_spend_discards_or_consume_pending(bad):
    state, destination = approach(Provender=4, Loot=1)
    kwargs = {}
    if bad == "approach":
        destination = "Figline"
    elif bad == "enemy":
        place(state, "astimberg", destination)
    else:
        kwargs["way_type"] = "sail"
    before = copy.deepcopy(state)
    with pytest.raises(A.IllegalAction):
        avoid(state, destination, **kwargs)
    assert state == before


def test_avoid_spoils_spill_around_full_winners_and_respect_mat_limits():
    state, destination = approach(Provender=4, Loot=3)
    state["lords"]["pisa"]["assets"] = {"Provender": 16, "Loot": 16}
    place(state, "astimberg", "Firenze", Provender=15)
    result = avoid(state, destination)
    assert state["lords"]["pisa"]["assets"] == {"Provender": 16, "Loot": 16}
    assert state["lords"]["astimberg"]["assets"] == {"Provender": 16, "Loot": 3}
    assert result["state_changes"]["spoils_allocation"]["lost_to_cap"] == {"Provender": 3}


@pytest.mark.parametrize("way,kept", [("road", 2), ("track", 1)])
def test_actual_postbattle_retreat_uses_the_chosen_way(way, kept):
    state, _ = approach(Provender=2, Cart=1, Loot=1, Coin=2)
    state["pending"] = []
    destination = "Figline" if way == "road" else "Prato"
    state["meta"]["approach_breadcrumb"] = {"approached_from": "Montelupo", "approached_via": "track"}
    result = {"loser": "defender", "conceded": "defender", "removed_lords": []}
    A._apply_post_battle(state, result, ["pisa"], ["arezzo"], battle_locale="Firenze", decisions=[
        {"type": "post_battle_withdraw", "choice": "retreat"},
        {"type": "retreat_destination", "choice": destination}])
    assert state["lords"]["arezzo"]["location"] == destination
    assert state["lords"]["arezzo"]["assets"]["Provender"] == kept
    assert state["lords"]["pisa"]["assets"].get("Provender", 0) == 2 - kept
    assert state["lords"]["pisa"]["assets"]["Loot"] == 1
    assert state["lords"]["arezzo"]["assets"]["Coin"] == 2


def test_conceding_coretreaters_share_carts_on_track():
    state, _ = approach(Provender=2)
    place(state, "firenze", "Firenze", Cart=2)
    state["pending"] = []
    result = {"loser": "defender", "conceded": "defender", "removed_lords": []}
    A._apply_post_battle(state, result, ["pisa"], ["arezzo", "firenze"], battle_locale="Firenze",
                         callback=lambda d: "retreat" if d["type"] == "post_battle_withdraw"
                         else ("Prato" if d["type"] == "retreat_destination" else d["options"][0]))
    assert state["lords"]["arezzo"]["assets"]["Provender"] == 2
    assert state["lords"]["firenze"]["assets"].get("Provender", 0) == 0


@pytest.mark.parametrize("way,kept", [("road", 2), ("track", 1)])
def test_dual_way_choice_is_explicit_for_avoid_and_retreat(monkeypatch, way, kept):
    original = sd.adjacent_to
    monkeypatch.setattr(sd, "adjacent_to", lambda source:
                        [("Prato", "road"), ("Prato", "track"), ("Figline", "road")]
                        if source == "Firenze" else original(source))
    state, destination = approach(Provender=2, Cart=1)
    advertised = {m["args"].get("way_type") for m in enumerate_legal(state)
                  if m["args"].get("destination") == destination}
    assert advertised == {"road", "track"}
    avoid(state, destination, way_type=way)
    assert state["lords"]["arezzo"]["assets"]["Provender"] == kept
    state, _ = approach(Provender=2, Cart=1)
    state["pending"] = []
    result = {"loser": "defender", "conceded": "defender", "removed_lords": []}
    A._apply_post_battle(state, result, ["pisa"], ["arezzo"], battle_locale="Firenze", decisions=[
        {"type": "post_battle_withdraw", "choice": "retreat"},
        {"type": "retreat_destination", "choice": "Prato"}, {"type": "retreat_way", "choice": way}])
    assert state["lords"]["arezzo"]["assets"]["Provender"] == kept
    if way == "track":  # Non-default choices enter the optional decision trace.
        assert any(d["type"] == "retreat_way" for d in result["post_battle_decisions"])


def test_avoid_state_and_results_survive_save_load_replay():
    state, destination = approach(Provender=4, Cart=1, Loot=1)
    restored = json.loads(json.dumps(state))
    assert avoid(state, destination) == avoid(restored, destination)
    assert state == restored


def test_alternate_track_does_not_reuse_the_parallel_approach_road(monkeypatch):
    original = sd.adjacent_to
    monkeypatch.setattr(sd, "adjacent_to", lambda source:
                        [("Prato", "road"), ("Prato", "track")]
                        if source == "Firenze" else original(source))
    state, destination = approach(Provender=2, Cart=1)
    state["pending"][0]["info"]["approached_from"] = "Prato"
    moves = [m for m in enumerate_legal(state) if m["args"].get("destination") == destination]
    assert [m["args"]["way_type"] for m in moves] == ["track"]
    with pytest.raises(A.IllegalAction, match="AVOID_ALONG_APPROACH_WAY"):
        avoid(state, destination, way_type="road")
    A.dispatch(state, moves[0])
    assert state["lords"]["arezzo"]["assets"]["Provender"] == 1
    state, _ = approach(Provender=2, Cart=1)
    state["pending"] = []
    state["meta"]["approach_breadcrumb"]["approached_from"] = "Prato"
    result = {"loser": "defender", "conceded": "defender", "removed_lords": []}
    A._apply_post_battle(state, result, ["pisa"], ["arezzo"], battle_locale="Firenze")
    assert state["lords"]["arezzo"]["location"] == "Prato"
    assert state["lords"]["arezzo"]["assets"]["Provender"] == 1


@pytest.mark.parametrize("conceded,withdraw", [(False, False), (True, True)])
def test_track_capacity_does_not_change_nonconceding_or_withdrawn_spoils(conceded, withdraw):
    assets = {"Provender": 2, "Cart": 1, "Loot": 1, "Ship": 1}
    state, _ = approach(**assets)
    state["pending"] = []
    result = {"loser": "defender", "conceded": "defender" if conceded else None,
              "removed_lords": []}
    A._apply_post_battle(state, result, ["pisa"], ["arezzo"], battle_locale="Firenze", decisions=[
        {"type": "post_battle_withdraw", "choice": "withdraw" if withdraw else "retreat"},
        {"type": "retreat_destination", "choice": "Prato"}])
    if withdraw:
        assert state["lords"]["arezzo"]["assets"] == assets
        assert not state["lords"]["pisa"]["assets"]
    else:
        assert state["lords"]["arezzo"]["assets"] == {"Provender": 0, "Cart": 0, "Loot": 0, "Ship": 1}
        assert state["lords"]["pisa"]["assets"] == {"Provender": 2, "Cart": 1, "Loot": 1}
