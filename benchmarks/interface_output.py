"""Measure wire output, not an imaginary token saving from omitted choices.

Runs real deterministic play sequences. Every selected action is applied to
independent direct-dispatch and versioned-interface states and compared. The
lookup policy pages ALL entries in the selected category, requests relevant
full Lord/board records, and loads action/card reference on first use per side.
A separate full-menu pagination measurement reports the cost of reading every
menu entry. No choice disappears from the player-facing catalog.

Optional tiktoken cl100k_base counts are reported when installed and available;
otherwise token columns are explicitly absent. This is not a live-LLM quality
study or a prediction of any provider's bill. Character and UTF-8 counts are exact.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import platform
from importlib.metadata import version as package_version
import importlib.util
import json
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from inferno.actions import dispatch, IllegalAction
from inferno.scenarios import load_scenario
from inferno.legal_moves import enumerate_legal
from inferno.invariants import check_all_invariants
from inferno.llm import PlayerView, DecisionView, play_with_interface
from inferno.llm.protocol import compact
from selfplay_bughunt import choose

spec=importlib.util.spec_from_file_location('inferno.llm._benchmark_legacy',ROOT/'benchmarks/legacy_briefing.py')
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)


def sizes(text,enc):
    return {'chars':len(text),'utf8_bytes':len(text.encode()),
            **({'tokens':len(enc.encode(text,disallowed_special=()))} if enc else {})}


def payload_sizes(payloads,enc):
    """Sum separate emitted payloads; do not invent cross-message token merges."""
    units=('chars','utf8_bytes')+(('tokens',) if enc else ())
    total={unit:0 for unit in units}
    for text in payloads:
        for key,n in sizes(text,enc).items():total[key]+=n
    return total


def page_all(view,request,outputs,inputs):
    records=[]
    while True:
        inputs.append(compact(request))
        answer=view.query(request);outputs.append(compact(answer))
        records+=answer['records']
        if not answer['next_cursor']:return records
        request={'request':request['request'],'cursor':answer['next_cursor'],'page_size':12,
                 **({'section':request['section']} if request['request']=='inspect' else {})}


def referenced(value,known):
    if isinstance(value,str):return {value} if value in known else set()
    if isinstance(value,dict):return set().union(*(referenced(v,known) for v in value.values()),set())
    if isinstance(value,list):return set().union(*(referenced(v,known) for v in value),set())
    return set()


def run(scenario,seed,max_steps,enc,policy_name='smoke'):
    state=load_scenario(scenario,seed=seed,hidden_mats=False)
    rng=random.Random(seed)
    endurance = None
    if policy_name == 'endurance':
        from benchmarks.endurance_policy import EndurancePolicy
        endurance = EndurancePolicy()
    rows=[];seen_refs={side:set() for side in ('guelph','ghibelline')}
    seen_cards={side:set() for side in seen_refs}
    for step in range(max_steps):
        if state['meta'].get('phase')=='victory':break
        moves=enumerate_legal(state)
        if not moves:raise AssertionError('Empty menu in nonterminal state')
        selected=endurance.choose(state,moves) if endurance else choose(state,moves,rng)
        action={k:deepcopy(selected[k]) for k in ('action','side','args') if k in selected}
        native,model=deepcopy(state),deepcopy(state)
        native_decisions=[]
        def raw_callback(payload):
            native_decisions.append(deepcopy(payload))
            return payload['options'][0]
        native['battle_callback']=raw_callback
        expected=dispatch(native,action)
        native.pop('battle_callback')
        new_outputs=[];queries=[];selections=[];views=[];full_menu_pages=[]
        same_fact_outputs=[];compact_full_outputs=[];legacy_outputs=[];detail_outputs=[];decision_count=0;coverage_count=0
        def callback(view):
            nonlocal decision_count,coverage_count
            overview=view.overview();views.append(overview)
            new_outputs.append(compact(overview))
            if isinstance(view,PlayerView):
                full=[e['move'] for e in view._catalog.entries]
                # Two baselines: actual old documented prompt, and the same
                # new essential facts plus an unsolicited full legacy menu.
                old=legacy.build_briefing(state,view.side,max_chars=3500)
                legacy_outputs.append(old+'\n\nLegal moves (choose exactly one, return its JSON):\n'+json.dumps(full,indent=2,ensure_ascii=False))
                same_fact_outputs.append(compact({k:v for k,v in overview.items() if k!='single_action'})+'\n'+json.dumps(full,indent=2,ensure_ascii=False))
                compact_full_outputs.append(compact({k:v for k,v in overview.items() if k!='single_action'})+'\n'+compact(full))
                # Cost of exhaustive paginated reads, independently measured.
                exhaustive=page_all(view,{'request':'actions','page_size':12},full_menu_pages,[])
                original=[m for m in moves if m.get('side')==view.side or m.get('action','').startswith('<')]
                assert Counter(compact(e['move']) for e in exhaustive)==Counter(map(compact,original))
                coverage_count+=len(exhaustive)
                if view.can_yield and view.side!=action['side']:
                    answer={'yield':True,'state_version':view.version};selections.append(compact(answer));return answer
                assert view.side==action['side']
                entries=([overview['single_action']] if overview.get('single_action', {}).get('move')==selected
                         else page_all(view,{'request':'actions','category':action['action'],'page_size':12},new_outputs,queries))
                detail_start=len(new_outputs)
                matching=[e for e in entries if e['move']==selected]
                assert len(matching)==1,(selected,entries)
                # Explicit extra reads. Their cost is included, not waved away.
                lord_keys=referenced([e['move'].get('args',{}) for e in entries],set(state['lords']))
                active=state.get('current_lord_id')
                if active:lord_keys.add(active)
                if lord_keys:page_all(view,{'request':'inspect','section':'lords','keys':sorted(lord_keys),'page_size':12},new_outputs,queries)
                board_keys=referenced([e['move'].get('args',{}) for e in entries],set(state['locales']))
                board_keys|={state['lords'][lid]['location'] for lid in lord_keys if state['lords'][lid].get('location')}
                if board_keys:page_all(view,{'request':'inspect','section':'board','keys':sorted(board_keys),'page_size':12},new_outputs,queries)
                if action['action'] not in seen_refs[view.side]:
                    page_all(view,{'request':'inspect','section':'action_reference','keys':[action['action']],'page_size':12},new_outputs,queries)
                    seen_refs[view.side].add(action['action'])
                cards=set(state['decks'][view.side].get('aow_held',[]))
                cards.update(c for l in state['lords'].values() if l['side']==view.side for c in l.get('capabilities',[]))
                cards.update(c['id'] for c in state.get('capabilities_in_play',[]) if c.get('side')==view.side)
                new=cards-seen_cards[view.side]
                if new:page_all(view,{'request':'inspect','section':'card_reference','keys':sorted(new),'page_size':12},new_outputs,queries)
                seen_cards[view.side]|=new
                detail_outputs.extend(new_outputs[detail_start:])
                answer={'action_id':matching[0]['action_id'],'state_version':view.version}
            else:
                entries=page_all(view,{'request':'actions','page_size':12},new_outputs,queries)
                payload=native_decisions[decision_count];decision_count+=1
                assert [e['move']['args']['choice'] for e in entries]==payload['options']
                answer={'action_id':entries[0]['action_id'],'state_version':view.version}
                # The old example had no live combat. For the corrected full-
                # information baseline charge the same tactical view/options.
                same_fact_outputs.append(compact(overview)+'\n'+compact(payload['options']))
                compact_full_outputs.append(compact(overview)+'\n'+compact(payload['options']))
            selections.append(compact(answer));return answer
        result=play_with_interface(model,callback,max_strikes=1)
        assert result.applied==expected and model==native
        assert decision_count==len(native_decisions)
        check_all_invariants(model)
        # Each full record can reconstruct its original engine entry. Correctness
        # is tested separately from how much the selection policy chose to read.
        row={'step':step+1,'turn':state['meta']['turn'],'phase':state['meta']['phase'],
             'step_name':state['meta'].get('levy_step') or state['meta'].get('campaign_step'),
             'side':action['side'],'action':action['action'],
             'menu_entries':len(moves),'covered_menu_entries':coverage_count,'lookups':len(queries),'tactical_decisions':decision_count,
             'legacy_documented':payload_sizes(legacy_outputs,enc),
             'same_essential_full_menu':payload_sizes(same_fact_outputs,enc),
             'equivalent_information_full_menu':payload_sizes(same_fact_outputs+detail_outputs,enc),
             'equivalent_information_compact_full_menu':payload_sizes(compact_full_outputs+detail_outputs,enc),
             'new_output_including_lookups':payload_sizes(new_outputs,enc),
             'new_requests_and_selections':payload_sizes(queries+selections,enc),
             'exhaustive_menu_pages_only':payload_sizes(full_menu_pages,enc)}
        # Re-sending every previous message inside one lookup loop can increase
        # provider input even when unique wire output shrinks. Give that count
        # explicitly; do not represent output savings as billing savings.
        # Unique emitted payloads are counted, not hypothetical cached billing.
        rows.append(row)
        if (step+1)%200==0:
            print(f'{scenario}:{seed} checked {step+1} actions, turn {state["meta"]["turn"]}',flush=True)
        state=model
    if state['meta'].get('phase')!='victory':
        raise AssertionError(f'{scenario} did not finish within {max_steps} steps')
    sums={metric:{unit:sum(r[metric].get(unit,0) for r in rows) for unit in ('chars','utf8_bytes')+(('tokens',) if enc else ())}
          for metric in ('legacy_documented','same_essential_full_menu','equivalent_information_full_menu','equivalent_information_compact_full_menu','new_output_including_lookups','new_requests_and_selections','exhaustive_menu_pages_only')}
    return {'scenario':scenario,'seed':seed,'policy':policy_name,'actions':len(rows),'final_turn':state['meta']['turn'],
            'winner':state['meta'].get('winner'),'vp':state['vp'],'lookups':sum(r['lookups'] for r in rows),
            'tactical_decisions':sum(r['tactical_decisions'] for r in rows),
            'covered_menu_entries':sum(r['covered_menu_entries'] for r in rows),
            'factions':{side:sum(r['side']==side for r in rows) for side in ('guelph','ghibelline')},
            'correctness':'All direct/interface results, final states and post-action invariants matched.',
            'totals':sums,'rows':rows}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cases',nargs='+',default=['A:11','C:11','F:20261012:endurance'])
    p.add_argument('--max-steps',type=int,default=3000)
    p.add_argument('--tokens',action='store_true',help='Require tiktoken cl100k_base; fail rather than estimate.')
    args=p.parse_args();enc=None
    if args.tokens:
        import tiktoken
        enc=tiktoken.get_encoding('cl100k_base')
    output={'method':'Deterministic real games; full chosen-category pages plus relevant full Lord/board records and first-use action/card references; all requests counted.',
            'tokenizer':'cl100k_base' if enc else None,
            'tokenizer_package':package_version('tiktoken') if enc else None,
            'python_version':platform.python_version(),
            'limitations':['Not a live LLM behavior or quality evaluation.',
              'The legacy prompt omitted information and within-combat choices; it is NOT a correctness-equivalent baseline.',
              'Equivalent-information controls include the same essential facts, all additional fact/reference reads, and every tactical choice. Formatted and compact full-menu controls are separate.',
              'The deterministic measurement policy caches static references after first use per faction. A fresh-context model may need additional repeated reads; this is not a live-provider measurement.',
              'Exhaustively paging the menu can cost more than one full-menu payload.',
              'Output savings are not provider billing savings; conversation resends, system prompts and caching differ.'],
            'runs':[]}
    for case in args.cases:
        parts=case.split(':');scenario,seed=parts[:2]
        r=run(scenario,int(seed),args.max_steps,enc,parts[2] if len(parts)>2 else 'smoke');output['runs'].append(r)
        print(case, r['actions'],r['totals'],flush=True)
        args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(output,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
