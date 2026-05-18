"""Inferno harness CLI.

Per BRIEF "LLM-Consumer Interface": the CLI wraps the library and is
suitable for an LLM to call via shell or for the user to run directly.

Phase 0 wires up all required subcommands but each is a no-op that
documents its rule citation slot.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .render import render_summary, render_verbose
from .scenarios import SCENARIO_IDS, list_scenarios


PHASE_0_NOTE = (
    "Phase 0 stub: no game logic implemented yet. See BRIEF.md phase plan."
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="inferno",
        description="Rules harness for Inferno (L&C Volume III).",
    )
    parser.add_argument("--version", action="version", version=f"inferno-harness {__version__}")

    sub = parser.add_subparsers(dest="cmd")

    # ---- new ----
    p_new = sub.add_parser("new", help="Initialize a state file from a scenario.")
    p_new.add_argument("scenario", choices=SCENARIO_IDS, help="A through F")
    p_new.add_argument("--seed", type=int, required=True, help="RNG seed.")
    p_new.add_argument(
        "--out", type=Path, default=Path("inferno.state.json"),
        help="Where to write the state file."
    )
    p_new.set_defaults(func=_cmd_new)

    # ---- state ----
    p_state = sub.add_parser("state", help="Render current state.")
    p_state.add_argument("state_file", type=Path)
    p_state.add_argument(
        "--mode", choices=["summary", "verbose"], default="summary",
        help="Rendering mode (focused views: phase 1+)."
    )
    p_state.set_defaults(func=_cmd_state)

    # ---- legal-moves ----
    p_legal = sub.add_parser("legal-moves", help="Enumerate legal actions.")
    p_legal.add_argument("state_file", type=Path)
    p_legal.set_defaults(func=_cmd_legal_moves)

    # ---- do ----
    p_do = sub.add_parser("do", help="Execute an action.")
    p_do.add_argument("state_file", type=Path)
    p_do.add_argument(
        "action_json",
        help="JSON action string (or path to a .json file).",
    )
    p_do.set_defaults(func=_cmd_do)

    # ---- pending ----
    p_pending = sub.add_parser(
        "pending", help="List pending decisions and who owes a response."
    )
    p_pending.add_argument("state_file", type=Path)
    p_pending.set_defaults(func=_cmd_pending)

    # ---- history ----
    p_hist = sub.add_parser("history", help="Return last N action results.")
    p_hist.add_argument("state_file", type=Path)
    p_hist.add_argument("-n", "--count", type=int, default=10)
    p_hist.set_defaults(func=_cmd_history)

    # ---- save / load ----
    p_save = sub.add_parser("save", help="Explicit save (in addition to automatic state-file updates).")
    p_save.add_argument("state_file", type=Path)
    p_save.add_argument("out", type=Path)
    p_save.set_defaults(func=_cmd_save)

    p_load = sub.add_parser("load", help="Validate a state file by loading it.")
    p_load.add_argument("state_file", type=Path)
    p_load.set_defaults(func=_cmd_load)

    # ---- scenarios ----
    p_sc = sub.add_parser("scenarios", help="List the six published scenarios.")
    p_sc.set_defaults(func=_cmd_scenarios)

    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 0
    return args.func(args)


# --------------------------------------------------------------------- handlers
def _cmd_new(args: argparse.Namespace) -> int:
    print(PHASE_0_NOTE)
    print(f"  Would init scenario {args.scenario} with seed {args.seed} -> {args.out}")
    print("  Phase 1 implements scenarios.load_scenario(), state initialization,")
    print("  and writing the state file. See BRIEF.md section 'Phasing'.")
    return 0


def _cmd_state(args: argparse.Namespace) -> int:
    state = _load_state(args.state_file)
    if args.mode == "summary":
        print(render_summary(state))
    else:
        print(render_verbose(state))
    return 0


def _cmd_legal_moves(args: argparse.Namespace) -> int:
    state = _load_state(args.state_file)
    from .legal_moves import enumerate_legal

    moves = enumerate_legal(state)
    print(json.dumps(moves, indent=2))
    return 0


def _cmd_do(args: argparse.Namespace) -> int:
    print(PHASE_0_NOTE)
    print(f"  Would apply action: {args.action_json}")
    print("  Phase 2+ implements actions.dispatch(). See ACTIONS.md.")
    return 0


def _cmd_pending(args: argparse.Namespace) -> int:
    state = _load_state(args.state_file)
    pending = state.get("pending", [])
    print(json.dumps(pending, indent=2))
    return 0


def _cmd_history(args: argparse.Namespace) -> int:
    state = _load_state(args.state_file)
    history = state.get("history", [])
    print(json.dumps(history[-args.count:], indent=2))
    return 0


def _cmd_save(args: argparse.Namespace) -> int:
    state = _load_state(args.state_file)
    args.out.write_text(json.dumps(state, indent=2, sort_keys=True))
    print(f"Wrote {args.out}")
    return 0


def _cmd_load(args: argparse.Namespace) -> int:
    state = _load_state(args.state_file)
    print(f"Loaded {args.state_file}; meta={state.get('meta', {})}")
    return 0


def _cmd_scenarios(args: argparse.Namespace) -> int:
    for s in list_scenarios():
        print(f"  {s['id']}: {s['name']}")
    return 0


# --------------------------------------------------------------------- helpers
def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        # Phase 0 convenience: synthesize a minimal stub state so commands
        # can be exercised end-to-end before scenarios.load() exists.
        return {
            "meta": {
                "scenario": "<unset>",
                "rules_edition": "living_rules_2023-04-10",
                "rng_seed": 0,
                "turn": 0,
                "phase": "levy",
                "active_player": "guelph",
                "game_over": False,
                "winner": None,
            },
            "calendar": {},
            "lords": {},
            "locales": {},
            "decks": {},
            "capabilities_in_play": [],
            "pending": [],
            "history": [],
            "vp": {"guelph": 0.0, "ghibelline": 0.0},
        }
    return json.loads(path.read_text())


if __name__ == "__main__":
    sys.exit(main())
