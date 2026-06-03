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
- `cmd_sail` — 4.7.3 (Pisa Podestà only, entire card)
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
- `battle_decision` — in-Battle decisions via BattleDecisionContext
- `concede` — 4.4.4
- `retreat` — 4.4.5

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
