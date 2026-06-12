"""v5.9 — Sail: enemy-Port destinations enumerated (4.7.3) + Greed discard.

Bug #11 (Fable edge-case hunt): the enumerator offered cmd_sail only to
FRIENDLY Ports, but 4.7.3 says "Move directly to any other Port that is free
of Unbesieged Enemy Lords" and "If Sailing to an Unbesieged Enemy Stronghold:
place a Siege marker (Besiege)". The handler implemented Sail-to-Enemy Siege
(SMOKE-Inferno-027) but no legal-moves consumer could ever reach it — an
under-enumeration invisible to the validated-palette check.

Bug #12: per 4.7.3/1.7.2 Greed, cargo that cannot be transported "must be
discarded or left behind" — the harness hard-blocked INSUFFICIENT_SHIPS with
no way to discard. cmd_sail now takes an optional `discard` arg
({"Provender": n, "Loot": m}), validated BEFORE any mutation, and the
enumerator offers a deterministic minimal-discard variant.
"""
from __future__ import annotations

import copy

import pytest

from inferno.actions import IllegalAction, dispatch
from inferno.legal_moves import enumerate_legal
from inferno.scenarios import load_scenario
from inferno.flow import current_campaign_step, current_side
from inferno import static_data as sd


def _stage_pisa(seed=1, port="Pisa", ship=6, prov=0, loot=0, forces=None):
    """Scenario F at a summer turn with Pisa Podesta mustered at `port`,
    his command card revealed and FPD cleared."""
    s = load_scenario("F", seed=seed)
    cal = s["calendar"]
    box = 3  # summer
    cal["boxes"][str(cal["levy_box"])]["markers"].remove("levy")
    cal["levy_box"] = box
    cal["boxes"].setdefault(str(box), {"cylinders": [], "services": [], "victory": [], "markers": []})
    cal["boxes"][str(box)]["markers"].append("levy")
    s["meta"]["turn"] = box
    # Park every Service marker at 16 so the turn-shift disbands nobody.
    moved = []
    for b in cal["boxes"].values():
        for lid in list(b.get("services", [])):
            b["services"].remove(lid)
            moved.append(lid)
    cal["boxes"].setdefault("16", {"cylinders": [], "services": [], "victory": [], "markers": []})
    for lid in moved:
        cal["boxes"]["16"]["services"].append(lid)
        s["lords"][lid]["service_box"] = 16
    for name, side in [("levy_aow_draw","guelph"),("levy_aow_draw","ghibelline"),
                       ("levy_pay_done","guelph"),("levy_pay_done","ghibelline"),
                       ("levy_disband_done","guelph"),("levy_disband_done","ghibelline"),
                       ("levy_muster_done","guelph"),("levy_muster_done","ghibelline"),
                       ("levy_cta_skip","guelph"),("levy_cta_skip","ghibelline")]:
        dispatch(s, {"action": name, "side": side})
    p = s["lords"]["pisa"]
    p["status"] = "mustered"
    p["location"] = port
    s["locales"][port]["lords_present"].append("pisa")
    p["forces"] = dict(forces or {})
    p["assets"] = {"Ship": ship, "Coin": 1, "Provender": prov, "Loot": loot}
    p.setdefault("flags", {})["in_stronghold"] = False
    for b in cal["boxes"].values():
        if "pisa" in b.get("cylinders", []):
            b["cylinders"].remove("pisa")
    cal["boxes"]["16"]["services"].append("pisa")
    p["service_box"] = 16
    from tests.test_phase3a import _skip_capability_discard
    _skip_capability_discard(s)
    size = sd.PLAN_SIZE_BY_SEASON[sd.SEASON_BY_BOX[box]]
    while current_campaign_step(s) == "plan":
        side = current_side(s)
        n = len(s["plan_stacks"][side])
        if n >= size:
            dispatch(s, {"action": "plan_done", "side": side})
            continue
        want = "command_pisa" if (side == "ghibelline" and n == 0) else "PASS"
        dispatch(s, {"action": "plan_add_card", "side": side, "args": {"card_id": want}})
        if len(s["plan_stacks"][side]) >= size:
            dispatch(s, {"action": "plan_done", "side": side})
    while s.get("current_lord_id") != "pisa":
        dispatch(s, {"action": "command_reveal", "side": current_side(s)})
    for _ in range(3):  # clear the FPD-pay window from guelph's PASS card
        moves = enumerate_legal(s)
        done = [m for m in moves if m["action"] == "cmd_fpd_pay_done"]
        if not done:
            break
        dispatch(s, {"action": "cmd_fpd_pay_done", "side": done[0]["side"]})
    return s


