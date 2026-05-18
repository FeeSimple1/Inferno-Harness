# Inferno Harness

Python rules-enforcement harness for GMT's *Inferno: Guelphs and
Ghibellines in Tuscany, 1259–1262* (Levy & Campaign Series Volume III,
Living Rules 2023-04-10).

The harness holds full game state in a portable JSON file, validates
and executes every action defined by the rules, runs Battle / Storm /
Sally combat automatically, rolls all dice with a seedable RNG, and
exposes a structured interface (`new`, `state`, `legal-moves`, `do`,
`pending`, `history`, `save`, `load`, `briefing`, `play-event`,
`replay`) designed to be consumed by an LLM playing one or both sides.

This is a private project. See [`BRIEF.md`](BRIEF.md) for the
authoring spec.

## Status — v1.0

All BRIEF Phase 0–4 mechanics are implemented:

- All 6 scenarios (A through F) load and play.
- Full Levy phase (3.1 AoW → 3.2 Pay → 3.3 Disband → 3.4 Muster → 3.5
  CtA-skip).
- Full Campaign phase (capability_discard → plan w/ Lieutenants →
  command_phase → end_campaign 4.9).
- All Commands: Tax, Forage, Ravage, Supply, Sail, Pass, March +
  Approach + Battle, Besiege/Bypass + Depart/Encamp/Sortie, Siege +
  Storm + Sally, Treachery-Revolt + Treachery-Bribe.
- Full Battle resolution with three-position Array, Flanking,
  Reposition, six-step Strike, Concede, Loss rolls (with Knights'
  Quarter), Service-shift dice, post-Battle Spoils.
- All 52 AoW card effects registered (encoded where mechanically
  unambiguous, flagged for manual application by the LLM consumer
  where Battle/Storm in-round modifiers require operator judgment).
- BattleDecisionContext with scripted_decisions / callback / leftmost
  fallback priority.
- LLM-play harness (`src/inferno/llm/`) per CROSS_PROJECT_LESSONS §5.

**291 tests pass** on Python 3.10 sandbox (project policy 3.11+).
17 SMOKE-Inferno-NNN markers with regression tests. Round-trip
enumerator/handler sweep + greedy self-play sweep + strategic-agent
sweep + Hypothesis property-based invariant tests all green.

## Quickstart

Requires Python 3.11+.

```bash
git clone https://github.com/FeeSimple1/Inferno-Harness.git
cd Inferno-Harness
pip install -e ".[dev]"
pytest -v                         # 291 tests
inferno scenarios                 # list the 6 scenarios
inferno new A --seed 42 --out a.state.json
inferno state a.state.json --mode summary
inferno legal-moves a.state.json
inferno briefing a.state.json --side guelph
```

## Architecture

```
src/inferno/
├── __init__.py
├── actions.py        # 43 action handlers, dispatch envelope, IllegalAction
├── battle.py         # resolve_battle / resolve_storm / BattleDecisionContext
├── card_data.py      # 52 AoW + 12 Treachery + 12 Command card IDs
├── card_effects.py   # per-card Event effects + Capability hooks
├── cli.py            # argparse CLI: new/state/do/legal-moves/...
├── data/             # static state schema + 6 scenario JSON setups
├── flow.py           # Levy/Campaign step state machine
├── legal_moves.py    # defensive enumerator (CROSS_PROJECT_LESSONS §1)
├── llm/              # LLM-play integration (filter/briefing/player/critique)
├── render.py         # summary/verbose/focused-view renderers
├── rng.py            # HarnessRNG: seedable, context-logged dice
├── scenarios.py      # load_scenario(scenario_id, seed) -> State
├── state.py          # State / Lord / Locale / Calendar / Decks TypedDicts
└── static_data.py    # 60 Locales, 14 Lords, 91 Ways, 8 Units, 4 tiers

tests/
├── test_smoke.py     # imports, CLI subcommands, scenario stubs
├── test_phase1.py    # state model, scenario loader, renderers
├── test_phase2.py    # Levy mechanics
├── test_phase3a.py   # Plan + simple Commands + FPD
├── test_phase3b.py   # March + Approach + Battle + BDC
├── test_phase3c.py   # Besiege/Bypass + Siege + Storm + Sally + Treachery
├── test_phase3d.py   # Battle cleanups + Bypass-state March + Lieutenants
├── test_phase3e.py   # End-of-Campaign 4.9 substeps
├── test_phase4.py    # per-card AoW effects (33 tests)
├── test_llm.py       # LLM-play harness (18 tests)
├── test_invariants.py # Hypothesis property-based invariant tests
└── test_round_trip.py # enumerator/handler round-trip sweep

scripts/
├── build_static_data.py  # regenerate static_data.py from references
├── build_scenarios.py    # regenerate scenario JSONs
├── build_cards.py        # regenerate card_data.py
├── self_play.py          # greedy self-play sweep
└── strategic_agent.py    # combat-weighted strategic agent sweep
```

## Working with the harness as an LLM

See [`LLM_PLAY_GUIDE.md`](LLM_PLAY_GUIDE.md) for the recommended
integration pattern: hidden-info filter, briefing builder, 3-strike
retry + safe fallback, post-game self-critique.

## Authoring discipline

See [`BRIEF.md`](BRIEF.md) for the source priority, ambiguity
policy, and Q-NNN consultation chain.
See [`FUTURE_PROJECTS_LESSONS.md`](FUTURE_PROJECTS_LESSONS.md) and
[`CROSS_PROJECT_LESSONS.md`](CROSS_PROJECT_LESSONS.md) for the bug
patterns + audit lenses ported from the Nevsky postmortem.
See [`RULES_DECISIONS.md`](RULES_DECISIONS.md) for the (append-only)
record of user-adjudicated rule interpretations.

## License

Private project; no license granted.
