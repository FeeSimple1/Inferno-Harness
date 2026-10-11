"""Regressions for F-LONG-01..08, including the actual saved failure positions."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from inferno import actions as A, card_effects as CE, static_data as SD
from inferno.flow import advance_to_next_side_or_step
from inferno.invariants import check_all_invariants
from inferno.legal_moves import enumerate_legal
from inferno.rng import HarnessRNG
from inferno.scenarios import load_scenario

FIXTURES = Path(__file__).parent / 'fixtures' / 'long_scenario'


def saved(name):
    return json.loads((FIXTURES / name).read_text())


def act(name, side='guelph', **args):
    return {'action': name, 'side': side, 'args': args}


def cta(side='guelph', sub='allies'):
    s = load_scenario('F', seed=20261010)
    s['meta'].update(phase='levy', levy_step='3.5', active_player=side,
                     cta_active=True, cta_substep=sub, cta_sides_done=[])
    return s


def move_fixture(s, lid, dest):
    for loc in s['locales'].values():
        loc['lords_present'] = [x for x in loc['lords_present'] if x != lid]
    A._place_cylinder(s, lid, None)
    s['lords'][lid].update(status='mustered', location=dest)
    s['locales'][dest]['lords_present'].append(lid)


def rejected_unchanged(s, action, code=None):
    before = deepcopy(s)
    with pytest.raises(A.IllegalAction) as exc:
        A.dispatch(s, action)
    if code:
        assert exc.value.code == code
    assert s == before


# F-LONG-01: actual saved position, but choose a Lord eligible under 3.4.
def test_actual_allies_extra_muster_is_playable_by_eligible_commander():
    s = saved('before_105_cta_allies.json')
    rejected_unchanged(s, act('cta_allies', mode='extra_muster', target_lord_id='arezzo'),
                       'MUSTER_NOT_ELIGIBLE')  # Cortona is Enemy aligned.
    choices = enumerate_legal(s)
    action = act('cta_allies', mode='extra_muster', target_lord_id='firenze')
    assert any(m['action'] == action['action'] and m['args'] == action['args'] for m in choices)
    A.dispatch(s, action)
    assert s['meta']['active_player'] == 'guelph'
    assert s['meta']['cta_substep'] == 'allies'
    assert s['meta']['cta_extra_muster_lord'] == 'firenze'
    cart = s['lords']['firenze']['assets'].get('Cart', 0)
    limit = A._lordship_limit(s, 'firenze')
    for _ in range(limit):
        action = act('levy_muster_transport', lord_id='firenze', kind='Cart')
        assert any(m['action'] == action['action'] and m.get('args') == action['args']
                   for m in enumerate_legal(s))
        A.dispatch(s, action)
    assert s['lords']['firenze']['assets']['Cart'] == cart + limit
    rejected_unchanged(s, action, 'LORDSHIP_EXHAUSTED')
    A.dispatch(s, act('levy_muster_done'))
    assert s['meta']['active_player'] == 'ghibelline'
    assert s['meta']['cta_substep'] == 'gather'
    assert not s['meta'].get('cta_extra_muster_lord')
    check_all_invariants(s)


@pytest.mark.parametrize('side,lid', [('guelph', 'firenze'), ('ghibelline', 'siena')])
def test_extra_muster_survives_save_load_and_can_end_early(side, lid):
    s = cta(side)
    s['lords'][lid]['flags'].update(lordship_used=99, just_mustered_this_segment=True)
    A.dispatch(s, act('cta_allies', side, mode='extra_muster', target_lord_id=lid))
    assert not s['lords'][lid]['flags'].get('just_mustered_this_segment')
    restored = json.loads(json.dumps(s))
    action = act('levy_muster_transport', side, lord_id=lid, kind='Cart')
    assert A.dispatch(s, action) == A.dispatch(restored, action)
    assert s == restored
    A.dispatch(s, act('levy_muster_done', side))
    assert not s['meta'].get('cta_extra_muster_lord')
    check_all_invariants(s)


@pytest.mark.parametrize('name,kwargs,code', [
    ('cta_allies', {'mode': 'extra_muster', 'target_lord_id': 'arezzo'}, 'CTA_MUSTER_ACTIVE'),
    ('cta_allies', {'mode': 'auto_muster', 'target_lord_id': 'guido_guerra'}, 'CTA_MUSTER_ACTIVE'),
    ('levy_cta_declare', {}, 'CTA_ALREADY_ACTIVE'),
    ('levy_cta_skip', {}, 'CTA_ALREADY_ACTIVE'),
    ('levy_muster_transport', {'lord_id': 'arezzo', 'kind': 'Cart'}, 'CTA_MUSTER_LORD'),
    ('levy_muster_capability', {'lord_id': 'arezzo', 'card_id': 'F6'}, 'CTA_MUSTER_LORD'),
    ('levy_muster_vassal', {'lord_id': 'arezzo', 'vassal': 'Altopascio'}, 'CTA_MUSTER_LORD'),
    ('levy_muster_lord', {'muster_lord_id': 'arezzo', 'target_lord_id': 'guido_guerra'}, 'CTA_MUSTER_LORD'),
])
def test_extra_muster_cannot_be_reselected_or_spent_by_another_lord(name, kwargs, code):
    s = cta()
    A.dispatch(s, act('cta_allies', mode='extra_muster', target_lord_id='firenze'))
    rejected_unchanged(s, act(name, **kwargs), code)
    before = deepcopy(s)
    moves = enumerate_legal(s)
    assert s == before
    for m in moves:
        if m['action'].startswith('levy_muster_') and m['action'] != 'levy_muster_done':
            assert m['args'].get('lord_id', m['args'].get('muster_lord_id')) == 'firenze'
            A.dispatch(deepcopy(s), m)


def test_extra_segment_allows_all_four_muster_action_kinds():
    s = cta()
    A._place_cylinder(s, 'guido_guerra', 1)
    A.dispatch(s, act('cta_allies', mode='extra_muster', target_lord_id='firenze'))
    kinds = {m['action'] for m in enumerate_legal(s)}
    assert {'levy_muster_lord', 'levy_muster_vassal', 'levy_muster_transport',
            'levy_muster_capability', 'levy_muster_done'} <= kinds
    for m in enumerate_legal(s):
        if m['action'].startswith('levy_muster_'):
            A.dispatch(deepcopy(s), m)


def test_extra_segment_never_allows_the_comune_as_an_independent_lord():
    s = cta(sub='comune')
    A.dispatch(s, act('cta_comune_setup'))
    rejected_unchanged(s, act('cta_allies', mode='extra_muster', target_lord_id='firenze_comune'),
                       'MUSTER_NOT_ELIGIBLE')


# F-LONG-02: exercise the lifecycle boundary that used to preserve old permission.
@pytest.mark.parametrize('sides', [['guelph'], ['ghibelline'], ['guelph', 'ghibelline']])
def test_war_permission_expires_at_levy_exit_and_next_turn(sides):
    s = cta('ghibelline')
    s['war_declared_this_levy'] = sides
    advance_to_next_side_or_step(s)
    assert s['meta']['phase'] == 'campaign'
    assert not s.get('war_declared_this_levy')
    # Even a loaded Campaign carrying the obsolete flag is cleaned by Reset.
    s['war_declared_this_levy'] = sides
    s['meta'].update(phase='campaign', campaign_step='end_campaign', active_player='guelph')
    A.dispatch(s, act('end_reset'))
    assert not s.get('war_declared_this_levy')
    assert s['meta']['turn'] == 2
    s['meta'].update(levy_step='3.5', cta_active=False)
    s['vp'] = {'guelph': 4.0, 'ghibelline': 4.0}
    rejected_unchanged(s, act('levy_cta_declare'), 'CTA_NOT_ELIGIBLE')
    assert not any(m['action'] == 'levy_cta_declare' for m in enumerate_legal(s))


@pytest.mark.parametrize('cid,side', [('F25','guelph'), ('F26','guelph'),
                                    ('S25','ghibelline'), ('S26','ghibelline')])
def test_current_war_event_still_allows_call_to_arms(cid, side):
    s = cta(side)
    s['meta']['cta_active'] = False
    getattr(CE, cid + '_event')(s, side, {}, HarnessRNG(4))
    assert A._cta_trigger_met(s, side) == (True, 'war_event')
    A.dispatch(s, act('levy_cta_declare', side))
    assert s['meta']['cta_active']


# F-LONG-03: no manual VP repair after the real Surprise/Sack action.
def test_actual_sack_score_matches_removed_allegiance_and_new_ruins():
    s = saved('before_242_sack_score.json')
    A.dispatch(s, act('play_event', card_id='F3'))
    assert not s['locales']['Poggio Bonizio']['current_allegiance']
    assert s['vp'] == {'guelph': 4.0, 'ghibelline': 2.5}
    assert A._compute_final_vp(s) == (4.0, 2.5)
    check_all_invariants(s)


# F-LONG-04: actual Gather, paired movement and prevention of the reverse split.
def test_actual_gather_moves_commander_and_comune_without_feeding():
    s = saved('turn4_cta_gather.json')
    before = deepcopy(s)
    action = act('cta_gather_march', lord_id='firenze', destination='Colle', way_type='track')
    moves = enumerate_legal(s)
    assert s == before
    assert any(m['action'] == action['action'] and m['args'] == action['args'] for m in moves)
    result = A.dispatch(s, action)
    assert result['state_changes']['group'] == ['firenze', 'firenze_comune']
    for lid in ('firenze', 'firenze_comune'):
        assert s['lords'][lid]['location'] == 'Colle'
        assert lid not in s['locales']['Casole']['lords_present']
        assert s['locales']['Colle']['lords_present'].count(lid) == 1
        assert s['lords'][lid]['assets'] == before['lords'][lid]['assets']
        assert s['lords'][lid]['flags'].get('moved_fought') == before['lords'][lid]['flags'].get('moved_fought')
    check_all_invariants(s)


@pytest.mark.parametrize('side,lid,comune,start,dest,way', [
    ('guelph','firenze','firenze_comune','Casole','Colle','track'),
    ('ghibelline','siena','siena_comune','Montalcino','Siena','track')])
def test_both_comuni_follow_and_neither_can_gather_independently(side,lid,comune,start,dest,way):
    s = cta(side, 'comune')
    A.dispatch(s, act('cta_comune_setup', side))
    for member in (lid,comune):
        move_fixture(s, member, start)
    s['meta']['cta_substep'] = 'gather'
    rejected_unchanged(s, act('cta_gather_march', side, lord_id=comune, destination=dest, way_type=way),
                       'COMUNE_CANNOT_LEAD')
    assert not any(m['action']=='cta_gather_march' and m['args']['lord_id']==comune
                   for m in enumerate_legal(s))
    A.dispatch(s, act('cta_gather_march', side, lord_id=lid, destination=dest, way_type=way))
    assert s['lords'][comune]['location'] == s['lords'][lid]['location'] == dest
    check_all_invariants(s)


def test_besieged_pair_cannot_gather_out():
    s = saved('turn4_cta_gather.json')
    loc = s['locales']['Casole']
    loc['siege'] = [{'side':'ghibelline', 'color':'gold', 'count':1}]
    for lid in ('firenze','firenze_comune'):
        s['lords'][lid]['flags']['in_stronghold'] = True
    rejected_unchanged(s, act('cta_gather_march', lord_id='firenze', destination='Colle', way_type='track'),
                       'BESIEGED')
    assert not any(m['action']=='cta_gather_march' and m['args']['lord_id'] in ('firenze','firenze_comune')
                   for m in enumerate_legal(s))


# F-LONG-05: preserve damaged/spent mats; never sum a vassal's contribution twice.
def test_actual_repeated_comune_setup_preserves_the_entire_mat():
    s = saved('turn4_existing_comune.json')
    before = deepcopy(s['lords']['siena_comune'])
    result = A.dispatch(s, act('cta_comune_setup','ghibelline'))
    assert result['state_changes']['mustered_vassals'] == []
    assert s['lords']['siena_comune'] == before
    assert sum(before['forces'].values()) == 5
    assert before['assets']['Cart'] == 2
    check_all_invariants(s)


def test_repeating_existing_vassals_does_not_heal_casualties_or_restore_assets():
    s = saved('turn4_existing_comune.json')
    comune = s['lords']['siena_comune']
    unit = next(u for u,c in comune['forces'].items() if c)
    comune['forces'][unit] -= 1
    comune['assets']['Coin'] = 0
    names = [v['name'] for v in comune['vassals'] if v.get('on_mat')]
    before = deepcopy(comune)
    A.dispatch(s, act('cta_comune_setup','ghibelline',muster_special_vassals=names))
    assert s['lords']['siena_comune'] == before


def test_existing_comune_adds_only_the_new_special_vassal():
    s = saved('turn4_existing_comune.json')
    comune = s['lords']['siena_comune']
    new = next(v for v in comune['vassals'] if v.get('special') and not v.get('on_mat'))
    before = deepcopy(comune)
    old_names = [v['name'] for v in comune['vassals'] if v.get('on_mat')]
    result = A.dispatch(s, act('cta_comune_setup','ghibelline',muster_special_vassals=old_names+[new['name']]))
    assert result['state_changes']['mustered_vassals'] == [new['name']]
    assert comune['assets'] == before['assets']
    assert comune['capabilities'] == before['capabilities']
    for unit,count in comune['forces'].items():
        assert count == before['forces'].get(unit,0) + new['forces'].get(unit,0)
    assert sum(v['name']==new['name'] and v['on_mat'] for v in comune['vassals']) == 1
    check_all_invariants(s)


@pytest.mark.parametrize('names', [['Carroccio'], ['Not a vassal'], ['Carroccio','Carroccio'], 4, {}])
def test_invalid_fresh_comune_setup_is_atomic(names):
    s = cta(sub='comune')
    rejected_unchanged(s, act('cta_comune_setup',muster_special_vassals=names))


def test_captured_carroccio_stays_captured_after_new_setup():
    s = cta(sub='comune')
    s['captured_carroccio_for_side'] = {'ghibelline':1}
    rejected_unchanged(s, act('cta_comune_setup', muster_special_vassals=['Carroccio','Sixth of Porta San Piero']),
                       'CARROCCIO_CAPTURED')
    A.dispatch(s, act('cta_comune_setup'))
    assert not any(v['name']=='Carroccio' for v in s['lords']['firenze_comune']['vassals'])
    assert s['captured_carroccio_for_side'] == {'ghibelline':1}
    check_all_invariants(s)


# F-LONG-06: the real corruption sequence now works without state repair.
def test_actual_commander_recall_removes_comune_then_sets_up_once():
    s = saved('before_641_commander_recall.json')
    A.dispatch(s, act('cta_commander_arms',mode='disband_and_remuster'))
    comune = s['lords']['firenze_comune']
    assert comune['status'] == 'in_levy_pool' and comune['location'] is None
    assert not comune['forces'] and not comune['assets'] and not comune['vassals']
    assert not comune['capabilities'] and not comune.get('routed_units')
    assert not any('firenze_comune' in loc['lords_present'] for loc in s['locales'].values())
    check_all_invariants(s)
    A.dispatch(s, act('cta_comune_setup'))
    assert [name for name,loc in s['locales'].items() if 'firenze_comune' in loc['lords_present']] == ['Firenze']
    assert sum(comune['forces'].values()) == 5
    check_all_invariants(s)


@pytest.mark.parametrize('side,commander,comune,cap', [
    ('guelph','firenze','firenze_comune','F6'), ('ghibelline','siena','siena_comune','S6')])
@pytest.mark.parametrize('disband', ['_disband_at_service_limit','_disband_beyond_service_limit'])
def test_any_commander_disband_clears_attached_comune_once(side,commander,comune,cap,disband):
    s = cta(side, 'comune')
    A.dispatch(s, act('cta_comune_setup',side))
    s['decks'][side]['aow_deck'].remove(cap)
    s['lords'][comune]['capabilities'].append(cap)
    if disband == '_disband_at_service_limit':
        A._disband_at_service_limit(s, commander, 1)
    else:
        A._disband_beyond_service_limit(s, commander)
    assert s['lords'][comune]['status'] == 'in_levy_pool'
    assert s['lords'][comune]['location'] is None
    assert s['decks'][side]['aow_deck'].count(cap) == 1
    check_all_invariants(s)


# F-LONG-07: the max-turn decision comes before Repair/Waste, with or without End.
def test_actual_last_turn_ends_before_any_repair_or_waste():
    s = saved('secondary_before_1684_game_end.json')
    before = deepcopy(s)
    result = A.dispatch(s, act('end_game_check'))
    assert result['state_changes'] == {'game_ended':True,'winner':'ghibelline','vp_g':2.0,'vp_h':4.0}
    assert s['meta']['final_vp'] == {'guelph':2.0,'ghibelline':4.0}
    assert s['lords'] == before['lords'] and s['locales'] == before['locales']
    assert s['meta']['game_over'] and s['meta']['phase'] == 'victory'
    assert enumerate_legal(s) == []
    for name in ('end_repair','end_waste','end_reset'):
        rejected_unchanged(s,act(name),'WRONG_STEP')
    check_all_invariants(s)


@pytest.mark.parametrize('turn,end,ended', [(15,None,False),(16,None,True),(12,14,False),(13,14,True),(15,16,True)])
def test_maximum_and_earlier_end_marker_boundaries(turn,end,ended):
    s = saved('secondary_before_1684_game_end.json')
    s['meta']['turn'] = turn
    s['calendar']['levy_box'] = turn
    s['calendar']['end_box'] = end
    r = A.dispatch(s,act('end_game_check'))
    assert r['state_changes']['game_ended'] is ended
    assert s['meta']['game_over'] is ended
    if not ended:
        assert any(m['action']=='end_repair' for m in enumerate_legal(s))


# F-LONG-08: serialized state and results must match in genuinely fresh processes.
def test_war_and_cta_serialization_is_identical_across_process_hash_seeds():
    script = r'''
import json
from inferno.scenarios import load_scenario
from inferno import actions as A, card_effects as C
from inferno.rng import HarnessRNG
s = load_scenario('F', seed=20261010)
rng = HarnessRNG(5)
results = []
for cid,side in [('S25','ghibelline'),('F25','guelph'),('S26','ghibelline'),('F26','guelph')]:
    results.append(getattr(C, cid+'_event')(s,side,{},rng))
s['lords']['firenze']['assets']['Coin'] = 2
results.append(C.F23_event(s,'guelph',{'mode':'declare_cta','coin_sources':{'firenze':2}},rng))
assert s['war_declared_this_levy'] == ['ghibelline','guelph']
s['meta'].update(phase='levy',levy_step='3.5',active_player='ghibelline',cta_active=True,
                 cta_substep='allies',cta_sides_done=[])
A._advance_cta(s)
assert s['meta']['cta_sides_done'] == ['ghibelline']
print(json.dumps({'state':s,'results':results},sort_keys=True))
'''
    root = Path(__file__).resolve().parents[1]
    outputs = []
    for hash_seed in ('0','1','42'):
        env = {**os.environ,'PYTHONPATH':str(root/'src'),'PYTHONHASHSEED':hash_seed}
        outputs.append(subprocess.check_output([sys.executable,'-c',script],env=env,cwd=root,text=True,timeout=30))
    assert outputs[0] == outputs[1] == outputs[2]


def test_actual_mirrored_recall_sequence_remains_consistent_after_each_action():
    s = saved('before_641_commander_recall.json')
    sequence = [
        act('cta_commander_arms', mode='disband_and_remuster'),
        act('cta_comune_setup'), act('cta_step_skip'),
        act('cta_step_skip', 'ghibelline'),
        act('cta_commander_arms', 'ghibelline', mode='disband_and_remuster'),
        act('cta_comune_setup', 'ghibelline'), act('cta_step_skip', 'ghibelline'),
    ]
    for action in sequence:
        A.dispatch(s, action)
        check_all_invariants(s)
        for side in ('guelph','ghibelline'):
            lord = s['lords'][A.COMUNE_LORD[side]]
            if lord['status'] == 'mustered':
                assert lord['location'] == s['lords'][A.COMMANDER_LORD[side]]['location']
    assert s['meta']['phase'] == 'campaign'


def test_existing_comune_menu_offers_each_new_vassal_without_replenishment():
    s = saved('turn4_existing_comune.json')
    before = deepcopy(s)
    new_names = {v['name'] for v in s['lords']['siena_comune']['vassals']
                 if v.get('special') and not v.get('on_mat')}
    offered = enumerate_legal(s)
    assert s == before
    for name in new_names:
        assert any(m['action']=='cta_comune_setup' and m['args']=={'muster_special_vassals':[name]}
                   for m in offered)
    for m in offered:
        probe = deepcopy(s)
        A.dispatch(probe,m)
        check_all_invariants(probe)


def test_new_comune_menu_does_not_offer_overcapacity_setup():
    s = cta(sub='comune')
    for lid in ('firenze','arezzo','guido_guerra'):
        move_fixture(s,lid,'Firenze')
        s['lords'][lid]['flags']['in_stronghold'] = True
    s['locales']['Firenze']['siege'] = [{'side':'ghibelline','color':'gold','count':1}]
    rejected_unchanged(s,act('cta_comune_setup'),'STRONGHOLD_FULL')
    assert not any(m['action']=='cta_comune_setup' for m in enumerate_legal(s))


@pytest.mark.parametrize('side,commander,comune,cap', [
    ('guelph','firenze','firenze_comune','F6'),('ghibelline','siena','siena_comune','S6')])
def test_extra_muster_commander_can_levy_a_card_for_his_comune(side,commander,comune,cap):
    s = cta(side,'comune')
    A.dispatch(s,act('cta_comune_setup',side))
    A.dispatch(s,act('cta_allies',side,mode='extra_muster',target_lord_id=commander))
    a = act('levy_muster_capability',side,lord_id=commander,target_lord_id=comune,card_id=cap,scope='this_lord')
    assert any(m['action']==a['action'] and m.get('args')==a['args'] for m in enumerate_legal(s))
    A.dispatch(s,a)
    assert cap in s['lords'][comune]['capabilities']
    check_all_invariants(s)


def test_fully_routed_lord_retreats_then_rolls_losses_before_removal(monkeypatch):
    # A Lord routed out of the Array is not yet a 4.4.5 removal.  He first
    # Retreats/Withdraws, then rolls every Routed unit; remove him only if none
    # recover.  This saved endurance position gives Colle one recovery.
    s = saved('secondary_before_459_battle_removal.json')
    roll_contexts = []
    original_roll = HarnessRNG.roll
    def record_roll(rng, context):
        roll_contexts.append(context)
        return original_roll(rng, context)
    monkeypatch.setattr(HarnessRNG, 'roll', record_roll)
    result = A.dispatch(s, act('approach_response', 'ghibelline',
                             lord_id='giordano', choice='stand'))
    battle = result['state_changes']['battle_result']
    assert 'colle' in battle['routed_out_lords']
    assert 'colle' not in battle['removed_lords']
    assert [c for c in roll_contexts if c.startswith('loss_colle_')] == [
        'loss_colle_Militia', 'loss_colle_Armigieri', 'loss_colle_Men-at-Arms']
    assert battle['loss_results']['colle']['recovered'] == {'Men-at-Arms': 1}
    assert s['lords']['colle']['status'] == 'mustered'
    assert s['lords']['colle']['location'] == 'San Gimignano'
    assert s['lords']['colle']['forces'] == {'Men-at-Arms': 1}
    assert s['lords']['colle']['routed_units'] == {}
    check_all_invariants(s)
