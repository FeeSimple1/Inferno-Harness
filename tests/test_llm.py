"""Tests for the LLM-play harness (post-v1.0)."""
from __future__ import annotations

import pytest

from inferno.actions import dispatch
from inferno.llm import (
    ActionResult,
    FallbackUsed,
    build_briefing,
    build_self_critique_prompt,
    hide_for_side,
    play_with_callback,
)
from inferno.scenarios import load_scenario


class TestHiddenInfoFilter:
    def test_opponent_aow_held_redacted(self):
        s = load_scenario("A", seed=1)
        s["decks"]["ghibelline"]["aow_held"] = ["S12", "S16"]
        filtered = hide_for_side(s, "guelph")
        held = filtered["decks"]["ghibelline"]["aow_held"]
        assert all("<hidden" in str(c) for c in held)

    def test_opponent_aow_deck_redacted(self):
        s = load_scenario("A", seed=1)
        # Pre-populate ghib aow_deck
        s["decks"]["ghibelline"]["aow_deck"] = ["S1", "S2", "S3", "S4"]
        filtered = hide_for_side(s, "guelph")
        deck = filtered["decks"]["ghibelline"]["aow_deck"]
        assert "<hidden:4>" in deck

    def test_own_side_unredacted(self):
        s = load_scenario("A", seed=1)
        # Guelph held should remain visible from guelph perspective
        s["decks"]["guelph"]["aow_held"] = ["F3"]
        filtered = hide_for_side(s, "guelph")
        assert filtered["decks"]["guelph"]["aow_held"] == ["F3"]

    def test_opponent_plan_stacks_face_down(self):
        s = load_scenario("A", seed=1)
        s["plan_stacks"]["ghibelline"] = ["command_siena", "PASS", "PASS"]
        filtered = hide_for_side(s, "guelph")
        assert filtered["plan_stacks"]["ghibelline"] == [
            "<facedown:1>", "<facedown:2>", "<facedown:3>"
        ]

    def test_hidden_mats_obscures_opponent_forces(self):
        s = load_scenario("A", seed=1)
        # Siena (Ghibelline, Mustered) has Cavalieri etc.
        filtered = hide_for_side(s, "guelph", hidden_mats=True)
        siena = filtered["lords"]["siena"]
        assert "<hidden_force_count>" in siena["forces"]
        assert "<hidden>" in siena["assets"]
        # Guelph mats remain visible
        firenze = filtered["lords"]["firenze"]
        assert firenze["forces"].get("Cavalieri", 0) > 0

    def test_filtered_marker_added(self):
        s = load_scenario("A", seed=1)
        filtered = hide_for_side(s, "guelph")
        assert filtered["_filtered_for"] == "guelph"

    def test_invalid_side_rejected(self):
        s = load_scenario("A", seed=1)
        with pytest.raises(ValueError):
            hide_for_side(s, "neutral")


class TestBriefing:
    def test_briefing_includes_scenario_and_side(self):
        s = load_scenario("A", seed=1)
        b = build_briefing(s, "guelph")
        assert "GUELPH" in b
        assert "Scenario A" in b
        assert "Turn 1" in b

    def test_briefing_lists_own_mustered_lords(self):
        s = load_scenario("F", seed=1)
        b = build_briefing(s, "guelph")
        assert "Firenze Podestà" in b
        assert "Arezzo Podestà" in b

    def test_briefing_shows_vp(self):
        s = load_scenario("A", seed=1)
        b = build_briefing(s, "guelph")
        assert "VP" in b

    def test_briefing_within_budget(self):
        s = load_scenario("F", seed=1)
        b = build_briefing(s, "guelph", max_chars=3500)
        assert len(b) <= 3500

    def test_briefing_recent_history(self):
        s = load_scenario("A", seed=1)
        dispatch(s, {"action": "levy_aow_draw", "side": "guelph"})
        dispatch(s, {"action": "levy_aow_draw", "side": "ghibelline"})
        b = build_briefing(s, "guelph")
        assert "levy_aow_draw" in b


