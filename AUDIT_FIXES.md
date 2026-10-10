# Inferno audit corrections — v6.14.0

Scope: the 22 defects reported against `9c505c76481e2d5cce32f65a61717670a625c690`.
The rule sources are the checked-in `reference/Inferno_*.txt` transcriptions,
particularly Commands, Battle and Storm, Sequence of Play, and Arts of War.
This is a regression repair, not a claim of exhaustive rules certification.

| Reported defect | Correction |
| --- | --- |
| Draws only reach the first six positions | Unbiased whole-deck selection from logged d6 rolls; reject the excess numeric range. |
| Paid off-right Service is disbanded | Only explicitly off-left Service is expired; off-right markers are preserved. |
| Legal payments skipped | Pay discovery and menus include Coin, Loot, co-located payers, and Podesta rates. |
| Opponent plan leaks through history | Redact plan/draw transcript details and unrevealed draw queues; withhold RNG reconstruction fields. |
| Fifth fallback PASS deadlocks planning | Enforce seasonal plan size in the handler; fallback selects an actual legal move and finishes a full plan. |
| Repeated reveal skips a turn | Require completion of the active card and pending decisions, including FPD. |
| Events consumed before choices | Ordered draw queue, explicit pending immediate-Event resolution, and atomic Held-Event validation. |
| Besieged ordinary March | Reject trapped Lords, including group members and free first Road Marches. |
| Enemy Supply source accepted | Validate route endpoints as well as intermediate locales and zero-length routes. |
| Storm continues after concession | Stop immediately, without another Strike step or completed round. |
| Hits disappear at Rout | Return unused typed hits and retarget them through the new flanking situation. |
| Palvesari Armor ignored | Apply +2 Armor before Crossbow reduction, ending the bonus at the third routed Armigieri on that mat. |
| Capability scope unenforced | Derive scope from printed Capability, enforce recipient eligibility, duplicate titles, and mat limits. |
| F9/F13 miss Mustered Service | Distinguish a cylinder on the Calendar from a Mustered Lord's Service marker. |
| Rejected actions corrupt state | Roll back all handler failures; preserve resources, decks, Lordship, history, and RNG. |
| Negative Pass creates actions | Reject zero and negative counts. |
| Entire-card restrictions absent | Track whether any Command already started, including a free March. |
| Unauthorized marching groups | Require a Commander or valid Lieutenant relationship. |
| Remote/shared Supply missing | Enumerate valid remote sources and use co-located shared Carts. |
| Example prompts wrong player | Build the prompt and briefing for the mandatory legal move's owner. |
| Array action/args crashes retry | Validate envelope types before handler lookup or argument use. |
| Exiles loses shifts/clamps edges | Retain unused shifts, refresh candidates, and use explicit off-calendar pools. |

## Related defects exposed during verification

The printed Capability-scope audit corrected Event/Capability confusion in the
scope registry, not only F6. Scenario B's assigned S18–S20 cards leave the draw
pool before its extra random draw. Re-entering the Calendar or mustering now
clears obsolete off-edge cylinder/Service pool entries. Event consequences
finish before the next queued Event resolves.

Older fixtures were adjusted where they skipped newly required Pay decisions,
assumed a fixed biased draw, used unauthorized groups, or counted only the old
card zones. The card-effect stress fixture now removes a duration Event before
staging that physical card as a Capability; it previously duplicated F5 at the
newly reachable Scenario A seed 6. Assertions were retained, not bypassed.

## Regression coverage

`tests/test_v614_audit_regressions.py` adds 137 cases, including all 52 printed
Capability scopes, all 26 Guelph cards reached over 100 initial-draw seeds,
atomic rejection checks, mandatory decision ownership, save/load while a draw
is pending, calendar boundaries, new-flank hit conservation, and Palvesari
normal/Crossbow/third-Rout behavior.

Validation commands (also run by the repository CI):

```sh
PYTHONPATH=src python -m pytest -q
for scenario in A B C D E F; do
  PYTHONPATH=src python selfplay_bughunt.py "$scenario" --seed 11 --max-steps 8000
done
PYTHONPATH=src python cardfx_fuzz.py --seeds 6
PYTHONPATH=src python saveload_fuzz.py --seeds 8 --max-steps 8000
PYTHONPATH=src python robustness_fuzz.py --seeds 3 --max-steps 6000 --probe-every 8
PYTHONPATH=src python state_injection_fuzz.py --seeds 2 --max-steps 400 --probe-every 60
```

See `ACTIONS.md` for the new immediate-Event action and changes to planning,
payment, Capability placement, and Exiles handling. The changed draw algorithm
intentionally changes old seed outcomes; cross-version replay compatibility
is not guaranteed.
