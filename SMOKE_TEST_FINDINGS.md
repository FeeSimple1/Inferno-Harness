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


---

## SMOKE-Inferno-043 — CLI `do` verb was a Phase-0 stub (no dispatch)

**Pattern:** Rule/feature cited-but-not-enforced at the boundary
(FUTURE_PROJECTS_LESSONS Pattern: surface-defined-but-dead).

**Symptom:** `inferno do <state> <action_json>` printed
`PHASE_NOT_IMPLEMENTED` and never called `dispatch()`. The engine fully
supports action execution (used by the LLM harness, example client, and
all tests) but the human-facing CLI verb did nothing — state never
changed on disk. Stale "Phase 0 stub" comments on `legal-moves`/`do`
masked this.

**Fix (v1.8):** `_cmd_do` now parses the action JSON (exit 2 on malformed
input or missing "action" key), calls `dispatch()`, prints the result,
and persists state to `--out` or in-place (mirrors `_cmd_play_event`).
IllegalAction → exit 1 with `IllegalAction[CODE]: msg`. Stale comments
corrected.

**Regression test:** `TestCliDo` (3 tests) — subprocess-drives the CLI:
a real `levy_aow_draw` mutates and persists state (history grows); bad
JSON exits 2; an illegal action does not crash.

## SMOKE-Inferno-044 — S7 Greek Fire (Ghibelline) was an unencoded stub

**Pattern:** Mirror-gap (the Guelph F7 was fully encoded; its Ghibelline
mirror S7 returned a bare `_manual`).

**Fix (v1.8):** Extracted the F7 mechanic into `_greek_fire_apply(state,
side, args)` and pointed both `F7_event` and `S7_event` at it. On a
Besieging Enemy Lord: reduce his Siege to 1 marker, remove 1 named unit,
discard 1 of his This Lord Capabilities. Validates the target is an
actual Enemy Lord; returns `_manual` only when no `enemy_lord_id` given
(the choose-target prompt path, by design).

**Regression test:** `TestS7GreekFire` (3 tests) — applies (siege->1,
unit removed, capability discarded), manual without target, rejects a
friendly (non-enemy) target.

## SMOKE-Inferno-045 — S18 Cortona and S19 Brigands were unencoded stubs

**Pattern:** State-cited-but-no-effect (both Events returned a bare
`_manual` with no mechanical effect at all).

**S18 CORTONA (AoW Reference)** — three uses now encoded:
  - `treachery_free` (default): registers a one-shot
    `cortona_treachery_free` entry in `treachery_modifiers_pending`,
    consumed by `cmd_treachery_revolt` / `cmd_treachery_bribe` when the
    target is/at Cortona — the Treachery succeeds for 0 Coin with no roll.
    The modifier is consumed only on success (peek-then-commit, so a
    failed-validation Revolt does NOT leak the modifier).
  - `add_treachery`: if Cortona has Ghibelline Allegiance (not Ruins),
    move one set-aside Ghibelline Treachery card to the Ghibelline Command
    deck.
  - `revolt_roll`: if Cortona Ghibelline, roll the Revolt Table (1 purple
    + 1 gold, recorded for audit/RNG fidelity) and flip an eligible Enemy
    Stronghold per 1.4.1/1.4.2 (Enemy, not Ruins/Outpost, no Enemy Lord
    at/adjacent, within 1 Locale of a Ghibelline cylinder/marker). NOTE:
    the physical Revolt-Table chart (die->named Locale) is not in the
    reference set; eligibility is the faithful gate, consistent with how
    the harness already abstracts all other Revolt-Table rolls
    (disband/sack add Treachery without resolving the named-Locale chart).

**S19 BRIGANDS (AoW Reference)** — when an Enemy (Guelph) Lord that just
Marched is within 2 Locales of Giordano or Astimberg, the receiver takes
one bundle from that Enemy: 2 Coin, or 2 Loot, or 4 Carts + 4 Provender.
Validates target is Guelph, receiver is Mustered Giordano/Astimberg, and
range <= 2 (BFS via `_locales_within`). Transfers are capped at what the
target holds.

**Regression tests:** `TestS18Cortona` (4) + `TestS18RevoltConsumption`
(1, 0-Coin Cortona Revolt via dispatch with modifier consumed) +
`TestS19Brigands` (3, in-range coin transfer, out-of-range rejection,
carts+prov bundle). 369 tests total; greedy self-play 90/90 reach a
winner with 0 invariant violations after the treachery-handler changes.


---

## SMOKE-Inferno-046 — Revolt Table was abstracted to eligibility (now table-driven)

**Pattern:** Box-only data fabricated as a stand-in (the v1.8 audit's
single true reasoning gap). RoP 1.4.2 gives the Revolt procedure but the
die-pair -> named-Locale grid is printed on the board, not in the rules
text. Pre-v1.9 every automatic Revolt roll (Disband 3.3.1, Surrender
4.5.1, Sack 4.5.2, Languish 4.9.2) rolled a die and added a Treachery
card but never flipped the table-named Locale; S18 revolt_roll used an
eligibility gate in place of the roll.

**Fix (v1.9):** The user supplied the full Revolt Tables; encoded in
`src/inferno/revolt.py` as REVOLT_TABLE_VS_GUELPH / _VS_GHIBELLINE
(reference spellings; validated — all 56 distinct named cells join to
LOCALES, both tables 36 cells, Siena absent, 10 Submission cells).
`resolve_revolt()` implements 1.4.2 Rebellion + Submission, 1.4.4 flip,
and Exiles; `trigger_revolts()`/`drain_revolts()` pre-roll dice
(replay-deterministic), resolve in order, and PARK any roll needing a
player choice as a pending decision. All Revolt triggers and S18 now
call it.

**Q-002 (RULES_DECISIONS.md):** the crossed-out cells are SUBMISSION,
not no-revolt; all player choices (Submission target, Rebellion
already-Friendly fallback, Exiles slides) are surfaced as decisions
(consumer supplies the choice), never auto-selected — No-Agent
constraint.

**Deadlock guard (CROSS_PROJECT_LESSONS §8.5):** the enumerator surfaces
ONLY the pending `cmd_resolve_revolt` / `cmd_resolve_exiles` moves until
the decision clears, and `dispatch()` exempts those resolutions from the
active-player turn check (the benefitting/losing side may not be active).

**Tests:** `test_v19_features.py` (16) — table integrity + Playbook
golden (Chiusi @ gold6/purple5 vs-Guelph), Rebellion (success / no
presence / ineligible / Friendly-fallback), Submission (choice / illegal
/ none), Exiles surfaced+applied, full enumerate->dispatch resolution,
and a real `trigger_revolts` Submission park-then-resolve via a
controlled RNG. Self-play sweep: 150/150 scenarios reach a winner, 0
invariant violations, 0 stalls.

**Reference-data flags logged (no guessing):** the supplied reference's
summary said "12 [NO REVOLT] cells" — the grid has 10 (corrected in the
repo reference); and the [NO REVOLT]->SUBMISSION relabel is recorded as
Q-002.

---

## SMOKE-Inferno-047 — S19 Brigands `carts_prov` bundle used asset key "Carts"

**Pattern:** §1/key-mismatch — a value written under a key the rest of the
game never reads (silent no-op against real state).

**Detected:** v2.0 batch audit (BRIEF "Rules Accuracy Trumps Simplification").
The S19 BRIGANDS (AoW) `carts_prov` transfer bundle in
`card_effects.py::S19_event` was `{"Carts": 4, "Provender": 4}`, but the
canonical Cart asset key everywhere else (static_data Lord assets, battle.py,
actions.py transport) is the SINGULAR `"Cart"`. A real Lord holds `Cart`, so
the bundle's `min(4, target.assets["Carts"]=0)` moved zero Carts — only the
Provender ever transferred.

**Fix (v2.0):** plan dict now uses `"Cart"`. Regression: the existing
`test_v18_features.py::TestS19Brigands::test_carts_prov_bundle` was rewritten
to seed the canonical `"Cart"` key and assert the Carts actually leave the
target and arrive at the receiver.

## SMOKE-Inferno-048 — Concede+Retreat Spoils Unladen carry was prov − Carts

**Pattern:** Pattern-class "off-by-a-rule-constant" + an explicit hedge-word
("conservative") flag that the BRIEF audit forbids.

**Detected:** v2.0 batch audit. `battle.py::transfer_spoils` Concede+Retreat
branch transferred Provender beyond `prov - carts` and the comment admitted
"Unladen carry on Road = up to 2*Carts; conservative". Battle&Storm 11.3
(4.4.3) gives away Provender BEYOND what the loser could carry Unladen, and
the Unladen carry is up to 2× Provender per Cart on Road (Commands 4.3.2 — the
same 2×Carts limit `actions.py` already enforces for Laden movement). So the
loser keeps `2*carts`, gives `prov - 2*carts`.

**Fix (v2.0):** `excess_prov = max(0, prov - 2 * carts)`, hedge comment
removed. Regression updated in
`test_phase3d.py::TestSpoilsTransfer::test_conceded_retreat_keeps_carroccio_loses_only_loot_and_excess_prov`.

## SMOKE-Inferno-049 — Player Treachery-Revolt (4.7.5) skipped the 1.4.4 Exiles step

**Pattern:** §2 rules-predicate re-derived inline instead of reusing the one
definition — the two copies drifted.

**Detected:** v2.0 batch audit. `actions.py::_h_cmd_treachery_revolt` flipped
the target's Allegiance with hand-rolled marker/VP code and never produced the
1.4.4 Exiles requirement, whereas every automatic revolt (via
`revolt.apply_allegiance_switch` → `_finish_resolved`) surfaces it. A
successful player Treachery-Revolt therefore let the losing side escape the
Exiles slides.

**Fix (v2.0):** the success path now calls
`revolt.apply_allegiance_switch(state, target, side)` and, when
`exiles_count > 0`, appends the same `pending_exiles` entry shape as automatic
revolts (resolved by the existing `cmd_resolve_exiles`, which the enumerator
surfaces and `dispatch` exempts from the turn check). This also correctly
handles the "revert to printed-Friendly" marker case. Regression:
`test_v20_features.py::TestTreacheryRevoltExiles`.

## SMOKE-Inferno-050 — Combat removal (4.4.5) did not roll on the Revolt table

**Pattern:** §2 missing trigger — the predicate "this removal triggers Revolt &
Treachery" was wired for Disband/Surrender/Sack/Languish but not for combat
removal, and was duplicated across handlers.

**Detected:** v2.0 batch audit. Rules Reference Revolt Triggers + Battle&Storm
Sec.13 list a Lord "Removed by combat" (once for a regular Lord, 3× for a
Podesta) as a Revolt-table + Treachery trigger, as if Disbanding Beyond
Service (3.3.1). The Battle (`_apply_post_battle`) and Sally (`_h_cmd_sally`)
removal loops only `_disband_beyond_service_limit`'d the Lord; the Storm Sack
(`_apply_sack`) rolled the SEPARATE Sack revolts but not the per-Lord
combat-removal ones.

**Fix (v2.0):** new shared `actions._trigger_combat_removal_revolts()` (1×
regular / 3× Podesta, Comune Lords exempt per 3.3.1) — defined once and called
from all three combat-removal sites (Storm runs it BEFORE the separate Sack
rolls, per Sec.13 ordering). Regression:
`test_v20_features.py::TestCombatRemovalRevolt` (roll/treachery counts,
Podesta 3×, Comune exemption, all-three-paths wiring).

---

## SMOKE-Inferno-051 — Forage was blocked by ANY Siege marker (4.7.1)

**Pattern:** §1 over-strict gate + Phase-3a simplification hedge.

**Detected:** v2.1 batch audit. `_h_cmd_forage` (and the enumerator pre-check)
blocked Forage whenever `loc.siege` was truthy, with the comment "Phase 3a
simplified". 4.7.1 only forbids Forage when the Lord is Besieged by Enemy Lords
numbering EQUAL TO OR MORE THAN the Stronghold's Size; fewer besiegers do not
block.

**Fix (v2.1):** new `static_data.forage_besieged_block(state, loc, side)`
predicate (besieging Enemy Lords not in_stronghold vs Stronghold Size), defined
ONCE and called by both the handler and the legal-moves enumerator.
Regression: `test_v21_features.py::TestForageSiegeThreshold`.

## SMOKE-Inferno-052 — "Friendly Locale" checks at Loot Pay (3.2.2) and F23

**Pattern:** §2 rules-predicate re-derived inline / omitted, plus a missing
requirement.

**Detected:** v2.1 batch audit. Loot Pay (3.2.2) required a Friendly Locale per
the rules but only checked Siege — the Friendly test was a comment, never
enforced. Via Francigena (F23) used an inline `printed==side or own markers`
test that wrongly treated a printed-Friendly Locale under ENEMY Allegiance
markers as Friendly.

**Fix (v2.1):** both routed through the canonical `_is_friendly_locale`
predicate (current Allegiance markers override printed Allegiance, 1.3); its
docstring de-hedged. Loot Pay now raises LOOT_NOT_FRIENDLY off-Friendly.
Regression: `test_v21_features.py::TestFriendlyLocaleChecks`.

## SMOKE-Inferno-053 — Captured Carroccio (+2 VP) dropped at end-game tally (5.0)

**Pattern:** write/read key mismatch + dead/confusing code.

**Detected:** v2.1 batch audit. `_compute_final_vp` recomputes end-game VP from
scratch and read Carroccio captures from `state["captured_carroccio_for_side"]`,
but NOTHING ever wrote that key — so every captured Carroccio's +2 VP was lost
when the final recompute overwrote `state.vp`. The function also contained a
discarded first-pass build ("re-do clean").

**Fix (v2.1):** Battle Spoils (`battle.transfer_spoils`) and Storm-Sack
(`_apply_sack`) now persist each capture into `captured_carroccio_for_side`;
`_compute_final_vp` rewritten cleanly (Allegiance +1, Ruins +1/2, Carroccio +2,
Ravaged +1/2 bucketed for the Scenario-E doubling exclusion). Ravaged/Ruins
tally verified correct per 5.0. Regression:
`test_v21_features.py::TestEndGameVpTally`.

