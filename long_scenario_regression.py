#!/usr/bin/env python3
"""Replay the recorded 16-turn Scenario F choices under the current rules.

The two-process check compares every new action result/state hash byte-for-byte,
without normalizing away unordered lists. Stops immediately at Game End; the
old erroneous post-game Repair/Waste/Reset choices are intentionally not run.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'src'))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def run():
    from inferno.actions import dispatch
    from inferno.scenarios import load_scenario
    from inferno.invariants import check_all_invariants
    from inferno.legal_moves import enumerate_legal
    actions=json.loads((ROOT/'tests/fixtures/long_scenario/endurance.actions.json').read_text())
    state=load_scenario('F',seed=20261011,hidden_mats=False,advanced_vassal_service=False)
    states,results=[],[]
    for action in actions:
        if state['meta'].get('game_over'):
            break
        result=dispatch(state,action)
        check_all_invariants(state)
        states.append(fingerprint(state));results.append(fingerprint(result))
    assert len(states)==1684, (len(states),state['meta'])
    assert state['meta']['turn']==16 and state['meta']['game_over']
    assert actions[len(states)-1]['action']=='end_game_check'
    assert not enumerate_legal(state)
    assert state['meta']['winner']=='ghibelline'
    return {'actions':len(states),'turn':16,'winner':state['meta']['winner'],
            'vp':state['vp'],'terminal_action':'end_game_check',
            'post_game_actions_not_run':len(actions)-len(states),
            'state_hashes':states,'result_hashes':results,'final_hash':fingerprint(state)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.child:
        print(json.dumps(run()));return
    runs=[]
    for seed in ('0','1'):
        result=subprocess.run([sys.executable,'-S',str(Path(__file__).resolve()),'--child'],
            env={**os.environ,'PYTHONHASHSEED':seed},text=True,capture_output=True,timeout=300,check=True)
        runs.append(json.loads(result.stdout))
    assert runs[0]==runs[1], 'Same-code results/state fingerprints differ across process hash seeds'
    summary={k:v for k,v in runs[0].items() if k not in ('state_hashes','result_hashes')}
    summary.update(python_hash_seeds=[0,1],every_action_result_identical=True,every_state_hash_identical=True,
                   all_post_action_invariants_passed=True)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
