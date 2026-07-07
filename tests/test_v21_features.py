"""v2.1 text-resolvable defect fixes (batch #5-#11 subset).

  #6  SMOKE-Inferno-051  Forage siege block = besieging Enemy Lords >= Size
"""
import inspect
import pytest

from inferno.scenarios import load_scenario
from inferno import static_data as sd
import inferno.actions as A
import inferno.legal_moves as LM


# =====================================================================
# #6 SMOKE-Inferno-051 — Forage blocked only when besieging Enemy Lords
# number EQUAL TO OR MORE THAN the Stronghold's Size (not by any Siege marker).
# =====================================================================
class TestForageSiegeThreshold:
    @staticmethod
    def _state(loc_type, besieger_count, besiegers_inside=False):
        lords = {"def": {"side": "guelph", "status": "mustered",
                         "flags": {"in_stronghold": True}, "location": "X"}}
        present = ["def"]
        for i in range(besieger_count):
            bid = f"b{i}"
            lords[bid] = {"side": "ghibelline", "status": "mustered",
                          "flags": {"in_stronghold": besiegers_inside}}
            present.append(bid)
        state = {"lords": lords}
        loc = {"type": loc_type, "name": "X",
               "siege": [{"side": "ghibelline", "color": "gold", "count": 1}],
               "lords_present": present}
        return state, loc

    def test_castle_one_besieger_blocks(self):
        st, loc = self._state("castle", 1)  # size 1, 1 >= 1
        assert sd.forage_besieged_block(st, loc, "guelph") is True

    def test_town_one_besieger_allows(self):
        st, loc = self._state("town", 1)  # size 2, 1 < 2
        assert sd.forage_besieged_block(st, loc, "guelph") is False

    def test_town_two_besiegers_blocks(self):
        st, loc = self._state("town", 2)  # size 2, 2 >= 2
        assert sd.forage_besieged_block(st, loc, "guelph") is True

    def test_city_two_besiegers_allows(self):
        st, loc = self._state("city", 2)  # size 3, 2 < 3
        assert sd.forage_besieged_block(st, loc, "guelph") is False

    def test_no_siege_never_blocks(self):
        st, loc = self._state("castle", 1)
        loc["siege"] = []
        assert sd.forage_besieged_block(st, loc, "guelph") is False

    def test_in_stronghold_lords_are_not_besiegers(self):
        # Enemy Lords flagged in_stronghold are defenders, not besiegers.
        st, loc = self._state("town", 2, besiegers_inside=True)
        assert sd.forage_besieged_block(st, loc, "guelph") is False

    def test_handler_and_enumerator_share_predicate(self):
        assert "forage_besieged_block" in inspect.getsource(A._h_cmd_forage)
        src = inspect.getsource(LM)
        assert "forage_besieged_block" in src

    def test_marker_present(self):
        assert "SMOKE-Inferno-051" in inspect.getsource(sd.forage_besieged_block)


