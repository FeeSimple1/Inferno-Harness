#!/usr/bin/env python3
"""Illegal-state injection fuzzer — tests the INVARIANT BATTERY's own coverage.

The other fuzzers ask "does play ever corrupt the state?"; this one asks the
reverse: "if the state WERE corrupted, would the invariant battery notice?"
Method: play each scenario to several mid-game probe points under a
deterministic random-legal-move policy, then at each probe apply every
applicable corruption from a catalogue of subtle illegal-state mutations to a
fresh deep copy and assert `check_all_invariants` REJECTS it. An undetected
corruption is an anomaly (a coverage hole in the battery). The uncorrupted
copy must still PASS at every probe (guards against over-strict invariants).

Exit non-zero on any anomaly. Wired into CI next to the other fuzzers.
"""
import argparse, copy, json, random, sys
sys.path.insert(0, "src")
from inferno.scenarios import load_scenario
from inferno.legal_moves import enumerate_legal
from inferno.actions import dispatch
from inferno.invariants import check_all_invariants

ANOMALIES = []
APPLIED = {}

def anomaly(kind, info):
    ANOMALIES.append({"kind": kind, **info})
    print(f"  !! ANOMALY [{kind}] {json.dumps(info, default=str)[:240]}")


# ----------------------------------------------------------------------
# Corruption catalogue. Each takes a state and mutates it IN PLACE,
# returning a short description, or None if not applicable to this state.
# ----------------------------------------------------------------------
def _mustered(s):
    return [lid for lid, l in s["lords"].items() if l.get("status") == "mustered"]

def c_negative_force(s):
    for lid in _mustered(s):
        f = s["lords"][lid].get("forces") or {}
        if f:
            u = sorted(f)[0]
            f[u] = -1
            return f"{lid}.forces[{u}] = -1"
    return None

def c_negative_asset(s):
    for lid in _mustered(s):
        s["lords"][lid].setdefault("assets", {})["Coin"] = -2
        return f"{lid}.assets[Coin] = -2"
    return None

def c_vp_overflow(s):
    s["vp"]["guelph"] = 99.0
    return "vp.guelph = 99"

def c_bad_calendar_key(s):
    s["calendar"]["boxes"]["77"] = {"cylinders": [], "services": [],
                                    "victory": [], "markers": []}
    return "calendar box '77'"

def c_bad_status(s):
    lid = sorted(s["lords"])[0]
    s["lords"][lid]["status"] = "zombie"
    return f"{lid}.status = zombie"

def c_mustered_no_location(s):
    for lid in _mustered(s):
        s["lords"][lid]["location"] = None
        return f"{lid}.location = None"
    return None

def c_ghost_in_lords_present(s):
    for name, loc in s["locales"].items():
        loc.setdefault("lords_present", []).append("phantom_lord")
        return f"phantom in {name}"
    return None

def c_location_mismatch(s):
    for lid in _mustered(s):
        lord = s["lords"][lid]
        others = [n for n in s["locales"] if n != lord["location"]]
        lord["location"] = others[0]
        return f"{lid}.location changed without list update"
    return None

def c_duplicate_lords_present(s):
    for name, loc in s["locales"].items():
        lp = loc.get("lords_present") or []
        if lp:
            lp.append(lp[0])
            return f"{lp[0]} duplicated at {name}"
    return None

def c_colocated_enemies(s):
    ms = _mustered(s)
    gs = [l for l in ms if s["lords"][l]["side"] == "guelph"]
    hs = [l for l in ms if s["lords"][l]["side"] == "ghibelline"]
    if not gs or not hs or (s.get("pending") or []):
        return None
    a, b = gs[0], hs[0]
    la = s["lords"][a]["location"]
    lb = s["lords"][b]["location"]
    if la == lb:
        return None
    s["locales"][lb]["lords_present"].remove(b)
    s["locales"][la]["lords_present"].append(b)
    s["lords"][b]["location"] = la
    for lid in (a, b):
        fl = s["lords"][lid].setdefault("flags", {})
        fl.pop("in_stronghold", None)
        fl.pop("bypassing", None)
    return f"{a} and {b} co-located in the open at {la}"

def c_aow_card_loss(s):
    d = s["decks"]["guelph"]["aow_deck"]
    if d:
        d.pop()
        return "guelph AoW card removed"
    return None

def c_aow_card_dup(s):
    d = s["decks"]["guelph"]["aow_deck"]
    if d:
        d.append(d[0])
        return f"guelph AoW {d[0]} duplicated"
    return None

