"""Revolt Tables (1.4.2) + Allegiance switching (1.4.4) + Exiles.

Encodes the two physical Revolt Tables from
`reference/INFERNO_Revolt_Tables_Reference.txt`:

  - TABLE 1 "Revolt Against Guelphs?"   — used when the GUELPHS lost a
    Lord/Stronghold; the GHIBELLINES are the benefitting (rolling) side.
  - TABLE 2 "Revolt Against Ghibellines?" — used when the GHIBELLINES
    lost; the GUELPHS roll.

Dice convention (per the reference): row die = gold (Guelph), column die
= purple (Ghibelline). A cell is keyed (gold, purple) and is either a
named Locale (REBELLION) or the SUBMISSION sentinel.

Per Q-002 (RULES_DECISIONS.md) the 10 crossed-out cells are SUBMISSION
results, not no-revolt. Per the No-Agent constraint, every player choice
(SUBMISSION target, Rebellion already-Friendly fallback target, and the
1.4.4 Exiles slides) is SURFACED as a decision — the harness never picks
among genuine alternatives.
"""
from __future__ import annotations

from typing import Any

from . import static_data as sd

SUBMISSION = "<SUBMISSION>"

# (gold, purple) -> Locale name (REBELLION) or SUBMISSION.
# Spellings match LOCALES keys (reference spellings; see reference doc note D).
REVOLT_TABLE_VS_GUELPH: dict[tuple[int, int], str] = {
    (1, 1): "Lucca",       (1, 2): "Montecatini",  (1, 3): "Firenze",
    (1, 4): "Firenze",     (1, 5): "Firenze",      (1, 6): "Battifolle",
    (2, 1): "Vecliano",    (2, 2): "Altopascio",   (2, 3): "Prato",
    (2, 4): "Figline",     (2, 5): "Ponte a Sieve",(2, 6): "Poppi",
    (3, 1): SUBMISSION,    (3, 2): "Empoli",       (3, 3): "Montelupo",
    (3, 4): "San Casciano",(3, 5): "San Giovanni", (3, 6): "Bibbiena",
    (4, 1): SUBMISSION,    (4, 2): "San Miniato",  (4, 3): "Montespertoli",
    (4, 4): "Barberino",   (4, 5): "Arezzo",       (4, 6): "Anghiari",
    (5, 1): SUBMISSION,    (5, 2): "San Gimignano",(5, 3): "Poggio Bonizio",
    (5, 4): "Montevarchi", (5, 5): "Monte San Savino", (5, 6): "Castiglione",
    (6, 1): SUBMISSION,    (6, 2): "Colle",        (6, 3): "Poggio Bonizio",
    (6, 4): "Castelnuovo Berardenga", (6, 5): "Chiusi", (6, 6): "Cortona",
}

REVOLT_TABLE_VS_GHIBELLINE: dict[tuple[int, int], str] = {
    (1, 1): "Pisa",        (1, 2): "Vicopisano",   (1, 3): "Volterra",
    (1, 4): "Monteriggioni",(1, 5): "Asinalunga",  (1, 6): SUBMISSION,
    (2, 1): "Borgo Livorno",(2, 2): "Pontedera",   (2, 3): "Volterra",
    (2, 4): "Asciano",     (2, 5): "Montepulciano",(2, 6): SUBMISSION,
    (3, 1): "Rosignano",   (3, 2): "Pecciole",     (3, 3): "Casole",
    (3, 4): "Montalcino",  (3, 5): "Montepulciano",(3, 6): SUBMISSION,
    (4, 1): "Campiglia",   (4, 2): "Rocca Sillana",(4, 3): "Radicondoli",
    (4, 4): "Montalcino",  (4, 5): "Chianciano",   (4, 6): SUBMISSION,
    (5, 1): "Massa Marittima",(5, 2): "Monterotondo",(5, 3): "Monticiano",
    (5, 4): "San Quirico", (5, 5): "Radicofani",   (5, 6): SUBMISSION,
    (6, 1): "Castiglione della Pescaia", (6, 2): "Grosseto", (6, 3): "Montemassi",
    (6, 4): "Montepescali",(6, 5): "Santa Fiora",  (6, 6): SUBMISSION,
}

# losing_side -> the table for "Revolt Against <losing_side>".
_TABLE_BY_LOSER = {
    "guelph": REVOLT_TABLE_VS_GUELPH,
    "ghibelline": REVOLT_TABLE_VS_GHIBELLINE,
}


def _other(side: str) -> str:
    return "ghibelline" if side == "guelph" else "guelph"


