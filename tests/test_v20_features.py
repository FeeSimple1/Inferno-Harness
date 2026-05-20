"""v2.0 text-resolvable defect fixes (batch #1-#4).

Regression coverage for:
  #1 SMOKE-Inferno-047  "Cart" vs "Carts" key       -> tests/test_v18_features.py
  #2 SMOKE-Inferno-048  Spoils Unladen carry 2*Carts -> tests/test_phase3d.py
  #3 SMOKE-Inferno-049  Treachery-Revolt -> 1.4.4 Exiles   (here)
  #4 SMOKE-Inferno-050  Combat removal (4.4.5) -> Revolt    (here)
"""
import inspect
import pytest

from inferno.scenarios import load_scenario
from inferno import static_data as sd
import inferno.actions as A


class _CountingRNG:
    """Minimal RNG stub: every roll() returns a fixed value and counts calls."""
    def __init__(self, value=1):
        self.value = value
        self.calls = 0

    def roll(self, context):
        self.calls += 1
        r = type("R", (), {})()
        r.value = self.value
        r.context = context
        return r


# =====================================================================
# #3 SMOKE-Inferno-049 — player Treachery-Revolt routes through the shared
# allegiance switch and surfaces the 1.4.4 Exiles step.
# =====================================================================
class TestTreacheryRevoltExiles:
    def test_success_surfaces_exiles(self):
        s = load_scenario("A", seed=1)
        # siena (Ghibelline) sits at Siena, adjacent to Montalcino — a Town
        # (size 2) currently held by Guelph (2 Guelph Allegiance markers),
        # printed Ghibelline. No Guelph Lord is at/adjacent to it.
        assert s["lords"]["siena"]["location"] == "Siena"
        mont = s["locales"]["Montalcino"]
        assert mont["type"] == "town"
        assert [m["side"] for m in mont["current_allegiance"]] == ["guelph", "guelph"]

        # Activate siena with Coin and an action; commit 4 Coin so a roll of 1
        # on each of the 2 dice is accepted.
        s["lords"]["siena"]["assets"]["Coin"] = 4
        s["current_lord_id"] = "siena"
        s["actions_remaining"] = 1
        s["current_card"] = "T_siena"
        s["meta"]["active_player"] = "ghibelline"

        before_exiles = len(s.get("pending_exiles", []))
        r = A._h_cmd_treachery_revolt(
            s, "ghibelline",
            {"lord_id": "siena", "target_locale": "Montalcino", "coin": 4},
            _CountingRNG(value=1),
        )
        tr = r["state_changes"]["treachery_revolt"]
        assert tr["accepted"] is True
        # Flip routed through revolt.apply_allegiance_switch.
        assert tr["switch"] is not None
        assert tr["switch"]["revolted"] == "Montalcino"
        # 1.4.4 Exiles surfaced for the LOSING (Guelph) side, count == the 2
        # Guelph markers that were removed.
        assert tr["exiles_required"] is not None
        assert tr["exiles_required"]["side"] == "guelph"
        assert tr["exiles_required"]["count"] == 2
        pend = s.get("pending_exiles", [])
        assert len(pend) == before_exiles + 1
        assert pend[-1]["side"] == "guelph" and pend[-1]["count"] == 2
        # Montalcino reverted to its printed (Ghibelline) Friendly state.
        assert all(m["side"] != "guelph" for m in
                   s["locales"]["Montalcino"]["current_allegiance"])

    def test_failed_revolt_no_exiles(self):
        s = load_scenario("A", seed=1)
        s["lords"]["siena"]["assets"]["Coin"] = 4
        s["current_lord_id"] = "siena"
        s["actions_remaining"] = 1
        s["current_card"] = "T_siena"
        s["meta"]["active_player"] = "ghibelline"
        before = len(s.get("pending_exiles", []))
        # value 6 > coin 4 on every die => not accepted.
        r = A._h_cmd_treachery_revolt(
            s, "ghibelline",
            {"lord_id": "siena", "target_locale": "Montalcino", "coin": 4},
            _CountingRNG(value=6),
        )
        tr = r["state_changes"]["treachery_revolt"]
        assert tr["accepted"] is False
        assert tr["switch"] is None
        assert tr["exiles_required"] is None
        assert len(s.get("pending_exiles", [])) == before

    def test_marker_present(self):
        assert "SMOKE-Inferno-049" in inspect.getsource(A._h_cmd_treachery_revolt)


# =====================================================================
# #4 SMOKE-Inferno-050 — a Lord removed by combat rolls on the Revolt table
# (1x regular, 3x Podesta) and adds Treachery cards, via a shared helper used
# by Battle, Storm-Sack, and Sally.
# =====================================================================
class TestCombatRemovalRevolt:
    def _guelph_lord(self, s):
        return next(lid for lid, l in s["lords"].items()
                    if l["side"] == "guelph" and l.get("status") == "mustered")

    def test_regular_lord_one_roll_one_treachery(self):
        s = load_scenario("A", seed=1)
        lid = self._guelph_lord(s)
        s["lords"][lid].pop("podesta", None)
        set_before = len(s["decks"]["ghibelline"]["treachery_set_aside"])
        cmd_before = len(s["decks"]["ghibelline"]["command_deck"])
        rng = _CountingRNG(value=1)
        res = A._trigger_disband_revolt_and_treachery(s, [lid], rng, "battle")
        # 1 Revolt roll == gold + purple die == 2 RNG calls.
        assert rng.calls == 2
        added = res["treachery_added"]
        assert len(added) == min(1, set_before)
        assert all(a["to_side"] == "ghibelline" for a in added)
        assert len(s["decks"]["ghibelline"]["command_deck"]) == cmd_before + len(added)

    def test_podesta_three_rolls_three_treachery(self):
        s = load_scenario("A", seed=1)
        lid = self._guelph_lord(s)
        s["lords"][lid]["podesta"] = True
        set_before = len(s["decks"]["ghibelline"]["treachery_set_aside"])
        rng = _CountingRNG(value=1)
        res = A._trigger_disband_revolt_and_treachery(s, [lid], rng, "battle")
        # Podesta = 3x => 3 Revolt rolls => 6 die rolls.
        assert rng.calls == 6
        assert len(res["treachery_added"]) == min(3, set_before)

    def test_comune_lord_no_revolt(self):
        s = load_scenario("A", seed=1)
        lid = self._guelph_lord(s)
        s["lords"][lid]["comune_of"] = "Firenze"
        rng = _CountingRNG(value=1)
        res = A._trigger_disband_revolt_and_treachery(s, [lid], rng, "battle")
        assert rng.calls == 0
        assert res["treachery_added"] == []

    def test_wired_into_all_three_combat_paths(self):
        # The shared trigger is invoked by Battle (_apply_post_battle), Storm
        # (_apply_sack), and Sally (_h_cmd_sally) — defined once, reused.
        for fn in (A._apply_post_battle, A._apply_sack, A._h_cmd_sally):
            assert "_trigger_disband_revolt_and_treachery" in inspect.getsource(fn)

    def test_marker_present(self):
        assert "SMOKE-Inferno-050" in inspect.getsource(A._trigger_disband_revolt_and_treachery)
