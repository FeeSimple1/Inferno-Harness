"""v6.0 — Conformance fixes CONF-008 (F14 shift direction) and
CONF-009 (F2/S2 Betrayals OR-choice, no phantom Revolt roll).

Both defects were surfaced by the Arts-of-War numeric conformance audit and
were invisible to the prior tests (which only checked F14's no-Siege case and
that F2 added *a* Treachery, never the shift direction or the double-apply).
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


def _plant_guelph_siege(state, locale="Volterra", n=1):
    state["locales"][locale]["siege"] = [
        {"side": "guelph", "color": "gold", "count": n}
    ]


# ---------------------------------------------------------------------------
# CONF-008 — F14 PROVENZANO: adverse shift (cylinder RIGHT / Service LEFT)
# ---------------------------------------------------------------------------
class TestF14ShiftDirection:
    def test_cylinder_shifts_right_two_boxes(self):
        """Provenzano is an ENEMY of the Guelphs: F14 must DELAY him
        (cylinder right +2), not advance him."""
        s = load_scenario("A", 1)
        _plant_guelph_siege(s)
        _place_cyl(s, "provenzano", 6)
        r = ce.apply_event_effect(s, "F14", "guelph", {}, _rng())
        assert r["applied"] is True
        assert s["lords"]["provenzano"]["calendar_box"] == 8  # 6 -> 8 (RIGHT)
        # And the cylinder list bookkeeping followed the move.
        boxes = s["calendar"]["boxes"]
        assert "provenzano" not in boxes["6"]["cylinders"]
        assert "provenzano" in boxes["8"]["cylinders"]

    def test_service_shifts_left_two_boxes_when_mustered(self):
        s = load_scenario("A", 1)
        _plant_guelph_siege(s)
        _place_svc(s, "provenzano", 9)
        r = ce.apply_event_effect(s, "F14", "guelph", {}, _rng())
        assert r["applied"] is True
        assert s["lords"]["provenzano"]["service_box"] == 7  # 9 -> 7 (LEFT)

    def test_mode_service_forces_service_left_even_with_cylinder(self):
        s = load_scenario("A", 1)
        _plant_guelph_siege(s)
        s["lords"]["provenzano"]["calendar_box"] = 6
        s["lords"]["provenzano"]["service_box"] = 9
        r = ce.apply_event_effect(s, "F14", "guelph", {"mode": "service"}, _rng())
        assert r["applied"] is True
        assert s["lords"]["provenzano"]["service_box"] == 7

    def test_requires_guelph_siege(self):
        s = load_scenario("A", 1)
        r = ce.apply_event_effect(s, "F14", "guelph", {}, _rng())
        assert r["applied"] is False


# ---------------------------------------------------------------------------
# CONF-009 — F2/S2 BETRAYALS: OR-choice, default all-Treachery, no phantom roll
# ---------------------------------------------------------------------------
class TestBetrayalsOrChoice:
    def _seed_set_aside(self, s, side, n):
        s["decks"][side]["treachery_set_aside"] = [
            f"treachery_card_{i}" for i in range(n)
        ]

    def test_default_adds_one_treachery_per_siege_no_revolt_roll(self):
        s = load_scenario("A", 1)
        s["locales"]["Volterra"]["siege"] = [{"side": "guelph", "color": "gold", "count": 1}]
        s["locales"]["Colle"]["siege"] = [{"side": "guelph", "color": "gold", "count": 1}]
        self._seed_set_aside(s, "guelph", 5)
        before = len(s["decks"]["guelph"]["command_deck"])
        r = ce.apply_event_effect(s, "F2", "guelph", {}, _rng())
        assert r["sieges"] == 2
        assert r["revolt_count"] == 0
        # Two Treachery added (one per Siege); NO phantom revolt rolls logged.
        assert len(r["treachery_added"]) == 2
        assert "rolls" not in r
        assert "revolts" not in r
        assert len(s["decks"]["guelph"]["command_deck"]) == before + 2

    def test_revolt_count_splits_between_revolt_and_treachery(self):
        s = load_scenario("A", 1)
        for loc in ("Volterra", "Colle"):
            s["locales"][loc]["siege"] = [{"side": "guelph", "color": "gold", "count": 1}]
        self._seed_set_aside(s, "guelph", 5)
        before = len(s["decks"]["guelph"]["command_deck"])
        r = ce.apply_event_effect(s, "F2", "guelph", {"revolt_count": 1}, _rng())
        assert r["sieges"] == 2
        assert r["revolt_count"] == 1
        # 1 Treachery added, 1 Revolt actually triggered (real revolt machinery).
        assert len(r["treachery_added"]) == 1
        assert "revolts" in r
        assert len(s["decks"]["guelph"]["command_deck"]) == before + 1

    def test_s2_mirrors_f2(self):
        s = load_scenario("A", 1)
        s["locales"]["Volterra"]["siege"] = [{"side": "ghibelline", "color": "purple", "count": 1}]
        self._seed_set_aside(s, "ghibelline", 3)
        r = ce.apply_event_effect(s, "S2", "ghibelline", {}, _rng())
        assert r["sieges"] == 1
        assert len(r["treachery_added"]) == 1
        assert "rolls" not in r

    def test_no_sieges_noop(self):
        s = load_scenario("A", 1)
        r = ce.apply_event_effect(s, "F2", "guelph", {}, _rng())
        assert r["applied"] is True and r["no_sieges"] is True
