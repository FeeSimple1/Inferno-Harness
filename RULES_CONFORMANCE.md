# Rules Conformance Audit — Inferno Harness

Positive, rule-by-rule cross-check of the implementation against the Rules of
Play (Living Rules 2023-04-10), the in-repo `reference/` distillations, and the
`sources/` PDFs. Distinct from the SMOKE structural sweeps (which prove the
engine is internally consistent, not rules-correct).

Status legend: OK = matches source; FIX = discrepancy fixed (see SMOKE/CONF id);
Q = ambiguity filed in RULES_QUESTIONS.md; NOTE = intentional/edge.

---

## A. Lords data table (vs Inferno_Lords.txt)

All 14 mats cross-checked field-by-field — Side, Seats, Ratings (F/S/L/C),
Forces, Assets, Podestà/Commander flags, and every Vassal's Seat / Service
Rating / Forces / Muster die.

- Ratings, Forces, Assets, Seats (all 12 Lords + 2 Comune): **OK** (exact match).
- Vassal rosters (names, service ratings, forces, muster dice 3/3/4/4/5): **OK**.
- Podestà set {Firenze, Arezzo, Colle, Lucca, Siena, Pisa}; Commanders
  {Firenze, Siena}: **OK**.
- Altopascio set-aside special vassal present in data: **OK**.
- CtA Comune Sestieri/Terzi auto-muster WITHOUT rolling (3.5.3 step 3): **OK**
  (matches "AS DESIRED, WITHOUT ROLLING").

### CONF-001 (FIX, SMOKE-Inferno-073) — Sestieri/Terzi later Muster (3.4.2)
The reference (Call to Arms "LATER MUSTER outside Call to Arms - 3.4.2") allows
a Commander INSIDE his Leading City to Muster a Ready Sestiere/Terzo via a
regular Levy Lordship action, rolling a die (<= the vassal's Muster die musters
it; higher wastes the action). The harness rejected ALL special-vassal musters
via `_h_levy_muster_vassal`. Carroccio still cannot be Mustered this way (CtA
only), nor Altopascio (Tau Company only). [fixed below]

---

## B. Strongholds / Map / Scenarios (vs Battle&Storm, Map, Scenario refs)

### Strongholds (Battle&Storm Sec.14) — **OK**
Castle (Size 1 / Walls 1-4 / Garrison 1 Men-at-Arms,1 Militia,1 Cavalieri /
Surrender 1d), Town (Size 2 / 2,2,2 / 2d), City (Size 3 / 3,3,3 / 3d),
Outpost (Size 0). All match exactly. Stronghold Value == Size (VP 1/2/3).

### Map (Map ref) — **OK**
- 60 Locales = 57 Strongholds + 3 Outposts: matches the ref header exactly.
- Locale types: Outposts (3) {Lombardia-Bologna E/W, Orvieto}, Cities (5)
  {Lucca, Firenze, Pisa, Siena, Arezzo} — matches the detailed "CITIES (5)"
  section (the abbreviated 3-city summary line is not authoritative).
- Ways: edge-by-edge diff against the Map ref's connection lists — every code
  edge (91) is in the ref and vice-versa (the only initial mismatches were a
  hyphen-parsing artifact on "Lombardia-Bologna"). Structure clean: symmetric,
  no self-loops, no duplicate edges, no isolated locales.
- Ports (8): {Firenze, Pisa, San Miniato, Pontedera, Empoli, Montelupo,
  Borgo Livorno, Castiglione della Pescaia} — exact match.

### Scenarios (Scenario ref) — **OK**
Start/end boxes match: A box1->end3, B box4->end9, C box6->end9, D box9->end12,
E box12->end15, F (Exhaustion, no fixed end). Running VP initialised from board
markers (SMOKE-069). Scenario special rules (Sudden Campaign A, Reprisal War B,
Maremma War C, Resistance E doubling, Exhaustion F) wired (SMOKE-035/036/038/...).

---

## Units (vs Inferno_Forces_and_Strongholds.md) — **OK**

