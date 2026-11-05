# Cross-game audit repairs

The November 4, 2026 cross-game audit identified eight Inferno defect groups.
The first repair batch addressed **IF-4 — hidden troop totals**.

With Hidden Mats enabled, player snapshots use a constant hidden marker for
opposing Forces. The old marker contained the exact sum of the hidden army.
Army size no longer changes the player snapshot or briefing. The owner still
sees their own Forces, open mats still show precise Forces, and combat reveals
only participating mats for the duration of the combat visibility scope.

Regression tests cover both factions, saved and explicit Hidden Mats options,
unchanged source states, repeated filtering, briefings, and combat reveal and
re-hide behavior. Existing interface tests now require the constant marker.

## Escape and Retreat batch — INF-1, INF-2 and INF-3

- **INF-1 — Unladen Avoid:** solo and group Avoids use two Provender per Cart
  on a Road or one on a Track. Co-Avoiders share spare capacity while food
  stays on its original mat. Loot and excess Provender go to the Approaching
  Lords as Spoils. Each menu option lists the discards, and execution uses
  the same preview to check the group, route, Ambush and destination before
  moving anyone or spending Assets.
- **INF-2 — Bypass on arrival:** Avoid into an Unbesieged enemy Stronghold
  places a Bypass marker and marks the arriving Lords as Bypassing. They can
  Encamp on a later Command. Friendly, Ruined and already Besieged locations
  do not create a new Bypass, and departing Lords still clear obsolete
  markers at their origin.
- **INF-3 — Conceded Retreat:** Spoils use the actual Retreat Way and spare
  Carts of co-retreaters on that route. Where two legal Ways connect, the owner
  can choose the Way explicitly. Conceders keep Carts, Coin, Ships and their
  Carroccio; existing non-conceding and Withdraw Spoils rules still apply.

Avoid and Battle Spoils use the same capacity-aware distributor. It skips
full mats and loses only markers that no recipient has room to take.

Thirty-three new regression cases cover both Way types, grouped and split
Avoids, cart sharing, discards and overflow, Bypass and Encamp, Ambush and
invalid-input rollback, explicit parallel Ways, conceded and non-conceded
Retreat, Withdraw and save/load. Nineteen fail on the previous main revision;
fourteen preservation cases pass. The older Approach predicate test now
checks the legal menu's behavior directly.

Validation: 1,164 tests passed. The six CI self-play scenarios all reached
game end without anomalies. Card-effect, save/load (48 scenario/seed pairs),
malformed-input and state-injection fuzz checks also reported zero anomalies.

## Asset caps and Spoils batch — INF-4 and INF-5

- **INF-4 — Asset caps**. Tax caps Coin at 16 and reports actual gain and
  overflow. Sack uses the shared capped distributor for both printed rewards
  and captured Assets, filling eligible allies before losing excess.
- **INF-5 — Owner allocation**. Field Battle, Sack and Avoid expose
  `spoils_recipient` and `spoils_amount` through the existing post-Battle
  decision channel. The owning faction may concentrate or split each pool
  among surviving eligible Lords. The legal menu advertises the choices,
  including Surprise's automatic Storm. Default allocation remains capped
  round-robin. Battle and Sack allocation wait for Losses and removal so
  an eliminated winner cannot receive Assets.

Seventeen new regression cases cover ordinary and Podesta Tax at zero, 15
and 16 Coin, printed and captured Sack overflow, concentrated and split
allocations, a winner eliminated by Losses, actual Storm resolution, Avoid
scripts and owner-routed player callbacks. Invalid recipients, amounts and
pinned factions reject atomically. Interrupted player responses roll back
the whole action. Fourteen of these cases fail on the preceding main
revision and three preservation cases pass.

Validation completed with 1,181 passing tests. All six CI self-play scenarios
reached game end with zero anomalies. Card-effect checks covered 52 cards
and six seeds. Save/load covered all six scenarios and eight seeds.
Malformed-input and state-injection fuzz checks also reported zero anomalies.

## Feed and Friars batch — INF-6 and IF-5

- **INF-6 — Feed choices**. The feeding faction chooses Provender or Loot
  and, during sharing, the donor. All Moved/Fought Lords feed their own
  Forces before sharing surplus. Commander and Comune mats count together.
  The same choices work when a Command ends explicitly or automatically.
  Scripts reject invalid and unused entries atomically. Player interfaces
  route each election to its owner and can pause and resume from the
  unchanged save. Results record every spent donor/resource pair.
- **IF-5 — Friars**. S14 has its printed This Campaign classification.
  Completing the Guelph Plan shuffles its chosen cards with the logged RNG.
  Both factions' snapshots conceal the remaining order, and public results
  and history conceal the shuffle indices. Commands reveal normally. Older
  Held copies remain playable. An older save with a completed, active S14
  Plan shuffles it once before revealing. Reset clears the effect.

Twenty-nine regression cases cover explicit and automatic Feed, mixed
resources, donor selection, own-food reservation, Commander/Comune feeding,
invalid-script rollback and retries, both player perspectives with Hidden
Mats, interrupted selections, and resumable sessions. Friars cases cover
normal drawing, deterministic save/load, actual permutations, snapshots,
public action results, version privacy, normal reveals, legacy saves and
Reset. Twenty-seven fail on the preceding main revision and two preservation
cases pass.

Validation completed with 1,210 passing tests on Python 3.12. All six CI
self-play scenarios reached game end with zero anomalies. Card-effect checks
covered 52 cards and six seeds. Save/load covered all six scenarios and eight
seeds. Malformed-input and state-injection checks also reported zero anomalies.

All eight original Inferno findings are fixed.

## Second audit, batch 1 — INF2-1, INF2-2 and INF2-4

