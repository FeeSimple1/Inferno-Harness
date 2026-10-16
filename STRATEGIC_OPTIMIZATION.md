# Inferno: improving strategic play without weakening rules fidelity

Priority order: **(1) rules fidelity, (2) LLM strategic strength, (3) token savings.**

## New experiment: side-private strategic continuity

The documented `examples/play_with_claude.py` previously created a **new provider
conversation on every action**. It therefore discarded the model's earlier
campaign intentions even when the game had not ended. Reconstructing a coherent
multi-card operation from scratch costs reasoning time and can create strategic
inconsistency. Simply keeping the entire conversation would instead grow input
context and resend thousands of old tokens.

The live example now carries **one optional, model-authored strategic note per
faction** across callbacks. The current state, mandatory decisions, legal-action
catalog, and full inspection tools are unchanged. The model can send
`"strategy_note":"..."` alongside an otherwise valid selection (or permitted
reaction yield), or `"strategy_note":""` to clear a plan. The note is an
explicit *hypothesis*, never a rules assertion or a filter on choices. It should
summarize the objective, constraints, opponent response, and contingency—not
repeat the entire state or dump chain-of-thought. No character/token clipping
is applied. Updates commit **only after the full action including combat
choices succeeds**. Failed or interrupted actions discard provisional notes.

Each faction sees **only its own previous notes**; no notebook data enters the
authoritative state, legal-menu generator, action ID, RNG, or game history.
`--no-strategy-memory` disables it entirely for fair A/B trials. Default live
play enables **in-memory** notes. `--strategy-journal PATH` saves notes with an
exact authoritative-state digest; `--resume STATE --strategy-journal PATH`
rejects mismatched notes rather than attaching another campaign's strategy.
The journal file itself is operator-private and should not be sent to either
player as raw JSON, especially during a hidden-information game.

## Falsifiable strength evaluation

`benchmarks/strategy_ab.py` runs the **same provider model** as both factions,
with strategic continuity enabled for one side and disabled for the other. It
then **swaps factions on the same seed**, recording outcomes, VP, game progress,
accepted actions, interruptions, usage and notebook size. For example:

```sh
PYTHONPATH=src python benchmarks/strategy_ab.py --scenario A \
  --seeds 42 43 44 45 --model YOUR_MODEL --out ab.json
PYTHONPATH=src python benchmarks/strategy_ab.py --scenario A \
  --seeds 42 --stub --out smoke-ab.json
```

Provider authentication and SDK are needed for actual LLM comparisons; **live
trials have not been run in CI**. `--stub` validates the routing and scenario
plumbing but is **not** a strategy evaluation. Treat victory rates from small
samples as inconclusive. Evaluate both factions, multiple seeds, strategic
mistakes and resource/Service use, and compare quality before making stronger
claims. Stronger results should be corroborated with blinded human review of
specific decisions, not only VP or token counts. Because model calls can be
stochastic, use enough crossovers and report uncertainty.

## Correctness gate and token accounting

Test new notes with both perspectives, hidden data, failed provider calls,
invalid selections, save/resume mismatches and direct-versus-interface state
identity. The note layer is observational/host-only, never a rules change.
In token reports count notebook **in every subsequent provider request** and
count note output from the model; don't claim token savings from no longer
including the prior conversation while ignoring the notebook. Quality gains,
if any, are separate from token savings. A strategically useful note may have
net **positive** token overhead, which is acceptable only if strategic results
justify it without a fidelity regression.

## Next gate

The current work establishes an *instrumented experiment*, not a proven
stronger LLM player. Run real matched-model crossovers, inspect specific
plans and tactical decisions, and retain or revise the strategy notebook only
if it measurably improves decision quality relative to cost.

## Prompt overhead baseline

`benchmarks/strategy_memory_overhead.py` now measures **the complete system
prompt plus the initial user overview**, tokenized as separate payloads. It
compares the notebook disabled, enabled but empty, and enabled with the
published 305-character example note for both factions across A, C and F.
The example adds **606–610 characters to the user overview alone**; the
conditional notebook system instructions add a further fixed overhead.
Together these add **1,302–1,306 characters to the full input** on the
measured initial positions. An empty notebook sends no prior-note *state*
payload, but still incurs the conditional notebook system instructions.
The A/B control receives no note-writing instruction. These are additional
inputs, not token savings. When available, named-tokenizer measurements count
both fields separately, while real provider A/B trials also meter notebook
output and subsequent requests. Strategic improvement remains unproven.