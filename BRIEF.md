Inferno Harness — Project Specification

Goal
A Python harness for Inferno: Guelphs and Ghibellines in Tuscany,
1259–1262 (GMT Games, Levy & Campaign Series Volume III, Living
Rules 2023-04-10). The harness holds full game state, validates and
executes all rules-defined actions, runs Battle, Storm, and Sally
engagements automatically, rolls all dice, and exposes a structured
interface designed to be consumed by an LLM (Claude or ChatGPT)
playing one or both sides. The user supplies strategic judgment via
the LLM. The user adjudicates rules ambiguities surfaced during
development. The harness supplies everything else: state, rules
enforcement, mechanical resolution.

This is a private project. Code quality should be good enough for
the user to maintain, not for external readers.

Authoritative Sources (Priority Order)

1. Inferno_Official_Errata.txt — 10 April 2023. Overrides any
   conflict in the Rules of Play or other sources.
2. Inferno_Rules_of_Play.pdf — Living Rules dated 2023-04-10. The
   rules-authoritative source.
3. The curated reference .txt files in `reference/` (Arts of War,
   Battle and Storm, Call to Arms, Commands, Lords, Map, Rules
   Reference, Scenario, Sequence of Play, Siege, plus the combined
   Forces and Strongholds .md). These are designer-clarified
   distillations of the higher-priority sources and the FIRST stop
   for any question about card text, capability mechanics, or rule
   interpretation. The Tips paragraphs in the Arts of War Reference
   in particular contain designer clarifications that resolve most
   apparent ambiguities without further escalation. They are
   derivative — if a Tip ever contradicts the Rules of Play or
   Errata, the higher source wins, but in practice the Tips are
   extracted from designer commentary and the conflict will be
   apparent on careful reading.
4. Inferno_PLAYBOOK.pdf — Background Book: examples, design notes,
   historical context. NOT a rules source; useful only for
   clarifying examples and Arts of War notes (pp. 33–55).

PDFs in `sources/` ARE readable; treat them as ordinary inputs. Any
PDF-restriction language elsewhere is about external/web PDFs, not
the in-repo PDFs.

When sources conflict, higher priority wins. For Q-NNN consultation,
the FIRST step is always the relevant .txt reference file's section
(Battle and Storm, Siege, Commands, Arts of War Reference, etc.).
Skipping that step is a process bug. The .txt references are not
optional starting material — they are the canonical organized
answers.

Scope of Inquiry — Hard Constraint
This is a software project to encode a board game's rules. It is NOT
a historical research project. The game's setting in 13th-century
Tuscany — the Guelph–Ghibelline conflict, the cities of Firenze,
Siena, Pisa, Lucca, Arezzo, the figures of Provenzano Salvani,
Farinata, Manfredi — is theme, not subject matter.

Sources you may consult

The repo's reference .txt files.
The repo's PDFs (Rules of Play, Playbook).
Standard Python documentation, language references, and library
docs needed to write the code.
Files in the repo that the user has placed there.

Sources you may NOT consult without explicit user instruction

