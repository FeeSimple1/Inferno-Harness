"""v3.2 — per-card NUMERIC verification of AoW Event effects.

Each test drives an Event handler against a controlled state and asserts the
EXACT numeric outcome the Arts of War reference specifies (boxes shifted,
assets moved, units removed, Lordship deltas), not merely that the effect
fired. This pass surfaced and corrected a cluster of Ghibelline-event defects
(SMOKE-076..079).
"""
from __future__ import annotations

from inferno import card_effects as ce
from inferno.rng import HarnessRNG
from inferno.scenarios import load_scenario


def _rng():
    return HarnessRNG(seed=1)


def _place_cyl(state, lid, box):
    state["lords"][lid]["calendar_box"] = box
    state["lords"][lid]["service_box"] = None


def _place_svc(state, lid, box):
    state["lords"][lid]["service_box"] = box
    state["lords"][lid]["calendar_box"] = None


# =====================================================================
# SMOKE-076 — S9 Pope at Bay: adverse shift of GUELPH lords / Orvieto by 3
# =====================================================================
class TestS9PopeAtBay:
    def test_shift_two_guelph_lords_right_one_box_and_set_aside_treachery(self):
        s = load_scenario("A", 1)
        # Put a Ghibelline Treachery card into the Command deck (acquired).
        s["decks"]["ghibelline"]["command_deck"].append("treachery_pisa")
        _place_cyl(s, "firenze", 5)
        _place_cyl(s, "arezzo", 6)
        r = ce.apply_event_effect(s, "S9", "ghibelline",
                                  {"targets": ["firenze", "arezzo"]}, _rng())
        assert r["applied"] is True
        assert r["treachery_set_aside"] == "treachery_pisa"
        # Cost paid: card left the Command deck and went to set-aside.
        assert "treachery_pisa" not in s["decks"]["ghibelline"]["command_deck"]
        assert "treachery_pisa" in s["decks"]["ghibelline"]["treachery_set_aside"]
        # Adverse = cylinders shift RIGHT by exactly 1.
        assert s["lords"]["firenze"]["calendar_box"] == 6
        assert s["lords"]["arezzo"]["calendar_box"] == 7

    def test_orvieto_by_three(self):
        s = load_scenario("A", 1)
        s["decks"]["ghibelline"]["command_deck"].append("treachery_siena")
        _place_cyl(s, "orvieto", 4)
        r = ce.apply_event_effect(s, "S9", "ghibelline", {"mode": "orvieto"}, _rng())
        assert r["applied"] is True
        assert s["lords"]["orvieto"]["calendar_box"] == 7  # 4 + 3

    def test_requires_treachery_in_command_deck(self):
        s = load_scenario("A", 1)
        # Ensure no Treachery card sits in the Command deck.
        s["decks"]["ghibelline"]["command_deck"] = [
            c for c in s["decks"]["ghibelline"]["command_deck"]
            if not c.startswith("treachery_")]
        r = ce.apply_event_effect(s, "S9", "ghibelline", {}, _rng())
        assert r["applied"] is False


# =====================================================================
# SMOKE-077 — S11 Volterra: Colle Service left 2 / Pisa cylinder to Levy
# =====================================================================
class TestS11Volterra:
    def test_colle_service_left_two(self):
        s = load_scenario("A", 1)
        s["locales"]["Volterra"]["current_allegiance"] = []  # Ghibelline (no Guelph marker)
        _place_svc(s, "colle", 5)
        r = ce.apply_event_effect(s, "S11", "ghibelline", {"mode": "colle"}, _rng())
        assert r["applied"] is True
        assert s["lords"]["colle"]["service_box"] == 3  # 5 - 2

    def test_pisa_cylinder_to_current_levy(self):
        s = load_scenario("A", 1)
        s["locales"]["Volterra"]["current_allegiance"] = []
        s["calendar"]["levy_box"] = 2
        _place_cyl(s, "pisa", 6)
        r = ce.apply_event_effect(s, "S11", "ghibelline", {"mode": "pisa"}, _rng())
        assert r["applied"] is True
        assert s["lords"]["pisa"]["calendar_box"] == 2

    def test_blocked_when_volterra_guelph(self):
        s = load_scenario("A", 1)
        s["locales"]["Volterra"]["current_allegiance"] = [{"side": "guelph", "value": 1}]
        r = ce.apply_event_effect(s, "S11", "ghibelline", {"mode": "colle"}, _rng())
        assert r["applied"] is False


# =====================================================================
# SMOKE-078 — S15 War Loans: shift one listed lord 2 boxes / Lordship +2
# =====================================================================
class TestS15WarLoans:
    def test_shift_cylinder_left_two(self):
        s = load_scenario("A", 1)
        _place_cyl(s, "giordano", 7)
        r = ce.apply_event_effect(s, "S15", "ghibelline", {"target": "giordano"}, _rng())
        assert r["applied"] is True
        assert s["lords"]["giordano"]["calendar_box"] == 5  # 7 - 2

    def test_lordship_plus_two(self):
        s = load_scenario("A", 1)
        r = ce.apply_event_effect(s, "S15", "ghibelline",
                                  {"target": "provenzano", "mode": "lordship"}, _rng())
        assert r["bonus"] == 2
        assert s["lords"]["provenzano"]["flags"]["lordship_bonus_pending"] == 2

    def test_rejects_unlisted_target(self):
        s = load_scenario("A", 1)
        r = ce.apply_event_effect(s, "S15", "ghibelline", {"target": "firenze"}, _rng())
        assert r["applied"] is False


