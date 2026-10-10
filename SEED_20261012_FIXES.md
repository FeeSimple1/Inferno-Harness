# Scenario F seed 20261012: follow-up repairs

This change fixes the seven reported defects from the retained 1,497-action
Scenario F playtest on local commit `b9346646c824517c0a4c1880f30f9f87dfac1e47`.
The publication also includes that previously unpublished commit's eight
long-game corrections; see `LONG_SCENARIO_FIXES.md` for their separate scope.
The code is one current harness, not a rules variant.

## Reported findings and corrections

| Finding | Correction |
| --- | --- |
| Gather offered six Road legs to a Command-2 Lord | Track a per-Lord Command allowance across the entire Gather substep. Apply ordinary March pricing, including shared transport, Laden status, Road Works, and a single first-Road discount. Reloading or alternating Lords does not reset it; menu and handler share validation. Gather does not Feed or change Campaign Moved flags. |
| Merely holding Treasurers enabled a free Call to Arms | Possession no longer enables `levy_cta_declare`. The F23 play must consume the Event and exactly two legal Guelph Coin before enabling declaration. Invalid sources and closed windows reject atomically. The final Guelph opportunity after a Ghibelline decline remains available. |
| Array Rout treated as permanent loss | Fully routed Lords receive the proper Retreat/Withdraw election and routed-unit recovery. The Commander and Comune follow the same movement outcome, count as one cylinder for withdrawal, and are removed only when actually required. |
| Comune Spoils erased by Commander cleanup | Process all losing mats' Spoils and Knights' Quarter before destructively removing any attached mat. Carts, Coin, and the Carroccio are transferred/captured exactly once, including removal after failed recovery. |
| Battle decision history changed retroactively | Snapshot decision information, offered choices, and selected choices recursively. Callbacks cannot mutate the recorded state of an earlier choice by sharing its objects. |
| Missing/duplicate dice in action logs | An action-scoped collector records every actual HarnessRNG roll once, in execution order, including separately resolved combat aftermath and Revolt. Dispatch uses that journal rather than concatenating overlapping summaries. Draining a local roll log no longer resets its consumed-roll counter. |
| Sorted saves changed actual Waste losses | Normalize game mappings to explicit stable orders in dispatch and in a pure legal-menu view. Defaults no longer depend on JSON key order; direct recovery and Spoils helpers also order their inputs. Arrays such as Plans, decks, queues, and selected destinations retain their meaningful order. |

Waste's existing default, when no explicit distribution is supplied, now has an
explicit asset priority: Coin, Cart, Provender, Loot, Ship. Explicit legal player
choices take precedence. This is a deterministic interface default, not a new
rule or a strategic bot prescription.

## Related paths repaired

Sally now shares the field-battle aftermath rather than maintaining a second
path with the same premature-removal defect. Actual retreat without concession
uses harsh recovery; withdrawn Sallying Lords use normal recovery. Doctors'
restoration occurs before testing a Storm participant for final removal.

Action history owns independent copies of returned rolls and changes, so a
consumer editing its result cannot rewrite the recorded action. Rejections
restore the pre-action mapping order as well as all mechanical values.

## Reproduction and regression coverage

`tests/test_seed_20261012_fixes.py` contains 37 new cases. Its retained positions
in `tests/fixtures/seed_20261012/` include the actual pre-Gather, pre-Treasurers,
pre-battle, post-Strikes, and pre-save states. Only their append-only history was
omitted. The manifest records provenance and checksums. Historical inputs are
retained as evidence, not as assertions that the old outcomes were correct.

The save/reload regression applies the original 104-action continuation from
after action 339 through action 443 to both an uninterrupted state and a
sorted-key JSON reload. Every action result and resulting state must match,
including actual Cart/Coin amounts after Waste. Pure legal-menu equality is
also checked on four retained positions. The battle reproduction instruments
actual RNG calls, compares the complete action journal and advance counter,
and independently snapshots live decisions before checking the returned trace.

Additional cases cover Gather costs and persistence, paid/invalid/final-window
Treasurers, fully routed withdrawal and retreat, capture before/after recovery,
true removal without recovery, hostile callback mutation, and Sally recovery.

The existing long-game removal test now establishes a genuinely impossible
Retreat/Withdraw before asserting removal; its original no-recovery assertions
remain. The older synthetic Relief-Sally test now gives the besieging side its
own siege markers and the defenders their Stronghold. Its one-marker reduction
and flag-cleanup assertions remain unchanged. The old source-wiring assertion
now follows Sally's delegation to the shared aftermath; a new behavioral test
independently confirms that actual Sally removal still triggers Revolt.

`saveload_fuzz.py` now uses the CLI's actual `sort_keys=True` serialization,
compares every action result, repeats saves every 17 actions, and compares legal
menus at those boundaries. The former insertion-order-preserving round trip
could not expose the reported bug.

## Validation commands

```sh
python -m compileall -q src tests examples
python -m pytest -q
for scenario in A B C D E F; do
  PYTHONPATH=src python selfplay_bughunt.py "$scenario" --seed 11 --max-steps 8000
done
PYTHONPATH=src python cardfx_fuzz.py --seeds 6
PYTHONPATH=src python saveload_fuzz.py --seeds 8 --max-steps 8000
PYTHONPATH=src python robustness_fuzz.py --seeds 3 --max-steps 6000 --probe-every 8
PYTHONPATH=src python state_injection_fuzz.py --seeds 2 --max-steps 400 --probe-every 60
```

These are repairs with reproduction coverage, not an exhaustive certification
of every Inferno rule or every possible game state. Rule sources are the
checked-in Call to Arms, Commands, Battle and Storm, and Arts of War references.
The earlier playtest score is not asserted to remain valid after these repairs.
