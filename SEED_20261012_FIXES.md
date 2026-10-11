# Scenario F seed 20261012 corrections

This change builds on the prior Scenario F long-game repair and resolves the
seven additional defects found in the second endurance game.

| Finding | Correction |
| --- | --- |
| Gather ignored the Lord's Command allowance | Gather now prices every leg with the ordinary March rules, records cumulative Command spent, and removes unaffordable legs from the legal menu. |
| Holding Treasurers enabled a free Call to Arms | F23 must be played, its two Coin paid, and the card consumed before the normal this-Levy War permission exists. |
| Fully Routed Lords were treated as permanently lost | Routing out of the Array is recorded separately. Lords Retreat or Withdraw, roll their Routed-unit losses, and are removed only if no Forces remain afterward. |
| Commander removal erased Comune Spoils | Combat removal processes an attached Comune's Assets and Carroccio before clearing either mat. |
| Battle decision history mutated after the choice | Choice metadata, options, and callback payloads are deep snapshots. |
| Dice logs omitted aftermath rolls and duplicated handler rolls | Post-Battle Service, Loss, and Revolt rolls join the action result; dispatch merges already-reported rolls by multiplicity rather than duplicating them. |
| Save/load changed Exiles, Feed, and Waste outcomes | Candidate, feeder, donor, Lord, Asset, and default Capability ordering is canonical. |

`tests/test_seed_20261012_fixes.py` adds focused regressions for all seven
findings. The saved action-623 battle and the uninterrupted-versus-save/reload
continuation were also rerun directly during verification.
