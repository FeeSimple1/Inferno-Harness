"""Default player interface: overview -> unlimited focused reads -> selection.

The model gets neither the authoritative state nor an unsolicited full menu.
All reads use the same perspective filter. Exhausting retries pauses play; it
never silently chooses a strategic action on behalf of a player.
"""
from __future__ import annotations

import copy
import hashlib
from types import SimpleNamespace
from typing import Callable

from ..actions import IllegalAction, dispatch
from ..battle import ScriptedDecisionError
from ..visibility import combat_visibility, strict_player_choices
from .briefing import build_briefing_document, information_page, render_briefing
from .menu import ActionCatalog, acting_side
from .player import ActionResult
from .protocol import (compact, page_records, query_position, require_version,
                       state_version, view_version, visible_state)


class PlayerView:
    """Immutable public snapshot with live freshness checking on every read."""
    def __init__(self, state: dict, side: str | None = None, *, max_chars: int | None = 3500,
                 hidden_mats: bool | None = None, can_yield: bool = False):
        self._state = state  # private, trusted host only; never serialized
        self.side = side or acting_side(state)
        self._catalog = ActionCatalog(state, self.side, hidden_mats)
        self.version = self._catalog.version
        self.max_chars = max_chars
        self.can_yield = can_yield

    def _fresh(self):
        require_version(self.version, state_version(self._state, self.side, self._catalog.hidden_mats))

    def overview(self) -> dict:
        self._fresh()
        document = build_briefing_document(self._state, self.side, self.max_chars,
                                           catalog=self._catalog)
        return {'state_version': self.version, 'perspective': self.side,
                'acting_player': self._catalog.acting_player,
                'briefing': render_briefing(document),
                'can_yield': self.can_yield,
                **({'single_action': copy.deepcopy(self._catalog.entries[0])} if len(self._catalog.entries) == 1 else {}),
                'selection': {'action_id': '<ID from an action page>', 'state_version': self.version},
                'retrieval': 'Use request=actions (optional category/lord/card/where/cursor) or request=inspect (section/keys/cursor). Reads never spend a turn. No limit on the number of lookups.'}

    def query(self, request: dict) -> dict:
        self._fresh()
        if not isinstance(request, dict):
            raise IllegalAction('BAD_REQUEST', 'A retrieval request must be a JSON object.')
        args = copy.deepcopy(request)
        supplied = args.pop('state_version', self.version)
        require_version(supplied, self.version)
        operation = args.pop('request', None)
        try:
            if operation == 'overview':
                if args:
                    raise TypeError('overview takes no other arguments')
                return self.overview()
            if operation == 'actions':
                return self._catalog.page(**args)
            if operation == 'inspect':
                return information_page(self._catalog, **args)
        except TypeError as exc:
            raise IllegalAction('BAD_REQUEST', 'Invalid retrieval parameters; no state was changed.') from exc
        raise IllegalAction('BAD_REQUEST', 'Choose overview, actions or inspect.')

    def resolve(self, selection: dict) -> dict:
        self._fresh()
        return self._catalog.resolve(selection)


