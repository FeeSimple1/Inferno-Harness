"""The player boundary must conserve information and choice, not just bytes."""
from copy import deepcopy
import json
from collections import Counter
from pathlib import Path

import pytest

from inferno.actions import dispatch, IllegalAction
from inferno.scenarios import load_scenario
from inferno.legal_moves import enumerate_legal
from inferno.llm.briefing import (build_briefing, build_briefing_document, information_sections,
                                 render_briefing)
from inferno.llm.interface import PlayerView, DecisionView, play_with_interface
from inferno.llm.menu import ActionCatalog, submit_selection
from inferno.llm.protocol import compact, state_version

SIDES = ('guelph', 'ghibelline')


def all_pages(view, request, page_size=3, max_chars=None):
    query = dict(request, page_size=page_size)
    if max_chars is not None:
        query['max_chars'] = max_chars
    records, offsets = [], []
    while True:
        page = view.query(query)
        assert page['offset'] == len(records)
        offsets.append(page['offset'])
        records += page['records']
        assert page['returned'] == len(page['records'])
        assert page['total'] >= len(records)
        if page['next_cursor'] is None:
            assert page['complete'] and page['total'] == len(records)
            break
        assert not page['complete'] and page['records']
        query = {'request': request['request'], 'cursor': page['next_cursor'],
                 'page_size': page_size}
        if request['request'] == 'inspect':
            query['section'] = request['section']
        if max_chars is not None:
            query['max_chars'] = max_chars
    assert len(set(offsets)) == len(offsets)
    return records


def selection(view, entry, **extra):
    return dict(action_id=entry['action_id'], state_version=view.version, **extra)


@pytest.mark.parametrize('side', SIDES)
def test_budget_is_soft_and_long_pending_and_changes_are_never_cut(side):
    s = load_scenario('F', seed=99)
    sentence = 'This is a required player decision, not expendable prose. ' * 250
    s['pending'] = [{'type': 'long_example', 'side': side, 'instruction': sentence,
                     'required_parameters': {'target': 'ENDING_PARAMETER_SENTINEL'}}]
    s['history'] = [{'side': side, 'action': 'diagnostic', 'args': {},
                     'state_changes': {'important': sentence + 'COMPLETE_CHANGE_END'}}]
    before = deepcopy(s)
    doc = build_briefing_document(s, side, max_chars=80)
    text = render_briefing(doc)
    assert len(text) > 80 and doc['soft_target_exceeded']
    assert sentence in text
    assert 'ENDING_PARAMETER_SENTINEL' in text and 'COMPLETE_CHANGE_END' in text
    assert 'Acting player:' in text and 'Phase levy/3.1' in text
    assert 'Available kinds of action' in text
    assert 'returned intact' in text
    assert {'pending', 'changes', 'actions', 'held', 'lords'} <= {a['id'] for a in doc['sections']}
    assert s == before


@pytest.mark.parametrize('side,prefix,enemy', [('guelph','F','ghibelline'), ('ghibelline','S','guelph')])
@pytest.mark.parametrize('hidden', [False, True])
def test_all_own_held_capabilities_resources_service_and_future_fields_retrievable(side,prefix,enemy,hidden):
    s = load_scenario('F', seed=37)
    s['meta']['hidden_mats'] = hidden
    s['decks'][side]['aow_held'] = [prefix + str(i) for i in range(1,27)]
    s['decks'][enemy]['aow_held'] = ['SECRET_EVENT_SENTINEL']
    lid = next(k for k,l in s['lords'].items() if l['side']==side and l['status']=='mustered')
    s['lords'][lid]['capabilities'] = [prefix+'6',prefix+'9']
    s['lords'][lid]['assets']['Coin'] = 123
    s['lords'][lid]['service_box'] = 16
    s['lords'][lid]['future_visible_property'] = 'new field must not disappear'
    s['new_game_property'] = {'value':'future root data'}
    before = deepcopy(s)
    v = PlayerView(s,side,max_chars=20)
    txt = compact(v.overview())
    for cid in s['decks'][side]['aow_held']:
        assert cid in txt
    assert 'SECRET_EVENT_SENTINEL' not in txt
    assert 'Service 16' in txt and '123' in txt
    records = all_pages(v, {'request':'inspect','section':'lords'},1,20)
    own = next(r['value'] for r in records if r['key']==lid)
    assert own == s['lords'][lid]
    snapshot = v.query({'request':'inspect','section':'snapshot','max_chars':10})
    assert snapshot['returned']==1 and snapshot['soft_target_exceeded']
    assert snapshot['records'][0]['value']['new_game_property']==s['new_game_property']
    assert 'SECRET_EVENT_SENTINEL' not in compact(snapshot)
    refs = all_pages(v, {'request':'inspect','section':'card_reference'},1,20)
    assert len(refs)==52
    assert all(r['value']['printed_reference']['event'] and r['value']['printed_reference']['capability'] for r in refs)
    assert s==before