Every unit's Battle/Storm strike values, Archery (kind + gating), and Armor
range cross-checked exactly:
  Ritter (B2/S1, armor 1-4, KQ); Cavalieri (1/1, 1-3, KQ, Feditori/ArmyReserve);
  Berrovieri (B0.5 / S-def 0.5 / S-atk 1, 1-2, double Ravage); Light Horse
  (0.5 all, armor 1); Men-at-Arms (melee 1, ½ Crossbow when Garrison/Balestre
  Grosse, 1-3); Armigieri (melee 1, full Crossbow when Garrison/Balestrieri,
  1-2 / 1-4 Palvesari); Militia (melee 1, x1 Archery when Garrison/Arcieri,
  x1.5 Luceria, armor 1); Villici (0.5 all, no armor, auto-removed if hit).

---

## C. Procedural rules (vs Rules Reference / Battle&Storm / Commands / Siege / SoP)

Concrete numeric/logic rules cross-checked against source:
- **Feed (4.8.1)**: 1-6 -> 1, 7-12 -> 2, 13+ -> 3 Provender/Loot — **OK**.
- **Fealty Muster (3.4.1)**: success iff die <= F rating — **OK**.
- **Surrender (4.5.1)**: roll Stronghold-Value dice; Surrender iff EACH <=
  (Siege markers + Ravage markers) — **OK**.
- **Laden / movement (4.3.2/4.3.3)**: Prov > 2*Carts may-not-move; Laden cost 2;
  Unladen first Road March 0 — **OK** (SMOKE-048/051/060).
- **Combat strike resolution (4.4.2/4.5.2)**: base Lord-unit Archery = 0 in
  Battle (fires only via Garrison or Capability); Capability strike modifiers
  numerically exact — Feditori (+1/Cavalieri, cap 4 Guelph / 3 Ghib, R1-2),
  Army Reserve (+1/Cavalieri, R3+, eligible Lords), Arcieri (Militia x1),
  Luceria (<=3 Militia x1.5), Balestrieri (<=3 Armigieri x1), Balestre Grosse
  (Men-at-Arms x0.5, Storm) — **OK**.
- **Garrison strike profiles (Battle&Storm)**: composition exact; Storm garrison
  Foot units fire Melee+Archery — **OK** (composition), strike resolver wired.
- **SoP step order, Levy 3.1-3.5, Command actions 4.3-4.7, Revolt 1.4, FPD 4.8,
  End-Campaign 4.9**: structure verified via the 11 OUTSTANDING rule fixes
  (SMOKE-047..055), the FPD/Disband fixes (057/058/070/071), CtA/Treachery
  reachability (059/072), and the 40-round smoke campaigns (replay-deterministic,
  schema-valid, conservation-clean).

### CONF-001 (FIX, SMOKE-073) — Sestieri/Terzi later Muster (3.4.2)
See section A. Commander-in-Leading-City later Muster of a Comune Sestiere/Terzo
with the Muster-die roll now implemented; Carroccio remains CtA-only.

**Depth note:** the deepest combat micro-interactions (Crossbow select-target +
-2-Armor hit assignment, flanking target selection, Sudden-Clash R1 reorder) are
implemented with rule citations and exercised by the test suite + smoke
campaigns, but were spot-checked rather than independently re-derived line-by-line.

---

## D. Arts-of-War card effects (vs Inferno_Arts_of_War_Reference.txt)

- All 52 cards have an implemented Event AND Capability (Audit of v2.7).
- The 24 distinct Capability *names* are each consumed by game logic
  (`_lord_has_capability` + bespoke hooks); the combat Capability numerics are
  verified exact (above).
- v2.7 non-combat Capabilities (Gualdana double-Ravage, Masnadieri 0-action
  Ravage, La Cavallata, Costruttori, Guastatori Siege+2 / besieged Pass->Bypass,
  War Engineers any-size / reduce-to-1, Reinforced Walls Tax->Walls+1,
  Sovrintendente Castle-Garrison swap, Tau Company Lordship+1 / free Altopascio)
  implemented directly from their reference entries.
- Scenario VP modifiers (E Resistance doubling, C Manfredi/S22 +3) applied at the
  5.1 final recompute, not the running track (SMOKE-069 design).

**Depth note:** per-card Event numerics were verified for the cards touched by
fixes and sampled across the rest; not every one of the 52 was independently
re-derived field-by-field.

---

## Summary
Data tables (Lords, Strongholds, Map, Scenarios, Units) and the concrete combat/
procedural numbers are **fully conformant** to the in-repo references. One
procedural gap found and fixed (CONF-001). Deepest combat micro-interactions and
some per-card Event numerics are implemented + tested but not exhaustively
re-derived — flagged above as the residual audit surface.


