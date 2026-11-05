# Action Grammar — Inferno Harness

Specification of the JSON action grammar accepted by the harness's `do`
command. Each action type has a schema; malformed actions are rejected
with a clear error.

This file is built up as phases progress. Phase 0 captures the action
envelope only; later phases fill in the per-command schemas.

---

## Envelope

Every action is a JSON object with at minimum:

```json
{
  "action": "<action_name>",
  "side": "guelph" | "ghibelline",
  "args": { ... }
}
```

`action` must be a nonempty string. `args`, when supplied, must be an object (not null or an array). Rejected actions leave state, resources, history, and RNG advancement unchanged.

`action` names follow snake_case. `side` is the side issuing the
action (matches `state.meta.active_player` unless the action is a
response to a pending decision owed by the other side).

## Action types (placeholders — schemas filled in by later phases)

### Levy phase (Phase 2)
- `levy_pay` — 3.2
- `levy_disband` — 3.3 (Beyond Service Limit / At Service Limit)
- `levy_muster` — 3.4
- `levy_vassal` — 3.4.2
- `levy_transport` — 3.4
- `levy_capability` — 3.4.4
- `levy_call_to_arms` — 3.5

### Campaign — simple Commands (Phase 3a)
- `cmd_tax` — 4.7.2 (entire card)
- `cmd_forage` — 4.6.2
- `cmd_ravage` — 4.7.1
- `cmd_supply` — 4.6
- `cmd_sail` — 4.7.3 (Pisa Podestà only, entire card). Destinations
  include enemy Ports free of Unbesieged Enemy Lords (arrival at an
  Unbesieged Enemy Stronghold places a Siege marker). Optional arg
  `discard`: `{"Provender": n, "Loot": m}` discarded per Greed (1.7.2)
  before the Ship-capacity check; the enumerator offers a deterministic
  minimal-discard variant when cargo exceeds Ships.
- `cmd_pass` — 4.7.7

### End-of-card Feed choices

Every action that finishes a card runs Feed before Pay and Disband. The
legal menu advertises an optional `feed_decisions` channel for Commands and
their reactions, including automatic completion when actions run out.
`feed_asset` chooses one food marker using a `choice` object with
`from_lord_id` and `asset` (`"Provender"` or `"Loot"`). For example, ending
Arezzo's card and feeding with his Loot uses this action.

```json
{
  "action": "cmd_end_card",
  "side": "guelph",
  "args": {
    "lord_id": "arezzo",
    "feed_decisions": [
      {"type": "feed_asset", "side": "guelph",
       "choice": {"from_lord_id": "arezzo", "asset": "Loot"}}
    ]
  }
}
```

The engine first feeds each Moved/Fought Lord from his own mats. A Commander
and Comune count together. Only after that pass may short Lords consume
surplus food from Friendly Mustered Lords at the same Locale. Each decision
reports the feeding `lord_id`, `remaining` requirement and whether `sharing`
is underway. The owner chooses any available donor/resource pair. Partial
food is consumed before an Unfed Service shift, and expenditure stops at
the exact requirement.

Scripts run in Feed order and supply one entry per marker until their prefix
ends, including forced markers encountered while entries remain. Invalid or
unused entries reject the whole action. Trusted automation defaults to own
Provender then Loot, followed by shared Provender then Loot in donor order.
Player interfaces route each choice to the feeding faction, including the
opponent of the active Lord. Interrupted selections roll back the Command.
`fpd.feed` reports the actual `spent` donor/resource pairs. Explicit elections
are recorded in `fpd.feed_decisions`. `selection_session` supports pausing,
retrieving options and resuming Feed from the original unchanged save.

### Friars and the Guelph Plan

S14 Friars is a This Campaign Event. A drawn Event enters
`active_events.this_campaign`. With Friars active, Guelphs select their
cards normally and `plan_done` shuffles the completed stack using the
logged replay RNG. Both players' snapshots conceal the remaining order,
and Commands reveal normally. Player results and history conceal the
shuffle rolls because those indices would reconstruct the stack.