def c_bad_captured_side(s):
    s.setdefault("captured_knights", {})["martian"] = {"Cavalieri": 1}
    return "captured_knights['martian']"

def c_cylinder_dup(s):
    for lid, l in s["lords"].items():
        if l.get("status") == "on_calendar" and l.get("calendar_box"):
            other = "1" if str(l["calendar_box"]) != "1" else "2"
            s["calendar"]["boxes"].setdefault(other, {"cylinders": [], "services": [],
                                                      "victory": [], "markers": []})
            s["calendar"]["boxes"][other]["cylinders"].append(lid)
            return f"{lid} cylinder duplicated into box {other}"
    return None

def c_cylinder_mustered(s):
    for lid in _mustered(s):
        s["calendar"]["boxes"].setdefault("3", {"cylinders": [], "services": [],
                                                "victory": [], "markers": []})
        s["calendar"]["boxes"]["3"]["cylinders"].append(lid)
        return f"Mustered {lid} given a cylinder in box 3"
    return None

def c_cylinder_box_mismatch(s):
    for lid, l in s["lords"].items():
        if l.get("status") == "on_calendar" and l.get("calendar_box"):
            l["calendar_box"] = (l["calendar_box"] % 16) + 1
            return f"{lid}.calendar_box points at the wrong box"
    return None

def c_service_dup(s):
    for lid, l in s["lords"].items():
        if l.get("status") == "mustered" and l.get("service_box"):
            other = "1" if str(l["service_box"]) != "1" else "2"
            s["calendar"]["boxes"].setdefault(other, {"cylinders": [], "services": [],
                                                      "victory": [], "markers": []})
            s["calendar"]["boxes"][other]["services"].append(lid)
            return f"{lid} Service marker duplicated into box {other}"
    return None

def c_service_mismatch(s):
    for lid, l in s["lords"].items():
        if l.get("status") == "mustered" and l.get("service_box"):
            l["service_box"] = (l["service_box"] % 16) + 1
            return f"{lid}.service_box points at the wrong box"
    return None

def c_siege_on_ruins(s):
    for name, loc in s["locales"].items():
        if loc.get("siege"):
            loc["ruins"] = "gold"
            return f"Ruins placed under the Siege at {name}"
    return None

def c_siege_count_overflow(s):
    for name, loc in s["locales"].items():
        if loc.get("siege"):
            loc["siege"][0]["count"] = 9
            return f"Siege count 9 at {name}"
        if loc.get("type") in ("castle", "town", "city") and not loc.get("ruins"):
            loc["siege"] = [{"side": "guelph", "color": "purple", "count": 9}]
            return f"Siege count 9 planted at {name}"
    return None

def c_siege_color_mismatch(s):
    for name, loc in s["locales"].items():
        if loc.get("type") in ("castle", "town", "city") and not loc.get("ruins") \
                and not loc.get("siege"):
            loc["siege"] = [{"side": "guelph", "color": "gold", "count": 1}]
            return f"Guelph Siege with GOLD marker at {name}"
    return None

def c_allegiance_own_printed(s):
    for name, loc in s["locales"].items():
        if loc.get("type") in ("castle", "town", "city") and not loc.get("ruins") \
                and not (loc.get("current_allegiance") or []):
            loc["current_allegiance"] = [{"side": loc["allegiance"], "value": 1}]
            return f"printed-side Allegiance marker stacked at {name}"
    return None

def c_allegiance_overstack(s):
    for name, loc in s["locales"].items():
        if loc.get("type") == "castle" and not loc.get("ruins"):
            other = "ghibelline" if loc["allegiance"] == "guelph" else "guelph"
            loc["current_allegiance"] = [{"side": other, "value": 1}] * 2
            return f"2 Allegiance markers on Size-1 {name}"
    return None

def c_inside_at_ruins(s):
    for lid in _mustered(s):
        lord = s["lords"][lid]
        if lord.get("flags", {}).get("in_stronghold"):
            s["locales"][lord["location"]]["ruins"] = "purple"
            return f"{lid} inside a Stronghold now marked Ruins"
    return None

def c_overstuffed_stronghold(s):
    ms = _mustered(s)
    for lid in ms:
        lord = s["lords"][lid]
        loc = s["locales"][lord["location"]]
        if loc.get("type") == "castle" and not loc.get("ruins"):
            friends = [o for o in ms
                       if o != lid and s["lords"][o]["side"] == lord["side"]]
            if len(friends) >= 1:
                o = friends[0]
                lo = s["lords"][o]
                s["locales"][lo["location"]]["lords_present"].remove(o)
                loc["lords_present"].append(o)
                lo["location"] = lord["location"]
                for x in (lid, o):
                    s["lords"][x].setdefault("flags", {})["in_stronghold"] = True
                return f"2 Lords inside Size-1 {lord['location']}"
    return None

