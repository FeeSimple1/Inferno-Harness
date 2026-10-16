"""Loss-aware, perspective-safe model interface.

Default: PlayerView / play_with_interface. Legacy play_with_callback is only
for trusted in-process automation; do not send its raw state/menu to a model.
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

from .interface import PlayerView, DecisionView, play_with_interface, selection_session
from .menu import ActionCatalog, submit_selection
from .briefing import build_briefing_document, render_briefing
from .protocol import state_version

__all__ += ["PlayerView", "DecisionView", "play_with_interface", "ActionCatalog",
            "submit_selection", "selection_session", "build_briefing_document", "render_briefing", "state_version"]

from .strategic_memory import StrategicMemory
__all__ += ["StrategicMemory"]
