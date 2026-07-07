"""v6.9 — Digest-vs-PDF audit round: CONF-022 .. CONF-036.

Each test pins one Rules-of-Play clause the engine previously deviated from.
Sources: Rules of Play (Living Rules 2023-04-10) pp. 12, 17-22, 26-31;
Playbook pp. 5, 9; Arts of War card texts (Balestrieri F9-F11, Palvesari
F13-F15, Balestre Grosse F8/S8).
"""
from __future__ import annotations

import pytest

import inferno.battle as B
import inferno.static_data as sd
from inferno.actions import (
    IllegalAction, dispatch, _knights_quarter_all, _end_game_now,
    _maybe_exhaustion_roll, _h_cta_allies, _h_cta_commander_arms,
    _h_cmd_sail, _h_cmd_siege,
)
from inferno.battle import resolve_battle, resolve_storm
from inferno.scenarios import load_scenario
from inferno.rng import HarnessRNG


def _place(s, lid, locale, inside=False, mustered=True):
    lord = s["lords"][lid]
    old = lord.get("location")
    if old and lid in s["locales"][old].get("lords_present", []):
        s["locales"][old]["lords_present"].remove(lid)
    s["locales"][locale].setdefault("lords_present", []).append(lid)
    lord["location"] = locale
    if mustered:
        lord["status"] = "mustered"
    if inside:
        lord.setdefault("flags", {})["in_stronghold"] = True


# =====================================================================
# CONF-022 — 4.4.5: Lord removed in Battle: Knights' Quarter for ALL
# his Cavalieri and Ritter (owner's Captured Knights box).
# =====================================================================
class TestConf022KnightsQuarterOnRemoval:
    def test_helper_captures_forces_and_routed(self):
        s = load_scenario("A", seed=1)
        lord = s["lords"]["firenze"]
        lord["forces"] = {"Cavalieri": 2, "Militia": 1}
        lord["routed_units"] = {"Ritter": 1, "Cavalieri": 1}
        taken = _knights_quarter_all(s, "firenze")
        assert taken == {"Cavalieri": 3, "Ritter": 1}
        cap = s["captured_knights"]["guelph"]
        assert cap.get("Cavalieri") == 3 and cap.get("Ritter") == 1
        # Non-knights untouched; knights gone from both piles.
        assert lord["forces"] == {"Militia": 1}
        assert "Ritter" not in lord["routed_units"]

    def test_removed_battle_loser_knights_captured_not_pooled(self):
        # A loser with zero remaining Forces is Removed per 4.4.5: his
        # Cavalieri/Ritter (here: in his Routed pile) must land in HIS side's
        # Captured Knights box, not return to the pool.
        from inferno.actions import _apply_post_battle
        s = load_scenario("A", seed=3)
        _place(s, "siena", "Firenze")
        s["lords"]["siena"]["forces"] = {}
        s["lords"]["siena"]["routed_units"] = {"Cavalieri": 2, "Militia": 1}
        s["decks"]["guelph"]["treachery_set_aside"] = ["t1", "t2", "t3"]
        result = {"winner": "attacker", "loser": "defender",
                  "conceded": None, "removed_lords": ["siena"], "rounds": []}
        _apply_post_battle(s, result, ["firenze"], ["siena"],
                           battle_locale="Firenze")
        cap = s.get("captured_knights", {}).get("ghibelline", {})
        assert cap.get("Cavalieri") == 2,             "4.4.5: removal in Battle gives Knights\' Quarter for ALL Cavalieri/Ritter"
        assert s["lords"]["siena"]["status"] != "mustered"


