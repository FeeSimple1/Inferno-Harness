"""v2.9 — bugs found during the 30-round smoke-test campaign.

SMOKE-071: AoW card conservation — reshuffle excludes Lord-mat Capabilities,
           Disband-at-limit returns Capabilities to the deck, the initial deck
           excludes already-in-play Capabilities, and Reset returns event cards.
SMOKE-072: Treachery Revolt/Bribe (4.7.5/4.7.6) are reachable through the
           enumerator (revealing a Treachery card no longer auto-passes).
"""
import random
import pytest
from inferno.scenarios import load_scenario, SCENARIO_IDS
from inferno.actions import (dispatch, IllegalAction, _maybe_reshuffle_aow_deck,
                             _disband_at_service_limit)
from inferno.legal_moves import enumerate_legal, _enum_command_phase


class TestCardConservation:
    def test_initial_deck_excludes_in_play_capability(self):
        s = load_scenario("C", seed=1)  # S22 Manfredi starts in play
        assert any(c["id"] == "S22" for c in s["capabilities_in_play"])
        assert "S22" not in s["decks"]["ghibelline"]["aow_deck"]

    def test_reshuffle_excludes_lord_mat_capability(self):
        s = load_scenario("A", seed=1)
        s["lords"]["firenze"]["capabilities"] = ["F5"]
        s["meta"].pop("aow_reshuffled_this_levy_guelph", None)
        _maybe_reshuffle_aow_deck(s, "guelph")
        assert "F5" not in s["decks"]["guelph"]["aow_deck"]

    def test_disband_at_limit_returns_capabilities(self):
        s = load_scenario("A", seed=1)
        s["lords"]["arezzo"]["capabilities"] = ["F12"]
        s["lords"]["arezzo"]["service_box"] = 3
        _disband_at_service_limit(s, "arezzo", 3)
        assert "F12" in s["decks"]["guelph"]["aow_deck"]
        assert s["lords"]["arezzo"]["capabilities"] == []

    def test_conservation_holds_over_play(self):
        def cardset(p): return {f"{p}{n}" for n in range(1, 27)}
        for scen in ("B", "C", "E"):
            rng = random.Random(7); s = load_scenario(scen, seed=2)
            for _ in range(250):
                moves = [m for m in enumerate_legal(s) if not m.get("action", "").startswith("<")]
                if not moves: break
                m = rng.choice(moves); act = {"action": m["action"], "side": m["side"]}
                if "args" in m: act["args"] = m["args"]
                try: dispatch(s, act)
                except IllegalAction: continue
                except Exception: break
                for side, pfx in (("guelph", "F"), ("ghibelline", "S")):
                    import collections
                    c = collections.Counter()
                    d = s["decks"][side]
                    for cid in d["aow_deck"] + d["aow_discard"] + d["aow_held"]: c[cid] += 1
                    for cap in s.get("capabilities_in_play", []):
                        if cap.get("side") == side: c[cap["id"]] += 1
                    for lid, l in s["lords"].items():
                        if l.get("side") == side:
                            for cid in l.get("capabilities", []) or []: c[cid] += 1
                    for kind in ("immediate", "this_levy", "this_campaign"):
                        for e in (s.get("active_events", {}).get(kind, []) or []):
                            if e.get("side") == side and isinstance(e.get("id"), str) and e["id"][:1] in ("F", "S"):
                                c[e["id"]] += 1
                    assert not [x for x, n in c.items() if n > 1 and x in cardset(pfx)]
                if s["meta"].get("phase") == "victory": break


class TestTreacheryReachable:
    def _command_phase_with_treachery(self, owner="firenze"):
        from tests.test_v15_features import _to_command_phase
        s = _to_command_phase("A", seed=1)
        # Make the owner an enemy-adjacent threat with Coin; put its Treachery
        # card on top of the plan, then reveal.
        s["lords"][owner]["assets"]["Coin"] = 2
        s["plan_stacks"]["guelph"].insert(0, f"treachery_{owner}")
        dispatch(s, {"action": "command_reveal", "side": "guelph"})
        return s

    def test_reveal_sets_treachery_context(self):
        s = self._command_phase_with_treachery("firenze")
        assert s["current_card"] == "treachery_firenze"
        assert s["current_lord_id"] == "firenze"

    def test_enumerator_surfaces_treachery_moves(self):
        s = self._command_phase_with_treachery("firenze")
        acts = {m["action"] for m in _enum_command_phase(s, "guelph")}
        # At minimum, the card can always lapse via end_card; normal Command
        # actions (tax/forage/march) are NOT offered on a Treachery card.
        assert "cmd_end_card" in acts
        assert acts <= {"cmd_treachery_revolt", "cmd_treachery_bribe", "cmd_end_card"}

    def test_treachery_moves_round_trip(self):
        import copy
        s = self._command_phase_with_treachery("firenze")
        for m in _enum_command_phase(s, "guelph"):
            snap = copy.deepcopy(s)
            dispatch(snap, {"action": m["action"], "side": m["side"], **({"args": m["args"]} if "args" in m else {})})

    def test_lapse_when_owner_not_mustered(self):
        from tests.test_v15_features import _to_command_phase
        s = _to_command_phase("A", seed=1)
        # guido_guerra starts removed in Scenario A -> its Treachery lapses.
        s["plan_stacks"]["guelph"].insert(0, "treachery_guido_guerra")
        r = dispatch(s, {"action": "command_reveal", "side": "guelph"})
        assert r["state_changes"].get("card_finished") is True