Wikipedia, encyclopedias, or any general-knowledge reference on the
historical period, persons, places, battles, or events.
Academic or popular history sources on the Guelph–Ghibelline
struggles, the Battle of Montaperti, the figures the game depicts —
even when the rulebook references them.
Other GMT board games or board game databases (BoardGameGeek,
Consimworld) for comparative rules interpretation. Particularly:
do NOT consult Nevsky or Almoravid rules to infer Inferno rules.
Volume III has its own rule set with explicit changes from Volume I
and II (see "Summary of Rules Changes from Nevsky" and "Summary of
Rules Changes from Almoravid" on pp. 2–3 of the RoP).
Your own pre-existing knowledge of Inferno or its themes when that
knowledge comes from outside the repo files. If you find yourself
"remembering" something about Inferno, treat that memory as if it
doesn't exist; consult the repo files instead.
Web searches of any kind related to the game's subject matter.

Why this matters
Proper names and identifiers (Provenzano, Farinata, Manfredi, Pisa
Podestà, Cavalieri, Berrovieri, Armigieri, Sestieri, Terzi,
Carroccio, Altopascio) are tokens used by the rules to identify
specific game pieces with specific game stats. Their historical
referents are irrelevant to the harness. Encoding any historical
"fact" as game logic is a bug, not a feature. Examples of forbidden
reasoning:

"Historically Manfredi died at Benevento in 1266, so the harness
should remove him in a late-period scenario" — WRONG. The scenarios
specify when each Lord is in play; the rules override the history.
"The Battle of Montaperti happened near Siena, so Battle outcomes
there should have terrain modifiers" — WRONG. The rules specify
what modifiers exist; nothing else.
"Florentine cavalry historically used Y armor, so Cavalieri should
have better Protection" — WRONG. The Forces table specifies
Protection ranges (Cavalieri 1–3); that is the only source.

What to do when the rules reference history
The Rules of Play and Playbook contain historical commentary,
campaign history (Playbook pp. 19–32), design notes, and flavor
text. Read them only for the game-mechanical content they contain.
Ignore the historical claims. If a Design Note explains the
rationale for a rule alongside the rule itself, the rule is the
input; the design rationale is not.

What to do if you think you need historical context to resolve an ambiguity
You don't. If a rule is ambiguous, the resolution path is the
consultation chain (below), then the user. Historical "what actually
happened" is never an input. If you find yourself reaching for
context outside the repo to formulate or resolve a question, that
is itself a signal the question needs to go to the user. Do not
fill in the gap from general knowledge.

Names and identifiers
You may and should use proper names from the game (Lords, Vassals,
Locales, Capabilities, Strongholds) for state tracking, code
identifiers, file names, comments, and user-facing displays. Use
them exactly as the rules use them. Do not annotate them with
historical context, do not gloss them, do not Anglicize (use
"Firenze" not "Florence"; "Cavalieri" not "knights"; "Podestà" with
the accent; "Comune" with one m for the Commander's second mat
versus "Commune" with two m's for the vassal type — they are
distinct game tokens, use them as written).

Card prefixes follow the printed convention: **F** for Guelph cards
(F1–F26 Events / F1–F26 Capabilities) and **S** for Ghibelline
cards (S1–S26 Events / S1–S26 Capabilities). Use these prefixes in
identifiers and tests.

Rules Accuracy Trumps Simplification — HARD CONSTRAINT
Where the rules are clear, the harness MUST implement them
faithfully. Simplifications, approximations, "Phase N+ deferrals",
convenience shortcuts, and GUESSES are NOT acceptable when the rules
are explicit about a behavior. The harness must follow the rules. It
must never guess, never approximate, and never quietly substitute a
placeholder for a mechanic it cannot fully resolve.

The only acceptable reasons to depart from the rules are:
  1. The rules are ambiguous (-> follow the Ambiguity Policy / Q-NNN
     consultation chain below).
  2. The user has explicitly adjudicated a deviation (recorded in
     RULES_DECISIONS.md as [HOUSE RULE]).

Reasons that are NOT acceptable:
  - "Easier to implement this way."
  - "Phase N is just a stub; Phase N+1 will fix it."
  - "Most games won't hit this case."
  - "The simplification is conservative / lenient."
  - "I will guess / approximate / use a sensible default for now."
  - "The exact value isn't in the references, so I'll infer it."

Missing data is a BLOCKING question, not a license to guess — HARD RULE
If a rule, value, table, or chart required to implement a mechanic
faithfully is NOT present in the available sources (Errata, Rules of
Play, the curated reference .txt files, the in-repo PDFs), you MUST:
  a. Log it as a Q-NNN in RULES_QUESTIONS.md, marked Blocking, naming
     exactly what datum is missing and where it physically lives
     (e.g. "the Revolt Table die->Locale grid printed on the board").
  b. Make the affected mechanic refuse to run (raise IllegalAction
     with a clear code) rather than silently approximate, abstract to
     "eligibility only", or fabricate a threshold/probability.
  c. Surface the question to the user before merge.
Inventing a stand-in (a "conservative" carry value, an eligibility
gate that replaces a die-roll, a best-guess garrison composition) is
a rules-fidelity bug even if it never crashes and even if it is the
"sensible" choice. Silent plausibility is the most dangerous failure
mode: it passes tests and ships a wrong rule.

When implementing a feature, if the chosen approach diverges from
the rules in any measurable way, the divergence MUST be either:
  a. Fixed in the same PR before merge.
  b. Logged as a Q-NNN in RULES_QUESTIONS.md and surfaced to the
     user before merge.

Code comments that say "simplified", "approximated", "abstracted",
"conservative", "assume", "for now", "best guess", "deferred", or
similar are flags for audit. Each must trace to either a Q-NNN, a
[HOUSE RULE] decision, or a future-phase commitment with an explicit
issue tracking it. Before every merge, grep the source for these
hedge-words; any hit without such a trace is a defect to fix or log,
not to ship.

Ambiguity Policy
The harness encodes rules deterministically. Every rule encoded in
code must trace to a source. The user is the sole authority on
rules interpretation when sources are silent or unclear.

Consultation Chain — REQUIRED before logging any question
When you encounter anything ambiguous, work through this chain in
order and document each step:

1. Curated reference file. Identify the most relevant .txt file
   (Battle and Storm for combat, Siege for the Bypass/Encamp/Sortie
   subsystem, Commands for Command actions, Arts of War Reference
   for card text and capability mechanics, Sequence of Play for
   phase flow, Call to Arms for the CtA subsystem, etc.) and read
   the relevant section IN FULL. The Tips paragraphs in the Arts of
   War Reference are designer-clarified text and resolve most
   apparent ambiguity about card mechanics on their own. If the
   answer is in the .txt reference, the consultation ends here and
   the question does not need to be logged.
2. Rules of Play, primary section. Find the rule section number
   cited in the reference file and read the full section in the
   PDF, plus any sub-sections.
3. Rules of Play, related sections. Use the Key Terms cross-
   references in the rulebook to locate any related sections. Read
   those too.
4. Playbook examples (pp. 6–18 Explanations of Play, plus the Arts
   of War Notes pp. 33–55). Search the Playbook for worked examples
   that might illustrate the case. Examples are not rules but they
   often resolve apparent ambiguity.
5. Official Errata. Check whether the case is addressed by the 10
   April 2023 erratum.

Only after all five steps have been performed and documented should
you log a question. If the consultation resolves the question,
encode the answer with a citation comment in the code and proceed.

Common process error: invoking PDF access concerns as a reason to
skip the .txt references. The .txt references are unrestricted in-
repo files and contain designer-clarified answers for most card-
text and capability-mechanics questions. Read them first.

Question Format — REQUIRED fields
Append questions to RULES_QUESTIONS.md. Each entry must contain:

Question ID — Q-NNN, sequential.
Context — what you were implementing when the question arose.
Consultation log — what you checked at each of the five steps
above, including section numbers and quoted text. Confirm
explicitly that no external/historical sources were consulted. If
a step was skipped, explain why.
What is ambiguous — specifically what the rules do not determine.
Options — at least two concrete possibilities, each with a brief
argument from the rules text for why a reader might choose it.
Affects — files, functions, tests, or scenarios that depend on
the answer.
Blocking? — whether other work can proceed without an answer.

Do not log a question without all seven fields. The discipline of
filling them in resolves a meaningful fraction of would-be
questions.

Decision Log
When the user answers a question, MOVE the entry from
RULES_QUESTIONS.md to RULES_DECISIONS.md, appending the user's
adjudication, any rules citation provided, and the commit hash
where the answer is encoded. Decisions are permanent — never
delete an entry from RULES_DECISIONS.md.

If the user marks a decision [HOUSE RULE] (rules silent on the
question), treat it as authoritative and cite it like any other
rule.

No Agent in the Harness — Hard Constraint
The harness encodes the rules and exposes state. It MUST NOT make
strategic decisions on the consumer's behalf. The LLM (or human)
consumer applies all strategic judgment. The harness's job is:

  - Maintain authoritative game state.
  - Enforce rules: actions either succeed and mutate state or
    raise IllegalAction with a code.
  - Surface state in forms the consumer can read efficiently
    (render_summary, lord_combat_summary, paths_from, etc.).
  - Enumerate legal moves with their mechanical effects.
  - Compute previews / forecasts on request (vp_forecast,
    battle_preview, storm_preview, siege_preview).

What the harness MUST NOT do:

  - Recommend specific actions ("Use when winrate < 30%").
  - Editorialise about strategic trade-offs ("loses tempo",
    "Trade losses now for...").
  - Pick decisions for the consumer (Reserve advance, Concede,
    Avoid Battle, Withdraw, Besiege vs Bypass, Encamp vs Depart
    vs Sortie, Plan ordering, Capability picks, Treachery
    targeting, etc.).
  - Run an internal agent that selects actions when the consumer
    hasn't.

Test fixtures under `tests/_playthrough_*.py` exercise the engine
by driving the harness with simple heuristic policies. Those
scripts ARE agents (necessarily — to stress-test the engine end-
to-end) but they are NOT part of the shipped harness. They live
in the test suite, are not in `src/inferno/`, and are excluded
from the package.

`STRATEGY_DIGEST.md` (top-level) is an advisory document the LLM
consumer MAY consult for tactical and strategic priors. It will
curate insights from the Playbook's "On Strategy" section (pp. 4–
6), the Background Book's Solitaire notes (p. 6), and this
project's smoke-driver findings. It is NOT loaded or parsed by the
harness; the LLM is free to apply, adapt, disagree with, or ignore
any of it. Adding strategy advice belongs in the digest, not in
the harness code.

