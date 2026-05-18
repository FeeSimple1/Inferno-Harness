"""Legal-moves enumerator — Phase 0 stub.

Per BRIEF: this is the primary interface an LLM uses to decide what to
do. Phase 2+ implements real enumeration per phase / pending decision.
"""

from __future__ import annotations

from typing import Any


def enumerate_legal(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all legal actions for `state.meta.active_player` in the
    current phase.

    Phase 0 returns an empty list with a single explanatory note. Phase
    2+ replaces this with real enumeration.
    """
    return [
        {
            "action": "<phase_0_stub>",
            "description": "legal-moves enumeration not implemented in Phase 0. See BRIEF.md.",
            "rule_citation": None,
        }
    ]
