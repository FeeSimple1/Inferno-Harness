"""Neutral shared test helpers.

This module deliberately has NO Hypothesis (or other optional-dependency)
imports and no module-level skips, so test modules can import shared helpers
from here without transitively inheriting another module's skip. (Historically,
helpers lived in test_invariants.py, which module-level-skips when Hypothesis is
absent — pulling every importer into the skip and silently hiding ordinary
regressions.)
"""
from __future__ import annotations


def _place(s, lid, loc, inside=False, forces=None):
    """Relocate Lord `lid` to Locale `loc` as a Mustered Lord, fixing up the
    source/destination lords_present lists, the in_stronghold flag, and
    (optionally) the Lord's forces. Shared by co-location / Battle setups."""
    old = s["lords"][lid].get("location")
    if old and old in s["locales"] and lid in s["locales"][old]["lords_present"]:
        s["locales"][old]["lords_present"].remove(lid)
    s["lords"][lid]["location"] = loc
    s["lords"][lid]["status"] = "mustered"
    if lid not in s["locales"][loc]["lords_present"]:
        s["locales"][loc]["lords_present"].append(lid)
    s["lords"][lid].setdefault("flags", {})["in_stronghold"] = inside
    if forces is not None:
        s["lords"][lid]["forces"] = dict(forces)


def _finish_pending_choices(state):
    """Finish explicit decision windows before a fixture advances the turn.

    Decline optional Pay/Exiles; resolve required drawn-card/Revolt choices
    through the same legal menu used by an interactive player.
    """
    from inferno.actions import dispatch
    from inferno.legal_moves import enumerate_legal
    for _ in range(100):
        pending = (state.get("pending_fpd") or state.get("pending_revolts")
                   or state.get("pending_exiles") or any(
                       p.get("type") in ("capability_placement", "event_resolution")
                       for p in state.get("pending", [])))
        if not pending:
            return
        moves = enumerate_legal(state)
        assert moves, "A pending fixture decision must be resolvable"
        preferred = next((m for m in moves if m["action"] == "cmd_fpd_pay_done"
                          or (m["action"] == "cmd_resolve_exiles" and not m["args"]["slides"])), moves[0])
        dispatch(state, preferred)
    raise AssertionError("Fixture pending-decision loop did not finish")
