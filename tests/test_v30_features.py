"""v3.0 — rule conformance audit fixes.

CONF-001 / SMOKE-Inferno-073: a Commander INSIDE his Leading City may Muster a
Ready Comune Sestiere/Terzo via a regular Levy action, rolling the vassal's
Muster die (Carroccio excluded — CtA only).
"""
import pytest
from inferno.scenarios import load_scenario
from inferno.actions import dispatch, IllegalAction
from inferno.rng import HarnessRNG


def _setup(seed=1):
    s = load_scenario("A", seed=seed)
    # Put Firenze (Commander) inside Firenze; bring out the Comune mat with a
    # Ready Sixth; set the Levy to step 3.4 with Guelph to act.
    s["meta"]["levy_step"] = "3.4"
    s["meta"]["active_player"] = "guelph"
    fz = s["lords"]["firenze"]
    if fz.get("location") != "Firenze":
        old = fz.get("location")
        if old and "firenze" in s["locales"].get(old, {}).get("lords_present", []):
            s["locales"][old]["lords_present"].remove("firenze")
        fz["location"] = "Firenze"
        s["locales"]["Firenze"].setdefault("lords_present", []).append("firenze")
    fz.setdefault("flags", {})["lordship_used"] = 0
    comune = s["lords"]["firenze_comune"]
    comune["status"] = "mustered"
    comune["location"] = "Firenze"
    comune["forces"] = {}
    # Initialize the Comune's special vassals (as CtA setup would).
    import inferno.static_data as sd
    from inferno.scenarios import _init_vassals_for
    comune["vassals"] = _init_vassals_for(sd.LORDS[comune["name"]])
    return s


def test_sestiere_later_muster_accepted():
    s = _setup()
    # Find a Ready non-special?? Sixths are special with muster_die. Pick one.
    sixth = next(v["name"] for v in s["lords"]["firenze_comune"]["vassals"]
                 if v.get("special") and "Sixth" in v["name"])
    for v in s["lords"]["firenze_comune"]["vassals"]:
        if v["name"] == sixth:
            v["ready"] = True; v["on_mat"] = False
    r = dispatch(s, {"action": "levy_muster_vassal", "side": "guelph",
                     "args": {"lord_id": "firenze", "vassal": sixth}})
    # Either mustered (roll<=die) or wasted (roll>die) — but NOT rejected.
    assert "die" in r["state_changes"]
    assert r["state_changes"].get("success") in (True, False)


def test_carroccio_still_cta_only():
    s = _setup()
    for v in s["lords"]["firenze_comune"]["vassals"]:
        if v["name"] == "Carroccio":
            v["ready"] = True; v["on_mat"] = False
    with pytest.raises(IllegalAction) as exc:
        dispatch(s, {"action": "levy_muster_vassal", "side": "guelph",
                     "args": {"lord_id": "firenze", "vassal": "Carroccio"}})
    assert exc.value.code == "CARROCCIO_CTA_ONLY"


def test_sestiere_rejected_when_commander_not_in_leading_city():
    s = _setup()
    # Move Firenze out of its Leading City.
    s["locales"]["Firenze"]["lords_present"].remove("firenze")
    s["lords"]["firenze"]["location"] = "Prato"
    s["locales"]["Prato"].setdefault("lords_present", []).append("firenze")
    sixth = next(v["name"] for v in s["lords"]["firenze_comune"]["vassals"]
                 if v.get("special") and "Sixth" in v["name"])
    for v in s["lords"]["firenze_comune"]["vassals"]:
        if v["name"] == sixth:
            v["ready"] = True
    with pytest.raises(IllegalAction) as exc:
        dispatch(s, {"action": "levy_muster_vassal", "side": "guelph",
                     "args": {"lord_id": "firenze", "vassal": sixth}})
    assert exc.value.code == "NOT_IN_LEADING_CITY"
