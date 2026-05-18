"""Enumerator/handler round-trip sweep.

Per CROSS_PROJECT_LESSONS.md §2:

    Matching argument names between the enumerator and the handler is not
    enough — the enumerator can emit values from the wrong domain while
    the field name looks correct.

    In a sweep test, replay every action shape the enumerator emits
    through the handler in a representative state and assert no bad_*
    / missing_arg / ineligible_* codes come back.

This sweep walks each scenario × seed for a bounded number of steps and
asserts that every move enumerate_legal() emits is actually accepted by
dispatch(). It catches:

  - Arg-shape mismatches (the SMOKE-119 family).
  - Over-enumeration of options the handler would reject (the SMOKE-122
    family). Both surface here as IllegalAction raised from the dispatch
    of a 'legal' move.
"""

from __future__ import annotations

import copy
import json

import pytest

from inferno.actions import IllegalAction, dispatch
from inferno.legal_moves import enumerate_legal
from inferno.scenarios import SCENARIO_IDS, load_scenario


SAFE_NAMES_PREFIXES = ("<", )  # placeholder/phase entries — skip


def _pick_first_legal(state):
    """Return the first non-placeholder move from the enumerator, or None."""
    moves = enumerate_legal(state)
    for m in moves:
        if any(m["action"].startswith(p) for p in SAFE_NAMES_PREFIXES):
            continue
        return m
    return None


@pytest.mark.parametrize("sid", SCENARIO_IDS)
@pytest.mark.parametrize("seed", [1, 7, 42])
def test_round_trip_sweep_per_scenario_seed(sid, seed):
    """For each (scenario, seed): walk up to STEPS steps; at every step,
    every move the enumerator returns must be accepted by dispatch().
    Then advance one step under a pick-first policy."""
    s = load_scenario(sid, seed=seed)
    STEPS = 30  # bounded walk

    for step in range(STEPS):
        moves = enumerate_legal(s)
        if not moves:
            break
        # Replay every move on a snapshot and assert dispatch accepts it.
        for m in moves:
            if any(m["action"].startswith(p) for p in SAFE_NAMES_PREFIXES):
                continue
            snapshot = copy.deepcopy(s)
            action = {"action": m["action"], "side": m["side"]}
            if "args" in m:
                action["args"] = m["args"]
            try:
                dispatch(snapshot, action)
            except IllegalAction as e:
                pytest.fail(
                    f"[{sid} seed={seed} step={step}] enumerator emitted "
                    f"illegal move {m['action']}: code={e.code} "
                    f"(citation={e.citation}) — action={action}"
                )
        # Advance the real state by one move under pick-first policy.
        chosen = _pick_first_legal(s)
        if chosen is None:
            break
        action = {"action": chosen["action"], "side": chosen["side"]}
        if "args" in chosen:
            action["args"] = chosen["args"]
        dispatch(s, action)
        # Stop if game ended.
        if s["meta"].get("phase") == "victory":
            break


def test_round_trip_history_remains_serialisable():
    """After any sequence of moves, the resulting state must JSON-serialise."""
    s = load_scenario("A", seed=1)
    for _ in range(50):
        chosen = _pick_first_legal(s)
        if chosen is None:
            break
        action = {"action": chosen["action"], "side": chosen["side"]}
        if "args" in chosen:
            action["args"] = chosen["args"]
        dispatch(s, action)
        if s["meta"].get("phase") == "victory":
            break
    # Should serialise without TypeError
    json.dumps(s, ensure_ascii=False)