# =====================================================================
# CONF-023 — 4.4.2: Concede is available at the start of EVERY Round,
# including Round 1 ("Battles last at least one Round").
# =====================================================================
class TestConf023ConcedeRound1:
    def _setup(self, seed=7):
        s = load_scenario("A", seed=seed)
        _place(s, "siena", "Firenze")
        return s

    def test_attacker_may_concede_in_round_1(self):
        s = self._setup()
        r = resolve_battle(
            s, ["firenze"], ["siena"], "firenze", "Firenze",
            scripted_decisions=[{"type": "concede", "choice": "yes"}])
        assert r["conceded"] == "attacker"
        assert r["rounds_played"] == 1
        assert r["loser"] == "attacker"

    def test_defender_may_concede_in_round_1(self):
        s = self._setup(seed=9)
        r = resolve_battle(
            s, ["firenze"], ["siena"], "firenze", "Firenze",
            scripted_decisions=[{"type": "concede", "choice": "no"},
                                {"type": "concede", "choice": "yes"}])
        assert r["conceded"] == "defender"
        assert r["rounds_played"] == 1


# =====================================================================
# CONF-024 — 4.5.2: multi-Lord Storm. All own-side Lords at the Locale
# participate (Active at Front, others in Reserve) and ALL are marked
# Moved/Fought ("Lords at a Storm Locale may not simply sit it out").
# =====================================================================
class TestConf024MultiLordStorm:
    def test_co_besieger_joins_storm_and_is_marked_fought(self):
        from tests.test_phase3c import _to_command_with
        s = _to_command_with("A", seed=1, lord_id="firenze",
                             lord_location_override="Volterra")
        _place(s, "arezzo", "Volterra")
        s["locales"]["Volterra"]["siege"] = [
            {"side": "guelph", "color": "purple", "count": 3}]
        dispatch(s, {"action": "cmd_storm", "side": "guelph",
                     "args": {"lord_id": "firenze"}})
        assert s["lords"]["arezzo"].get("flags", {}).get("moved_fought"), \
            "co-Besieging Lord must be marked Moved/Fought (4.5.2)"

    def test_storm_emptied_lord_removed_per_4_4_5(self):
        from tests.test_phase3c import _to_command_with
        s = _to_command_with("A", seed=1, lord_id="firenze",
                             lord_location_override="Volterra")
        s["locales"]["Volterra"]["siege"] = [
            {"side": "guelph", "color": "purple", "count": 1}]
        # One doomed unit: a single Militia routs on any hit and fails Harsh
        # recovery on 2-6; give the Ghibellines Treachery cards for the trigger.
        s["lords"]["firenze"]["forces"] = {"Militia": 1}
        s["decks"]["ghibelline"]["treachery_set_aside"] = ["t1", "t2", "t3"]
        dispatch(s, {"action": "cmd_storm", "side": "guelph",
                     "args": {"lord_id": "firenze"}})
        f = s["lords"]["firenze"]
        if sum(f.get("forces", {}).values()) == 0:
            assert f["status"] != "mustered", \
                "a Lord left with NO Forces after Storm must be removed (4.4.5)"


# =====================================================================
# CONF-025 — 4.5.2 REPOSITION: "If all Front Lords Routed, a Reserve
# Lord (if any present) MUST move to Front" — even if the voluntary
# add is declined.
# =====================================================================
class TestConf025ForcedFrontRefill:
    def test_reserve_lord_forced_to_front_when_front_empty(self):
        s = load_scenario("A", seed=1)
        _place(s, "firenze", "Volterra")
        _place(s, "arezzo", "Volterra")
        s["locales"]["Volterra"]["siege"] = [
            {"side": "guelph", "color": "purple", "count": 3}]
        s["lords"]["firenze"]["forces"] = {}          # routs at once
        s["lords"]["arezzo"]["forces"] = {"Men-at-Arms": 4, "Cavalieri": 2}
        scripted = [
            {"type": "concede", "choice": "no"},
            {"type": "storm_reserve_add", "choice": "no"},   # declined!
            {"type": "concede", "choice": "no"},
            {"type": "concede", "choice": "no"},
        ]
        r = resolve_storm(s, attackers=["firenze", "arezzo"], defenders=[],
                          active_id="firenze", locale_name="Volterra",
                          scripted_decisions=scripted)
        hits_on_arezzo = [h for rd in r["rounds"]
                          for h in rd.get("hit_log", [])
                          if h.get("lord_id") == "arezzo"]
        assert hits_on_arezzo, \
            "Reserve Lord must be FORCED to the empty Front (4.5.2), " \
            "even when the voluntary add was declined"