If a comment, docstring, note field, or helper output in
src/inferno/ contains language like "Use when...", "should",
"recommend", "prefer", or any other prescription about WHEN to take
an action, that's a bug. The remedy is to replace the prescriptive
text with a description of the rule's mechanical effect and let the
consumer decide.

Architecture Requirements
The user does not require specific implementation choices, but the
harness must satisfy these constraints:

Language: Python 3.11+.
State representation: A single JSON file holds complete game
state. State files are portable across sessions. Loading a state
file fully reconstructs the game.
Determinism: Given a state file and an action, the resulting state
is deterministic except for dice. Dice use a seedable RNG; the
seed is stored in the state file.
Two interfaces:

A library API (Python functions/classes) for programmatic use.
A CLI that wraps the library, suitable for an LLM to call via
shell or for the user to run directly.


No graphical interface.

LLM-Consumer Interface — Required Capabilities
The harness must expose, at minimum:

new — Initialize a state file from a scenario. All six scenarios
(A through F) supported.
state — Render current state. Must support:

Summary mode — compact view fitting in ~500 tokens, sufficient
for an LLM to make routine decisions.
Verbose mode — full state.
Focused views — a single Lord's mat, a single Locale, the
Calendar, the deck composition.


legal-moves — Enumerate all legal actions for a given player in
the current phase. Each move includes its action grammar, costs,
prerequisites met, and a brief description with rule citation.
This is the primary interface an LLM uses to decide what to do.
do — Execute a submitted action. Validates against rules,
updates state, returns a structured result describing what
happened (including dice rolled, hits assigned, markers placed,
VP changes).
Errors include rule citations.
pending — When an action triggers a sub-decision (e.g., Approach:
each defender chooses Avoid/Withdraw/Stand; Besiege/Bypass at a
new Stronghold; Depart/Encamp/Sortie from Bypass), the harness
records the pending decision in the state file. pending returns
the current pending decisions and which player owes a response.
history — Return the last N actions and results, for context.
save / load — Explicit state persistence (in addition to
automatic state file updates).

