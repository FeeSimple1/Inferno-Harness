"""Measure the per-request prompt overhead of side-private strategy notes.

These are *not* provider billing numbers, model reasoning savings, or measures
of strategic skill. Note output and all subsequent resends must also be counted
by the actual provider meter when running a live paired experiment.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from inferno.llm import PlayerView, StrategicMemory
from inferno.llm.protocol import compact
from inferno.scenarios import load_scenario

EXAMPLE_NOTE = ('Objective: complete the existing siege before Service expires. '
                'Constraints: check Provender, Pay opportunity and available full-card activations. '
                'Contingency: if storm odds look poor, preserve troops and invest in siege markers. '
                'Opponent: watch for enemy reinforcements, Treachery and political reversals.')


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--out', type=Path, default=Path('benchmarks/results/STRATEGY_MEMORY_OVERHEAD.json'))
    args=p.parse_args(argv)
    try:
        import tiktoken
        enc=tiktoken.get_encoding('cl100k_base')
    except (ImportError, OSError):
        enc=None
    rows=[]
    for scenario,seed in [('A',42),('C',11),('F',20261012)]:
        state=load_scenario(scenario,seed=seed)
        for side in ('guelph','ghibelline'):
            view=PlayerView(state,side)
            base=compact(view.overview())
            memory=StrategicMemory()
            none=compact(view.overview()) # An empty notebook transmits no metadata.
            memory.stage(side,EXAMPLE_NOTE,view.version)
            memory.commit(state)
            with_note=compact({**view.overview(),'prior_strategy':memory.read(side)})
            def measure(s):
                d={'characters':len(s),'bytes':len(s.encode('utf-8'))}
                if enc:d['cl100k_tokens']=len(enc.encode(s))
                return d
            count=measure(base);absent=measure(none);present=measure(with_note)
            rows.append({'scenario':scenario,'seed':seed,'side':side,
                         'without_notebook':count,'empty_notebook':absent,
                         'example_note':present,
                         'added_tokens_if_tokenizer_available':(present['cl100k_tokens']-count['cl100k_tokens']) if enc else None,
                         'added_chars':len(with_note)-len(base),
                         'note_chars':len(EXAMPLE_NOTE)})
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps({'tokenizer':'cl100k_base' if enc else None,
                         'warning':'Only per-request input size. This does not show cost or strategic performance of a live model.',
                         'rows':rows},indent=2))
    for row in rows:
        print(f"{row['scenario']} {row['side']}: +{row['added_chars']} chars; "
              f"token overhead {row['added_tokens_if_tokenizer_available']}")
    print(f'Measured output: {args.out}')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
