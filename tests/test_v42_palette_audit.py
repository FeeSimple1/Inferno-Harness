"""v4.2: validated agent-facing palette (SMOKE-Inferno-092) + negative
enumerator tests guarding the v4.0/v4.1 placement fixes."""
import sys, os, copy, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest
from inferno.scenarios import load_scenario, SCENARIO_IDS
import inferno.legal_moves as LM
from inferno.legal_moves import enumerate_legal, enumerate_legal_validated
from inferno.actions import dispatch, IllegalAction


def _to_muster_step(scenario="B", seed=1):
    s = load_scenario(scenario, seed=seed)
    for nm, side in [("levy_aow_draw", "guelph"), ("levy_aow_draw", "ghibelline"),
                     ("levy_pay_done", "guelph"), ("levy_pay_done", "ghibelline"),
                     ("levy_disband_done", "guelph"), ("levy_disband_done", "ghibelline")]:
        dispatch(s, {"action": nm, "side": side})
    return s


class TestValidatedPalette:
    def test_every_kept_move_is_dispatchable(self):
        # On a fresh state, every move the palette KEEPS must apply cleanly.
        for sc in SCENARIO_IDS:
            s = load_scenario(sc, seed=3)
            pal = enumerate_legal_validated(s)
            for m in pal["moves"]:
                probe = copy.deepcopy(s)
                dispatch(probe, {k: m[k] for k in ("action", "side", "args") if k in m})

    def test_clean_state_has_no_dropped(self):
        s = load_scenario("B", seed=1)
        pal = enumerate_legal_validated(s)
        assert pal["dropped"] == []

    def test_palette_drops_planted_over_enumeration(self, monkeypatch):
        s = load_scenario("B", seed=1)
        real = LM.enumerate_legal

        def poisoned(state):
            moves = list(real(state))
            # A guaranteed-illegal candidate (no such Lord / bad muster).
            moves.append({"action": "levy_muster_lord", "side": "guelph",
                          "args": {"muster_lord_id": "firenze",
                                   "target_lord_id": "firenze", "target_seat": "Nowhere"}})
            return moves
        monkeypatch.setattr(LM, "enumerate_legal", poisoned)
        pal = enumerate_legal_validated(s)
        assert any(d["move"]["args"].get("target_seat") == "Nowhere" for d in pal["dropped"])
        assert all(m.get("args", {}).get("target_seat") != "Nowhere" for m in pal["moves"])

    def test_self_play_never_over_enumerates(self):
        # Strong invariant: across self-play, the validated palette must never
        # drop a candidate (enumerator/handler stay in agreement).
        s = load_scenario("B", seed=2)
        rng = random.Random(2)
        for _ in range(150):
            pal = enumerate_legal_validated(s)
            assert pal["dropped"] == [], f"over-enumeration: {pal['dropped'][:2]}"
            moves = [m for m in pal["moves"] if not m.get("action", "").startswith("<")]
            if not moves:
                break
            m = rng.choice(moves)
            dispatch(s, {k: m[k] for k in ("action", "side", "args") if k in m})
            if s["meta"].get("phase") == "victory":
                break


class TestNegativeEnumeratorMuster:
    """SMOKE-Inferno-087: the menu must NOT offer an illegal Muster Seat."""
    def test_nonpodesta_besieged_seat_not_offered(self):
        s = _to_muster_step("B", seed=1)
        tlid, seat = "orvieto", "Orvieto"
        s["lords"][tlid]["calendar_box"] = s["calendar"]["levy_box"]  # force Ready
        loc = s["locales"][seat]
        loc["siege"] = [{"side": "ghibelline", "color": "gold", "count": 1}]
        # park enemy besieger
        old = s["lords"]["siena"]["location"]
        if old and "siena" in s["locales"][old]["lords_present"]:
            s["locales"][old]["lords_present"].remove("siena")
        s["lords"]["siena"]["location"] = seat
        if "siena" not in loc["lords_present"]:
            loc["lords_present"].append("siena")
        s["lords"]["siena"].setdefault("flags", {})["in_stronghold"] = False
        offered = [m for m in enumerate_legal(s) if m["action"] == "levy_muster_lord"
                   and m["args"].get("target_lord_id") == tlid and m["args"].get("target_seat") == seat]
        assert offered == [], "non-Podesta Muster onto an Enemy-besieged Seat must NOT be offered"

    def test_podesta_besieged_main_seat_is_offered(self):
        # Positive control: the Urban-Army exception IS offered (Podesta, Main Seat).
        s = _to_muster_step("B", seed=1)
        tlid, seat = "colle", "Colle"
        s["lords"][tlid]["calendar_box"] = s["calendar"]["levy_box"]
        loc = s["locales"][seat]
        loc["siege"] = [{"side": "ghibelline", "color": "gold", "count": 1}]
        old = s["lords"]["siena"]["location"]
        if old and "siena" in s["locales"][old]["lords_present"]:
            s["locales"][old]["lords_present"].remove("siena")
        s["lords"]["siena"]["location"] = seat
        if "siena" not in loc["lords_present"]:
            loc["lords_present"].append("siena")
        s["lords"]["siena"].setdefault("flags", {})["in_stronghold"] = False
        offered = [m for m in enumerate_legal(s) if m["action"] == "levy_muster_lord"
                   and m["args"].get("target_lord_id") == tlid and m["args"].get("target_seat") == seat]
        assert offered, "Podesta Urban-Army Muster at his Besieged Main Seat should be offered"
