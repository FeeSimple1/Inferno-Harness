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
