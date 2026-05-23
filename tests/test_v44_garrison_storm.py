"""v4.5 regression: SMOKE-Inferno-097 — Storm against a Stronghold defended by
its Garrison ALONE (no Lord inside) must resolve real combat and be Sackable.
Found by a ChatGPT self-play of Scenario F (seed 11): a besieger Stormed a
garrison-only city and got an automatic attacker_loss with an EMPTY hit_log."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from inferno.scenarios import load_scenario
from inferno.battle import resolve_storm


def _setup(scenario, seed, stype, siege, forces):
    s = load_scenario(scenario, seed=seed)
    town = next(n for n, l in s["locales"].items() if l.get("type") == stype)
    loc = s["locales"][town]
    loc["siege"] = [{"side": "ghibelline", "color": "purple", "count": siege}]
    lid = "siena"
    old = s["lords"][lid]["location"]
    if old and lid in s["locales"].get(old, {}).get("lords_present", []):
        s["locales"][old]["lords_present"].remove(lid)
    s["lords"][lid]["location"] = town
    s["lords"][lid]["status"] = "mustered"
    if lid not in loc["lords_present"]:
        loc["lords_present"].append(lid)
    s["lords"][lid].setdefault("flags", {})["in_stronghold"] = False
    s["lords"][lid]["forces"] = dict(forces)
    return s, town, lid


def test_garrison_only_storm_resolves_real_combat():
    # A garrison-only city storm must produce strikes (not an empty no-op).
    s, town, lid = _setup("F", 1, "city", 3,
                          {"Cavalieri": 4, "Men-at-Arms": 4, "Armigieri": 4, "Militia": 4})
    res = resolve_storm(s, attackers=[lid], defenders=[], active_id=lid, locale_name=town)
    total_hits = sum(len(r["hit_log"]) for r in res["rounds"])
    assert total_hits > 0, "garrison-only Storm produced no strikes (the SMOKE-097 bug)"
    assert len(res["rolls"]) > 0
    # Combat actually happened: the garrison lost units and/or the attacker did.
    garr_units = sum(res["garrison_final"].values())
    atk_units = sum(s["lords"][lid].get("forces", {}).values())
    assert garr_units < 9 or atk_units < 16, "no losses on either side — combat was inert"


def test_garrison_only_stronghold_is_sackable():
    # Overwhelming attacker + max siege against a small (castle) garrison -> Sack.
    s, town, lid = _setup("F", 3, "castle", 4, {"Cavalieri": 12, "Men-at-Arms": 12})
    res = resolve_storm(s, attackers=[lid], defenders=[], active_id=lid, locale_name=town)
    assert res["outcome"] == "sack"
    assert sum(res["garrison_final"].values()) == 0   # garrison fully Routed


def test_undermanned_storm_still_loses():
    # Sanity: a weak attacker against a city garrison still loses (no false Sack).
    s, town, lid = _setup("F", 1, "city", 1, {"Militia": 1})
    res = resolve_storm(s, attackers=[lid], defenders=[], active_id=lid, locale_name=town)
    assert res["outcome"] == "attacker_loss"


# ---- SMOKE-Inferno-098: combat-engagement tripwire ----
def test_storm_result_reports_engaged():
    from inferno.invariants import assert_combat_engaged
    s, town, lid = _setup("F", 1, "city", 2, {"Cavalieri": 3, "Men-at-Arms": 3})
    res = resolve_storm(s, attackers=[lid], defenders=[], active_id=lid, locale_name=town)
    assert res["both_sides_armed"] is True
    assert res["engaged"] is True
    assert_combat_engaged(res)   # must not raise on a healthy combat


def test_tripwire_raises_on_inert_combat():
    import pytest
    from inferno.invariants import assert_combat_engaged
    # Simulate the SMOKE-097 signature: forces on both sides, zero strikes.
    inert = {"locale": "Siena", "mode": "storm", "outcome": "attacker_loss",
             "both_sides_armed": True, "engaged": False}
    with pytest.raises(AssertionError):
        assert_combat_engaged(inert)
    # And it must NOT fire when only one side was armed.
    assert_combat_engaged({"both_sides_armed": False, "engaged": False})