Older saves with S14 Held still offer its normal `play_event` action.
Playing that copy activates the duration effect and, if planning is already
complete, shuffles the remaining Guelph stack immediately. Reset discards
S14 and clears its duration effect. An older save with an already active S14
and a completed unshuffled Plan shuffles once before the first Guelph reveal.

### Campaign — March and Battle (Phase 3b)
- `cmd_march` — 4.3
- `approach_response` — 4.3.4 (Avoid / Withdraw / Battle). Optional arg
  `scripted_decisions`: a FIFO list of Battle tactical choices (array
  placement, tie-breaks, hit allocation, concession) for the field
  Battle this Approach may trigger — same channel `cmd_storm` /
  `cmd_sally` accept. Entries are accumulated across the response
  window and routed per side by each decision's `side`. Omit for the
  deterministic leftmost fallback. For `choice: "avoid"`, supply the
  `destination`, optional `way_type` (`"road"` or `"track"`), and optional
  `with_lords` (other pending defenders avoiding together). Shared Carts
  carry up to two Provender per Cart on Roads or one on Tracks. Avoiding
  discards Loot and excess Provender to the approaching Lords as Spoils;
  the legal menu lists each option's `discarded_assets`. Arrival at an
  Unbesieged enemy Stronghold establishes Bypass.

Battles resolve synchronously within the triggering action, so there are no
separate `battle_decision`, `concede`, or `retreat` actions. In-Battle choices
— array placement, reserve/center fill, flanker tie-breaks, hit allocation,
and **concession** (4.4.4) — flow through the `BattleDecisionContext` via the
`scripted_decisions` / callback channel above.

The losing side's Retreat / Withdraw / Removed fate (4.4.5) is applied
automatically in the post-Battle step, with player choices available.
`approach_response` accepts an optional
`post_battle_decisions` arg (a FIFO list, same shape as `scripted_decisions`)
with these decision types:

- `post_battle_withdraw` — for each eligible losing Lord, `choice` is
  `"withdraw"` (go inside the Friendly Stronghold at the Battle Locale, 4.4.3 /
  11.2) or `"retreat"`. Default: `"withdraw"` if the Lord id is in
  `meta.post_battle_withdraw`, else `"retreat"`.
- `retreat_destination` — for each Retreating Lord, `choice` is one of the legal
  target Locales. Default: the deterministic leftmost (Friendly first, then
  alphabetical).
- `retreat_way` — when more than one legal Way connects the chosen
  destination, select `"road"` or `"track"`. Conceding Lords retain
  Provender according to the selected Way and their co-retreaters' Carts.
- `spoils_recipient` — the winning faction chooses a surviving Lord with
  room for the current Asset type. The decision info identifies the `asset`
  and `remaining` markers in that pool.
- `spoils_amount` — choose how many of those markers the selected Lord
  receives, from one through the remaining pool or that mat's spare capacity,
  whichever is smaller. Repeat recipient and amount choices until the pool
  is exhausted. With just one eligible recipient the full legal amount is
  forced. Each mat holds at most 16 of each Asset type. Excess that cannot
  fit on any eligible mat is lost and reported in `lost_to_cap`.

For example, these entries give four Coin to Astimberg after the losing
side's Retreat choices have resolved.

```json
[
  {"type": "spoils_recipient", "side": "ghibelline", "choice": "astimberg"},
  {"type": "spoils_amount", "side": "ghibelline", "choice": 4}
]
```

Spoils use the winning faction's decision callback, including when an Enemy
Avoid triggers the award. Player-facing interfaces require a valid selection
at each optional choice. Operator scripts reject invalid recipients, amounts
and pinned sides atomically. Without a script or callback the engine divides
Spoils in capped round-robin order. Field Battle and Sack awards wait until
Losses and removal have determined the surviving recipients.

Omit `post_battle_decisions` (and leave `meta.post_battle_withdraw` unset) for
the deterministic defaults. Non-default post-Battle choices are echoed
on `battle_result["post_battle_decisions"]`.

