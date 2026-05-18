"""Inferno harness CLI.

Per BRIEF "LLM-Consumer Interface": the CLI wraps the library and is
suitable for an LLM to call via shell or for the user to run directly.

Phase 1 wires `new` (creates a real state file from a scenario), `state`
(renders summary/verbose/focused), and `scenarios`. The action-bearing
commands (`do`, `legal-moves`, `pending`) are still Phase-0 stubs and
will be filled in by Phase 2+.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .render import (
    render_calendar,
    render_decks,
    render_locale,
    render_lord,
    render_summary,
    render_verbose,
)
from .scenarios import SCENARIO_IDS, list_scenarios, load_scenario


PHASE_NOT_IMPLEMENTED = (
    "Not implemented yet. See BRIEF.md phase plan for the schedule."
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
        help="Where to write the state file (default: ./inferno.state.json).",
    )
    p_new.set_defaults(func=_cmd_new)

    # ---- state ----
    p_state = sub.add_parser("state", help="Render current state.")
    p_state.add_argument("state_file", type=Path)
    p_state.add_argument(
        "--mode", choices=["summary", "verbose"], default="summary",
    )
    p_state.add_argument("--lord", help="Focused view: single Lord (id or name).")
    p_state.add_argument("--locale", help="Focused view: single Locale by name.")
    p_state.add_argument("--calendar", action="store_true", help="Focused view: Calendar.")
    p_state.add_argument("--decks", action="store_true", help="Focused view: deck composition.")
    p_state.set_defaults(func=_cmd_state)

    # ---- legal-moves (Phase 0 stub still) ----
    p_legal = sub.add_parser("legal-moves", help="Enumerate legal actions (Phase 2+).")
    p_legal.add_argument("state_file", type=Path)
    p_legal.set_defaults(func=_cmd_legal_moves)

    # ---- do (Phase 0 stub still) ----
    p_do = sub.add_parser("do", help="Execute an action (Phase 2+).")
    p_do.add_argument("state_file", type=Path)
    p_do.add_argument("action_json")
    p_do.set_defaults(func=_cmd_do)

    # ---- pending / history / save / load ----
    p_pending = sub.add_parser("pending", help="List pending decisions.")
    p_pending.add_argument("state_file", type=Path)
    p_pending.set_defaults(func=_cmd_pending)

    p_hist = sub.add_parser("history", help="Last N action results.")
    p_hist.add_argument("state_file", type=Path)
    p_hist.add_argument("-n", "--count", type=int, default=10)
    p_hist.set_defaults(func=_cmd_history)

    p_save = sub.add_parser("save", help="Explicit save (pretty-prints to a new path).")
    p_save.add_argument("state_file", type=Path)
    p_save.add_argument("out", type=Path)
    p_save.set_defaults(func=_cmd_save)

    p_load = sub.add_parser("load", help="Validate a state file by loading it.")
    p_load.add_argument("state_file", type=Path)
    p_load.set_defaults(func=_cmd_load)

    p_sc = sub.add_parser("scenarios", help="List the six published scenarios.")
    p_sc.set_defaults(func=_cmd_scenarios)

    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 0
    return args.func(args)


# ----------------------------------------------------------- handlers
def _cmd_new(args: argparse.Namespace) -> int:
    state = load_scenario(args.scenario, seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=False))
    print(f"Wrote {args.out}")
    print(f"  Scenario {args.scenario} loaded; seed={args.seed}")
    print(f"  {sum(1 for l in state['lords'].values() if l['status']=='mustered')} Lords Mustered, "
          f"{sum(1 for l in state['lords'].values() if l['status']=='on_calendar')} on Calendar, "
          f"{sum(1 for l in state['lords'].values() if l['status']=='removed')} removed.")
    return 0


def _cmd_state(args: argparse.Namespace) -> int:
    state = _load_state(args.state_file)
    # Focused views take precedence over --mode
    if args.lord:
        print(render_lord(state, args.lord))
        return 0
    if args.locale:
        print(render_locale(state, args.locale))
        return 0
    if args.calendar:
        print(render_calendar(state))
        return 0
    if args.decks:
        print(render_decks(state))
        return 0
    if args.mode == "verbose":
        print(render_verbose(state))
    else:
        print(render_summary(state))
    return 0


def _cmd_legal_moves(args: argparse.Namespace) -> int:
    from .legal_moves import enumerate_legal
    state = _load_state(args.state_file)
    print(json.dumps(enumerate_legal(state), indent=2, ensure_ascii=False))
    return 0


def _cmd_do(args: argparse.Namespace) -> int:
    print(PHASE_NOT_IMPLEMENTED)
    print(f"  Would apply action: {args.action_json}")
    return 0


def _cmd_pending(args: argparse.Namespace) -> int:
    state = _load_state(args.state_file)
    print(json.dumps(state.get("pending", []), indent=2, ensure_ascii=False))
    return 0


def _cmd_history(args: argparse.Namespace) -> int:
    state = _load_state(args.state_file)
    print(json.dumps(state.get("history", [])[-args.count:], indent=2, ensure_ascii=False))
    return 0


def _cmd_save(args: argparse.Namespace) -> int:
    state = _load_state(args.state_file)
    args.out.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True))
    print(f"Wrote {args.out}")
    return 0


def _cmd_load(args: argparse.Namespace) -> int:
    state = _load_state(args.state_file)
    print(f"Loaded {args.state_file}; scenario={state['meta'].get('scenario')}, "
          f"turn={state['meta'].get('turn')}, phase={state['meta'].get('phase')}")
    return 0


def _cmd_scenarios(args: argparse.Namespace) -> int:
    for s in list_scenarios():
        print(f"  {s['id']}: {s['name']}")
    return 0


# ----------------------------------------------------------- helpers
def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        # Synthetic stub keeps the CLI runnable even without a loaded scenario.
        return {
            "meta": {
                "scenario": "<unset>", "rules_edition": "living_rules_2023-04-10",
                "rng_seed": 0, "turn": 0, "phase": "levy", "active_player": "guelph",
                "game_over": False, "winner": None,
            },
            "calendar": {"boxes": {}, "off_left": [], "off_right": [],
                         "off_left_service": [], "off_right_service": [],
                         "end_box": None, "levy_box": 1},
            "lords": {}, "locales": {}, "decks": {},
            "capabilities_in_play": [], "pending": [], "history": [],
            "vp": {"guelph": 0.0, "ghibelline": 0.0},
        }
    return json.loads(path.read_text())


if __name__ == "__main__":
    sys.exit(main())