## E. Subsystem deep-audit (v3.6) — End-Campaign 4.9, economic Commands, Naval, Pursuit
Numeric microscope over the previously structural-only subsystems. CONFORMANT:
Feed/Grow/Repair/Waste/Reset, Scoring 5.x (incl. Scenario E doubling / C +3),
Forage/Supply/Tax/Ravage, Sail, and Pursuit (= Concede halving). FIXED two
Ransom (4.9.2) defects: recovery over-count (SMOKE-083) and Languish double
penalty (SMOKE-084). See SMOKE_TEST_FINDINGS.md v3.6.


## F. Capabilities / Battle / Call-to-Arms audit (v3.8)
Numeric microscope. CONFORMANT: all combat Capability strike numerics (Feditori
4/3, Army Reserve R3+, Luceria x1.5 cap 3, Arcieri, Balestrieri, Balestre
Grosse) and siege/storm Capabilities (Guastatori +2, War Engineers, Trebuchets,
Siege Towers — all name-driven); 6-step Battle initiative; Retreat service-shift
die; CtA triggers + Comune-without-rolling + Allies. FIXED: capability hook
mislabel / latent walls bug (SMOKE-085) and missing Scenario D Escalation CtA
rule (SMOKE-086). See SMOKE_TEST_FINDINGS.md v3.8.

## v4.0 — Illegal co-location class (Muster placement / Marker lifecycle / Retreat)
FIXED three independent routes to an illegal "opposing Lords co-located outside a
Stronghold" state, plus the missing invariant that had hidden them:
- SMOKE-Inferno-087: Muster Seat eligibility (3.4.1) + Besieged-Podesta Urban-Army
  inside placement (3.4 / CtA 3.5.2). Non-Podesta may not Muster onto an
  Enemy-occupied/Besieged/Ruins Seat; a Podesta at his Besieged Main Seat is placed
  INSIDE (Size-limited).
- SMOKE-Inferno-088: stale Siege/Bypass marker sweep on every departure path
  (4.3.5) — Stronghold free of Enemy Lords ⇒ remove markers, un-flag defenders.
- SMOKE-Inferno-090: Retreat relocates the loser to a legal adjacent Locale
  (4.4.3 / Battle&Storm 11.2), with Approach-Way / Marching-Attacker-origin /
  Enemy-Stronghold / no-Sail constraints; no legal target ⇒ Removed (4.4.5).
- SMOKE-Inferno-089: `assert_no_colocated_enemies` added to `check_all_invariants`.
See SMOKE_TEST_FINDINGS.md v4.0. Full suite 582 pass.

## v4.1 — Door C completeness (Commander-to-Arms / Comune)
FIXED two further on-board placement paths missed in v4.0 (SMOKE-Inferno-091):
`_h_cta_commander_arms` now places a Commander Mustered into a Besieged Leading
City INSIDE the Stronghold (3.5.2 Urban Army) via the shared
`muster_seat_status` gate; the Comune (`_h_cta_comune_setup`) inherits the
Commander's besieged-inside flag (3.5.3). Known cold-path follow-up: Sally
besieger-loss relocation (4.5.3/11.2), not reachable via gameplay (no surfaced
Sally Concede). Full suite 585 pass.

## v4.2 — Validated palette + symmetry audit (SMOKE-092)
Added `enumerate_legal_validated` (probe-and-filter agent palette with structured
over-enumeration diagnostics). Audit: over-enumeration NONE (1,188 probed steps);
51/58 handlers menu-reachable. Documented two under-enumeration gaps for a
pure-menu agent (Held Events `play_event`; `cmd_play_ambush`), both with working
alternate channels, deferred pending per-card-timing / mid-Approach enumeration
work. Negative enumerator tests added for the Muster-Seat gate. Full suite 591 pass.

## v4.3 — Sally retreat + event window-guard + Ambush enumeration
- SMOKE-Inferno-093: Sally losing Besiegers now Retreat (4.5.3/11.2) via the
  shared `_retreat_destination`, not left co-located.
- SMOKE-Inferno-094: `_h_play_event` now gates combat-window Held Events to their
  play window (`_HOLD_EVENT_WINDOW`); wrong-window plays raise NO_PLAY_WINDOW.
- SMOKE-Inferno-095: F1/S1 Ambush + `cmd_play_ambush` are enumerated for the
  attacker in the Approach window; Avoid no longer offered to an ambush-pinned
  Lord. Remaining: menu enumeration of battle/besiege-window Holds (guarded +
  classified, safe follow-up). Full suite 596 pass.

