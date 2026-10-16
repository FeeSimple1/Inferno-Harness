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
from examples.play_with_claude import SYSTEM_PROMPT, STRATEGY_PROMPT

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
            # An empty notebook transmits no state record, but its separate
            # conditional system instructions still cost input tokens.
            none=compact(view.overview())
            memory.stage(side,EXAMPLE_NOTE,view.version)
            memory.commit(state)
            with_note=compact({**view.overview(),'prior_strategy':memory.read(side)})
            def measure(user_payload, system_prompt):
                d={'characters':len(user_payload)+len(system_prompt),
                   'bytes':len(user_payload.encode('utf-8'))+len(system_prompt.encode('utf-8'))}
                if enc:
                    # The provider receives distinct system and user fields;
                    # count tokenized payloads separately, not as concatenation.
                    d['cl100k_tokens']=len(enc.encode(user_payload))+len(enc.encode(system_prompt))
                return d
            control_system=SYSTEM_PROMPT.format(side=side)
            memory_system=control_system + STRATEGY_PROMPT
            count=measure(base,control_system)
            absent=measure(none,memory_system)
            present=measure(with_note,memory_system)
            rows.append({'scenario':scenario,'seed':seed,'side':side,
                         'without_notebook':count,'empty_notebook':absent,
                         'example_note':present,
                         'added_tokens_if_tokenizer_available':(present['cl100k_tokens']-count['cl100k_tokens']) if enc else None,
                         'added_chars':present['characters']-count['characters'],
                         'empty_notebook_extra_chars':absent['characters']-count['characters'],
                         'strategy_system_instruction_chars':len(STRATEGY_PROMPT),
                         'note_chars':len(EXAMPLE_NOTE)})
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps({'tokenizer':'cl100k_base' if enc else None,
                         'warning':'Per-request system+initial-user tokenization, counted separately. Provider usage and note output can differ; no strategic-strength claim.',
                         'rows':rows},indent=2))
    for row in rows:
        print(f"{row['scenario']} {row['side']}: +{row['added_chars']} chars; "
              f"token overhead {row['added_tokens_if_tokenizer_available']}")
    print(f'Measured output: {args.out}')
    return 0

if __name__=='__main__':
    raise SystemExit(main())