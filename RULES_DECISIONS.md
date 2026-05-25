# Rules Decisions — Inferno Harness

User adjudications of rules ambiguities and house rules. Entries are
**append-only**: never delete a decision; supersede with a follow-up
entry if a prior ruling is revised.

Each entry should record:
- The original Q-NNN context and options.
- The user's adjudication.
- Any rules citation provided.
- The commit hash where the answer is encoded.
- `[HOUSE RULE]` tag if the rules are silent and the user is declaring
  a policy.

---

## Q-001 — Season classification of Aug-Sep and Feb-Mar calendar boxes

**Resolved:** Option A.

**Adjudication:** Inferno Rules of Play 4.9.1 directly enumerates Grow
turns as "boxes 2, 5, 8, 11, and 14" labelled "April-May late-Spring" and
"October-November Autumn." Since Grow fires on every Spring and every
Autumn turn, the enumerated set is exhaustive: **Spring = Apr-May only**
(boxes 2, 8, 14) and **Autumn = Oct-Nov only** (boxes 5, 11). The
remaining month-pairs are forced:
  - Feb-Mar (boxes 1, 7, 13)   = Winter
  - Jun-Jul (boxes 3, 9, 15)   = Summer
  - Aug-Sep (boxes 4, 10, 16)  = Summer
  - Dec-Jan (boxes 6, 12)      = Winter

**Citation:** Rules of Play 4.9.1 (direct enumeration of Grow turns).

**Code state:** `SEASON_BY_BOX` in `src/inferno/static_data.py` was already
written to Option A; no code change required. The consultation-log
note that called RoP "not yet consulted page-by-page" is superseded —
4.9.1 is itself the disambiguator, not only the physical-calendar
colour bands.

**Encoded in commit:** `b6e5fdc` (Phase 3a: Plan + simple Commands + FPD;
the commit that introduced `SEASON_BY_BOX` and `PLAN_SIZE_BY_SEASON`).

---

## Q-002 — Revolt Table "crossed-out" cells: no-revolt or Submission?

**Context:** Encoding the physical Revolt Tables (1.4.2) into the
harness from the user-supplied `INFERNO_Revolt_Tables_Reference.txt`.
The reference's initial draft labeled 10 cells (Table 1 col-1 rows 3–6;
Table 2 col-6 rows 1–6) as "[NO REVOLT] = crossed-out faction shield
(no revolt possible)" and showed no Submission cells. RoP 1.4.2,
however, describes a SUBMISSION result ("if the table result shows an
'X' over an Allegiance marker, the rolling side must if able select a
Stronghold marked with Enemy Allegiance ... at or adjacent to which the
rolling side has a Lord cylinder; it Revolts").

**What was ambiguous:** Whether those 10 cells are no-ops or are the
RoP 1.4.2 Submission result.

**Resolved (2026-05-20):** They are **Submission** results. "No revolt
should mean a submission result." The repo reference
(`reference/INFERNO_Revolt_Tables_Reference.txt`) was corrected
accordingly (RECONCILIATION NOTE G), and the harness encodes those
cells as a player-choice Submission flip, not a no-op.

**Companion ruling:** All revolt player-choices — the Submission target,
the Rebellion "already-Friendly" adjacent-Stronghold fallback (≤ Value,
eligible), and the 1.4.4 Exiles cylinder/Service slides — are **surfaced
as decisions** (consumer/LLM supplies the choice via args); the harness
never auto-selects among genuine alternatives, per the No-Agent
constraint.

**Citation:** Rules of Play 1.4.2 (Rebellion / Submission), 1.4.4
(Switching Allegiance + Exiles).

**Encoded in commit:** (v1.9 — src/inferno/revolt.py + trigger wiring).

## SMOKE-Inferno-099 — Moved/Fought scope (which actions trigger Feed, 4.6/4.8)
Decision: a Lord is marked Moved/Fought (and therefore must Feed at end-of-card)
ONLY by the canonical actions March, Avoid, Sail, Encamp, Battle, Storm, and
Siege. Authority: Inferno_Commands.txt 606-607 ("pure Supply/Forage/Ravage/Tax
with no movement does NOT mark a Lord Moved/Fought - so no Feed required") and
609 ("Siege action marks BOTH sides' Lords at the Locale"); plus the per-command
"Mark Moved/Fought" lines (March 57, Avoid 103, Encamp 148, Storm 223, Sail 382).

Explicitly named non-marking: Forage, Ravage, Tax, Supply (and La Cavallata,
which is a Ravage of an adjacent Outpost per F18/S18 / note 344).

Not explicitly named, ruled non-marking by the closed-list principle (none is a
March/Avoid/Sail/Encamp/Battle/Storm/Siege): Guastatori Pass (F2/S2 — a 4.7.7
Pass, "do nothing else"), War Engineers siege-reduction (F5/S5 — a Besieged
Lord's siege-work, not a besieger's Siege action), Costruttori Ruins repair
(F26/S26). NOTE: War Engineers is the least explicit of the three; flagged here
for review. A Besieged Lord is still marked Moved/Fought when the BESIEGER takes
a Siege action at the Locale (609) — independent of these capability actions.
