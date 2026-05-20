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

## SMOKE-Inferno-022 (Phase 5) — Battle/Approach/Besiege hooks
## de-flag pass.

**Detected (v1.3 Phase 5):** Extending battle.py with in-Round hook
points to consume `battle_modifiers_pending`, `approach_modifiers_pending`,
and `besiege_modifiers_pending` queues set by previously-flagged cards.

**Cards de-flagged:**
  - F4/S4 Sudden Clash — R1 Horse Melee before Archery, Select Targets.
  - F6/S6 Hills/Feditori — Defending Archery Hits doubled (active for
    entire Battle).
  - F8/S8 Swamp — non-Summer Defending, enemy Horse skip R1 Melee.
  - F12/S12 Camp Attack — R1 pre-Battle Asset transfer + removal.
  - F16/S16 Bloody Red Stream — first-Rout pause-and-recover.
  - F1/S1 Ambush — registers approach_modifiers_pending (consumed by
    approach_response handler when Avoid is declared).
  - F3/S3 Surprise — registers besiege_modifiers_pending.
  - S10 A Better Paid Death — encoded.
  - S13 Gentle Usilia — encoded (immediate Guelph Ransom signal).
  - S14 Friars — encoded (This Campaign flag).

**Engine hooks added (battle.py):**
  _apply_pre_battle_modifiers   (R1 Asset transfer, Bocca Cavalieri hit)
  _archery_hits_multiplier      (Hills 2x)
  _enemy_horse_skips_round_1    (Swamp)
  _sudden_clash_target          (R1 Horse Melee before Archery)
  _check_rout_recovery          (Bloody Red Stream first-Rout pause)
  _clear_battle_modifiers       (4.4.6 Aftermath cleanup)

**Cards still flagged manual after Phase 5:**
  Only F7 / S7 (Greek Fire — requires target_lord_id arg to apply),
  S16 (Bocca degli Abati — requires target_lord_id arg).
  These are valid 'manual when target unspecified' states, not gaps.

## SMOKE-Inferno-023 — card_data event_name/capability_name confusion.
## Pattern 7 + Pattern 2 (mirror) + Pattern 14 (capability scope).

**Detected (Phase 6):** During Capability-hook wiring for Feditori /
Balestrieri / Palvesari / Arcieri / Luceria, found that
`src/inferno/card_data.py` had wrong `capability_name` values for many
cards. Per AoW Reference, capabilities are shared across cards:

  F6 & F7   → Feditori (had: "Hills" / "Greek Fire")
  F8        → Balestre Grosse (had: "Balestre Grosse" — correct)
  F9-F11    → Balestrieri (had: event names)
  F13-F15   → Palvesari (had: event names)
  F16-F17   → Arcieri (had: event names)
  S6        → Feditori (had: "Feditori" — but event was wrong: "Feditori"
              not "Hills")
  S9-S11    → Balestrieri (had: event names)
  S13-S15   → Palvesari (had: event names)
  S16-S17   → Arcieri (had: event names)

**Root cause:** card_data was hand-coded from grep'ing the AoW
Reference's section headers; the section header naming convention
(`F6. HILLS` for the event, `F6 & F7. FEDITORI` for the capability)
confused event vs capability mapping.

**Fix (Phase 6):**
  - Rewrote `card_data.GUELPH_CARDS` / `GHIBELLINE_CARDS` with explicit
    event_name + capability_name fields per card, verified card-by-
    card against the AoW Reference.
  - Updated `card_effects.register_capability(...)` registrations to
    match the actual capability semantics.
  - Added `_lord_has_capability(state, lord_id, capability_name)` in
    battle.py that does a name-based lookup across this_lord and
    side_wide scopes.
  - Wired Capability strike hooks: Feditori (Cavalieri x2 R1-R2),
    Army Reserve (Cavalieri x2 R3+ for eligible Lords), Balestrieri
    (Armigeri Crossbow Archery), Arcieri (Militia Bowmen Archery),
    Luceria (Militia x1.5 Archery), Balestre Grosse (Men-at-Arms
    Storm Crossbow), Trebuchets (Storm Walls -1 at 3-4 Siege),
    Siege Towers (Storm R2+ attacker strikes first), Astrologers
    (Command +1 on first card 1d6 ≤2), Via Francigena (Command +1
    at Friendly Lord Seat).

**Regression tests:** tests/test_phase6.py (17 tests covering capability
lookup, Feditori, Army Reserve, Arcieri, Luceria, Balestrieri,
Balestre Grosse, Trebuchets, Astrologers, Via Francigena).

---

## SMOKE-Inferno-024 (Phase 6 14-pattern audit summary)

