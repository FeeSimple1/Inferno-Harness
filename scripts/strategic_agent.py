"""Combat-weighted strategic agent (CROSS_PROJECT_LESSONS §4).

The greedy agent in self_play.py avoids combat. A second agent style
that *weights combat shapes high* finds different bug classes — per
the Nevsky postmortem, SMOKE-118 (levy_capability over-enumeration)
and SMOKE-119 (concede arg shape) were both caught by the strategic
agent because it actually opens battles and stands them.

Priority delta vs greedy:
  cmd_storm:  92 (was 35)
  cmd_sally:  88 (was 35)
  cmd_siege:  85 (was 35)
  cmd_march:  78 (was 40)  — aggressive march
  cmd_treachery_revolt: 75
  cmd_treachery_bribe:  72
  approach_response 'stand': prefer Stand over Avoid/Withdraw

The agent runs the full Inferno scenario set across seeds; any
'no_legal_moves' stall mid-game, any unhandled IllegalAction, or any
run that doesn't terminate is a candidate SMOKE for
SMOKE_TEST_FINDINGS.md.

Run from repo root:
  python3 scripts/strategic_agent.py --scenarios A,B,C,D,E,F \\
                                     --seeds 1,2,3,7,42,100 \\
                                     --max-actions 1500
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from inferno.actions import IllegalAction, dispatch
from inferno.legal_moves import enumerate_legal
from inferno.scenarios import SCENARIO_IDS, load_scenario


STRATEGIC_PRIORITY = {
    # Phase machinery — high so we get through admin quickly
    "levy_aow_draw": 100,
    "campaign_discard_done": 95,
    "campaign_discard_capability": 100,
    "plan_done": 95,
    "command_reveal": 100,
    "end_grow": 90,
    "end_grow_skip": 80,
    "end_ransom": 80,
    "end_game_check": 100,
    "end_repair": 95,
    "end_waste": 80,
    "end_reset": 100,
    "levy_pay_done": 60,
    "levy_disband_done": 80,
    "levy_muster_done": 30,  # lower than muster_lord so we Muster aggressively
    "levy_cta_skip": 60,
    # Combat shapes — high
    "cmd_storm": 92,
    "cmd_sally": 88,
    "cmd_siege": 85,
    "cmd_march": 78,
    "besiege_or_bypass": 85,
    "approach_response": 95,  # decisive; tier-broken below
    "cmd_treachery_revolt": 75,
    "cmd_treachery_bribe": 72,
    "cmd_ravage": 65,
    "cmd_forage": 55,
    "cmd_tax": 50,
    "cmd_supply": 40,
    "cmd_sail": 30,
    "cmd_pass": 5,
    "cmd_end_card": 10,
    "cmd_depart": 50,
    "cmd_encamp": 60,
    "cmd_sortie": 70,
    "levy_muster_lord": 80,
    "levy_muster_vassal": 60,
    "levy_muster_transport": 35,
    "levy_muster_capability": 50,
    "plan_add_card": 50,
    "plan_attach_lieutenant": 20,
    "play_event": 40,
}


def score(move):
    base = STRATEGIC_PRIORITY.get(move.get("action"), 0)
    # Tier-break for approach_response: prefer Stand
    if move.get("action") == "approach_response":
        choice = move.get("args", {}).get("choice")
        if choice == "stand":
            base += 5
        elif choice == "withdraw":
            base -= 3
    # Prefer besiege over bypass (more aggressive)
    if move.get("action") == "besiege_or_bypass":
        if move.get("args", {}).get("choice") == "besiege":
            base += 3
    return base


def play_one(scenario_id, seed, max_actions):
    s = load_scenario(scenario_id, seed=seed)
    result = {
        "scenario": scenario_id, "seed": seed,
        "actions_played": 0, "terminal_phase": None,
        "stall": False, "winner": None, "error": None, "vp": None,
        "combat_events": 0,
    }
    try:
        for step in range(max_actions):
            phase = s["meta"].get("phase")
            if phase == "victory":
                result["winner"] = s["meta"].get("winner")
                break
            moves = enumerate_legal(s)
            moves = [m for m in moves if not m.get("action", "").startswith("<")]
            if not moves:
                result["stall"] = True
                break
            chosen = max(moves, key=score)
            action = {"action": chosen["action"], "side": chosen["side"]}
            if "args" in chosen:
                action["args"] = chosen["args"]
            if chosen["action"] in ("cmd_storm", "cmd_sally", "cmd_siege"):
                result["combat_events"] += 1
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
    parser.add_argument("--seeds", default="1,2,3,7,42,100")
    parser.add_argument("--max-actions", type=int, default=1500)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    scenarios = args.scenarios.split(",")
    seeds = [int(x) for x in args.seeds.split(",")]
    results = []
    for sid in scenarios:
        for seed in seeds:
            r = play_one(sid, seed, args.max_actions)
            results.append(r)
            status = ("WIN " + (r["winner"] or "draw")) if r["winner"] or r["terminal_phase"] == "victory" else (
                "STALL" if r["stall"] else ("ERR" if r["error"] else "TIMEOUT"))
            print(f"{sid} seed={seed:>4}: {status:>9} actions={r['actions_played']:>4} combat={r['combat_events']:>2} terminal={r['terminal_phase']}")
            if r["error"]:
                print(f"    error: {r['error']}")
    if args.output:
        args.output.write_text(json.dumps(results, indent=2))
        print(f"\nWrote {args.output}")
    if any(r["error"] for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