## SMOKE-Inferno-054 — F17 Foreign Help treachery->cylinder branch was a stub

**Pattern:** unimplemented secondary card branch (returned applied=False).

**Detected:** v2.1 batch audit. F17's second option ("set aside 1 Treachery
from the Guelph deck to shift Guido's/Orvieto's cylinders left to current
Levy") was a "Phase 4 simplified" stub.

**Fix (v2.1):** implemented `mode="treachery_cylinder"`: validates an eligible
cylinder (Guido/Orvieto on the Calendar right of the Levy box) and a Guelph
Treachery card in the Command deck, sets that card aside again, and moves the
chosen cylinder(s) into the Levy box. Player choices (mode, targets, which
card) are consumer-supplied (No-Agent); missing/ambiguous -> `_manual` prompt.
Regression: `test_v21_features.py::TestF17ForeignHelp`.

## SMOKE-Inferno-055 — Avoid-Battle could retreat along the approach Way (4.3.4)

**Pattern:** §6 state-not-tracked — the restriction existed but the data it
needed (Active Lord's from-Locale) was never recorded, so it was a no-op
(completes the long-open SMOKE-Inferno-009).

**Detected:** v2.1 batch audit. The Avoid handler and enumerator both had a
`pass`/no-op where 4.3.4 forbids an Avoiding Lord from retreating back along the
Way the Active Lord just used; the code comment admitted "we don't track the
active Lord's from".

**Fix (v2.1):** the March handler now records `approached_from` on the
approach_response pending; new shared `static_data.avoid_along_approach_way()`
predicate blocks an Avoid to that origin when the sole connecting Way is the
approach Way. Enforced in both the handler (raises AVOID_ALONG_APPROACH_WAY) and
the enumerator. Regression: `test_v21_features.py::TestAvoidApproachWay`.

---

## SMOKE-Inferno-056 — Sally reused plain Battle instead of the Storm-style Array (4.5.3 / 2.3)

**Pattern:** rules-procedure under-modeled — a distinct combat mode collapsed
onto a more generic one, dropping its specific Array and Walls.

**Detected:** v2.2 work. `_h_cmd_sally` resolved a Sally with `resolve_battle`
(commented "Phase 3c approximation"), so it used the full Battle Array (up to 3
Front + auto-Reposition) and gave NEITHER side Walls. Battle&Storm 2.3 requires:
each side starts with 1 Front Lord (Attacker = Sallying Active Lord, Defender =
a Besieger), the rest in Reserve; each Round after the first each side MAY add
ONE Reserve Lord to Front up to the Stronghold Size; if all of a side's Front
Lords Rout a Reserve Lord MUST promote; the Besiegers defend behind SIEGEWORKS
(= # Siege markers) as Walls; and the Sallying side gets NO Walls and NO
Garrison. Sally otherwise uses Battle rules (the full 6-step initiative — 2.3
lists only Array/Reposition differences, not Storm's melee collapse).

**Fix (v2.2):** new `battle.resolve_sally` (Battle 6-step Strike + Storm-style
1-Front/Reserve Array + reserve-add-up-to-Size + forced promotion). `_resolve_step`
gained an optional `walls_by_side` parameter so the Besieging (defender) side
can defend behind Siegeworks-as-Walls while the Sallying side has none (plain
Battle passes None — unchanged). `_h_cmd_sally` now calls `resolve_sally`; its
existing aftermath (Besiegers lose -> Siege ends; Sally fails -> Raid to 1 Siege
marker + back inside; 4.4.5 combat-removal Revolt/Treachery) is unchanged.
Regression: `test_v22_features.py::TestSallyArray`.

---

## SMOKE-Inferno-057 — FPD optional Pay sub-step (4.8.2) was auto-skipped

**Pattern:** No-Agent violation — a player choice silently auto-decided (here,
always "decline to Pay"), plus a "skip for now / Phase 3a" hedge.

**Detected:** v2.3 work. `_run_fpd` ran Feed -> Disband and skipped the Pay
sub-step entirely ("Pay step is auto-skipped ... skip for now"). SoP 4.8.2
gives Guelphs then Ghibellines an OPTIONAL Pay (per Levy 3.2) BETWEEN Feed and
Disband, which can save a Lord from Disband by shifting its Service marker
right. Auto-skipping denied that legal choice.

**Fix (v2.3):** after Feed, when either side has a legal Pay, `_run_fpd` parks a
`pending_fpd` Pay decision and DEFERS Disband; the enumerator surfaces ONLY the
FPD-Pay moves (deadlock guard) for the active segment side (Guelph then Ghib,
`cmd_fpd_pay` / `cmd_fpd_pay_done`, pay_done listed first so a greedy consumer
declines cleanly); `dispatch` exempts them from the turn check. Disband + remove
Moved/Fought (`_fpd_run_disband`) runs only after both sides finish Pay (or
immediately when neither side can Pay — unchanged behaviour). The Pay mechanic
was factored into a shared `_apply_pay_action` used by both Levy Pay and FPD
Pay. Self-play sweep: 240 games, 0 stalls across ~6k FPD-parked steps.
Regression: `test_v23_features.py::TestFpdPaySubStep`.

**Scope note:** the enumerator surfaces the self-Coin Pay for each eligible Lord
plus `pay_done`; the handler still accepts any valid 3.2 Pay the consumer
supplies (cross-Lord, Loot, multi-box). Beyond-Service-Limit Disband Revolt/
Treachery wiring at FPD is a separate pre-existing item (unchanged here).

---

## SMOKE-Inferno-058 — FPD Beyond-Service Disband skipped its Revolt & Treachery

**Pattern:** §2 missing trigger + misleading docstring — the predicate "this
Disband triggers Revolt & Treachery (3.3.1)" was wired for Levy Disband and (as
of SMOKE-050) combat removal, but NOT for the FPD (4.8.2) Beyond-Service Disband,
even though `_fpd_run_disband`'s docstring claimed it applied.

**Detected:** v2.4 (flagged at end of v2.3). `_fpd_run_disband` called
`_disband_beyond_service_limit` directly and never rolled Revolt or added
Treachery. SoP 4.8.2 Errata: "Beyond-Service-Limit Revolt/Treachery DOES apply."
(At-Service-Limit Disband correctly adds none.)

**Fix (v2.4):** the v2.0 combat-removal helper was generalised and renamed
`_trigger_disband_revolt_and_treachery` — the Rules Reference groups "Disbanded
Beyond Service OR Removed by combat" as one 3.3.1 trigger (1x regular / 3x
Podesta, Comune exempt). It is now called by `_fpd_run_disband` for the
Beyond-Service (and off-left-Service) Disbands, with a state-seeded RNG that
updates `rng_advance` (replay-deterministic; this path has no handler rng). The
three combat call sites (Battle/Storm/Sally) were updated to the new name (return
keys neutralised to `revolt_rolls` / `treachery_added`). At-Service-Limit Disband
still triggers nothing. Self-play: 240 games, 0 stalls. Regression:
`test_v23_features.py::TestFpdDisbandRevolt`.

---

## SMOKE-Inferno-059 — Call to Arms (3.5) was unreachable through the enumerator

**Pattern:** §"enumerator/handler round-trip" — handlers exist but the move
enumerator never surfaces them, so the feature is dead via the intended
`enumerate_legal -> dispatch` interface (the "green sweep ≠ no bugs" trap: the
CtA handlers had tests that dispatched them DIRECTLY, masking the gap).

**Detected:** v2.5 (during a completeness review before smoke testing).
`legal_moves._enum_cta` returned ONLY the skip move (with a stale "Phase 2 stub"
description) even though the full Call to Arms is implemented
(`levy_cta_declare` + the four sub-steps `cta_gather_march` / `cta_commander_arms`
/ `cta_comune_setup` / `cta_allies`, all registered and tested). A consumer
playing through the enumerator could only ever DECLINE Call to Arms.

**Fix (v2.5):** `_enum_cta` now surfaces the real moves. When CtA is not active,
the current side may DECLARE (only if `_cta_trigger_met`) or DECLINE. Once active,
the side currently in CtA gets that sub-step's concrete moves plus a skip:
gather (each Lord's Ways that end strictly closer to the Leading City and pass
the destination-legality predicate), commander_arms (modes valid for the
Commander's status), comune setup, and allies (auto-/extra-Muster targets). The
Gather destination check (no Unbesieged Enemy Lord; no un-Ruined Enemy
Stronghold) was factored into a shared `actions._cta_gather_dest_legal` used by
BOTH the handler and the enumerator, so the round-trip can't drift.

**Verification:** round-trip sweep over every scenario/seed — 30,086 enumerated
moves dispatched with 0 illegal emissions across 160 CtA-active steps; greedy
self-play exercised 41 real CtA declarations with no stalls. Regression:
`test_v25_features.py::TestCtAEnumeration` (incl. a per-move round-trip and a
full enumerator-driven CtA walkthrough).

---

## SMOKE-Inferno-060 — Enumerator over-enumeration (8 round-trip gaps)

**Pattern:** §"enumerator/handler round-trip" — the move enumerator offered moves
that dispatch then correctly rejected (the engine enforced the rule; the
enumerator was over-permissive). Found by a randomized self-play smoke test
(900 games / 271k steps) that flagged every enumerated move dispatch refused.

**Detected & fixed (v2.6):** each enumerator pre-check tightened to mirror its
handler:
  - cmd_march EXCESS_PROVENDER — a Lord (or its auto-paired Lieutenant+Lower-Lord
    group, 4.1.3) with Provender > 2*Carts may not move (4.3.2); the group sum
    is now checked.
  - cmd_sail INSUFFICIENT_SHIPS — Sail needs Ships >= Horse + Provender + 2*Loot
    (4.7.3).
  - besiege_or_bypass / cmd_tax — require >= 1 action (were ungated).
  - cmd_supply — supplier may not be Besieged (was unchecked).
  - cmd_encamp NOT_AT_BYPASS — Lord must be AT its Bypass marker.
  - cmd_sortie NO_BYPASSERS — a Bypassing Enemy Lord must be present (not just a
    Bypass marker).
  - end_ransom INSUFFICIENT_COIN — only offer PAY if a Mustered Lord can afford
    the Ransom; always offer Languish.
  - levy_pay LOOT_NOT_FRIENDLY — Loot Pay requires a Friendly Locale (3.2.2).
  - cmd_tax TAX_BLOCKED_S23 — no Guelph Tax while S23 Economic Sanctions is in
    play.

**Verification:** randomized smoke sweep across all scenarios/seeds — 900 games,
271,225 steps, 784 winners, 0 stalls, **0 over-enumerations, 0 invariant
violations**. Regression: `test_v26_features.py::TestEnumeratorRoundTrip`.

## SMOKE-Inferno-061 — End Card was illegal with 0 actions remaining

**Pattern:** handler over-gate — `_h_cmd_end_card` used `_require_active_lord`,
which raises NO_ACTIONS_LEFT at 0 actions, so a state with an active Lord and 0
actions could not be closed out via cmd_end_card (the enumerator offered it).

**Fix (v2.6):** ending a card is always legal for the active player (stop early
OR close out a spent card); `_h_cmd_end_card` now validates the active Lord/side
WITHOUT gating on actions_remaining. Regression in `test_v26_features.py`.

---

## SMOKE-Inferno-062..066 — Persistent AoW Capabilities (bottom-half) implemented

**Pattern:** §"missing implementation" — all 52 AoW Event halves were wired, but
9 distinct persistent Capability effects were no-ops (their `register_capability`
hooks were empty/unconsumed). The capability *names* are documented in the
reference's GUELPH/GHIBELLINE CAPABILITIES sections; consumption is by name via
`battle._lord_has_capability`.

**Audit:** 24 distinct capability_names; 15 were already consumed (Arcieri, Army
Reserve, Astrologers, Balestre Grosse, Balestrieri, Distringitores, Feditori,
Luceria, Palvesari, Siege Towers, Stores & Well Water, Taglia, Trebuchets, Via
Francigena, Manfredi-via-VP). The other 9 were implemented in v2.7:

  - SMOKE-062 Ravage cluster — F19/S19 GUALDANA (Ravage gains double when the
    Lord has a Horse unit) plus the base Berrovieri doubling; F20/S20 MASNADIERI
    (0-action Ravage taking no Loot); F18/S18 LA CAVALLATA (new entire-card
    action: 1 Provender Shared, Ravage adjacent); F26/S26 COSTRUTTORI (new
    entire-card action: 1 Coin + 3 Provender, remove Ruins). Shared
    `_apply_ravage_gains` / `_share_available` / `_pay_from_locale` helpers.
  - SMOKE-063 Siege — F2/S2 GUASTATORI (Siege adds 2 markers; besieged Pass
    clears Enemy Siege and Bypasses them) and F5/S5 WAR ENGINEERS (Siege adds a
    marker at any Stronghold Size; besieged entire-card reduces Enemy Siege to 1).
  - SMOKE-064 F25/S25 REINFORCED WALLS — Tax variant places a Walls +1 marker
    (no Coin); Seat must not be Ruins/Outpost/already-marked; max 4 per side;
    blocked for Guelphs by S23.
  - SMOKE-065 S21 SOVRINTENDENTE — Ghibelline-held Castle Garrisons swap their
    Militia for a Crossbow Armigeri (`_garrison_for` is now state/side-aware).
  - SMOKE-066 F22 TAU COMPANY — Firenze/Lucca Lordship +1 (wired
    `_capability_bonus_lordship` into `_consume_lordship`) and free (0-Lordship)
    Altopascio Muster.

All new actions/modes are surfaced by the command-phase enumerator only when the
Lord holds the Capability and preconditions are met.

## SMOKE-Inferno-067 — Round-trip gaps surfaced by the wider capability sweep

**Pattern:** §enumerator/handler round-trip (continuation of SMOKE-060), exposed
by a larger randomized sweep once Capabilities were exercised.

**Fixed (v2.7):** the new capability actions gained the same `actions_remaining`
gate their handlers enforce; the March cost estimate in the enumerator now
mirrors the handler exactly (group-summed Carts/Provender/Loot + Road-Works);
cmd_sail no longer offers a Port holding an Unbesieged Enemy Lord; cmd_sally now
requires a Besieging Enemy Lord present.

**Verification:** randomized smoke sweep — 990 games, 298,939 steps, 857 winners,
0 over-enumerations, 0 stalls, 0 invariant violations (capability actions
exercised hundreds of times). Regression: `test_v27_features.py`.

---

## Smoke-test campaign (v2.8) — 10 rounds, 3 bugs found & fixed

Ten diverse probe rounds (~1.5M dispatched steps total): R1 large randomized
self-play; R2 exhaustive enumerator round-trip; R3 replay determinism + strict
JSON portability; R4 combat-heavy; R5 all-capabilities injection; R6 VP/scoring
conservation; R7 state-schema validation every step; R8 multi-turn
calendar/season integrity; R9 biased single-subsystem policies; R10 board
placement consistency.

## SMOKE-Inferno-068 — empty/short AoW deck dead-locked the Levy

**Found:** R5 (all 52 Capabilities injected -> reshuffled AoW deck empty).
`_h_levy_aow_draw` raised EMPTY_DECK when the deck had < 2 cards, but the
enumerator still offered `levy_aow_draw`, so the Levy could not advance
(reachable in long games per the SMOKE-025 note). **Fix:** 3.1 draws UP TO 2
cards — draw `min(2, len(deck))` (0-2) and proceed.

## SMOKE-Inferno-069 — running VP not initialised from the starting board

**Found:** R6 (end-game VP recompute jumped from a running 0 to 8+). Every
scenario set `vp = {0, 0}` while the starting board markers were worth real VP
(e.g. Scenario C: 14 vs 5), so mid-game VP-dependent logic (Call to Arms
"VP lag >= 4") was wrong from Turn 1. **Fix:** `load_scenario` now initialises
the running VP track from the board's marker tally
(`_init_vp_from_markers`: Allegiance +1, Ruins/Ravaged +1/2; NOT the end-game
Scenario-E/C modifiers, which belong to the 5.1 final recompute).

## SMOKE-Inferno-070 — calendar cylinder/service lists drifted from Lord boxes

**Found:** R8 (a Lord listed in box N's `services` while its `service_box` was a
different box or None). A whole CLASS of bug: several sites changed a Lord's
`service_box`/`calendar_box` without updating the calendar's `services`/
`cylinders` lists — `_disband_at_service_limit` (called by CtA Commander-to-Arms
with a marker NOT at the Levy box) and, most pervasively, `revolt.apply_exiles`
(the 1.4.4 slide changed only the `*_box` field). **Fix:** centralised
`_place_service` / `_place_cylinder` helpers (remove from EVERY box first, then
place) now used by `_shift_service_right`, Muster, both Disband paths, the FPD
unfed shift, and both CtA musters; `apply_exiles` got an equivalent
`_slide_marker`. **Verification (post-fix sweep):** 135,556 steps, 0 calendar
violations; 0 placement violations over 117,683 steps (R10).

Regression: `test_v28_features.py` (8 tests). Full suite 469 pass. Final
all-checks sweep across the 10 rounds: 0 crashes, 0 over-enumerations, 0 stalls,
0 invariant/schema/calendar/placement violations.

---

## Smoke-test campaign II (v2.9) — 30 rounds, 2 bug classes found & fixed

Twenty new probe lenses (R11-R30) on top of the v2.8 ten: R11 failed-dispatch
atomicity; R12 AoW card conservation; R13 deck dup integrity; R14 enumerate
no-mutation; R15 marker integrity; R16 asset bounds; R17 mid-game JSON save/load
continuation equivalence; R18 hidden_mats mode; R19 advanced_vassal_service mode;
R20 same-seed reproducibility; R21 longest-game accumulation; R22 pending-decision
exclusivity; R23 capability combos; R24 Storm/Sack post-conditions; R25 Bribe;
R26 Avoid/Withdraw/Approach; R27 Lord status-transition legality; R28 plan-size
caps; R29 unit bounds; R30 final-scoring/tie. Most came back clean on the first
pass; two bug classes surfaced.

## SMOKE-Inferno-071 — AoW card conservation (dup & loss)

**Found:** R12 (per-side 26-card multiset drifted). Four distinct leaks:
  - the Levy reshuffle (`_maybe_reshuffle_aow_deck`) excluded Held + side-wide
    Capabilities but NOT Capabilities on Lord mats (`lord["capabilities"]`), so a
    this-Lord Capability duplicated back into the draw deck (could be drawn and
    deployed a second time — a real double-effect risk);
  - `_disband_at_service_limit` cleared `lord["capabilities"]` WITHOUT returning
    the cards to the AoW deck (lost on every at-limit / CtA-remuster Disband);
  - the initial deck (`_init_decks`) included Capabilities already in play at
    setup (Scenario C Manfredi / E Taglia) -> duplicate until first reshuffle;
  - `end_reset` dropped `active_events` wholesale instead of returning their
    cards to the discard.

**Fix (v2.9):** reshuffle now also excludes Lord-mat Capabilities; disband-at
returns Capabilities to the deck; `_init_decks` excludes `capabilities_in_play`;
`end_reset` returns expiring event cards to the discard. **Verification:**
card conservation held over 135,116 steps (was failing within ~50).

## SMOKE-Inferno-072 — Treachery Revolt/Bribe unreachable via the enumerator

**Found:** R25 (Bribe exercised 0 times). Revealing a Treachery card called
`_finish_card` ("Phase 3a does not implement Revolt or Bribe") and auto-passed,
so the implemented `cmd_treachery_revolt` / `cmd_treachery_bribe` handlers were
unreachable through `enumerate_legal -> dispatch` (only callable directly in
tests — the same masking trap as the CtA gap, SMOKE-059).

**Fix (v2.9):** `command_reveal` of a Treachery card now sets up an active
Treachery context for the card's (Mustered) Lord; the command-phase enumerator
surfaces Revolt (eligible target Locales, gated on >= 1 Coin) / Bribe (Path-A
enemy Mustered Vassal) / lapse, and nothing else. Round-trip clean.

**Final campaign verification:** comprehensive all-checks randomized sweep
(116,086 steps): 0 over-enumerations, 0 crashes, 0 stalls, and 0 violations of
VP / forces / calendar-consistency / placement / marker / card-conservation
invariants. Regression: `test_v29_features.py` (8 tests). Full suite 477 pass.

## SMOKE-Inferno-074 — Crossbow Hits: -2 Armor and SELECT their target

**Found:** Per-card / combat-conformance review after the v3.0 audit. Crossbow
archery Hits (Balestrieri Armigieri; Balestre Grosse Men-at-Arms in Storm) were
absorbed by the same routine as melee Hits — full Armor protection and the
NORMAL forced casualty order (Villici/Light Horse first). The Battle & Storm
reference is explicit that Crossbow Hits apply **-2 to the target's Armor** and
that the **firing player SELECTS** which enemy unit each Crossbow Hit strikes
(so they pick the most valuable still-standing unit, not the cheapest).

**Fix (v3.1):** `_absorb_hits` / `_absorb_garrison_hits` now take a
`crossbow_hits` count and an `armor_penalty` (default 2). Crossbow Hits resolve
first against a SELECT order (Ritter -> Cavalieri -> Armigieri -> Men-at-Arms ->
Berrovieri -> Light Horse -> Militia -> Villici) with each target's protection
band truncated by `armor_penalty` (`prot[:max(0, len(prot)-2)]`); remaining
(melee) Hits keep the original NORMAL order and full Armor. Crossbow count per
striking step is computed by `_crossbow_archery_hits` (Armigieri w/Balestrieri
= min(arms,3) x 1.0; Men-at-Arms w/Balestre Grosse, Storm only, x 0.5) and
threaded through `_resolve_step` / `_resolve_storm_step` alongside the
hills/concede/ceil transforms, and through the Garrison's own crossbow tally.
Default (`crossbow_hits=0`) reproduces the prior behavior exactly.
**Verification:** `tests/test_v31_features.py::TestCrossbowMinus2Armor` (a
Cavalieri with Armor 1-3 routs on a die of 2 when struck by a Crossbow Hit but
survives the same die from a melee Hit; Crossbow selects Ritter over Villici)
plus `TestCrossbowArcheryCount`. Full suite 488 pass.

## SMOKE-Inferno-075 — Storm Archery is granted only via Capability, not by default

**Found:** Same review. The Storm strike path granted base Archery Hits to a
Lord's own Foot units and ALSO double-counted Garrison Archery by merging the
Garrison into the Lord's unit dict before striking. The reference gives a Lord's
ordinary Foot units no base Storm Archery — Archery in Storm comes only from a
Capability (Balestrieri / Balestre Grosse Crossbow, or the Arcieri/Luceria
Militia-archery cards) — and the Garrison strikes as a separate body.

**Fix (v3.1):** the Storm archery branch (`_strike_hits_storm`, "def_archery")
now returns `0.0`; the Garrison's contribution is computed separately by
`_garrison_strike` (archery = sum c x UNITS[u].archery; melee = sum c x
storm_strikes_defender) and added once, with the Garrison's crossbow Hits
(Men-at-Arms x 0.5 + Armigieri x 1.0) tracked for the -2 Armor SELECT path.
**Verification:** `tests/test_v31_features.py::TestStormArchery`
(`_strike_hits_storm({"Armigieri":3}, "def_archery") == 0.0`;
`_garrison_strike(castle_garrison, "def_archery") == 1.5`, melee `== 3.0`).

## Note — `cmd_end_card` WRONG_LORD_SIDE / `approach_response` AVOID_INTO_ENEMY_LOCALE (not bugs)

A combat-preferring, all-Capabilities-injected sweep in the v3.1 cycle reported
`over-enum: {(cmd_end_card, WRONG_LORD_SIDE): 406, (approach_response,
AVOID_INTO_ENEMY_LOCALE): 1}`. Investigation showed these are **harness
artifacts, not reachable engine states**. The only path to a wrong-side
`cmd_end_card` is the defensive branch in `_enum_command_phase` that fires when
`current_lord_id`'s side != `current_side(state)`. Instrumenting that exact
condition across 120 capability-injected, combat-heavy games (Scenarios A-F,
seeds 1-10, two trials each) produced **0 hits** — `enumerate_legal` never
constructs the wrong-side end_card, so `dispatch` can never reject one. The
counts arose from the prior probe re-dispatching moves against a state that had
already advanced (stale-move probing). No code change.

## v3.2 — Per-card NUMERIC verification of the 52 AoW Events

After v3.1 the user asked for the deepest rules-fidelity pass: verify each AoW
Event produces the EXACT number its card text specifies, not merely that an
effect fires. The earlier Audit D (v3.0) confirmed effects were *wired*; it did
not check the *quantities*. This pass extracted every card's verbatim Text from
`reference/Inferno_Arts_of_War_Reference.txt`, mapped it to its handler in
`card_effects.py`, and added `tests/test_v32_card_numbers.py` (18 numeric
assertions). It surfaced a cluster of Ghibelline-event defects where the
implementation had been written as a loose "mirror" of a Guelph card and so
implemented the WRONG effect entirely.

### SMOKE-Inferno-076 — S9 Pope at Bay implemented the opposite effect

**Card:** "Set aside 1 Treachery to shift any 2 Guelph cylinders or Service 1
Calendar box or Orvieto by 3." **Was:** shifted Pisa/Siena/Provenzano
(Ghibelline) cylinders LEFT by 1 — favourable to the Ghibellines, the reverse
of the card. **Now:** sets aside one Ghibelline Treachery card already in the
Command deck (the enabling cost; without one the Event can't be played), then
shifts any 2 GUELPH Lords' cylinder RIGHT / Service LEFT by 1 (adverse delay),
or Orvieto by 3. New adverse-shift helpers `_shift_cylinder_right` /
`_shift_service_left` and a `_set_aside_treachery_from_command` cost helper.

### SMOKE-Inferno-077 — S11 Volterra targeted the wrong Lords

**Card:** "If Volterra Ghibelline, shift Colle Service 2 boxes or Pisa cylinder
left to current Levy or add 1 Treachery." **Was:** shifted Astimberg/Santa
Fiora Service RIGHT 2, with no Volterra condition. **Now:** gated on Volterra
free of Guelph markers; default shifts Colle Service LEFT 2, `mode="pisa"`
shifts Pisa's cylinder to the current Levy box (only if to its right),
`mode="treachery"` adds 1. New `_shift_cylinder_to_box` helper.

### SMOKE-Inferno-078 — S15 War Loans gave +1 Coin instead of a shift / Lordship

**Card:** "Shift Siena, Provenzano, Giordano, OR Astimberg cylinder or Service
2 boxes or this Levy give 1 Lordship +2." **Was:** added +1 Coin to one Lord
(an effect that appears nowhere on the card). **Now:** shifts one of the four
listed Lords favourably 2 boxes, or `mode="lordship"` grants a one-shot +2
Lordship (`lordship_bonus_pending`). The stale test that asserted the +1-Coin
bug (`test_S15_war_loans_adds_coin_to_siena`) was rewritten to assert the
Lordship +2 outcome.

### SMOKE-Inferno-079 — F25/F26/S25/S26 War events dropped their Calendar shift

**Cards** each read "If <Stronghold condition>, shift <named Lords> N boxes.
<Side> may declare Call to Arms." **Was:** only the Call-to-Arms flag was set;
the conditional Calendar shift was omitted entirely. **Now:** when the board
condition holds the named Lords shift favourably — F25 Colle 3 (an originally-
Ghibelline Castle now carries a Guelph 1VP marker); F26 Firenze/Arezzo/Orvieto
1 each (originally-Ghibelline Town marked Guelph); S25 three Ghibelline cylinders
1 each (any of Grosseto / Castiglione della Pescaia / Montemassi / Montepescali
marked Guelph); S26 Provenzano/Siena 1 each (originally-Ghibelline Town marked
Guelph). Call-to-Arms is still granted regardless of the condition (per Tips).
New `_favorable_shift` and `_stronghold_marked` helpers.

**Verification:** `tests/test_v32_card_numbers.py` (18 assertions) + the
rewritten phase-4 test. Full suite 506 pass.

### DEFERRED (precise specs for a follow-up combat-engine pass)

**F24 / S24 Doctors — wrong mechanic, needs a battle+storm post-combat hook.**
Card: "Hold: Play in Battle or Storm for [Firenze & Arezzo / Siena & Pisa] each
to restore to their Forces half of their Lost units (round up)" — applied at the
end after all 4.4.4 Loss rolls, including Knights who received Quarter. The
current handler instead rolls each ROUTED unit's Protection die (a different
mechanic) and does so for ALL Lords of the side rather than the two named ones.
A faithful fix must: (a) register a battle modifier at 4.4.1 naming the two
Lords; (b) accumulate each named Lord's Lost+Captured count during loss
resolution — in BOTH `_apply_post_battle` (battle, actions.py) AND inside
`resolve_storm` (storm, battle.py), which resolve losses on separate code
paths; (c) restore ceil(total_lost / 2) units to Forces (and pull restored
Knights back out of `captured_knights`). Deferred because it spans two combat
resolvers and carries regression risk; isolated from the deterministic v3.2
fixes by design.

**F10 / S22 Closed Gates — gold/purple branch asymmetry + ambiguous Revolt
direction.** Card: "Remove 1 [gold/purple] Ruins or, if none, remove 1
[purple/gold] Ruins where Stronghold then eligible for Revolt (1.4.1); it
Revolts (1.4.4)." The current handler triggers a Revolt (placing Allegiance
markers) on only one of its two branches, and the Tips' fallback ("if there are
NO Ruins on the map, instead replace a Ruins benefitting your side with
Allegiance markers equal to Stronghold Value") is not represented. The Revolt
*direction* of the de-ruined Stronghold (toward the playing side vs. per the
Revolt table) is not pinned down by the card text alone, so this is left for a
rules-clarified pass rather than guessed.

## v3.3 — F24/S24 Doctors (Battle) + a newly-found Storm/Sally loss-roll gap

### SMOKE-Inferno-080 — Doctors now restores half of Lost units (Battle), not a Protection re-roll

The v3.2 numeric pass flagged F24/S24 Doctors as using the wrong mechanic. Fixed
for the Battle path. The Event handler no longer rolls each Routed unit's
Protection for every Lord of the side; instead it registers a battle modifier at
the 4.4.1 outset naming the eligible Lords (F24: Firenze, Firenze Comune,
Arezzo; S24: Siena, Siena Comune, Pisa). `resolve_battle` preserves that
modifier onto its result before the 4.4.6 cleanup discards it, and the
post-Battle loss step (`_apply_post_battle` -> `_apply_doctors_restoration`)
restores ceil(L/2) units to each named Lord that fought, where L counts both
units Lost to the pool AND Knights who received Quarter (Captured). The most
valuable units are restored first; restored Captured Knights are pulled back out
of the owner's Captured Knights box. Lords removed in the combat are skipped.
**Verification:** `tests/test_v33_doctors.py` (9 tests) — ceil math (even/odd),
named-lord scoping, Knights'-Quarter inclusion + ledger pull-back, and the
modifier surviving `resolve_battle`'s cleanup onto its result. Full suite 515.

### SMOKE-Inferno-081 — Storm and Sally do not perform the 4.4.4 Loss rolls (gap)

Discovered while implementing Doctors. Battle resolves 4.4.4 Losses in
`_apply_post_battle` (`loss_roll_for_routed` per participant). Storm
(`_h_cmd_storm` -> `resolve_storm` / `_apply_sack`) and Sally (`_h_cmd_sally` ->
`resolve_sally`) determine outcomes from routs but never roll losses for the
routed units, so Routed units after a Storm/Sally are neither recovered nor
removed — they linger in `routed_units` until the Lord's NEXT Battle rolls them
(at the wrong time, with the wrong harsh-recovery context). Per
`reference/Inferno_Battle_and_Storm.txt` §12, "After Retreat/Withdraw/Removal,
BOTH SIDES determine the fate of Routed units" applies to Storm as well, with
harsh recovery for Storm Attackers and Knights' Quarter handled on a Sack
(§12.3: garrison Cavalieri = Stronghold Size, plus all Cavalieri/Ritter of Lords
who lost Defending inside, are Captured; Attackers in Storm never lose units to
Quarter). **Consequence for Doctors:** because Storm produces no "Lost" units
today, F24/S24 played in a Storm currently restore nothing — faithful
Storm-Doctors is gated on this gap. Deferred to its own focused pass (it spans
`resolve_storm`, `resolve_sally`, `_apply_sack`, changes RNG consumption, and
needs care around harsh recovery + garrison Knights' Quarter) rather than rushed.

## v3.4 — SMOKE-Inferno-082: F10/S22 Closed Gates (resolves the deferred item)

The v3.2 pass deferred Closed Gates as "Revolt-direction ambiguous." Resolved by
grounding it in three core rules rather than the card's loose colour wording:
  - Sack rule: a Ruins marker is the colour OPPOSITE the Stronghold's printed
    Allegiance, worth 1/2 VP. So a GOLD Ruins (1/2 VP Guelph) sits on an
    originally-Ghibelline Stronghold; a PURPLE Ruins (1/2 VP Ghibelline) on an
    originally-Guelph one — matching `scenarios._init_vp_from_markers`.
  - 1.4.1: only an Enemy Stronghold with no Enemy Lord there or adjacent Revolts.
  - 1.4.4: a Revolt places Size Allegiance markers of the side OPPOSITE the
    printed Allegiance, and the loser slides Exiles.

Two bugs in the prior implementation: (1) the gold/purple VP sides were
INVERTED (gold decremented Ghibelline, purple decremented Guelph — backwards
from rule 413 and scenarios.py); (2) the 1.4.4 Revolt was skipped on the primary
branch and mis-placed markers on the fallback.

**Now (shared `_closed_gates(state, side, args)`):**
  - PRIMARY — remove the playing side's own-colour Ruins (Guelph=gold,
    Ghibelline=purple) sitting on an originally-ENEMY Stronghold. Once de-ruined
    it is an eligible Enemy Stronghold (1.4.1) that Revolts (1.4.4) to the
    playing side via `revolt.apply_allegiance_switch` — Size markers placed,
    correct VP (own side: -0.5 for the removed Ruins, +Size for the Allegiance),
    and the loser's Exiles surfaced as a `pending_exiles` decision (No-Agent).
  - FALLBACK ("or, if none") — remove one enemy-colour Ruins to DENY the enemy
    its 1/2 VP. Enemy-colour Ruins sit on the playing side's own-home
    Strongholds, which revert to printed-Friendly on de-ruining (no markers).
  - Reconciles card text ("remove gold ... or if none purple"), the Tips
    ("remove a Ruins giving the other side 1/2 VP"), and 1.4.1/1.4.4: the
    primary trades your 1/2 VP Ruins for a full Size flip; the fallback denies
    the enemy their 1/2 VP.

**Verification:** `tests/test_v32_card_numbers.py::TestClosedGates` (4) + the two
rewritten phase-4 tests (which had used invalid boards with a Ruins and
Allegiance markers coexisting). Full suite 519 pass; a live sweep firing F10/S22
across all scenarios with seeded Ruins held VP in [0, 17.5] and never produced a
Locale with both a Ruins and Allegiance markers.

With this, the remaining open AoW item is SMOKE-081 (Storm/Sally do not perform
4.4.4 Loss rolls), which gates faithful Storm-Doctors.

## v3.5 — SMOKE-Inferno-081 resolved: Storm & Sally 4.4.4 Loss rolls (+ Storm-Doctors)

The Doctors work (v3.3) surfaced that Storm and Sally never performed the 4.4.4
Loss rolls that Battle does — routed units lingered in `routed_units` until the
Lord's next Battle. Now closed.

**Shared helper** `_roll_routed_losses(state, specs, capture_knights)` rolls the
4.4.4 Losses for a set of (lord_id, harsh) using a fresh RNG built from the
current `rng_advance` (so it composes after a resolver that already advanced the
stream). `loss_roll_for_routed` gained a `capture_knights` flag.

**Storm** (`_h_cmd_storm`): after `resolve_storm`, the Attacker (besieger) rolls
with HARSH recovery (Attacking in Storm, §12.1b); on `attacker_loss` the
Defenders roll Standard. `capture_knights=False` for both — Storm Knights'
Quarter happens ONLY on a Sack and Attackers are never Captured, so a failed
Knight here is simply Lost.

**Sack Knights' Quarter** (`_apply_sack`, §13): before removing the inside
losers, ALL their Cavalieri/Ritter PLUS the Garrison's Cavalieri (# = Stronghold
Size) are Captured to the losing (owner) side's Captured Knights box for Ransom.

