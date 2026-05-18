# Driving the Inferno Harness with an LLM

This guide describes the suggested integration pattern for wiring an
LLM (Claude, GPT, or any tool-using model) to play one or both sides
of Inferno via this harness.

The pattern is the one CROSS_PROJECT_LESSONS.md §5 documents as
having worked for Nevsky: hidden-info filter at the boundary,
curated ~3 KB briefing, pre-filtered legal moves, 3-strike retry with
safe fallback, post-game self-critique.

## Boundary contract

The harness exposes:

- `src/inferno/llm/filter.py` — `hide_for_side(state, "guelph")` produces
  a JSON-serialisable copy of the state with the opponent's hand,
  face-down plan stack, and (with `hidden_mats=True`) opposing Lord
  mats redacted.
- `src/inferno/llm/briefing.py` — `build_briefing(state, "guelph")` packs
  the filtered state into a ~3 KB text briefing suitable for inclusion
  in a system prompt.
- `src/inferno/llm/player.py` — `play_with_callback(state, cb)` drives
  one action via a caller-supplied callback that receives the briefing-
  ready state plus the pre-filtered `legal_moves` list and returns
  an action dict. The callback can be anything: an HTTP request to
  Claude, a JSON-mode OpenAI call, a custom local model. After three
  rejected actions, the harness falls through to a safe
  phase-appropriate move (e.g., `levy_aow_draw` in 3.1,
  `command_reveal` in command_phase) so the game never deadlocks on
  an LLM hallucination.
- `src/inferno/llm/critique.py` — `build_self_critique_prompt(state, side)`
  emits a post-game prompt asking the model what it would have done
  differently. The Nevsky postmortem found this surprisingly
  productive for surfacing rule-interaction ambiguities.

## System prompt shape

A working system prompt looks like:

```text
You are playing Inferno (GMT Games, Levy & Campaign Vol. III) as
{side}. You are a calculating medieval Italian commander.

The harness will give you, each turn:
  (a) A briefing of the current game state from your perspective.
      Opposing-side secrets are redacted to counts.
  (b) A JSON array of legal moves. Every move is currently legal.
      You MUST respond with one of these moves verbatim — do not
      invent actions or args the engine didn't offer.
  (c) Recent action history.

Respond with EXACTLY ONE JSON object matching one of the legal
moves. No explanation, no markdown fence.

Strategic priors (advisory, see STRATEGY_DIGEST.md):
  - Firenze and Siena are the Leading Cities. Capturing either is
    often the winning theme.
  - Forage at Friendly Strongholds is automatic; Forage elsewhere
    is seasonal (no Winter outside friendly).
  - Sail (Pisa only, non-Winter) is the fastest map-traversal.
  - Treachery cards enable Revolt / Bribe — high upside but Coin-
    intensive.
  - Sieges end Command cards; plan extra Pass/Treachery cards if
    you'll be Besieging.

If you do not understand a legal move, prefer cmd_pass / *_done /
plan_add_card PASS — anything that ends a step cleanly.
```

## Per-turn loop

```python
from inferno.scenarios import load_scenario
from inferno.llm import play_with_callback, build_briefing, hide_for_side
import your_llm_client

state = load_scenario("F", seed=42)

def llm_callback(state, legal_moves):
    briefing = build_briefing(state, state["meta"]["active_player"])
    response = your_llm_client.complete(
        system=SYSTEM_PROMPT,
        user=f"{briefing}\n\nLegal moves (pick one):\n{json.dumps(legal_moves, indent=2)}",
    )
    return parse_json_from_response(response)

while state["meta"].get("phase") != "victory":
    result = play_with_callback(state, llm_callback, max_strikes=3)
    if result.fallback:
        log_fallback(result.fallback)
```

## Hidden-info policy

The harness redacts opposing-side info at the boundary; the LLM
literally cannot see it. This is more reliable than instructing the
model to ignore visible information.

Specifically hidden (when calling `hide_for_side(state, side)`):

  - Opposing side's `aow_held` cards → `<hidden:N>` count only.
  - Opposing side's `aow_deck` → `<hidden:N>` count only.
  - Opposing side's `plan_stacks` → `<facedown:i>` per slot.
  - With `hidden_mats=True`: opposing Lord mats' Forces (replaced by
    a single `<hidden_force_count>` total), Assets, Vassal readiness,
    Capabilities. Lord name/location/ratings/podesta/commander remain
    visible.

Public information NOT hidden:

  - Calendar (cylinder positions and Service marker positions are
    visible to both sides).
  - `aow_discard` (discarded cards are public knowledge).
  - `treachery_set_aside` (which Lord-specific Treachery cards have
    been set aside is public).
  - All map markers (Allegiance, Ravaged, Ruins, Siege, Bypass).
  - All Lord locations and statuses.
  - All VP totals.

## Failure modes the harness handles

| Failure | What the harness does |
|---------|----------------------|
| Callback raises an exception | Counts as a strike; retries up to `max_strikes`. |
| LLM returns malformed JSON | `dispatch` raises `IllegalAction[MALFORMED]`; counts as a strike. |
| LLM picks an action for the wrong side | `IllegalAction[WRONG_TURN]`; counts as a strike. |
| LLM picks a phantom-legal action | `IllegalAction[*]` with rule citation; counts as a strike. |
| Three strikes accumulated | Phase-appropriate safe fallback is applied. |
| State serialisation produces a non-JSON value | Caller should round-trip JSON before sending to LLM. The Phase 1 invariant tests verify scenario JSON round-trip is clean. |

## After the game

```python
from inferno.llm import build_self_critique_prompt
prompt = build_self_critique_prompt(state, "guelph")
critique = your_llm_client.complete(system="", user=prompt)
# Save to PLAYTESTS.md or feed the suggested strategic priors into
# STRATEGY_DIGEST.md
```

## What this guide does NOT include

- The actual LLM API call. Wire to your model of choice. The harness
  is framework-agnostic.
- Multi-turn dialog memory. The callback receives the full briefing
  each turn; whether you also keep transcript memory is your call.
- Tool-calling vs JSON-mode. Both work; pick whichever your model
  supports.

For the engine semantics, see `BRIEF.md`. For per-card text, see
`reference/Inferno_Arts_of_War_Reference.txt`. For strategic priors
the LLM may consult, see `STRATEGY_DIGEST.md` (currently a stub —
populate with playthrough findings).