class DecisionView:
    """A synchronous combat election: exact context and every legal option."""
    def __init__(self, state: dict, payload: dict, owner: str, parent_version: str, ordinal: int, hidden_mats: bool | None = None):
        self.side = owner
        self._state = state
        self._payload = copy.deepcopy(payload)
        view = visible_state(state, owner, hidden_mats)
        self._hidden_mats = view["_hidden_mats"]
        self._position_version = view_version(view)
        identity = compact({'parent': parent_version, 'ordinal': ordinal, 'payload': self._payload})
        self.version = f"{self._position_version}/d{ordinal}-" + hashlib.sha256(identity.encode()).hexdigest()[:16]
        self._catalog = SimpleNamespace(view=view, version=self.version)
        self._entries = []
        for i, option in enumerate(payload['options']):
            # Preserve the engine's order; pagination does not choose a default.
            self._entries.append({'action_id': 'd-' + hashlib.sha256(f'{self.version}/option-{i}'.encode()).hexdigest()[:16],
                                  'move': {'action':'combat_decision', 'side':owner,
                                           'args': {'choice': copy.deepcopy(option)}},
                                  'parameterized':False})
        self.can_yield = False

    def _fresh(self):
        require_version(self._position_version, state_version(self._state, self.side, self._hidden_mats))

    def overview(self) -> dict:
        self._fresh()
        scope = combat_visibility(self._state)
        # Revealed mats are complete records, not rough or ranked strengths.
        mats = {lid: self._catalog.view['lords'][lid] for lid in sorted(scope.get('lords', []))
                if lid in self._catalog.view['lords']}
        return {'state_version': self.version, 'perspective':self.side,
                'acting_player':self.side, 'decision':self._payload['type'],
                'context':self._payload.get('info', {}), 'participating_mats':mats,
                'option_count':len(self._entries), 'available_kinds':['combat_decision'],
                'retrieval':{'request':'actions'}, 'can_yield':False,
                'selection':{'action_id':'<option ID>', 'state_version':self.version},
                'note':'This is a player election, not a new Command. Every option is accessible; no choice is assumed on a failed or incomplete reply.'}

    def query(self, request: dict) -> dict:
        self._fresh()
        if not isinstance(request, dict):
            raise IllegalAction('BAD_REQUEST', 'A retrieval request must be an object.')
        args = copy.deepcopy(request)
        require_version(args.pop('state_version', self.version), self.version)
        operation = args.pop('request', None)
        if operation == 'overview' and not args:
            return self.overview()
        try:
            if operation == 'inspect':
                return information_page(self._catalog, **args)
            if operation == 'actions':
                category = args.pop('category', 'combat_decision')
                if category != 'combat_decision':
                    raise IllegalAction('BAD_FILTER', 'This choice has only the combat_decision category.')
                cursor = args.pop('cursor', None)
                offset, filters = query_position(cursor, self.version, 'decision', {})
                return page_records(self._entries, self.version, 'decision', filters, offset, **args)
        except TypeError as exc:
            raise IllegalAction('BAD_REQUEST', 'Invalid decision lookup parameters.') from exc
        raise IllegalAction('BAD_REQUEST', 'Choose overview, actions or inspect.')

    def resolve(self, selection: dict):
        self._fresh()
        if not isinstance(selection, dict) or set(selection) != {'action_id','state_version'}:
            raise IllegalAction('BAD_SELECTION', 'A combat election requires action_id and state_version.')
        require_version(selection.get('state_version'), self.version)
        for entry in self._entries:
            if entry['action_id'] == selection.get('action_id'):
                return copy.deepcopy(entry['move']['args']['choice'])
        raise IllegalAction('STALE_ACTION', 'Unknown combat option for this decision.')


def _call_for_selection(view, callback, max_strikes):
    rejected = []
    for _ in range(max_strikes):
        try:
            selection = callback(view)
            if isinstance(selection, dict) and selection.get('yield') is True:
                if not view.can_yield or set(selection) != {'yield','state_version'}:
                    raise IllegalAction('BAD_SELECTION', 'Only an optional reaction window can be yielded.')
                view._fresh()
                require_version(selection.get('state_version'), view.version)
                return None, rejected
            return view.resolve(selection), rejected
        except (IllegalAction, ValueError, TypeError) as exc:
            rejected.append(({'error': type(exc).__name__}, str(exc)))
    raise IllegalAction('PLAYER_CHOICE_REQUIRED',
                        f'No valid complete selection after {max_strikes} attempts. Play is paused; no fallback action was chosen.')


def _require_live_elections(state: dict, action: dict) -> None:
    # Bulk operator scripts may contain the OPPONENT'S future choices. The
    # player transport exposes the same elections via owner-bound DecisionView,
    # rather than letting the initiating faction pre-empt another player.
    args = action.get('args', {})
    if any(args.get(k) for k in ('scripted_decisions', 'post_battle_decisions')) or any(
            state.get(k) for k in ('approach_battle_decisions', 'approach_post_battle_decisions')):
        raise IllegalAction('OWNER_DECISION_REQUIRED',
            'Bulk tactical scripts are trusted-operator inputs. In player mode, make the same choices through each owning faction’s versioned DecisionView; no action was applied.')


