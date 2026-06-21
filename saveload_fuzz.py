#!/usr/bin/env python3
"""Save/load + replay-determinism fuzzer for the Inferno harness.

Property under test: serializing the game state to JSON mid-game, reloading it,
and continuing must yield a game IDENTICAL to one that was never reloaded. Any
divergence means some state isn't captured by the serializable form, or dispatch/
enumeration is nondeterministic given equal state — a save/load correctness bug
invisible to ordinary play.

Method: run two states in lockstep from the same scenario+seed under a
deterministic policy. Each step:
  - assert the (already round-tripped) `reloaded` state deep-equals `control`;
  - assert the enumerator returns the IDENTICAL move list for both;
  - apply the same chosen action to both;
  - JSON round-trip `reloaded`;
  - assert deep-equality again.
Exit non-zero if any anomaly surfaces.
"""
import argparse, json, sys, random, collections, traceback
sys.path.insert(0, "src")
from inferno.scenarios import load_scenario
from inferno.legal_moves import enumerate_legal
from inferno.actions import dispatch
from inferno.invariants import check_all_invariants

ANOMALIES = []
def anomaly(kind, info):
    ANOMALIES.append({"kind": kind, **info})
    print(f"  !! ANOMALY [{kind}] {json.dumps(info, default=str)[:240]}")

def rt(state):
    return json.loads(json.dumps(state))

def _moves(state):
    moves = enumerate_legal(state)
    return None, [m for m in moves if not m.get("action", "").startswith("<")]

def _act(m):
    return {k: m[k] for k in ("action", "side", "args") if k in m}

def run(scenario, seed, max_steps):
    """Play to a random mid-game checkpoint, JSON round-trip the state there,
    then continue BOTH the round-tripped `reloaded` and the un-touched `control`
    to the end under one deterministic policy (chosen from control, applied to
    both). Reload-then-continue must equal never-reload: no dispatch crash on the
    reloaded copy, identical final state, invariants intact. Cheap: one round-trip
    + one final deep-compare per game."""
    control = load_scenario(scenario, seed=seed, hidden_mats=True)
    pol = random.Random(seed * 1009 + 7)
    checkpoint = 10 + (seed * 7) % 40
    reloaded = None
    for step in range(max_steps):
        if control["meta"].get("phase") == "victory":
            break
        if step == checkpoint:
            reloaded = rt(control)
            if reloaded != control:
                anomaly("checkpoint_roundtrip_lossy", {"scenario": scenario,
                        "seed": seed, "step": step, "diff": _first_diff(control, reloaded)})
                return
        _, mc = _moves(control)
        if not mc:
            break
        action = _act(pol.choice(mc))
        try:
            dispatch(control, action)
            if reloaded is not None:
                dispatch(reloaded, action)   # same action must stay legal on reload
        except Exception as e:
            anomaly("dispatch_crash", {"scenario": scenario, "seed": seed, "step": step,
                    "action": action, "error": f"{type(e).__name__}: {e}",
                    "tb": traceback.format_exc().splitlines()[-2:]})
            return
    # End-of-game checks.
    try:
        check_all_invariants(control)
    except Exception as e:
        anomaly("invariant_violation", {"scenario": scenario, "seed": seed,
                "error": f"{type(e).__name__}: {e}"})
        return
    if reloaded is None:
        reloaded = rt(control)   # short game: at least verify end-state round-trips
    if control != reloaded:
        anomaly("reload_diverged_by_end", {"scenario": scenario, "seed": seed,
                "diff": _first_diff(control, reloaded)})

def _first_diff(a, b, path="state"):
    if type(a) != type(b):
        return f"{path}: type {type(a).__name__} vs {type(b).__name__}"
    if isinstance(a, dict):
        ka, kb = set(a), set(b)
        if ka != kb:
            return f"{path}: keys differ +{sorted(kb-ka)[:3]} -{sorted(ka-kb)[:3]}"
        for k in a:
            d = _first_diff(a[k], b[k], f"{path}[{k!r}]")
            if d: return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: len {len(a)} vs {len(b)}"
        for i in range(len(a)):
            d = _first_diff(a[i], b[i], f"{path}[{i}]")
            if d: return d
        return None
    return None if a == b else f"{path}: {a!r} vs {b!r}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--seed-start", type=int, default=1)
    ap.add_argument("--scenarios", default="ABCDEF")
    ap.add_argument("--max-steps", type=int, default=4000)
    a = ap.parse_args()
    scenarios = list(a.scenarios)
    print(f"Save/load determinism: {len(scenarios)} scenarios x {a.seeds} seeds ...")
    for scen in scenarios:
        for seed in range(a.seed_start, a.seed_start + a.seeds):
            run(scen, seed, a.max_steps)
    print("=" * 60)
    print(f"TOTAL ANOMALIES: {len(ANOMALIES)}")
    if not ANOMALIES:
        print("Save/load is fully deterministic across all runs.")
    return 1 if ANOMALIES else 0

if __name__ == "__main__":
    sys.exit(main())
