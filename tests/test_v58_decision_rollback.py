"""v5.8 — transactional dispatch: an invalid operator decision cannot corrupt
state.

Bug (Fable self-play, scenario F): an invalid ``scripted_decisions`` entry
(wrong type, wrong side, or a choice outside the legal options) raised a bare
``ValueError`` from ``BattleDecisionContext.decide`` AFTER the Battle had
started mutating state. The exception escaped ``dispatch`` with units already
routed, the pending approach window consumed, and the card flow stranded —
and, because it was not an ``IllegalAction``, the LLM player's retry loop
(``play_with_callback``) could not catch it either.

Fix: ``dispatch`` snapshots the state before invoking a handler and restores
it on ANY handler exception; operator-input decision errors are raised as
``ScriptedDecisionError`` and surfaced as ``IllegalAction("BAD_DECISION")``.
"""
from __future__ import annotations

import copy

import pytest

from inferno.actions import IllegalAction, dispatch
from inferno.battle import ScriptedDecisionError
from tests.test_v52_field_battle_decisions import _setup_approach, _march_to_figline


def _stand_with(script):
    return {"action": "approach_response", "side": "ghibelline",
            "args": {"lord_id": "siena", "choice": "stand",
                     "scripted_decisions": script}}


class TestBadScriptedDecisionRollsBack:
    def test_invalid_choice_raises_illegal_action_and_state_intact(self):
        s = _setup_approach(seed=99)
        _march_to_figline(s)
        before = copy.deepcopy(s)

        with pytest.raises(IllegalAction) as ei:
            dispatch(s, _stand_with([{"type": "concede", "choice": "nonsense"}]))

        assert ei.value.code == "BAD_DECISION"
        assert s == before, "state must be untouched after a rejected decision"

    def test_wrong_type_raises_illegal_action_and_state_intact(self):
        s = _setup_approach(seed=99)
        _march_to_figline(s)
        before = copy.deepcopy(s)

        with pytest.raises(IllegalAction) as ei:
            dispatch(s, _stand_with([{"type": "flanker_target", "choice": "x"}]))

        assert ei.value.code == "BAD_DECISION"
        assert s == before

    def test_retry_with_valid_decision_succeeds_after_rejection(self):
        """The exact recovery path an LLM operator takes: rejected decision,
        then a corrected one — the Battle must resolve normally."""
        s = _setup_approach(seed=99)
        _march_to_figline(s)

        with pytest.raises(IllegalAction):
            dispatch(s, _stand_with([{"type": "concede", "choice": "nonsense"}]))

        r = dispatch(s, _stand_with([{"type": "concede", "choice": "no"}]))
        assert r["state_changes"]["approach_resolved"] == "battle"

    def test_scripted_decision_error_is_value_error_subclass(self):
        """Back-compat: callers that caught ValueError still catch the new
        exception type."""
        assert issubclass(ScriptedDecisionError, ValueError)