**Sally** (`_h_cmd_sally`): Sally uses Battle procedure (Battle&Storm 2.3), so
the routed units roll with Standard recovery and Battle Knights' Quarter
(`capture_knights=True`); Harsh Recovery does not apply (no side "Retreats
without Conceding" in a raid).

**Storm-Doctors** (SMOKE-080 completion): `resolve_storm` now stashes the
`doctors_restore_half_lost` modifiers onto its result (and consumes them from
pending), and `_h_cmd_storm` calls `_apply_doctors_restoration` after the Loss
rolls — so F24/S24 work in Storm as well as Battle. (Sally is left out: the card
text enumerates "Battle or Storm," not Sally.)

**Verification:** `tests/test_v35_storm_sally_losses.py` (6 tests: capture-knights
gate, routed-pile resolution + conservation, resolve_storm doctors stash, Sack
Knights' Quarter counts, Storm-Doctors restoration). Full suite 525 pass. A
combat sweep across all scenarios drove 57 live Storms with 0 invariant breaks
(no negative forces/routed, VP in [0, 17.5]) and confirmed routed units no
longer linger.

With this, all AoW Events are numerically verified and Battle/Storm/Sally all
perform the 4.4.4 Loss rolls. No known AoW or combat-loss gaps remain open.

## v3.6 — Subsystem audit: End-Campaign 4.9, economic Commands, Naval, Pursuit

Put the four subsystems that had only structural/smoke coverage under a numeric
microscope (rules extracted verbatim from the in-repo references, mapped to each
handler). Most were already conformant; two real defects, both in Ransom (4.9.2).

### SMOKE-Inferno-083 — Ransom recovered too many units

4.9.2: "the paying side selects HALF (rounded UP) of those units." The handler
recovered `sum(ceil(count/2))` PER UNIT TYPE, which over-recovers — e.g. one
Cavalieri + one Ritter (total 2) recovered 2 instead of ceil(2/2)=1. **Fixed:**
recover ceil(TOTAL/2) units, most valuable first.

### SMOKE-Inferno-084 — Languish applied a double penalty

4.9.2: on Languish the captor gets, per 6 unransomed prisoners (round up), ONE
of either a Revolt roll OR a Treachery card (captor's choice; Revolt mandatory
if chosen). The handler did BOTH `n` Revolt rolls AND `n` Treachery adds — twice
the intended penalty. **Fixed:** `n_events = ceil(captured/6)` split between
Revolt rolls and Treachery (default all Revolt; `args.languish_treachery` chooses
the split).

### Verified CONFORMANT (no change needed)

- **End-Campaign**: Feed (4.8.1 1-6/7-12/13+ → 1/2/3, underfed Service -1),
  Grow (4.9.1 reduce enemy Ravage to ceil(N/2) on Calendar boxes 2/5/8/11/14;
  Scenario B Turn-5 skip), Repair (4.9.4 Errata — remove 1 Siege from Town/City
  with 3-4, Castles excluded), Waste (4.9.5 discard 1 from each Lord with >1 of a
  type), Reset (4.9.6).
- **Scoring/Victory (5.x)**: 1/Allegiance, 1/2 Ruins, 1/2 Ravaged, 2 Carroccio;
  Scenario E doubles Guelph VP except Ravaged; Scenario C +3 Ghibelline with S22
  Manfredi in play; 5.2 instant win on no Mustered Lords; 5.3 tie = draw.
- **Economic Commands**: Forage (4.7.1 friendly-stronghold/Summer auto, Spring/
  Autumn die 1-3, Winter blocked outside friendly, Besieged>=Size block, cap 16),
  Supply (4.6 per-Seat = Size / Outpost 1 / Pisa-Ship-at-Port; >=1 Cart per
  Provender per Way; Stores & Well Water = 4), Tax (4.7.4 +1 Coin / Podesta +2,
  own Seat Unbesieged, entire card; S23 block; F25/S25 Reinforced-Walls Tax
  alternative), Ravage (4.7.2 Castle +1 Prov / Town-City +1 Prov +1 Loot;
  Berrovieri/Gualdana doubling; Masnadieri 0-action no-Loot; 1/2 action cost;
  Ravaged marker opposite printed colour +1/2 VP).
- **Naval (Sail 4.7.3)**: Pisa Podesta only, non-Winter, Port-to-Port; capacity
  1 Ship/Horse + 1 Ship/Provender + 2 Ships/Loot; no Sail into Unbesieged Enemy
  Lord; Besiege on Sail to an Enemy Stronghold.
- **Pursuit**: in these rules "Pursuit" is the Concede mechanic, not a separate
  action — the Conceding side halves its Hits (round up per Strike step),
  correctly applied in `_resolve_step`. The "pursues Siege" enumerator label is
  flavour text for continuing a normal `cmd_siege`, not a phantom mechanic.

**Verification:** `tests/test_v36_endcampaign_audit.py` (8 tests: Ransom
recovery half-of-total even/odd, Languish default-all-Revolt + split, Repair
Castle exclusion, Scenario E doubling, Scenario C +3, Ravage Berrovieri
doubling). Full suite 533 pass.

## v3.8 — Audit: 52 AoW Capabilities, core Battle mechanics, Call to Arms

Numeric microscope over the last three structural-only subsystems. Most
conformant; two defects.

### SMOKE-Inferno-085 — Capability hooks mislabeled (latent walls bug)

The combat strike-modifier Capabilities are all correct by NAME (verified:
Feditori +1/Cavalieri cap 4 Guelph / 3 Ghibelline, Rounds 1-2 Battle only;
Army Reserve +1/Cavalieri Round 3+ for eligible Lords; Luceria Militia x1.5 cap
3; Arcieri x1; Balestrieri Armigieri x1 cap 3; Balestre Grosse Men-at-Arms x0.5
Storm). The siege/storm Capabilities also resolve by NAME (Guastatori +2 Siege,
War Engineers any-size + reduce-to-1, Trebuchets Walls/Siegeworks -1 at 3-4
Siege, Siege Towers Storm-Attacker R2+ strikes first). BUT the `register_
capability` HOOK dicts for F3/S3, F4/S4, F5/S5 carried the WRONG effect keys:
F3/S3 Siege Towers registered `storm_walls_minus` (Siege Towers does not reduce
Walls), F4/S4 Trebuchets registered `siege_extra_marker`, F5/S5 War Engineers
registered `siege_walls_minus_1_storm`. `siege_extra_marker` /
`siege_walls_minus_1_storm` are never consumed (dead), but `storm_walls_minus`
IS consumed in `resolve_storm` via `active_capabilities_for` — so if a Siege
Towers (F3/S3) Capability ever entered `capabilities_in_play` (e.g. injected
side-wide), it would spuriously reduce the defender's Walls by 1. Inert in
normal play (Siege Towers is a `this_lord` cap living on a Lord mat, not in
`capabilities_in_play`), but a real latent defect. **Fixed:** the F3/F4/F5 (+S)
hooks now carry descriptive, non-consumed keys; the named lookups (which drive
the actual effects) are unchanged.

### SMOKE-Inferno-086 — Scenario D 'Escalation' CtA rule missing

Call to Arms triggers (VP behind by >=4, drew a War Event, F23 Treasurers + 2
Coin) and the Scenario A/E (no CtA) and C (Ghibelline first-Levy only)
exclusions all matched. But Scenario D ("Arbia Colorata in Rosso") has an
Escalation rule — "In the first Levy, EITHER side may trigger Call to Arms as if
it had drawn a War Event; standard rules thereafter" — that `_cta_trigger_met`
did not implement, so a Scenario D player could not declare a first-Levy CtA
unless a normal trigger happened to be met. **Fixed:** Scenario D, turn 9 (its
starting Levy box) now makes either side eligible; standard triggers apply from
turn 10 on.

### Verified CONFORMANT (no change)

- Battle Strike Initiative — exact 6-step order (Def Archery, Atk Archery, Def
  Horse Melee, Atk Horse Melee, Def Foot Melee, Atk Foot Melee).
- Retreat Service-shift die (4.4.3): 1-2 -> 1 box, 3-4 -> 2, 5-6 -> 3; Concede +
  retained Carroccio -> exactly 1.
- CtA Comune (3.5.3): Sestieri/Terzi Muster WITHOUT rolling (default Carroccio +
  one Sestiere/Terzo minimum); Allies (3.5.4) auto-Muster (no Fealty) / extra
  Muster paths.

**Verification:** `tests/test_v38_caps_battle_cta.py` (11 tests). Full suite 567
pass.

## v3.9 — 20-round aggressive smoke campaign (no engine defects)

Ran 20 distinct probes across all six scenarios: (R1) invariants under random
play, (R2) exhaustive enumerator/handler round-trip, (R3) replay determinism,
(R4) combat-heavy (49 live Storms), (R5) all-capabilities injection, (R6) VP
half-step conservation, (R7) state-schema validation every step, (R8) multi-turn
progression, (R9) biased greedy policies (ravage/tax/treachery/muster/supply),
(R10) AoW card conservation, (R11) routed-pile runaway guard, (R12) captured-
knights shape, (R13) calendar cylinder/service consistency, (R14) atomicity
(rejected dispatch must not mutate), (R15) no-deadlock, (R16) end-campaign
substep integrity, (R17) RNG-advance monotonicity, (R18) JSON round-trip,
(R19) Hidden Mats option, (R20) Advanced Vassal Service option.

Result: **no engine defects.** The only flag (R10, Scenario F) was a HARNESS
counting artifact — the probe's card multiset omitted `state['active_events']`,
where a card drawn as a This-Campaign/This-Levy Event lives until `end_reset`
returns it to the discard. Re-running with `active_events` counted showed exact
conservation at every step (0 drift across 6 scenarios x 6 seeds). Locked with
`tests/test_v39_conservation.py` (asserts the exact per-side total of 26 holds
every step, counting all pools including active_events — catching both loss and
duplication). Full suite 573 pass.

## v4.0 — Illegal co-location bug class (3 engine defects fixed)

Cross-project bug-hunt (with Seljuk-Harness, L&C Vol. V). A single illegal board
state — two opposing Mustered Lords sharing a Locale, BOTH outside a Stronghold,
with no pending Approach/Battle — was reachable through three independent paths.
The existing invariant suite never forbade that state, so heavy fuzzing reported
"0 defects" (a silent-oracle false negative). Added the missing invariant
(SMOKE-Inferno-089, `assert_no_colocated_enemies`, wired into
`check_all_invariants`) and fixed all three doors.

### SMOKE-Inferno-087 — Muster Seat eligibility + Besieged-Podesta placement
Found via Scenario B self-play (seeds 500, 2, 31337; both `levy_muster_lord` and
`cta_allies` auto-muster). The Muster enumerator/handler did NO Seat eligibility
check: a Ready non-Podesta Lord could be Mustered onto an Enemy-occupied/Besieged
Seat (3.4.1 forbids: "free Seat — Friendly, not Enemy-occupied, not Ruins"), and a
Podesta legitimately Mustering at his Besieged Main Seat (Urban Army, 3.4) was
placed in the OPEN beside the besiegers instead of INSIDE the Stronghold
(CtA 3.5.2 example: cylinder goes inside, counting against Size). Fix: shared
`sd.muster_seat_status()` predicate gates both the enumerator and both handlers;
the legal Urban-Army case sets `in_stronghold=True` (respecting Size).

### SMOKE-Inferno-088 — Stale Siege/Bypass marker on departure (4.3.5)
Confirmed after Seljuk reported the analogue. When besiegers Marched out of a
Besieged Stronghold (vs. being defeated), the Siege marker persisted and the
inside defender stayed flagged Besieged — corrupting Forage/Supply/Tax legality
and besiege-vs-join decisions. Fix: shared `_sweep_freed_stronghold()` removes
Siege+Bypass markers and clears the freed defenders' flags whenever a Stronghold
becomes free of Enemy Lords; invoked on March-out and both Disband paths (Bypass
was already swept on Depart).

### SMOKE-Inferno-090 — Post-Battle Retreat now relocates the loser (4.4.3 / 11.2)
The "retreated" branch only applied a Service-box shift; the losing-but-surviving
Lord's map position never changed, leaving him co-located with the victor. Cold
under leftmost-fallback play (which never Concedes, so losers were always fully
Routed → Removed); a random-callback fuzz produced the illegal state in 39.5% of
multi-Lord battles, undetected by the old oracle. Fix: `_retreat_destination()`
picks a legal adjacent Locale per 11.2 (no Enemy Lords; no un-Besieged/un-Bypassed
Enemy Stronghold; Defenders not back along the Approach Way; Marching Attackers to
the origin; no Sail), threading the Approach breadcrumb (March → meta →
post-Battle); no legal target → Removed (4.4.5). Post-fix fuzz: 0/1500 (0.0%).

**Verification:** `tests/test_v40_colocation_fixes.py` (9 tests). Full suite 582 pass.

## v4.1 — Door C completeness: Commander-to-Arms / Comune placement (SMOKE-091)

Prompted by the Nevsky-Harness advisory ("centralize one eligibility gate; every
placement path must call it"). v4.0 routed `levy_muster_lord` and `cta_allies`
through `sd.muster_seat_status`, but TWO more on-board placement paths were
missed:

- `_h_cta_commander_arms` (3.5.2): musters the Commander into the Leading City
  "from ANY Calendar box" — and the CtA worked example does this while the
  Leading City is BESIEGED (Urban Army). The handler set location + lords_present
  but never `in_stronghold`, so a Commander mustered into his besieged Leading
  City landed in the OPEN beside the besiegers (illegal co-location, no Battle).
  Reproduced (Scenario B, Guelph Firenze under Ghibelline Siege). Fixed: route
  through `muster_seat_status`; set `in_stronghold=True` on the Urban-Army case.
- `_h_cta_comune_setup` (3.5.3): the Comune stacks UNDER the Commander cylinder.
  When the Commander is Besieged inside, the Comune must be inside too, else it
  read as an in-the-open Lord co-located with the besiegers. Fixed: Comune
  inherits the Commander's `in_stronghold` flag.

NOT changed (documented cold-path follow-ups, not reachable through gameplay):
- Sally besieger-loss relocation: a losing-but-surviving Besieger should Retreat
  (4.5.3 / 11.2). Through `_h_cmd_sally` the besieger is always either the winner
  or fully Routed→Removed (leftmost fallback never Concedes), so the
  survive-and-retreat branch is cold — same situation Battle Retreat was in
  before a Concede is scripted. To be revisited if/when Sally Concede is surfaced.

**Verification:** `tests/test_v40_colocation_fixes.py` (12 tests; +3 for SMOKE-091).
Full suite 585 pass.

## v4.2 — Validated action palette + enumerator/handler symmetry audit (SMOKE-092)

Adopted the Nevsky-Harness recommendations (validated palette + invariants-first +
enumerator/handler symmetry).

### SMOKE-Inferno-092 — `enumerate_legal_validated`
New agent-facing palette in `legal_moves.py`: wraps `enumerate_legal`, probes each
concrete candidate on a `deepcopy(state)` via `dispatch`, drops any the handler
rejects, and returns `{"moves", "dropped", "unvalidated"}`. `dropped` is a
structured over-enumeration diagnostic. Safe because the RNG is in-state
(`meta.rng_seed`/`rng_advance`) — probing advances only the copy's counter. For
the interactive/agent path only (one deepcopy+dispatch per candidate); hot loops
keep raw `enumerate_legal`.

### Symmetry audit results
- **Over-enumeration: NONE.** 1,188 validated steps across Scenarios B and F
  probed every concrete candidate each step; `dispatch` accepted every move the
  menu offered. Locked by a self-play regression test asserting `dropped == []`.
- **Under-enumeration: 51/58 handlers menu-reachable.** Of the 7 not hit in a
  random sweep, 4 are correctly gated by holding a Capability/Treachery card or a
  Bypass/siege state (`cmd_costruttori`, `cmd_sortie`, `cmd_treachery_bribe`,
  `cmd_war_engineers_reduce` — all have enumerator emit-sites), and `cmd_depart`
  is intentionally surfaced as `cmd_march` for a Bypassing Lord (handler is a
  redundant alias). TWO are genuine under-enumeration gaps (handler exists, menu
  never offers it, alternate channel only):
    - `play_event` — Held Events are playable only via the dedicated CLI
      `play-event` command; `enumerate_legal` never offers them, so a pure-menu
      agent cannot play a Held Event. Proper fix needs per-card play-timing rules
      (to avoid introducing over-enumeration); deferred as a scoped follow-up.
    - `cmd_play_ambush` — F1/S1 Ambush is played by the ATTACKER during the
      defender's Approach-response window, when the active player is the defender;
      the menu (built for the active player) never offers it. Reachable only via
      the out-of-turn `ambush_exempt` dispatch path. Fix needs the enumerator to
      surface attacker reactions mid-Approach; deferred as a scoped follow-up.

### Negative enumerator tests (Nevsky §9)
`tests/test_v42_palette_audit.py` asserts the MENU does not offer an illegal move
(non-Podesta Muster onto an Enemy-besieged Seat), with a positive control for the
Podesta Urban-Army case — guarding the v4.0/v4.1 placement fixes at the
enumerator level, not just handler-rejection.

**Verification:** `tests/test_v42_palette_audit.py` (6 tests). Full suite 591 pass.

## v4.3 — Closing the open items (Sally retreat, event window-guard, Ambush enum)

### SMOKE-Inferno-093 — Sally besieger-loss relocation (4.5.3 / 11.2)
`_h_cmd_sally` cleared the Siege on a besieger loss but never relocated the
losing-but-surviving Besiegers (they remained at the Locale). Now each surviving
losing Besieger Retreats via the shared `_retreat_destination` (no Approach
breadcrumb in a Sally); no legal target → Removed. Cold path (needs a Sally
Concede to leave survivors), verified by replaying a defender-conceding decision
trace through the handler.

### SMOKE-Inferno-094 — Held-Event play-window guard
`_h_play_event` applied any Held Event with NO timing check. Classified each
combat-window Hold by the pending list its effect targets (`_HOLD_EVENT_WINDOW`:
F1/S1 approach; F3/S3 + the battle-modifier Holds = combat) and now reject a play
when its window isn't open (`NO_PLAY_WINDOW`) — closing a latent rules hole
(arming a modifier with no combat) and making the validated palette a sufficient
guard for future event enumeration. (Direct-effect Holds remain ungated; their
own handlers validate context.)

### SMOKE-Inferno-095 — Ambush in the Approach window (under-enumeration fix)
The v4.2 audit flagged `cmd_play_ambush` and `play_event` as never offered by the
menu. Fixed for Ambush: `_enum_approach_reactions` now surfaces, to the ATTACKER
during the defender's Approach-response window, `play_event` for the F1/S1 Ambush
card and then `cmd_play_ambush` to pin an Avoiding Lord; dispatch exempts the
attacker's reactive `play_event` from the turn check (mirroring the existing
ambush exemption). Also fixed the matching over-enumeration: `_enum_approach_
response` no longer offers Avoid to an `ambush_forced` Lord (the handler already
rejected it). Full Ambush flow now works end-to-end through enumerate→dispatch;
validated palette shows 0 drops in the window.

REMAINING (documented, de-risked): proactive menu enumeration of the
battle-/besiege-window Holds (Hills, Swamp, Surprise, …) at their windows. They
are now window-GUARDED (cannot be mis-played) and classified; surfacing them in
the menu at the besiege/pre-battle moment is a safe, well-specified follow-up.

**Verification:** `tests/test_v40_colocation_fixes.py` (+1, Sally),
`tests/test_v43_events_ambush.py` (4). Full suite 596 pass.

## v4.4 — External-agent playability (no engine defect)

Prep for handing the harness to an external LLM (ChatGPT) to self-play Scenario F
and hunt bugs.
- Confirmed the runtime is **stdlib-only**: a full Scenario F game plays to a
  proper victory via the library with NO `pip install` (deps are test-only).
- SMOKE-Inferno-096: extracted the always-on invariants into the runtime package
  `inferno/invariants.py` (importable without pytest/hypothesis), so external
  bug-hunters get `check_all_invariants` (incl. co-location + AoW 26/side
  conservation). `tests/test_invariants.py` now re-exports them (one source of
  truth). Added `selfplay_bughunt.py` (stdlib-only driver: validated palette +
  invariant battery + structured anomaly report) and `CHATGPT_SETUP.md`.

Full suite 596 pass.

## v4.5 — Garrison-only Storm defect (SMOKE-097, found via ChatGPT self-play)

A ChatGPT self-play of Scenario F (seed 11) Stormed the city of Siena while it
was held by its GARRISON alone (no Lord inside) and got an automatic
`attacker_loss` with an EMPTY hit_log and zero rolls — twice. Its driver's
self-checks reported "0 anomalies" because the result was a legal-looking loss;
no invariant watches for "attacker dealt zero hits."

Root cause in `_resolve_storm_step`: the Garrison only struck and only absorbed
Hits when a defending LORD occupied a slot. With a Lord-less defence, the
attacker's Hits were discarded (no target Lord) and the Garrison never struck —
so the attacker could neither damage nor be damaged, and a Storm against a
Garrison-only Stronghold was a total no-op the attacker always lost. Per 4.5.2 /
Siege Sec. 6 (and the rulebook Storm example: "Garrison = 1 Men-at-Arms + 1
Militia + 1 Cavalieri … On Defender total Rout: SACK"), a Garrison-only
Stronghold fights and can be Sacked.

Fix: the Garrison now strikes the Attacker even with no defending Lord (computed
once, aimed at the Attacker's Front slot — also fixing a latent multi-Lord
double-count), and the Garrison absorbs the Attacker's Hits (behind Walls) even
with no Lord in the slot. Verified: a 16-unit Storm now resolves real combat
(26 hits, 75 rolls, both sides take losses); an overwhelming attacker can SACK a
garrison-only Castle; an undermanned attacker still loses (no false Sack).

**Verification:** `tests/test_v44_garrison_storm.py` (3 tests). Full suite 599 pass.

## v4.6 — Combat-engagement tripwire (SMOKE-098)

Make the SMOKE-097 class self-reporting. `resolve_storm` now tags its result
with `both_sides_armed` (forces on both sides at start) and `engaged` (at least
one Strike/roll occurred). `inferno.invariants.assert_combat_engaged(result)`
raises when a combat had forces on both sides but resolved zero strikes — the
exact signature of the garrison-only no-op. The bug-hunt driver
(`selfplay_bughunt.py`) now runs it on every storm/battle/sally result and logs
a `combat_inert` anomaly. So a recurrence of "a combat that should happen but
doesn't" is caught automatically instead of slipping past as a legal-looking loss.

**Verification:** `tests/test_v44_garrison_storm.py` (+2). Full suite 601 pass.

## v4.7 — Feed/Moved-Fought scope (SMOKE-099, Nevsky §8 starvation-spiral class)

Audit prompted by the cross-harness guide (Part II §6 / Nevsky §8). Inferno DID
have the bug. `_h_cmd_forage` and `_h_cmd_ravage` set `moved_fought = True`
unconditionally — so a Lord that only Foraged/Ravaged (no movement) was forced to
Feed at end-of-card, against Commands 606-607 ("pure Supply/Forage/Ravage/Tax
with no movement does NOT mark ... no Feed required"). Reproduced: firenze Forages
+1 Provender at its own Stronghold, then is marked Moved/Fought and would Feed
1-3 Provender (or shift Service left if unfed) — a net loss / starvation spiral.

The same erroneous mark was on four more non-Moved/Fought actions: La Cavallata
(a Ravage, F18/S18), Guastatori Pass (a 4.7.7 Pass), War Engineers
siege-reduction (F5/S5), Costruttori repair (F26/S26). Fixed all six: the only
remaining `moved_fought` set-sites are the canonical March/Avoid/Sail/Encamp/
Battle/Storm/Siege actions (Siege still marks both sides per 609). Capability-trio
rationale recorded in RULES_DECISIONS.md (War Engineers flagged for review).

**Verification:** `tests/test_v45_feed_scope.py` (3 tests, incl. a guard that no
forbidden handler sets `moved_fought`). Full suite 604 pass.

## v4.8 — Surface owner choices the harness auto-resolved (CPL 8.4)

Two player choices the engine had silently auto-resolved are now opt-in through
the BattleDecisionContext, with defaults unchanged. (A) Non-Select-Target Hit
assignment (Battle&Storm 10.2, "the owner chooses units for any other Hits"):
default stays cheapest-first, a consumer may elect a unit via
`bdc.decide_optional("absorb_target", ...)`. (B) Post-Battle Withdraw
(Battle&Storm 11.2): a losing Lord Defending at a Friendly Stronghold MAY
Withdraw into it instead of Retreating; default Retreat, opt-in via
`meta.post_battle_withdraw`.

**Verification:** `tests/test_v48_owner_choices.py` (8 tests).

## v4.9 — Storm armored-first absorption + striker Select-Target (Battle&Storm 10.2)

(A) Hits AGAINST a Storm Attacker must assign to ARMORED units before Unarmored
"regardless of who is choosing" (Battle&Storm 10.2 / Commands 210 / Rules Ref
294) — a forced order, no owner choice. (B) Crossbow / Sudden-Clash Hits let the
STRIKING side Select Target in Battle/Sally; default most-valuable-first,
unchanged.

**Verification:** `tests/test_v49_storm_armored_select.py` (6 tests).

## v5.0 — Full rules-audit fixes

A1 (4.4.1): a combined Relief-Sally loss reduces the Siege markers at the Locale
to ONE. A2 (F23): Via Francigena's +1 Command excludes Guido Guerra and Orvieto.
A5 (5.2): Campaign Victory sudden-death — a side with no Mustered Lords on the
map during the command phase loses immediately.

**Verification:** `tests/test_v50_audit_fixes.py` (7 tests).

## v5.1 — First-Levy Capability This-Lord scope (3.1.2)

A "This Lord" Capability must attach to exactly one Mustered Lord's mat (eligible
per the card, max 2/mat; discard if none) rather than deploying side-wide. A
genuinely side-wide Capability tucks at the map edge.

**Verification:** `tests/test_v51_capability_scope.py` (10 tests).

## v5.2 — Field-Battle tactical choices reachable from the action interface

Storm and Sally exposed `scripted_decisions`, but ordinary March-triggered field
Battles called `resolve_battle()` with no decision channel, so array placement,
tie-breaks, hit allocation, and concession always fell back to the deterministic
leftmost choice — an LLM on the public action interface could not control them.
`approach_response` now accepts an optional `scripted_decisions` arg, accumulated
across the response window and drained by `_finalize_approach` into the field
Battle's BattleDecisionContext (`state['battle_callback']` is also threaded for
self-play).

**Verification:** `tests/test_v52_field_battle_decisions.py` (5 tests).

## v5.3 — Post-Battle Withdraw/Retreat elections via the decision channel

The withdraw-vs-retreat election was only settable by mutating
`meta.post_battle_withdraw`, and the Retreat destination was always the
deterministic leftmost Locale, so a pure-dispatch operator could make neither
choice. `_apply_post_battle` now resolves both through a BattleDecisionContext
fed by an optional `post_battle_decisions` list + callback: `post_battle_withdraw`
(per eligible losing Lord) and `retreat_destination` (per Retreating Lord, among
the legal targets exposed by the new `_retreat_candidates` helper). Defaults are
byte-identical; resolved choices echo on `battle_result['post_battle_decisions']`.

**Verification:** `tests/test_v53_post_battle_decisions.py` (6 tests).

## v5.4 — Sally retreat parity + decision-channel discoverability

(1) `cmd_sally` now resolves a losing-but-surviving Besieger's Retreat
destination through the `post_battle_decisions` (`retreat_destination`) channel,
matching the field-Battle path (default deterministic leftmost). (2)
`enumerate_legal` tags each Battle-triggering move (the Stand `approach_response`,
`cmd_storm`, `cmd_sally`) with an informational `accepts_decisions` key listing
the decision-type vocabulary each optional channel accepts; it is a sibling of
`args`, so `dispatch` ignores it and the move-replay sweep is unaffected. Also
adds a multi-stander field-Battle test proving `scripted_decisions` accumulate
FIFO across the response window.

**Verification:** `tests/test_v54_decision_discoverability.py` (6 tests).

## v5.5 — Stale Approach breadcrumb cleanup + Hypothesis-skip QA fix

(1) Engine: `_finalize_approach` cleared `meta.approach_breadcrumb` only after a
Battle; an all-Avoid / all-Withdraw resolution (no Battle) left a stale
`{approached_from, approached_via}` in the serialized state. Now popped on the
no-standers branch too. (2) Test-suite QA: `tests/test_invariants.py`
module-level-skips when Hypothesis is absent, and several ordinary regression
modules imported helpers through it, so they silently skipped too (hiding the
new decision-interface checks). Invariant-assertion imports now come straight
from `inferno.invariants`, and the shared `_place` helper moved to a neutral,
dependency-free `tests/_helpers.py`.

**Verification:** `tests/test_v55_breadcrumb_cleanup.py` (4 tests). Full suite:
663 pass with Hypothesis; 657 pass + 1 skipped (the Hypothesis property module)
without it.


## v5.6 — Independent (Fable) bug-hunt follow-ups (engine #2–#8)

A second-pass adversarial review surfaced seven issues beyond the v5.2–v5.5
work; all fixed here (the eighth, an Approach-Battle card-flow question, is held
pending a rules second opinion).

- **#2 validate-before-mutate**: `_h_approach_response` popped the pending entry
  (and stored decision lists) BEFORE the Avoid/Withdraw validations, so a
  rejected response stranded the whole Approach window (dispatch has no
  rollback). Now it peeks, validates/applies, then consumes the entry.
- **#3 enumerator/handler symmetry**: the handler rejected Avoid into ANY
  enemy-occupied Locale, but `enumerate_legal` offers Avoid past an Enemy that
  is Besieged inside. Handler now rejects only an UNBESIEGED Enemy (4.3.4).
- **#4 freed-Siege sweep on Retreat**: a loser Retreating off the Battle Locale
  is a departure too; `_apply_post_battle` now calls `_sweep_freed_stronghold`
  when a Retreat actually relocates a Lord (gated so the relief-Sally
  withdraw-inside case is untouched).
- **#5 Withdraw capacity**: post-Battle Withdraw now counts Lords already inside
  the Stronghold against its Size, mirroring the Approach-response path.
- **#6 Friendly predicate**: `_can_withdraw_into_stronghold` now uses the
  canonical `_is_friendly_locale` (current-Allegiance markers) instead of raw
  printed allegiance (SMOKE-Inferno-052).
- **#7 Disband clears flags**: `_disband_beyond_service_limit` now resets a
  Lord's transient `flags`, so a re-Mustered Podestà is not phantom
  `in_stronghold` / `moved_fought`.
- **#8 scripted side**: `BattleDecisionContext` enforces a scripted entry's
  `side` when it pins one (entries omitting `side` stay valid for either),
  closing an adversarial two-operator scripting hole.

**Verification:** `tests/test_v56_fable_followups.py` (13 tests). Full suite:
676 pass with Hypothesis; 670 pass + 1 skipped without it.


## v5.7 — Approach Battle ends the Command card (4.4.6 Recovery; bug-hunt #1)

Ruling (definitive, RoP 4.4.6 Recovery): "Skip any Command actions remaining
this card. Go to Feed/Pay/Disband (4.8). A Battle or Storm blocks any further
Command actions on the current Command card." Cross-ref 4.2.1; the Sequence of
Play confirms card ends -> both sides FPD -> the OTHER side flips next.

`_finalize_approach` had been ending the marching card by manually nulling
current_card/current_lord_id/actions_remaining while skipping `_run_fpd` (4.8)
AND `_flip_active_side` (4.2) — so after an Approach Battle the attacker revealed
another Command card, the defender's turn was skipped, and neither side's
Fought Lords Fed. (Not a hard deadlock: the "0 legal moves" seen in single-Lord
cases was a legitimate 5.2 sudden-death victory.) Now the path routes through
the canonical `_finish_card_with`, the single correct card-end for all three
combat actions (Battle / Storm / Sally) per 4.4.6. active_player is restored to
the attacker first so the flip hands the turn to the defender (4.2), and FPD
feeds BOTH sides' Fought Lords.

**Verification:** `tests/test_v57_approach_battle_card_end.py` (4 tests:
card_finished + FPD present, turn flips to the defender and the attacker cannot
re-reveal, the defender's surviving Fought Lord is Fed, and the card still ends
through FPD even when the lone defender is wiped). Full suite: 680 pass with
Hypothesis; 674 pass + 1 skipped without it.


## v5.8 — Transactional dispatch for operator decision channels (bug-hunt, scenario F self-play)

Found by scripted-decision fuzzing during scenario-F self-play: an invalid
`scripted_decisions` / `post_battle_decisions` entry (wrong type for the
choice point, wrong side, or a choice outside the legal options) was rejected
by `BattleDecisionContext.decide` only at the choice point itself — i.e. AFTER
the Battle had begun mutating state. The bare `ValueError` escaped `dispatch`
with units already Routed, the pending `approach_response` window consumed,
and the Approach/card flow stranded; and because it was not an
`IllegalAction`, the LLM player's retry loop (`play_with_callback`) could not
catch it either, so one malformed decision killed the driver AND corrupted the
game. The same applied to a `battle_callback` returning an invalid option.

Fix: (a) those rejections are now a dedicated `ScriptedDecisionError`
(`ValueError` subclass, so legacy catchers still work); (b) `dispatch`
snapshots the state whenever a decision channel is live (args carry
`scripted_decisions` / `post_battle_decisions`, a `battle_callback` is set, or
scripts have accumulated across an Approach-response window) and restores it
on ANY handler failure, then surfaces the decision error as
`IllegalAction("BAD_DECISION")`. A rejected decision is now exactly like any
other rejected action: state untouched, retry with a corrected script
resolves the Battle normally. Handlers without a live decision channel follow
validate-then-mutate and pay no snapshot cost.

**Verification:** `tests/test_v58_decision_rollback.py` (4 tests: invalid
choice and wrong-type entries raise `BAD_DECISION` with byte-identical state,
a corrected retry resolves the Battle, exception-type back-compat). Full
suite: 678 pass + 1 skipped without Hypothesis. Self-play: scenario F clean
across aggressive / passive / chaos / rarity-weighted policies (20+ full
games, zero anomalies).


## v5.9 — Storm/Sally callback threading + Sail enemy-Port enumeration + Greed discard (edge-case hunt #10–#12)

Round 2 of scenario-F bug-hunting aimed at the never-exercised paths: a
random-valid `battle_callback` decision fuzzer (1,500 direct
Battle/Storm/Sally resolutions, every decision type hit), plus staged-state
fuzzers for Sail (190+ sails) and Treachery (37 Revolts/Bribes through the
validated palette).

**#10 — `cmd_storm` / `cmd_sally` dropped `state['battle_callback']`.**
`resolve_storm`/`resolve_sally` accept a `callback`, field Battles pass it,
and even the Sally POST-battle retreat context passed it — but the Storm and
Sally combats themselves never did. A self-play operator steering tactics via
callback silently lost control (concede, reserve adds, hit allocation all
fell back to leftmost) in every Storm and Sally. Both call sites now thread
the callback. `tests/test_v59_storm_sally_callback.py`.

**#11 — Sail under-enumeration: enemy Ports never offered.** 4.7.3: "Move
directly to any other Port that is free of Unbesieged Enemy Lords"; arrival at
an Unbesieged Enemy Stronghold Besieges (Siege marker). The handler
implemented this (SMOKE-Inferno-027) but the enumerator filtered destinations
to FRIENDLY Ports only, so Sail-to-Enemy Siege was unreachable from
`legal-moves` — invisible to the validated-palette check, which only catches
over-enumeration. The enumerator now mirrors the handler.

**#12 — No Greed discard for Sail.** 4.7.3: cargo that cannot be transported
"must be discarded or left behind (per Greed, 1.7.2)" — the harness
hard-blocked INSUFFICIENT_SHIPS with no discard mechanism, making Sail
unusable for an over-laden Pisa. `cmd_sail` now accepts an optional `discard`
arg ({"Provender": n, "Loot": m}), fully validated BEFORE any mutation (a
rejected Sail consumes nothing); the enumerator offers a deterministic
minimal-discard variant. `tests/test_v59_sail_enemy_port_and_greed.py`.

**Verification:** suite 686 pass + 1 skipped. Combat fuzz: 1,500 resolutions,
0 anomalies. Sail fuzz: 190+ sails (32 enemy-Port Besieges), 0 anomalies.
Treachery fuzz: 0 anomalies.

---

## v6.0 — Arts-of-War numeric conformance audit (CONF-008, CONF-009)

Round-3 conformance pass: a full card-by-card re-derivation of all 52 Arts-of-War
Event/Capability numerics against `reference/Inferno_Arts_of_War_Reference.txt`
(the residual surface flagged in RULES_CONFORMANCE "Depth note" — per-card Event
numerics were previously sampled, not re-derived field-by-field). All 52 located;
combat/economic numerics (Feditori 4/3, Luceria ≤3 ×1.5, Doctors ceil, Camp
Attack 2+2, Guastatori marker cap, garrison/Sovrintendente) re-confirmed exact.
Two real defects found and fixed; two reported `event_kind` items investigated and
ruled NOT bugs (see below).

**CONF-008 — F14 Provenzano shifted the ENEMY Lord the WRONG WAY (HIGH).**
AoW F14 Tips: "shift Provenzano's cylinder **right** or Service marker **left**"
— an adverse shift, because Provenzano is a Ghibelline (enemy of the Guelph who
plays F14). The handler called `_shift_cylinder_left(..., "provenzano", 2)`,
advancing the enemy Lord's *arrival* by two boxes — a direct gift to the
opponent — even though the inline comment said "right." Now mirrors the
correctly-implemented sibling cards F18 Grosseto / F19 Volterra: cylinder RIGHT
(+2) if on the Calendar, else Service LEFT (−2) if Mustered, with `mode="service"`
to force the Service option. The prior test only exercised the no-Siege branch,
so the reversed direction was never asserted. `tests/test_v60_conf008_009.py`.

**CONF-009 — F2/S2 Betrayals double-applied and never resolved the Revolt (HIGH).**
AoW F2: "For each Stronghold with any [side] Siege markers, roll on the Revolt
table **OR** add 1 Treachery" — per Siege, choose one; the choices sum to the
Siege count. The handler instead, on every Siege, rolled a die *and* added a
Treachery card — and the die roll applied **no Revolt outcome at all** (it was
logged and discarded). So it ignored the "OR" and left the Revolt option
unimplemented while spending RNG on a phantom roll. Refactored both F/S copies
onto a shared `_betrayals(...)`: default = add one Treachery per Siege (a legal
all-Treachery choice, deterministic, same realized Treachery count as before
minus the phantom rolls); pass `revolt_count=k` to roll `k` real Revolts through
`revolt.trigger_revolts` (benefitting the playing side) and add `sieges−k`
Treachery. `tests/test_v60_conf008_009.py`.

**Investigated, NOT bugs (event_kind metadata).** The audit also flagged F20
Heat & Frost ("should be immediate") and S14 Friars ("should be this_campaign").
Both were ruled non-defects on verification: (a) `event_kind` only auto-invokes
the handler for `immediate`; `hold` correctly routes through the play-event
window where S14's handler sets its own `this_campaign` flag, so re-tagging S14
would bypass the handler. (b) F20's effect fires "before Feed," a Campaign-phase
window — tagging it `immediate` would fire Wastage at Levy-draw (wrong time); the
S20 mirror reads "Hold:" and its Tips say it "works the same as F20," so the
missing "Hold:" on F20 is a reference-digest transcription artifact, not a card
difference. Left as-is and documented.

**Also noted (doc, not engine):** the `Inferno_Battle_and_Storm.txt` digest's
Forces table lists Light Horse with "Archery ×1/2" and Militia melee "×1/2";
both contradict the authoritative `Inferno_Forces_and_Strongholds.md` (Light
Horse has no Archery; Militia melee is ×1) — and the engine follows the
authoritative source. Digest-only typos; no code impact.

**Verification:** full suite **700 pass** (8 new); no regression.

---

## v6.1 — Revolt-table conformance audit (CONF-010)

Round-3 continued: full line-by-line audit of the Revolt subsystem (revolt.py)
against `reference/INFERNO_Revolt_Tables_Reference.txt` + Rules of Play 1.4.1–1.4.4.

**Verified conformant:** both 6×6 Revolt matrices are byte-perfect (72/72 cells
diffed programmatically; every named Locale exists in the map data; SUBMISSION
cell counts 4/6 correct; Playbook Chiusi example confirmed at gold6×purple5).
Dice convention (row=gold, col=purple, no flip between tables) and table
selection (loser→"Revolt Against <loser>") correct. REBELLION presence check
correctly requires a real Lord cylinder OR Allegiance MARKER within 1 (not
printed). 1.4.4 allegiance switch (place Value markers / revert-to-printed) and
Exiles (cylinders left / Service right, count = markers placed-or-removed)
conformant. Economic Tax spot-check (+1 Coin, Podestà +2, own-Seat only)
conformant.

**CONF-010 — SUBMISSION accepted printed-enemy (un-marked) targets (HIGH).**
RoP 1.4.2 SUBMISSION: "select a Stronghold **marked with Enemy Allegiance
(only, not printed Allegiance)** ... at or adjacent to which the rolling side
has a Lord cylinder." The SUBMISSION branch reused `is_eligible_for_revolt`,
whose `_effective_allegiance` falls back to *printed* allegiance — so a
printed-enemy Stronghold with **no** Allegiance markers (53 of 57 Strongholds
at game start) was wrongly offered as a SUBMISSION flip. Repro: a SUBMISSION
roll offered un-marked printed-Ghibelline Pisa to the Guelphs. Fixed: SUBMISSION
candidates now additionally require an actual losing-side Allegiance MARKER
(`_is_marked_with_allegiance`). This is exactly the "(only, not printed)"
distinction the Rules draw — and the same clause, on the REBELLION side, governs
*presence* (already correct), which is why the two paths must differ. Matches
the project's own Q-002 adjudication (RULES_DECISIONS.md). Two existing v19
submission-flow tests built their states from un-marked printed-enemy
Strongholds; updated to place real Enemy markers (so they keep exercising the
multi-candidate path, now correctly). Guards: `tests/test_v61_conf010_submission.py`
+ updated `tests/test_v19_features.py`.

**Verification:** full suite **702 pass** (2 new, +2 previously-skipping v19
tests now active); Revolt matrix diff 72/72; six-scenario self-play smoke clean.

---

## v6.2 — Card-effect INTEGRATION fuzzing (clean round)

New harness `cardfx_fuzz.py` forces all 52 Arts-of-War card effects into LIVE
play rather than unit tests:
  - **Capabilities × combat:** each Capability is deployed (conservation-faithful:
    moved out of the deck into exactly one play slot) and then run through a 1v1
    Battle, a Storm, a 2v2 Battle, and a Sally with randomized force compositions
    (always incl. Armigieri/Men-at-Arms so Crossbows can fire). Every decision is
    driven by a random-valid callback; invariants + `assert_combat_engaged` are
    checked after each combat.
  - **Events × live state:** each Event is reset to a clean in-hand state and
    applied across seeds/arg-variants, with full invariants after (and faithful
    discard so AoW card conservation stays a real signal).

**Coverage win:** this is the first harness to exercise the Crossbow
`select_target_unit` decision channel — 3,933 firings across a 10-seed run — which
no full self-play game ever reached (flagged as the last unreached channel in the
v5.9 edge-case report). Also fires `initial_placement_*` (Array), `center_fill`
(Reposition), `concede`, and `absorb_target` across all 52 cards.

**Result: 0 engine anomalies** across 52 cards × 10 seeds. The defects surfaced
during harness development were all *staging* artifacts (double-counted AoW cards
from registering a Capability without removing it from the deck; a Mustered Lord
left without a location in 2v2 setup) — fixed in the fuzzer, not the engine. This
is the first diverse round to come back empty, consistent with the bug-find rate
beginning to flatten on the combat/card surfaces audited in v6.0–v6.1.

Locked in as `tests/test_v62_cardfx_integration.py` (52 cards × 2 seeds; asserts
no anomalies AND that the Crossbow/Array/absorb channels actually fire).

**Verification:** full suite **703 pass** (1 new).

---

## v6.2.1 — CI tooling (housekeeping)

The hosted GitHub Actions workflow can't be pushed by the automated PAT (no
`workflow` scope — GitHub blocks any push under `.github/workflows/`). To deal
with this without losing the automation:
  - `scripts/ci.sh` + `Makefile` run the identical checks locally / as a git
    pre-push hook: full suite + six-scenario self-play smoke + card-effect fuzz,
    non-zero exit on any failure.
  - The workflow YAML is parked (version-controlled) at `ci/github-actions-ci.yml`
    with `ci/README.md` documenting the one-line enable (web-UI add or a
    `workflow`-scoped token).
Also fixed the git remote to the repo's new canonical URL (Inferno-Harness).
No engine changes.

---

## v6.2.3 — CI hardening (pre-empt first-run failure)

Before the first hosted run could go red on an environment difference: the
workflow's test step used bare `pytest`, but the suite relies on the repo root
being on `sys.path` (24 files do `from tests.X import ...` / `import cardfx_fuzz`).
`tests/` is a package so pytest's rootdir insertion covers it, but to remove all
doubt the step now uses `python -m pytest -q` (guarantees CWD on path — exactly
how the suite is validated locally). Also added a `cardfx_fuzz.py --seeds 6` CI
step so the Crossbow `select_target_unit` / Array / Sally channels are exercised
on every push (the in-suite `test_v62` runs only 2 seeds). No engine changes.

---

## v6.3 — Save/load + replay-determinism fuzz (clean round)

New harness `saveload_fuzz.py`: plays each scenario to a random mid-game
checkpoint, JSON round-trips the state there, then continues BOTH the reloaded
copy and the untouched control to game end under one deterministic policy
(chosen from control, applied to both). Asserts: the checkpoint round-trips
losslessly, the same action stays legal on the reloaded copy every step (no
dispatch crash), the final states are deep-equal, and invariants hold.

This is harness-level correctness no playtest exercises — it proves the
serializable state form fully captures the game (no tuple/set/int-key drift, no
hidden module-level or non-deterministic state).

**Result: 0 anomalies across 360 full games** (6 scenarios x 60 seeds). State is
JSON-clean without `default=` and round-trips with equality at every depth.
Locked in as `tests/test_v63_saveload_determinism.py` (6 scenarios x 3 seeds) and
added as a CI step (`saveload_fuzz.py --seeds 8`).

This is the SECOND consecutive diverse round to come back empty (after v6.2
card-effect integration fuzzing) — continued evidence the bug-find rate is
flattening on the combat, card, and harness-correctness surfaces.

---

## v6.4 — Siege subsystem conformance audit (CONF-011, CONF-012)

Line-by-line audit of the Siege subsystem (Besiege/Bypass, Siege action,
Encamp, Sortie, Surrender, Sally raid) vs reference/Inferno_Siege.txt + RoP
4.3.4-.6 / 4.5.1.

**Verified conformant:** Siegeworks (add 1 marker iff Besiegers ≥ Stronghold
Size; Guastatori +2; War Engineers any size; MAX 4); Surrender threshold (Value
dice, each ≤ Siege+Ravage markers; one Ravage marker adds 1 regardless of
owner); Besiege (1 marker, ends card); Bypass (continues card); Encamp (replace
all Bypass with ONE Siege, mark only the encamper); single-Lord Sortie; Sally
raid (loser reduces Siege to 1); marker removal when a Stronghold is free of
Enemy Lords; Repair erosion (Town/City 3-4 markers, Castles excluded — prior
Section E). Group Sortie is a documented deferral (single-Lord is correct).

**CONF-011 — Surrender flipped Allegiance / VP incorrectly (HIGH).**
RoP 4.5.1: surrender sets the Stronghold to the Besieger's Allegiance "EITHER
placing markers equal to its Value OR removing markers already there; adjust
Victory (5.1)." `_apply_surrender` instead ALWAYS placed `size` Besieger markers
and did vp[side]+=size / vp[enemy]-=size. Two errors: (a) on a Besieger-PRINTED
Stronghold (flipped to the enemy then re-taken) it should revert to
printed-Friendly — place 0 markers — but it stacked `size` markers, inflating the
Besieger's final marker-counted VP (`_compute_final_vp` counts actual markers);
(b) the enemy lost `size` VP even when it held fewer than `size` markers (e.g. a
printed-enemy Stronghold with no markers — 53/57 at start), over-subtracting the
running VP that feeds the 4-VP Call-to-Arms ("vp_lag") trigger. Fixed by routing
the flip through the audited `revolt.apply_allegiance_switch` (place Value when
enemy-printed, else revert; VP by markers actually placed/removed). Confirmed
against the RoP that Surrender does NOT trigger 1.4.4 Exiles (the digest's
Section 9 over-generalized — Exiles are Revolt-specific). Guard:
`tests/test_v64_conf011_surrender_vp.py`.

**CONF-012 — Encamp left co-located Bypassers flagged Bypassing (MED).**
Encamp replaces the Bypass with a Siege, but cleared the `bypassing` flag only on
the active Lord. A second Lord Bypassing the same Locale was left flagged
Bypassing a now-Besieged Locale (violating 4.3.5/4.3.6 "all outside Lords are
either all Besieging OR all Bypassing"), a stale flag that would mislead a later
Depart/Sortie. Now clears every co-located Bypasser. Guard: same test file.

**Verification:** full suite **708 pass** (4 new); save/load + self-play smokes
clean.

---

## v6.5 — Levy / Muster / Feed-Pay-Disband audit (CONF-013)

Line-by-line audit of the Levy phase (3.1-3.5) and Campaign Feed/Pay/Disband
(4.8) vs reference/Inferno_Commands.txt + RoP.

**Verified conformant:** Pay (3.2 — 1 Coin/Loot = 1 box, Podestà 2/box, payer+
target same Locale, Loot needs a Friendly unbesieged Locale); Feed thresholds
(1-6→1, 7-12→2, 13+→3 Provender/Loot); FPD sequencing (Feed → optional Pay,
Guelph then Ghibelline → Disband → remove Moved/Fought); Disband Beyond Service
(3.3.1) triggers Revolt+Treachery 1× regular / 3× Podestà (Comune exempt),
At-Service-Limit (3.3.2) does not; Fealty Muster (3.4.1 die ≤ F rating, Section C).

**CONF-013 — Feed ignored mandatory Sharing (1.5.2) (MED/HIGH).**
The 4.8.1 Feed step fed each Moved/Fought Lord from his OWN Provender/Loot only —
the inline comment read "Sharing deferred." Rule 1.5.2 makes Sharing MANDATORY:
"Lords at the same Locale MUST Share Provender/Loot to Feed any other Friendly
Lord at that Locale who could not fully Feed ... a side may NOT withhold." So a
Lord with a co-located Friendly Lord holding surplus was wrongly left Unfed and
took a Service-left shift (cascading toward Disband Beyond Service → Revolt/
Treachery). Separately, an Unfed Lord did not even consume his PARTIAL assets,
though 1.5.2/4.8.1 say he "still consumes those AND suffers the shift." Rewrote
Feed as two passes: (1) every Lord feeds from his own assets; (2) co-located
Friendly Mustered Lords Share their remaining Provender/Loot to cover shortfalls
before any Service shift; a Lord still short has consumed all available and
shifts. (The harness already had `_share_available`/`_pay_from_locale` for the
active-Lord commands — Feed simply never used them.) Guard:
`tests/test_v65_conf013_feed_sharing.py`.

**Verification:** full suite **710 pass** (2 new); save/load determinism (72
games) + six-scenario self-play smoke clean after the Feed change.

---

## v6.6 — Supply / Forage / Ravage audit (CONF-014, CONF-015, CONF-016)

Re-derived line-by-line vs reference/Inferno_Commands.txt + RoP 4.6/4.7.1/4.7.2.

**Verified conformant:** Forage (Ravaged/Besieged-by-≥Size blocks; Friendly
unbesieged Stronghold auto +1; Summer auto; Spring/Autumn 1d6 ≤3 → +1; Winter
none outside Friendly; no Moved/Fought); Supply (Source = own unruined Seat or
Pisa-Ships-Port; route BFS avoiding un-Besieged/un-Bypassed enemy; 1 Cart per
Provender per Way, 0 at own Seat; max = Stronghold Size / 1 Outpost / 4 with
Stores & Well Water); Ravage cost (Castle 1, Town/City 2; Masnadieri 0), marker
= opposite PRINTED Allegiance, +½ VP to that side, gains (Castle +1 Prov; Town/
City +1 Prov +1 Loot; Berrovieri/Gualdana double).

**CONF-014 — Ravage Loot capped at 8 instead of 16 (MED).** `_apply_ravage_gains`
capped Loot at 8 while the Asset maximum is 16 (1.7.3; Provender caps at 16
everywhere). A Lord Ravaging Towns/Cities was wrongly denied Loot past 8. → 16.

**CONF-015 — Ravage accepted a REMOTE target (HIGH).** `cmd_ravage` honoured any
`target_locale` without checking the Lord was there — so a Lord at Firenze could
Ravage Pisa (non-adjacent), gaining Provender/Loot/VP and placing a Ravaged
marker on a Locale he never occupied. Repro confirmed. Ravage (4.7.2) acts on the
Lord's OWN Locale (adjacent-Outpost Ravage is the separate La Cavallata
Capability); handler now rejects a target ≠ the Lord's Locale. The enumerator was
already correct (only offers the Lord's Locale), so this was pure handler
under-validation.

**CONF-016 — Pisa Ship-Supply not blocked in Winter (LOW/MED).** 4.6.2: a Port is
a Ship-Source "only ... not in Winter" (Ships don't operate in Winter, as with
Sail 4.7.3). Supply allowed a remote Port Ship-Source year-round; now gated to
non-Winter (a Winter Port-via-Ships Source is rejected BAD_SOURCE; Pisa's own
Seat-Port still supplies normally).

**Verification:** full suite **716 pass** (6 new); save/load determinism + six-
scenario self-play smoke clean.

---

## v6.7 — Victory-scoring (5.x) audit (CONF-017)

Re-derived 5.1/5.2/5.3 + scenario modifiers vs RoP.

**Verified conformant:** 5.1 VP sources (1 VP per Allegiance marker, ½ VP per
Ruins, ½ VP per Ravaged, 2 VP per Captured Carroccio); 5.2 Campaign sudden-death
(a side with no Mustered Lords loses regardless of VP); 5.3 End-of-Scenario
(more VP wins, tie = draw); Scenario E 'Resistance' doubles Guelph VP except
Ravaged; Scenario C 'Alliance Treaty' adds +3 to Ghibelline iff the S22 card
(whose Capability IS "Manfredi") is in play. Ruins/Ravaged marker colours score
to the opposite-of-printed side. End-of-game step (4.9.3) on the last Campaign.

**CONF-017 — End-game winner used CAPPED VP (LOW, edge).** `_compute_final_vp`
clamped each side to 17.5, but VP has no upper cap in the rules (2.2.5: scores
over 16½ are tracked off-map past box 16) and 5.3 decides the winner by who has
MORE VP. In a blow-out where BOTH sides exceed 17.5 (reachable mainly via the
Scenario-E Guelph doubling), the clamp could flatten a real win into a false
DRAW, and always understated a high final score. Now `_compute_final_vp` returns
true totals (floor 0) so the winner comparison is exact; the game-end handler
still clamps the persisted running track `state["vp"]` to 17.5 to honor the
display bound and the `assert_vp_cap` invariant. Guard:
`tests/test_v67_conf017_vp_uncap.py`.

**Verification:** full suite **719 pass** (3 new); save/load determinism + six-
scenario self-play smoke clean.

---

## v6.8 — Adversarial-input robustness fuzz (round-3 #3): CONF-018..021

A new diverse technique: instead of valid play, `robustness_fuzz.py` feeds every
handler malformed/illegal/mutated args (unknown actions, missing/None/wrong-type
lord_ids, bad locales, negative/huge/non-numeric amounts, a legal move with one
field corrupted, malformed envelopes) and asserts the dispatch contract:
  1. bad input is ALWAYS rejected with IllegalAction — never a bare crash;
  2. a REJECTED action leaves state byte-identical (validate-then-mutate);
  3. an ACCEPTED action keeps the always-on invariants.
Each mutation runs on an isolated JSON copy so probes never perturb the game.

Found and fixed FOUR defect classes (all invisible to a valid-palette agent):

**CONF-018 — Muster sub-handlers consumed Lordship before validating (MED).**
`levy_muster_vassal/_lord/_transport/_capability` each called `_consume_lordship`
up front, so a rejected Muster (unknown/not-ready/CtA-only Vassal, bad target/
seat, non-Pisa Ship, empty deck) leaked a consumed Lordship action — a
validate-then-mutate violation (same class as the original bug #9). All four now
consume Lordship only AFTER validation passes (a failed Fealty/Sestiere roll
still consumes, as the rules intend; a rejection consumes nothing).

**CONF-019 — `plan_add_card` crashed on a non-string card_id (MED).** A
missing/None card_id hit `cid.startswith(...)` → bare AttributeError instead of
IllegalAction. Now type-checked up front.

**CONF-020 — `cmd_march` Maremma latch leaked on rejection (LOW).** The Scenario-C
dashed-line check memoized `meta.guelph_aggression_seen=True` mid-validation, so a
March that rejected downstream left the flag set. The latch was only a cache;
dropped it and recompute the gate each time (no behaviour change, no leak).

**CONF-021 — `int(args[...])` crashed on non-numeric input (MED).** Five sites
(`amount`, `provender`, `count`, `coin`, `languish_treachery`) did a raw `int()`
on operator-supplied args → bare ValueError/TypeError. Added a guarded `_int_arg`
that raises IllegalAction("BAD_INT_ARG").

**Verification:** full suite **722 pass** (3 new); robustness fuzz now CLEAN
across all six scenarios × 3 seeds (~30k+ rejected mutations, 0 crashes, 0
transactional leaks). Locked in as `tests/test_v68_robustness.py` + a CI step.
This was a productive round (4 finds), so it does NOT count toward the "empty
rounds" release criterion — but the surface is now clean for re-runs.

---

# v6.9 — Digest-vs-PDF re-derivation round (CONF-022 … CONF-036)

Method: four parallel line-by-line diffs of the `reference/*.txt` digests
against `pdftotext -layout` of the Rules of Play (+ Playbook + errata), every
candidate re-verified against the PDF first-hand, then against the engine.
~30 digest discrepancies found; roughly half were digest-only (engine already
followed the PDF — logged in RULES_CONFORMANCE.md), the rest were inherited:

- **CONF-022 (HIGH)** Lords removed in Battle/Sally now receive Knights'
  Quarter for ALL their Cavalieri/Ritter (owner's Captured Knights box, 4.4.5).
- **CONF-023 (MED)** Battle/Sally Concede now available at the start of
  Round 1 (4.4.2); Storm stays Round ≥ 2 Attacker-only.
- **CONF-024 (HIGH)** Multi-Lord Storm and Sally: all own-side Lords at the
  Locale join (Active at Front, rest Reserve), all marked Moved/Fought;
  Storm-emptied Lords removed per 4.4.5.
- **CONF-025 (MED)** Storm: Reserve Lord FORCED to an empty Front (4.5.2).
- **CONF-026 (HIGH)** Crossbow Select-Target only in Storm Defense or with
  Balestrieri+Palvesari; other crossbow Hits stay -2 Armor but owner-assigned.
- **CONF-027 (LOW)** Comune may take Front center when its Commander is the
  Active Lord (Battle + Storm); Storm defender front choice surfaced.
- **CONF-028 (MED)** Carroccio Concede-Service 1-box shift applies to EVERY
  Retreated Lord of the Conceding side, not just the carrier.
- **CONF-029 (HIGH)** Muster Seat eligibility: Enemy-ALLEGIANCE now blocks
  (was unchecked — could Muster at a Revolted Seat!); Ruins allowed unless
  enemy-occupied; Bypassed Seats allowed (Lord comes up inside).
- **CONF-030 (MED)** Emergency Army implemented (Podestà Ready-waiver when
  enemy Lords at his Main Seat), handler + enumerator.
- **CONF-031 (MED)** 3.5.4 auto-Muster now requires Ready.
- **CONF-032 (MED)** 3.5.2 Commander Muster validates Leading-City
  eligibility (Enemy-aligned blocks; Urban Army besieged-entry kept).
- **CONF-033 (MED)** Surrender roll optional (`roll_surrender: false`);
  declined roll still accrues Siegeworks.
- **CONF-034 (NOTE)** Sortie→Avoid was already reachable; misleading pending
  metadata fixed + end-to-end regression test.
- **CONF-035 (LOW)** Sail requires a FRIENDLY unbesieged start Port.
- **CONF-036 (MED)** Scenario F Exhaustion: unclamped slide + immediate end
  when Levy and End meet; ALL fallback endings now score from computed final
  VP (was running VP — Scenario F's normal ending always mis-scored).

Open: CONF-037 (Relief Sally rear-array/Reserve-first targeting) — needs a
two-front battle model, deferred.

Tests: +29 (`tests/test_v69_conformance.py`) → 751 passing. Fuzzers: cardfx,
saveload (via suite), robustness (ABCDEF×2), selfplay A/C/E/F — all clean.
