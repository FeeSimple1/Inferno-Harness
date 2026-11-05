"""Transient combat visibility, outside the saved mechanical game state."""
from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
import inspect
from contextlib import contextmanager

_COMBAT = ContextVar('inferno_combat_visibility', default=None)


def friars_active(state: dict) -> bool:
    """Recognize both duration records and older explicit S14 effect flags."""
    return any(event.get('id') == 'S14'
               or event.get('effect') == 'guelph_plan_blind_no_inspect'
               for event in state.get('active_events', {}).get('this_campaign', []))


def combat_view_scope(attacker_argument: str, defender_argument: str):
    """Reveal only actual participating mats during synchronous combat choices."""
    def decorate(function):
        signature = inspect.signature(function)
        @wraps(function)
        def wrapped(*args, **kwargs):
            bound = signature.bind(*args, **kwargs)
            state = bound.arguments['state']
            attackers = list(bound.arguments.get(attacker_argument, []))
            defenders = list(bound.arguments.get(defender_argument, []))
            atk_side = next((state['lords'][lid]['side'] for lid in attackers if lid in state['lords']), None)
            def_side = next((state['lords'][lid]['side'] for lid in defenders if lid in state['lords']),
                            ('ghibelline' if atk_side == 'guelph' else 'guelph'))
            token = _COMBAT.set({'state_id': id(state), 'lords': set(attackers + defenders),
                                 'attacker': atk_side, 'defender': def_side})
            try:
                return function(*args, **kwargs)
            finally:
                _COMBAT.reset(token)
        return wrapped
    return decorate


def combat_visibility(state: dict) -> dict:
    scope = _COMBAT.get()
    return scope if scope and scope['state_id'] == id(state) else {}


_STRICT = ContextVar('inferno_strict_player_choices', default=False)

@contextmanager
def strict_player_choices():
    token = _STRICT.set(True)
    try:
        yield
    finally:
        _STRICT.reset(token)


def player_choice_required() -> bool:
    return _STRICT.get()
