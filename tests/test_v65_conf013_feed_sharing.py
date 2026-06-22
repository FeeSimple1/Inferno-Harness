"""v6.5 — CONF-013: Feed Sharing (1.5.2) in the 4.8.1 Feed step.

A Moved/Fought Lord that cannot fully feed from his OWN Provender/Loot must be
fed by co-located Friendly Mustered Lords sharing their surplus BEFORE he is left
Unfed (Service shift). A Lord still short after Sharing consumes what was
available and shifts Service 1 box left. The prior Feed fed each Lord from his
own assets only (Sharing was deferred).
"""
from __future__ import annotations

from inferno.actions import _run_fpd
from inferno.scenarios import load_scenario


def _bare_state():
    s = load_scenario("A", seed=1)
    s["meta"]["phase"] = "campaign"
    return s


def _put(s, lid, loc, forces, prov=0, loot=0, svc=8):
    s["lords"][lid]["status"] = "mustered"
    s["lords"][lid]["location"] = loc
    s["lords"][lid]["forces"] = dict(forces)
    s["lords"][lid]["assets"]["Provender"] = prov
    s["lords"][lid]["assets"]["Loot"] = loot
    s["lords"][lid]["service_box"] = svc
    s["lords"][lid].setdefault("flags", {})


class TestFeedSharing:
    def test_colocated_lord_shares_to_feed_short_lord(self):
        s = _bare_state()
        # Firenze: 4 units (need 1), NO own Provender/Loot, Moved/Fought.
        _put(s, "firenze", "Figline", {"Cavalieri": 2, "Men-at-Arms": 2}, prov=0, loot=0, svc=8)
        s["lords"]["firenze"]["flags"]["moved_fought"] = True
        # Lucca: same Locale, 5 surplus Provender, NOT moved (no own need).
        _put(s, "lucca", "Figline", {"Militia": 1}, prov=5, loot=0, svc=8)
        s["lords"]["lucca"]["flags"]["moved_fought"] = False
        svc0 = s["lords"]["firenze"]["service_box"]
        out = _run_fpd(s)
        fed = {f["lord_id"]: f for f in out["feed"]}
        assert fed["firenze"]["fed"] is True            # fed via Sharing
        assert s["lords"]["firenze"]["service_box"] == svc0   # NO shift
        assert s["lords"]["lucca"]["assets"]["Provender"] == 4  # shared 1

    def test_unfed_when_no_sharer_and_consumes_partial(self):
        s = _bare_state()
        # Firenze: 8 units (need 2), only 1 own Provender, alone at the Locale.
        _put(s, "firenze", "Figline",
             {"Cavalieri": 3, "Men-at-Arms": 3, "Militia": 2}, prov=1, loot=0, svc=8)
        s["lords"]["firenze"]["flags"]["moved_fought"] = True
        # Move every other Lord away so there is no sharer at Figline.
        for lid, l in s["lords"].items():
            if lid != "firenze" and l.get("location") == "Figline":
                l["location"] = "Arezzo"
        svc0 = s["lords"]["firenze"]["service_box"]
        out = _run_fpd(s)
        fed = {f["lord_id"]: f for f in out["feed"]}
        assert fed["firenze"]["fed"] is False
        assert s["lords"]["firenze"]["service_box"] == svc0 - 1   # shifted left
        # Partial consumption: the 1 Provender he had IS consumed (Greed/rule).
        assert s["lords"]["firenze"]["assets"]["Provender"] == 0