def _sails(s):
    return [m for m in enumerate_legal(s) if m["action"] == "cmd_sail"]


class TestSailEnemyPort:
    def test_enemy_port_destinations_enumerated(self):
        s = _stage_pisa()
        dests = {m["args"]["dest_locale"] for m in _sails(s)}
        from inferno.legal_moves import _is_friendly_locale_quiet
        enemy_dests = {d for d in dests
                       if not _is_friendly_locale_quiet(s, s["locales"][d], "ghibelline")}
        assert enemy_dests, (
            "4.7.3 allows Sail to ANY Port free of Unbesieged Enemy Lords; "
            f"only friendly dests were offered: {sorted(dests)}")

    def test_sail_to_enemy_stronghold_besieges(self):
        s = _stage_pisa()
        from inferno.legal_moves import _is_friendly_locale_quiet
        target = None
        for m in _sails(s):
            d = m["args"]["dest_locale"]
            dest = s["locales"][d]
            if (not _is_friendly_locale_quiet(s, dest, "ghibelline")
                    and dest.get("type") != "outpost"
                    and not dest.get("ruins") and not dest.get("siege")):
                target = m
                break
        assert target is not None
        r = dispatch(s, {k: target[k] for k in ("action", "side", "args")})
        assert r["state_changes"]["besieged_via_sail"] is True
        siege = s["locales"][target["args"]["dest_locale"]]["siege"]
        assert siege and siege[0]["side"] == "ghibelline"


class TestSailGreedDiscard:
    def test_over_capacity_offers_minimal_discard_variant(self):
        s = _stage_pisa(ship=1, prov=3, loot=1)
        sails = _sails(s)
        assert sails, "over-capacity Pisa must still be offered Sail-with-discard"
        for m in sails:
            d = m["args"].get("discard")
            assert d, f"expected a discard arg on {m['args']}"
            # post-discard cargo must fit: 0 horses + prov' + 2*loot' <= 1 Ship
            assert (3 - d.get("Provender", 0)) + 2 * (1 - d.get("Loot", 0)) <= 1

    def test_dispatch_with_discard_succeeds_and_reduces_assets(self):
        s = _stage_pisa(ship=1, prov=3, loot=1)
        m = _sails(s)[0]
        r = dispatch(s, {k: m[k] for k in ("action", "side", "args")})
        assert r["state_changes"]["discarded"]
        p = s["lords"]["pisa"]
        assert p["assets"]["Provender"] == 3 - r["state_changes"]["discarded"].get("Provender", 0)
        assert p["assets"]["Loot"] == 1 - r["state_changes"]["discarded"].get("Loot", 0)
        assert p["location"] == m["args"]["dest_locale"]

    def test_bad_discard_rejected_without_mutation(self):
        s = _stage_pisa(ship=1, prov=3, loot=1)
        before = copy.deepcopy(s)
        with pytest.raises(IllegalAction) as ei:
            dispatch(s, {"action": "cmd_sail", "side": "ghibelline",
                         "args": {"lord_id": "pisa", "dest_locale": "Pontedera",
                                  "discard": {"Provender": 99}}})
        assert ei.value.code == "BAD_DISCARD"
        assert s == before

    def test_insufficient_even_after_discard_rejected_without_mutation(self):
        s = _stage_pisa(ship=0, prov=2, loot=0, forces={"Cavalieri": 2})
        before = copy.deepcopy(s)
        with pytest.raises(IllegalAction) as ei:
            dispatch(s, {"action": "cmd_sail", "side": "ghibelline",
                         "args": {"lord_id": "pisa", "dest_locale": "Pontedera",
                                  "discard": {"Provender": 2}}})
        assert ei.value.code == "INSUFFICIENT_SHIPS"
        assert s == before, "failed Sail must not consume the discard"
