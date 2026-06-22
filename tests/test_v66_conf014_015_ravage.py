"""v6.6 — CONF-014 (Ravage Loot caps at the 16 Asset maximum, not 8) and
CONF-015 (Ravage acts on the Lord's OWN Locale, not an arbitrary target).
"""
from __future__ import annotations

import pytest
from inferno import static_data as sd
from inferno.actions import dispatch, IllegalAction, _apply_ravage_gains
from tests.test_phase3b import _to_command_phase


class TestRavageLootCap:
    def test_loot_can_exceed_8_up_to_16(self):
        s = _to_command_phase("A", seed=1, lord_for_active="firenze")
        lid = "firenze"
        s["lords"][lid]["assets"]["Loot"] = 8
        s["lords"][lid]["forces"] = {"Men-at-Arms": 2}  # no Berrovieri -> x1
        gains = _apply_ravage_gains(s, lid, "town")     # Town -> +1 Loot
        assert gains["Loot"] == 1
        assert s["lords"][lid]["assets"]["Loot"] == 9   # not capped at 8

    def test_loot_caps_at_16(self):
        s = _to_command_phase("A", seed=1, lord_for_active="firenze")
        lid = "firenze"
        s["lords"][lid]["assets"]["Loot"] = 16
        s["lords"][lid]["forces"] = {"Men-at-Arms": 2}
        _apply_ravage_gains(s, lid, "city")
        assert s["lords"][lid]["assets"]["Loot"] == 16  # ceiling holds


class TestRavageOwnLocaleOnly:
    def test_remote_ravage_rejected(self):
        s = _to_command_phase("A", seed=1, lord_for_active="firenze")
        here = s["lords"]["firenze"]["location"]
        adj = {n for n, _ in sd.adjacent_to(here)}
        remote = next(n for n, l in s["locales"].items()
                      if n != here and n not in adj
                      and l.get("allegiance") == "ghibelline"
                      and l.get("type") in ("castle", "town", "city")
                      and not l.get("ruins"))
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {"action": "cmd_ravage", "side": "guelph",
                         "args": {"lord_id": "firenze", "target_locale": remote}})
        assert exc.value.code == "RAVAGE_NOT_AT_LOCALE"

    def test_ravage_at_own_locale_still_works(self):
        # Put Firenze at an enemy Castle and Ravage where he stands.
        s = _to_command_phase("A", seed=1, lord_for_active="firenze")
        target = next(n for n, l in s["locales"].items()
                      if l.get("allegiance") == "ghibelline"
                      and l.get("type") == "castle" and not l.get("ruins")
                      and not l.get("siege"))
        f = s["lords"]["firenze"]
        old = f["location"]
        if old and "firenze" in s["locales"].get(old, {}).get("lords_present", []):
            s["locales"][old]["lords_present"].remove("firenze")
        f["location"] = target
        s["locales"][target]["lords_present"].append("firenze")
        r = dispatch(s, {"action": "cmd_ravage", "side": "guelph",
                         "args": {"lord_id": "firenze"}})
        assert r["state_changes"]["ravaged_locale"] == target


class TestPisaShipSupplyWinter:
    """CONF-016: Pisa's Ships do not operate in Winter (4.6.2) — a Port may be a
    Ship-Source only in non-Winter (same restriction as Sail 4.7.3)."""

    def _setup(self):
        from inferno.scenarios import load_scenario
        s = load_scenario("A", 1)
        p = s["lords"]["pisa"]
        p["status"] = "mustered"; p["location"] = "Empoli"
        s["locales"]["Empoli"].setdefault("lords_present", []).append("pisa")
        p["assets"]["Ship"] = 3
        s["current_lord_id"] = "pisa"; s["actions_remaining"] = 2
        seats = set(p.get("seats", []))
        source = next(n for n in ["Pontedera", "Borgo Livorno", "San Miniato",
                                  "Montelupo", "Castiglione della Pescaia"]
                      if n not in seats and n != "Empoli")
        return s, source

    def test_winter_blocks_pisa_ship_source(self):
        from inferno.actions import _h_cmd_supply, IllegalAction
        from inferno.rng import HarnessRNG
        s, source = self._setup()
        s["meta"]["turn"] = 1   # Winter box
        with pytest.raises(IllegalAction) as e:
            _h_cmd_supply(s, "ghibelline",
                          {"lord_id": "pisa", "source": source}, HarnessRNG(seed=1))
        assert e.value.code == "BAD_SOURCE"   # Port not a valid Ship-Source in Winter

    def test_nonwinter_port_is_a_valid_ship_source(self):
        from inferno.actions import _h_cmd_supply, IllegalAction
        from inferno.rng import HarnessRNG
        s, source = self._setup()
        s["meta"]["turn"] = 3   # Summer box
        code = None
        try:
            _h_cmd_supply(s, "ghibelline",
                          {"lord_id": "pisa", "source": source}, HarnessRNG(seed=1))
        except IllegalAction as e:
            code = e.code
        # May still fail on route/carts, but NOT because the Port is an invalid Source.
        assert code != "BAD_SOURCE"
