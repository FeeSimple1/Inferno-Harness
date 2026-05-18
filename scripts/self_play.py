"""Greedy self-play sweep for the Inferno harness.

Per CROSS_PROJECT_LESSONS §4 ("Different agent styles surface different
bug classes"): a greedy agent that picks the highest-priority legal
move from enumerate_legal() exercises every code path that the round-
trip sweep can't, because (a) it actually plays full turns instead of
just spot-checking each move, (b) it surfaces 'no_legal_moves' stalls
mid-game which round-trip can't detect.

Run from repo root:
  python3 scripts/self_play.py --scenarios A,B,C,D,E,F --seeds 1,2,3,42 \\
                                --max-actions 500 --output /tmp/self_play.json

Outputs a JSON summary listing per-(scenario, seed) outcome:
  - actions_played: count of dispatch calls
  - terminal_phase: phase at termination
  - stall: True if zero legal moves before victory
  - winner: side or None
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from inferno.actions import IllegalAction, dispatch
from inferno.legal_moves import enumerate_legal
from inferno.scenarios import SCENARIO_IDS, load_scenario


# Greedy priorities — higher score = picked first.
PRIORITY = {
    "levy_aow_draw":         100,
    "levy_pay_done":          90,
    "levy_disband":           95,
    "levy_disband_done":      80,
    "levy_muster_lord":       85,  # try to bring Lords on
    "levy_muster_vassal":     70,
    "levy_muster_capability": 50,
    "levy_muster_transport":  40,
    "levy_muster_done":        5,
    "levy_cta_skip":         100,  # always skip CtA in greedy
    "campaign_discard_done":  90,
    "campaign_discard_capability": 100,
    "plan_done":              90,
    "plan_add_card":          50,
    "command_reveal":        100,
    "cmd_tax":                80,
    "cmd_forage":             60,
    "cmd_supply":             50,
    "cmd_pass":               10,
    "cmd_end_card":           20,
    "cmd_march":              40,  # bias against random marching
    "cmd_ravage":             45,
    "cmd_sail":               30,
    "cmd_siege":              35,
    "cmd_storm":              35,
    "cmd_sally":              35,
    "cmd_treachery_revolt":   25,
    "cmd_treachery_bribe":    25,
    "cmd_depart":             40,
    "cmd_encamp":             35,
    "cmd_sortie":             35,
    "besiege_or_bypass":      55,  # the choice itself
    "approach_response":      90,  # decisive
    "plan_attach_lieutenant":  5,
    "end_grow":               90,
    "end_grow_skip":          80,
    "end_ransom":             80,
    "end_game_check":         95,
    "end_repair":             90,
    "end_waste":              80,
    "end_reset":             100,
    "play_event":              5,
}


def score_move(move):
    return PRIORITY.get(move.get("action"), 0)


def play_one(scenario_id, seed, max_actions=500):
    s = load_scenario(scenario_id, seed=seed)
    result = {
        "scenario": scenario_id, "seed": seed,
        "actions_played": 0, "terminal_phase": None, "stall": False,
        "winner": None, "error": None, "vp": None,
    }
    try:
        for step in range(max_actions):
            phase = s["meta"].get("phase")
            if phase == "victory":
                result["winner"] = s["meta"].get("winner")
                break
            moves = enumerate_legal(s)
            # Filter placeholder marker moves
            moves = [m for m in moves if not m.get("action", "").startswith("<")]
            if not moves:
                result["stall"] = True
                break
            chosen = max(moves, key=score_move)
            action = {"action": chosen["action"], "side": chosen["side"]}
            if "args" in chosen:
                action["args"] = chosen["args"]
            dispatch(s, action)
            result["actions_played"] += 1
        result["terminal_phase"] = s["meta"].get("phase")
        result["vp"] = dict(s.get("vp", {}))
    except IllegalAction as e:
        result["error"] = f"IllegalAction[{e.code}]: {e}"
        result["terminal_phase"] = s["meta"].get("phase")
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        result["traceback"] = traceback.format_exc()
        result["terminal_phase"] = s["meta"].get("phase")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", default=",".join(SCENARIO_IDS))
    parser.add_argument("--seeds", default="1,2,3,42")
    parser.add_argument("--max-actions", type=int, default=500)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    scenarios = args.scenarios.split(",")
    seeds = [int(x) for x in args.seeds.split(",")]
    results = []
    for sid in scenarios:
        for seed in seeds:
            r = play_one(sid, seed, max_actions=args.max_actions)
            results.append(r)
            status = "WIN " + (r["winner"] or "draw") if r["winner"] or r["terminal_phase"] == "victory" else (
                "STALL" if r["stall"] else ("ERR" if r["error"] else "TIMEOUT"))
            print(f"{sid} seed={seed:>4}: {status:>10} actions={r['actions_played']:>4} terminal={r['terminal_phase']}")
            if r["error"]:
                print(f"    error: {r['error']}")
    if args.output:
        args.output.write_text(json.dumps(results, indent=2))
        print(f"\nWrote {args.output}")
    # Exit code: nonzero if any errors
    if any(r["error"] for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