def lookup_revolt_cell(losing_side: str, gold: int, purple: int) -> str:
    """Return the Locale name (REBELLION) or SUBMISSION for a roll on the
    'Revolt Against <losing_side>' table. Raises on out-of-range dice."""
    if losing_side not in _TABLE_BY_LOSER:
        raise ValueError(f"losing_side must be guelph/ghibelline, got {losing_side!r}")
    if not (1 <= gold <= 6 and 1 <= purple <= 6):
        raise ValueError(f"dice out of range: gold={gold} purple={purple}")
    return _TABLE_BY_LOSER[losing_side][(gold, purple)]


# ----------------------------------------------------------------------
# Allegiance / eligibility helpers (1.4.1)
# ----------------------------------------------------------------------
def _effective_allegiance(loc: dict) -> str | None:
    """Side that currently controls a Locale: its current Allegiance
    markers if any, else its printed Allegiance."""
    markers = loc.get("current_allegiance") or []
    sides = {m.get("side") for m in markers}
    if sides == {"guelph"}:
        return "guelph"
    if sides == {"ghibelline"}:
        return "ghibelline"
    if sides:
        # Mixed shouldn't happen post-flip, but be explicit.
        return None
    return loc.get("allegiance")


def _locales_within_1(name: str) -> set[str]:
    return {name} | {n for n, _ in sd.adjacent_to(name)}


def _has_enemy_lord_at_or_adjacent(state: dict, name: str, enemy_side: str) -> bool:
    for loc_n in _locales_within_1(name):
        loc = state["locales"].get(loc_n)
        if not loc:
            continue
        for lid in loc.get("lords_present", []):
            lord = state["lords"].get(lid)
            if lord and lord.get("side") == enemy_side and lord.get("status") == "mustered":
                return True
    return False


def is_eligible_for_revolt(state: dict, name: str, rolling_side: str) -> bool:
    """1.4.1: an Enemy (to rolling_side) Stronghold with no Enemy
    (= losing_side) Lords there or adjacent. Ruins and Outposts never
    Revolt. 'Enemy' is judged by effective Allegiance."""
    loc = state["locales"].get(name)
    if not loc:
        return False
    if loc.get("ruins") or loc.get("type") == "outpost":
        return False
    losing_side = _other(rolling_side)
    if _effective_allegiance(loc) != losing_side:
        return False
    if _has_enemy_lord_at_or_adjacent(state, name, losing_side):
        return False
    return True


def _rolling_presence_within_1(state: dict, name: str, rolling_side: str,
                               cylinder_only: bool = False) -> bool:
    """True if the rolling side has a Lord cylinder (and, unless
    cylinder_only, an Allegiance marker) within one Locale of `name`."""
    for loc_n in _locales_within_1(name):
        loc = state["locales"].get(loc_n)
        if not loc:
            continue
        for lid in loc.get("lords_present", []):
            lord = state["lords"].get(lid)
            if lord and lord.get("side") == rolling_side and lord.get("status") == "mustered":
                return True
        if not cylinder_only:
            if any(m.get("side") == rolling_side for m in loc.get("current_allegiance") or []):
                return True
    return False


def _stronghold_value(loc: dict) -> int:
    return sd.STRONGHOLDS.get(loc.get("type"), {}).get("size", 0)


# ----------------------------------------------------------------------
# 1.4.4 flip
# ----------------------------------------------------------------------
def apply_allegiance_switch(state: dict, name: str, rolling_side: str) -> dict[str, Any]:
    """1.4.4: the Stronghold Revolts to the rolling side. Adds Allegiance
    markers = Stronghold Value of the side, removing the loser's markers
    (or, if the printed Allegiance is the rolling side, simply removes all
    current markers to revert to printed-Friendly). Adjusts VP. Returns
    the number of markers placed-or-removed (for Exiles) and the loser."""
    loc = state["locales"][name]
    loser = _other(rolling_side)
    value = _stronghold_value(loc)
    before = list(loc.get("current_allegiance") or [])
    removed = sum(1 for m in before if m.get("side") == loser)

    if loc.get("allegiance") == rolling_side:
        # Reverting to printed-Friendly: remove all current markers.
        loc["current_allegiance"] = []
        placed = 0
        markers_changed = removed
        # VP: loser loses the markers it had (1 VP each).
        state["vp"][loser] = max(state["vp"].get(loser, 0) - removed, 0)
    else:
        # Place `value` rolling-side markers, removing loser's.
        loc["current_allegiance"] = [{"side": rolling_side, "value": 1} for _ in range(value)]
        placed = value
        markers_changed = max(placed, removed)
        state["vp"][rolling_side] = min(state["vp"].get(rolling_side, 0) + value, 17.5)
        state["vp"][loser] = max(state["vp"].get(loser, 0) - removed, 0)

    # A Stronghold cannot hold Ruins and Allegiance simultaneously (handled
    # elsewhere); revolt also clears Bypass/Siege per 1.4 (caller's domain).
    return {
        "revolted": name, "to": rolling_side, "value": value,
        "markers_placed": placed, "markers_removed": removed,
        "exiles_count": markers_changed, "exiles_side": loser,
    }