def c_stale_bypassing_flag(s):
    for lid in _mustered(s):
        lord = s["lords"][lid]
        other = next((n for n in s["locales"] if n != lord["location"]), None)
        if other:
            lord.setdefault("flags", {})["bypassing"] = other
            return f"{lid} flagged bypassing a Locale he is not at"
    return None

def c_rng_negative(s):
    s["meta"]["rng_advance"] = -3
    return "rng_advance = -3"

def c_bad_side(s):
    lid = sorted(s["lords"])[0]
    s["lords"][lid]["side"] = "roman"
    return f"{lid}.side = roman"

def c_bad_turn(s):
    s["meta"]["turn"] = 42
    return "meta.turn = 42"


CORRUPTIONS = [
    c_negative_force, c_negative_asset, c_vp_overflow, c_bad_calendar_key,
    c_bad_status, c_mustered_no_location, c_ghost_in_lords_present,
    c_location_mismatch, c_duplicate_lords_present, c_colocated_enemies,
    c_aow_card_loss, c_aow_card_dup, c_bad_captured_side,
    c_cylinder_dup, c_cylinder_mustered, c_cylinder_box_mismatch,
    c_service_dup, c_service_mismatch,
    c_siege_on_ruins, c_siege_count_overflow, c_siege_color_mismatch,
    c_allegiance_own_printed, c_allegiance_overstack,
    c_inside_at_ruins, c_overstuffed_stronghold,
    c_stale_bypassing_flag,
    c_rng_negative, c_bad_side, c_bad_turn,
]


def probe(state, scenario, seed, step):
    # 0) the uncorrupted state must PASS (no over-strict invariant).
    try:
        check_all_invariants(state)
    except AssertionError as e:
        anomaly("clean_state_rejected", {"scenario": scenario, "seed": seed,
                "step": step, "error": str(e)[:200]})
        return
    # 1) every applicable corruption must be DETECTED.
    for c in CORRUPTIONS:
        victim = copy.deepcopy(state)
        try:
            desc = c(victim)
        except Exception as e:
            anomaly("corruption_helper_crash", {"corruption": c.__name__,
                    "scenario": scenario, "seed": seed, "error": f"{type(e).__name__}: {e}"})
            continue
        if desc is None:
            continue
        APPLIED[c.__name__] = APPLIED.get(c.__name__, 0) + 1
        try:
            check_all_invariants(victim)
        except AssertionError:
            continue  # detected — good
        except Exception:
            continue  # any loud failure counts as detection
        anomaly("undetected_corruption", {"corruption": c.__name__, "desc": desc,
                "scenario": scenario, "seed": seed, "step": step})


def run(scenario, seed, max_steps, probe_every):
    s = load_scenario(scenario, seed=seed)
    pol = random.Random(seed * 7919 + 13)
    for step in range(max_steps):
        if s["meta"].get("phase") == "victory":
            break
        if step and step % probe_every == 0:
            probe(s, scenario, seed, step)
        moves = [m for m in enumerate_legal(s)
                 if not m.get("action", "").startswith("<")]
        if not moves:
            break
        m = pol.choice(moves)
        try:
            dispatch(s, {k: m[k] for k in ("action", "side", "args") if k in m})
        except Exception as e:
            anomaly("dispatch_crash", {"scenario": scenario, "seed": seed,
                    "step": step, "action": m.get("action"),
                    "error": f"{type(e).__name__}: {e}"})
            return
    probe(s, scenario, seed, "end")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default="ABCDEF")
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--max-steps", type=int, default=400)
    ap.add_argument("--probe-every", type=int, default=60)
    args = ap.parse_args()
    for sc in args.scenarios:
        for seed in range(1, args.seeds + 1):
            run(sc, seed, args.max_steps, args.probe_every)
    print(f"corruptions applied: { {k: v for k, v in sorted(APPLIED.items())} }")
    never = [c.__name__ for c in CORRUPTIONS if c.__name__ not in APPLIED]
    if never:
        print(f"NOTE: never applicable on these runs: {never}")
    print(f"TOTAL ANOMALIES: {len(ANOMALIES)}")
    if ANOMALIES:
        sys.exit(1)
    print("Every injected corruption was detected; clean states passed.")


if __name__ == "__main__":
    main()