@pytest.mark.parametrize('scenario',list('ABCDEF'))
@pytest.mark.parametrize('side',SIDES)
def test_menu_pages_preserve_every_original_entry_and_id(scenario,side):
    s=load_scenario(scenario,seed=17)
    s['meta'].update(phase='levy', levy_step='3.4', active_player=side)
    before=deepcopy(s)
    v=PlayerView(s,side)
    originals=[m for m in enumerate_legal(s) if m.get('side')==side or m['action'].startswith('<')]
    entries=all_pages(v,{'request':'actions'},page_size=2,max_chars=100)
    assert Counter(compact(e['move']) for e in entries)==Counter(map(compact,originals))
    assert len({e['action_id'] for e in entries})==len(entries)
    overview=v._catalog.overview()
    assert sum(c['count'] for c in overview['categories'])==len(entries)
    collected=[]
    for c in overview['categories']:
        pages=all_pages(v,{'request':'actions','category':c['category']},1)
        assert len(pages)==c['count']
        collected.extend(pages)
    assert Counter(e['action_id'] for e in collected)==Counter(e['action_id'] for e in entries)
    # Save/reload does not change query identity or results.
    reloaded=json.loads(json.dumps(s,sort_keys=True))
    assert PlayerView(reloaded,side)._catalog.entries==entries
    assert s==before


@pytest.mark.parametrize('side',SIDES)
def test_stale_id_cursor_and_live_view_rejected_atomically(side):
    s=load_scenario('F',seed=2)
    s['meta'].update(phase='levy', levy_step='3.4', active_player=side)
    v=PlayerView(s,side)
    page=v.query({'request':'actions','page_size':1})
    assert page['next_cursor']
    chosen=selection(v,page['records'][0])
    # A passed procedure is a new revision even if the board did not move.
    dispatch(s,{'action':'levy_muster_done','side':side})
    before=deepcopy(s)
    for action in (lambda:submit_selection(s,side,chosen),
                   lambda:v.query({'request':'actions'}),
                   lambda:PlayerView(s,side).query({'request':'actions','cursor':page['next_cursor']})):
        with pytest.raises(IllegalAction,match='STALE_VIEW'):
            action()
        assert s==before


@pytest.mark.parametrize('scenario', list('ABCDEF'))
def test_mechanical_results_equal_for_concrete_catalog_choices(scenario):
    s=load_scenario(scenario,seed=19)
    # Fixed deterministic path, not a presentation restriction. At every state
    # compare all offered concrete actions on independent copies.
    for step in range(24):
        v=PlayerView(s)
        entries=all_pages(v,{'request':'actions'},5)
        valid=[]
        for entry in entries:
            if entry['parameterized'] or entry['move']['action'].startswith('<'):
                continue
            direct={k:deepcopy(entry['move'][k]) for k in ('action','side','args') if k in entry['move']}
            a,b=deepcopy(s),deepcopy(s)
            try:
                result=dispatch(a,direct)
            except IllegalAction as e:
                with pytest.raises(IllegalAction) as other:
                    submit_selection(b,v.side,selection(v,entry))
                assert other.value.code==e.code and b==s
            else:
                via=submit_selection(b,v.side,selection(v,entry))
                assert via==result and b==a
                valid.append(entry)
        if not valid or s['meta'].get('game_over'):
            break
        # Exercise nontrivial moves while retaining identical mechanics.
        selected=valid[step%len(valid)]
        submit_selection(s,v.side,selection(v,selected))


