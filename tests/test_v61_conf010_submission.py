"""v6.1 — CONF-010: SUBMISSION targets must be MARKED with Enemy Allegiance.

RoP 1.4.2 SUBMISSION: "select a Stronghold marked with Enemy Allegiance
(only, not printed Allegiance) ... at or adjacent to which the rolling side
has a Lord cylinder." The harness previously reused is_eligible_for_revolt,
which accepts a printed-enemy Stronghold with NO Allegiance markers (53/57
Strongholds start printed-only), so SUBMISSION could illegally flip an
un-marked printed-enemy Stronghold.
"""
from __future__ import annotations

from inferno import revolt as rv
from inferno.scenarios import load_scenario
from inferno import static_data as sd


def _place_ghib_cylinder_at(s, locale):
    gid = next(lid for lid, l in s["lords"].items() if l["side"] == "ghibelline")
    s["lords"][gid]["status"] = "mustered"
    old = s["lords"][gid].get("location")
    if old and gid in s["locales"].get(old, {}).get("lords_present", []):
        s["locales"][old]["lords_present"].remove(gid)
    s["lords"][gid]["location"] = locale
    s["locales"][locale].setdefault("lords_present", []).append(gid)
    return gid


def _clear_guelph_lords_near(s, name):
    near = {name} | {n for n, _ in sd.adjacent_to(name)}
    for n in near:
        loc = s["locales"].get(n)
        if not loc:
            continue
        for lid in list(loc.get("lords_present", [])):
            if s["lords"][lid]["side"] == "guelph":
                loc["lords_present"].remove(lid)


class TestSubmissionMarkedOnly:
    def test_unmarked_printed_enemy_is_NOT_a_submission_target(self):
        """The core regression: a printed-Ghibelline Stronghold with no
        markers must not be offered as a SUBMISSION flip to the Guelphs."""
        s = load_scenario("A", seed=1)
        # Rolling side = guelph (losing_side = ghibelline). SUBMISSION cell in
        # the vs-Ghibelline table is e.g. (gold=1, purple=6).
        # Pisa is printed-ghibelline and unmarked at start.
        assert s["locales"]["Pisa"]["allegiance"] == "ghibelline"
        assert not (s["locales"]["Pisa"].get("current_allegiance") or [])
        # Give the Guelphs a cylinder at Pisa so only the marked-ness gates it.
        gid = next(lid for lid, l in s["lords"].items() if l["side"] == "guelph")
        s["lords"][gid]["status"] = "mustered"
        s["lords"][gid]["location"] = "Pisa"
        s["locales"]["Pisa"].setdefault("lords_present", []).append(gid)
        r = rv.resolve_revolt(s, "ghibelline", 1, 6)  # SUBMISSION
        # Pisa (unmarked) must not be a candidate / forced flip.
        if r["status"] == "decision_required":
            assert "Pisa" not in r["decision"]["candidates"]
        else:
            assert r.get("forced_choice") != "Pisa"
            assert r["status"] in ("no_effect", "resolved")
            if r["status"] == "resolved":
                assert r["switch"]["revolted"] != "Pisa"

    def test_marked_enemy_stronghold_IS_a_valid_submission_target(self):
        s = load_scenario("A", seed=1)
        # Mark Volterra (a town) with Ghibelline Allegiance, give Guelph cylinder.
        v = s["locales"]["Volterra"]
        v["current_allegiance"] = [{"side": "ghibelline", "value": 1},
                                   {"side": "ghibelline", "value": 1}]
        v["ruins"] = None
        _clear_guelph_lords_near(s, "Volterra")
        # Remove any ghibelline lord at/adjacent (eligibility 1.4.1) then add
        # a Guelph cylinder at Volterra for presence.
        near = {"Volterra"} | {n for n, _ in sd.adjacent_to("Volterra")}
        for n in near:
            loc = s["locales"].get(n)
            if loc:
                loc["lords_present"] = [lid for lid in loc.get("lords_present", [])
                                        if s["lords"][lid]["side"] != "ghibelline"]
        gid = next(lid for lid, l in s["lords"].items() if l["side"] == "guelph")
        s["lords"][gid]["status"] = "mustered"
        s["lords"][gid]["location"] = "Volterra"
        s["locales"]["Volterra"].setdefault("lords_present", []).append(gid)
        r = rv.resolve_revolt(s, "ghibelline", 1, 6)  # SUBMISSION (vs-ghib table)
        if r["status"] == "decision_required":
            assert "Volterra" in r["decision"]["candidates"]
            r = rv.resolve_revolt(s, "ghibelline", 1, 6, choice="Volterra")
        assert r["status"] == "resolved"
        assert r["switch"]["revolted"] == "Volterra"