`cmd_storm` and `cmd_sally` accept the same `scripted_decisions` channel for
their in-Battle choices. `cmd_sally` additionally accepts `post_battle_decisions`
with `retreat_destination` and `retreat_way` entries to direct where a losing-but-surviving
Besieger Retreats (default: deterministic leftmost). `cmd_storm` accepts
`post_battle_decisions` for Spoils allocation after a Sack, as do Surprise
(`play_event` with F3/S3) and its automatic Storm through `besiege_or_bypass`.
Sack pools are offered in Loot, Provender and Coin order, followed by the
captured Assets of each inside Lord. Avoid responses accept the same Spoils
entries for Assets discarded to the approaching faction. Field Battle
allocations are recorded under `battle_result["spoils"]`, Sack allocations
under `storm_result["spoils"]` (or `auto_storm["spoils"]`), and Avoid allocations
under `spoils_allocation`.

Discoverability: `enumerate_legal` tags each Battle-triggering move (the Stand
`approach_response`, `cmd_storm`, `cmd_sally`) with an informational
`accepts_decisions` key listing the decision-type vocabulary each optional
channel accepts. It is a sibling of `args`; `dispatch` ignores it.

### Campaign — Siege subsystem (Phase 3c)
- `besiege_or_bypass` — 4.3.5 (mandatory choice)
- `bypass_march` — 4.3.6 Depart
- `bypass_encamp` — 4.3.6 Encamp
- `bypass_sortie` — 4.3.6 Sortie
- `cmd_siege` — 4.5.1 (entire card)
- `cmd_storm` — 4.5.2
- `cmd_sally` — 4.5.3
- `cmd_treachery_revolt` — 4.2.3 / 4.7.6
- `cmd_treachery_bribe` — 4.2.3 / 4.7.6

### Arts of War (Phase 4 deferred)
- `play_event` — 3.1.3 + per-card text
- `play_capability` — 3.4.4 + per-card text
- `play_held_event` — designated Hold-window resolution


## Audit corrections — v6.14.0

Use `enumerate_legal(state)` to obtain executable choices and their decision
owner. Pending choices can belong to a different side from
`state.meta.active_player`; always use the move's `side` in the action and in
the player's briefing. An active Command card and its Feed/Pay/Disband must
finish before `command_reveal` can advance the sequence.

### Drawn immediate Events

`levy_aow_draw` now pauses at an Event that requires a choice, keeping its card
in `pending` with `type: "event_resolution"`. Remaining drawn cards stay in
`aow_resolution.remaining`, in draw order. Resolve with:

```json
{
  "action": "levy_resolve_event",
  "side": "guelph",
  "args": {
    "card_id": "F22",
    "effect_args": {"target_lord_id": "giordano", "mode": "shift"}
  }
}
```

The enumerator provides valid targets/effects for the actual state. Resolution
consumes the card once, then continues the draw queue. Event consequences such
as Revolt/Exiles also finish before the next card. Incomplete `play_event`
submissions are rejected without losing the Held card or partially applying
its effect. Save/load preserves the pending draw queue.

### Levy Capability

`levy_muster_capability` accepts `lord_id`, optional explicit `card_id`, and
optional `target_lord_id` (default: the levying Lord). Scope is determined by the
printed Capability, not by the caller. An explicitly incompatible `scope` is
rejected. The menu names the available card and a legal recipient; a Commander
may provide the Capability to its own eligible Comune. Duplicate titles,
mat limits, and printed eligibility are checked before spending Lordship.

### Payments and Exiles

`cmd_fpd_pay` accepts `from_lord_id`, `target_lord_id`, `asset` (`Coin` or
`Loot`), and `amount`. The legal menu includes co-located payers, legal Loot,
and the Podesta rate. `cmd_fpd_pay_done` declines remaining payment choices.
Service beyond box 16 is not expired Service.

`cmd_resolve_exiles` accepts `slides`, a list of `{"lord_id": "...", "kind":
"service"}` or `"kind": "cylinder"` entries. Each entry spends one shift.
A partial list preserves the remaining entitlement and refreshes its targets;
an empty list declines the remainder. Shifts may leave either calendar edge.