@pytest.mark.parametrize('side',SIDES)
def test_enumeration_and_focused_queries_do_not_roll_dice(side,monkeypatch):
    from inferno.rng import HarnessRNG
    def forbidden(*a,**k): raise AssertionError('read operation rolled dice')
    monkeypatch.setattr(HarnessRNG,'roll',forbidden)
    s=load_scenario('F',seed=1)
    v=PlayerView(s,side)
    v.overview()
    all_pages(v,{'request':'actions'},1)
    for section in information_sections(v._catalog.view):
        all_pages(v,{'request':'inspect','section':section},3)


def test_optional_handler_arguments_remain_selectable_and_documented():
    s=load_scenario('F',seed=1)
    s['meta'].update(phase='campaign',campaign_step='end_campaign',active_player='guelph', end_substep_done=['grow','ransom','game_check','repair'])
    v=PlayerView(s,'guelph')
    ref=v.query({'request':'inspect','section':'action_reference','keys':['end_waste']})
    assert 'discards' in ref['records'][0]['value']['argument_fields']
    # Resolve does not restrict args to the enumerator's default placeholders.
    cat=ActionCatalog(s,'guelph')
    if not cat.entries:
        pytest.fail('Waste category unexpectedly absent')
    e=next(e for e in cat.entries if e['move']['action']=='end_waste')
    args={'discards':{'firenze':{'asset':'Cart'}}}
    assert cat.resolve(selection(v,e,args=args))['args']==args


@pytest.mark.parametrize('hidden',[False,True])
def test_opponent_secrets_do_not_change_visible_ids_or_payloads(hidden):
    s=load_scenario('F',seed=3)
    s['meta']['hidden_mats']=hidden
    t=deepcopy(s)
    t['decks']['ghibelline']['aow_held']=['S19' for _ in t['decks']['ghibelline']['aow_held']]
    t['decks']['ghibelline']['aow_deck'].reverse()
    t['plan_stacks']['ghibelline']=['command_pisa']*len(s['plan_stacks']['ghibelline'])
    t['meta']['rng_seed']=999999
    if hidden:
        l=t['lords']['siena']
        l['assets']={'Coin':999,'Cart':123}
        total=sum(l['forces'].values());l['forces']={'Villici':total}
        l['capabilities']=['S17']*len(l['capabilities'])
        for va in l['vassals']:va['on_mat']=not va.get('on_mat')
    a,b=PlayerView(s,'guelph'),PlayerView(t,'guelph')
    assert a.overview()==b.overview()
    assert a.query({'request':'actions'})==b.query({'request':'actions'})
    assert a.query({'request':'inspect','section':'snapshot'})==b.query({'request':'inspect','section':'snapshot'})


@pytest.mark.parametrize('query_request',[{'request':'actions','page_size':0},
 {'request':'actions','page_size':True},{'request':'actions','category':[]},
 {'request':'actions','cursor':'bad@@'},{'request':'inspect','section':[]},
 {'request':'inspect','section':'lords','keys':'siena'}, {'request':'oops'}])
def test_malformed_queries_are_clean_rejections(query_request):
    s=load_scenario('A',seed=1);before=deepcopy(s)
    with pytest.raises(IllegalAction):PlayerView(s).query(query_request)
    assert s==before


def test_failed_default_callback_pauses_without_fallback():
    s=load_scenario('A',seed=42);before=deepcopy(s)
    with pytest.raises(IllegalAction,match='PLAYER_CHOICE_REQUIRED'):
        play_with_interface(s,lambda view:{'action_id':'bad','state_version':view.version})
    assert s==before