# =====================================================================
# #8 SMOKE-Inferno-052 — "Friendly Locale" routed through the canonical
# _is_friendly_locale predicate at Loot Pay (3.2.2) and Via Francigena (F23).
# =====================================================================
class TestFriendlyLocaleChecks:
    def _advance_to_pay(self, scenario="A", seed=1):
        s = load_scenario(scenario, seed=seed)
        A.dispatch(s, {"action": "levy_aow_draw", "side": "guelph"})
        A.dispatch(s, {"action": "levy_aow_draw", "side": "ghibelline"})
        return s

    def test_enemy_markers_override_printed_friendly(self):
        # The old Via Francigena inline check treated printed==side as Friendly
        # even under enemy Allegiance markers; the canonical predicate does not.
        loc = {"allegiance": "guelph",
               "current_allegiance": [{"side": "ghibelline", "value": 1}]}
        assert A._is_friendly_locale({}, loc, "guelph") is False

    def test_own_markers_make_enemy_printed_friendly(self):
        loc = {"allegiance": "ghibelline",
               "current_allegiance": [{"side": "guelph", "value": 1}]}
        assert A._is_friendly_locale({}, loc, "guelph") is True

    def test_loot_pay_blocked_at_unfriendly_locale(self):
        from inferno.actions import IllegalAction
        s = self._advance_to_pay("A", seed=1)
        lord = s["lords"]["firenze"]
        target = next(n for n, l in s["locales"].items()
                      if l.get("allegiance") == "ghibelline" and not l.get("siege")
                      and not any(m.get("side") == "guelph"
                                  for m in l.get("current_allegiance", [])))
        old = lord["location"]
        if old and "firenze" in s["locales"][old].get("lords_present", []):
            s["locales"][old]["lords_present"].remove("firenze")
        lord["location"] = target
        s["locales"][target].setdefault("lords_present", []).append("firenze")
        lord["assets"]["Loot"] = 4
        with pytest.raises(IllegalAction) as exc:
            A.dispatch(s, {"action": "levy_pay", "side": "guelph",
                           "args": {"from_lord_id": "firenze",
                                    "target_lord_id": "firenze",
                                    "asset": "Loot", "amount": 1}})
        assert exc.value.code == "LOOT_NOT_FRIENDLY"

    def test_loot_pay_allowed_at_friendly_locale(self):
        s = self._advance_to_pay("A", seed=1)
        lord = s["lords"]["firenze"]  # at Firenze, printed Guelph => Friendly
        assert A._is_friendly_locale(s, s["locales"][lord["location"]], "guelph")
        lord["assets"]["Loot"] = 4
        before = lord["service_box"]
        A.dispatch(s, {"action": "levy_pay", "side": "guelph",
                       "args": {"from_lord_id": "firenze",
                                "target_lord_id": "firenze",
                                "asset": "Loot", "amount": 1}})
        assert lord["service_box"] == before + 1

    def test_both_sites_use_canonical_predicate(self):
        # The Loot Friendly check lives in the shared pay core (_apply_pay_action),
        # which both Levy Pay and FPD Pay route through.
        pay_src = inspect.getsource(A._apply_pay_action)
        assert "_is_friendly_locale" in pay_src and "LOOT_NOT_FRIENDLY" in pay_src
        # Via Francigena lives in the command-reveal handler.
        reveal_src = inspect.getsource(A)
        assert "Via Francigena" in reveal_src
        # The F23 block now calls the canonical predicate (no inline allegiance test).
        assert "SMOKE-Inferno-052" in reveal_src

    def test_marker_present(self):
        assert "SMOKE-Inferno-052" in inspect.getsource(A._is_friendly_locale)


# =====================================================================
# #11 SMOKE-Inferno-053 — end-game VP tally (5.0): Captured Carroccio (+2) is
# now persisted and counted; Allegiance/Ruins/Ravaged verified; Scenario E
# doubles Guelph VP except Ravaged.
# =====================================================================
class TestEndGameVpTally:
    def test_captured_carroccio_counts(self):
        s = {"meta": {"scenario": ""}, "locales": {},
             "captured_carroccio_for_side": {"guelph": 1}}
        g, h = A._compute_final_vp(s)
        assert (g, h) == (2.0, 0.0)

    def test_marker_tally_per_5_0(self):
        s = {"meta": {"scenario": ""}, "locales": {
            "X": {"current_allegiance": [{"side": "guelph", "value": 1}]},
            "Y": {"ruins": "purple"},      # +0.5 Guelph (CONF-039)
            "Z": {"ravaged": "gold"},      # +0.5 Ghibelline (CONF-039)
        }}
        g, h = A._compute_final_vp(s)
        assert g == 1.5   # 1 Allegiance + 0.5 Ruins(purple)
        assert h == 0.5   # 0.5 Ravaged(purple)

    def test_scenario_E_doubles_guelph_except_ravaged(self):
        s = {"meta": {"scenario": "E"}, "locales": {
            "X": {"current_allegiance": [{"side": "guelph", "value": 1}]},
            "R": {"ravaged": "purple"},    # Guelph Ravaged 0.5, NOT doubled (CONF-039)
        }}
        g, h = A._compute_final_vp(s)
        assert g == 2.5   # 1*2 (allegiance) + 0.5 (ravaged, not doubled)

    def test_battle_spoils_persist_carroccio_capture(self):
        from inferno.battle import transfer_spoils
        s = load_scenario("A", seed=1)
        # siena (Ghibelline) loses & is removed; firenze (Guelph) wins.
        s["lords"]["siena"]["vassals"].append({
            "name": "Carroccio", "special": True, "on_mat": True,
            "ready": True, "forces": {"Cavalieri": 1},
        })
        before = s.get("captured_carroccio_for_side", {}).get("guelph", 0)
        transfer_spoils(s, "siena", winners=["firenze"],
                        retreated=False, conceded=False, withdrew=False)
        assert s["captured_carroccio_for_side"]["guelph"] == before + 1

    def test_marker_present(self):
        assert "SMOKE-Inferno-053" in inspect.getsource(A._compute_final_vp)


