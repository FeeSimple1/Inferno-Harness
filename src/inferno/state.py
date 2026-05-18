"""State model — sketch only.

Phase 0 defines the top-level shape via TypedDicts. Phase 1 fills in the
real data (Lords, Locales, Calendar, decks) and the loader from scenario
files. See BRIEF.md "Architecture Requirements" and "LLM-Consumer
Interface".

The state file is JSON-serializable end to end. No Python-only objects
(dataclasses-with-default-factories that hold runtime handles, etc.)
should appear in the persisted structure.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

Side = Literal["guelph", "ghibelline"]


class Meta(TypedDict, total=False):
    """Top-level run metadata."""

    scenario: str               # "A".."F"
    rules_edition: str          # "living_rules_2023-04-10"
    rng_seed: int
    turn: int                   # 1-based Calendar box of current turn
    phase: Literal["levy", "campaign", "feed_pay_disband", "end_campaign", "victory"]
    levy_step: str | None       # 3.1..3.5 sub-step when phase == "levy"
    active_player: Side
    game_over: bool
    winner: Side | None


class State(TypedDict, total=False):
    """Top-level state object. Phase 1 fleshes out the sub-fields."""

    meta: Meta
    calendar: dict[str, Any]            # box -> markers
    lords: dict[str, Any]               # lord_id -> Lord data
    locales: dict[str, Any]             # locale_id -> Locale data
    decks: dict[str, Any]               # per-side AoW deck composition
    capabilities_in_play: list[Any]     # side-wide capabilities
    pending: list[Any]                  # pending decisions, see BRIEF "Non-Combat Pending Decisions"
    history: list[Any]                  # last N action results
    vp: dict[Side, float]               # running VP totals (cap 17.5 per rule 5.x)
