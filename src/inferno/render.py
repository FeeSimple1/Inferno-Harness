"""State rendering — Phase 0 stub.

Per BRIEF: state command must support summary mode (~500 tokens),
verbose mode (full state), and focused views (single Lord, Locale,
Calendar, deck). Phase 1+ implements real rendering.
"""

from __future__ import annotations

import json
from typing import Any


def render_summary(state: dict[str, Any]) -> str:
    """Compact view sufficient for routine LLM decisions."""
    meta = state.get("meta", {})
    scenario = meta.get("scenario", "<none>")
    turn = meta.get("turn", "?")
    phase = meta.get("phase", "?")
    active = meta.get("active_player", "?")
    return (
        f"Inferno harness — Phase 0 stub\n"
        f"  scenario: {scenario}\n"
        f"  turn: {turn}\n"
        f"  phase: {phase}\n"
        f"  active_player: {active}\n"
        f"  (full rendering not implemented in Phase 0)"
    )


def render_verbose(state: dict[str, Any]) -> str:
    """Full state dump (JSON pretty-printed)."""
    return json.dumps(state, indent=2, sort_keys=True)
