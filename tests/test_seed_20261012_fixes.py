"""Seven fresh long-game findings, tested at the actual failure positions."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from inferno import actions as A, battle as B
from inferno.legal_moves import enumerate_legal
from inferno.scenarios import load_scenario
from inferno.rng import HarnessRNG
from inferno.invariants import check_all_invariants

FIXTURES = Path(__file__).parent / 'fixtures' / 'seed_20261012'
def saved(name):
    return json.loads((FIXTURES / name).read_text())
def action(name, side='guelph', **args):
    return {'action': name, 'side': side, 'args': args}
def reject(state, act, code=None):
    before = json.dumps(state)
    with pytest.raises(A.IllegalAction) as err:
        A.dispatch(state, act)
    if code:
        assert err.value.code == code
    assert json.dumps(state) == before

def test_actual_gather_stops_after_command_budget_and_save_does_not_refill_it():
    s = saved('before_gather.json')
    moves = saved('gather_actions.json')
    A.dispatch(s, moves[0])
    for move, cost in zip(moves[1:4], [0,1,1]):
        assert any(m['action']==move['action'] and m['args']==move['args'] for m in enumerate_legal(s))
        before = deepcopy(s['lords']['arezzo']['assets'])
        result = A.dispatch(s, move)
        assert result['state_changes']['cost'] == cost
        assert s['lords']['arezzo']['assets'] == before
        s = json.loads(json.dumps(s, sort_keys=True))
    assert s['lords']['arezzo']['location'] == 'Montevarchi'
    assert s['meta']['cta_gather_progress']['arezzo']['spent'] == 2
    assert not any(m['action']=='cta_gather_march' and m['args']['lord_id']=='arezzo'
                   for m in enumerate_legal(s))
    reject(s, moves[4], 'GATHER_EXHAUSTED')
    assert not s['lords']['arezzo']['flags'].get('moved_fought')
    check_all_invariants(s)

@pytest.mark.parametrize('loot,expected_cost', [(0,0),(1,2)])
def test_gather_uses_actual_laden_cost_and_does_not_spend_assets(loot,expected_cost):
    s = saved('before_gather.json'); moves=saved('gather_actions.json')
    A.dispatch(s, moves[0]);s['lords']['arezzo']['assets']['Loot']=loot
    before=deepcopy(s['lords']['arezzo']['assets'])
    r=A.dispatch(s,moves[1]);assert r['state_changes']['cost']==expected_cost
    assert s['lords']['arezzo']['assets']==before
    if loot: reject(s,moves[2],'GATHER_EXHAUSTED')

def test_gather_road_works_and_command_modifiers_are_scoped_to_gather():
    s=saved('before_gather.json');A.dispatch(s,saved('gather_actions.json')[0])
    l=s['lords']['arezzo'];l['flags']['first_march_used_this_card']=True
    l['assets']['Loot']=1
    s.setdefault('active_events',{}).setdefault('this_campaign',[]).append({'id':'F5','side':'guelph'})
    r=A.dispatch(s,saved('gather_actions.json')[1]);assert r['state_changes']['cost']==0
    assert l['flags']['first_march_used_this_card'] is True
    # The allowance does not increase just by entering a seat on a later leg.
    s['capabilities_in_play'].append({'id':'F23','name':'Via Francigena','side':'guelph','scope':'side_wide'})
    A.dispatch(s,saved('gather_actions.json')[2])
    assert s['meta']['cta_gather_progress']['arezzo']['allowance']==2
    A.dispatch(s, action('cta_step_skip'))
    assert not s['meta'].get('cta_gather_progress')


def test_actual_treasurers_cannot_be_used_without_playing_and_paying():
    s=saved('before_treasurers.json')
    assert 'F23' in s['decks']['guelph']['aow_held']
    assert not A._cta_trigger_met(s,'guelph')[0]
    assert not any(m['action']=='levy_cta_declare' for m in enumerate_legal(s))
    reject(s,action('levy_cta_declare'),'CTA_NOT_ELIGIBLE')
    options=[m for m in enumerate_legal(s) if m['action']=='play_event'
             and m['args']['card_id']=='F23' and m['args']['effect_args']['mode']=='declare_cta']
    assert options
    before=sum(l['assets'].get('Coin',0) for l in s['lords'].values())
    A.dispatch(s,options[0])
    assert sum(l['assets'].get('Coin',0) for l in s['lords'].values())==before-2
    assert 'F23' not in s['decks']['guelph']['aow_held']
    A.dispatch(s,action('levy_cta_declare'))
    assert s['meta']['cta_active']
    check_all_invariants(s)

@pytest.mark.parametrize('payment', [{'siena':2},{'arezzo':-1,'firenze':3},{'arezzo':True,'colle':1},[],{'missing':2}])
def test_treasurers_rejects_invalid_payment_atomically(payment):
    s=saved('before_treasurers.json')
    reject(s,action('play_event',card_id='F23',effect_args={'mode':'declare_cta','coin_sources':payment}))

@pytest.mark.parametrize('play', [False,True])
def test_treasurers_final_offer_after_ghibellines_decline(play):
    s=saved('before_treasurers.json')
    A.dispatch(s,action('levy_cta_skip'))
    assert s['meta']['active_player']=='ghibelline'
    A.dispatch(s,action('levy_cta_skip','ghibelline'))
    assert s['meta']['active_player']=='guelph'
    assert s['meta']['cta_treasurers_final_offer']
    if play:
        m=next(m for m in enumerate_legal(s) if m['action']=='play_event' and m['args']['card_id']=='F23'
               and m['args']['effect_args']['mode']=='declare_cta')
        A.dispatch(s,m);A.dispatch(s,action('levy_cta_declare'))
        assert s['meta']['cta_active']
    else:
        A.dispatch(s,action('levy_cta_skip'))
        assert s['meta']['phase']=='campaign'
        assert 'F23' in s['decks']['guelph']['aow_held']

@pytest.mark.parametrize('scenario,active', [('A',False),('C',False),('E',False),('F',True)])
def test_treasurers_cannot_declare_in_closed_window(scenario,active):
    s=saved('before_treasurers.json');s['meta']['scenario']=scenario;s['meta']['cta_active']=active
    reject(s,action('play_event',card_id='F23',effect_args={'mode':'declare_cta'}),'NO_PLAY_WINDOW')


def post_result():
    return {'loser':'defender','winner':'attacker','conceded':None,
            'removed_lords':['siena','siena_comune'],'rolls':[]}
def aftermath(s,r,**kw):
    A._apply_post_battle(s,r,['firenze','firenze_comune'],['siena_comune','siena'],battle_locale='Siena',**kw)

def test_actual_fully_routed_siena_gets_withdrawal_and_recovery_for_both_mats(monkeypatch):
    s=saved('before_aftermath.json');r=post_result()
    assert sum(s['lords']['siena']['forces'].values())==0
    assert sum(s['lords']['siena']['routed_units'].values())==5
    # All recovery rolls succeed, isolating the routing/removal distinction.
    monkeypatch.setattr('random.Random.randint',lambda self,a,b:1)
    before={lid:deepcopy(s['lords'][lid]['assets']) for lid in ['siena','siena_comune']}
    aftermath(s,r,decisions=[{'type':'post_battle_withdraw','choice':'withdraw','side':'ghibelline'}])
    for lid in before:
        assert s['lords'][lid]['status']=='mustered'
        assert s['lords'][lid]['location']=='Siena'
        assert s['lords'][lid]['flags']['in_stronghold']
        assert s['lords'][lid]['assets']==before[lid]
        assert sum(r['loss_results'][lid]['recovered'].values())==5
    assert r['removed_lords']==[]
    assert r['routed_lords']==['siena','siena_comune']
    assert not s.get('captured_carroccio_for_side',{}).get('guelph')
    check_all_invariants(s)

@pytest.mark.parametrize('conceded',[False,True])
def test_fully_routed_retreat_rolls_losses_and_keeps_pair_together(conceded,monkeypatch):
    s=saved('before_aftermath.json');r=post_result()
    if conceded:r['conceded']='defender'
    monkeypatch.setattr('random.Random.randint',lambda self,a,b:1)
    aftermath(s,r)
    assert s['lords']['siena']['status']=='mustered'
    assert s['lords']['siena']['location']==s['lords']['siena_comune']['location']!='Siena'
    for lid in ['siena','siena_comune']:
        assert r['loss_results'][lid]['harsh_recovery'] is not conceded
    assert s.get('captured_carroccio_for_side',{}).get('guelph',0)==(0 if conceded else 1)
    check_all_invariants(s)

@pytest.mark.parametrize('when', ['before_recovery','after_recovery'])
def test_real_removal_processes_comune_spoils_before_cleanup(when,monkeypatch):
    s=saved('before_aftermath.json');r=post_result()
    before=sum(s['lords'][lid]['assets'].get('Cart',0) for lid in ['firenze','firenze_comune'])
    if when=='before_recovery':
        monkeypatch.setattr(A,'_retreat_candidates',lambda *a,**k:[])
        monkeypatch.setattr(A,'_can_withdraw_into_stronghold',lambda *a,**k:False)
        decisions=[]
    else:
        # Withdraw keeps the mats until recovery fails; removal still captures them.
        monkeypatch.setattr('random.Random.randint',lambda self,a,b:6)
        decisions=[{'type':'post_battle_withdraw','choice':'withdraw'}]
    aftermath(s,r,decisions=decisions)
    assert s['lords']['siena']['status']!='mustered'
    assert s['lords']['siena_comune']['status']=='in_levy_pool'
    assert not s['lords']['siena_comune']['assets']
    assert sum(s['lords'][lid]['assets'].get('Cart',0) for lid in ['firenze','firenze_comune'])==before+12
    assert s['captured_carroccio_for_side']['guelph']==1
    assert sum(x['carroccio_captured'] for x in r['spoils'])==1
    assert any(x['loser_id']=='siena_comune' and x['transferred'].get('Cart')==6 for x in r['spoils'])
    if when=='before_recovery':
        assert 'siena' not in r['loss_results']
        assert 'siena_comune' not in r['loss_results']
    check_all_invariants(s)

@pytest.mark.parametrize('optional',[False,True])
def test_battle_trace_is_a_deep_snapshot_including_options_and_callback(optional):
    positions={'defender':{'center':'siena'}};options=[{'x':[1]},{'x':[2]}]
    def callback(ctx):
        ctx['info']['positions']['defender']['center']='callback edit'
        return ctx['options'][1]
    bdc=B.BattleDecisionContext(callback=callback)
    if optional:bdc.decide_optional('probe','ghibelline',options,options[0],{'positions':positions})
    else:bdc.decide('probe','ghibelline',options,{'positions':positions})
    assert positions['defender']['center']=='siena'
    positions['defender']['center']=None;options[1]['x'].append(99)
    assert bdc.trace[0]['info']['positions']['defender']['center']=='siena'
    assert bdc.trace[0]['choice']=={'x':[2]}


def test_actual_battle_roll_log_records_every_call_once_and_freezes_trace(monkeypatch):
    s=saved('before_battle.json');calls=[];infos=[]
    original=HarnessRNG.roll;decide=B.BattleDecisionContext.decide
    def roll(rng,context):
        r=original(rng,context);calls.append({'context':context,'value':r.value});return r
    def record_decision(bdc,typ,side,options,info=None):
        if typ=='concede':infos.append(deepcopy(info))
        return decide(bdc,typ,side,options,info)
    monkeypatch.setattr(HarnessRNG,'roll',roll)
    monkeypatch.setattr(B.BattleDecisionContext,'decide',record_decision)
    n=s['meta']['rng_advance']
    r=A.dispatch(s,action('approach_response','ghibelline',lord_id='siena_comune',choice='stand'))
    assert r['rolls']==calls
    assert len(calls)==s['meta']['rng_advance']-n
    assert any(x['context'].startswith('loss_siena_') for x in calls)
    assert any(x['context'].startswith('loss_firenze_') for x in calls)
    trace=[x for x in r['state_changes']['battle_result']['decisions'] if x['type']=='concede']
    assert [x['info'] for x in trace]==infos
    check_all_invariants(s)


def test_single_fealty_roll_is_not_logged_twice(monkeypatch):
    s=load_scenario('F',seed=20261012);calls=[];original=HarnessRNG.roll
    def roll(rng,context):
        r=original(rng,context);calls.append({'context':context,'value':r.value});return r
    monkeypatch.setattr(HarnessRNG,'roll',roll)
    for act in saved('initial_actions.json'):
        calls.clear();start=s['meta'].get('rng_advance',0);r=A.dispatch(s,act)
        assert r['rolls']==calls
        assert len(calls)==s['meta']['rng_advance']-start
    assert len(r['rolls'])==1
    old=deepcopy(s['history'][-1]);r['rolls'].clear();r['state_changes'].clear()
    assert s['history'][-1]==old


def test_drain_log_does_not_reset_rng_advance():
    r=HarnessRNG(7,3);r.roll('one');assert r.advance_count==4
    assert len(r.drain_log())==1;assert r.advance_count==4
    r.roll('two');assert r.advance_count==5


def test_original_save_boundary_same_results_and_assets_through_waste():
    live=saved('before_save.json');loaded=json.loads(json.dumps(live,sort_keys=True))
    assert json.dumps(live)!=json.dumps(loaded) and live==loaded
    for n,act in enumerate(saved('save_continuation.json'),340):
        r1=A.dispatch(live,act);r2=A.dispatch(loaded,act)
        assert r1==r2, n
        assert live==loaded, n
    assert n==443
    assert live['lords']['colle']['assets']==loaded['lords']['colle']['assets']
    assert live['lords']['firenze']['assets']==loaded['lords']['firenze']['assets']
    check_all_invariants(live)

@pytest.mark.parametrize('order', [['Cart','Coin','Provender'],['Coin','Provender','Cart'],['Provender','Cart','Coin']])
def test_waste_default_does_not_depend_on_asset_insertion_order(order):
    s=load_scenario('F',seed=8)
    s['meta'].update(phase='campaign',campaign_step='end_campaign',active_player='guelph')
    s['lords']['firenze']['assets']={k:4 for k in order}
    A._h_end_waste(s,'guelph',{},HarnessRNG(8))
    assert s['lords']['firenze']['assets']=={'Cart':4,'Coin':3,'Provender':4}

@pytest.mark.parametrize('fixture',['before_gather.json','before_treasurers.json','before_battle.json','before_save.json'])
def test_menu_is_identical_across_sorted_saves_and_never_mutates_state(fixture):
    s=saved(fixture);loaded=json.loads(json.dumps(s,sort_keys=True));before=json.dumps(s)
    assert enumerate_legal(s)==enumerate_legal(loaded)
    assert json.dumps(s)==before

@pytest.mark.parametrize('loser',['attacker','defender'])
def test_sally_also_recovers_fully_routed_lords_instead_of_removing_them(loser,monkeypatch):
    s=load_scenario('F',seed=1)
    A._place_cylinder(s,'firenze',None)
    s['locales']['Firenze']['lords_present'].remove('firenze')
    s['locales']['Siena']['lords_present'].append('firenze');s['lords']['firenze']['location']='Siena'
    s['locales']['Siena']['siege']=[{'side':'guelph','color':'purple','count':3}]
    s['lords']['siena']['flags']['in_stronghold']=True
    s['lords']['siena']['assets']['Provender']=20
    s['lords']['firenze']['assets']['Provender']=20
    s['meta'].update(phase='campaign',levy_step=None,campaign_step='command_phase',active_player='ghibelline')
    s.update(current_lord_id='siena',current_card='command_siena',actions_remaining=2)
    routed='siena' if loser=='attacker' else 'firenze'
    def combat(state,**kwargs):
        state['lords'][routed]['forces']={};state['lords'][routed]['routed_units']={'Men-at-Arms':2}
        return {'loser':loser,'winner':'defender' if loser=='attacker' else 'attacker',
                'conceded':None,'removed_lords':[routed],'rolls':[]}
    monkeypatch.setattr(B,'resolve_sally',combat)
    monkeypatch.setattr('random.Random.randint',lambda self,a,b:1)
    r=A.dispatch(s,action('cmd_sally','ghibelline',lord_id='siena'))
    battle=r['state_changes']['sally_result']
    assert s['lords'][routed]['status']=='mustered'
    assert battle['loss_results'][routed]['recovered']=={'Men-at-Arms':2}
    assert battle['loss_results'][routed]['harsh_recovery']==(loser=='defender')
    assert not battle['removed_lords']
    if loser=='attacker':
        assert s['lords']['siena']['flags']['in_stronghold']
        assert s['locales']['Siena']['siege'][0]['count']==1
    else:
        assert s['lords']['firenze']['location']!='Siena'
        assert s['locales']['Siena']['siege']==[]


def test_sally_true_removal_still_triggers_revolt_through_shared_aftermath(monkeypatch):
    s=load_scenario('F',seed=1)
    s['locales']['Firenze']['lords_present'].remove('firenze')
    s['locales']['Siena']['lords_present'].append('firenze');s['lords']['firenze']['location']='Siena'
    s['locales']['Siena']['siege']=[{'side':'guelph','color':'purple','count':3}]
    s['lords']['siena']['flags']['in_stronghold']=True
    s['lords']['firenze']['assets']['Provender']=20
    s['meta'].update(phase='campaign',levy_step=None,campaign_step='command_phase',active_player='ghibelline')
    s.update(current_lord_id='siena',current_card='command_siena',actions_remaining=2)
    def combat(state,**kwargs):
        state['lords']['siena']['forces']={};state['lords']['siena']['routed_units']={}
        return {'loser':'attacker','winner':'defender','conceded':None,
                'removed_lords':['siena'],'rolls':[]}
    monkeypatch.setattr(B,'resolve_sally',combat)
    calls=[];original=A._trigger_disband_revolt_and_treachery
    def record(state,removed,rng,context):
        calls.append(list(removed));return original(state,removed,rng,context)
    monkeypatch.setattr(A,'_trigger_disband_revolt_and_treachery',record)
    r=A.dispatch(s,action('cmd_sally','ghibelline',lord_id='siena'))
    assert any('siena' in ids for ids in calls)
    assert 'siena' in r['state_changes']['sally_result']['removed_lords']
    assert s['lords']['siena']['status']!='mustered'
    assert any('revolt' in roll['context'] for roll in r['rolls'])
    check_all_invariants(s)
