#!/usr/bin/env python3
"""Adversarial input / robustness fuzzer for the Inferno dispatch boundary.

A NEW technique (round-3 #3): instead of driving valid play, it feeds every
handler MALFORMED / ILLEGAL / mutated arguments and asserts the dispatch
contract holds:

  1. dispatch ALWAYS rejects bad input with IllegalAction — never a bare
     KeyError/TypeError/IndexError/AttributeError/ValueError/AssertionError
     (a bare exception = a handler that read args without validating).
  2. A REJECTED action leaves the state byte-identical (validate-then-mutate /
     transactional — no half-applied mutation on the failure path).
  3. Any ACCEPTED action leaves the always-on invariants intact.

The game itself is advanced only with VALID palette moves; each mutation is
tried on an isolated JSON copy so probes never perturb the main line.

Exit non-zero if any anomaly surfaces.
"""
import argparse, json, random, sys, traceback, collections
sys.path.insert(0, "src")
from inferno.scenarios import load_scenario
from inferno.legal_moves import enumerate_legal
from inferno.actions import dispatch, IllegalAction
from inferno.invariants import check_all_invariants
from inferno import static_data as sd

ANOMALIES = []
KINDS = collections.Counter()
def anomaly(kind, info):
    ANOMALIES.append({"kind": kind, **info})
    print(f"  !! ANOMALY [{kind}] {json.dumps(info, default=str)[:260]}")

def rt(s): return json.loads(json.dumps(s))

ALL_ACTIONS = None
def _all_action_names():
    global ALL_ACTIONS
    if ALL_ACTIONS is None:
        import inferno.actions as A
        ALL_ACTIONS = sorted(A._HANDLERS.keys())
    return ALL_ACTIONS

GARBAGE_ARGS = [
    {}, {"lord_id": "DOES_NOT_EXIST"}, {"lord_id": None}, {"lord_id": 12345},
    {"lord_id": ""}, {"target_locale": "Nowhere"}, {"target_locale": None},
    {"amount": -5}, {"amount": 99999}, {"amount": "lots"}, {"amount": None},
    {"choice": "garbage"}, {"choice": None}, {"destination": "Nowhere"},
    {"source": "Nowhere"}, {"way_type": "teleport"}, {"provender": -3},
    {"slides": "nope"}, {"target_seat": "Nowhere"}, {"placements": "bad"},
    {"card_id": "ZZ99"}, {"revolt_count": -1}, {"mode": "bogus"},
]

def _mutations(state, legal, rng):
    """A batch of mutated/illegal actions for the current state."""
    muts = []
    sides = ["guelph", "ghibelline"]
    lords = list(state.get("lords", {}).keys())
    locales = list(state.get("locales", {}).keys())
    names = _all_action_names()
    # 1. unknown action names
    muts.append({"action": "totally_made_up", "side": rng.choice(sides)})
    muts.append({"action": "", "side": rng.choice(sides)})
    # 2/3. known action + garbage args, both sides
    for _ in range(6):
        muts.append({"action": rng.choice(names), "side": rng.choice(sides),
                     "args": dict(rng.choice(GARBAGE_ARGS))})
    # 4. random action + random plausible-but-likely-illegal args
    for _ in range(6):
        muts.append({"action": rng.choice(names), "side": rng.choice(sides),
                     "args": {"lord_id": rng.choice(lords) if lords else "x",
                              "target_locale": rng.choice(locales) if locales else "x",
                              "destination": rng.choice(locales) if locales else "x",
                              "amount": rng.randint(-3, 9),
                              "choice": rng.choice(["besiege", "bypass", "stand", "avoid", "x"])}})
    # 5. take a LEGAL move and mutate ONE field (the CONF-015 class)
    for m in legal[:6]:
        base = {k: m[k] for k in ("action", "side", "args") if k in m}
        a = json.loads(json.dumps(base))
        a.setdefault("args", {})
        f = rng.choice(["side", "lord_id", "target_locale", "destination", "amount"])
        if f == "side":
            a["side"] = "guelph" if a.get("side") == "ghibelline" else "ghibelline"
        elif f == "lord_id":
            a["args"]["lord_id"] = rng.choice(lords) if lords else "x"
        else:
            a["args"][f] = rng.choice(locales) if locales and f in ("target_locale", "destination") else rng.randint(-2, 50)
        muts.append(a)
    # 6. malformed envelopes
    muts.append({"action": rng.choice(names)})                       # no side
    muts.append({"action": rng.choice(names), "side": "neither"})    # bad side
    muts.append({"action": rng.choice(names), "side": rng.choice(sides), "args": None})
    return muts

