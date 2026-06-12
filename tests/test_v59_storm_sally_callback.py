"""v5.9 — Storm and Sally thread state['battle_callback'] into combat.

Bug (Fable edge-case hunt #10): ``resolve_storm`` and ``resolve_sally`` both
accept a ``callback`` parameter, and field Battles (and even the Sally
POST-battle retreat context) pass ``state['battle_callback']`` — but the
``cmd_storm`` / ``cmd_sally`` handlers never did for the combat itself. A
self-play operator steering tactics through ``battle_callback`` silently lost
control in every Storm and Sally (concede, reserve adds, hit allocation all
fell back to leftmost) with no error.
"""
from __future__ import annotations

import inferno.battle as battle_mod
from inferno.actions import dispatch
from tests.test_phase3c import _to_command_with


def _besieged_storm_state():
    """Firenze (Guelph, active) at Volterra with a Guelph Siege in place."""
    s = _to_command_with("A", seed=1, lord_id="firenze",
                         lord_location_override="Volterra")
    s["locales"]["Volterra"]["siege"] = [
        {"side": "guelph", "color": "gold", "count": 3}]
    return s


class TestStormSallyCallbackPlumbing:
    def test_cmd_storm_threads_battle_callback(self, monkeypatch):
        s = _besieged_storm_state()
        sentinel_calls = []

        def sentinel(q):
            sentinel_calls.append(q)
            return q["options"][0]

        s["battle_callback"] = sentinel
        captured = {}
        real = battle_mod.resolve_storm

        def spy(*a, **kw):
            captured["callback"] = kw.get("callback")
            return real(*a, **kw)

        monkeypatch.setattr(battle_mod, "resolve_storm", spy)
        import inferno.actions as actions_mod
        monkeypatch.setattr(actions_mod, "resolve_storm", spy, raising=False)

        dispatch(s, {"action": "cmd_storm", "side": "guelph",
                     "args": {"lord_id": "firenze"}})

        assert captured["callback"] is sentinel, \
            "cmd_storm must hand state['battle_callback'] to resolve_storm"

    def test_cmd_sally_threads_battle_callback(self, monkeypatch):
        """Siena (Ghibelline) besieged inside Siena by Firenze: Sally must
        receive the callback for its in-Battle decisions."""
        s = _to_command_with("A", seed=1, lord_id="siena",
                             lord_location_override="Siena")
        # Firenze besieges Siena; Siena Podesta is inside the Stronghold.
        f = s["lords"]["firenze"]
        s["locales"][f["location"]]["lords_present"].remove("firenze")
        s["locales"]["Siena"]["lords_present"].append("firenze")
        f["location"] = "Siena"
        s["locales"]["Siena"]["siege"] = [
            {"side": "guelph", "color": "gold", "count": 1}]
        s["lords"]["siena"].setdefault("flags", {})["in_stronghold"] = True

        sentinel_calls = []

        def sentinel(q):
            sentinel_calls.append(q)
            return q["options"][0]

        s["battle_callback"] = sentinel
        captured = {}
        real = battle_mod.resolve_sally

        def spy(*a, **kw):
            captured["callback"] = kw.get("callback")
            return real(*a, **kw)

        monkeypatch.setattr(battle_mod, "resolve_sally", spy)
        import inferno.actions as actions_mod
        monkeypatch.setattr(actions_mod, "resolve_sally", spy, raising=False)

        dispatch(s, {"action": "cmd_sally", "side": "ghibelline",
                     "args": {"lord_id": "siena"}})

        assert captured["callback"] is sentinel, \
            "cmd_sally must hand state['battle_callback'] to resolve_sally"