def test_actual_saved_battle_routes_both_players_and_every_tactical_choice():
    # A small portable position from the already-verified routed-loss test.
    from tests.test_seed_20261012_fixes import _battle_state
    from inferno.actions import _apply_post_battle
    from inferno.battle import ScriptedDecisionError
    s=_battle_state()
    s['lords']['firenze']['forces']={'Militia':1}
    s['lords']['siena']['forces']={}
    s['lords']['siena']['routed_units']={'Cavalieri':1}
    seen=[]
    def callback(payload):
        view=DecisionView(s,payload,payload['side'],'test-parent',len(seen))
        overview=view.overview();entries=all_pages(view,{'request':'actions'},1,10)
        assert len(entries)==len(payload['options'])
        assert [e['move']['args']['choice'] for e in entries]==payload['options']
        assert overview['acting_player']==payload['side']
        seen.append(overview)
        wanted=next((e for e in entries if e['move']['args']['choice']=='withdraw'),entries[0])
        return view.resolve(selection(view,wanted))
    s['battle_callback']=callback
    result={'loser':'defender','conceded':None,'removed_lords':['siena'],'rolls':[]}
    _apply_post_battle(s,result,['firenze'],['siena'],battle_locale='Siena',callback=callback)
    assert seen and any(x['acting_player']=='ghibelline' for x in seen)
    assert s['lords']['siena']['flags']['in_stronghold']


def test_live_storm_views_preserve_choices_results_and_reveal_only_combat_mats():
    from tests.test_v59_storm_sally_callback import _besieged_storm_state
    from inferno.llm.filter import hide_for_side
    s=_besieged_storm_state();s['meta']['hidden_mats']=True
    base=deepcopy(s);other=deepcopy(s)
    choice={'action':'cmd_storm','side':'guelph','args':{'lord_id':'firenze'}}
    traces=[]
    def native(payload):
        traces.append(deepcopy(payload))
        return payload['options'][0]
    other['battle_callback']=native
    expected=dispatch(other,choice)
    other.pop('battle_callback')
    returned=[]
    def cb(view):
        if isinstance(view,PlayerView):
            page=view.query({'request':'actions','category':'cmd_storm'})
            e=page['records'][0]
        else:
            overview=view.overview();entries=all_pages(view,{'request':'actions'},1)
            payload=traces[len(returned)]
            assert [e['move']['args']['choice'] for e in entries]==payload['options']
            assert overview['context']==payload.get('info',{})
            visible=view.query({'request':'inspect','section':'lords','keys':['siena']})
            # Siena is NOT at this Storm, so he stays hidden.
            if view.side=='guelph':
                assert '<hidden>' in compact(visible)
            returned.append(overview)
            e=entries[0]
        return selection(view,e)
    result=play_with_interface(s,cb)
    assert returned and len(returned)==len(traces)
    assert result.applied==expected and s==other
    assert 'battle_callback' not in s
    assert '<hidden_force_count>' in hide_for_side(s,'ghibelline')['lords']['firenze']['forces']


def test_interrupted_optional_combat_decision_rolls_back_without_silent_default():
    from tests.test_v59_storm_sally_callback import _besieged_storm_state
    s=_besieged_storm_state();before=deepcopy(s)
    def cb(view):
        if isinstance(view,DecisionView):
            return {'action_id':'nonexistent','state_version':view.version}
        return selection(view,view.query({'request':'actions','category':'cmd_storm'})['records'][0])
    with pytest.raises(IllegalAction,match='BAD_DECISION'):
        play_with_interface(s,cb,max_strikes=1)
    assert s==before


def test_resumable_combat_queries_preserve_original_save_until_complete():
    from tests.test_v59_storm_sally_callback import _besieged_storm_state
    from inferno.llm.interface import selection_session
    s=_besieged_storm_state();before=deepcopy(s)
    v=PlayerView(s,'guelph')
    chosen=selection(v,v.query({'request':'actions','category':'cmd_storm'})['records'][0])
    prefix=[];observed=[]
    for _ in range(200):
        packet=selection_session(s,'guelph',chosen,decisions=prefix)
        if packet['status']=='accepted':
            break
        assert packet['status']=='awaiting_decision' and s==before
        assert packet['decision_index']==len(prefix)
        observed.append(packet['perspective'])
        page=selection_session(s,'guelph',chosen,decisions=prefix,
                               decision_request={'request':'actions','page_size':1})
        assert s==before
        entry=page['response']['records'][0]
        prefix.append({'action_id':entry['action_id'],'state_version':page['response']['state_version']})
    else:
        pytest.fail('Combat did not finish within the test safety bound')
    assert prefix and observed and s!=before
    check=deepcopy(before)
    check['battle_callback']=lambda payload:payload['options'][0]
    dispatch(check,{'action':'cmd_storm','side':'guelph','args':{'lord_id':'firenze'}})
    check.pop('battle_callback')
    assert s==check
    # Stale tactical selections cannot be turned into default choices.
    fresh=deepcopy(before);bad=deepcopy(prefix);bad[0]['state_version']='stale'
    with pytest.raises(IllegalAction):selection_session(fresh,'guelph',chosen,decisions=bad)
    assert fresh==before