def play_with_interface(state: dict, callback: Callable, *, max_strikes: int = 3,
                        decision_callback: Callable | None = None,
                        max_chars: int | None = 3500) -> ActionResult:
    """Apply one selected action. Both factions' reactions and combat choices
    are routed to their own PlayerView/DecisionView, including when they are
    not meta.active_player. callback(view) may issue as many queries as needed.

    A callback is trusted host code. Only its JSON/text view outputs should be
    sent to a model. It must not introspect the private host state.
    """
    if type(max_strikes) is not int or max_strikes < 1:
        raise ValueError('max_strikes must be positive')
    owner = acting_side(state)
    attacker = state.get('meta', {}).get('approach_attacker_side')
    if attacker and attacker != owner and any(p.get('type') == 'approach_response' for p in state.get('pending', [])):
        reaction = PlayerView(state, attacker, max_chars=max_chars, can_yield=True)
        if reaction._catalog.entries:
            action, rejected = _call_for_selection(reaction, callback, max_strikes)
            if action is not None:
                chosen_view = reaction
            else:
                chosen_view = PlayerView(state, owner, max_chars=max_chars)
                action, more = _call_for_selection(chosen_view, callback, max_strikes)
                rejected += more
        else:
            chosen_view = PlayerView(state, owner, max_chars=max_chars)
            action, rejected = _call_for_selection(chosen_view, callback, max_strikes)
    else:
        chosen_view = PlayerView(state, owner, max_chars=max_chars)
        action, rejected = _call_for_selection(chosen_view, callback, max_strikes)
    _require_live_elections(state, action)
    choose_combat = decision_callback or callback
    ordinal = 0
    def live_decision(payload):
        nonlocal ordinal
        ordinal += 1
        scope = combat_visibility(state)
        owner = payload['side']
        if owner in ('attacker', 'defender'):
            atk = scope.get('attacker') or state.get('meta', {}).get('approach_attacker_side') or action['side']
            owner = (atk if owner == 'attacker' else ('ghibelline' if atk == 'guelph' else 'guelph'))
        dv = DecisionView(state, payload, owner, chosen_view.version, ordinal)
        try:
            choice, _ = _call_for_selection(dv, choose_combat, max_strikes)
            return choice
        except Exception as exc:
            # BDC's optional-choice fallback must not silently decide for a
            # player because the model/provider was interrupted.
            raise ScriptedDecisionError('A complete player decision is required; combat must be retried.') from exc
    missing = object()
    original = state.get('battle_callback', missing)
    state['battle_callback'] = live_decision
    try:
        with strict_player_choices():
            result = dispatch(state, action)
    finally:
        if original is missing:
            state.pop('battle_callback', None)
        else:
            state['battle_callback'] = original
    return ActionResult(applied=result, rejected=rejected)


def selection_session(state: dict, side: str, selection: dict, *,
                      decisions: list[dict] | None = None,
                      decision_request: dict | None = None,
                      hidden_mats: bool | None = None) -> dict:
    """Stateless CLI/HTTP continuation for a selected combat action.

    Replay from the unchanged base save with the prefix of explicit decision
    selections. Stop at the next unanswered election and return its full owner-
    filtered view or requested page. Commit only when every election is answered.
    This is not an automatic default or a partial game-state commit. The trusted
    host must route each returned perspective to that player, not to the enemy.
    """
    if decisions is not None and (not isinstance(decisions, list)
                                 or not all(isinstance(d, dict) for d in decisions)):
        raise IllegalAction('BAD_DECISIONS', 'decisions must be an array of versioned selections.')
    prefix = copy.deepcopy(decisions or [])
    base = PlayerView(state, side, hidden_mats=hidden_mats)
    action = base.resolve(selection)
    _require_live_elections(state, action)
    before = copy.deepcopy(state)
    pending = {}
    used = 0
    def callback(payload):
        nonlocal used
        scope = combat_visibility(state)
        owner = payload['side']
        if owner in ('attacker', 'defender'):
            atk = scope.get('attacker') or state.get('meta', {}).get('approach_attacker_side') or side
            owner = atk if owner == 'attacker' else ('ghibelline' if atk == 'guelph' else 'guelph')
        view = DecisionView(state, payload, owner, base.version, used+1, base._catalog.hidden_mats)
        if used < len(prefix):
            choice = view.resolve(prefix[used])
            used += 1
            return choice
        pending.update(status='awaiting_decision', base_version=base.version,
                       decision_index=used, perspective=owner,
                       state_changed=False,
                       response=view.query(decision_request) if decision_request is not None else view.overview(),
                       resume={'base_version':base.version, 'decisions':prefix},
                       instructions='Keep the original save unchanged. Send this response only to its perspective. Retrieve any decision pages by resubmitting this prefix with decision_request. Append one complete choice ID/version and retry; no default choice is made.')
        raise ScriptedDecisionError('An explicit player election is pending.')
    election = callback
    def strict_callback(payload):
        try:
            return election(payload)
        except ScriptedDecisionError:
            raise
        except Exception as exc:
            raise ScriptedDecisionError('Invalid or stale player election; no default was chosen.') from exc
    missing=object()
    original=state.get('battle_callback',missing)
    state['battle_callback']=strict_callback
    try:
        with strict_player_choices():
            result=dispatch(state,action)
        if used != len(prefix):
            raise IllegalAction('EXTRA_DECISIONS','The action finished before the supplied decision prefix was exhausted.')
    except Exception:
        state.clear();state.update(before)
        if pending:
            return pending
        raise
    finally:
        if original is missing:
            state.pop('battle_callback',None)
        else:
            state['battle_callback']=original
    from .filter import hide_for_side
    public=hide_for_side(state,side,hidden_mats=base._catalog.hidden_mats)
    return {'status':'accepted','state_changed':True,'decisions_applied':used,
            'perspective':side, 'latest_action':public.get('history',[])[-1:]}
