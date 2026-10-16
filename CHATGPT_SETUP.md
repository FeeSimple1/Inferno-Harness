# Running Inferno with ChatGPT or another external player

Python 3.11 or newer is required. Game mechanics and the player interface use the
standard library. From the repository root use `PYTHONPATH=src`; install the
optional development dependencies only for the full test suite.

## Player interface

Use `PlayerView` / `play_with_interface`, not an unfiltered state or the entire
legal list. The acting faction can differ from `meta.active_player` during Pay,
Exiles, Approach reactions or combat. Route each view to its named perspective.

```python
from inferno.scenarios import load_scenario
from inferno.llm import play_with_interface
from inferno.invariants import check_all_invariants

state = load_scenario("F", seed=42, hidden_mats=True)
# model_callback(view) sends view.overview(); answers any number of view.query
# requests, then returns a state-bound action_id/state_version selection.
while state["meta"]["phase"] != "victory":
    play_with_interface(state, model_callback)
    check_all_invariants(state)
```

The 3,500-character briefing target is soft. Essential sections and complete
pending decisions are never cut. Explicitly abbreviated/deferred data remain
available through focused `inspect` requests, including all own cards, visible
mats, board records, Calendar information and history. `snapshot` retrieves the
whole filtered state. Every legal-menu entry is reachable through unranked
category pages. Templates and optional handler parameters are not limited to
printed default arguments. Follow `next_cursor` until null to inspect all pages.

See **LLM_PLAY_GUIDE.md** for the complete protocol, privacy rules and
`examples/play_with_claude.py` for a working provider callback. Use `--stub`
explicitly for its offline deterministic test policy; absence of credentials
never silently changes the player to a stub.

## Shell-driven play

```sh
PYTHONPATH=src python -m inferno.cli new F --seed 42 --hidden-mats --out game.json
PYTHONPATH=src python -m inferno.cli briefing game.json --side guelph
PYTHONPATH=src python -m inferno.cli legal-moves game.json --side guelph
PYTHONPATH=src python -m inferno.cli query game.json '{"request":"actions","page_size":12}' --side guelph
PYTHONPATH=src python -m inferno.cli inspect game.json card_reference --keys F3 --side guelph
PYTHONPATH=src python -m inferno.cli choose game.json '{"action_id":"ID","state_version":"VERSION"}' --side guelph
```

IDs and cursors expire when the position/revision changes. Rejected selections
never alter the save. A `choose` that reaches a tactical election returns an
owner-filtered `awaiting_decision` packet and leaves the save unchanged. Inspect
and extend its `--decisions-json` prefix as documented; the complete action commits
only when all choices have explicit answers. There is no strategic fallback.
Never send the save file or explicit operator `state --raw` / `do` output to a
model. Native library dispatch is for trusted engine tests, not a privacy boundary.

## Bug hunting is separate from player choice

```sh
PYTHONPATH=src python selfplay_bughunt.py F --seed 11 --max-steps 8000
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python benchmarks/interface_output.py --out benchmark.json
```

The legacy smoke driver uses execution probes to diagnose over-enumeration. The
new player interface deliberately does **not** use that validated/probed palette:
probing and dropping moves could conceal choices or use future dice. A rejected
concrete menu entry is a bug to record, not a reason to hide it from the player.
Distinguish structural invariant checks from full rules correctness, and output
counts from correctness. Preserve exact reproduction states and action sequences.