def legal_exiles_targets(state: dict, side: str) -> list[dict[str, Any]]:
    """1.4.4 EXILES: the losing side may slide its own (only) cylinders one
    box LEFT or Service markers one box RIGHT, one box per marker
    placed/removed. Returns the candidate markers the side may slide."""
    out: list[dict[str, Any]] = []
    for lid, lord in state["lords"].items():
        if lord.get("side") != side:
            continue
        if lord.get("calendar_box") is not None:
            out.append({"lord_id": lid, "kind": "cylinder",
                        "box": lord["calendar_box"], "direction": "left"})
        if lord.get("service_box") is not None:
            out.append({"lord_id": lid, "kind": "service",
                        "box": lord["service_box"], "direction": "right"})
    return out


# ----------------------------------------------------------------------
# Top-level resolution (1.4.2)
# ----------------------------------------------------------------------
def resolve_revolt(state: dict, losing_side: str, gold: int, purple: int,
                   choice: str | None = None) -> dict[str, Any]:
    """Resolve one Revolt Table roll for the side benefitting from
    `losing_side`'s loss. `gold`/`purple` are the rolled dice. `choice`
    is a Locale name supplied by the consumer when a player decision is
    required (SUBMISSION target or Rebellion already-Friendly fallback).

    Returns one of:
      {"status": "no_effect", ...}
      {"status": "decision_required", "decision": {"kind","candidates",...}}
      {"status": "resolved", "switch": {...}, "exiles_required": {...}}
    """
    rolling_side = _other(losing_side)
    cell = lookup_revolt_cell(losing_side, gold, purple)
    base = {"losing_side": losing_side, "rolling_side": rolling_side,
            "gold": gold, "purple": purple, "cell": cell}

    if cell == SUBMISSION:
        candidates = sorted(
            name for name in state["locales"]
            if is_eligible_for_revolt(state, name, rolling_side)
            and _rolling_presence_within_1(state, name, rolling_side, cylinder_only=True)
        )
        return _resolve_choice(state, rolling_side, candidates, choice,
                               kind="submission", base=base)

    # REBELLION — cell names a Locale.
    loc = state["locales"].get(cell)
    if loc is None:
        return {**base, "status": "no_effect", "reason": f"unknown locale {cell!r}"}

    eff = _effective_allegiance(loc)
    if eff == rolling_side:
        # Already Friendly: pick an ADJACENT eligible Enemy Stronghold of
        # same-or-less Value (1.4.2 Rebellion, third bullet).
        max_value = _stronghold_value(loc)
        candidates = sorted(
            n for n, _ in sd.adjacent_to(cell)
            if is_eligible_for_revolt(state, n, rolling_side)
            and _stronghold_value(state["locales"][n]) <= max_value
        )
        return _resolve_choice(state, rolling_side, candidates, choice,
                               kind="rebellion_friendly_fallback", base=base,
                               named=cell)

    # Named Locale is Enemy to the rolling side.
    if not is_eligible_for_revolt(state, cell, rolling_side):
        return {**base, "status": "no_effect",
                "reason": "named Locale not eligible (Enemy Lord adjacent / Ruined)"}
    if not _rolling_presence_within_1(state, cell, rolling_side, cylinder_only=False):
        return {**base, "status": "no_effect",
                "reason": "no rolling-side cylinder or Allegiance marker within 1 Locale"}
    switch = apply_allegiance_switch(state, cell, rolling_side)
    return _finish_resolved(state, base, switch)