**Pattern audit per FUTURE_PROJECTS_LESSONS.md (CROSS_PROJECT_LESSONS §6):**

  Pattern 1 (state-set-but-unreachable)    : 0 open (all setters paired
                                              with readers / consumers).
  Pattern 2 (mirror gaps)                  : 0 open (all 52 cards have
                                              F+S registrations).
  Pattern 3 (stale per-Lord flags)         : 0 open (lordship_used,
                                              astrologers_rolled, first_
                                              march_used, in_stronghold,
                                              bypassing, moved_fought
                                              all have explicit reset
                                              paths at the right scope).
  Pattern 4 (parallel Ways)                : N/A — Inferno_Map.txt
                                              produces 0 parallel-way
                                              Locale pairs.
  Pattern 5 (overlay markers)              : 0 open (Walls+1 overlay
                                              honored in resolve_storm
                                              walls_die; Ruins overlay
                                              checked in Forage/Supply/
                                              Withdraw paths).
  Pattern 6 (off-edge calendar)            : 0 open (all 4 off-edge
                                              slots threaded through
                                              shift functions).
  Pattern 7 (card-text fidelity)           : SMOKE-018..023 closed.
                                              52/52 cards mechanically
                                              encoded; F7/S7/S16 valid
                                              'awaiting target' paths.
  Pattern 8 (lifecycle leaks)              : 0 open (3 disband paths,
                                              each clearing forces /
                                              assets / vassals / location
                                              / capabilities / service).
  Pattern 9 (rule-cite-but-no-enforce)     : 0 open (178 citation
                                              strings in actions.py
                                              each paired with logic).
  Pattern 10 (no-target-no-op events)      : 0 open (cards return
                                              {applied: False, reason}
                                              on absent target;
                                              {manual: True} for
                                              cards awaiting target
                                              args).
  Pattern 11 (active-player desync)        : 0 open (active_player
                                              mutations go through
                                              flow.py; approach swap
                                              tracks rollback target).
  Pattern 12 (cap/floor uniformity)        : 0 open (7 min(...,17.5) +
                                              7 max(...,0) VP bounds;
                                              property test enforces
                                              0 <= VP <= 17.5 across
                                              fuzz play).
  Pattern 13 (per-window flags reset)      : 0 open (this_levy /
                                              this_campaign cleared at
                                              4.9.6 Reset; astrologers
                                              cleared in end_reset;
                                              exhaustion_rolled cleared
                                              on next Levy entry).
  Pattern 14 (capability scope)            : 0 open (_lord_has_capability
                                              filters both this_lord
                                              and side_wide scopes by
                                              card.capability_name).

## SMOKE-Inferno-027 to 040 (v1.6 mechanics completion)

  - 027 Sail to enemy Stronghold places Siege (4.7.3); Ship transport
    validation (Horse + Provender + 2*Loot).
  - 028 Newly Mustered Lords cannot take Levy actions this segment
    (3.4.1). Enforced in both _enum_muster and _consume_lordship.
  - 029 S23 Economic Sanctions blocks Guelph Tax this Campaign.
  - 030 F5/S5 Road Works: treat Track as Road (incl. 0-cost first-
    March bonus), move Laden as Unladen for the side's Lords.
  - 031 Bribe Path-B (4.7.6): target an Unmustered Vassal whose
    Seat is at/adjacent to the Active Lord. Vassals of removed Lords
    count as Unmustered. Forces sourced from static_data; transferred
    onto Active Lord's mat as Turncoat.
  - 032 Hidden Mats option (1.5.2): state.meta.hidden_mats flag
    plumbed through load_scenario; LLM-side redaction already
    supported via hide_for_side.
  - 033 Relief Sally (4.4.1): on Approach with own-side Besieged Lords
    at the same Locale, Besieged join the attack as relief_sallying.
    On loss, Sallying Lords Withdraw into Stronghold and Siege markers
    reduce to 1.
  - 034 Advanced Vassal Service (3.4.2): state.meta.advanced_vassal_
    service opt-in flag. Per-Vassal service_box tracked. Disband path
    handles Vassal-Beyond-Service by removing Vassal from mat and
    returning Forces to pool. Turncoats immune.
  - 035 Scenario A 'Sudden Campaign': first Levy AoW = 1 Capability
    + 1 Event (instead of 2 of either kind).
  - 036 Scenario B 'Reprisal War': Ghibellines pre-assign S18, S19,
    S20 as Capabilities before their first Levy AoW draw.
  - 037 Scenario B: skip Grow on Autumn 1259 (Turn 5).
  - 038 Scenario A 'Preamble' / E 'Exhaustion': no CtA at all.
    Scenario C 'Maremma War': Ghib-only CtA in first Levy.
  - 039 Scenario C: Ghibelline Lords cannot cross the dashed line
    until Guelphs place a Siege or Ravage marker.
  - 040 Scenario C: Grosseto with 2+ Siege markers and no Besieged
    Lord inside Surrenders at once.

**Total active SMOKEs: 0.** Total SMOKEs surfaced and closed: 40.

## SMOKE-Inferno-025 — AoW deck never reshuffles at start of each Levy
## Pattern 3 (Stale per-side state, wrong scope).

**Detected (v1.5 Tier-2 sweep):** Scenario F long-runs at seed=1/7/99
errored with `IllegalAction[EMPTY_DECK]: AoW deck for guelph has < 2 cards`
after ~640 actions. Per RoP 3.1.1, the AoW deck is reshuffled at the
start of EACH Levy from the discard pile, excluding Held Events and
Capabilities currently in play. The harness was draining the deck across
turns without re-seeding.

