# Self-play follow-up corrections

This change resolves the five outstanding findings in
`playtests/2026-10-09-scenario-a.md`. The Command-card copy limit and ambiguous
side markers were already corrected in the preceding merge. The rules sources
are the checked-in Arts of War reference (F3/S3 Surprise and other Held Events),
Commands (4.3.1–4.3.5), and Battle and Storm (4.5.2).

## Corrections

| Finding | Correction |
| --- | --- |
| Surprise rejected at its initial legal window | March records the destination's pre-arrival occupancy and pauses for Besiege/Bypass. F3/S3 is offered only for that lone arrival at an Enemy Stronghold; an unrelated siege cannot open the window. |
| Surprise stops after two rounds | Surprise explicitly allows three Storm rounds while retaining two Siege markers, Siegeworks protection 1–2, and Walls −2. Normal Storm limits are unchanged. Concession still ends combat immediately. |
| Group March absent from the legal menu | Commander subsets and compulsory Lieutenant/Comune companions are included. The menu and executor share pure group validation and pricing for shared Carts, Laden status, Road Works, besieged Lords, and scenario restrictions. |
| Held Event plays absent from the legal menu | The menu now includes playable Held Events and concrete target, mode, payment, and selection arguments rather than requiring an undocumented direct submission. Surprise includes the normal Storm decision channel. |
| Owner's Held Event hand absent from briefing | The owner's card IDs and Event names appear before the long board/history sections. The opponent's hand remains hidden with either open or hidden mats. |

Playing Surprise immediately chooses Besiege and resolves its mandatory Storm.
It cannot be left armed for a later Lord, another Stronghold, or a Bypass choice.
Ordinary groups and Lieutenant pairs are ineligible; a Commander with his own
Comune still counts as one cylinder. Commander/Comune matching accepts the
scenario data's printed commander name as well as its internal Lord ID.

The free Besiege/Bypass decision also remains available when March spent the
last Command action. Feed/Pay/Disband cannot run before that decision. Rejected
Surprise combat decisions restore the Event, arrival record, resources, and RNG.

## Related defects exposed by the new paths

Surprise now uses the same Storm aftermath as an ordinary Storm: routed-loss
rolls, Sack, Doctors, and removal of Lords with no Forces. Previously its separate
shortcut bypassed part of that processing.

A played duration Event now occupies its active duration zone, not that zone
and the discard pile simultaneously. The additional menu coverage exposed this
physical-card duplication during save/load testing.

The new Held Event path exposed a premature base-Lordship check that rejected
legal actions granted by Constituto and similar bonuses. Menu and handler now
share the complete allowance, including Capability bonuses. Event bonuses
stack; segment-only grants expire after that Muster/Allies segment, while
This-Levy grants survive into Call to Arms but not into another Levy.

Greek Fire honors the selected enemy unit and This-Lord Capability. F11 and F23
honor the selected Treachery card; F23 exposes the legal two-Coin payment
splits. Listing choices never consumes a card, changes the saved state, rolls
combat, or consults future dice to decide what to offer.

## Regression coverage

`tests/test_selfplay_followup_fixes.py` adds 51 regression cases. They include:

- Both Surprise cards, the actual original action-35 blocked position, three
  rounds with two Siege markers, the normal Storm limit, and immediate concession.
- Occupied destinations, groups, Lieutenant pairs, the Commander/Comune exception,
  last-action arrival, atomic rejection, real routed losses, and save/load.
- The original action-39 grouped March position, all eligible Commander subsets,
  shared Carts, Laden/Road Works costs, and no mutation during enumeration.
- Targeted Held Event choices, selected Treachery/payment outcomes, physical-card
  conservation, owner/opponent hand visibility under both mat options, and
  spending/stacking/expiration of Lordship bonuses. The exact Scenario C seed-3
  stress path that exposed the allowance bug is a regression test.

Older Surprise fixtures now perform a real March rather than treating an
unrelated siege or an unscoped injected flag as permission to play the card.
The Ambush test still checks that Ambush is absent when not held; it no longer
incorrectly bans every other Held Event from the response menu. Existing
assertions of card removal and effect application were retained.

Validation commands:

```sh
python -m pytest -q
for scenario in A B C D E F; do
  PYTHONPATH=src python selfplay_bughunt.py "$scenario" --seed 11 --max-steps 8000
done
PYTHONPATH=src python cardfx_fuzz.py --seeds 6
PYTHONPATH=src python saveload_fuzz.py --seeds 8 --max-steps 8000
PYTHONPATH=src python robustness_fuzz.py --seeds 3 --max-steps 6000 --probe-every 8
PYTHONPATH=src python state_injection_fuzz.py --seeds 2 --max-steps 400 --probe-every 60
```

The historical self-play score remains a record of the game as it was played,
not a prediction of the outcome with these corrections. Passing this regression
coverage does not establish exhaustive rules correctness for every game state.
