"""LLM-play harness — beyond BRIEF, per CROSS_PROJECT_LESSONS §5.

Provides the integration layer between the rules engine and a human-
language model that will play one or both sides.

Components:
  filter.py        — Hidden-info filter (strip opposing hand / plan /
                     held events / set-aside Treachery / Calendar
                     cylinder secrets from the state seen by side S).
  briefing.py      — Curated ~3 KB briefing builder for system prompt:
                     game state, current phase, recent history, on-
                     demand card-text lookups, strategy hints.
  player.py        — play_with_callback(prompt -> action_json):
                     3-strike retry with safe phase-appropriate fallback
                     so a hallucinating LLM never deadlocks the game.
  critique.py      — Post-game self-critique helper: hands the
                     transcript back with "what would you do differently?"

These are deliberately framework-agnostic: the user wires the
callback to Claude, GPT, or any other model.
"""
from __future__ import annotations

from .filter import hide_for_side
from .briefing import build_briefing
from .player import play_with_callback, ActionResult, FallbackUsed
from .critique import build_self_critique_prompt

__all__ = [
    "hide_for_side",
    "build_briefing",
    "play_with_callback",
    "ActionResult",
    "FallbackUsed",
    "build_self_critique_prompt",
]
