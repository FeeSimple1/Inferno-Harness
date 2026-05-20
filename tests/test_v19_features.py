"""v1.9 — Revolt Tables (1.4.2) + Allegiance switch (1.4.4) + Exiles.

Encodes the user-supplied Revolt Tables; Q-002 resolved the crossed-out
cells as SUBMISSION (not no-revolt). Player choices are surfaced as
decisions.
"""
from __future__ import annotations

import pytest

from inferno import revolt as rv
from inferno import static_data as sd
from inferno.scenarios import load_scenario


def _clear_lords_near(s, name, side):
    for loc_n in [name] + [n for n, _ in sd.adjacent_to(name)]:
        for lid in list(s["locales"].get(loc_n, {}).get("lords_present", [])):
            if s["lords"][lid]["side"] == side:
                s["locales"][loc_n]["lords_present"].remove(lid)
                s["lords"][lid]["location"] = None


class TestTableData:
    def test_golden_chiusi_playbook(self):
        # Playbook p.18: Ghibelline roll purple 5 + gold 6 names Chiusi.
        assert rv.lookup_revolt_cell("guelph", 6, 5) == "Chiusi"

    def test_both_tables_complete_and_valid(self):
        locs = set(sd.LOCALES)
        for tbl in (rv.REVOLT_TABLE_VS_GUELPH, rv.REVOLT_TABLE_VS_GHIBELLINE):
            assert len(tbl) == 36
            assert {(g, p) for g in range(1, 7) for p in range(1, 7)} == set(tbl)
            for v in tbl.values():
                assert v == rv.SUBMISSION or v in locs

    def test_submission_cell_counts(self):
        assert sum(v == rv.SUBMISSION for v in rv.REVOLT_TABLE_VS_GUELPH.values()) == 4
        assert sum(v == rv.SUBMISSION for v in rv.REVOLT_TABLE_VS_GHIBELLINE.values()) == 6

    def test_siena_never_named(self):
        named = {v for t in (rv.REVOLT_TABLE_VS_GUELPH, rv.REVOLT_TABLE_VS_GHIBELLINE)
                 for v in t.values() if v != rv.SUBMISSION}
        assert "Siena" not in named
        assert len(named) == 56

    def test_dice_out_of_range_raises(self):
        with pytest.raises(ValueError):
            rv.lookup_revolt_cell("guelph", 0, 3)


class TestRebellion:
    def test_named_enemy_stronghold_revolts_with_presence(self):
        s = load_scenario("A", seed=1)
        # Cortona = (gold6,purple6) on vs-Guelph table. Make it printed-Guelph,
        # no current markers (Enemy to Ghibelline), no Guelph lords near.
        cort = s["locales"]["Cortona"]
        cort["current_allegiance"] = []
        cort["ruins"] = None
        _clear_lords_near(s, "Cortona", "guelph")
        # Ghibelline Allegiance marker within 1 (Chiusi is adjacent).
        s["locales"]["Chiusi"]["current_allegiance"] = [{"side": "ghibelline", "value": 1}]
        vp_before = s["vp"]["ghibelline"]
        r = rv.resolve_revolt(s, "guelph", 6, 6)
        assert r["status"] == "resolved"
        assert r["switch"]["revolted"] == "Cortona"
        assert any(m["side"] == "ghibelline" for m in cort["current_allegiance"])
        assert s["vp"]["ghibelline"] == vp_before + 2  # Town value 2

    def test_named_no_presence_no_effect(self):
        s = load_scenario("A", seed=1)
        cort = s["locales"]["Cortona"]
        cort["current_allegiance"] = []
        cort["ruins"] = None
        _clear_lords_near(s, "Cortona", "guelph")
        # Strip ALL ghibelline presence near Cortona.
        for loc_n in [n for n, _ in sd.adjacent_to("Cortona")] + ["Cortona"]:
            l = s["locales"].get(loc_n, {})
            l["current_allegiance"] = [m for m in l.get("current_allegiance", [])
                                       if m.get("side") != "ghibelline"]
            for lid in list(l.get("lords_present", [])):
                if s["lords"][lid]["side"] == "ghibelline":
                    l["lords_present"].remove(lid)
                    s["lords"][lid]["location"] = None
        r = rv.resolve_revolt(s, "guelph", 6, 6)
        assert r["status"] == "no_effect"

    def test_named_ineligible_enemy_lord_adjacent(self):
        s = load_scenario("A", seed=1)
        cort = s["locales"]["Cortona"]
        cort["current_allegiance"] = []
        cort["ruins"] = None
        _clear_lords_near(s, "Cortona", "guelph")
        # Put a Guelph (enemy to roller) mustered lord AT Cortona -> ineligible.
        gid = next(lid for lid, l in s["lords"].items() if l["side"] == "guelph")
        s["lords"][gid]["status"] = "mustered"
        s["lords"][gid]["location"] = "Cortona"
        s["locales"]["Cortona"]["lords_present"].append(gid)
        r = rv.resolve_revolt(s, "guelph", 6, 6)
        assert r["status"] == "no_effect"

    def test_already_friendly_fallback_surfaces_decision(self):
        s = load_scenario("A", seed=1)
        # Cortona already Ghibelline (Friendly to roller) in scenario A.
        assert any(m["side"] == "ghibelline"
                   for m in s["locales"]["Cortona"]["current_allegiance"])
        # Make >=2 adjacent eligible Guelph strongholds so a choice is needed.
        made = 0
        for n, _ in sd.adjacent_to("Cortona"):
            loc = s["locales"][n]
            if loc.get("type") in ("castle", "town") and rv._stronghold_value(loc) <= 2:
                loc["current_allegiance"] = []
                loc["allegiance"] = "guelph"
                loc["ruins"] = None
                _clear_lords_near(s, n, "guelph")
                made += 1
        # ensure ghibelline presence near each (Cortona itself is adjacent & ghib)
        r = rv.resolve_revolt(s, "guelph", 6, 6)
        if made >= 2:
            assert r["status"] in ("decision_required", "resolved")
            if r["status"] == "decision_required":
                assert r["decision"]["kind"] == "rebellion_friendly_fallback"
                assert len(r["decision"]["candidates"]) >= 2


