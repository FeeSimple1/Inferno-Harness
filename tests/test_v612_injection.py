"""v6.12 — illegal-state injection fuzz (fourth diverse fuzz technique).

Proves the invariant battery's coverage: every corruption in the catalogue,
applied to real mid-game states, must be detected by check_all_invariants,
and the uncorrupted states must keep passing (no over-strict invariant).
This round's battery additions (calendar-cylinder / Service-marker
consistency, map-marker sanity, inside-capacity, meta sanity, side enum,
duplicate lords_present) exist because the first sweep showed the old
battery missed those whole classes.
"""
import state_injection_fuzz as xf


def test_injection_sweep_small():
    xf.ANOMALIES.clear()
    xf.APPLIED.clear()
    for scen in "AD":
        xf.run(scen, 1, max_steps=250, probe_every=60)
    assert not xf.ANOMALIES, xf.ANOMALIES[:5]
    # The sweep must have actually exercised a broad slice of the catalogue.
    assert len(xf.APPLIED) >= 20, sorted(xf.APPLIED)