def test_cli_default_overview_focused_reads_and_stale_selection_file_unchanged(tmp_path,capsys):
    from inferno.cli import main
    s=load_scenario('A',seed=42)
    p=tmp_path/'game.json';p.write_text(json.dumps(s))
    assert main(['legal-moves',str(p)])==0
    overview=json.loads(capsys.readouterr().out)
    assert overview['categories'] and 'records' not in overview
    assert main(['legal-moves',str(p),'--page','--page-size','1'])==0
    page=json.loads(capsys.readouterr().out)
    chosen={'action_id':page['records'][0]['action_id'],'state_version':page['state_version']}
    assert main(['choose',str(p),json.dumps(chosen)])==0
    assert json.loads(capsys.readouterr().out)['status']=='accepted'
    saved=p.read_bytes()
    assert main(['choose',str(p),json.dumps(chosen)])==1
    assert json.loads(capsys.readouterr().out)['error']=='STALE_VIEW'
    assert p.read_bytes()==saved
    assert main(['inspect',str(p),'board','--keys','Firenze','--max-chars','10'])==0
    full=json.loads(capsys.readouterr().out)
    assert full['records'][0]['key']=='Firenze' and full['soft_target_exceeded']


def test_conditional_hidden_event_templates_do_not_leak_enemy_assets():
    from tests.test_selfplay_followup_fixes import arrive
    # At an actual solo arrival, held Greek Fire is available if its window
    # allows it; swap enemy resources/units and ensure catalog identity is safe.
    s=arrive(seed=1)
    s['meta']['hidden_mats']=True
    s['decks']['guelph']['aow_held'].append('F7')
    t=deepcopy(s)
    enemy=t['lords']['siena']
    total=sum(enemy['forces'].values());enemy['forces']={'Armigieri':total}
    enemy['assets']={'Coin':1000}
    a,b=PlayerView(s,'guelph'),PlayerView(t,'guelph')
    assert a._catalog.entries==b._catalog.entries


def test_oversized_single_action_is_an_intact_page_and_templates_not_pruned(monkeypatch):
    import inferno.llm.menu as menu
    s=load_scenario('A',seed=1)
    long='A whole action description. '*300
    raw=[{'action':'levy_pay','side':'guelph','args':{'from_lord_id':'<payer>',
         'target_lord_id':'<recipient>','amount':'<integer>'},'description':long,
         'required_parameters':{'last':'COMPLETE_END'}},
         {'action':'levy_pay_done','side':'guelph','description':'Second action.'}]
    monkeypatch.setattr(menu,'enumerate_legal',lambda state:deepcopy(raw))
    v=PlayerView(s,'guelph')
    records=all_pages(v,{'request':'actions'},page_size=1,max_chars=10)
    assert Counter(compact(e['move']) for e in records)==Counter(map(compact,raw))
    assert any(e['parameterized'] for e in records)
    assert long in compact(records)
    before=deepcopy(s)
    template=next(e for e in records if e['parameterized'])
    with pytest.raises(IllegalAction,match='MISSING_PARAMETERS'):v.resolve(selection(v,template))
    assert s==before


def test_tactical_ids_bind_options_and_context_not_only_board_state():
    s=load_scenario('A',seed=42)
    a=DecisionView(s,{'type':'concede','side':'guelph','options':[False,True],'info':{'round':1}},'guelph','parent',1)
    b=DecisionView(s,{'type':'concede','side':'guelph','options':[False,True],'info':{'round':2}},'guelph','parent',1)
    c=DecisionView(s,{'type':'concede','side':'guelph','options':[True,False],'info':{'round':1}},'guelph','parent',1)
    assert len({a.version,b.version,c.version})==3
    choice=selection(a,a.query({'request':'actions'})['records'][0])
    for other in (b,c):
        with pytest.raises(IllegalAction,match='STALE_VIEW'):other.resolve(choice)