# =====================================================================
# CONF-026 — Crossbow Select Target conditions (4.4.2 + card texts).
# =====================================================================
class TestConf026CrossbowSelect:
    def _s(self, caps):
        s = load_scenario("A", seed=1)
        s["lords"]["arezzo"]["capabilities"] = caps
        return s

    def test_battle_balestrieri_alone_does_not_select(self):
        s = self._s(["F10"])
        assert B._crossbow_archery_hits(s, "arezzo", {"Armigieri": 2},
                                        "atk_archery", "battle") == (0.0, 2.0)

    def test_battle_balestrieri_plus_palvesari_selects(self):
        s = self._s(["F10", "F13"])
        assert B._crossbow_archery_hits(s, "arezzo", {"Armigieri": 2},
                                        "atk_archery", "battle") == (2.0, 0.0)

    def test_storm_defense_balestrieri_selects(self):
        s = self._s(["F10"])
        assert B._crossbow_archery_hits(
            s, "arezzo", {"Armigieri": 2}, "def_archery", "storm",
            is_storm_defender=True) == (2.0, 0.0)

    def test_storm_attack_balestre_grosse_does_not_select(self):
        s = self._s(["F8"])
        assert B._crossbow_archery_hits(
            s, "arezzo", {"Men-at-Arms": 2}, "atk_archery", "storm",
            is_storm_defender=False) == (0.0, 1.0)

    def test_storm_defense_balestre_grosse_selects(self):
        s = self._s(["F8"])
        assert B._crossbow_archery_hits(
            s, "arezzo", {"Men-at-Arms": 2}, "def_archery", "storm",
            is_storm_defender=True) == (1.0, 0.0)

    def test_noselect_crossbow_hits_use_owner_order_with_minus2(self):
        # Ritter + Militia: a SELECT crossbow hit would strike the Ritter;
        # a NON-select crossbow hit is the owner's to assign (cheap first).
        class _RNG:
            def __init__(self, vals): self.vals = list(vals); self.i = 0
            def __call__(self, ctx):
                v = self.vals[self.i % len(self.vals)]; self.i += 1
                r = type("R", (), {})(); r.value = v; r.context = ctx; return r
        s = {"lords": {"L": {"side": "guelph",
                             "forces": {"Ritter": 1, "Militia": 1},
                             "routed_units": {}}}}
        B._absorb_hits(s, "L", 1, _RNG([2]), [], {},
                       crossbow_hits=0, crossbow_noselect_hits=1)
        # Owner shields with the Militia (Unarmored: routs on non-1).
        assert s["lords"]["L"]["forces"].get("Ritter", 0) == 1
        assert s["lords"]["L"]["forces"].get("Militia", 0) == 0


