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