Action Grammar
Actions are submitted as JSON. The action grammar is part of the
specification and must be documented in ACTIONS.md as it is
developed. Every action type has a schema; the harness rejects
malformed actions with a clear error.

Dice and Mechanical Resolution
The harness rolls all dice. The LLM never rolls. Every roll is
logged in the action result with the context (whose roll, against
what target, what happened). This is non-negotiable: it removes a
class of errors and makes the game auditable.

Inferno-specific dice contexts the harness MUST handle:
  - Battle/Storm/Sally Protection rolls (per-unit, color-coded by
    unit type, e.g., Cavalieri 1–3, Ritter 1–4, Berrovieri 1–2,
    Light Horse 1, Men-at-Arms 1–3, Armigieri 1–2 or 1–4 under
    Palvasari, Militia 1, Villici 0).
  - Walls rolls in Storm (Walls 1–4 base, modified by Siegeworks,
    Walls+1 Reinforced Walls, –2 Surprise, etc.).
  - Surrender rolls during Siege (one die per Stronghold Size; <=
    Siege+Ravage markers).
  - Revolt-table rolls following Disband, Surrender, Sack, or
    Betrayals.
  - Bribe rolls (per 4.7.6).
  - Any other rolls explicitly called for by a rule or card.

Two-Sided Play
The harness supports:

