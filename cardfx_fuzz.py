#!/usr/bin/env python3
"""Card-effect INTEGRATION fuzzer for the Inferno harness.

Round-3 goal (commercial-quality push): exercise all 52 Arts-of-War card
effects in LIVE combat / live state, not just their unit tests — especially
the Crossbow Capabilities (Balestrieri / Balestre Grosse / Garrison) that drive
the `select_target_unit` decision channel that no full self-play game ever hit.

Two phases:
  A. CAPABILITY x COMBAT: deploy each Capability, then resolve a Battle AND a
     Storm between two richly-stocked Lords, driving every choice with a
     random-valid callback. Assert invariants + combat-engaged after each.
  B. EVENT x LIVE STATE: invoke each Event effect on a live command-phase state
     across seeds/arg-variants; assert no crash + invariants hold.

Anything in ANOMALIES is a candidate defect. Exit non-zero if any surface.
"""
import argparse, json, random, sys, traceback, collections
sys.path.insert(0, "src")

from inferno.scenarios import load_scenario
from inferno.actions import dispatch
from inferno import battle as battle_mod
from inferno import card_data as cd
from inferno import card_effects as ce
from inferno.invariants import check_all_invariants, assert_combat_engaged
from inferno.rng import HarnessRNG

ANOMALIES = []
CHANNELS = collections.Counter()

def anomaly(kind, info):
    ANOMALIES.append({"kind": kind, **info})
    print(f"  !! ANOMALY [{kind}] {json.dumps(info, default=str)[:240]}")

# ---- bring a fresh scenario to Campaign command_phase (reuse test helper) ----
sys.path.insert(0, ".")
from tests.test_phase3b import _to_command_phase

RICH_ATT = {"Cavalieri": 2, "Armigieri": 2, "Men-at-Arms": 1, "Militia": 1, "Light Horse": 1}
RICH_DEF = {"Cavalieri": 1, "Ritter": 1, "Armigieri": 2, "Men-at-Arms": 1, "Villici": 1}

_UNIT_POOL = ["Ritter", "Cavalieri", "Berrovieri", "Light Horse",
              "Men-at-Arms", "Armigieri", "Militia", "Villici"]

def _rand_forces(rng):
    # always include Armigieri + Men-at-Arms so crossbow caps can fire, plus a
    # random tail to vary unit mixes (Palvesari/Luceria/Feditori targets, etc.)
    f = {"Armigieri": rng.randint(1, 3), "Men-at-Arms": rng.randint(1, 2)}
    for u in _UNIT_POOL:
        if rng.random() < 0.5:
            f[u] = f.get(u, 0) + rng.randint(1, 2)
    return f

def _mk_callback(rng):
    def cb(q):
        CHANNELS[q["type"]] += 1
        opts = q["options"]
        # optional channels: usually return a valid option to exercise them.
        return rng.choice(opts)
    return cb

def _deploy_capability(state, cid, side, lord_id):
    """Deploy a Capability into play WITHOUT breaking AoW card conservation:
    move the card out of the side's deck/held/discard pools and add it to
    exactly ONE play location (this-Lord -> the Lord's mat; else side-wide).
    `_lord_has_capability` (battle) checks the Lord mat then side-wide, and
    `capability_in_play` (card_effects) checks side-wide -- so each kind is
    registered where its consumers look."""
    from inferno.actions import _capability_is_this_lord
    card = cd.AOW_CARDS_BY_ID[cid]
    d = state["decks"][side]
    for pool in ("aow_deck", "aow_held", "aow_discard"):
        while cid in d.get(pool, []):
            d[pool].remove(cid)
    # also clear any stray copies so we add exactly one
    for l in state["lords"].values():
        while cid in (l.get("capabilities") or []):
            l["capabilities"].remove(cid)
    state["capabilities_in_play"] = [c for c in state.get("capabilities_in_play", [])
                                     if c.get("id") != cid]
    if _capability_is_this_lord(cid):
        state["lords"][lord_id].setdefault("capabilities", []).append(cid)
    else:
        state.setdefault("capabilities_in_play", []).append(
            {"id": cid, "name": card.get("capability_name"), "side": side, "scope": "side_wide"})

def _stage_battle(seed, cap_cid=None, cap_side="guelph"):
    s = _to_command_phase("A", seed=seed, lord_for_active="firenze")
    att, dfn = "firenze", "siena"
    s["lords"][att]["forces"] = _rand_forces(random.Random(seed*3+1))
    s["lords"][dfn]["forces"] = _rand_forces(random.Random(seed*3+2))
    s["lords"][att]["status"] = "mustered"
    s["lords"][dfn]["status"] = "mustered"
    if cap_cid:
        _deploy_capability(s, cap_cid, cap_side, att if cap_side == "guelph" else dfn)
    return s, att, dfn