# =====================================================================
# SMOKE-079 — F25/F26/S25/S26 War events: conditional Calendar shift
# =====================================================================
class TestWarEventShifts:
    def _mark_guelph(self, s, name):
        s["locales"][name]["current_allegiance"] = [{"side": "guelph", "value": 1}]

    def test_F25_colle_shift_3_when_ghib_castle_marked_guelph(self):
        s = load_scenario("A", 1)
        castle = next(n for n, l in s["locales"].items()
                      if l.get("type") == "castle" and l.get("allegiance") == "ghibelline")
        self._mark_guelph(s, castle)
        _place_svc(s, "colle", 5)
        r = ce.apply_event_effect(s, "F25", "guelph", {}, _rng())
        assert "guelph" in s["war_declared_this_levy"]
        assert s["lords"]["colle"]["service_box"] == 8  # 5 + 3 (favourable)

    def test_F25_no_shift_when_condition_unmet_but_cta_still_set(self):
        s = load_scenario("A", 1)
        for l in s["locales"].values():
            l["current_allegiance"] = [m for m in l.get("current_allegiance", [])
                                       if m.get("side") != "guelph"]
        _place_svc(s, "colle", 5)
        r = ce.apply_event_effect(s, "F25", "guelph", {}, _rng())
        assert r["shifted"] is None
        assert s["lords"]["colle"]["service_box"] == 5  # unchanged
        assert "guelph" in s["war_declared_this_levy"]

    def test_F26_three_lords_shift_1_when_ghib_town_marked_guelph(self):
        s = load_scenario("A", 1)
        town = next(n for n, l in s["locales"].items()
                    if l.get("type") == "town" and l.get("allegiance") == "ghibelline")
        self._mark_guelph(s, town)
        _place_cyl(s, "firenze", 5)
        _place_cyl(s, "arezzo", 6)
        _place_cyl(s, "orvieto", 7)
        ce.apply_event_effect(s, "F26", "guelph", {}, _rng())
        assert s["lords"]["firenze"]["calendar_box"] == 4
        assert s["lords"]["arezzo"]["calendar_box"] == 5
        assert s["lords"]["orvieto"]["calendar_box"] == 6

    def test_S25_three_ghib_shift_1_when_maremma_marked_guelph(self):
        s = load_scenario("A", 1)
        self._mark_guelph(s, "Grosseto")
        _place_cyl(s, "siena", 5)
        _place_cyl(s, "provenzano", 6)
        _place_cyl(s, "pisa", 7)
        r = ce.apply_event_effect(s, "S25", "ghibelline",
                                  {"targets": ["siena", "provenzano", "pisa"]}, _rng())
        assert "ghibelline" in s["war_declared_this_levy"]
        assert s["lords"]["siena"]["calendar_box"] == 4
        assert s["lords"]["provenzano"]["calendar_box"] == 5
        assert s["lords"]["pisa"]["calendar_box"] == 6

    def test_S26_provenzano_siena_shift_1_when_ghib_town_marked_guelph(self):
        s = load_scenario("A", 1)
        town = next(n for n, l in s["locales"].items()
                    if l.get("type") == "town" and l.get("allegiance") == "ghibelline")
        self._mark_guelph(s, town)
        _place_cyl(s, "provenzano", 5)
        _place_cyl(s, "siena", 6)
        ce.apply_event_effect(s, "S26", "ghibelline", {}, _rng())
        assert s["lords"]["provenzano"]["calendar_box"] == 4
        assert s["lords"]["siena"]["calendar_box"] == 5


# =====================================================================
# Regression coverage of already-correct numeric events (sanity anchors)
# =====================================================================
class TestExistingNumericAnchors:
    def test_F22_remove_three_assets_cap(self):
        s = load_scenario("A", 1)
        lid = "firenze"
        s["lords"][lid].setdefault("forces", {})["Ritter"] = 1
        s["lords"][lid]["assets"] = {"Coin": 5}
        r = ce.apply_event_effect(s, "F22", "guelph",
                                  {"target_lord_id": lid, "mode": "remove_assets",
                                   "assets_to_remove": {"Coin": 3}}, _rng())
        assert r["applied"] is True
        assert s["lords"][lid]["assets"]["Coin"] == 2  # 5 - 3

    def test_F22_remove_more_than_three_rejected(self):
        s = load_scenario("A", 1)
        lid = "firenze"
        s["lords"][lid].setdefault("forces", {})["Ritter"] = 1
        s["lords"][lid]["assets"] = {"Coin": 5}
        r = ce.apply_event_effect(s, "F22", "guelph",
                                  {"target_lord_id": lid, "mode": "remove_assets",
                                   "assets_to_remove": {"Coin": 4}}, _rng())
        assert r["applied"] is False

    def test_S21_constituto_lordship_plus_3(self):
        s = load_scenario("A", 1)
        r = ce.apply_event_effect(s, "S21", "ghibelline",
                                  {"target": "siena", "mode": "lordship"}, _rng())
        assert r["bonus"] == 3
        assert s["lords"]["siena"]["flags"]["lordship_bonus_pending"] == 3

    def test_F14_provenzano_shift_2_requires_guelph_siege(self):
        s = load_scenario("A", 1)
        # No Guelph Siege -> not applicable.
        r = ce.apply_event_effect(s, "F14", "guelph", {}, _rng())
        assert r["applied"] is False
