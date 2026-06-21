#!/usr/bin/env python3
"""Self-contained bug-hunt self-play driver for the Inferno harness.

No third-party dependencies (stdlib only). Run from the repo root:

    PYTHONPATH=src python selfplay_bughunt.py F --seed 11 --max-steps 8000

It drives a full game via the VALIDATED action palette (so an over-enumerated
move self-reports instead of crashing), asserts the always-on invariant battery
after every applied action, and prints a structured anomaly report. Replace
`choose()` with your own model's decision to hunt bugs with a smarter policy;
the default is a seeded aggressive/random policy.

Anything in the ANOMALIES list is a candidate engine defect: an over-enumerated
move, a dispatch crash, an invariant violation, or a deadlock. Cross-check
against reference/*.txt (Rules of Play + Errata are authoritative).
"""
import argparse, json, random, sys, traceback, collections
sys.path.insert(0, "src")

from inferno.scenarios import load_scenario
from inferno.legal_moves import enumerate_legal_validated
from inferno.actions import dispatch
from inferno.invariants import check_all_invariants, assert_combat_engaged
from inferno import static_data as sd

ANOMALIES = []
def anomaly(kind, info):
    ANOMALIES.append({"kind": kind, **info})
    print(f"  !! ANOMALY [{kind}] {json.dumps(info, default=str)[:200]}")

# --- default aggressive/random policy (replace with your model) ---
_ADJ = collections.defaultdict(set)
for _a, _b, _w in sd.WAYS:
    _ADJ[_a].add(_b); _ADJ[_b].add(_a)

def _bfs(start, targets):
    if start in targets: return 0
    seen, frontier, d = {start}, [start], 0
    while frontier:
        d += 1; nxt = []
        for n in frontier:
            for m in _ADJ[n]:
                if m in seen: continue
                if m in targets: return d
                seen.add(m); nxt.append(m)
        frontier = nxt
    return 999

def _enemy_locs(s, side):
    en = "ghibelline" if side == "guelph" else "guelph"; out = set()
    for lid, l in s["lords"].items():
        if l.get("side") == en and l.get("status") == "mustered" and l.get("location"):
            out.add(l["location"])
    for ln, l in s["locales"].items():
        if l.get("allegiance") == en: out.add(ln)
    return out

def choose(state, moves, rng):
    """Pick one move from `moves` (already validated-legal). Aggressive default."""
    for m in moves:
        if m["action"] == "approach_response" and m.get("args", {}).get("choice") == "stand":
            return m
    for act in ("cmd_play_ambush", "besiege_or_bypass", "cmd_storm", "cmd_sally"):
        c = [m for m in moves if m["action"] == act]
        if c: return rng.choice(c)
    marches = [m for m in moves if m["action"] in ("cmd_march", "cta_gather_march")]
    if marches:
        side = marches[0]["side"]; tg = _enemy_locs(state, side)
        if tg:
            best, bd = None, 10**9
            for m in marches:
                dest = m.get("args", {}).get("destination")
                if dest is None: continue
                d = _bfs(dest, tg)
                if d < bd: bd, best = d, m
            if best is not None: return best
        return rng.choice(marches)
    return rng.choice(moves)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=["A","B","C","D","E","F"])
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--max-steps", type=int, default=8000)
    a = ap.parse_args()

    s = load_scenario(a.scenario, seed=a.seed, hidden_mats=True)
    rng = random.Random(a.seed)
    steps = 0
    while s["meta"].get("phase") != "victory" and steps < a.max_steps:
        pal = enumerate_legal_validated(s)
        for d in pal["dropped"]:
            anomaly("over_enumeration", {"step": steps, "move": d["move"], "reason": d["reason"]})
        moves = [m for m in pal["moves"] if not m.get("action", "").startswith("<")]
        if not moves:
            if s["meta"].get("phase") != "victory":
                anomaly("deadlock", {"step": steps, "phase": s["meta"].get("phase"),
                                     "turn": s["meta"].get("turn")})
            break
        m = choose(s, moves, rng)
        action = {k: m[k] for k in ("action", "side", "args") if k in m}
        try:
            r = dispatch(s, action)
        except Exception as e:
            anomaly("dispatch_crash", {"step": steps, "action": action,
                                       "error": f"{type(e).__name__}: {e}",
                                       "tb": traceback.format_exc().splitlines()[-2:]})
            break
        # SMOKE-Inferno-098: flag any combat that should have engaged but didn't.
        sc = (r or {}).get("state_changes", {}) if isinstance(r, dict) else {}
        for key in ("storm_result", "battle_result", "sally_result"):
            try:
                assert_combat_engaged(sc.get(key))
            except AssertionError as e:
                anomaly("combat_inert", {"step": steps, "action": action, "detail": str(e)})
        try:
            check_all_invariants(s)
        except AssertionError as e:
            anomaly("invariant_violation", {"step": steps, "after": action, "detail": str(e)})
            break
        steps += 1

    print("=" * 60)
    print(f"scenario {a.scenario} seed {a.seed}: phase={s['meta'].get('phase')} "
          f"turn={s['meta'].get('turn')} winner={s['meta'].get('winner')} "
          f"VP={s.get('vp')} steps={steps}")
    print(f"TOTAL ANOMALIES: {len(ANOMALIES)}")
    if not ANOMALIES:
        print("No engine defects surfaced on this run.")
    # CI hook: non-zero exit if any anomaly surfaced, so a smoke run can gate a build.
    return 1 if ANOMALIES else 0

if __name__ == "__main__":
    sys.exit(main())
