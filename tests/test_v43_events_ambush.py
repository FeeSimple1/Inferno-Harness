"""v4.3: held-event play-window guard (SMOKE-094) + Ambush approach-window
enumeration (SMOKE-095)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from inferno.scenarios import load_scenario
from inferno.actions import dispatch, IllegalAction
from inferno.legal_moves import enumerate_legal
from tests.test_phase3b import _to_command_phase


class TestHoldEventWindowGuard:
    def test_combat_window_event_rejected_with_no_window(self):
        # F6 'Hills' is a battle-window Hold; playing it with no combat open is illegal.
        s = load_scenario("A", seed=1)
        s["decks"]["guelph"]["aow_held"].append("F6")
        with pytest.raises(IllegalAction) as exc:
            dispatch(s, {"action": "play_event", "side": "guelph", "args": {"card_id": "F6"}})
        assert exc.value.code == "NO_PLAY_WINDOW"

    def test_combat_window_event_ok_when_besieging(self):
        s = load_scenario("A", seed=1)
        s["decks"]["guelph"]["aow_held"].append("F6")
        fl = s["lords"]["firenze"]
        s["locales"][fl["location"]].setdefault("siege", []).append(
            {"side": "guelph", "color": "gold", "count": 1})
        r = dispatch(s, {"action": "play_event", "side": "guelph", "args": {"card_id": "F6"}})
        assert r["state_changes"]["played"] == "F6"


class TestAmbushApproachWindow:
    def _approach_with_F1(self):
        s = _to_command_phase("A", seed=1, lord_for_active="firenze")
        if "F1" not in s["decks"]["guelph"]["aow_held"]:
            s["decks"]["guelph"]["aow_held"].append("F1")
        sl = s["lords"]["siena"]["location"]
        if "siena" in s["locales"][sl]["lords_present"]:
            s["locales"][sl]["lords_present"].remove("siena")
        s["lords"]["siena"]["location"] = "Figline"
        s["locales"]["Figline"]["lords_present"].append("siena")
        dispatch(s, {"action": "cmd_march", "side": "guelph",
                     "args": {"lord_id": "firenze", "destination": "Figline", "way_type": "road"}})
        return s

    def test_ambush_offered_and_pins_lord(self):
        s = self._approach_with_F1()
        # F1 offered to the attacker during the defender's response window
        assert any(m["action"] == "play_event" and m["args"].get("card_id") == "F1"
                   and m["side"] == "guelph" for m in enumerate_legal(s))
        dispatch(s, {"action": "play_event", "side": "guelph", "args": {"card_id": "F1"}})
        # cmd_play_ambush now offered, targeting the open-response Lord
        amb = [m for m in enumerate_legal(s) if m["action"] == "cmd_play_ambush"]
        assert any(m["args"].get("target_lord_id") == "siena" for m in amb)
        dispatch(s, {"action": "cmd_play_ambush", "side": "guelph", "args": {"target_lord_id": "siena"}})
        # The pinned Lord may no longer Avoid (menu must not offer it).
        opts = [m["args"].get("choice") for m in enumerate_legal(s)
                if m["action"] == "approach_response" and m["args"].get("lord_id") == "siena"]
        assert "avoid" not in opts and "stand" in opts

    def test_no_ambush_offered_without_card(self):
        s = _to_command_phase("A", seed=1, lord_for_active="firenze")
        # Ensure F1 is NOT held
        if "F1" in s["decks"]["guelph"]["aow_held"]:
            s["decks"]["guelph"]["aow_held"].remove("F1")
        sl = s["lords"]["siena"]["location"]
        if "siena" in s["locales"][sl]["lords_present"]:
            s["locales"][sl]["lords_present"].remove("siena")
        s["lords"]["siena"]["location"] = "Figline"
        s["locales"]["Figline"]["lords_present"].append("siena")
        dispatch(s, {"action": "cmd_march", "side": "guelph",
                     "args": {"lord_id": "firenze", "destination": "Figline", "way_type": "road"}})
        assert not any(m["action"] in ("play_event", "cmd_play_ambush") for m in enumerate_legal(s))