LLM plays one side, user plays the other.
LLM plays both sides (alternating activations).
Pure observer mode (state inspection only).

The harness does not need to know which player is the LLM; it just
exposes legal moves and validates submissions per the active
player.

Phasing
Each phase is a separate PR. Do not start the next phase until the
previous PR is merged by the user.

Phase 0: Project skeleton, JSON schema for state, scenario data
file stubs, basic CLI structure, test framework. No game logic
yet.
Phase 1: State model, scenario loader (all six: A Dolenti Note,
B In Far Vendetta, C Santafior Oscura, D Arbia Colorata in Rosso,
E Lasciate Ogne Speranza, F Di Sangue t'Empio), state display
(summary/verbose/focused), state command.
Phase 2: Levy phase mechanics — Pay (including Podestà 2-Coin/box
rule), Disband (3.3.1 Beyond Service Limit including Podestà 3x
Revolt/Treachery; 3.3.2 At Service Limit per Errata), Muster,
Vassal Levy (standard + advanced Vassal Service rule 3.4.2,
including Special Vassals: Sestieri, Terzi, Carroccio, Altopascio),
Transport Levy, Capability Levy, Call to Arms (3.5; requires a
"War" Event in play). legal-moves for Levy.
Phase 3a: Simple Commands — Tax (entire-card), Forage, Ravage,
Supply, Sail (Pisa Podestà only, 4.7.3), Pass. Feed/Pay/Disband
cycle (4.8). legal-moves for these.
Phase 3b: March with Approach decision tree (Avoid Battle,
Withdraw, Battle), Battle resolution including the three-position
Array with Flanking, Reposition (Advance + Center fill), six-step
Strike sequence, Concede/Pursuit, post-Battle Spoils and
Withdraw/Retreat.
Phase 3c: Besiege/Bypass at arrival (4.3.5), Depart/Encamp/Sortie
from Bypass (4.3.6), Siege command (entire-card, Surrender roll,
Siegeworks), Storm (4.5.2 including Storm-specific Reposition
capped at Stronghold Size, Walls rolls, Sack vs Surrender
outcomes, Ruins), Sally (4.5.3), Treachery cards (Treachery-Revolt
and Treachery-Bribe per 4.2.3 and 4.7.6).
Phase 4 (deferred): Per-card Arts of War effects (F1–F26 and S1–
S26 Events and Capabilities). Until Phase 4, cards are tracked as
data with effect text in a notes field; the user/LLM applies card
effects manually. The harness flags when a card in play would
affect a current action so the user knows to consider it.

Test Discipline
Every rule encoded in code must have at least one test. The test's
docstring cites the rule section. A rule without a test does not
exist in the harness.
`pytest -v` should produce a list of every rule the harness claims
to implement, organized by rule section.
End-to-end scenario tests exist for at least one full Levy +
Campaign turn of Scenario A by end of Phase 3a, and at least one
full Battle by end of Phase 3b.

Commit and PR Workflow

Small, focused commits with descriptive messages.
Each commit message references the rule section it implements OR
the question/decision it resolves.
One PR per phase (regular, not draft).
The user reviews and merges PRs. Cowork has the user's standing
authorization to push, pull, merge, and commit on its own
judgment (granted 2026-05-17); use that authority for routine
operations, but still surface phase PRs for user review before
considering a phase complete.
Branch naming: phase-N-short-description.

When to Ping the User
These are the only times you ping the user:

A new question batch is ready in RULES_QUESTIONS.md (don't ping
per question — let questions accumulate to a reasonable batch,
then ping).
A phase PR is ready for review.
A test is failing in a way the consultation chain cannot resolve.
A playtest issue logged in PLAYTESTS.md requires interpretation.

Outside these triggers, work autonomously. The user expects long
stretches of no contact.

Out of Scope

AI opponents, strategy advice, or playstyle tuning.
Graphical interface.
Networked / multi-user play.
Sharing or distribution; this is a private project.
Anything not directly serving "run an Inferno game with state
persistence, rules enforcement, and an LLM-friendly interface."

Engine / Operator Split — Battle / Storm / Sally decisions
The harness's combat resolution (resolve_battle, resolve_storm,
resolve_sally) faithfully implements Inferno's three-position
Array with Flanking, Reposition, and per-position Strike
resolution. Some moments require player judgment that no
deterministic rule pins down: which Reserve to advance, which
left/right Lord to slide to center, where to direct Hits when
multiple targets are eligible, etc.

