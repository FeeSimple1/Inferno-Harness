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