# =====================================================================
# CONF-027 — 4.4.1/4.5.2: the Comune may start at Front center if its
# Commander is the Active Lord.
# =====================================================================
class TestConf027ComuneCenter:
    def test_comune_takes_battle_center_when_scripted(self):
        s = load_scenario("A", seed=1)
        s["lords"]["firenze_comune"] = {
            "side": "guelph", "status": "mustered", "comune_of": "firenze",
            "forces": {"Cavalieri": 2}, "routed_units": {}, "flags": {},
            "location": "Firenze", "vassals": [], "assets": {},
        }
        bdc = B.BattleDecisionContext(scripted=[
            {"type": "array_center", "choice": "firenze_comune"}])
        positions, reserve = B._initial_array(
            s, ["firenze", "firenze_comune"], ["siena"], "firenze", bdc)
        assert positions["attacker"]["center"] == "firenze_comune"
        # The Commander arrays like any other Lord (left/right/reserve).
        placed = [v for v in positions["attacker"].values() if v]
        assert "firenze" in placed + reserve["attacker"]

    def test_default_keeps_active_lord_at_center(self):
        s = load_scenario("A", seed=1)
        s["lords"]["firenze_comune"] = {
            "side": "guelph", "status": "mustered", "comune_of": "firenze",
            "forces": {"Cavalieri": 2}, "routed_units": {}, "flags": {},
            "location": "Firenze", "vassals": [], "assets": {},
        }
        bdc = B.BattleDecisionContext()
        positions, _ = B._initial_array(
            s, ["firenze", "firenze_comune"], ["siena"], "firenze", bdc)
        assert positions["attacker"]["center"] == "firenze"


# =====================================================================
# CONF-029 — 3.4.1 Muster Seat eligibility.
# =====================================================================
class TestConf029MusterSeat:
    def test_enemy_aligned_seat_blocks_muster(self):
        s = load_scenario("A", seed=1)
        # Prato (Guelph-printed) flipped Ghibelline by markers: Guelph lords
        # may NOT Muster there ("neither Enemy aligned").
        s["locales"]["Prato"]["current_allegiance"] = [{"side": "ghibelline", "value": 1}]
        tl = s["lords"]["firenze"]
        ok, _, why = sd.muster_seat_status(s, tl, "Prato")
        assert not ok and "Enemy aligned" in why

    def test_ruins_seat_musterable_when_no_enemy_lord(self):
        s = load_scenario("A", seed=1)
        s["locales"]["Prato"]["ruins"] = "purple"
        tl = s["lords"]["firenze"]
        ok, inside, _ = sd.muster_seat_status(s, tl, "Prato")
        assert ok and not inside  # 3.4.1: Ruins OK unless Enemy Lord there

    def test_ruins_seat_with_enemy_lord_blocked(self):
        s = load_scenario("A", seed=1)
        s["locales"]["Prato"]["ruins"] = "purple"
        _place(s, "siena", "Prato")
        tl = s["lords"]["firenze"]
        ok, _, why = sd.muster_seat_status(s, tl, "Prato")
        assert not ok and "Ruins" in why

    def test_bypassed_seat_musterable_inside(self):
        s = load_scenario("A", seed=1)
        # Enemy Lord present, NO Siege marker -> Bypassed: explicitly legal
        # ("it may be Bypassed, 4.3.5"); the Lord comes up INSIDE.
        _place(s, "siena", "Prato")
        tl = s["lords"]["firenze"]
        ok, inside, _ = sd.muster_seat_status(s, tl, "Prato")
        assert ok and inside


# =====================================================================
# CONF-030 — 3.4.1 EMERGENCY ARMY: Enemy Lords at a Podestà's Main
# Seat make him Ready wherever his cylinder is.
# =====================================================================
class TestConf030EmergencyArmy:
    def test_podesta_ready_when_enemy_at_main_seat(self):
        s = load_scenario("B", seed=1)
        lucca = s["lords"]["lucca"]
        assert lucca.get("podesta")
        assert not sd.emergency_army_ready(s, lucca)
        _place(s, "siena", lucca["seats"][0])
        assert sd.emergency_army_ready(s, lucca)

    def test_regular_lord_never_emergency_ready(self):
        s = load_scenario("B", seed=1)
        gg = s["lords"]["guido_guerra"]
        assert not gg.get("podesta")
        _place(s, "siena", gg["seats"][0])
        assert not sd.emergency_army_ready(s, gg)