### Commands and randomness

`cmd_pass.count` must be positive. Entire-card Commands are unavailable after
any earlier Command on that card, including a zero-action Road March. Ordinary
March cannot release a besieged Lord; an explicit marching group needs a legal
Commander/Lieutenant relationship. Supply choices include remote sources and
shared Carts, with the endpoint subject to the same blocking rules as the route.

Deck indices now use unbiased, logged base-six rejection sampling across the
whole deck. Old seed numbers will therefore produce different games from
v6.13.0; replays recorded under the old draw algorithm are not promised to
reproduce under this version. New runs remain deterministic.

## Self-play follow-up: arrival and Held Event choices

### March arrival and Surprise

`cmd_march` records `pending_besiege` when arriving at an unencircled Enemy
Stronghold. It contains the decision owner, active Lord, destination, marching
group, and whether the destination had no Lords before arrival. Resolve the
free `besiege_or_bypass` choice even if March spent the last action; the menu
retains it before Feed/Pay/Disband.

When F3/S3 Surprise is legal, `play_event` itself chooses Besiege, places two
Siege markers, and resolves the mandatory Storm immediately. Do not submit a
second `besiege_or_bypass` after playing Surprise. Example:

```json
{
  "action": "play_event",
  "side": "guelph",
  "args": {
    "card_id": "F3",
    "scripted_decisions": [
      {"type": "concede", "side": "attacker", "choice": "yes"}
    ]
  }
}
```

This example fights the compulsory first round, then concedes at the next
eligible decision. Without that concession, Surprise allows up to three rounds
if Forces remain. The action accepts the same Storm decision types as
`cmd_storm`; the menu advertises them in `accepts_decisions`. Failed decisions
reject the entire play atomically.

### Group March and Held Event menus

Group March options use `with_lords` for the chosen Commander companions;
Lieutenant partners and a Commander's own Comune move together automatically.
The description lists the effective group and its action cost. Shared Carts,
Laden status, Road Works, and trapped-Lord restrictions are validated identically
by the menu and the executor.

Held Event options use `play_event.args.effect_args` for card-specific choices.
For Greek Fire this includes `enemy_lord_id`, `unit_to_remove`, and (when there
is a Capability to discard) `capability_to_discard`. F11/F23 Treachery choices
include `treachery_card`; F23 also includes the two-Coin `coin_sources` split.
The briefing lists the owner's Held Event hand independently of recent history.

Muster action limits include printed Lordship, applicable Capability bonuses,
and Event grants. Segment-only Held Event grants expire after that segment;
This-Levy grants remain for Call to Arms and expire before Campaign. The menu
uses the same allowance calculation as the action handler.

## Call to Arms: usable Allies Muster and safe Comune lifecycle

`cta_allies` with `mode: "extra_muster"` starts a one-Lord Muster segment; it
no longer silently ends that player's Call to Arms. `target_lord_id` must name
a Mustered Lord eligible to Muster at his current location under 3.4. The
Commander is eligible; his Comune cannot conduct an independent segment.

While this segment is open, the same player submits ordinary
`levy_muster_lord`, `levy_muster_vassal`, `levy_muster_transport`, or
`levy_muster_capability` actions, using the selected Lord as the mustering Lord.
Normal costs, Lordship allowance, and recipient restrictions apply. The selected
Lord's allowance is fresh for this extra segment. `levy_muster_done` ends it,
including when the player chooses not to spend the entire allowance. A second
Allies selection or Call to Arms declaration cannot bypass the open segment.
The legal menu supplies the corresponding choices, and saving/loading preserves
the pending segment.

`cta_gather_march` automatically moves the Commander's mustered Comune with
him. It does not require the caller to name that compulsory companion, and the
Comune cannot be moved independently by that action.

`cta_comune_setup` distinguishes a fresh mat from an already Mustered Comune.
Its `muster_special_vassals` argument is a list of distinct Special Vassal names;
already Mustered names do not add their Forces again. Newly chosen eligible
vassals add only their own Forces. Omitting the list fills any missing minimum
requirements without restoring casualties or spent Assets. A captured Carroccio
cannot be reintroduced. The menu enumerates valid reinforcement selections.

