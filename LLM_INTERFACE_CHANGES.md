# Loss-aware player interface

## Starting point and prior playtest repairs

This work started from published `main` commit
`4cda8cfe87d1827a4e5f235f337e68aef1e1c2c8` (6.15.0). It already contains
`LONG_SCENARIO_FIXES.md`, `SEED_20261012_FIXES.md`, and the earlier Scenario F
repairs. Those repairs were not reimplemented or attributed to the interface
change. The 52 long-scenario and 9 seed-20261012 regressions were rerun before
interface work. The saved Siena position from the prior playtest also resolved
with all 41 actual dice rolls recorded exactly once and Routed-unit recovery
before removal.

## New interface contract

- Structured whole briefing sections, with complete essentials and a soft
  character target; explicit complete/abbreviated/deferred status and retrieval.
- Actual deciding faction, phase, pending choices, recent changes, all action
  kinds, full own Held hand, visible Capabilities, resources and Service.
- Focused whole-record pages for Lords, board/ways, Calendar, cards, effects,
  history, phase context, printed card/effect-argument references, action/helper
  argument grammar, and a complete filtered snapshot. Unknown visible fields
  remain available rather than silently disappearing from the interface.
- Exact category/lord/card/field filters and exhaustive action pages, never a
  ranked shortlist. IDs preserve every original move's metadata and support
  complete argument overrides for optional parameters and templates.
- Perspective-bound state versions and filter-bound cursors. Stale selections
  fail before any dispatch or file write. Tactical IDs also bind their context,
  option set, parent action and ordinal.
- Private opponent targeting uses conditional templates rather than exposing
  hidden unit types, Assets or Vassal readiness through a menu oracle. Every
  legal instantiation remains executable through the same dispatcher.
- Live tactical elections go to their owner, with all options accessible. An
  interrupted or invalid callback never becomes an automatic strategic choice.
  Operator bulk scripts are not allowed to preselect the opponent's decisions;
  the same elections remain available through owner-bound DecisionView pages.
- CLI combat continuations keep the save unchanged until all elections are
  complete. Pending replies identify the faction and do not echo the originating
  player's raw action parameters. Explicit raw/operator entry points remain
  separate. Missing saves are errors, not fabricated placeholder games.

The default callback example uses a retrieval loop, not full-menu serialization.
Provider length stops pause instead of submitting partial JSON. A stub player
requires explicit selection; absent credentials never silently select a stub.

## Independent correctness checks

The dedicated interface tests cover both factions, oversized briefings/pending
messages/action descriptions, complete Held hands and references, all menu
pages/filters/templates, long histories, exact state immutability, stale
cursors/selections, hidden-state noninterference, tactical visibility/ownership,
interrupted combat and CLI continuation. Existing mechanics suites remain
independent of output savings. Old tests asserting a hard 3,500-character cap,
raw CLI menu shape, raw-state callback signature or fictional missing-file stub
were updated to assert the deliberately changed interface contract; their card
visibility, acting-player and action-availability assertions were retained.

`benchmarks/interface_output.py` additionally executes complete real games in
independent direct-dispatch and interface states. It compares every mechanical
result and state, checks invariants, and reconstructs each faction's entire raw
menu from all pages at every sampled position. It does not claim that an existing
rules enumerator is an exhaustive mathematical specification of Inferno.

## Measurement protocol and limits

Default cases are A seed 11, C seed 11, and the longest Scenario F seed 20261012.
The benchmark charges each overview, all pages in the selected action category,
relevant complete Lord and board records, first-use card/action references,
private reaction views and all tactical-option pages. Requests and selections
are separately counted. It also measures the cost of reading every menu page.

Four controls/results must not be confused:

1. The old documented 3,500-character truncated briefing plus formatted full
   menu. It omitted information and live tactical elections, so its smaller
   size is not a correctness-equivalent success criterion.
2. Identical essential information, additional fact/reference lookups and
   tactical elections, with an unsolicited formatted full menu.
3. The same complete-information control with a compact full menu, to separate
   pagination benefits from whitespace savings.
4. The new overview/pages/focused-lookups path, with all those lookup outputs
   included. A player who reads the entire menu can incur pagination overhead.

Exact character and UTF-8 counts are always reported. `--tokens` requires the
named `cl100k_base` tokenizer and records its package version; it fails rather
than estimating token counts. This deterministic lookup policy caches static
references after first use per faction. A fresh-context model may need repeated
reads. These are emitted-payload measurements, not a live-model quality study or
provider bill: system prompts, conversation resends and cache accounting differ.
No minimum saving is a correctness gate. Negative savings are reported as such.

## Reproduction

```sh
python -m pip install -e '.[dev]' tiktoken
python -m pytest -q
PYTHONPATH=src python benchmarks/interface_output.py --tokens --out interface-output.json
for scenario in A B C D E F; do
  PYTHONPATH=src python selfplay_bughunt.py "$scenario" --seed 11 --max-steps 8000
done
PYTHONPATH=src python cardfx_fuzz.py --seeds 6
PYTHONPATH=src python saveload_fuzz.py --seeds 8 --max-steps 8000
PYTHONPATH=src python robustness_fuzz.py --seeds 3 --max-steps 6000 --probe-every 8
PYTHONPATH=src python state_injection_fuzz.py --seeds 2 --max-steps 400 --probe-every 60
```

Final measured numbers and CI logs are produced by the verification run, not
inferred from smaller individual prompts. See `LLM_PLAY_GUIDE.md` and
`examples/play_with_claude.py` for integrations.