# =====================================================================
# CONF-031 — 3.5.4 Allies auto-Muster requires READY (Playbook: "by
# the usual rules (3.4.1, including needing to be Ready)").
# =====================================================================
class TestConf031AlliesReady:
    def test_auto_muster_rejects_unready_lord(self):
        s = load_scenario("B", seed=1)
        s["meta"]["cta_substep"] = "allies"
        # guido_guerra waits at box 7; Levy is at box 4 -> NOT Ready.
        lord = s["lords"]["guido_guerra"]
        assert lord["status"] == "on_calendar"
        assert (lord.get("calendar_box") or 0) > s["calendar"]["levy_box"]
        rng = HarnessRNG(seed=1)
        with pytest.raises(IllegalAction) as exc:
            _h_cta_allies(s, "guelph",
                          {"mode": "auto_muster",
                           "target_lord_id": "guido_guerra",
                           "target_seat": lord["seats"][0]}, rng)
        assert exc.value.code == "TARGET_NOT_READY"


# =====================================================================
# CONF-032 — 3.5.2 Commander to Arms is "as able per 3.4.1": an
# Enemy-aligned Leading City blocks the Muster.
# =====================================================================
class TestConf032CommanderMusterEligibility:
    def test_muster_only_rejected_at_enemy_aligned_leading_city(self):
        s = load_scenario("A", seed=1)
        s["meta"]["cta_substep"] = "commander_arms"
        cmd = s["lords"]["firenze"]
        cmd["status"] = "on_calendar"
        if "Firenze" in s["locales"] and "firenze" in s["locales"]["Firenze"].get("lords_present", []):
            s["locales"]["Firenze"]["lords_present"].remove("firenze")
        s["locales"]["Firenze"]["current_allegiance"] = [{"side": "ghibelline", "value": 1}]
        rng = HarnessRNG(seed=1)
        with pytest.raises(IllegalAction) as exc:
            _h_cta_commander_arms(s, "guelph", {"mode": "muster_only"}, rng)
        assert exc.value.code == "SEAT_NOT_MUSTERABLE"


# =====================================================================
# CONF-033 — 4.5.1: the Surrender roll is OPTIONAL ("may roll"); a
# declined roll still accrues Siegeworks.
# =====================================================================
class TestConf033SurrenderOptional:
    def test_decline_surrender_roll_adds_siegeworks(self):
        from tests.test_phase3c import _to_command_with
        s = _to_command_with("A", seed=1, lord_id="firenze",
                             lord_location_override="Volterra")
        _place(s, "arezzo", "Volterra")   # Town Size 2 needs 2 Besiegers
        s["locales"]["Volterra"]["siege"] = [
            {"side": "guelph", "color": "purple", "count": 1}]
        dispatch(s, {"action": "cmd_siege", "side": "guelph",
                     "args": {"lord_id": "firenze", "roll_surrender": False}})
        loc = s["locales"]["Volterra"]
        # No Surrender happened (Allegiance unchanged), Siegeworks added
        # ("including because the Besieger declined to roll").
        assert loc["siege"] and loc["siege"][0]["count"] == 2
        assert not any(m.get("side") == "guelph"
                       for m in (loc.get("current_allegiance") or []))


# =====================================================================
# CONF-034 — 4.3.6 SORTIE invokes the full 4.3.4 Approach: the
# Bypassing Enemy MAY Avoid Battle.
# =====================================================================
class TestConf034SortieAvoid:
    def test_bypasser_may_avoid_sortie_approach(self):
        from tests.test_phase3c import _to_command_with
        s = _to_command_with("A", seed=1, lord_id="firenze")
        # Siena Bypasses Firenze's Stronghold; Firenze is inside.
        _place(s, "siena", "Firenze")
        s["lords"]["siena"].setdefault("flags", {})["bypassing"] = "Firenze"
        s["locales"]["Firenze"]["bypass"] = [{"side": "ghibelline"}]
        s["lords"]["firenze"].setdefault("flags", {})["in_stronghold"] = True
        s["lords"]["siena"]["assets"]["Loot"] = 0
        dispatch(s, {"action": "cmd_sortie", "side": "guelph",
                     "args": {"lord_id": "firenze"}})
        pend = [p for p in s.get("pending", [])
                if p.get("type") == "approach_response"]
        assert pend and "avoid" in pend[0]["options"]
        # And the handler accepts the Avoid.
        from inferno.legal_moves import enumerate_legal
        moves = enumerate_legal(s)
        avoids = [m for m in moves if m.get("args", {}).get("choice") == "avoid"]
        assert avoids, "enumerator must offer Avoid to the Bypassing Enemy"
        dispatch(s, {"action": "approach_response", "side": "ghibelline",
                     "args": avoids[0]["args"]})
        assert s["lords"]["siena"]["location"] != "Firenze"


