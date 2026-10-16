"""Paired *live-model* strategy evaluation, with no rule-engine shortcuts.

Run the SAME model in two Scenario games per seed, swapping which faction
receives side-private strategic continuity. The opponent uses the same model
without memory. Outcomes, action integrity and provider usage are recorded
separately. This is an experiment runner, NOT proof of strategic superiority;
model stochasticity, scenario side imbalance and sample size all matter.

  PYTHONPATH=src python benchmarks/strategy_ab.py --scenario A --seeds 42 43 --model MODEL_ID
  PYTHONPATH=src python benchmarks/strategy_ab.py --scenario A --seeds 42 --stub

Live play incurs provider costs. --stub verifies routing mechanically but does
NOT measure strategic intelligence or notebook effectiveness.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
from examples.play_with_claude import make_claude_callback, make_stub_callback
from inferno.invariants import check_all_invariants
from inferno.llm import StrategicMemory, play_with_interface
from inferno.scenarios import load_scenario


def trial(scenario: str, seed: int, notes_side: str, max_actions: int, *,
          stub: bool, model: str | None, hidden_mats: bool = False) -> dict:
    if notes_side not in ('guelph', 'ghibelline'):
        raise ValueError('notes_side must be one faction')
    state = load_scenario(scenario, seed=seed, hidden_mats=hidden_mats)
    notes = StrategicMemory()
    meter = {'guelph': [], 'ghibelline': []}
    if stub:
        callbacks = {'guelph': make_stub_callback(), 'ghibelline': make_stub_callback()}
    else:
        if not model:
            raise ValueError('A provider model is required for non-stub experiments')
        callbacks = {side: make_claude_callback(model, meter=meter[side],
                     strategic_memory=notes if side == notes_side else None)
                     for side in ('guelph','ghibelline')}
    counts = Counter()
    status = 'incomplete'
    error = None
    for _ in range(max_actions):
        if state['meta'].get('phase') == 'victory':
            status = 'completed'
            break
        notes.abort()
        try:
            result = play_with_interface(state, lambda v: callbacks[v.side](v))
            check_all_invariants(state)
            notes.commit(state)
            # The engine, not the evaluator, supplies the winning side.
            counts[state['history'][-1]['side']] += 1
        except Exception as exc:
            notes.abort()
            status = 'paused'
            error = f'{type(exc).__name__}: {exc}'
            break
    if state['meta'].get('phase') == 'victory':
        status = 'completed'
    def usage(rows):
        totals = Counter()
        for row in rows:
            u = row.get('usage') or {}
            # Provider token counts can be absent for mocks or SDK variants.
            for field in ('input_tokens', 'output_tokens', 'cache_creation_input_tokens',
                          'cache_read_input_tokens'):
                if isinstance(u.get(field), int):
                    totals[field] += u[field]
            totals['request_count'] += 1
            totals['input_chars'] += row.get('input_chars', 0)
            totals['output_chars'] += row.get('output_chars', 0)
        return dict(totals)
    return {'scenario':scenario, 'seed':seed, 'notebook_side':notes_side,
            'status':status, 'error':error,
            'winner':state['meta'].get('winner') if status == 'completed' else None,
            'vp':state.get('vp'), 'turn':state['meta'].get('turn'),
            'accepted_actions':sum(counts.values()), 'actions_by_side':dict(counts),
            'notebook_chars':len(notes.read(notes_side)['note'] or ''),
            'provider_usage_by_side':{s:usage(meter[s]) for s in meter},
            'interpretation':'stub mechanics only; not a strategic test' if stub else 'live model; compare across paired seeds and side swaps'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario',default='A',choices='ABCDEF')
    parser.add_argument('--seeds',type=int,nargs='+',default=[42,43])
    parser.add_argument('--max-actions',type=int,default=8000)
    parser.add_argument('--model')
    parser.add_argument('--stub',action='store_true')
    parser.add_argument('--hidden-mats',action='store_true')
    parser.add_argument('--out',type=Path,default=Path('strategy_ab_results.json'))
    args=parser.parse_args(argv)
    if not args.stub and not args.model:
        parser.error('Live strategic A/B comparison requires --model and provider credentials; or --stub for plumbing only.')
    results=[]
    for seed in args.seeds:
        for notes_side in ('guelph','ghibelline'):
            result=trial(args.scenario,seed,notes_side,args.max_actions,
                         stub=args.stub,model=args.model,hidden_mats=args.hidden_mats)
            results.append(result)
            print(f"{seed} {notes_side}: {result['status']} actions={result['accepted_actions']} winner={result['winner']}")
    completed=[r for r in results if r['status']=='completed']
    summary={'games_completed':len(completed), 'total_games':len(results),
             'notebook_wins':sum(r['winner']==r['notebook_side'] for r in completed),
             'control_wins':sum(r['winner'] in ('guelph','ghibelline') and r['winner']!=r['notebook_side'] for r in completed),
             'ties_or_no_winner':sum(r['winner'] not in ('guelph','ghibelline') for r in completed),
             'evaluation_warning':'No causal strength claim from one game or one seed. Compare repeated crossover pairs with equal models and settings; inspect choices and strategy, not wins alone. Stub mode is not an LLM evaluation.'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps({'parameters':vars(args)|{'out':str(args.out)},
                                    'summary':summary,'games':results},indent=2,default=str))
    print(f'Results: {args.out}')
    return 0 if all(r['status']=='completed' for r in results) else 1


if __name__=='__main__':
    raise SystemExit(main())
