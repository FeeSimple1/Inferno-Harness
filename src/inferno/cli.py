"""Inferno CLI: perspective-safe queries and version-bound player selections.

`do`, `play-event`, `save`, and the state file itself are trusted operator APIs.
LLMs should use briefing -> legal-moves/query/inspect -> choose.
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
    p_new.add_argument("--hidden-mats", action="store_true", help="Persist the Hidden Mats rule in the game.")
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
    p_state.add_argument("--side", choices=["guelph", "ghibelline"])
    p_state.add_argument("--raw", action="store_true", help="Trusted operator only: show unfiltered state; never send this to a player.")
    p_state.add_argument("--hidden-mats", action="store_true", help="Strengthen visibility; cannot disable a game rule.")
    p_state.set_defaults(func=_cmd_state)

    # ---- legal-moves ----
    p_legal = sub.add_parser("legal-moves", help="Enumerate legal actions.")
    p_legal.add_argument("state_file", type=Path)
    p_legal.add_argument("--side", choices=["guelph", "ghibelline"])
    p_legal.add_argument("--page", action="store_true", help="Retrieve entries instead of the category overview.")
    p_legal.add_argument("--category")
    p_legal.add_argument("--lord")
    p_legal.add_argument("--card")
    p_legal.add_argument("--where", help="JSON object of exact dotted-path filters.")
    p_legal.add_argument("--cursor")
    p_legal.add_argument("--page-size", type=int, default=12)
    p_legal.add_argument("--max-chars", type=int)
    p_legal.add_argument("--hidden-mats", action="store_true", help="Strengthen visibility; cannot disable a game rule.")
    p_legal.set_defaults(func=_cmd_legal_moves)

    p_query = sub.add_parser("query", help="Read a focused, versioned player query; never mutates the state.")
    p_query.add_argument("state_file", type=Path)
    p_query.add_argument("request_json")
    p_query.add_argument("--side", choices=["guelph", "ghibelline"])
    p_query.add_argument("--hidden-mats", action="store_true", help="Strengthen visibility; cannot disable a game rule.")
    p_query.set_defaults(func=_cmd_query)

    p_inspect = sub.add_parser("inspect", help="Page through full player-visible information records.")
    p_inspect.add_argument("state_file", type=Path)
    p_inspect.add_argument("section")
    p_inspect.add_argument("--keys", nargs="+")
    p_inspect.add_argument("--side", choices=["guelph", "ghibelline"])
    p_inspect.add_argument("--cursor")
    p_inspect.add_argument("--page-size", type=int, default=12)
    p_inspect.add_argument("--max-chars", type=int)
    p_inspect.add_argument("--hidden-mats", action="store_true", help="Strengthen visibility; cannot disable a game rule.")
    p_inspect.set_defaults(func=_cmd_inspect)

    p_choose = sub.add_parser("choose", help="Apply a player selection by state-bound ID; stale IDs never change the save.")
    p_choose.add_argument("state_file", type=Path)
    p_choose.add_argument("selection_json")
    p_choose.add_argument("--side", choices=["guelph", "ghibelline"])
    p_choose.add_argument("--out", type=Path)
    p_choose.add_argument("--decisions-json", default="[]", help="Prefix of complete tactical ID/version selections; never implicit defaults.")
    p_choose.add_argument("--decision-query", help="JSON focused lookup at the next unanswered tactical election.")
    p_choose.add_argument("--hidden-mats", action="store_true", help="Strengthen visibility; cannot disable a game rule.")
    p_choose.set_defaults(func=_cmd_choose)

    # ---- do ----
    p_do = sub.add_parser("do", help="Execute an action via dispatch() and persist the result.")
    p_do.add_argument("state_file", type=Path)
    p_do.add_argument("action_json", help='Action object as JSON, e.g. \'{"action":"levy_aow_draw","side":"guelph"}\'.')
    p_do.add_argument("--out", type=Path, default=None,
                      help="Write updated state here instead of in-place.")
    p_do.set_defaults(func=_cmd_do)

    # ---- pending / history / save / load ----
    p_pending = sub.add_parser("pending", help="List pending decisions.")
    p_pending.add_argument("state_file", type=Path)
    p_pending.add_argument("--side", choices=["guelph", "ghibelline"])
    p_pending.add_argument("--hidden-mats", action="store_true", help="Strengthen visibility; cannot disable a game rule.")
    p_pending.set_defaults(func=_cmd_pending)

    p_hist = sub.add_parser("history", help="Last N action results.")
    p_hist.add_argument("state_file", type=Path)
    p_hist.add_argument("-n", "--count", type=int, default=10)
    p_hist.add_argument("--side", choices=["guelph", "ghibelline"])
    p_hist.add_argument("--hidden-mats", action="store_true", help="Strengthen visibility; cannot disable a game rule.")
    p_hist.set_defaults(func=_cmd_history)

    p_save = sub.add_parser("save", help="Explicit save (pretty-prints to a new path).")
    p_save.add_argument("state_file", type=Path)
    p_save.add_argument("out", type=Path)
    p_save.set_defaults(func=_cmd_save)

    p_load = sub.add_parser("load", help="Validate a state file by loading it.")
    p_load.add_argument("state_file", type=Path)
    p_load.set_defaults(func=_cmd_load)

    # ---- briefing ----
    p_brief = sub.add_parser("briefing", help="Emit LLM-friendly briefing for a state file.")
    p_brief.add_argument("state_file", type=Path)
    p_brief.add_argument("--side", choices=["guelph", "ghibelline"])
    p_brief.add_argument("--hidden-mats", action="store_true",
                          help="Apply 1.5.2 Hidden Mats option to redaction.")
    p_brief.add_argument("--max-chars", type=int, default=3500)
    p_brief.add_argument("--json", action="store_true", help="Structured sections, status and retrieval metadata.")
    p_brief.set_defaults(func=_cmd_briefing)

    # ---- play-event ----
    p_ev = sub.add_parser("play-event", help="Play a Held Event card from this side's aow_held.")
    p_ev.add_argument("state_file", type=Path)
    p_ev.add_argument("--side", choices=["guelph", "ghibelline"], required=True)
    p_ev.add_argument("--card", required=True, help="Card id (e.g. F3).")
    p_ev.add_argument("--out", type=Path, default=None, help="Where to write updated state.")
    p_ev.set_defaults(func=_cmd_play_event)

    # ---- replay ----
    p_rp = sub.add_parser("replay", help="Re-execute a state file's history step by step.")
    p_rp.add_argument("state_file", type=Path)
    p_rp.add_argument("-n", "--count", type=int, default=None,
                       help="Stop after N actions (default: replay all).")
    p_rp.add_argument("--side", choices=["guelph", "ghibelline"])
    p_rp.add_argument("--hidden-mats", action="store_true", help="Strengthen visibility; cannot disable a game rule.")
    p_rp.set_defaults(func=_cmd_replay)

    p_sc = sub.add_parser("scenarios", help="List the six published scenarios.")
    p_sc.set_defaults(func=_cmd_scenarios)

    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 0
    from .actions import IllegalAction
    try:
        return args.func(args)
    except IllegalAction as exc:
        print(json.dumps({"error": exc.code, "message": str(exc), "state_changed": False}))
        return 1
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": "BAD_REQUEST", "message": str(exc), "state_changed": False}))
        return 2


# ----------------------------------------------------------- handlers
def _cmd_new(args: argparse.Namespace) -> int:
    state = load_scenario(args.scenario, seed=args.seed, hidden_mats=args.hidden_mats)
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
    from .llm.menu import acting_side
    from .llm.filter import hide_for_side
    if not args.raw:
        state = hide_for_side(state, args.side or acting_side(state), hidden_mats=args.hidden_mats)
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


def _player_view(args):
    from .llm import PlayerView
    return PlayerView(_load_state(args.state_file), getattr(args, "side", None), hidden_mats=getattr(args, "hidden_mats", False))


def _emit(value):
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _cmd_legal_moves(args: argparse.Namespace) -> int:
    view = _player_view(args)
    if args.page or any((args.category, args.lord, args.card, args.where, args.cursor)):
        request = {"request": "actions", "page_size": args.page_size}
        for key in ("category", "lord", "card", "cursor", "max_chars"):
            value = getattr(args, key)
            if value is not None:
                request[key] = value
        if args.where is not None:
            request["where"] = json.loads(args.where)
        _emit(view.query(request))
    else:
        _emit(view._catalog.overview())
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    _emit(_player_view(args).query(json.loads(args.request_json)))
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    request = {"request": "inspect", "section": args.section, "page_size": args.page_size}
    for key in ("keys", "cursor", "max_chars"):
        if getattr(args, key) is not None:
            request[key] = getattr(args, key)
    _emit(_player_view(args).query(request))
    return 0


def _cmd_choose(args: argparse.Namespace) -> int:
    from .llm import PlayerView, selection_session
    state = _load_state(args.state_file)
    view = PlayerView(state, args.side, hidden_mats=args.hidden_mats)
    answer = selection_session(state, view.side, json.loads(args.selection_json),
        decisions=json.loads(args.decisions_json),
        decision_request=json.loads(args.decision_query) if args.decision_query else None, hidden_mats=args.hidden_mats)
    if answer["status"] == "accepted":
        out_path = args.out or args.state_file
        out_path.write_text(json.dumps(state, ensure_ascii=False, indent=2))
        answer["saved"] = str(out_path)
    _emit(answer)
    return 0


def _cmd_do(args: argparse.Namespace) -> int:
    state = _load_state(args.state_file)
    from .actions import IllegalAction, dispatch
    try:
        action = json.loads(args.action_json)
    except json.JSONDecodeError as e:
        print(f"Invalid action JSON: {e}")
        return 2
    if not isinstance(action, dict) or "action" not in action:
        print('Action JSON must be an object with at least an "action" key, '
              'e.g. \'{"action": "levy_aow_draw", "side": "guelph"}\'.')
        return 2
    try:
        result = dispatch(state, action)
    except IllegalAction as e:
        print(f"IllegalAction[{e.code}]: {e}")
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    out_path = args.out or args.state_file
    out_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    print(f"Updated state at {out_path}")
    return 0


def _cmd_pending(args: argparse.Namespace) -> int:
    view = _player_view(args)
    _emit(view.query({"request": "inspect", "section": "pending"}))
    return 0


def _cmd_history(args: argparse.Namespace) -> int:
    if args.count < 1:
        raise ValueError("History count must be positive.")
    view = _player_view(args)
    total = len(view._catalog.view.get("history", []))
    keys = [str(i) for i in range(max(1, total-args.count+1), total+1)]
    page = view.query({"request": "inspect", "section": "history", "keys": keys, "page_size": args.count})
    page["earlier_records_deferred"] = max(total-args.count, 0)
    page["retrieve_all"] = {"request": "inspect", "section": "history"}
    _emit(page)
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



def _cmd_briefing(args: argparse.Namespace) -> int:
    from .llm import PlayerView, build_briefing_document, render_briefing
    state = _load_state(args.state_file)
    view = PlayerView(state, args.side, max_chars=args.max_chars, hidden_mats=args.hidden_mats)
    doc = build_briefing_document(state, view.side, args.max_chars, catalog=view._catalog)
    _emit(doc) if args.json else print(render_briefing(doc))
    return 0


def _cmd_play_event(args: argparse.Namespace) -> int:
    state = _load_state(args.state_file)
    from .actions import IllegalAction, dispatch
    try:
        result = dispatch(state, {
            "action": "play_event", "side": args.side,
            "args": {"card_id": args.card},
        })
    except IllegalAction as e:
        print(f"IllegalAction[{e.code}]: {e}")
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    out_path = args.out or args.state_file
    out_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    print(f"Updated state at {out_path}")
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    # Transcript display only; actual deterministic replay tools are separate.
    view = _player_view(args)
    history = view._catalog.view.get("history", [])
    shown = history if args.count is None else history[:args.count]
    print(f"Replaying transcript display: {len(shown)} whole records from {args.state_file}.")
    for i, h in enumerate(shown, 1):
        print(json.dumps({"index": i, "record": h}, ensure_ascii=False))
    if len(shown) != len(history):
        print(f"{len(history)-len(shown)} records deferred; query inspect/history for all pages.")
    return 0


# ----------------------------------------------------------- helpers
def _load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        from .actions import IllegalAction
        raise IllegalAction("STATE_NOT_FOUND", "No saved game at this path. Use new to initialize a scenario; no synthetic game was created.")
    return json.loads(path.read_text())


if __name__ == "__main__":
    sys.exit(main())
