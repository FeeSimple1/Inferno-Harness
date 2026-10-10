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

### Campaign — March and Battle (Phase 3b)
- `cmd_march` — 4.3
- `approach_response` — 4.3.4 (Avoid / Withdraw / Battle). Optional arg
  `scripted_decisions`: a FIFO list of Battle tactical choices (array
  placement, tie-breaks, hit allocation, concession) for the field
  Battle this Approach may trigger — same channel `cmd_storm` /
  `cmd_sally` accept. Entries are accumulated across the response
  window and routed per side by each decision's `side`. Omit for the
  deterministic leftmost fallback.

Battles resolve synchronously within the triggering action, so there are no
separate `battle_decision`, `concede`, or `retreat` actions. In-Battle choices
— array placement, reserve/center fill, flanker tie-breaks, hit allocation,
and **concession** (4.4.4) — flow through the `BattleDecisionContext` via the
`scripted_decisions` / callback channel above.

The losing side's Retreat / Withdraw / Removed fate (4.4.5) is applied
automatically in the post-Battle step, but the two player elections are
operator-controllable. `approach_response` accepts an optional
`post_battle_decisions` arg (a FIFO list, same shape as `scripted_decisions`)
with two decision types:

- `post_battle_withdraw` — for each eligible losing Lord, `choice` is
  `"withdraw"` (go inside the Friendly Stronghold at the Battle Locale, 4.4.3 /
  11.2) or `"retreat"`. Default: `"withdraw"` if the Lord id is in
  `meta.post_battle_withdraw`, else `"retreat"`.
- `retreat_destination` — for each Retreating Lord, `choice` is one of the legal
  target Locales. Default: the deterministic leftmost (Friendly first, then
  alphabetical).

Omit `post_battle_decisions` (and leave `meta.post_battle_withdraw` unset) for
the legacy deterministic behaviour. The resolved post-Battle choices are echoed
on `battle_result["post_battle_decisions"]`.

`cmd_storm` and `cmd_sally` accept the same `scripted_decisions` channel for
their in-Battle choices. `cmd_sally` additionally accepts `post_battle_decisions`
with `retreat_destination` entries to direct where a losing-but-surviving
Besieger Retreats (default: deterministic leftmost). `cmd_storm` has no
post-Battle election (Storm Attackers never Retreat).

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

## Long-scenario Call to Arms and Game End corrections

`cta_allies` with `mode="extra_muster"` now parks on `meta.cta_substep="allies_muster"`
and records `meta.cta_extra_muster_lord`. The active side retains the turn. Use
`levy_muster_lord`, `levy_muster_vassal`, `levy_muster_transport`, and
`levy_muster_capability` for that Lord only. End with `levy_muster_done` (or
`cta_step_skip`), then the next side's Gather begins. The selected Lord must be
eligible per 3.4; the Commander is eligible for extra Muster, but not auto-Muster.

`cta_comune_setup` initializes starting assets only for a fresh Comune. On an
existing mat it adds only requested, previously unmustered Special Vassals;
requesting already-mustered names does not duplicate their forces. Empty/default
arguments on an existing mat leave its troops/assets intact. The legal menu
exposes possible new Special Vassal combinations. A captured Carroccio stays
captured even after recall and remustering.

`cta_gather_march` moves the Commander with his compulsory Comune and does not
permit an independent Comune move. No Moved/Feed charge is added. Call to Arms
cannot be redeclared or bypassed with `levy_cta_skip` while its substeps are active.

At turn 16, `end_game_check` ends the game without requiring Repair/Waste/Reset.
Once terminal, the menu is empty and action submissions raise `GAME_OVER`.