def _resolve_choice(state, rolling_side, candidates, choice, kind, base,
                    named=None):
    if not candidates:
        return {**base, "status": "no_effect",
                "reason": f"{kind}: no eligible target", "named": named}
    if choice is None:
        if len(candidates) == 1:
            # Forced — only one legal target — still report it was forced.
            switch = apply_allegiance_switch(state, candidates[0], rolling_side)
            res = _finish_resolved(state, base, switch)
            res["forced_choice"] = candidates[0]
            return res
        return {**base, "status": "decision_required",
                "decision": {"kind": kind, "side": rolling_side,
                             "candidates": candidates, "named": named}}
    if choice not in candidates:
        return {**base, "status": "illegal_choice",
                "reason": f"{choice!r} not in eligible candidates {candidates}"}
    switch = apply_allegiance_switch(state, choice, rolling_side)
    return _finish_resolved(state, base, switch)


def _finish_resolved(state, base, switch):
    res = {**base, "status": "resolved", "switch": switch}
    if switch["exiles_count"] > 0:
        res["exiles_required"] = {
            "side": switch["exiles_side"],
            "count": switch["exiles_count"],
            "candidates": legal_exiles_targets(state, switch["exiles_side"]),
        }
    return res


def apply_exiles(state: dict, side: str, slides: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the losing side's chosen Exiles slides (1.4.4): cylinders one
    box LEFT, Service markers one box RIGHT, each slide = one box. `slides`
    is a list of {"lord_id","kind"} chosen by that side (count must equal
    the markers placed/removed, but we apply what is supplied)."""
    applied = []
    for sl in slides:
        lid = sl.get("lord_id")
        kind = sl.get("kind")
        lord = state["lords"].get(lid)
        if not lord or lord.get("side") != side:
            continue
        if kind == "cylinder" and lord.get("calendar_box") is not None:
            lord["calendar_box"] = max(1, lord["calendar_box"] - 1)
            applied.append({"lord_id": lid, "kind": "cylinder", "to": lord["calendar_box"]})
        elif kind == "service" and lord.get("service_box") is not None:
            lord["service_box"] = min(16, lord["service_box"] + 1)
            applied.append({"lord_id": lid, "kind": "service", "to": lord["service_box"]})
    return {"applied_exiles": applied}


# ----------------------------------------------------------------------
# Trigger + drain mechanism (used by Disband/Surrender/Sack/Languish/S18)
# ----------------------------------------------------------------------
def trigger_revolts(state: dict, losing_side: str, count: int, rng,
                    context: str) -> dict[str, Any]:
    """Queue `count` Revolt Table rolls (1.4.2) benefitting the side opposite
    `losing_side`, then drain deterministic results. Rolls are pre-generated
    (gold+purple per roll) for replay determinism and resolved in order
    ('results of one can affect the next', 1.4.2). A roll needing a player
    choice (Submission target / Rebellion already-Friendly fallback) parks the
    batch as a pending decision the consumer resolves via cmd_resolve_revolt.
    Treachery-card additions (1.4.3) are handled separately by callers."""
    rolls = []
    for i in range(count):
        gold = rng.roll(f"revolt_{context}_gold_{i}").value
        purple = rng.roll(f"revolt_{context}_purple_{i}").value
        rolls.append([gold, purple])
    state.setdefault("pending_revolts", []).append({
        "losing_side": losing_side, "context": context, "rolls": rolls, "log": [],
    })
    return drain_revolts(state)


def drain_revolts(state: dict) -> dict[str, Any]:
    """Process pending revolt batches head-first, auto-applying deterministic
    rolls and stopping at the first roll that requires a player choice."""
    log: list[dict[str, Any]] = []
    batches = state.get("pending_revolts", [])
    while batches:
        batch = batches[0]
        if batch.get("decision"):
            break  # awaiting cmd_resolve_revolt
        if not batch["rolls"]:
            batches.pop(0)
            continue
        gold, purple = batch["rolls"][0]
        res = resolve_revolt(state, batch["losing_side"], gold, purple)
        if res["status"] == "decision_required":
            batch["decision"] = res["decision"]
            log.append({"context": batch["context"], "gold": gold, "purple": purple,
                        "status": "decision_required", "cell": res["cell"]})
            break
        batch["rolls"].pop(0)
        entry = {"context": batch["context"], "gold": gold, "purple": purple,
                 "status": res["status"], "cell": res.get("cell")}
        if res.get("forced_choice"):
            entry["forced_choice"] = res["forced_choice"]
        if res.get("switch"):
            entry["revolted"] = res["switch"]["revolted"]
        if res.get("exiles_required"):
            state.setdefault("pending_exiles", []).append(res["exiles_required"])
        batch["log"].append(entry)
        log.append(entry)
        if not batch["rolls"]:
            batches.pop(0)
    return {"revolt_rolls": log}
