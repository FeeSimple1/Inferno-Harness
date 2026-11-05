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

Six of eight original Inferno findings are fixed. **INF-6** (Feed choices)
and **IF-5** (Friars) remain open.