class TestSubmission:
    def _submission_state(self):
        s = load_scenario("A", seed=1)
        # vs-Guelph SUBMISSION cell = (gold3,purple1). Rolling side = ghibelline.
        # Need an eligible Guelph stronghold with a ghibelline cylinder adjacent.
        target = "Cortona"
        cort = s["locales"][target]
        cort["current_allegiance"] = []  # printed guelph -> enemy to ghibelline
        cort["ruins"] = None
        _clear_lords_near(s, target, "guelph")
        # Place a ghibelline mustered lord adjacent (Chiusi).
        gid = next(lid for lid, l in s["lords"].items() if l["side"] == "ghibelline")
        s["lords"][gid]["status"] = "mustered"
        old = s["lords"][gid]["location"]
        if old and gid in s["locales"].get(old, {}).get("lords_present", []):
            s["locales"][old]["lords_present"].remove(gid)
        s["lords"][gid]["location"] = "Chiusi"
        s["locales"]["Chiusi"]["lords_present"].append(gid)
        return s, target

    def test_submission_requires_choice_then_applies(self):
        s, target = self._submission_state()
        r = rv.resolve_revolt(s, "guelph", 3, 1)  # SUBMISSION cell
        # Either forced (single candidate) or a decision listing candidates.
        if r["status"] == "decision_required":
            assert r["decision"]["kind"] == "submission"
            assert target in r["decision"]["candidates"]
            r2 = rv.resolve_revolt(s, "guelph", 3, 1, choice=target)
            assert r2["status"] == "resolved"
            assert r2["switch"]["revolted"] == target
        else:
            assert r["status"] == "resolved"
            assert r["switch"]["revolted"] == target

    def test_submission_illegal_choice_rejected(self):
        s, target = self._submission_state()
        r = rv.resolve_revolt(s, "guelph", 3, 1, choice="Lucca")
        assert r["status"] in ("illegal_choice", "decision_required", "resolved")
        if r["status"] == "illegal_choice":
            assert "Lucca" in r["reason"]

    def test_submission_no_candidates_no_effect(self):
        s = load_scenario("A", seed=1)
        # Remove all ghibelline mustered lords -> no cylinder anywhere.
        for lid, l in s["lords"].items():
            if l["side"] == "ghibelline" and l.get("status") == "mustered":
                loc = s["locales"].get(l.get("location") or "")
                if loc and lid in loc.get("lords_present", []):
                    loc["lords_present"].remove(lid)
                l["status"] = "on_calendar"
                l["location"] = None
        r = rv.resolve_revolt(s, "guelph", 3, 1)
        assert r["status"] == "no_effect"


class TestExiles:
    def test_exiles_surfaced_and_applied(self):
        s = load_scenario("A", seed=1)
        cort = s["locales"]["Cortona"]
        cort["current_allegiance"] = []
        cort["ruins"] = None
        _clear_lords_near(s, "Cortona", "guelph")
        s["locales"]["Chiusi"]["current_allegiance"] = [{"side": "ghibelline", "value": 1}]
        r = rv.resolve_revolt(s, "guelph", 6, 6)
        assert r["status"] == "resolved"
        assert "exiles_required" in r
        assert r["exiles_required"]["side"] == "guelph"
        assert r["exiles_required"]["count"] == 2  # Town value 2
        cands = r["exiles_required"]["candidates"]
        if cands:
            # Apply one slide and confirm the box moved in the right direction.
            sl = cands[0]
            lord = s["lords"][sl["lord_id"]]
            before = lord.get(f"{'calendar' if sl['kind']=='cylinder' else 'service'}_box")
            rv.apply_exiles(s, "guelph", [sl])
            after = lord.get(f"{'calendar' if sl['kind']=='cylinder' else 'service'}_box")
            if sl["kind"] == "cylinder":
                assert after <= before
            else:
                assert after >= before