Commander disbanding clears his Comune too; the Comune can subsequently be set
up once at the Leading City. See `LONG_SCENARIO_FIXES.md` for the related saved
position regressions, corrected Sack scoring, terminal Game End behavior, and
canonical serialization of Call to Arms permissions.


## Model-facing discovery and execution

Use `PlayerView` and `play_with_interface`, or CLI `briefing`, `legal-moves`,
`query`, `inspect`, `choose`. The default prompt is a complete essential briefing
and exhaustive category overview, not an unsolicited full action list. Briefing
and page character budgets are soft; whole decisions/descriptions/parameters
are never sliced. Abbreviated or deferred sections advertise exact retrieval.

`request=actions` supports category, lord, card, exact dotted-field `where`,
caller-selected page size, cursor and optional character target. No strategic
ranking, preview-based pruning or first-N menu restriction is added. Each entry
preserves full action metadata. `request=inspect` provides complete visible
records and printed card references; `action_reference` exposes handler/helper
parameter grammar. Defaults do not limit legal argument values: an ID selection
may supply complete `args`, validated by the unchanged authoritative handler.

IDs and cursors bind the accepted-action revision, visible position, perspective
and query filters; tactical IDs additionally bind the context/option set and
parent action. Stale selections are rejected before dice, history or resources
change. The host must also bind requests to the correct game/player; IDs are not
a substitute for authentication. Hidden-mat target templates avoid leaking
secret eligibility while retaining every legal instantiation.

Every synchronous combat election is routed to its actual owner. Failed model
responses pause instead of silently selecting fallback actions. CLI `choose`
returns `awaiting_decision` with an unchanged save and a versioned continuation
when a tactical election is reached. Send that response only to its named
faction; use `--decision-query` for every page, and append explicit choices via
`--decisions-json` until the whole action commits.

Missing saves now produce `STATE_NOT_FOUND`, not an invented placeholder game.
Raw `dispatch`, `do`, `play-event`, saves and legacy `play_with_callback` remain
trusted-operator APIs. Never pass their unfiltered state/results to a model.
See `LLM_PLAY_GUIDE.md` and `examples/play_with_claude.py` for the current callback.

### Voluntary Reset discards (4.9.6)

After Waste, `end_reset` runs the compulsory Reset cleanup once: set aside
used Treachery, unstack Lieutenants, and expire Campaign Events. Guelphs then
Ghibellines may return any of their Held Events, This-Lord Capabilities or
side-wide Capabilities to their own Arts of War decks. The Calendar stays in
the current box until both factions finish their elections.

```json
{"action":"end_reset","side":"guelph","args":{"reset_discard":["F4","F22"]}}
{"action":"end_reset","side":"ghibelline","args":{"reset_discard":[]}}
```

Unselected cards stay in play or Held. Omitting `reset_discard` keeps all
cards. By default each action finishes that faction's election; use
`done:false` to discard some cards and continue choosing. The legal menu
offers every available card as a repeatable single-card choice plus a finish
choice, so every subset remains reachable without listing every combination.
Explicit batches are accepted as well. Wrong owners, duplicate IDs, invalid
cards and malformed selections reject without mutation.

Returning a Hold does not play its Event. Returning Tau Company (F22's
Capability) removes Altopascio and temporarily Disbands a Lord left without
Forces; F22's Held Event does not apply those Capability effects. Cascade
discards return each card once. Immediate Campaign victory stops the remaining
batch before further cards or Calendar advance, and opponent history reveals
only completed discards. Other eligible Held Events can still be played during
Reset and expire normally. Political decisions must resolve before continuing.

The `meta.reset_started` flag persists compulsory cleanup and the active
faction across save/load. Past End Campaign substeps cannot be replayed once
Reset begins. Finishing the Ghibelline election advances the Calendar once,
clears the flag, and resumes Levy or game end. Final Game End checking remains
before Repair, Waste and Reset.
