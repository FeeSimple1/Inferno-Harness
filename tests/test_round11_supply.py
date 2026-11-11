"""Additive Supply across Seats and Port Sources (4.6)."""

import json

import pytest

from inferno.actions import dispatch
from inferno.legal_moves import enumerate_legal
from inferno.llm.interface import PlayerView
from inferno.llm.menu import submit_selection
from tests.test_v614_audit_regressions import apply, command, muster, rejected_unchanged


def test_single_action_can_supply_from_both_firenze_and_prato():
    state = command()
    lord = state["lords"]["firenze"]
    lord["assets"] = {"Cart": 2, "Provender": 0}
    view = PlayerView(state)
    records = view.query({"request": "actions", "category": "cmd_supply", "page_size": 50})["records"]
    multi = next(record for record in records if "sources" in record["move"]["args"])
    assert multi["parameterized"]
    assert multi["move"]["parameters"]["carts_available"] == 2
    args = {"lord_id": "firenze", "sources": [{"source": "Firenze", "provender": 3},
                                           {"source": "Prato", "provender": 2}]}
    selection = {"action_id": multi["action_id"], "state_version": view.version, "args": args}
    restored = json.loads(json.dumps(state))
    result = submit_selection(state, "guelph", selection)
    assert result == dispatch(restored, {"action": "cmd_supply", "side": "guelph", "args": args})
    assert state == restored
    assert result["state_changes"]["supply_added"] == 5
    assert result["state_changes"]["carts_required"] == 2
    assert lord["assets"] == {"Cart": 2, "Provender": 5}
    assert state["actions_remaining"] == 1


@pytest.mark.parametrize(("turn", "ships", "expected"), [(9, 2, 5), (9, 0, 3), (12, 2, 3)])
def test_pisa_seat_and_ships_add_together_outside_winter(turn, ships, expected):
    state = command("pisa", "Pisa", turn=turn)
    state["lords"]["pisa"]["forces"] = {"Cavalieri": 1}
    state["lords"]["pisa"]["assets"] = {"Ship": ships, "Provender": 0}
    amounts = [m["args"]["provender"] for m in enumerate_legal(state)
               if m["action"] == "cmd_supply" and m["args"].get("source") == "Pisa"]
    assert amounts == list(range(1, expected + 1))
    result = apply(state, "cmd_supply", {"source": "Pisa", "provender": 16})
    assert result["state_changes"]["supply_added"] == expected
    assert state["lords"]["pisa"]["assets"]["Ship"] == ships


@pytest.mark.parametrize(("active", "location", "carts", "expected"), [
    ("giordano", "Borgo Livorno", 0, 2),
    ("pisa", "Rosignano", 0, 0),
    ("pisa", "Rosignano", 1, 1),
])
def test_port_supply_shares_ships_and_charges_land_ways(active, location, carts, expected):
    state = command(active, location)
    lord = state["lords"][active]
    lord["forces"] = {"Ritter": 1} if active == "giordano" else {"Cavalieri": 1}
    lord["assets"] = {"Provender": 0, "Cart": carts}
    if active != "pisa":
        muster(state, "pisa", location, forces={"Cavalieri": 1})["assets"] = {"Ship": 2}
    else:
        lord["assets"]["Ship"] = 2
    args = {"source": "Borgo Livorno", "provender": 16}
    if expected:
        result = apply(state, "cmd_supply", args)["state_changes"]
        assert result["supply_added"] == expected and result["carts_required"] == carts
        assert state["lords"]["pisa"]["assets"]["Ship"] == 2
    else:
        assert rejected_unchanged(state, "cmd_supply", args) == "INSUFFICIENT_CARTS"


def test_multiple_ports_cannot_reuse_pisas_ships():
    state = command("pisa", "Pisa")
    state["lords"]["pisa"]["forces"] = {"Cavalieri": 1}
    state["lords"]["pisa"]["assets"] = {"Ship": 2, "Cart": 4, "Provender": 0}
    too_many = {"sources": [{"source": "Pisa", "provender": 5},
                            {"source": "Borgo Livorno", "provender": 2}]}
    assert rejected_unchanged(state, "cmd_supply", too_many) == "INSUFFICIENT_SHIPS"
    split = {"sources": [{"source": "Pisa", "provender": 4},
                         {"source": "Borgo Livorno", "provender": 1}]}
    result = apply(state, "cmd_supply", split)["state_changes"]
    assert result["supply_added"] == 5
    assert [r["ship_provender"] for r in result["sources"]] == [1, 1]