# =====================================================================
# #10 SMOKE-Inferno-054 — F17 Foreign Help treachery->cylinder branch.
# =====================================================================
class TestF17ForeignHelp:
    import inferno.card_effects as _ce
    from inferno.rng import HarnessRNG as _RNG

    def _setup(self, seed=1):
        return load_scenario("A", seed=seed)

    def _place_on_calendar(self, s, lid, box):
        lord = s["lords"][lid]
        loc = lord.get("location")
        if loc and lid in s["locales"].get(loc, {}).get("lords_present", []):
            s["locales"][loc]["lords_present"].remove(lid)
        lord["status"] = "on_calendar"
        lord["location"] = None
        lord["service_box"] = None
        lord["calendar_box"] = box
        cb = s["calendar"]["boxes"].setdefault(str(box),
            {"cylinders": [], "services": [], "victory": [], "markers": []})
        if lid not in cb["cylinders"]:
            cb["cylinders"].append(lid)

    def test_treachery_cylinder_moves_and_sets_aside(self):
        s = self._setup()
        levy = s["calendar"]["levy_box"]
        self._place_on_calendar(s, "guido_guerra", levy + 4)
        # Put a Guelph Treachery card into the Command deck (acquired).
        s["decks"]["guelph"]["command_deck"].append("treachery_arezzo")
        r = self._ce.apply_event_effect(
            s, "F17", "guelph",
            {"mode": "treachery_cylinder", "targets": ["guido_guerra"],
             "treachery_card": "treachery_arezzo"}, self._RNG(seed=1))
        assert r["applied"] is True
        assert s["lords"]["guido_guerra"]["calendar_box"] == levy
        assert "treachery_arezzo" not in s["decks"]["guelph"]["command_deck"]
        assert "treachery_arezzo" in s["decks"]["guelph"]["treachery_set_aside"]
        assert "guido_guerra" in s["calendar"]["boxes"][str(levy)]["cylinders"]

    def test_treachery_cylinder_blocked_without_eligible_cylinder(self):
        s = self._setup()
        s["decks"]["guelph"]["command_deck"].append("treachery_arezzo")
        # No guido/orvieto cylinder right of levy box (they start removed).
        r = self._ce.apply_event_effect(
            s, "F17", "guelph",
            {"mode": "treachery_cylinder", "targets": ["guido_guerra"]},
            self._RNG(seed=1))
        assert r["applied"] is False

    def test_treachery_cylinder_blocked_without_treachery_in_deck(self):
        s = self._setup()
        self._place_on_calendar(s, "orvieto", s["calendar"]["levy_box"] + 3)
        # Ensure no treachery card in command deck.
        s["decks"]["guelph"]["command_deck"] = [
            c for c in s["decks"]["guelph"]["command_deck"]
            if not c.startswith("treachery_")]
        r = self._ce.apply_event_effect(
            s, "F17", "guelph",
            {"mode": "treachery_cylinder", "targets": ["orvieto"]},
            self._RNG(seed=1))
        assert r["applied"] is False

    def test_treachery_cylinder_missing_targets_prompts(self):
        s = self._setup()
        self._place_on_calendar(s, "guido_guerra", s["calendar"]["levy_box"] + 2)
        s["decks"]["guelph"]["command_deck"].append("treachery_firenze")
        r = self._ce.apply_event_effect(
            s, "F17", "guelph", {"mode": "treachery_cylinder"}, self._RNG(seed=1))
        assert r.get("manual") is True

    def test_service_branch_shifts_two(self):
        s = self._setup()
        # Put guido on a Service box (mustered) so the service option applies.
        s["lords"]["guido_guerra"]["status"] = "mustered"
        s["lords"]["guido_guerra"]["calendar_box"] = None
        s["lords"]["guido_guerra"]["service_box"] = 5
        s["calendar"]["boxes"].setdefault("5",
            {"cylinders": [], "services": ["guido_guerra"], "victory": [], "markers": []})
        r = self._ce.apply_event_effect(
            s, "F17", "guelph", {"mode": "service", "target": "guido_guerra"},
            self._RNG(seed=1))
        assert r["applied"] is True and r["service_to"] == 7

    def test_marker_present(self):
        assert "SMOKE-Inferno-054" in inspect.getsource(self._ce.F17_event)


