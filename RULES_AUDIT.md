# Full Rules Audit — Inferno Harness

A systematic, subsystem-by-subsystem cross-check of the implementation against
every file in `reference/` (the authoritative Rules-of-Play / Errata distillations)
and the in-repo data. Programmatic diffs were used for all data tables.

## Result summary
13 subsystems audited. The data model is **exact** to the references; five
rules-logic gaps were found and **all five are now fixed** (A1–A5; A5 verified
against the full Rules of Play PDF). 639 tests pass; self-play anomaly-free across all six scenarios.

## Conformant (verified this pass)
| Subsystem | Method | Result |
|---|---|---|
| Lords (14 mats) | programmatic field diff | exact — ratings/forces/assets/vassals (service+forces+muster dice), Comune special vassals, Altopascio, Podestà/Commander flags |
| Map | edge-set diff vs adjacency list | exact — 60 locales (5/16/36/3), 8 ports, 91 Ways w/ Road/Track types, no self-loops/dupes/isolated |
| Forces & Strongholds | field diff | exact — 8 unit profiles; garrisons (Castle Militia vs Town/City Armigieri), sizes, surrender dice, walls |
| Scenarios A–F | field diff + effect checks | exact — start/end boxes, mustered Lords, special rules + effects (Reprisal S18/19/20, Spoils Giordano 2 Coin, Maremma line, Resistance) |
| Sequence of Play | structural | Levy 3.1–3.5, Campaign steps, End-Campaign 4.9.1–4.9.6; Pay (Podestà 2/box, Loot friendly+siege-free) |
| Commands | numeric | March speed 0/1/2 + Laden 4.3.2; Forage season table; Ravage cost/gains/doubling/VP; Tax +1/+2; Sail ships 1/1/2; Supply own-Seat |
| Battle & Storm | order + numeric | 6-step / 4-step initiative; concede (both Battle/Sally, attacker-only Storm); pursuit halving; Spoils 11.3; crossbow MIN-1; sudden clash; armored-first |
| Siege | numeric | surrender-if-no-Lord-inside, dice=Size, marker needs besiegers≥Size, max 4, both Fought; Sally RAID→1; Repair Town/City 3–4 |
| Call to Arms | structural + data | triggers (VP-lag/War/Treasurers), 4 War events, 4 substeps, Allies modes, scenario restrictions |
| Revolt & Treachery | full table diff | all 72 cells (both 6×6 tables) exact; counts 3×/1× Podestà, Value for Surrender/Sack; Comune-no-trigger |
| Arts of War (52) | names + numerics | 52 IDs, all capability names (0 mismatches), 4 War events, combat-capability numerics |
| Scoring / Victory | numeric | VP sources (Allegiance=Size markers, Ruins/Ravaged 1/2, Carroccio 2), cap 17.5, end-scenario more-VP/tie=draw, E/C modifiers |

## Findings

### Fixed this pass
- **A1 — Relief Sally combined-loss now reduces Siege to ONE (4.4.1).** The regular
  Sally applied the RAID reduce-to-1; the Relief-Sally path (Approach →
  `_apply_post_battle`) withdrew the sallying Lords but left the Siege markers.
- **A2 — F23 Via Francigena now excludes Guido Guerra & Orvieto.** The +1 Command was
  granted to any Guelph with the side-wide capability; the card restricts it to
  Firenze/Arezzo/Lucca/Colle.
- **A3 — Removed inert `track_as_road` flag from the F23 registration** (belongs to
  F5/S5 Road Works; never consumed — cosmetic).
- **A5 — Campaign Victory sudden-death (5.2) implemented.** Verified against the full
  Rules of Play (sources/Inferno_Rules_of_Play.pdf, §5.2): "If at any moment during
  Campaign (4.0) a side has no Mustered Lords on the map, the game ends immediately—
  the other side wins regardless of VP." A Lord disbanded to the Calendar is off the
  map (status != mustered) and correctly does NOT count — so the strict reading is
  confirmed. The check is gated to the whole Campaign phase (`phase=="campaign"`,
  including End Campaign 4.9) to match "any moment during Campaign," and never fires
  during Levy (before Muster).

### Fixed this pass (cont.)
- **A4 — First-Levy capability deployment now respects This-Lord scope (3.1.2).** [SIGNIFICANT]
  The first-Levy draw handler hard-codes `scope="side_wide"` for **every** drawn
  Capability, ignoring the card's `this_lord` flag. A "This Lord" Capability (Feditori,
  Astrologers, War Engineers, Balestrieri, …) must tuck at ONE Mustered Lord's mat
  (max 2/mat; discard if none eligible). Demonstrated: an S6 Feditori deployed this way
  returns `True` from `_lord_has_capability` for **all four** Ghibelline Lords (should
  be one) and bypasses the Ghib Feditori eligibility set. Net: This-Lord
  combat/economic capabilities drawn in the first Levy apply side-wide rather than to a
  single Lord. A correct fix surfaces the target-Lord choice (No-Agent) using the card's
  `this_lord` flag + per-card "Lords:" eligibility, discarding when no eligible Mustered
  Lord exists. (The 3.4.4 Levy-Capability path already takes a scope arg and is fine.)
