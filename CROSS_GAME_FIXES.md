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
full mats and loses only markers that no recipient has room to take. Tax and
Sack still need the remaining INF-4 corrections.

Thirty-three new regression cases cover both Way types, grouped and split
Avoids, cart sharing, discards and overflow, Bypass and Encamp, Ambush and
invalid-input rollback, explicit parallel Ways, conceded and non-conceded
Retreat, Withdraw and save/load. Nineteen fail on the previous main revision;
fourteen preservation cases pass. The older Approach predicate test now
checks the legal menu's behavior directly.

Validation: 1,164 tests passed. The six CI self-play scenarios all reached
game end without anomalies. Card-effect, save/load (48 scenario/seed pairs),
malformed-input and state-injection fuzz checks also reported zero anomalies.

Four of eight original Inferno findings are fixed. **INF-4** (remaining Asset
caps), **INF-5** (owner Spoils allocation), **INF-6** (Feed choices) and **IF-5**
(Friars) remain open.
