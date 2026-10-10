# Interactive Scenario A self-play — 9 October 2026

## Result and method

Scenario A (Dolenti Note), seed 42, open mats, no advanced Vassal Service.
Started from main commit b7cc7c533b1da13e87f0ed86dc4414a3ff13fef9.
The assistant chose both sides' plans, Levy choices, movements, logistics,
sieges, and assaults. The harness resolved dice and its default within-combat
choices. Single-option procedural steps were advanced automatically. This was
not the repository's random self-play policy, nor two independent blind agents.

The game reached its normal endpoint after 157 accepted actions in two turns.
The recorded result was Ghibelline 4.5 VP to Guelph 2 VP. All 157 post-action
invariant checks passed, and replay reproduced every recorded state hash and
the final state exactly. There were four Storms (nine rounds in total), plus
Sieges, Supply, grouped March, Pay, card draws, and end-turn processing.

A planning correction described below was applied at action 24 before
continuing the same saved position. No accepted action or die result was
rewound. The remaining Surprise defects affect rules fidelity, so the score
is a diagnostic outcome, not an assurance that corrected rules give that score.

## Course of play

Arezzo advanced on Cortona with Palvesari and Balestrieri. Firenze advanced on
Poggio Bonizio. Siena successfully mustered Provenzano at Siena and led both
Lords to Montalcino. The initial assaults failed; a Palvesari Armigieri did
correctly survive a protection roll of 3 at Cortona (action 55).

On turn 2, Siena's remaining Coin paid Provenzano to extend Service from box
2 to box 3. Both sides reinforced and resupplied. Another costly Ghibelline
assault failed, but Provenzano subsequently obtained Montalcino's surrender
(action 133). The Ghibellines then held their gains. The final Guelph surrender
attempts at Cortona and Poggio Bonizio failed.

The Guelph player made a genuine strategic mistake: Ravaging printed-Guelph
Cortona gained food and Loot but correctly awarded 0.5 VP to the Ghibellines.
That is not an engine defect.

## Corrected findings

1. **Only one Command card per Lord could be planned.** Rule 4.1.1 supplies
   three action cards per Lord. Both the handler and the legal menu treated a
   Command ID as a unique physical card. They now permit three occurrences,
   reject the fourth atomically, and retain single-copy Treachery handling.
   Deck IDs continue to identify card types; their representation is documented.
   This was discovered when adding the second Arezzo/Firenze cards to the first
   winter plan. Tests cover both sides, menu availability, and atomic rejection.
2. **Briefing markers did not distinguish sides.** Both Guelph and Ghibelline
   Allegiance and Siege markers used the initial `G`. They now spell out the
   side name, with a regression comparing Cortona and Montalcino.

## Findings recorded at the end of this game

**Subsequently corrected:** all five findings below are addressed in
[the self-play follow-up](../SELFPLAY_FIXES.md). Their original observations and
reproduction points are preserved here as the historical playtest record.


### Surprise's first legal window is rejected

After action 35 (Arezzo has Marched alone to Cortona, before Besiege), playing
held F3 is rejected with `NO_PLAY_WINDOW`. `_HOLD_EVENT_WINDOW` classifies F3/S3
as generic combat events; `_combat_window_open` requires an existing siege or
Approach. The printed Surprise window is upon Besieging after arriving alone,
not an already-established siege. The probe was run on a copy and did not
change the played game. Later Firenze could play F3 at Poggio Bonizio because
another Guelph Lord already stood at a siege elsewhere, which masks the error.

### Surprise loses its third Storm round

Action 66 used F3 at Poggio Bonizio. Both sides still had Forces and no
concession occurred, but the Storm stopped after round 2. The Surprise handler
places two Siege markers and calls `resolve_storm`; `resolve_storm` sets the
round limit from the Siege count. Surprise's explicit three-round exception is
not passed to the resolver. The Arts of War reference F3/S3 explicitly permits
up to three rounds despite only two Siege markers.

### Important choices are missing from the player interface

At action 39, Commander Siena and Provenzano were co-located, but the March
menu listed only single-Lord moves. The documented `with_lords` argument was
submitted directly and the group moved legally in action 40.

At action 64, the relevant F3 Surprise play was missing from the menu; it was
submitted directly before Besiege. The briefing also does not list the owner's
Held Event hand, making these omissions harder for a player to notice.

These omissions mean a legal-menu-only LLM cannot make all the choices used
in this game. They should not be hidden by calling the game a clean smoke test.

## Reproduction

The adjacent `.actions.json` file contains the accepted action sequence in
order. Load Scenario A with seed 42, apply each action with `dispatch`, and run
`check_all_invariants` after each. With the planning correction and the still-
open defects as tested, the endpoint is Ghibelline 4.5, Guelph 2.

The accompanying chat download also contains full action results and player
rationales, initial/final states, findings, and per-action replay hash verification.

Rule sources: checked-in `reference/Inferno_Rules_Reference.txt` (4.1.1),
`reference/Inferno_Commands.txt` (March, Supply, Siege), and
`reference/Inferno_Arts_of_War_Reference.txt` (F3/S3 Surprise, Palvesari).
