# Playing Inferno through the loss-aware LLM interface

Use **`PlayerView` and `play_with_interface`** for model-driven play. A model
receives a perspective-filtered overview, then may request any number of focused
information or action pages before making a version-bound selection. It does not
receive the authoritative state or an unsolicited complete legal-menu array.

## Briefings: completeness before the character target

`build_briefing_document(state, side, max_chars=3500)` returns structured sections
with `id`, `title`, `status`, `essential`, `text`, and focused retrieval metadata.
`build_briefing` renders them to text. The character target is **soft**, not a
cutoff. An oversized essential section is returned intact. Pending decisions are
complete for their owner, including every required parameter and long message.
No sentence, action description, array element or parameter is sliced in half.

Every overview identifies the acting player (which may differ from the phase's
active player), perspective, phase/substep, current Command, available action
categories, pending decisions and recent changes. It lists the owner's **entire
Held Event hand**, visible Capabilities, resources and Service. Board summaries
show dynamic markers and positions. Repeated Vassal readiness states are grouped
without losing names or Service values. Static ratings, seats, geography, ways,
force composition of Vassals and notes are explicitly marked abbreviated and
remain accessible as complete records.

The latest public action's arguments and state changes are preserved. Verbose
combat round/dice/option traces may be replaced by clearly identified counts;
all other change fields and recorded choices remain visible. Full chronological
history, including exact traces, is retrievable. Earlier history may be deferred
as whole records, never silently chopped. `inspect/snapshot` returns the entire
filtered state as **one unsplit record**, including future visible fields not
known to the current formatter. This is the completeness escape hatch, not the
default prompt.

## Discovery and selection

```python
from inferno.scenarios import load_scenario
from inferno.llm import PlayerView, play_with_interface

state = load_scenario("F", seed=42, hidden_mats=True)
view = PlayerView(state)  # resolves the actual mandatory decision owner
print(view.overview())
```

The overview lists **every currently enumerated action category**, exact entry
counts, parameterized-template counts and tactical decision channels. A genuinely
singleton menu also includes its complete entry and ID; this avoids a redundant
lookup, not the player's decision. Otherwise retrieve pages:

```python
page = view.query({"request": "actions", "category": "cmd_march", "page_size": 12})
# Exact optional filters: lord, card, or where with dotted paths.
page = view.query({"request": "actions", "where": {"args.destination": "Cortona"}})
# Omit filters to inspect every entry. Continue until next_cursor is null.
page = view.query({"request": "actions", "page_size": 12})
if page["next_cursor"]:
    following = view.query({"request": "actions", "cursor": page["next_cursor"]})
```

`records` contain stable `action_id`, full original `move` metadata (including
arguments, complete description and `accepts_decisions`) and `parameterized`.
Every page reports `total`, `offset`, `returned`, `complete`, `next_cursor` and
`state_version`. Page sizes are caller-selected. An optional page character
target packs **whole records**; the first oversized record is returned intact.
No legal moves are ranked, sampled, preview-executed or discarded to meet a
budget. Filtered pages are exact partitions; cursors retain their filters.

Select an entry from this position and perspective:

```python
selection = {"action_id": entry["action_id"], "state_version": view.version}
# To instantiate a template OR choose optional parameters, supply complete args:
selection["args"] = {"lord_id": "siena", "destination": "Montalcino",
                     "way_type": "track", "with_lords": ["provenzano"]}
```

**Defaults are not a restriction on legal parameter values.** For example,
`end_waste` permits explicit per-Lord Asset/Capability discards; it is not limited
to the enumerator's default discard. Retrieve `action_reference` for accepted
argument fields and complete handler/helper documentation. References follow
argument forwarding through validators, so March, Supply and Pay parameters do
not disappear behind thin handler wrappers. Full printed Event and Capability
text for all 52 Arts of War cards is packaged in `card_reference`.

```python
view.query({"request": "inspect", "section": "action_reference", "keys": ["end_waste"]})
view.query({"request": "inspect", "section": "card_reference", "keys": ["F3", "F7"]})
view.query({"request": "inspect", "section": "lords", "keys": ["firenze"]})
view.query({"request": "inspect", "section": "board", "keys": ["Cortona"]})
view.query({"request": "inspect", "section": "index"})
```

Full sections are `context`, `pending`, `lords`, `board`, `calendar`, `cards`,
`effects`, `history`, `card_reference`, `action_reference`, `index`, and
`snapshot`. Omit keys to page all records. History keys are one-based indices.
Read results can be arbitrarily large when correctness requires it. A transport
must paginate whole records or increase its limit, not silently truncate them.

## Version and privacy contract

IDs and cursors are bound to the **visible position plus accepted-action
revision and perspective**. Every successful dispatch grows that revision,
including passes and hidden actions. Read operations never change it or use game
dice. Save/load with the same visible state retains identifiers. IDs deliberately
do not publish a digest of a secret hand or seed: hidden state is not a guessing
oracle. They are stale-state checks, not authentication credentials; the host
must bind each model to its own faction/game session.

Changing a position makes old views, cursors and selections fail with
`STALE_VIEW` before dispatch. Unknown IDs, malformed queries and incomplete
parameters are clean rejections. The state, resources, history and RNG remain
unchanged. A cursor cannot be silently reused with different filters.

All overview, page, reference and focused-state routes use the same visibility
boundary. Opposing Held hands and Plans, unrevealed draw queues and operator
scripts/callbacks are not exposed. Hidden Mats cannot be disabled by a query.
Only actually participating mats are revealed during combat; other enemy mats
remain hidden. Their visibility is scoped outside the saved mechanical state.

