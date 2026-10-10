"""Regression repairs for all eight findings from actual Scenario F play.

Rules: supplied Call to Arms (3.5), Sequence of Play (3.3/4.9.3), and
Siege (4.5.2 Sack) reference transcriptions. No old outcomes are preserved.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from inferno import actions as A, card_effects as CE, static_data as SD
from inferno.actions import dispatch, IllegalAction
from inferno.flow import advance_to_next_side_or_step, advance_campaign_step
from inferno.invariants import check_all_invariants
from inferno.legal_moves import enumerate_legal
from inferno.rng import HarnessRNG
from inferno.scenarios import load_scenario

FIXTURES = Path(__file__).parent / 'fixtures' / 'long_scenario'


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def act(name, side='guelph', **args):
    return {'action': name, 'side': side, 'args': args}


def reject_unchanged(state, action, code=None):
    before = deepcopy(state)
    with pytest.raises(IllegalAction) as error:
        dispatch(state, action)
    if code:
        assert error.value.code == code
    assert state == before


def cta_state(side='guelph', step='allies'):
    state = load_scenario('F', seed=42)
    state['meta'].update(phase='levy', levy_step='3.5', active_player=side,
                         cta_active=True, cta_substep=step, cta_sides_done=[])
    return state


def test_original_extra_muster_rejects_besieger_then_plays_eligible_commander():
    s = fixture('before_105_cta_allies.json')
    # The recorded request was itself ineligible: Arezzo besieged hostile Cortona.
    # Reject that target, then spend the earned segment with eligible Firenze.
    reject_unchanged(s, act('cta_allies', mode='extra_muster', target_lord_id='arezzo'), 'MUSTER_NOT_ELIGIBLE')
    before = s['lords']['firenze']['assets'].get('Cart', 0)
    dispatch(s, act('cta_allies', mode='extra_muster', target_lord_id='firenze'))
    assert s['meta']['active_player'] == 'guelph'
    assert s['meta']['cta_substep'] == 'allies_muster'
    assert any(m['action'] == 'levy_muster_transport' and
               m['args']['lord_id'] == 'firenze' for m in enumerate_legal(s))
    reject_unchanged(s, act('levy_muster_transport', lord_id='arezzo', kind='Cart'))
    reject_unchanged(s, act('cta_allies', mode='extra_muster', target_lord_id='firenze'))
    reject_unchanged(s, act('levy_cta_declare'))
    reject_unchanged(s, act('levy_cta_skip'))
    for _ in range(A._lordship_limit(s, 'firenze')):
        dispatch(s, act('levy_muster_transport', lord_id='firenze', kind='Cart'))
    assert s['lords']['firenze']['assets']['Cart'] > before
    reject_unchanged(s, act('levy_muster_transport', lord_id='firenze', kind='Cart'), 'LORDSHIP_EXHAUSTED')
    dispatch(s, act('levy_muster_done'))
    assert s['meta']['active_player'] == 'ghibelline'
    assert s['meta']['cta_substep'] == 'gather'
    check_all_invariants(s)


@pytest.mark.parametrize('side,lid', [('guelph','firenze'), ('ghibelline','siena')])
def test_commander_can_receive_extra_segment_and_it_survives_save_load(side, lid, tmp_path):
    s = cta_state(side)
    s['lords'][lid]['flags'].update(lordship_used=999, just_mustered_this_segment=True)
    extra = act('cta_allies', side, mode='extra_muster', target_lord_id=lid)
    assert any(m['action'] == extra['action'] and m.get('args') == extra['args'] for m in enumerate_legal(s))
    dispatch(s, extra)
    p = tmp_path / 'save.json'; p.write_text(json.dumps(s))
    restored = json.loads(p.read_text())
    move = act('levy_muster_transport', side, lord_id=lid, kind='Cart')
    assert dispatch(s, move) == dispatch(restored, move)
    assert s == restored
    dispatch(s, act('cta_step_skip', side))
    assert s['meta']['cta_substep'] != 'allies_muster'


@pytest.mark.parametrize('exit_path', ['levy_complete','reset','campaign_advance'])
def test_war_permission_expires_before_next_levy(exit_path):
    s = cta_state('ghibelline')
    CE.F25_event(s, 'guelph', {}, HarnessRNG(1))
    CE.S26_event(s, 'ghibelline', {}, HarnessRNG(1))
    assert set(s['war_declared_this_levy']) == {'guelph','ghibelline'}
    if exit_path == 'levy_complete':
        advance_to_next_side_or_step(s)
    else:
        s['meta'].update(phase='campaign', campaign_step='end_campaign', levy_step=None)
        if exit_path == 'reset':
            dispatch(s, act('end_reset', 'ghibelline'))
        else:
            advance_campaign_step(s)
    assert not s.get('war_declared_this_levy')
    s['meta'].update(phase='levy', levy_step='3.5', turn=3,
                    active_player='guelph', cta_active=False)
    s['vp'] = {'guelph':4, 'ghibelline':4}
    s['decks']['guelph']['aow_held'] = []
    assert not A._cta_trigger_met(s, 'guelph')[0]
    reject_unchanged(s, act('levy_cta_declare'), 'CTA_NOT_ELIGIBLE')
    CE.F25_event(s, 'guelph', {}, HarnessRNG(1))
    assert A._cta_trigger_met(s, 'guelph') == (True, 'war_event')


def test_original_surprise_sack_subtracts_allegiance_points():
    s = fixture('before_242_sack_score.json')
    result = dispatch(s, act('play_event', card_id='F3'))
    assert s['locales']['Poggio Bonizio']['current_allegiance'] == []
    assert s['vp'] == {'guelph':4.0, 'ghibelline':2.5}
    assert A._compute_final_vp(s) == (4.0, 2.5)
    check_all_invariants(s)


def test_original_gather_moves_compulsory_comune_with_commander():
    s = fixture('turn4_cta_gather.json')
    before = deepcopy(s)
    moves = enumerate_legal(s)
    assert s == before
    assert not any(m['action'] == 'cta_gather_march' and
                   m['args']['lord_id'] == 'firenze_comune' for m in moves)
    reject_unchanged(s, act('cta_gather_march', lord_id='firenze_comune',
                            destination='Colle', way_type='track'))
    dispatch(s, act('cta_gather_march', lord_id='firenze', destination='Colle', way_type='track'))
    for lid in ('firenze','firenze_comune'):
        assert s['lords'][lid]['location'] == 'Colle'
        assert lid not in s['locales']['Casole']['lords_present']
        assert s['locales']['Colle']['lords_present'].count(lid) == 1
        assert s['lords'][lid]['assets'] == before['lords'][lid]['assets']
        assert s['lords'][lid]['flags'].get('moved_fought') == before['lords'][lid]['flags'].get('moved_fought')
    check_all_invariants(s)


def test_gather_does_not_let_a_besieged_pair_escape():
    s = fixture('turn4_cta_gather.json')
    s['locales']['Casole']['siege'] = [{'side':'ghibelline','color':'gold','count':1}]
    for lid in ('firenze','firenze_comune'):
        s['lords'][lid]['flags']['in_stronghold'] = True
    reject_unchanged(s, act('cta_gather_march', lord_id='firenze', destination='Colle', way_type='track'), 'BESIEGED')
    assert not any(m['action'] == 'cta_gather_march' and m['args']['lord_id'] == 'firenze'
                   for m in enumerate_legal(s))


def test_repeating_existing_comune_setup_does_not_regenerate_anything():
    s = fixture('turn4_existing_comune.json')
    before = deepcopy(s['lords']['siena_comune'])
    dispatch(s, act('cta_comune_setup', 'ghibelline'))
    assert s['lords']['siena_comune'] == before
    check_all_invariants(s)


def test_existing_comune_adds_only_previously_unmustered_vassals():
    s = fixture('turn4_existing_comune.json')
    old = deepcopy(s['lords']['siena_comune'])
    fresh = next(v for v in old['vassals'] if not v['on_mat'] and v['special'])
    requested = ['Carroccio', 'Terzo di Camollia', fresh['name']]
    dispatch(s, act('cta_comune_setup', 'ghibelline', muster_special_vassals=requested))
    new = s['lords']['siena_comune']
    for unit in set(old['forces']) | set(fresh['forces']):
        assert new['forces'].get(unit,0) == old['forces'].get(unit,0) + fresh['forces'].get(unit,0)
    assert new['assets'] == old['assets']
    s['meta']['cta_substep'] = 'comune'
    new_before = deepcopy(new)
    dispatch(s, act('cta_comune_setup', 'ghibelline', muster_special_vassals=requested))
    assert s['lords']['siena_comune'] == new_before
    check_all_invariants(s)


def test_bad_comune_selection_is_atomic():
    s = fixture('turn4_existing_comune.json')
    reject_unchanged(s, act('cta_comune_setup', 'ghibelline', muster_special_vassals=['Unknown']))


def test_original_commander_recall_removes_comune_before_remuster():
    s = fixture('before_641_commander_recall.json')
    dispatch(s, act('cta_commander_arms', mode='disband_and_remuster'))
    c = s['lords']['firenze_comune']
    assert c['status'] == 'in_levy_pool' and c['location'] is None
    assert not c['forces'] and not c['assets'] and not c['capabilities'] and not c['routed_units']
    assert all('firenze_comune' not in loc['lords_present'] for loc in s['locales'].values())
    check_all_invariants(s)
    dispatch(s, act('cta_comune_setup'))
    assert s['lords']['firenze_comune']['location'] == 'Firenze'
    assert s['locales']['Firenze']['lords_present'].count('firenze_comune') == 1
    assert all('firenze_comune' not in loc['lords_present']
               for name,loc in s['locales'].items() if name != 'Firenze')
    check_all_invariants(s)


@pytest.mark.parametrize('side,commander,comune', [('guelph','firenze','firenze_comune'),
                                                ('ghibelline','siena','siena_comune')])
@pytest.mark.parametrize('kind', ['at','beyond'])
def test_general_commander_disband_returns_attached_comune_to_pool(side,commander,comune,kind):
    s = cta_state(side, 'comune')
    dispatch(s, act('cta_comune_setup',side))
    c = s['lords'][comune]
    cid = 'F9' if side == 'guelph' else 'S9'
    s['decks'][side]['aow_deck'].remove(cid)
    c['capabilities'] = [cid]
    c['routed_units'] = {'Militia':1}
    if kind == 'at': A._disband_at_service_limit(s, commander, s['meta']['turn'])
    else: A._disband_beyond_service_limit(s, commander)
    assert c['status'] == 'in_levy_pool'
    assert c['location'] is None and c['calendar_box'] is None and c['service_box'] is None
    assert not c['forces'] and not c['routed_units'] and not c['flags']
    assert not c['capabilities'] and s['decks'][side]['aow_deck'].count(cid) == 1
    check_all_invariants(s)


def test_turn_16_ends_at_game_check_without_repair_or_waste():
    s = fixture('secondary_before_1684_game_end.json')
    before = deepcopy(s)
    result = dispatch(s, act('end_game_check'))
    assert result['state_changes']['game_ended'] is True
    assert s['meta']['game_over'] and s['meta']['phase'] == 'victory'
    assert s['meta']['winner'] == 'ghibelline'
    assert enumerate_legal(s) == []
    assert s['lords'] == before['lords'] and s['locales'] == before['locales']
    reject_unchanged(s, act('end_repair'))


@pytest.mark.parametrize('turn,end_box,ended', [(15,None,False),(16,None,True),
                                               (13,15,False),(14,15,True),(15,16,True)])
def test_game_end_checks_respect_calendar_and_end_marker(turn,end_box,ended):
    s = fixture('secondary_before_1684_game_end.json')
    s['meta']['turn'] = turn; s['calendar']['levy_box'] = turn
    s['calendar']['end_box'] = end_box
    r = dispatch(s, act('end_game_check'))
    assert r['state_changes']['game_ended'] == ended


def test_same_code_state_is_identical_across_process_hash_seeds():
    code = '''
import hashlib,json
from inferno.scenarios import load_scenario
from inferno.rng import HarnessRNG
from inferno import card_effects as C, actions as A
s=load_scenario('F',seed=20261010)
r=HarnessRNG(42)
for cid,side in [('F25','guelph'),('S25','ghibelline'),('F26','guelph'),('S26','ghibelline')]:
    getattr(C,cid+'_event')(s,side,{},r)
s['meta'].update(cta_active=True,cta_substep='allies',cta_sides_done=['guelph'],active_player='ghibelline',levy_step='3.5')
first=hashlib.sha256(json.dumps(s,sort_keys=True).encode()).hexdigest()
A._advance_cta(s)
print(first,hashlib.sha256(json.dumps(s,sort_keys=True).encode()).hexdigest())
'''
    root = Path(__file__).resolve().parents[1]
    values = [subprocess.check_output([sys.executable,'-S','-c',code], text=True, cwd=root,
                 env={**os.environ,'PYTHONHASHSEED':str(seed),'PYTHONPATH':str(root/'src')})
              for seed in (0,1,2,7,42)]
    assert len(set(values)) == 1

@pytest.mark.parametrize('side,lid,comune,card', [('guelph','firenze','firenze_comune','F9'),
                                               ('ghibelline','siena','siena_comune','S9')])
def test_extra_muster_can_levy_capability_for_commanders_own_comune(side,lid,comune,card):
    s = cta_state(side, 'comune')
    dispatch(s, act('cta_comune_setup', side))
    dispatch(s, act('cta_allies',side,mode='extra_muster',target_lord_id=lid))
    target = act('levy_muster_capability',side,lord_id=lid,target_lord_id=comune,
                 card_id=card,scope='this_lord')
    assert any(m['action']==target['action'] and m.get('args')==target['args'] for m in enumerate_legal(s))
    dispatch(s,target)
    assert card in s['lords'][comune]['capabilities']
    assert card not in s['lords'][lid]['capabilities']
    check_all_invariants(s)


def test_lordship_event_can_extend_extra_muster_without_granting_another_lord_a_turn():
    s = cta_state()
    s['decks']['guelph']['aow_deck'].remove('F11')
    s['decks']['guelph']['aow_held'].append('F11')
    # F11 requires Poggio Bonizio to be free of enemy Allegiance.
    s['locales']['Poggio Bonizio']['current_allegiance'] = []
    s['vp']['ghibelline'] -= 2
    dispatch(s,act('cta_allies',mode='extra_muster',target_lord_id='firenze'))
    for _ in range(A._lordship_limit(s,'firenze')):
        dispatch(s,act('levy_muster_transport',lord_id='firenze',kind='Cart'))
    option = next(m for m in enumerate_legal(s) if m['action']=='play_event'
                  and m['args']['card_id']=='F11'
                  and m['args']['effect_args']=={'mode':'lordship','target_lord_id':'firenze'})
    dispatch(s,option)
    used = s['lords']['firenze']['flags']['lordship_used']
    assert A._lordship_limit(s,'firenze') > used
    dispatch(s,act('levy_muster_transport',lord_id='firenze',kind='Cart'))
    dispatch(s,act('levy_muster_done'))
    assert not s['lords']['firenze']['flags'].get('lordship_bonus_segment')
    assert not s['meta'].get('cta_extra_muster_lord')
    check_all_invariants(s)


@pytest.mark.parametrize('side,comune', [('guelph','firenze_comune'),('ghibelline','siena_comune')])
def test_comune_menu_offers_all_unmustered_special_vassals_and_is_pure(side,comune):
    s = cta_state(side,'comune')
    before = deepcopy(s)
    moves = enumerate_legal(s)
    assert s==before
    setup=[m for m in moves if m['action']=='cta_comune_setup']
    assert len(setup)>1
    for m in setup:
        candidate=deepcopy(s)
        dispatch(candidate,m)
        check_all_invariants(candidate)
    all_names={v['name'] for v in SD.LORDS[s['lords'][comune]['name']]['vassals'] if v.get('special')}
    assert any(set(m['args'].get('muster_special_vassals',[]))==all_names for m in setup)


def test_captured_carroccio_cannot_be_regenerated_by_a_later_call_to_arms():
    s = cta_state('ghibelline','comune')
    s['captured_carroccio_for_side']={'guelph':1}
    dispatch(s,act('cta_comune_setup','ghibelline'))
    c=s['lords']['siena_comune']
    assert not any(v['name']=='Carroccio' and v['on_mat'] for v in c['vassals'])
    assert any('Terzo' in v['name'] and v['on_mat'] for v in c['vassals'])
    s['meta']['cta_substep']='comune'
    reject_unchanged(s,act('cta_comune_setup','ghibelline',muster_special_vassals=['Carroccio']))
    A._disband_at_service_limit(s,'siena',s['meta']['turn'])
    s['meta']['cta_substep']='commander_arms'
    dispatch(s,act('cta_commander_arms','ghibelline',mode='muster_only'))
    dispatch(s,act('cta_comune_setup','ghibelline'))
    assert not any(v['name']=='Carroccio' for v in s['lords']['siena_comune']['vassals'])
    check_all_invariants(s)
