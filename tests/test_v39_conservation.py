"""v3.9 — strict AoW card-conservation regression. The 20-round smoke campaign's
only flag was a counting artifact: cards drawn as This-Campaign/This-Levy Events
live in state['active_events'] until end_reset returns them to the discard. This
test asserts the EXACT per-side total (26) at every step — counting every pool
INCLUDING active_events — so both a LOSS and a DUPLICATION are caught.
"""
from __future__ import annotations

import collections
import copy
import random

import pytest

from inferno.actions import dispatch
from inferno.legal_moves import enumerate_legal
from inferno.scenarios import load_scenario, SCENARIO_IDS


def _per_side_total(s, side):
    c = collections.Counter()
    d = s["decks"][side]
    for cid in d.get("aow_deck", []) + d.get("aow_discard", []) + d.get("aow_held", []):
        c[cid] += 1
    for cap in s.get("capabilities_in_play", []):
        if cap.get("side") == side:
            c[cap["id"]] += 1
    for lid, l in s["lords"].items():
        if l.get("side") == side:
            for cid in l.get("capabilities", []) or []:
                c[cid] += 1
    for pnd in (s.get("pending", []) or []):
        if pnd.get("type") == "capability_placement" and pnd.get("side") == side:
            cid = pnd.get("card_id")
            if isinstance(cid, str):
                c[cid] += 1
    for kind in ("immediate", "this_levy", "this_campaign"):
        for e in (s.get("active_events", {}).get(kind, []) or []):
            cid = e.get("id")
            if e.get("side") == side and isinstance(cid, str) and cid[:1] in ("F", "S"):
                c[cid] += 1
    # Only count the 26 AoW cards of this side's prefix (ignore treachery_* etc).
    pfx = "F" if side == "guelph" else "S"
    return sum(n for x, n in c.items() if isinstance(x, str) and x[:1] == pfx
               and x[1:].isdigit())


@pytest.mark.parametrize("scenario", SCENARIO_IDS)
def test_exact_aow_total_holds_over_play(scenario):
    s = load_scenario(scenario, seed=2)
    rng = random.Random(7)
    base = {side: _per_side_total(s, side) for side in ("guelph", "ghibelline")}
    assert base["guelph"] == 26 and base["ghibelline"] == 26
    TERM = ("<unknown_phase>", "<unknown_campaign_step>", "<game_over>")
    for _ in range(600):
        moves = enumerate_legal(s)
        if not moves or moves[0].get("action") in TERM or s["meta"].get("game_over"):
            break
        m = rng.choice(moves)
        try:
            dispatch(s, m)
        except Exception:
            ok = False
            for cand in moves:
                pr = copy.deepcopy(s)
                try:
                    dispatch(pr, cand); s.clear(); s.update(pr); ok = True; break
                except Exception:
                    continue
            if not ok:
                break
        for side in ("guelph", "ghibelline"):
            assert _per_side_total(s, side) == 26, \
                f"{scenario}: {side} AoW total = {_per_side_total(s, side)} (expected 26)"
