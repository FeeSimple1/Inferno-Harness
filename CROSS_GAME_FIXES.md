# Cross-game audit repairs

The November 4, 2026 cross-game audit identified eight Inferno defect groups.
This repair batch addresses **IF-4 — hidden troop totals**.

With Hidden Mats enabled, player snapshots use a constant hidden marker for
opposing Forces. The old marker contained the exact sum of the hidden army.
Army size no longer changes the player snapshot or briefing. The owner still
sees their own Forces, open mats still show precise Forces, and combat reveals
only participating mats for the duration of the combat visibility scope.

Regression tests cover both factions, saved and explicit Hidden Mats options,
unchanged source states, repeated filtering, briefings, and combat reveal and
re-hide behavior. Existing interface tests now require the constant marker.

One of eight Inferno findings is fixed; the other seven remain open.
