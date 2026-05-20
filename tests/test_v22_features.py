"""v2.2 — Sally uses the Storm-style Array (Battle&Storm 2.3).

  #5 SMOKE-Inferno-056: Sally Array (1 Front per side + Reserves up to Stronghold
     Size + forced promotion) with the Besiegers defending behind Siegeworks =
     # Siege markers, and the Sallying side getting no Walls / no Garrison.
"""
import copy
import inspect
import pytest

from inferno.scenarios import load_scenario
from inferno import static_data as sd
from inferno.battle import resolve_sally, _resolve_step
import inferno.actions as A

CASTLE = "Vecliano"
SALLYER = "arezzo"        # Guelph (besieged, sallying)
BESIEGER = "siena"        # Ghibelline (besieging)


def _besieged_setup(seed=1, siege_count=4, extra_besiegers=()):
    s = load_scenario("A", seed=seed)
    loc = s["locales"][CASTLE]
    loc["ruins"] = None
    # Place the Sallying Lord inside the Castle.
    for lid in [SALLYER, BESIEGER, *extra_besiegers]:
        l = s["lords"][lid]
        old = l.get("location")
        if old and lid in s["locales"].get(old, {}).get("lords_present", []):
            s["locales"][old]["lords_present"].remove(lid)
        l["location"] = CASTLE
        loc.setdefault("lords_present", []).append(lid)
        l["status"] = "mustered"
    s["lords"][SALLYER].setdefault("flags", {})["in_stronghold"] = True
    # Besiegers: outside the Stronghold, with forces.
    for lid in [BESIEGER, *extra_besiegers]:
        s["lords"][lid].setdefault("flags", {})["in_stronghold"] = False
        if sum(s["lords"][lid].get("forces", {}).values()) == 0:
            s["lords"][lid]["forces"] = {"Cavalieri": 1, "Men-at-Arms": 1}
    loc["siege"] = [{"side": "ghibelline", "color": "purple", "count": siege_count}]
    return s


class TestSallyArray:
    def test_result_shape_is_sally(self):
        s = _besieged_setup()
        r = resolve_sally(s, sallying=[SALLYER], besiegers=[BESIEGER],
                          active_id=SALLYER, locale_name=CASTLE)
        assert r["mode"] == "sally"
        assert r["winner"] in ("attacker", "defender")
        assert r["loser"] in ("attacker", "defender")
        assert r["siege_count"] == 4
        assert r["stronghold_size"] == sd.STRONGHOLDS["castle"]["size"]
        assert isinstance(r["removed_lords"], list)

    def test_siegeworks_fully_protect_besiegers(self):
        # Siege count high enough that the Siegeworks die range (1..N) covers a
        # whole d6 -> EVERY Hit against the Besiegers is cancelled, so they take
        # no losses and the Sally cannot succeed.
        s = _besieged_setup(siege_count=10)
        orig = sum(s["lords"][BESIEGER]["forces"].values())
        r = resolve_sally(s, sallying=[SALLYER], besiegers=[BESIEGER],
                          active_id=SALLYER, locale_name=CASTLE)
        assert sum(s["lords"][BESIEGER]["forces"].values()) == orig  # untouched
        assert r["loser"] == "attacker"   # Besiegers hold; Sally fails
        assert BESIEGER not in r["removed_lords"]

    def test_attacker_gets_no_walls(self):
        # Same setup with NO Siegeworks vs FULL Siegeworks, same seed: the
        # Besiegers fare at least as well WITH Siegeworks (the Sallying attacker
        # never gets Walls, so its losses are unaffected by siege count).
        base = _besieged_setup(siege_count=10)
        protected = copy.deepcopy(base)
        rp = resolve_sally(protected, sallying=[SALLYER], besiegers=[BESIEGER],
                           active_id=SALLYER, locale_name=CASTLE)
        unprot = copy.deepcopy(base)
        unprot["locales"][CASTLE]["siege"] = [{"side": "ghibelline", "color": "purple", "count": 0}]
        ru = resolve_sally(unprot, sallying=[SALLYER], besiegers=[BESIEGER],
                           active_id=SALLYER, locale_name=CASTLE)
        besieger_protected = sum(protected["lords"][BESIEGER]["forces"].values())
        besieger_unprot = sum(unprot["lords"][BESIEGER]["forces"].values())
        assert besieger_protected >= besieger_unprot

    def test_castle_array_caps_front_at_size_one(self):
        # At a Castle (Size 1) extra Besiegers stay in Reserve; with full
        # Siegeworks the Front Besieger never Routs, so no forced promotion.
        s = _besieged_setup(siege_count=10, extra_besiegers=("provenzano",))
        r = resolve_sally(s, sallying=[SALLYER], besiegers=[BESIEGER, "provenzano"],
                          active_id=SALLYER, locale_name=CASTLE)
        assert "provenzano" in r["reserve_final"]["defender"]

    def test_handler_uses_resolve_sally(self):
        assert "resolve_sally" in inspect.getsource(A._h_cmd_sally)

    def test_marker_present(self):
        assert "SMOKE-Inferno-056" in inspect.getsource(resolve_sally)