These choice points flow through a BattleDecisionContext. The
engine generates the legal options at each choice point and asks
the context for a selection. The context resolves the request in
one of three ways, in priority order:
  1. scripted_decisions list (FIFO, consumed in order). Used by
     tests to pin operator choices. A type mismatch raises
     immediately.
  2. callback (callable). Used by live play; the harness invokes
     the callback with {type, side, options, info} and expects a
     return value present in options.
  3. deterministic fallback ("leftmost"). Used when neither
     scripted nor callback is provided; picks options[0]. Keeps
     the harness usable as a deterministic black box.

Decision types (will grow as Phase 3b/3c expand):
  initial_placement_attacker — non-Active Attacker Lord into a slot
  initial_placement_defender — Defender Lord into a slot
  garrison_initial_placement — Storm only: which slot(s) the
                               Garrison Forces inhabit
  reserve_advance            — Battle: which Reserve advances to
                               which empty Front slot
  center_fill                — Battle: which Left/Right Lord
                               slides to fill empty Center
  storm_reserve_add          — Storm/Sally: per-round optional
                               add from Reserve, capped at
                               Stronghold Size
  flanker_target             — Center Flanker tie-break (Left or
                               Right)
  flanker_absorb             — Flanking Lord's owner choice to
                               absorb Hits aimed elsewhere when
                               Flanking all enemy Strikers
  hit_allocation             — when both a Flanker and a directly-
                               opposed Lord can be targeted

The full decision trace appears under `result["decisions"]` for any
combat resolution, so a reproduced Battle from a state file plus a
recorded scripted_decisions list will replay deterministically.

Tests must use scripted_decisions for any combat they assert
outcomes on. The leftmost fallback is acceptable only for tests
that verify structural properties (winner exists, positions are
valid, etc.) and not for tests that pin specific Hit counts or
Lord-Routs.

Non-Combat Pending Decisions
Combat is the most decision-heavy area, but pending decisions also
appear elsewhere in the engine — these flow through the same
`pending` mechanism (not BattleDecisionContext):

  - Approach: each Inactive Lord chooses Avoid Battle / Withdraw /
    Stand for Battle (4.3.4).
  - Besiege-or-Bypass: mandatory choice when Lord(s) arrive
    outside an Enemy Stronghold with no Enemy Lord outside (4.3.5).
  - Depart/Encamp/Sortie: choices for Lord(s) at a Bypass marker
    at start of a Command card (4.3.6).
  - Concede: defender's choice during Battle to Concede before
    Strike resolution (4.4.4).
  - Withdraw/Retreat: post-Battle defender choice when permitted
    (4.4.5).
  - Treachery targeting: when a Treachery card is played, the
    target choice (4.7.6).
  - Hold-card timing: Held Events have player-discretion play
    windows; the engine flags the window as a pending opportunity
    rather than forcing immediate play.

Each pending decision is recorded in state with: type, side that
owes the response, valid options, and any context needed for the
decision. The CLI's `pending` command surfaces these; the LLM
responds via `do` with the chosen option.
