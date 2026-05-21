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
