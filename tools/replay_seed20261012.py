#!/usr/bin/env python3
"""Replay the corrected full Scenario F game, optionally through CLI-style saves."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from inferno.actions import dispatch
from inferno.scenarios import load_scenario
from inferno.invariants import check_all_invariants
from inferno.legal_moves import enumerate_legal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reload-every', type=int, default=0)
    args = parser.parse_args()
    if args.reload_every < 0:
        parser.error('--reload-every must be nonnegative')
    record = json.loads((ROOT / 'playtests/2026-10-10-seed20261012-corrected.json').read_text())
    state = load_scenario(record['scenario'], seed=record['seed'],
                          hidden_mats=record['hidden_mats'],
                          advanced_vassal_service=record['advanced_vassal_service'])
    rolls = 0
    for number, action in enumerate(record['actions'], 1):
        before = state['meta'].get('rng_advance', 0)
        result = dispatch(state, action)
        consumed = state['meta']['rng_advance'] - before
        assert len(result['rolls']) == consumed, (number, 'RNG journal')
        rolls += consumed
        check_all_invariants(state)
        if args.reload_every and number % args.reload_every == 0:
            loaded = json.loads(json.dumps(state, sort_keys=True))
            assert enumerate_legal(loaded) == enumerate_legal(state), (number, 'menu')
            state = loaded
    digest = hashlib.sha256(json.dumps(state, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    actual = {'actions': len(record['actions']), 'turn': state['meta']['turn'],
              'phase': state['meta']['phase'], 'winner': state['meta'].get('winner'),
              'final_vp': state['vp'], 'rng_calls': rolls, 'state_hash': digest}
    assert actual == record['expected'], {'expected': record['expected'], 'actual': actual}
    print(json.dumps({'result': 'passed', 'reload_every': args.reload_every, **actual}, sort_keys=True))


if __name__ == '__main__':
    main()
