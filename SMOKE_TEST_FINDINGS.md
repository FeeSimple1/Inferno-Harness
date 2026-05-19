# Smoke Test Findings — Inferno Harness

Per-round log of probe-test discoveries (SMOKE-Inferno-NNN). Each entry
traces a bug from detection through fix, following the pattern
established in Nevsky's `SMOKE_TEST_FINDINGS.md`.

Pattern taxonomy: see `FUTURE_PROJECTS_LESSONS.md` (14 patterns) and
`CROSS_PROJECT_LESSONS.md` (7 audit lenses).

---

## SMOKE-Inferno-001 — Ravage pre-checks: own-territory, already-Ravaged,
## Friendly. Pattern: §1 Legal-moves over-enumeration.

Detected: Phase 3a implementation. Fixed: same commit.
Source marker: `inferno.actions` _h_cmd_ravage and
`inferno.legal_moves` Ravage candidate enumeration.

## SMOKE-Inferno-002 — Plan size gate. Pattern: Pattern 1 state-set-but-
## unreachable (plan size not enforced).

Detected: Phase 3a. Fixed: same commit.
Source marker: `inferno.legal_moves` `_enum_plan`.

## SMOKE-Inferno-003 .. 007 — Phase 3a pre-checks (Tax, Forage, Ravage,
## Supply, Sail). Pattern: §1 defensive enumeration mirroring handler
## checks.

Detected and fixed: Phase 3a.

## SMOKE-Inferno-008 — March way_type validation. Pattern: parallel
## Ways edge case (Pattern 4).

The crossroads pattern in Inferno_Map.txt creates multiple Ways between
the same Locale pair (e.g., Dorpat/Odenpah-style for Vicopisano-Pisa).
`cmd_march` requires the caller's `way_type` to match an actual
adjacency edge.

## SMOKE-Inferno-009 — Avoid Battle Way-of-Approach restriction.

Avoiding Lord may NOT use the same Way the Active Lord used. Enforced
defensively.

## SMOKE-Inferno-010 .. 012 — Phase 3b enumeration pre-checks
## (cmd_march, Avoid Battle, Withdraw).

## SMOKE-Inferno-013 .. 015 — Phase 3c enumeration (Besiege/Bypass,
## Siege/Storm, Sally).

## SMOKE-Inferno-016 .. 017 — Phase 3d enumeration (Bypass-state moves,
## Lieutenants).

## SMOKE-Inferno-018 — F20 Heat & Frost: wrong mechanic. Pattern 7
## card-text fidelity gap.

**Detected (post-v1.1):** Tier-3 rule-diff audit per
CROSS_PROJECT_LESSONS §6.

**Symptom:** The Phase 4 implementation of F20 Heat & Frost added
+1 Provender to each Guelph Mustered Lord. The actual card text reads
"Play before Feed in Summer or Winter for Wastage (4.9.5) now, twice
at Siege or if Moved/Fought. If Summer, remove 1 Ritter." The card
triggers Wastage, not asset gain.

**Root cause:** Card was implemented from event_name alone ("Heat &
Frost") without reading the Text+Tips block.

**Fix:** Implemented full Wastage trigger; 2 cycles for Lords at Siege
or Moved/Fought; Summer additionally removes 1 Ritter from any
Mustered Lord (chosen).

**Regression test:** `TestTier3Fixes.test_smoke_inferno_018_*`.

## SMOKE-Inferno-019 — S20 Heat & Frost: same bug (mirror gap).
## Pattern 7 + Pattern 2 (mirror gap).

**Detected (post-v1.1):** Same Tier-3 sweep.

**Symptom:** Mirror of SMOKE-018. S20's "If Summer, remove 1 unit from
Guido" specifically targets Guido Guerra (not a generic Ritter).

**Fix:** Rewrote S20 to mirror corrected F20 with the Guido-specific
Summer effect.

## SMOKE-Inferno-020 — F22 Manfredi: wrong mechanic.

**Symptom:** Phase 4 F22 implementation said "Choose any Ghibelline
Lord with Ritter shown on his mat: he may not Muster this Levy."
The actual card text reads "Select a Lord with Ritter. Shift his
cylinder or Service 1 Calendar box or remove 3 of his Assets."
Errata: "Ghibelline" deleted — any-side Lord with Ritter qualifies.

**Fix:** Implemented as two-mode card (shift / remove_assets). Validates
target has Ritter; any side OK per Errata.

**Regression tests:** `test_smoke_inferno_020_*` (three tests).

## SMOKE-Inferno-021 — F21 Primo Popolo: wrong mechanic.

**Symptom:** Phase 4 F21 said "Name a Vassal-Seat at Friendly Locale:
+1 Coin to Lord there." The actual card text: "Shift Firenze or
Arezzo cylinder or Service 2 Calendar boxes or add 1 of their
Treachery."

**Fix:** Two-mode implementation (target shift / Treachery add).

## SMOKE-Inferno-022 (post-v1.2 SLOT) — reserved for future findings.

---

## Audit summary

Per CROSS_PROJECT_LESSONS §6 audit lenses run against Inferno-Harness
codebase:

  - Dead-code-surfaces: 0 findings (43 handlers defined, 43 registered).
  - Mirror-gaps: 1 finding (SMOKE-019, F20/S20 mirror).
  - State-set-but-unreachable: 0 active findings post-Phase-3.
  - Rule-cite-but-no-enforce: under continuous audit; no current open
    items.
  - Lifecycle-leak: 0 findings (auto-disband on zero forces wired).

Card-text fidelity (Pattern 7) sweep run post-v1.1: 4 findings (018,
019, 020, 021). The remaining ~15 "flagged manual" cards have Battle/
Storm in-round modifiers reserved for the Phase 5+ in-Battle hooks
(BattleDecisionContext extensions for flanker_target, flanker_absorb,
hit_allocation, and per-card Hold-Event trigger points).
