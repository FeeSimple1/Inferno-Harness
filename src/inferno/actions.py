"""Action dispatcher — Phase 0 stub.

Phase 2+ implements real action handlers. See ACTIONS.md for the action
grammar specification.
"""

from __future__ import annotations

from typing import Any


class IllegalAction(Exception):
    """Raised when an action fails rule validation.

    Per BRIEF: error messages MUST include rule citations.
    """

    def __init__(self, code: str, message: str, citation: str | None = None):
        self.code = code
        self.citation = citation
        super().__init__(f"[{code}] {message}" + (f" ({citation})" if citation else ""))


def dispatch(state: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    """Apply `action` to `state`, returning a result dict.

    Phase 0: raises NotImplementedError. Phase 2+ implements real
    handlers per action type.
    """
    action_name = action.get("action", "<unknown>")
    raise NotImplementedError(
        f"Action {action_name!r} not implemented in Phase 0. See BRIEF.md "
        "for the phase plan and ACTIONS.md for the action grammar."
    )
