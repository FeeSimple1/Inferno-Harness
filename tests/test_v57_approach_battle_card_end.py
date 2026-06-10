"""v5.7 — an Approach Battle ends the active side's Command card (RoP 4.4.6).

Ruling: 4.4.6 Recovery — "Skip any Command actions remaining this card. Go to
Feed/Pay/Disband (4.8). A Battle or Storm blocks any further Command actions on
the current Command card" (cross-ref 4.2.1). So a March-triggered Battle must
route through the canonical card-end path (_finish_card_with): run FPD for BOTH
sides' Fought Lords, then flip to the other side — exactly like Storm and Sally.

Previously _finalize_approach nulled the card by hand and skipped FPD + the
side-flip, letting the attacker reveal another card and skipping the defender's
turn and Feed.
"""
from __future__ import annotations

from inferno.actions import dispatch
from inferno.legal_moves import enumerate_legal
from tests.test_phase3b import _to_command_phase


def _approach(seed=99, keep_ghib_alive=True, big_defender=False):
    s = _to_command_phase("A", seed=seed, lord_for_active="firenze")
    sl = s["lords"]["siena"]["location"]
    s["locales"][sl]["lords_present"].remove("siena")
    s["locales"]["Figline"]["lords_present"].append("siena")
    s["lords"]["siena"]["location"] = "Figline"
    if big_defender:
        s["lords"]["siena"]["forces"] = {"Cavalieri": 4, "Men-at-Arms": 4, "Militia": 4}
        s["lords"]["siena"].setdefault("assets", {})["Provender"] = 5
        s["lords"]["firenze"]["forces"] = {"Militia": 1}
    if keep_ghib_alive:
        prov = s["lords"]["provenzano"]
        prov["status"] = "mustered"
        prov["location"] = "Siena"
        prov["forces"] = {"Militia": 2}
        prov.setdefault("flags", {})
        s["locales"]["Siena"]["lords_present"].append("provenzano")
    dispatch(s, {"action": "cmd_march", "side": "guelph",
                 "args": {"lord_id": "firenze",
                          "destination": "Figline", "way_type": "road"}})
    return s


def _stand(s):
    return dispatch(s, {"action": "approach_response", "side": "ghibelline",
                        "args": {"lord_id": "siena", "choice": "stand"}})


class TestApproachBattleEndsCard:
    def test_card_finished_and_fpd_run(self):
        s = _approach()
        sc = _stand(s)["state_changes"]
        assert sc["approach_resolved"] == "battle"
        assert sc.get("card_finished") is True   # 4.4.6 ended the card
        assert "fpd" in sc                        # Feed/Pay/Disband (4.8) ran

    def test_turn_flips_to_defender_not_back_to_attacker(self):
        s = _approach()
        _stand(s)
        # 4.2: the OTHER side flips next. active_player must be the defender now,
        # never the attacker (which would let Guelph reveal consecutive cards).
        assert s["meta"]["active_player"] == "ghibelline"
        legal = [m for m in enumerate_legal(s) if not m.get("action", "").startswith("<")]
        # The attacker must NOT be able to immediately reveal another card.
        assert not any(m["action"] == "command_reveal" and m["side"] == "guelph"
                       for m in legal)

    def test_fpd_feeds_both_sides_defender_fought_lord(self):
        # Defender survives (overwhelming force) and, being Fought, is Fed by FPD.
        s = _approach(seed=7, big_defender=True)
        sc = _stand(s)["state_changes"]
        assert s["lords"]["siena"]["status"] == "mustered"   # survived
        fed_ids = [f["lord_id"] for f in sc.get("fpd", {}).get("feed", [])]
        assert "siena" in fed_ids   # the DEFENDER's Fought Lord was Fed, not just the attacker

    def test_card_end_applies_even_when_defender_wiped(self):
        # Even when the lone defender is removed (the case that used to look like
        # a "deadlock"), the card still ends through 4.4.6 -> FPD; the engine is
        # never left waiting on the attacker to reveal another card.
        s = _approach(keep_ghib_alive=False)
        sc = _stand(s)["state_changes"]
        assert sc.get("card_finished") is True and "fpd" in sc
        legal = [m for m in enumerate_legal(s) if not m.get("action", "").startswith("<")]
        assert not any(m["action"] == "command_reveal" and m["side"] == "guelph"
                       for m in legal)