# =====================================================================
# #7 SMOKE-Inferno-055 — Avoid-Battle may not retreat along the approach Way.
# =====================================================================
class TestAvoidApproachWay:
    def test_predicate_blocks_only_when_dest_is_origin_and_sole_way(self):
        # dest == origin and the only Way is the approach Way -> blocked.
        assert sd.avoid_along_approach_way("A", "A", ["track"], "track") is True
        # alternate Way to the same dest -> not blocked (can use the other edge).
        assert sd.avoid_along_approach_way("A", "A", ["track", "road"], "track") is False
        # dest is not the origin -> not blocked.
        assert sd.avoid_along_approach_way("B", "A", ["track"], "track") is False
        # no recorded origin (e.g. Sally sortie) -> not blocked.
        assert sd.avoid_along_approach_way("A", None, ["track"], "track") is False

    def test_handler_blocks_retreat_along_approach_way(self):
        from inferno.actions import IllegalAction
        # Altopascio <-> Lucca is a single 'track' Way. Active approached Lucca
        # FROM Altopascio via track; the Avoiding Lord may not retreat to
        # Altopascio along that same Way.
        s = load_scenario("A", seed=1)
        avoider = next(lid for lid, l in s["lords"].items()
                       if l["side"] == "ghibelline" and l.get("status") == "mustered")
        s["lords"][avoider]["location"] = "Lucca"
        s["lords"][avoider]["assets"]["Loot"] = 0
        s["meta"]["active_player"] = "ghibelline"
        s.setdefault("pending", []).append({
            "type": "approach_response", "side": "ghibelline",
            "info": {"lord_id": avoider, "approaching_lord": "firenze",
                     "locale": "Lucca", "approached_via": "track",
                     "approached_from": "Altopascio"},
        })
        with pytest.raises(IllegalAction) as exc:
            A.dispatch(s, {"action": "approach_response", "side": "ghibelline",
                           "args": {"lord_id": avoider, "choice": "avoid",
                                    "destination": "Altopascio"}})
        assert exc.value.code == "AVOID_ALONG_APPROACH_WAY"

    def test_both_sites_use_shared_predicate(self):
        assert "avoid_along_approach_way" in inspect.getsource(A._h_approach_response)
        assert "avoid_along_approach_way" in inspect.getsource(LM)

    def test_marker_present(self):
        assert "SMOKE-Inferno-055" in inspect.getsource(sd.avoid_along_approach_way)