class TestPlayWithCallback:
    def test_legal_callback_action_applied(self):
        s = load_scenario("A", seed=1)
        def cb(state, moves):
            return {"action": moves[0]["action"], "side": moves[0]["side"],
                    **({"args": moves[0]["args"]} if "args" in moves[0] else {})}
        r = play_with_callback(s, cb)
        assert r.fallback is None
        assert r.applied is not None

    def test_three_strikes_then_fallback(self):
        s = load_scenario("A", seed=1)
        # Callback that always proposes an illegal action
        def bad_cb(state, moves):
            return {"action": "no_such_action", "side": "guelph"}
        r = play_with_callback(s, bad_cb, max_strikes=3)
        assert r.fallback is not None
        assert "max_strikes (3)" in r.fallback.reason
        assert r.fallback.fallback_action is not None
        assert len(r.rejected) == 3

    def test_fallback_action_is_safe_for_phase(self):
        s = load_scenario("A", seed=1)
        def bad_cb(state, moves):
            return {"action": "cmd_storm", "side": "guelph"}  # wrong phase
        r = play_with_callback(s, bad_cb, max_strikes=2)
        assert r.fallback is not None
        # Phase is levy/3.1 -> fallback should be levy_aow_draw
        assert r.fallback.fallback_action["action"] == "levy_aow_draw"

    def test_callback_exception_counts_as_strike(self):
        s = load_scenario("A", seed=1)
        def crashy_cb(state, moves):
            raise RuntimeError("LLM gave up")
        r = play_with_callback(s, crashy_cb, max_strikes=2)
        assert r.fallback is not None
        assert any("callback_error" in str(rj) for rj in r.rejected)


class TestSelfCritique:
    def test_critique_prompt_includes_outcome(self):
        s = load_scenario("A", seed=1)
        # Force a fake win for Guelph
        s["meta"]["winner"] = "guelph"
        s["vp"] = {"guelph": 6, "ghibelline": 4}
        prompt = build_self_critique_prompt(s, "guelph")
        assert "post-game self-critique" in prompt
        assert "GUELPH" in prompt
        assert "WIN" in prompt

    def test_critique_prompt_includes_history(self):
        s = load_scenario("A", seed=1)
        dispatch(s, {"action": "levy_aow_draw", "side": "guelph"})
        prompt = build_self_critique_prompt(s, "guelph")
        assert "levy_aow_draw" in prompt


# =====================================================================
# Example client (examples/play_with_claude.py) — stub-mode smoke test
# =====================================================================
class TestExampleClient:
    def test_stub_callback_plays_to_terminal(self):
        """The example's stub callback drives a scenario to victory."""
        import importlib.util
        from pathlib import Path
        ex_path = Path(__file__).parent.parent / "examples" / "play_with_claude.py"
        spec = importlib.util.spec_from_file_location("play_with_claude", ex_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        from inferno.scenarios import load_scenario
        from inferno.llm import play_with_callback
        cb = mod.make_stub_callback()
        s = load_scenario("A", seed=42)
        for _ in range(300):
            if s["meta"].get("phase") == "victory":
                break
            play_with_callback(s, cb, max_strikes=3)
        assert s["meta"]["phase"] == "victory"

    def test_parse_action_strips_fences(self):
        import importlib.util
        from pathlib import Path
        ex_path = Path(__file__).parent.parent / "examples" / "play_with_claude.py"
        spec = importlib.util.spec_from_file_location("play_with_claude2", ex_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        parsed = mod._parse_action('```json\n{"action": "levy_pay_done", "side": "guelph"}\n```')
        assert parsed["action"] == "levy_pay_done"
        # Bare JSON with surrounding prose
        parsed2 = mod._parse_action('I choose: {"action": "cmd_pass", "side": "guelph", "args": {"count": 1}} done')
        assert parsed2["action"] == "cmd_pass"
