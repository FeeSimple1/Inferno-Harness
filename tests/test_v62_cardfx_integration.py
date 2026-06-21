"""v6.2 — Card-effect INTEGRATION coverage (round-3 fuzz, locked in).

Drives all 52 Arts-of-War Capabilities through live Battle/Storm/Sally combats
(1v1 + 2v2, randomized forces) and every Event through live state, asserting the
always-on invariant battery + combat-engagement after each. Crucially this is the
only coverage that fires the Crossbow `select_target_unit` decision channel,
which no full self-play game ever reached. Backed by the cardfx_fuzz.py harness.
"""
from __future__ import annotations

import cardfx_fuzz as cf
from inferno import card_data as cd


def test_all_52_cards_integration_clean_and_crossbow_fires():
    cf.ANOMALIES.clear()
    cf.CHANNELS.clear()
    cards = [c["id"] for c in (cd.GUELPH_CARDS + cd.GHIBELLINE_CARDS)]
    assert len(cards) == 52
    for cid in cards:
        cf.fuzz_capability(cid, [1, 2])
        cf.fuzz_event(cid, [1, 2])
    # No crash / invariant break / inert combat across any card.
    assert not cf.ANOMALIES, cf.ANOMALIES[:5]
    # The whole point: the Crossbow select-target channel actually executes.
    assert cf.CHANNELS.get("select_target_unit", 0) > 0
    # And the array / hit-absorption / concede channels too.
    for ch in ("absorb_target", "concede", "initial_placement_attacker"):
        assert cf.CHANNELS.get(ch, 0) > 0