ALLOWED = (IllegalAction,)

def probe(state, scen, seed, step, rng):
    legal = [m for m in enumerate_legal(state) if not m.get("action", "").startswith("<")]
    for m in _mutations(state, legal, rng):
        c = rt(state)
        before = rt(c)
        try:
            dispatch(c, m)
        except IllegalAction:
            KINDS["clean_reject"] += 1
            if c != before:
                anomaly("reject_mutated_state", {"scen": scen, "seed": seed, "step": step,
                        "action": m.get("action"), "diff": _first_diff(before, c)})
        except Exception as e:
            anomaly("bare_crash", {"scen": scen, "seed": seed, "step": step,
                    "action": m.get("action"), "args": m.get("args"),
                    "error": f"{type(e).__name__}: {e}",
                    "tb": traceback.format_exc().splitlines()[-2:]})
        else:
            KINDS["accepted"] += 1
            try:
                check_all_invariants(c)
            except Exception as e:
                anomaly("invariant_after_accept", {"scen": scen, "seed": seed, "step": step,
                        "action": m.get("action"), "args": m.get("args"),
                        "error": f"{type(e).__name__}: {e}"})

def _first_diff(a, b, path="s"):
    if type(a) != type(b): return f"{path}:type {type(a).__name__}/{type(b).__name__}"
    if isinstance(a, dict):
        for k in set(a) | set(b):
            if k not in a or k not in b: return f"{path}:key {k}"
            d = _first_diff(a[k], b[k], f"{path}.{k}")
            if d: return d
        return None
    if isinstance(a, list):
        if len(a) != len(b): return f"{path}:len {len(a)}/{len(b)}"
        for i in range(len(a)):
            d = _first_diff(a[i], b[i], f"{path}[{i}]")
            if d: return d
        return None
    return None if a == b else f"{path}:{a!r}/{b!r}"

def run(scen, seed, max_steps, probe_every):
    s = load_scenario(scen, seed=seed, hidden_mats=True)
    pol = random.Random(seed * 131 + 5)
    mrng = random.Random(seed * 977 + 13)
    for step in range(max_steps):
        if s["meta"].get("phase") == "victory":
            break
        if step % probe_every == 0:
            probe(s, scen, seed, step, mrng)
        legal = [m for m in enumerate_legal(s) if not m.get("action", "").startswith("<")]
        if not legal:
            break
        m = pol.choice(legal)
        try:
            dispatch(s, {k: m[k] for k in ("action", "side", "args") if k in m})
        except Exception as e:
            anomaly("valid_move_crash", {"scen": scen, "seed": seed, "step": step,
                    "action": m.get("action"), "error": f"{type(e).__name__}: {e}"})
            break

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--scenarios", default="ABCDEF")
    ap.add_argument("--max-steps", type=int, default=4000)
    ap.add_argument("--probe-every", type=int, default=8)
    a = ap.parse_args()
    print(f"Robustness fuzz: {len(a.scenarios)} scenarios x {a.seeds} seeds, probing every {a.probe_every} steps...")
    for scen in a.scenarios:
        for seed in range(1, a.seeds + 1):
            run(scen, seed, a.max_steps, a.probe_every)
    print("=" * 60)
    print("probe outcomes:", dict(KINDS))
    print(f"TOTAL ANOMALIES: {len(ANOMALIES)}")
    if not ANOMALIES:
        print("Dispatch rejected all bad input cleanly and transactionally.")
    return 1 if ANOMALIES else 0

if __name__ == "__main__":
    sys.exit(main())