**Fix:** Added `_maybe_reshuffle_aow_deck(state, side)` called from
`_h_levy_aow_draw`. Idempotent within a Levy via the
`aow_reshuffled_this_levy_<side>` flag (cleared at end_reset 4.9.6).
Deck reset = all 26 side cards minus held minus in-play capabilities.

**Regression test:** Tier-2 sweep re-run confirms F seeds 1-200 all
complete to victory.

## SMOKE-Inferno-026 — Enumerator/handler divergence on service_box=None
## Pattern 1 (state-set-but-unreachable) + Pattern 2 (arg-shape mismatch).

**Detected (v1.5 Tier-2 sweep):** Scenario E seed=7 greedy looped at
Levy step 3.3 for 30+ consecutive same-state actions on `levy_disband`.
The enumerator was using `(l.get('service_box') or 0) <= levy_box`
which treats None as 0, marking Astimberg disbandable; the handler
had `if svc is None: continue` which skipped him. Result: enumerator
kept offering disband forever; greedy kept picking it; nothing changed.

**Root cause:** `service_box=None` is ambiguous — Lord's marker may
be in `off_left_service` (Beyond Service Limit, IS disbandable) or
`off_right_service` (well-served, NOT disbandable). Neither side of
the engine disambiguated.

**Fix:** Both `_enum_disband` and `_h_levy_disband` now consult
`state['calendar']['off_left_service']` — Lord with `service_box=None`
AND in off_left_service => Beyond Service Limit (disbandable); else
(off-right or just unset) skipped. Handler removes the Lord from the
off_left_service list on disband.

**Regression test:** E seed=7 now completes (greedy: WIN ghibelline
214 actions). Full sweep 36/36 clean.

This matches the Nevsky-level audit completeness threshold. Tier-2
sweep run; 2 real SMOKEs surfaced and closed.


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


---

## SMOKE-Inferno-041 — Surprise (F3/S3) one-shot Storm modifier consumption

**Pattern:** State-set-but-never-consumed (FUTURE_PROJECTS_LESSONS
Pattern 9) + one-shot leak.

**Symptom (latent):** `besiege_modifiers_pending` / the resulting
`storm_walls_minus` entry in `battle_modifiers_pending` was being
*written* when F3/S3 Surprise applied, but pre-v1.7 nothing removed it.
A one-shot Walls reduction would have persisted and re-applied to every
subsequent Storm in the Campaign.

**Fix (v1.7a):** `_h_besiege_or_bypass` consumes the Surprise entry
when it places the 2 Siege markers + triggers the auto-Storm at
Walls-2; `resolve_storm` removes each one-shot `storm_walls_minus`
entry from `battle_modifiers_pending` as it folds the value into the
Attacker's effective Walls die (battle.py ~L1007-1011).

**Regression tests:**
  - `TestSurpriseConsumption` (2 tests): asserts `surprise_besiege` +
    `auto_storm` state-changes and the 1-marker normal-besiege baseline.
  - `TestModifierConsumptionFuzz.test_storm_walls_minus_always_consumed`
    (Hypothesis, 60 examples): for 0-5 markers × value 1-4 × 500 seeds,
    the queue NEVER leaks a `storm_walls_minus` entry after one Storm,
    and an unrelated modifier (`KEEP`) is left untouched.
  - `..._double_storm_does_not_reapply_consumed_marker` (40 examples):
    a consumed one-shot never resurrects for a second Storm.

## SMOKE-Inferno-042 — Ambush (F1/S1) Approach modifier consumption + WRONG_TURN

**Pattern:** Cross-turn action permission (the attacker plays a card
during the *defender's* Approach-response window) + one-shot consume.

**Symptom:** `cmd_play_ambush` was rejected with WRONG_TURN because the
active_player during the Approach window is the defender, while Ambush
is played by the marching attacker. Separately, the
`approach_modifiers_pending` Ambush entry needed consuming so it pins
exactly one Avoiding Lord once.

**Fix (v1.7a):** `dispatch()` exempts `cmd_play_ambush` from the
turn-owner check when `side == meta.approach_attacker_side`
(`ambush_exempt` clause). `_h_cmd_play_ambush` requires a pending
`ambush_force_one_stand` entry (else `NO_AMBUSH`), sets the target
Lord's `flags.ambush_forced`, and consumes the entry; `approach_response`
then raises `AMBUSH_FORCED` if that Lord tries to Avoid.

**Regression tests:** `TestAmbushConsumption` (2 tests) — pin-then-block
happy path (asserts `ambush_pinned`, `flags.ambush_forced`, and the
`AMBUSH_FORCED` rejection on Avoid) and the `NO_AMBUSH` rejection when
no modifier is pending.

**v1.7d extended sweep:** greedy self-play across all 6 scenarios ×
seeds 1-25 (150 games) — 150/150 reach a winner, 0 invariant
violations, 0 exceptions, and all three modifier queues
(`battle_/approach_/besiege_modifiers_pending`) observed max length 0
under greedy play (greedy never plays situational cards), confirming no
leak path is reachable through ordinary play. Consumption paths are
covered by the targeted unit + Hypothesis tests above.