- **INF2-1:** Losing a Lord's final Force outside combat invokes temporary
  At Service Limit Disband under 1.6/3.3.2. Advanced Vassal expiry and Tau
  Company discard clear the mat and place the cylinder for later Muster,
  without Beyond-Service Revolt/Treachery. Surviving regular or Routed Forces
  keep the Lord on map. Actual Beyond-Service penalties still apply normally.
- **INF2-2:** At Service Limit placement counts from the current Levy box,
  or the next box during Campaign, as specified by the erratum.
- **INF2-4:** Late Disband and all three Muster paths place cylinders and
  Service markers off-right rather than clamping to box 16. Shared placement
  helpers maintain Calendar indexes. An off-right cylinder is not Ready in
  either normal Muster or Allies menus/handlers; printed Emergency Army and
  Commander-to-Arms exceptions remain available. One leftward Service shift
  returns an off-right marker to 16.

Nineteen new regressions cover both phases, Vassal and Tau removal, surviving
Forces, political consequences, phase-relative placement, right-edge overflow,
ordinary/Commander/Allies Muster, save/load, leftward Service shifts, menu
agreement and rejected-action rollback. Thirteen fail on the preceding main;
six preservation cases pass. One older Vassal test now expects temporary
Calendar placement and no Revolt for an empty Lord, correcting its old premise.

Validation: 1,229 tests pass. All six CI self-play scenarios end with zero
anomalies. The configured card-effect, save/load, malformed-input and
state-injection fuzz checks also report zero anomalies. New tests pass Ruff;
changed source adds no Ruff diagnostics relative to the preceding main.

Second-audit progress: **3 of 4 Inferno groups fixed**. INF2-3, voluntary Reset
Arts of War discards, remains open. The original eight groups remain fixed.

## Second audit, batch 2 — INF2-3

Reset now runs compulsory cleanup once, then offers Guelph and Ghibelline
players their 4.9.6 elections before Calendar advance. Both factions may keep
everything or return any owned Holds, This-Lord Capabilities or side-wide
Capabilities to their own decks, independently of Waste or excess limits.
The menu offers repeatable single-card selections and a finish choice, with
optional batch arguments, preserving every subset without an exponential menu.

Holds return unused. Tau Company Capability discard removes Altopascio and
uses the repaired temporary Disband rule if a Lord loses his final Force.
Regular or Routed survivors keep him on the map, and the Held F22 Event does
not invoke Capability cleanup. Mat-clearance cascades return cards once.
Campaign victory stops the remaining selections and Calendar advance; a
submitted but uncompleted Hold discard remains concealed in opponent history.

Save/load retains Reset progress and the active faction. Treachery, unstacking
and expired Events are not processed twice. Eligible Holds remain playable
during Reset and expire before the next Levy. Political decisions block Reset
until resolved, and earlier End Campaign substeps cannot replay after it starts.
Final scoring remains ahead of Repair, Waste and Reset. Existing Reset tests
now explicitly finish both factions' elections; synthetic fixtures mark their
preceding End Campaign steps complete.

Thirty-three regressions cover both factions, all card locations, subsets and
batches, conservation, Tau removal, surviving Forces, Disband, cascades,
immediate victory, secrecy, compulsory cleanup, live Holds, save/load,
malformed selections, actor ownership, political blocking and final scoring.
Thirty fail on the preceding main; three preservation cases pass.

Validation: **1,262 tests passed**. All six configured CI self-play scenarios
ended with zero anomalies. Card-effect checks covered 52 cards and six seeds;
save/load covered all six scenarios and eight seeds. Malformed-input and
state-injection checks also reported zero anomalies. New tests pass Ruff;
changed source adds no Ruff diagnostics relative to the preceding main.

Second-audit progress: **all 4 Inferno groups fixed**. All eight original
Inferno findings remain fixed.

## Third audit, batch 1 — INF3-01 through INF3-04

- **INF3-01 — Sally Losses.** Sally uses the shared Battle aftermath. Fully
  Routed Lords roll for recovery before final-Force removal. Losing Sallying
  Lords Withdraw, and their raid leaves one Siege marker. Actual combat
  removals apply Knights' Quarter, Revolt and Treachery under the same rules
  as field Battle.
- **INF3-02 — Sally Retreat.** Losing besiegers Retreat by a legal Way or
  suffer combat removal if blocked. Retreat uses the actual Way, Shared Carts,
  Spoils, Service shifts and harsh Loss recovery when appropriate. The Siege
  ends when the besiegers depart. The winning faction can allocate Spoils
  among eligible survivors through the existing decision channel.
- **INF3-03 — Trebuchets.** At three or four Siege markers, an Unrouted
  Sallying holder reduces enemy Siegeworks by one. The reduction ends when
  that mat Routes.
- **INF3-04 — Doctors.** Sally uses and clears its one-shot Doctors modifier.
  Restoration follows Loss rolls and precedes final-Force removal, including
  reclaiming recovered Knights from the Captured Knights box.

Thirteen public-action cases cover seeded recovery and removal, Road and
Track capacity, shared Carts, owner allocation, invalid-choice rollback,
blocked Retreat, Trebuchets timing and Doctors restoration. Against preceding
main, 11 fail and two control cases pass. The old direct-call check for Sally's
removal trigger is covered by the public blocked-Retreat test, which verifies
both the Revolt dice and the transfer of Treachery cards into the winner's deck.

**1,275 tests passed.** All six CI smoke scenarios reached victory over 1,194
actions with zero anomalies. The configured card-effect, save/load,
malformed-input and state-injection checks also reported zero anomalies.
New tests pass Ruff, and changed source adds no diagnostics against main.

All four third-audit Inferno groups are fixed. **7 of 23** are fixed across
the five games.
