# Running the Inferno Harness in ChatGPT (or any external LLM/agent)

This harness is **self-contained and dependency-free to play** — pure Python
stdlib, no `pip install` required. (Third-party packages are needed only to run
the *test suite*.) It is designed to be driven by an LLM to self-play and to
surface engine bugs.

## Environment
- **Python 3.11** (the package targets >=3.11; it also runs on 3.10).
- From the project root, always run with `PYTHONPATH=src`.
- **No install / no dependencies needed to play.** Do NOT run `pip install -e .`.
- To run the *test suite* only: `pip install pytest hypothesis` then
  `PYTHONPATH=src python -m pytest -q` (expect all green).

## Fastest path: the bug-hunt driver
A ready-to-run, stdlib-only self-play driver is included:

    PYTHONPATH=src python selfplay_bughunt.py F --seed 11 --max-steps 8000

It plays a full game of the longest scenario (F) via the **validated** action
palette, asserts the always-on invariant battery after every step, and prints a
structured ANOMALY report. To hunt bugs with your own judgment, edit the
`choose(state, moves, rng)` function to make the decisions yourself.

## Driving it yourself (library API)
```python
import sys; sys.path.insert(0, "src")
from inferno.scenarios import load_scenario
from inferno.legal_moves import enumerate_legal_validated   # validated palette
from inferno.actions import dispatch
from inferno.invariants import check_all_invariants
from inferno.llm.briefing import build_briefing             # ~3KB text view

s = load_scenario("F", seed=11, hidden_mats=True)           # longest scenario, hidden info
while s["meta"]["phase"] != "victory":
    pal = enumerate_legal_validated(s)        # {"moves","dropped","unvalidated"}
    # pal["dropped"] = over-enumeration diagnostics (a bug if non-empty)
    briefing = build_briefing(s, s["meta"]["active_player"])   # show this to the model
    move = your_pick(pal["moves"])            # choose ONE move dict verbatim
    dispatch(s, {k: move[k] for k in ("action","side","args") if k in move})
    check_all_invariants(s)                   # raises AssertionError on a defect
```
Rules of engagement: pick ONLY from `pal["moves"]` (never invent actions/args);
resolve every pending decision the same way; if `pal["moves"]` is empty and the
phase isn't `victory`, that's a **deadlock** (a bug).

## CLI alternative (shell-driven)
`PYTHONPATH=src python -m inferno.cli new F --seed 11 --out g.json`, then loop
`legal-moves` -> `briefing --side <side> --hidden-mats` -> `do '<move json>'` ->
`pending`. See `LLM_PLAY_GUIDE.md`.

## What counts as a bug (log it, with reproduction)
- `enumerate_legal_validated` returns anything in `dropped` (menu offered a move
  the executor rejects — over-enumeration).
- `dispatch` raises on a move the palette offered.
- `check_all_invariants` raises (VP cap, non-negative forces, lord/locale
  consistency, **no co-located enemies**, **AoW card conservation = 26/side**, …).
- A deadlock (no legal moves, not `victory`).
- Any behavior contradicting `reference/*.txt` (Rules of Play + Errata are
  authoritative — quote the rule).

Distinguish **harness bugs** (mistakes in your own driver, e.g. indexing a Lord
with `location = None`) from **engine bugs** (a real engine function misbehaving
on input the engine produced). Only the latter count.