## v4.5 — Garrison-only Storm (SMOKE-097)
FIXED: a Storm against a Stronghold held by its Garrison alone (no Lord inside)
was a no-op the attacker auto-lost (empty hit_log). `_resolve_storm_step` now
engages the Garrison's strikes and Hit-absorption without requiring a defending
Lord (4.5.2 / Siege Sec. 6), so such Strongholds fight and are Sackable. Found
by a ChatGPT Scenario-F self-play. Full suite 599 pass.

## v4.7 — Feed/Moved-Fought scope (SMOKE-099)
FIXED the Nevsky-§8 starvation-spiral class in Inferno: Forage, Ravage, La
Cavallata, Guastatori-Pass, War-Engineers-reduce, and Costruttori wrongly marked
Moved/Fought, forcing an unnecessary Feed. Now only March/Avoid/Sail/Encamp/
Battle/Storm/Siege mark it (Commands 4.6/4.8; 606-607/609). Guard test ensures no
non-movement handler reintroduces the mark. Full suite 604 pass.

## v4.8 — Deep combat-fidelity audit (Crossbow MIN-1 fix + Sudden Clash gaps)

Independent re-derivation of the combat micro-interactions previously marked
"spot-checked, not re-derived." Cross-checked against Battle&Storm 10.2/10.3,
the Forces table, and the Official Errata.

### CONF-002 (FIX) — Crossbow "-2 Armor, MIN 1" floor
Battle&Storm 10.3: "Crossbow Hits roll vs Armor reduced by -2, **MIN 1**." The
hit-absorption (`_absorb_hits`) and garrison-absorption resolvers reduced the
target's Protection range by slicing off the top 2 values via
`prot[:max(0, len(prot) - penalty)]`. For units with Armor 1 (Light Horse,
Militia) or Armor 1-2 (Berrovieri, Armigieri) this yields an **empty** range, so
a single Crossbow Hit removed the unit on ANY die face — violating the MIN-1
floor (the unit should still roll vs Armor 1 and survive on a "1"). Fixed to
`max(1, len(prot) - penalty)` at both sites; Cavalieri (1-1), Men-at-Arms (1-1)
and Ritter (1-2) behaviour is unchanged. Guard: `tests/test_v46_crossbow_min1.py`.

