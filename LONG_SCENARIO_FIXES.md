# Long Scenario F corrections — 10 October 2026

Repairs the eight findings from the 647-action primary and 1,688-action
endurance playtests of `60da72b8265e4d5e797d56499dec88046a852853`.
Rule sources are the checked-in Call to Arms, Sequence of Play, Siege, and
Scenario reference transcriptions. No game variants are introduced.

| Finding | Correction |
| --- | --- |
| F-LONG-01: lost extra Muster | Allies opens a persistent `allies_muster` substep. Only the chosen eligible Lord may spend the full normal allowance. Normal Muster actions and `levy_muster_done` work here. Lordship Events remain usable, and the Commander can Levy for his Comune. |
| F-LONG-02: stale War permission | Clear the permission when the Levy ends and at both next-Levy entry paths; a new War Event can grant it again. |
| F-LONG-03: wrong running Sack score | Deduct removed enemy Allegiance points before adding the Ruins half-point. Both display and Call to Arms eligibility see the corrected running score. |
| F-LONG-04: Gather splits Comune | Gather and ordinary March share compulsory group resolution. A Comune cannot move independently; a Besieged pair cannot escape. Gather remains free of Feed/Moved costs. |
| F-LONG-05: repeated Comune setup duplicates units/assets | Fresh mat setup is separate from reinforcing an existing mat. Only unmustered Special Vassals add troops; existing assets and losses remain unchanged. Legal combinations are exposed in the menu. Captured Carroccio cannot be regenerated. |
| F-LONG-06: recall leaves old Comune behind | Both Service-disband paths set aside attached Comune mats/cylinders, clear old occupancy and resources, and return their cards. Recall then permits a genuinely fresh setup. Both sides and printed-name/internal-ID attachment forms are supported. |
| F-LONG-07: late final-turn ending | The turn-16 boundary is checked at Game End, before Repair/Waste. Terminal states reject subsequent actions and have no legal moves. Earlier End-marker endings still apply. |
| F-LONG-08: process-dependent hashes | Persist War permission and completed Call to Arms side sets in sorted order. Exact per-action replay hashes are checked in separate processes, without normalization. |

## Qualification to the original extra-Muster finding

The original action-105 request named Arezzo at hostile Cortona, where he was
besieging. Under 3.4 he was not an eligible recipient in that position. The
old engine wrongly granted that request *and* lacked any playable extra segment.
The regression now rejects Arezzo atomically, then grants and spends the earned
segment with eligible Firenze in the same saved position. It does not legalize
an ineligible Muster to reproduce an inaccurate expectation from the old report.

## Evidence and tests

`tests/test_long_scenario_fixes.py` adds 30 cases covering the six saved failure positions,
both factions' attachment/disband behavior, duplicate/refill prevention,
Lordship allowance and Event use, invalid-action atomicity, captured Carroccio,
menu purity, final-turn boundaries, and cross-process serialization. Fixtures
retain all game fields and remove only the old diagnostic history.

`long_scenario_regression.py` replays the original endurance choices using the
current rules and stops at the corrected Game End. The result is 1,684 actions,
turn 16, Ghibellines 4–2. The four previously accepted post-game actions are not
executed. Every new action result and full-state hash is identical under process
hash seeds 0 and 1; all post-action structural invariants pass. The standard CI
now runs this regression.

`long_scenario_selfplay.py` is an explicitly labeled deterministic test policy,
not an official bot or rule variant. It starts a fresh Scenario F, accepts
eligible optional Calls to Arms, and uses ordinary public action dispatch. It
adds a Commander/Comune co-location check after each action. Seed 20261010
completed in 1,512 actions on turn 14 (Guelphs 9.5–0.5), with eight Calls to Arms,
14 Commander-to-Arms actions, 16 Comune setups, and 16 completed extra Muster
segments. All post-action checks passed. It voluntarily skips Gather; that
movement path is covered separately by the saved-position regressions.

Validation commands:

```sh
python -m pytest -q
python long_scenario_regression.py
python long_scenario_selfplay.py --seed 20261010 --output /tmp/inferno-long-fresh
for scenario in A B C D E F; do
  PYTHONPATH=src python selfplay_bughunt.py "$scenario" --seed 11 --max-steps 8000
done
PYTHONPATH=src python cardfx_fuzz.py --seeds 6
PYTHONPATH=src python saveload_fuzz.py --seeds 8 --max-steps 8000
PYTHONPATH=src python robustness_fuzz.py --seeds 3 --max-steps 6000 --probe-every 8
PYTHONPATH=src python state_injection_fuzz.py --seeds 2 --max-steps 400 --probe-every 60
```

Passing these regressions addresses the reported failures; it does not establish
exhaustive correctness for every possible rules interaction.
