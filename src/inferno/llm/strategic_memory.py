"""Optional, player-authored strategic continuity for *separate* model calls.

Plans are hypotheses, NEVER rules, engine state, or legal-action filters.
Notes stay in the trusted host, scoped by faction, and are committed only after
an entire authoritative action (including tactical elections) succeeds. A
journal file can be loaded only beside the *exact* state with which it was
saved. There is no token budget or strategic truncation applied to the note.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy

from .protocol import compact

SIDES = ('guelph', 'ghibelline')


def _state_digest(state: dict) -> str:
    """Trusted host-only save pairing, not a player-facing version or ID."""
    return hashlib.sha256(compact(state).encode('utf-8')).hexdigest()


class StrategicMemory:
    """A two-faction strategic notebook, outside the game/dispatch state.

    `stage` is called only after a selection has passed PlayerView.resolve.
    `commit` is called only after dispatch succeeds. `abort` discards all
    provisional notes if an action, a combat decision, or a provider fails.
    """

    def __init__(self):
        self._notes = {side: None for side in SIDES}
        self._pending: dict[str, tuple[str, str]] = {}

    @staticmethod
    def _side(side: str) -> None:
        if side not in SIDES:
            raise ValueError('A journal is restricted to a real faction.')

    def read(self, side: str) -> dict:
        self._side(side)
        entry = self._notes[side]
        return {
            'source': 'The same faction\'s previous model-authored plan; not verified rules or current facts.',
            'side': side,
            'note': entry['note'] if entry else None,
            'written_after_revision': entry['revision'] if entry else None,
            'warning': 'Reassess this plan against the CURRENT briefing, events, Service, and legal choices. Replace or clear it when obsolete.',
        }

    def stage(self, side: str, note: str, source_version: str) -> None:
        self._side(side)
        if not isinstance(note, str):
            raise ValueError('strategy_note must be a string (empty to clear).')
        if not isinstance(source_version, str) or not source_version:
            raise ValueError('Notes must originate from a validated, versioned player decision.')
        # Empty clears the old plan; otherwise preserve the model's complete
        # note without an arbitrary character/token limit or raw slicing.
        self._pending[side] = (note, source_version)

    def abort(self) -> None:
        self._pending.clear()

    def commit(self, state: dict) -> None:
        """Commit notes only AFTER a successful, complete game action."""
        revision = len(state.get('history', []))
        for side, (note, source_version) in self._pending.items():
            self._notes[side] = ({'note': note, 'revision': revision,
                                  'source_version': source_version}
                                 if note else None)
        self.abort()

    def save(self, state: dict) -> dict:
        if self._pending:
            raise ValueError('Cannot save journal with uncommitted decisions.')
        return {'format': 1, 'state_digest': _state_digest(state),
                'notes': deepcopy(self._notes)}

    @classmethod
    def load(cls, saved: dict, state: dict) -> 'StrategicMemory':
        """Reject foreign/stale journals: never pair with a different save."""
        if not isinstance(saved, dict) or saved.get('format') != 1:
            raise ValueError('Unsupported or malformed strategic notebook.')
        if saved.get('state_digest') != _state_digest(state):
            raise ValueError('Strategic notebook does not match this exact saved position.')
        notes = saved.get('notes')
        if not isinstance(notes, dict) or set(notes) != set(SIDES):
            raise ValueError('Strategic notebook must contain exactly two separate factions.')
        rev = len(state.get('history', []))
        for side in SIDES:
            item = notes[side]
            if item is None:
                continue
            if (not isinstance(item, dict) or set(item) != {'note', 'revision', 'source_version'}
                    or not isinstance(item['note'], str)
                    or type(item['revision']) is not int or item['revision'] > rev
                    or item['revision'] < 0 or not isinstance(item['source_version'], str)):
                raise ValueError('Malformed or future strategic notebook entry.')
        journal = cls()
        journal._notes = deepcopy(notes)
        return journal