@pytest.mark.parametrize('action,fields',[
 ('cmd_march',{'lord_id','destination','way_type','with_lords'}),
 ('cmd_supply',{'lord_id','source','provender'}),
 ('levy_pay',{'from_lord_id','target_lord_id','asset','amount'}),
 ('cmd_fpd_pay',{'from_lord_id','target_lord_id','asset','amount'})])
def test_parameter_reference_follows_validation_helpers(action,fields):
    view=PlayerView(load_scenario('A',seed=42))
    record=view.query({'request':'inspect','section':'action_reference','keys':[action]})['records'][0]
    assert fields<=set(record['value']['argument_fields'])
    assert record['value']['handler_documentation']


def test_trace_abbreviation_does_not_cut_required_args_or_unlabelled_changes():
    s=load_scenario('A',seed=42)
    args={'decisions':[{'necessary':'Keep me complete.'*500}],'rounds':[1,2,3]}
    s['history']=[{'side':'guelph','action':'example','args':args,
      'state_changes':{'important':'IMPORTANT_END','battle_result':{'loser':'attacker','rounds':[{'strikes':list(range(2000))}]}},
      'rolls':[{'context':'roll','value':1}]}]
    doc=build_briefing_document(s,'guelph',max_chars=100)
    change=next(x for x in doc['sections'] if x['id']=='changes')
    assert change['status']=='abbreviated' and 'IMPORTANT_END' in change['text']
    assert compact(args) in change['text']
    assert 'deferred' in change['text']
    full=PlayerView(s).query({'request':'inspect','section':'history','keys':['1']})
    assert full['records'][0]['value']==s['history'][0]


def test_hidden_game_flag_is_preserved_across_cli_entry_points(tmp_path,capsys):
    from inferno.cli import main
    p=tmp_path/'hidden.json'
    assert main(['new','A','--seed','42','--hidden-mats','--out',str(p)])==0
    capsys.readouterr()
    s=json.loads(p.read_text());s['decks']['ghibelline']['aow_held']=['SECRET_TOKEN']
    s['lords']['siena']['assets']={'Coin':87654}
    p.write_text(json.dumps(s))
    for argv in (['query',str(p),' {"request":"inspect","section":"snapshot"}','--side','guelph'],
                 ['state',str(p),'--mode','verbose','--side','guelph'],
                 ['briefing',str(p),'--side','guelph'],
                 ['inspect',str(p),'lords','--keys','siena','--side','guelph']):
        assert main(argv)==0
        output=capsys.readouterr().out
        assert 'SECRET_TOKEN' not in output and '87654' not in output


def test_fast_freshness_hash_equals_complete_filtered_snapshot():
    from inferno.llm.protocol import view_version, visible_state
    s=load_scenario('A',seed=42)
    s['history']=[{'action':'plan_add_card','side':'ghibelline','args':{'card_id':'SECRET'},'state_changes':{}} for _ in range(500)]
    for side in SIDES:
        for hidden in (False,True):
            assert state_version(s,side,hidden)==view_version(visible_state(s,side,hidden))


@pytest.mark.parametrize('side,lid,enemy,cid,cap',[
 ('guelph','arezzo','siena','F7','S2'),('ghibelline','siena','arezzo','S7','F5')])
def test_hidden_greek_fire_templates_cover_all_instantiations_without_mat_oracle(side,lid,enemy,cid,cap):
    from tests.test_selfplay_followup_fixes import active, hold
    s=load_scenario('A',seed=42);active(s,side,lid)
    s['meta']['hidden_mats']=True
    hold(s,side,cid)
    foe=s['lords'][enemy];foe['capabilities']=[cap]
    loc=s['locales'][foe['location']]
    loc['siege']=[{'side':foe['side'],'color':'gold' if side=='guelph' else 'purple','count':2}]
    foe['forces']={'Armigieri':2,'Cavalieri':1}
    raw=[m for m in enumerate_legal(s) if m['action']=='play_event' and m['args']['card_id']==cid]
    assert len(raw)==2
    v=PlayerView(s,side)
    templates=[e for e in all_pages(v,{'request':'actions'}) if e['move']['action']=='play_event' and e['move']['args']['card_id']==cid]
    assert len(templates)==1 and templates[0]['parameterized']
    for move in raw:
        a,b=deepcopy(s),deepcopy(s)
        assert dispatch(a,move)==submit_selection(b,side,selection(v,templates[0],args=move['args']))
        assert a==b
    t=deepcopy(s);t['lords'][enemy]['forces']={'Militia':3};t['lords'][enemy]['assets']={'Coin':999}
    w=PlayerView(t,side)
    assert v.version==w.version and v.overview()==w.overview()
    assert all_pages(v,{'request':'actions'})==all_pages(w,{'request':'actions'})
    # A private off-turn reader must not receive apparently available plays.
    t['meta']['active_player']=foe['side']
    assert not PlayerView(t,side)._catalog.entries


