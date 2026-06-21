"""v6.3 — Save/load + replay determinism (round-3 fuzz, locked in).

Serializing the game state to JSON mid-game, reloading it, and continuing must
yield a game IDENTICAL to one never reloaded. Catches any state not captured by
the serializable form, or nondeterminism in dispatch/enumeration. Backed by the
saveload_fuzz.py harness; here a compact 6-scenario x 3-seed sweep.
"""
from __future__ import annotations

import saveload_fuzz as sf


def test_saveload_determinism_all_scenarios():
    sf.ANOMALIES.clear()
    for scen in "ABCDEF":
        for seed in (1, 2, 3):
            sf.run(scen, seed, max_steps=4000)
    assert not sf.ANOMALIES, sf.ANOMALIES[:5]