### CONF-003 (FIX) — Sudden Clash (F4/S4) "select targets" + named-Lord precedence
Battle&Storm 10.2 / cards F4,S4: the named Lord's Round-1 Horse Melee "selects
its targets" (striking side chooses which enemy unit absorbs each Hit, like
Crossbow Hits but WITHOUT the -2 Armor) and only THAT Lord's Horse Melee
precedes the Archery. Previously the engine had the precedence right (defender's
named Lord before attacker's) but (a) routed the Hits through the normal
defender-favourable absorption order — no select-target — and (b) applied the
precedence to the whole side's `*_horse_melee` step rather than the named Lord
only. Fixed: `_absorb_hits` gains a `select_hits` mode (valuable-first order at
FULL Armor, no -2); `_resolve_step` gains `only_slots`/`exclude_slots`/
`select_target`; the Round-1 loop resolves ONLY the named Lord's slot early with
select-target and excludes that one slot from the normal Horse-Melee step (the
rest of the side's Horse still strikes at the normal time). Guard:
`tests/test_v47_sudden_clash.py`.

### Re-verified conformant
Errata items: Repair = Town/City with 3-4 markers, Castles excluded (4.9.4);
Languish recovers Captured Knights only (4.9.2); Battle participants exclude
in-Stronghold Lords (4.4); Knights' Quarter captures only REMOVED Cavalieri/Ritter
on a 3-6 loss roll (4.4.4, with the two rule examples reproduced exactly).
Mixed-Archery rounding favours Crossbows (crossbow subset `ceil`'d, capped at
total). Plan size by season {7,6,7,4} and Astrologers (+1 Command on 1-2, first
Command card/Campaign) match source.

## v4.9 — Surface auto-resolved player choices (CPL 8.4 audit)

Audit pass for the project's own hard constraint (BRIEF: "Rules Accuracy Trumps
Simplification") and lesson CROSS_PROJECT_LESSONS 8.4 ("auto-resolved player
choices are silent fidelity bugs"). Most decision points were already surfaced
(Lord placement, flanking direction, concede on both sides in Battle/Sally,
reserve adds, pre-battle Avoid/Withdraw/Stand). Two were still auto-resolved and
are now opt-in, defaulting to the prior auto-behaviour (no outcome change unless
a consumer asserts a preference).

### CONF-004 (FIX) — Owner chooses which unit absorbs a non-select Hit
Battle&Storm 10.2: "the owner chooses units for any other (non-Select-Target)
Hits." `_absorb_hits` hard-coded cheapest-first (`NORMAL_ORDER`). Added
`BattleDecisionContext.decide_optional` (consumes a scripted decision only when
its type matches; a callback that returns no valid option falls back to the
default; otherwise default) and threaded `bdc` into `_absorb_hits` at the Battle/
Sally (`_resolve_step`) and Storm (`_resolve_storm_step`) sites. Crossbow and
Sudden-Clash Hits remain attacker-selected (valuable-first). Default = cheapest-
first, byte-identical. Guard: `tests/test_v48_owner_choices.py`.

### CONF-005 (FIX) — Post-battle Withdraw into a Friendly Stronghold
Battle&Storm 11.2: the losing side's Lords "must each (owner chooses for each)"
Retreat / Withdraw into a Friendly Stronghold at the Battle Locale (if Defending
at one, <= Stronghold Size) / be Removed. `_apply_post_battle` only honoured a
pre-existing `in_stronghold` flag, so an open-field Lord defending at his own
Stronghold who lost was always Retreated — the Withdraw option was never offered.
Now a consumer may list lord_ids in `meta.post_battle_withdraw`; eligible electors
(`_can_withdraw_into_stronghold`, capped by `_withdraw_capacity` = Stronghold
Size) go INSIDE (keep Assets, no Service shift). Default (absent) = Retreat,
unchanged. Verified the resulting besieged-style co-location passes
`assert_no_colocated_enemies`.

## v4.10 — Storm Attacker armored-first (FIX) + Battle/Sally striker Select-Target

Follow-up to the CPL-8.4 pass, deciding the Crossbow/Sudden-Clash striker choice
only where strictly rules-compliant.

### CONF-006 (FIX) — Hits vs the Storm Attacker: Armored before Unarmored
Battle&Storm 10.2 ("STORM ATTACK: Armored units must absorb before Unarmored"),
reinforced at B&S 297-298 ("Hits against the Storm ATTACKER must select ARMORED
units before Unarmored units, regardless of who is choosing what") and 744,
Commands 210, Rules Ref 294. The Storm path absorbed Attacker Hits through the
default cheap/Unarmored-first `NORMAL_ORDER`, so the Attacker shed Light Horse /
Militia / Villici before his Armored units — a latent rules violation independent
of any player choice. `_absorb_hits` now takes `armored_first`; `_resolve_storm_step`
sets it whenever the target is the Attacker, forcing an Armored-first order
(cheapest-armored-first within the group) with NO owner choice ("regardless of who
is choosing"). Defender absorption (garrison-first then owner choice) is unchanged.
Verified end-to-end across 39 seeds: the Storm Attacker never sheds an Unarmored
unit while an Armored one remains. Guard: `tests/test_v49_storm_armored_select.py`.

### CONF-007 (FIX) — Striker Select-Target surfaced in Battle/Sally only
Battle&Storm 10.2: Crossbow and Sudden-Clash Hits let the STRIKING side choose
which Enemy unit takes each such Hit. In Battle and Sally this is a FREE choice
(no Armored-first constraint), so it is now surfaced via
`decide_optional("select_target_unit", striker_side, ...)` (`allow_striker_select`
on `_resolve_step`), defaulting to most-valuable-first — unchanged unless a
consumer opts in. It is deliberately NOT surfaced in Storm: Hits vs the Attacker
are forced Armored-first (CONF-006), and Hits vs the Defender route through the
garrison-first / Walls machinery — neither is a clean free choice, so surfacing
there would not be strictly rules-compliant.

## v6.0 — Arts-of-War per-card numeric re-derivation (closes the "Depth note")

Full card-by-card re-derivation of all 52 AoW Event/Capability numerics vs
`reference/Inferno_Arts_of_War_Reference.txt` — the residual surface the Section
C/D Depth notes flagged ("per-card Event numerics verified for the cards touched
by fixes and sampled across the rest"). 52/52 located; all combat/economic
numerics re-confirmed exact. Two defects fixed:

### CONF-008 (FIX) — F14 Provenzano adverse-shift direction
AoW F14 Tips: "shift Provenzano's cylinder **right** or Service marker **left**."
Provenzano is a Ghibelline, so the shift is adverse to the Guelph who plays F14.
The handler shifted his cylinder **left** (cur−2), advancing the enemy Lord's
arrival. Fixed to cylinder RIGHT (cur+2) / Service LEFT, mirroring the
correctly-implemented F18 Grosseto and F19 Volterra. Guard:
`tests/test_v60_conf008_009.py`.

### CONF-009 (FIX) — F2/S2 Betrayals "OR" + phantom Revolt roll
AoW F2: per Besieged Stronghold, roll Revolt **OR** add 1 Treachery (choices sum
to the Siege count). The handler rolled a die AND added a Treachery on every
Stronghold, and the roll applied no Revolt outcome (logged, discarded). Refactored
both copies onto `_betrayals(...)`: default all-Treachery (deterministic, same
realized count, no phantom roll); `revolt_count=k` rolls `k` real Revolts via
`revolt.trigger_revolts` + `sieges−k` Treachery. Guard:
`tests/test_v60_conf008_009.py`.

### Investigated, ruled NOT defects
- **F20 / S14 `event_kind`:** `hold` is correct for both. `event_kind` only
  auto-invokes the handler for `immediate`; `hold` routes through the play-event
  window (how S14's handler sets its `this_campaign` flag). F20's "before Feed"
  timing would be wrong as `immediate` (fires at Levy-draw); the S20 mirror's
  "Hold:" + "works the same as F20" Tips mark the missing F20 "Hold:" as a digest
  artifact.
- **Battle&Storm digest Forces table:** lists Light Horse "Archery ×1/2" and
  Militia melee "×1/2"; both contradict the authoritative
  `Inferno_Forces_and_Strongholds.md` (Light Horse no Archery; Militia melee ×1).
  The engine follows the authoritative source — digest typos only.

**Verification:** suite 700 pass (8 new).

## v6.1 — Revolt subsystem (matrix + 1.4.1–1.4.4)

Full audit of `revolt.py` vs `INFERNO_Revolt_Tables_Reference.txt` + RoP 1.4.
Both 6×6 matrices byte-perfect (72/72 cells; all Locales valid; SUBMISSION 4/6).
Dice convention, table selection, REBELLION presence (cylinder/marker-only),
1.4.4 switch + Exiles, and economic Tax all conformant.

### CONF-010 (FIX) — SUBMISSION requires a MARKED Enemy target
RoP 1.4.2: SUBMISSION targets a Stronghold "marked with Enemy Allegiance (only,
not printed Allegiance)." The code reused `is_eligible_for_revolt`, which accepts
printed-enemy via `_effective_allegiance` — so un-marked printed-enemy Strongholds
(53/57 at start) were illegal-but-offered SUBMISSION flips. Added
`_is_marked_with_allegiance` gate to the SUBMISSION branch only (REBELLION
correctly stays printed-eligible per 1.4.1). Guard:
`tests/test_v61_conf010_submission.py`.

## v6.4 — Siege subsystem (4.3.4-.6 / 4.5.1)

Full audit vs Inferno_Siege.txt + RoP. Siegeworks, Surrender threshold, Besiege/
Bypass/Encamp/Sortie, Sally raid, marker removal, Repair erosion all conformant.

### CONF-011 (FIX) — Surrender Allegiance flip + VP
RoP 4.5.1 sets the Stronghold to the Besieger's Allegiance "either placing markers
equal to Value OR removing markers already there; adjust Victory 5.1." The code
always placed `size` markers and did ±size VP — wrong on a Besieger-printed
Stronghold (should revert, place 0; was inflating final VP) and when the enemy
held <size markers (over-subtracted the running VP behind the 4-VP CtA trigger).
Now routed through `revolt.apply_allegiance_switch`. Surrender does NOT trigger
1.4.4 Exiles (Revolt-specific). Guard: `tests/test_v64_conf011_surrender_vp.py`.

### CONF-012 (FIX) — Encamp clears all co-located Bypassers
Encamp cleared `bypassing` only on the active Lord; a co-located Bypasser was left
flagged Bypassing a now-Besieged Locale. Now clears all. Same guard file.