def _stage_storm(seed, cap_cid=None, cap_side="guelph"):
    # Guelph Firenze storms Volterra (a Town) held by Ghibelline Siena inside.
    s = _to_command_phase("A", seed=seed, lord_for_active="firenze")
    loc = "Volterra"
    s["locales"][loc]["siege"] = [{"side": "guelph", "color": "purple", "count": 3}]
    att, dfn = "firenze", "siena"
    for lid in (att, dfn):
        cur = s["lords"][lid].get("location")
        if cur and lid in s["locales"].get(cur, {}).get("lords_present", []):
            s["locales"][cur]["lords_present"].remove(lid)
    s["lords"][att]["location"] = loc; s["locales"][loc]["lords_present"].append(att)
    s["lords"][dfn]["location"] = loc; s["locales"][loc]["lords_present"].append(dfn)
    s["lords"][dfn].setdefault("flags", {})["in_stronghold"] = True
    s["lords"][att]["forces"] = dict(RICH_ATT)
    s["lords"][dfn]["forces"] = dict(RICH_DEF)
    s["lords"][att]["status"] = "mustered"; s["lords"][dfn]["status"] = "mustered"
    if cap_cid:
        _deploy_capability(s, cap_cid, cap_side, att if cap_side == "guelph" else dfn)
    return s, att, dfn, loc

def _place(s, lid, loc):
    cur = s["lords"][lid].get("location")
    if cur and lid in s["locales"].get(cur, {}).get("lords_present", []):
        s["locales"][cur]["lords_present"].remove(lid)
    s["lords"][lid]["location"] = loc
    s["lords"][lid]["status"] = "mustered"
    s["locales"][loc].setdefault("lords_present", []).append(lid)

def _stage_battle_2v2(seed, rng, cap_cid=None, cap_side="guelph"):
    s = _to_command_phase("A", seed=seed, lord_for_active="firenze")
    atts, dfns = ["firenze", "lucca"], ["siena", "pisa"]
    # Park each side at a distinct Locale (same-side co-location is legal; we
    # never physically co-locate the two enemy sides — the Battle is resolved
    # via the id lists, and the post-combat invariants need valid locations).
    a_loc, d_loc = "Figline", "Asciano"
    for lid in (a_loc, d_loc):
        s["locales"][lid]["lords_present"] = []
    for lid in atts:
        _place(s, lid, a_loc); s["lords"][lid]["forces"] = _rand_forces(rng)
    for lid in dfns:
        _place(s, lid, d_loc); s["lords"][lid]["forces"] = _rand_forces(rng)
    if cap_cid:
        holder = atts[0] if cap_side == "guelph" else dfns[0]
        _deploy_capability(s, cap_cid, cap_side, holder)
    return s, atts, dfns

def _stage_sally(seed, rng, cap_cid=None, cap_side="guelph"):
    # Ghibelline Siena besieged inside Siena by Guelph Firenze; Siena Sallies.
    s = _to_command_phase("A", seed=seed, lord_for_active="siena")
    loc = "Siena"
    for lid in ("firenze", "siena"):
        cur = s["lords"][lid].get("location")
        if cur and lid in s["locales"].get(cur, {}).get("lords_present", []):
            s["locales"][cur]["lords_present"].remove(lid)
        s["lords"][lid]["location"] = loc
        s["locales"][loc]["lords_present"].append(lid)
    s["locales"][loc]["siege"] = [{"side": "guelph", "color": "purple", "count": 2}]
    s["lords"]["siena"].setdefault("flags", {})["in_stronghold"] = True
    s["lords"]["firenze"]["forces"] = _rand_forces(rng)
    s["lords"]["siena"]["forces"] = _rand_forces(rng)
    s["lords"]["firenze"]["status"] = "mustered"; s["lords"]["siena"]["status"] = "mustered"
    if cap_cid:
        holder = "siena" if cap_side == "ghibelline" else "firenze"
        _deploy_capability(s, cap_cid, cap_side, holder)
    return s, ["siena"], ["firenze"], loc

