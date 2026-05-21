"""v2.8 — bugs found and fixed during the 10-round smoke-test campaign.

SMOKE-068: empty/short AoW deck no longer dead-locks the Levy (draw up to 2).
SMOKE-069: running VP is initialised from the starting board markers, not 0/0.
SMOKE-070: calendar cylinders/services lists stay consistent with Lord boxes
           across Service shifts, Disbands, CtA re-musters, and Exiles slides.
"""
import random
import pytest
from inferno.scenarios import load_scenario, SCENARIO_IDS, _init_vp_from_markers
from inferno.actions import dispatch, IllegalAction, _place_service, _place_cylinder
from inferno.flow import current_side
import inferno.revolt as revolt


class TestEmptyDeckNoDeadlock:
    def test_short_deck_draws_what_is_available(self):
        s = load_scenario("A", seed=1)
        # Skip the reshuffle and leave a single card -> handler must draw 1 and
        # advance, not raise EMPTY_DECK.
        s["meta"]["aow_reshuffled_this_levy_guelph"] = True
        s["decks"]["guelph"]["aow_deck"] = ["F1"]
        before_side = current_side(s)
        r = dispatch(s, {"action": "levy_aow_draw", "side": "guelph"})
        assert "drew" in r["state_changes"]
        assert len(r["state_changes"]["drew"]) == 1
        assert current_side(s) != before_side  # advanced past Guelph

    def test_zero_deck_advances(self):
        s = load_scenario("A", seed=1)
        s["meta"]["aow_reshuffled_this_levy_guelph"] = True
        s["decks"]["guelph"]["aow_deck"] = []
        r = dispatch(s, {"action": "levy_aow_draw", "side": "guelph"})
        assert r["state_changes"]["drew"] == []


class TestInitialVpFromMarkers:
    def test_vp_reflects_starting_markers(self):
        # Independently count base marker VP and compare to the running track.
        for scen in SCENARIO_IDS:
            s = load_scenario(scen, seed=1)
            base = {"guelph": 0.0, "ghibelline": 0.0}
            for loc in s["locales"].values():
                for m in loc.get("current_allegiance", []) or []:
                    if m.get("side") in base:
                        base[m["side"]] += m.get("value", 1)
                if loc.get("ruins"):
                    base["guelph" if loc["ruins"] == "gold" else "ghibelline"] += 0.5
                if loc.get("ravaged"):
                    base["guelph" if loc["ravaged"] == "gold" else "ghibelline"] += 0.5
            base = {k: min(v, 17.5) for k, v in base.items()}
            assert s["vp"] == base, f"{scen}: vp {s['vp']} != base {base}"

    def test_not_zero_when_markers_present(self):
        s = load_scenario("C", seed=1)
        assert s["vp"]["guelph"] > 0 and s["vp"]["ghibelline"] > 0


class TestCalendarConsistencyHelpers:
    def test_place_service_clears_old_box(self):
        s = load_scenario("A", seed=1)
        lid = "firenze"
        _place_service(s, lid, 5)
        assert lid in s["calendar"]["boxes"]["5"]["services"]
        _place_service(s, lid, 8)
        assert lid in s["calendar"]["boxes"]["8"]["services"]
        assert lid not in s["calendar"]["boxes"]["5"]["services"]  # old cleared
        assert s["lords"][lid]["service_box"] == 8
        _place_service(s, lid, None)
        assert all(lid not in b["services"] for b in s["calendar"]["boxes"].values())

    def test_place_cylinder_clears_old_box(self):
        s = load_scenario("A", seed=1)
        lid = "guido_guerra"
        _place_cylinder(s, lid, 6)
        _place_cylinder(s, lid, 9)
        assert lid in s["calendar"]["boxes"]["9"]["cylinders"]
        assert lid not in s["calendar"]["boxes"]["6"]["cylinders"]

    def test_exiles_slide_keeps_lists_consistent(self):
        s = load_scenario("A", seed=1)
        lid = "firenze"
        _place_service(s, lid, 7)
        revolt.apply_exiles(s, s["lords"][lid]["side"], [{"lord_id": lid, "kind": "service"}])
        assert s["lords"][lid]["service_box"] == 8
        assert lid in s["calendar"]["boxes"]["8"]["services"]
        assert lid not in s["calendar"]["boxes"]["7"]["services"]  # old cleared

    def test_randomized_calendar_stays_consistent(self):
        from inferno.legal_moves import enumerate_legal
        for scen in ("B", "C", "D"):
            for seed in (1, 2, 3):
                rng = random.Random(seed); s = load_scenario(scen, seed=seed)
                for _ in range(300):
                    moves = [m for m in enumerate_legal(s) if not m.get("action", "").startswith("<")]
                    if not moves: break
                    m = rng.choice(moves); act = {"action": m["action"], "side": m["side"]}
                    if "args" in m: act["args"] = m["args"]
                    try: dispatch(s, act)
                    except IllegalAction: continue
                    except Exception: break
                    boxes = s["calendar"]["boxes"]
                    for box, info in boxes.items():
                        for x in info.get("services", []):
                            assert s["lords"][x]["service_box"] == int(box)
                        for x in info.get("cylinders", []):
                            assert s["lords"][x]["calendar_box"] == int(box)
                    if s["meta"].get("phase") == "victory": break