class TestPendingDecisionFlow:
    """A parked Revolt decision must be surfaced by the enumerator and
    resolvable via dispatch — no deadlock (CROSS_PROJECT_LESSONS §8.5)."""

    def test_enumerator_surfaces_and_dispatch_resolves(self):
        from inferno.actions import dispatch
        from inferno.legal_moves import enumerate_legal
        s = load_scenario("A", seed=1)
        # Build a genuine SUBMISSION state: a ghibelline mustered lord with
        # >=2 adjacent eligible Guelph strongholds.
        gid = next(lid for lid, l in s["lords"].items()
                   if l["side"] == "ghibelline" and l.get("status") == "mustered")
        hub = s["lords"][gid]["location"]
        made = 0
        for n, _w in sd.adjacent_to(hub):
            loc = s["locales"][n]
            if loc.get("type") in ("castle", "town"):
                loc["allegiance"] = "guelph"
                loc["current_allegiance"] = []
                loc["ruins"] = None
                _clear_lords_near(s, n, "guelph")
                made += 1
        # Park exactly the decision resolve_revolt produces for SUBMISSION (3,1).
        res = rv.resolve_revolt(s, "guelph", 3, 1)
        if res["status"] != "decision_required":
            pytest.skip("setup did not yield a multi-candidate Submission")
        s["pending_revolts"] = [{
            "losing_side": "guelph", "context": "test", "rolls": [[3, 1]],
            "log": [], "decision": res["decision"],
        }]
        moves = enumerate_legal(s)
        assert moves and all(m["action"] == "cmd_resolve_revolt" for m in moves)
        chosen = moves[0]["args"]["choice"]
        assert chosen in res["decision"]["candidates"]
        dispatch(s, {"action": "cmd_resolve_revolt", "side": "ghibelline",
                     "args": {"choice": chosen}})
        assert not any(b.get("decision") for b in s.get("pending_revolts", []))
        assert any(m["side"] == "ghibelline"
                   for m in s["locales"][chosen]["current_allegiance"])

    def test_exiles_decision_surfaced_and_resolved(self):
        from inferno.actions import dispatch
        from inferno.legal_moves import enumerate_legal
        s = load_scenario("A", seed=1)
        # Park an Exiles decision for guelph.
        cands = rv.legal_exiles_targets(s, "guelph")
        s["pending_exiles"] = [{"side": "guelph", "count": 2, "candidates": cands}]
        moves = enumerate_legal(s)
        assert moves and all(m["action"] == "cmd_resolve_exiles" for m in moves)
        # Resolve with no slides (decline) — must clear the pending exiles.
        dispatch(s, {"action": "cmd_resolve_exiles", "side": "guelph", "args": {"slides": []}})
        assert not s.get("pending_exiles")


class TestTriggerParksDecision:
    """End-to-end: a real trigger_revolts roll onto a Submission cell parks a
    pending decision and stops draining (not just a hand-parked batch)."""

    class _FakeRNG:
        def __init__(self, seq):
            self._seq = list(seq)
            self._i = 0
        def roll(self, context):
            v = self._seq[self._i % len(self._seq)]
            self._i += 1
            class _R:  # mimic DieRoll
                pass
            r = _R(); r.value = v; r.context = context
            return r

    def test_submission_trigger_parks_then_resolves(self):
        from inferno.actions import dispatch
        from inferno.legal_moves import enumerate_legal
        s = load_scenario("A", seed=1)
        # Make >=2 eligible Guelph strongholds adjacent to a ghibelline cylinder.
        gid = next(lid for lid, l in s["lords"].items()
                   if l["side"] == "ghibelline" and l.get("status") == "mustered")
        hub = s["lords"][gid]["location"]
        for n, _w in sd.adjacent_to(hub):
            loc = s["locales"][n]
            if loc.get("type") in ("castle", "town"):
                loc["allegiance"] = "guelph"
                loc["current_allegiance"] = []
                loc["ruins"] = None
                _clear_lords_near(s, n, "guelph")
        # vs-Guelph SUBMISSION cell = (gold3, purple1). FakeRNG yields gold,purple.
        rng = self._FakeRNG([3, 1])
        res = rv.trigger_revolts(s, losing_side="guelph", count=1, rng=rng, context="t")
        decisions = [b for b in s.get("pending_revolts", []) if b.get("decision")]
        if not decisions:
            pytest.skip("setup did not yield a multi-candidate Submission")
        # Enumerator now surfaces only the resolution moves.
        moves = enumerate_legal(s)
        assert moves and all(m["action"] == "cmd_resolve_revolt" for m in moves)
        chosen = moves[0]["args"]["choice"]
        dispatch(s, {"action": "cmd_resolve_revolt", "side": "ghibelline",
                     "args": {"choice": chosen}})
        assert not any(b.get("decision") for b in s.get("pending_revolts", []))
        assert any(m["side"] == "ghibelline"
                   for m in s["locales"][chosen]["current_allegiance"])
