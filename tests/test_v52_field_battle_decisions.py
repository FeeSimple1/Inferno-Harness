"""v5.2 — ordinary field-Battle tactical choices are reachable from the
public action interface.

Background: Storm and Sally already accept ``scripted_decisions`` so an
operator (test or LLM) can pin array placement, tie-breaks, hit allocation,
and concession. Ordinary March-triggered field Battles, however, called
``resolve_battle()`` with no decision channel, so they always fell back to the
deterministic leftmost choice. These tests lock in that ``approach_response``
now threads ``scripted_decisions`` (and, for in-process self-play, a
``state['battle_callback']``) through ``_finalize_approach`` into the field
Battle, with the transient queue accumulated across the response window and
never leaking into a later Battle.
"""
from __future__ import annotations

import inferno.battle as battle_mod
from inferno.actions import dispatch
from tests.test_phase3b import _to_command_phase


def _setup_approach(seed=1):
    """Firenze (Guelph, Active) one-step Road March into Figline where the
    Siena Podesta (Ghibelline) sits, triggering an Approach with a single
    potential Stander."""
    s = _to_command_phase("A", seed=seed, lord_for_active="firenze")
    siena_loc = s["lords"]["siena"]["location"]
    s["locales"][siena_loc]["lords_present"].remove("siena")
    s["locales"]["Figline"]["lords_present"].append("siena")
    s["lords"]["siena"]["location"] = "Figline"
    return s


def _march_to_figline(s):
    dispatch(s, {"action": "cmd_march", "side": "guelph",
                 "args": {"lord_id": "firenze",
                          "destination": "Figline", "way_type": "road"}})


class TestFieldBattleDecisionPlumbing:
    def test_scripted_decisions_reach_resolve_battle(self, monkeypatch):
        """A scripted_decisions list attached to the Stand response is handed
        to resolve_battle for an ordinary field Battle (was dropped before)."""
        s = _setup_approach(seed=99)
        _march_to_figline(s)

        captured = {}
        real = battle_mod.resolve_battle

        def spy(*a, **kw):
            captured["scripted"] = kw.get("scripted_decisions")
            captured["callback"] = kw.get("callback")
            return real(*a, **kw)

        monkeypatch.setattr(battle_mod, "resolve_battle", spy)

        script = [{"type": "concede", "choice": "no"}] * 20
        r = dispatch(s, {"action": "approach_response", "side": "ghibelline",
                         "args": {"lord_id": "siena", "choice": "stand",
                                  "scripted_decisions": script}})

        assert r["state_changes"]["approach_resolved"] == "battle"
        assert captured["scripted"] == script

    def test_no_scripted_decisions_still_resolves_leftmost(self, monkeypatch):
        """Backwards-compatible: without a script, the field Battle still runs
        and resolve_battle receives scripted_decisions=None (leftmost)."""
        s = _setup_approach(seed=99)
        _march_to_figline(s)

        captured = {}
        real = battle_mod.resolve_battle

        def spy(*a, **kw):
            captured["scripted"] = kw.get("scripted_decisions")
            return real(*a, **kw)

        monkeypatch.setattr(battle_mod, "resolve_battle", spy)

        r = dispatch(s, {"action": "approach_response", "side": "ghibelline",
                         "args": {"lord_id": "siena", "choice": "stand"}})

        assert r["state_changes"]["approach_resolved"] == "battle"
        assert captured["scripted"] is None
        assert "decisions" in r["state_changes"]["battle_result"]

    def test_battle_callback_threaded_for_self_play(self, monkeypatch):
        """An in-process callback on state is used when no scripted list is
        given (enables live tactical control in genuine self-play)."""
        s = _setup_approach(seed=99)
        _march_to_figline(s)

        seen = []

        def cb(req):
            seen.append(req["type"])
            return req["options"][0]

        s["battle_callback"] = cb

        captured = {}
        real = battle_mod.resolve_battle

        def spy(*a, **kw):
            captured["callback"] = kw.get("callback")
            return real(*a, **kw)

        monkeypatch.setattr(battle_mod, "resolve_battle", spy)

        dispatch(s, {"action": "approach_response", "side": "ghibelline",
                     "args": {"lord_id": "siena", "choice": "stand"}})

        assert captured["callback"] is cb

    def test_decision_queue_is_drained_and_does_not_leak(self):
        """The transient approach_battle_decisions queue is cleared once the
        Approach resolves, so a later Battle cannot inherit a stale script."""
        s = _setup_approach(seed=99)
        _march_to_figline(s)
        dispatch(s, {"action": "approach_response", "side": "ghibelline",
                     "args": {"lord_id": "siena", "choice": "stand",
                              "scripted_decisions": [
                                  {"type": "concede", "choice": "no"}] * 20}})
        assert not s.get("approach_battle_decisions")

    def test_no_queue_left_when_defender_avoids(self):
        """If the defender Avoids (no Battle), any supplied script is still
        cleaned up rather than lingering for the next Approach."""
        s = _setup_approach(seed=99)
        _march_to_figline(s)
        dispatch(s, {"action": "approach_response", "side": "ghibelline",
                     "args": {"lord_id": "siena", "choice": "avoid",
                              "destination": "San Giovanni",
                              "scripted_decisions": [
                                  {"type": "concede", "choice": "no"}]}})
        assert not s.get("approach_battle_decisions")