@pytest.mark.parametrize('side,lid,enemy', [('guelph','arezzo','siena'),('ghibelline','siena','arezzo')])
def test_hidden_bribe_category_does_not_reveal_vassal_readiness(side,lid,enemy):
    from tests.test_selfplay_followup_fixes import active,relocate
    s=load_scenario('A',seed=42);active(s,side,lid)
    s['meta']['hidden_mats']=True;s['current_card']='treachery_'+lid
    s['lords'][lid]['assets']['Coin']=2
    relocate(s,enemy,s['lords'][lid]['location'])
    s['lords'][enemy]['vassals']=[{'name':'UNKNOWN_PRIVATE_VASSAL','on_mat':True,'special':False}]
    t=deepcopy(s);t['lords'][enemy]['vassals'][0]['on_mat']=False
    a,b=PlayerView(s,side),PlayerView(t,side)
    assert a.version==b.version
    assert a._catalog.entries==b._catalog.entries
    entries=[e for e in a._catalog.entries if e['move']['action']=='cmd_treachery_bribe']
    assert len(entries)==1 and entries[0]['parameterized']
    assert 'UNKNOWN_PRIVATE_VASSAL' not in compact(entries)


@pytest.mark.parametrize('cid,fields', [('F7',{'enemy_lord_id','unit_to_remove','capability_to_discard'}),
 ('S7',{'enemy_lord_id','unit_to_remove','capability_to_discard'}),
 ('F23',{'mode','coin_sources','treachery_card'})])
def test_full_card_reference_includes_effect_parameter_grammar(cid,fields):
    v=PlayerView(load_scenario('A',seed=42))
    ref=v.query({'request':'inspect','section':'card_reference','keys':[cid]})['records'][0]['value']
    assert fields<=set(ref['event_parameters']['argument_fields'])
    assert ref['event_parameters']['handler_documentation']


def test_invalid_optional_script_in_model_path_cannot_become_a_default():
    from inferno.battle import BattleDecisionContext, ScriptedDecisionError
    from inferno.visibility import strict_player_choices
    bdc=BattleDecisionContext(scripted=[{'type':'concede','side':'attacker','choice':'NOT_AN_OPTION'}])
    with strict_player_choices(),pytest.raises(ScriptedDecisionError):
        bdc.decide_optional('concede','attacker',[False,True],False)


def test_player_cannot_preselect_opponents_tactical_choices_via_operator_script():
    from tests.test_v59_storm_sally_callback import _besieged_storm_state
    from inferno.llm import selection_session
    s=_besieged_storm_state();before=deepcopy(s)
    v=PlayerView(s);entry=v.query({'request':'actions','category':'cmd_storm'})['records'][0]
    choice=selection(v,entry,args={**entry['move']['args'],'scripted_decisions':[
        {'type':'concede','side':'defender','choice':True}]})
    for run in (lambda: play_with_interface(s,lambda view:choice),
                lambda: selection_session(s,v.side,choice)):
        with pytest.raises(IllegalAction,match='OWNER_DECISION_REQUIRED'):run()
        assert s==before


def test_cli_combat_continuation_does_not_echo_raw_originating_player_selection():
    from tests.test_v59_storm_sally_callback import _besieged_storm_state
    from inferno.llm import selection_session
    s=_besieged_storm_state();v=PlayerView(s)
    entry=v.query({'request':'actions','category':'cmd_storm'})['records'][0]
    result=selection_session(s,v.side,selection(v,entry))
    assert result['status']=='awaiting_decision'
    assert 'selection' not in result['resume']
    assert result['resume']['base_version']==v.version