Where a list of valid targets would reveal secret Forces, Assets or Vassal
readiness, the interface supplies a **conditional parameterized template**
instead (Greek Fire, S16/S19 and Bribe). All legal instantiations remain accepted;
the engine validates them on submission. A conditional template is not a claim
that every guessed hidden target is valid. Public card rules and public roster
information remain retrievable. This is privacy preservation, not strategic
pruning of inconvenient choices.

## Default callback: unlimited reads, then one explicit choice

`examples/play_with_claude.py` implements the full loop. The callback receives a
`PlayerView` or a synchronous `DecisionView`. It starts with `view.overview()`,
processes JSON `request` objects through `view.query()`, and returns a selection.
It has no lookup-count cap. Provider length stops do not apply partial choices.
The response limit is configurable independently from briefing/page targets.

```python
def callback(view):
    messages = [{"role": "user", "content": encode(view.overview())}]
    while True:
        reply = complete_json(messages)  # your provider; require complete output
        if "request" in reply:
            answer = view.query(reply)
            messages += [{"role": "assistant", "content": encode(reply)},
                         {"role": "user", "content": encode(answer)}]
        else:
            return reply

while state["meta"]["phase"] != "victory":
    play_with_interface(state, callback)
```

Bulk `scripted_decisions` and `post_battle_decisions` arrays are trusted-operator
inputs, not authority for one player to preselect the opponent's choices. The
player transport rejects those arrays before mutation and exposes **all the same
elections and options** through their owner's `DecisionView`. No tactical option
is removed; the ownership boundary is different from bulk operator automation.

The same callback is asked for **every tactical election**. `DecisionView`
identifies the actual faction, exposes complete decision context and participating
mats, and pages all legal options. Its IDs also bind the option set, context,
parent action and ordinal. A failed or stale election cannot become a default.
The entire triggering action rolls back if a required callback is interrupted.
An optional Approach reaction is offered privately to the attacker before the
defender proceeds; `can_yield` permits an explicit yield, not an automatic pass.

No valid selection after the retry allowance means **play pauses**, not that the
harness chooses a strategically consequential fallback. `play_with_callback`
continues to exist for trusted legacy in-process tests/automation; it exposes raw
state and uses fallback, so it is **not the documented model interface**.
`submit_selection` is likewise a trusted low-level executor; use
`play_with_interface` or `selection_session` when player tactical choices matter.

## CLI / stateless tools

```sh
PYTHONPATH=src python -m inferno.cli new F --seed 42 --hidden-mats --out game.json
PYTHONPATH=src python -m inferno.cli briefing game.json --side guelph
PYTHONPATH=src python -m inferno.cli legal-moves game.json --side guelph
PYTHONPATH=src python -m inferno.cli legal-moves game.json --page --category levy_aow_draw --side guelph
PYTHONPATH=src python -m inferno.cli inspect game.json lords --keys firenze --side guelph
PYTHONPATH=src python -m inferno.cli query game.json '{"request":"actions","page_size":12}' --side guelph
PYTHONPATH=src python -m inferno.cli choose game.json '{"action_id":"ID","state_version":"VERSION"}' --side guelph
```

`legal-moves` defaults to the category overview, not the whole array. `briefing
--json` emits the structured document. `state`, `pending`, `history` and transcript
display are perspective-filtered by default. The save file and explicit `state
--raw`, `do`, `play-event`, `save` are trusted operator interfaces; never forward
raw saves or unfiltered dispatch results to a player.

A CLI `choose` that enters combat does **not** silently use default tactics. It
returns `status=awaiting_decision`, the deciding perspective, complete decision
view and a resume prefix, without modifying the save. Reissue the same selection
with `--decisions-json '[...]'` and optional `--decision-query '{"request":"actions"}'`
to inspect/answer the next election. Append its ID/version to the prefix. All
queries replay only that selected action from the unchanged base and roll back;
only a completely answered action commits. Route each response to its named
faction. Stale or surplus decision prefixes are rejected atomically. The host retains the
original action selection; continuation responses do not echo its raw parameters
to the opposing faction. Missing saves return an error, never an invented game.

## Verification and measurement

`tests/test_llm_structured_interface.py` checks both factions, oversized decisions,
whole pages/templates, exhaustive menu equivalence, identical mechanical results,
read-only queries, hidden-state noninterference, stale IDs/cursors, full reference
grammar, tactical ownership, interrupted combat rollback and CLI continuation.
Existing mechanical tests remain independent of output metrics.

`benchmarks/interface_output.py` runs representative complete deterministic games
and compares independent direct and interface executions. It charges all chosen-
category pages, relevant full Lord/board records, first-use action/card references,
private reaction views and complete tactical-option pages. It separately measures
exhaustive-menu pagination. An optional `--tokens` run uses `tiktoken`'s named
`cl100k_base` encoding; otherwise exact character/UTF-8 counts are reported, not
fabricated token estimates.

Report the old documented truncated prompt and an equivalent-information full-
menu control separately. The old prompt omitted facts and tactical elections;
its smaller size was not a correctness-equivalent achievement. Pagination can
cost more when a player reads every entry. Model/provider context resends, system
prompts and cache accounting can also change billing; unique emitted output
savings are not a promise of lower API charges. No live-model quality claim is
made by deterministic-policy measurement.
