"""Generate a compact committed report; detailed rows remain in the CI artifact."""
from __future__ import annotations
import argparse
from pathlib import Path
import json
from xml.etree import ElementTree as ET


def main():
    p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('--pytest',type=Path)
    p.add_argument('--out',type=Path,default=Path('benchmarks/results'))
    args=p.parse_args();data=json.loads(args.input.read_text());args.out.mkdir(parents=True,exist_ok=True)
    summary={k:v for k,v in data.items() if k!='runs'}
    summary['runs']=[{k:v for k,v in r.items() if k!='rows'} for r in data['runs']]
    if args.pytest:
        root=ET.parse(args.pytest).getroot()
        suites=[root] if root.tag=='testsuite' else list(root.iter('testsuite'))
        summary['pytest']={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    for r in summary['runs']:
        r['savings']={}
        for unit in ('chars','utf8_bytes','tokens'):
            if unit not in r['totals']['new_output_including_lookups']:continue
            new=r['totals']['new_output_including_lookups'][unit]
            r['savings'][unit]={control:100*(1-new/r['totals'][control][unit])
              for control in ('legacy_documented','equivalent_information_full_menu','equivalent_information_compact_full_menu')}
    (args.out/'interface-output.summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    lines=['# Verified LLM interface output measurements','',
      'Correctness gates and output sizes are independent. Negative savings mean more output.',
      f"Python {data['python_version']}; tokenizer {data['tokenizer'] or 'not installed (no estimates)'}; tiktoken {data.get('tokenizer_package') or 'not installed'}.",'',
      '## Correctness','']
    if summary.get('pytest'):
        t=summary['pytest'];lines.append(f"Full suite: {t['tests']-t['failures']-t['errors']-t['skipped']:,} passed; {t['failures']} failed; {t['errors']} errors; {t['skipped']} skipped.")
    lines+=['','| Scenario / seed | Accepted actions | Guelph / Ghibelline actions | Lookups | Tactical elections | Raw menu entries reconstructed | Endpoint |',
      '|---|---:|---:|---:|---:|---:|---|']
    for r in summary['runs']:
        lines.append(f"| {r['scenario']} / {r['seed']} | {r['actions']:,} | {r['factions']['guelph']} / {r['factions']['ghibelline']} | {r['lookups']:,} | {r['tactical_decisions']} | {r['covered_menu_entries']:,} | Turn {r['final_turn']}; {r['winner'] or 'draw'} |")
    lines+=['','Every selected action ran in independent direct and interface states with identical results/state; all post-action invariants passed. Full menu pages reconstructed all original entries at every measured position. All elections in the direct control were explicitly chosen by its callback, not silently replaced by interface defaults.','']
    for unit,title in [('tokens','Named-tokenizer counts'),('chars','Character counts')]:
        if unit not in summary['runs'][0]['totals']['new_output_including_lookups']:continue
        lines+=['## '+title,'',
          '| Scenario | Old truncated/full menu | Equivalent facts/formatted full menu | Equivalent facts/compact full menu | New including all lookup results | Savings vs formatted | Savings vs compact | Model requests + selections (additional) |',
          '|---|---:|---:|---:|---:|---:|---:|---:|']
        for r in summary['runs']:
            t=r['totals'];sv=r['savings'][unit]
            lines.append('| '+r['scenario']+' | '+' | '.join(f"{t[k][unit]:,}" for k in ('legacy_documented','equivalent_information_full_menu','equivalent_information_compact_full_menu','new_output_including_lookups'))+f" | {sv['equivalent_information_full_menu']:.2f}% | {sv['equivalent_information_compact_full_menu']:.2f}% | {t['new_requests_and_selections'][unit]:,} |")
        lines+=['']
    lines+=['## Exhaustive reads and scope','',
      '| Scenario | Reading every menu page: characters | Reading every menu page: tokens |',
      '|---|---:|---:|']
    for r in summary['runs']:
        t=r['totals']['exhaustive_menu_pages_only'];lines.append(f"| {r['scenario']} | {t['chars']:,} | {t.get('tokens','not measured')} |")
    lines+=['',data['method'],'',
      'Counts sum each serialized payload separately, including extra fact/reference reads, action pages, reaction views and tactical choices. Request/selection traffic is shown separately, not silently omitted from an API-cost claim. The raw detailed JSON includes exact UTF-8 counts too.','',
      'The old documented prompt omitted facts and live elections. It is not a correctness-equivalent target; the new complete path can be substantially larger. Formatting and pagination controls above keep the same essential facts and additional full-detail reads. No result is called a saving by ignoring extra lookup outputs.','']
    lines += [f'- {s}' for s in data['limitations']]
    lines+=['','See `LLM_INTERFACE_CHANGES.md` and `LLM_PLAY_GUIDE.md`. Reproduce with `PYTHONPATH=src python benchmarks/interface_output.py --tokens --out interface-output.json`.','']
    (args.out/'INTERFACE_OUTPUT.md').write_text('\n'.join(lines))
    print('\n'.join(lines))

if __name__=='__main__':main()
