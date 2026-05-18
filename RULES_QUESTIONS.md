# Rules Questions — Inferno Harness

Open questions awaiting user adjudication. Follow the format defined in
[`BRIEF.md`](BRIEF.md) under "Question Format — REQUIRED fields".

Required fields per entry: Question ID, Context, Consultation log, What
is ambiguous, Options, Affects, Blocking?

When the user answers, MOVE the entry to `RULES_DECISIONS.md`.

---

(no open questions)

---

## Q-001 — Season classification of Aug-Sep and Feb-Mar calendar boxes

**Context:** Phase 3a encodes `SEASON_BY_BOX` in `static_data.py` to drive Plan
stack sizes per `PLAN_SIZE_BY_SEASON` (Spring 7, Summer 6, Autumn 7, Winter 4)
from Inferno_Sequence_of_Play.txt.

**Consultation log:**
1. Curated reference file: Inferno_Sequence_of_Play.txt section 4.1 PLAN
   explicitly tables Plan sizes per season but does not enumerate which
   month-pairs map to which season. The GROW rule (4.9.1) cites
   "late-Spring (April-May)" -> Spring and "Autumn (October-November)" ->
   Autumn, anchoring those two month-pairs.
2. Rules of Play: not yet consulted page-by-page; the Calendar in the
   physical game has color bands per season that disambiguate this.
3. Cross-references: not consulted.
4. Playbook examples: not consulted.
5. Official Errata: no entry on season classification.

**What is ambiguous:** Whether Aug-Sep (boxes 4, 10, 16) is Summer or Autumn,
and whether Feb-Mar (boxes 1, 7, 13) is Winter or Spring.

**Options:**
- Option A (currently in code): Aug-Sep = Summer; Feb-Mar = Winter. Yields
  the calendar Spring/Summer/Summer/Autumn/Winter/Winter pattern (boxes
  2-7 per year).
- Option B: Aug-Sep = Autumn; Feb-Mar = Spring. Yields Spring/Spring/
  Summer/Autumn/Autumn/Winter.

**Affects:** `src/inferno/static_data.py` `SEASON_BY_BOX`; Plan-stack sizing
(4.1); Forage seasonal die roll (4.7.1); Sail "no Winter" gate (4.7.3);
any other Season-gated rule that lands in Phase 3+.

**Blocking?** No. Phase 3a tests pin Plan sizes for the boxes the published
scenarios actually start at (boxes 1, 4, 6, 9, 12), which under both
options come out the same except box 4 (Summer vs Autumn) and box 1
(Winter vs Spring). Worth resolving before Phase 3b Battle lands so
Forage rolls and Sail gating are correctly seeded.