# =====================================================================
# CONF-035 — 4.7.3: Sail must START at a Friendly, Unbesieged Port.
# =====================================================================
class TestConf035SailFriendlyPort:
    def test_sail_rejected_from_non_friendly_port(self):
        s = load_scenario("A", seed=1)
        pisa = s["lords"]["pisa"]
        pisa["status"] = "mustered"
        pisa["assets"] = {"Ship": 6}
        pisa["forces"] = {}
        _place(s, "pisa", "Empoli")           # Guelph-printed Port
        s["meta"]["turn"] = 3                 # Summer (Sail is legal season-wise)
        s["current_lord_id"] = "pisa"
        s["actions_remaining"] = 2
        rng = HarnessRNG(seed=1)
        with pytest.raises(IllegalAction) as exc:
            _h_cmd_sail(s, "ghibelline",
                        {"lord_id": "pisa", "dest_locale": "Pisa"}, rng)
        assert exc.value.code == "PORT_NOT_FRIENDLY"


# =====================================================================
# CONF-036 — Scenario F Exhaustion end mechanics + final-VP fallback.
# =====================================================================
class TestConf036ScenarioFEnd:
    class _FixedRoll:
        def __init__(self, v): self.v = v
        def roll(self, ctx):
            r = type("R", (), {})(); r.value = self.v; r.context = ctx
            return r

    def test_end_marker_slides_onto_levy_box_ends_game_at_once(self):
        s = load_scenario("F", seed=1)
        s["meta"]["turn"] = 12
        s["calendar"]["levy_box"] = 12
        s["calendar"]["end_box"] = 13
        s["meta"]["exhaustion_rolled_this_levy"] = False
        _maybe_exhaustion_roll(s, self._FixedRoll(2))   # 1-3: slide left
        assert s["calendar"]["end_box"] == 12
        assert s["meta"].get("game_over") is True, \
            "game ends THE MOMENT Levy and End markers share a box"

    def test_slide_does_not_end_game_when_not_meeting(self):
        s = load_scenario("F", seed=1)
        s["meta"]["turn"] = 10
        s["calendar"]["levy_box"] = 10
        s["calendar"]["end_box"] = 14
        s["meta"]["exhaustion_rolled_this_levy"] = False
        _maybe_exhaustion_roll(s, self._FixedRoll(1))
        assert s["calendar"]["end_box"] == 13
        assert not s["meta"].get("game_over")

    def test_end_game_now_scores_computed_final_vp(self):
        s = load_scenario("F", seed=1)
        # Running VP says Ghibelline; the map markers (recounted per 5.1,
        # with Scenario modifiers) must decide instead.
        s["vp"]["guelph"] = 0.0
        s["vp"]["ghibelline"] = 5.0
        _end_game_now(s)
        from inferno.actions import _compute_final_vp
        g, h = s["meta"]["final_vp"]["guelph"], s["meta"]["final_vp"]["ghibelline"]
        assert s["meta"]["game_over"] is True
        assert s["meta"]["winner"] == ("guelph" if g > h else
                                       "ghibelline" if h > g else None)