def fuzz_capability(cid, seeds):
    card = cd.AOW_CARDS_BY_ID[cid]
    side = card["side"]
    for seed in seeds:
        rng = random.Random(seed)
        # ---- Battle ----
        try:
            s, att, dfn = _stage_battle(seed, cid, side)
            res = battle_mod.resolve_battle(s, [att], [dfn], att, s["lords"][att]["location"] or "Figline",
                                            callback=_mk_callback(rng))
            assert_combat_engaged(res)
            check_all_invariants(s)
        except Exception as e:
            anomaly("capability_battle_crash", {"card": cid, "cap": card.get("capability_name"),
                    "seed": seed, "error": f"{type(e).__name__}: {e}",
                    "tb": traceback.format_exc().splitlines()[-2:]})
        # ---- Storm ----
        try:
            s, att, dfn, loc = _stage_storm(seed, cid, side)
            res = battle_mod.resolve_storm(s, [att], [dfn], att, loc, callback=_mk_callback(rng))
            assert_combat_engaged(res)
            check_all_invariants(s)
        except Exception as e:
            anomaly("capability_storm_crash", {"card": cid, "cap": card.get("capability_name"),
                    "seed": seed, "error": f"{type(e).__name__}: {e}",
                    "tb": traceback.format_exc().splitlines()[-2:]})
        # ---- 2v2 Battle (flanking / reserve / reposition / multi-round) ----
        try:
            s, atts, dfns = _stage_battle_2v2(seed, random.Random(seed * 7 + 1), cid, side)
            res = battle_mod.resolve_battle(s, atts, dfns, atts[0],
                                            s["lords"][atts[0]]["location"] or "Figline",
                                            callback=_mk_callback(rng))
            assert_combat_engaged(res); check_all_invariants(s)
        except Exception as e:
            anomaly("capability_battle2v2_crash", {"card": cid, "cap": card.get("capability_name"),
                    "seed": seed, "error": f"{type(e).__name__}: {e}",
                    "tb": traceback.format_exc().splitlines()[-2:]})
        # ---- Sally ----
        try:
            s, sal, bes, loc = _stage_sally(seed, random.Random(seed * 13 + 2), cid, side)
            res = battle_mod.resolve_sally(s, sal, bes, sal[0], loc, callback=_mk_callback(rng))
            assert_combat_engaged(res); check_all_invariants(s)
        except Exception as e:
            anomaly("capability_sally_crash", {"card": cid, "cap": card.get("capability_name"),
                    "seed": seed, "error": f"{type(e).__name__}: {e}",
                    "tb": traceback.format_exc().splitlines()[-2:]})

def fuzz_event(cid, seeds):
    card = cd.AOW_CARDS_BY_ID[cid]
    side = card["side"]
    arg_variants = [{}, {"mode": "treachery"}, {"mode": "service"},
                    {"revolt_count": 1}, {"target": "firenze"}, {"targets": ["siena", "pisa"]}]
    for seed in seeds:
        for args in arg_variants:
            try:
                s = _to_command_phase("A", seed=seed, lord_for_active="firenze")
                rng = HarnessRNG(seed=seed)
                # Faithfully mimic the dispatcher's play path so AoW card
                # conservation stays a REAL signal: a played Event leaves the
                # hand; if the effect didn't turn it into a duration/Capability
                # in play, it goes to discard (spent).
                d = s["decks"][side]
                # Reset the card to a CLEAN in-hand state (undo whatever the
                # Levy setup drew/deployed it into), so conservation is exact
                # and seed-independent: exactly one copy, in hand, none in play.
                for pool in ("aow_deck", "aow_held", "aow_discard"):
                    while cid in d.get(pool, []):
                        d[pool].remove(cid)
                for kind in ("immediate", "this_levy", "this_campaign"):
                    lst = s.get("active_events", {}).get(kind, [])
                    s.setdefault("active_events", {})[kind] = [e for e in (lst or []) if e.get("id") != cid]
                s["capabilities_in_play"] = [c for c in s.get("capabilities_in_play", []) if c.get("id") != cid]
                for l in s["lords"].values():
                    while cid in (l.get("capabilities") or []):
                        l["capabilities"].remove(cid)
                ce.apply_event_effect(s, cid, side, dict(args), rng)
                def _in_play(cc):
                    for kind in ("immediate", "this_levy", "this_campaign"):
                        if any(e.get("id") == cc for e in (s.get("active_events", {}).get(kind, []) or [])):
                            return True
                    if any(c.get("id") == cc for c in s.get("capabilities_in_play", [])):
                        return True
                    return any(cc in (l.get("capabilities") or []) for l in s["lords"].values())
                if not _in_play(cid):
                    d["aow_discard"].append(cid)
                check_all_invariants(s)
            except Exception as e:
                # Many events legitimately reject bad args via IllegalAction —
                # only flag non-IllegalAction crashes + invariant breaks.
                if type(e).__name__ in ("IllegalAction", "ScriptedDecisionError"):
                    continue
                anomaly("event_crash", {"card": cid, "event": card.get("event_name"),
                        "seed": seed, "args": args, "error": f"{type(e).__name__}: {e}",
                        "tb": traceback.format_exc().splitlines()[-2:]})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--only", default=None, help="comma-separated card ids")
    a = ap.parse_args()
    seeds = list(range(1, a.seeds + 1))
    cards = [c["id"] for c in (cd.GUELPH_CARDS + cd.GHIBELLINE_CARDS)]
    if a.only:
        only = set(a.only.split(","))
        cards = [c for c in cards if c in only]
    print(f"Fuzzing {len(cards)} cards x {len(seeds)} seeds (capability combats + events)...")
    for cid in cards:
        fuzz_capability(cid, seeds)
        fuzz_event(cid, seeds)
    print("=" * 64)
    print("Decision channels exercised:", dict(CHANNELS))
    print("select_target_unit fired:", CHANNELS.get("select_target_unit", 0))
    print(f"TOTAL ANOMALIES: {len(ANOMALIES)}")
    if not ANOMALIES:
        print("No card-effect integration defects surfaced.")
    return 1 if ANOMALIES else 0

if __name__ == "__main__":
    sys.exit(main())
