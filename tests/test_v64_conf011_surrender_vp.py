"""v6.4 — CONF-011: Surrender Allegiance flip + VP via the shared 1.3.1/5.1 logic.

RoP 4.5.1: surrender sets the Stronghold to the Besieger's Allegiance "either
placing markers equal to its Value OR removing markers already there; adjust
Victory (5.1)". The prior _apply_surrender ALWAYS placed `size` Besieger markers
and did vp[side]+=size / vp[enemy]-=size, which (a) over-placed markers (and so
over-counted final VP) when the Stronghold's PRINTED Allegiance was already the
Besieger's, and (b) over-subtracted enemy VP when the enemy held fewer than
`size` markers (feeding the running-VP 4-VP Call-to-Arms trigger).
"""
from __future__ import annotations

from inferno.actions import _apply_surrender, _compute_final_vp
from inferno.scenarios import load_scenario
from inferno.rng import HarnessRNG


def _rng():
    return HarnessRNG(seed=1)


class TestSurrenderVP:
    def test_printed_enemy_unmarked_does_not_oversubtract_enemy_vp(self):
        s = load_scenario("A", 1)
        loc = "Volterra"  # printed-Ghibelline Town (Value 2), unmarked at start
        assert s["locales"][loc]["allegiance"] == "ghibelline"
        assert not (s["locales"][loc].get("current_allegiance") or [])
        s["decks"]["guelph"]["treachery_set_aside"] = ["treachery_x1", "treachery_x2"]
        vp_g0 = s["vp"]["guelph"]; vp_h0 = s["vp"]["ghibelline"]
        _apply_surrender(s, loc, "guelph", _rng(), [])
        # Besieger places Value=2 Guelph markers -> +2; enemy held 0 -> -0.
        assert sum(1 for m in s["locales"][loc]["current_allegiance"]
                   if m["side"] == "guelph") == 2
        assert s["vp"]["guelph"] == vp_g0 + 2
        assert s["vp"]["ghibelline"] == vp_h0           # NOT -2

    def test_besieger_printed_reverts_to_friendly_no_markers(self):
        s = load_scenario("A", 1)
        # A Guelph-PRINTED stronghold currently flipped to Ghibelline (2 markers).
        loc = "Firenze"  # printed-Guelph City (Value 3)
        assert s["locales"][loc]["allegiance"] == "guelph"
        s["locales"][loc]["current_allegiance"] = [{"side": "ghibelline", "value": 1},
                                                   {"side": "ghibelline", "value": 1}]
        vp_g0 = s["vp"]["guelph"]; vp_h0 = s["vp"]["ghibelline"]
        s["decks"]["guelph"]["treachery_set_aside"] = ["t1", "t2", "t3"]
        _apply_surrender(s, loc, "guelph", _rng(), [])
        # Reverts to printed-Friendly: NO markers placed (printed Guelph = 0 VP).
        assert s["locales"][loc]["current_allegiance"] == []
        assert s["vp"]["guelph"] == vp_g0               # +0, not +3
        # Enemy loses the 2 markers it actually held.
        assert s["vp"]["ghibelline"] == max(0, vp_h0 - 2)
        # Siege cleared.
        assert s["locales"][loc]["siege"] == []

    def test_final_vp_not_inflated_on_besieger_printed_surrender(self):
        s = load_scenario("A", 1)
        loc = "Firenze"
        s["locales"][loc]["current_allegiance"] = [{"side": "ghibelline", "value": 1}]
        _apply_surrender(s, loc, "guelph", _rng(), [])
        g, h = _compute_final_vp(s)
        # Firenze contributes 0 marker-VP to Guelph (printed-Friendly, no marker).
        assert not s["locales"][loc]["current_allegiance"]


class TestEncampClearsAllBypassers:
    """CONF-012: Encamp replaces the Bypass with a Siege, converting EVERY
    Bypassing Lord at the Locale into a Besieger — no co-located Lord may be
    left flagged Bypassing a now-Besieged Locale (4.3.5/4.3.6)."""

    def test_encamp_clears_colocated_bypasser_flag(self):
        from inferno.actions import dispatch
        from tests.test_phase3c import _to_command_with
        s = _to_command_with("A", seed=1, lord_id="firenze",
                             lord_location_override="Volterra")
        # A second Guelph Lord also Bypassing Volterra.
        other = "lucca"
        cur = s["lords"][other].get("location")
        if cur and other in s["locales"].get(cur, {}).get("lords_present", []):
            s["locales"][cur]["lords_present"].remove(other)
        s["lords"][other]["status"] = "mustered"
        s["lords"][other]["location"] = "Volterra"
        s["locales"]["Volterra"]["lords_present"].append(other)
        s["lords"][other].setdefault("flags", {})["bypassing"] = "Volterra"

        dispatch(s, {"action": "besiege_or_bypass", "side": "guelph",
                     "args": {"lord_id": "firenze", "choice": "bypass"}})
        dispatch(s, {"action": "cmd_encamp", "side": "guelph",
                     "args": {"lord_id": "firenze"}})

        assert s["locales"]["Volterra"]["siege"]
        assert s["locales"]["Volterra"]["bypass"] == []
        # BOTH Lords are now Besiegers — neither retains a Bypassing flag.
        assert s["lords"]["firenze"]["flags"].get("bypassing") is None
        assert s["lords"][other]["flags"].get("bypassing") is None
