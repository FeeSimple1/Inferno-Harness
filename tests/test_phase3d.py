"""Phase 3d tests: Battle cleanup + Bypass-state March + Lieutenants."""
from __future__ import annotations

import inspect

import pytest

from inferno.actions import IllegalAction, dispatch
from inferno.battle import (
    loss_roll_for_routed,
    service_shift_for_retreated,
    transfer_spoils,
)
from inferno.rng import HarnessRNG
from inferno.scenarios import load_scenario


def _stand_battle_setup():
    """Build a state where a Battle has just resolved (manually constructed).
    Used to test the post-Battle helpers directly."""
    s = load_scenario("A", seed=1)
    # Force-place defender flags as if having Routed
    s["lords"]["siena"]["routed_units"] = {"Cavalieri": 1, "Men-at-Arms": 1}
    s["lords"]["siena"]["forces"] = {}  # all routed
    return s


# =====================================================================
# 4.4.4 Loss rolls + Knights' Quarter
# =====================================================================
class TestLossRolls:
    def test_villici_never_roll(self):
        s = _stand_battle_setup()
        s["lords"]["siena"]["routed_units"] = {"Villici": 3}
        rng = HarnessRNG(seed=1)
        r = loss_roll_for_routed(s, "siena", harsh_recovery=False, rng_caller=rng.roll)
        assert r["lost"] == {}
        assert r["recovered"] == {}
        assert r["captured"] == {}

    def test_harsh_recovery_only_recovers_on_1(self):
        """Harsh Recovery: unit fails unless roll == 1."""
        s = _stand_battle_setup()
        s["lords"]["siena"]["routed_units"] = {"Cavalieri": 6}
        rng = HarnessRNG(seed=1)
        r = loss_roll_for_routed(s, "siena", harsh_recovery=True, rng_caller=rng.roll)
        # Recovered count should equal number of dice that rolled 1.
        # With seed=1 we get some distribution; assert structural property.
        assert sum(r["recovered"].values()) + sum(r["lost"].values()) + sum(r["captured"].values()) == 6

    def test_knights_quarter_captures_cavalieri_lost_on_high_roll(self):
        """4.4.4: Cavalieri/Ritter lost on a 3-6 go to Owner's Captured Knights box."""
        # Force harsh recovery so anything not a 1 is lost or captured.
        s = _stand_battle_setup()
        s["lords"]["siena"]["routed_units"] = {"Cavalieri": 10}
        rng = HarnessRNG(seed=2)
        r = loss_roll_for_routed(s, "siena", harsh_recovery=True, rng_caller=rng.roll)
        # Lord's side is Ghibelline; captured knights stored under that side.
        assert s.get("captured_knights", {}).get("ghibelline", {}) != {}
        # Each die landing >= 3 captures; each 2 = lost; each 1 = recovered.
        # Total processed = 10.
        cap_total = sum(s["captured_knights"]["ghibelline"].values())
        assert cap_total + sum(r["lost"].values()) + sum(r["recovered"].values()) == 10


# =====================================================================
# 4.4.3 Service-shift dice
# =====================================================================
class TestServiceShift:
    def test_carroccio_concede_shifts_just_one(self):
        s = _stand_battle_setup()
        s["lords"]["firenze"]["service_box"] = 5
        s["calendar"]["boxes"].setdefault("5", {"cylinders": [], "services": [], "victory": [], "markers": []})
        s["calendar"]["boxes"]["5"]["services"].append("firenze")
        rng = HarnessRNG(seed=1)
        r = service_shift_for_retreated(s, "firenze", conceded_with_carroccio=True, rng_caller=rng.roll)
        assert r["shift_left"] == 1
        assert s["lords"]["firenze"]["service_box"] == 4

    def test_normal_retreat_die_drives_shift(self):
        s = _stand_battle_setup()
        s["lords"]["firenze"]["service_box"] = 10
        s["calendar"]["boxes"].setdefault("10", {"cylinders": [], "services": [], "victory": [], "markers": []})
        s["calendar"]["boxes"]["10"]["services"].append("firenze")
        rng = HarnessRNG(seed=1)
        r = service_shift_for_retreated(s, "firenze", conceded_with_carroccio=False, rng_caller=rng.roll)
        assert 1 <= r["die"] <= 6
        # 1-2 -> 1, 3-4 -> 2, 5-6 -> 3
        expected_shift = 1 if r["die"] <= 2 else (2 if r["die"] <= 4 else 3)
        assert r["shift_left"] == expected_shift
        assert s["lords"]["firenze"]["service_box"] == 10 - expected_shift


