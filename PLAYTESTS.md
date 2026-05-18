# Playtest Log — Inferno Harness

Issues, anomalies, and findings surfaced during playtests that require
user interpretation rather than a code fix.

A playtest issue belongs here when:
- A scenario plays out in a way that suggests a rule is implemented
  incorrectly, but the implementation traces to a citation.
- A combination of rules produces an outcome the user wants to
  inspect before deciding whether it's a bug or correct behavior.
- An end-to-end run surfaces a state the consultation chain cannot
  resolve.

Format per entry:
- PLAY-NNN sequential ID.
- Scenario and seed.
- Step that produced the issue (`new` / `do` action / `state` view).
- Observed behavior.
- Expected behavior per the user (filled in after adjudication).
- Resolution: code fix commit hash, Q-NNN, or [HOUSE RULE].

---

(no playtest issues yet)