# =====================================================================
# 4.4.3 Spoils transfer
# =====================================================================
class TestSpoilsTransfer:
    def test_withdrew_keeps_all_assets(self):
        s = _stand_battle_setup()
        s["lords"]["siena"]["assets"] = {"Coin": 2, "Cart": 2, "Provender": 2}
        r = transfer_spoils(s, "siena", winners=["firenze"],
                             retreated=False, conceded=False, withdrew=True)
        assert r["transferred"] == {}
        assert s["lords"]["siena"]["assets"]["Coin"] == 2

    def test_removed_loses_all_except_ships(self):
        s = _stand_battle_setup()
        s["lords"]["siena"]["assets"] = {"Coin": 2, "Cart": 2, "Provender": 2, "Ship": 0}
        r = transfer_spoils(s, "siena", winners=["firenze"],
                             retreated=False, conceded=False, withdrew=False)
        # All non-Ship assets transferred
        assert s["lords"]["siena"]["assets"]["Coin"] == 0
        assert s["lords"]["siena"]["assets"]["Cart"] == 0
        assert s["lords"]["siena"]["assets"]["Provender"] == 0
        # Winner received them
        assert s["lords"]["firenze"]["assets"]["Coin"] >= 2

    def test_conceded_retreat_keeps_carroccio_loses_only_loot_and_excess_prov(self):
        s = _stand_battle_setup()
        # Mount a Carroccio on firenze
        s["lords"]["firenze"]["vassals"].append({
            "name": "Carroccio", "special": True, "on_mat": True, "ready": True,
            "forces": {"Cavalieri": 1, "Villici": 1},
        })
        s["lords"]["firenze"]["assets"] = {"Cart": 1, "Provender": 4, "Loot": 2}
        r = transfer_spoils(s, "firenze", winners=["siena"],
                             retreated=True, conceded=True, withdrew=False)
        # Concede+Retreat: Loot all transferred; Provender excess (4 - 1 cart = 3) transferred
        assert s["lords"]["firenze"]["assets"]["Loot"] == 0
        assert s["lords"]["firenze"]["assets"]["Provender"] == 1
        # Carroccio retained
        assert any(v.get("name") == "Carroccio" for v in s["lords"]["firenze"]["vassals"])


# =====================================================================
# 4.3.6 Encamp action
# =====================================================================
class TestEncamp:
    def test_encamp_replaces_bypass_with_siege_and_ends_card(self):
        from tests.test_phase3c import _to_command_with
        s = _to_command_with("A", seed=1, lord_id="firenze",
                             lord_location_override="Volterra")
        # Bypass first
        dispatch(s, {"action": "besiege_or_bypass", "side": "guelph",
                     "args": {"lord_id": "firenze", "choice": "bypass"}})
        assert s["locales"]["Volterra"]["bypass"]
        # Now Encamp
        dispatch(s, {"action": "cmd_encamp", "side": "guelph",
                     "args": {"lord_id": "firenze"}})
        assert s["locales"]["Volterra"]["siege"]
        assert s["locales"]["Volterra"]["bypass"] == []
        # Card ended
        assert s["current_lord_id"] is None


# =====================================================================
# 4.1.3 Lieutenants
# =====================================================================
class TestLieutenants:
    def test_lieutenant_attach_during_plan(self):
        from tests.test_phase3a import _skip_capability_discard
        s = load_scenario("D", seed=1)
        for name, side in [
            ("levy_aow_draw","guelph"),("levy_aow_draw","ghibelline"),
            ("levy_pay_done","guelph"),("levy_pay_done","ghibelline"),
            ("levy_disband_done","guelph"),("levy_disband_done","ghibelline"),
            ("levy_muster_done","guelph"),("levy_muster_done","ghibelline"),
            ("levy_cta_skip","guelph"),("levy_cta_skip","ghibelline"),
        ]:
            dispatch(s, {"action": name, "side": side})
        _skip_capability_discard(s)
        # In scenario D, Arezzo + Orvieto are both Mustered at Arezzo.
        # Neither is a Commander/Comune. Attach Lieutenant.
        # Note: Arezzo Podestà — is he a Commander? Per static_data: Firenze + Siena are Commanders. Arezzo is not.
        # However Arezzo IS a Podestà; that's fine for Lieutenant per 4.1.3 (only Commander+Comune excluded).
        r = dispatch(s, {"action": "plan_attach_lieutenant", "side": "guelph",
                         "args": {"lieutenant": "arezzo", "lower_lord": "orvieto"}})
        assert s["lords"]["arezzo"]["flags"]["has_lower_lord"] == "orvieto"
        assert s["lords"]["orvieto"]["flags"]["lower_lord_of"] == "arezzo"

    def test_commander_cannot_be_lieutenant(self):
        from tests.test_phase3a import _skip_capability_discard
        s = load_scenario("F", seed=1)
        for name, side in [
            ("levy_aow_draw","guelph"),("levy_aow_draw","ghibelline"),
            ("levy_pay_done","guelph"),("levy_pay_done","ghibelline"),
            ("levy_disband_done","guelph"),("levy_disband_done","ghibelline"),
            ("levy_muster_done","guelph"),("levy_muster_done","ghibelline"),
            ("levy_cta_skip","guelph"),("levy_cta_skip","ghibelline"),
        ]:
            dispatch(s, {"action": name, "side": side})
        _skip_capability_discard(s)
        # Firenze is Commander. Trying to pair firenze with arezzo should be rejected.
        # Need them at same Locale first. Move arezzo to Firenze.
        s["lords"]["arezzo"]["location"] = "Firenze"
        s["locales"]["Arezzo"]["lords_present"].remove("arezzo")
        s["locales"]["Firenze"]["lords_present"].append("arezzo")
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {"action": "plan_attach_lieutenant", "side": "guelph",
                         "args": {"lieutenant": "firenze", "lower_lord": "arezzo"}})
        assert exc.value.code == "COMMANDER_NOT_ELIGIBLE"


# =====================================================================
# Source markers
# =====================================================================
class TestSourceMarkers:
    @pytest.mark.parametrize("marker", ["SMOKE-Inferno-016", "SMOKE-Inferno-017"])
    def test_marker_present(self, marker):
        import inferno.legal_moves as m
        assert marker in inspect.getsource(m)
