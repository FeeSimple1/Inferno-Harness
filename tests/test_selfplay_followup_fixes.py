"""Regression cases for the remaining findings from the Scenario A game.

Surprise fixtures perform a real March; an unrelated siege is NOT a legal
substitute for the card's printed arrival window.
"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from inferno.actions import IllegalAction, dispatch, _march_preview
from inferno.battle import resolve_storm
from inferno.invariants import check_all_invariants
from inferno.legal_moves import enumerate_legal
from inferno.llm.briefing import build_briefing
from inferno.scenarios import load_scenario


def relocate(s, lid, dest):
    lord = s['lords'][lid]
    for loc in s['locales'].values():
        if lid in loc.get('lords_present', []):
            loc['lords_present'].remove(lid)
    lord.update(status='mustered', location=dest)
    s['locales'][dest]['lords_present'].append(lid)


def hold(s, side, cid):
    deck = s['decks'][side]
    for zone in ('aow_deck', 'aow_discard', 'aow_held'):
        while cid in deck[zone]:
            deck[zone].remove(cid)
    deck['aow_held'].append(cid)


def active(s, side, lid, actions=2):
    s['meta'].update(phase='campaign', campaign_step='command_phase', levy_step=None, active_player=side)
    s.update(current_lord_id=lid, current_card='command_' + lid, actions_remaining=actions,
             card_actions_started=False, card_action_consumed_by_entire_card=False)


def arrive(side='guelph', *, actions=2, seed=42):
    s = load_scenario('A', seed=seed)
    lid, dest, way, cid = ('arezzo', 'Cortona', 'road', 'F3') if side == 'guelph' else ('siena', 'Montalcino', 'track', 'S3')
    if side == 'guelph':
        relocate(s, lid, 'Castiglione')
        s['lords'][lid]['flags']['first_march_used_this_card'] = True
    active(s, side, lid, actions)
    hold(s, side, cid)
    dispatch(s, {'action': 'cmd_march', 'side': side,
                 'args': {'lord_id': lid, 'destination': dest, 'way_type': way}})
    return s


def surprise_moves(s):
    return [m for m in enumerate_legal(s) if m['action'] == 'play_event'
            and m['args'].get('card_id') in ('F3', 'S3')]


def no_strikes(monkeypatch):
    # Hold both armies intact to isolate the printed round cap from die luck.
    monkeypatch.setattr('inferno.battle._resolve_storm_step', lambda *a, **kw: None)


@pytest.mark.parametrize('side,cid', [('guelph', 'F3'), ('ghibelline', 'S3')])
def test_first_arrival_offers_surprise_and_resolves_three_rounds(monkeypatch, side, cid):
    no_strikes(monkeypatch)
    s = arrive(side)
    before = deepcopy(s)
    moves = surprise_moves(s)
    assert len(moves) == 1
    assert s == before  # menu must not roll dice / consume the Event
    assert 'scripted_decisions' in moves[0]['accepts_decisions']
    result = dispatch(s, moves[0])
    storm = result['state_changes']['auto_storm']
    assert storm['rounds_played'] == 3
    assert storm['siege_count'] == 2
    assert storm['round_limit'] == 3
    assert cid not in s['decks'][side]['aow_held']
    assert cid in s['decks'][side]['aow_discard']
    assert not s.get('pending_besiege')
    assert not s.get('besiege_modifiers_pending')
    assert result['state_changes']['card_finished']


@pytest.mark.parametrize('side', ['guelph', 'ghibelline'])
def test_last_march_action_does_not_skip_arrival_or_feed_before_surprise(side):
    s = arrive(side, actions=1)
    assert s['actions_remaining'] == 0
    assert s['current_lord_id'] is not None
    assert not s.get('pending_fpd')
    assert surprise_moves(s)
    check_all_invariants(s)


@pytest.mark.parametrize('choice', ['besiege', 'bypass'])
def test_arrival_choice_is_free_at_zero_actions_and_keeps_unplayed_card(choice):
    s = arrive(actions=1)
    result = dispatch(s, {'action': 'besiege_or_bypass', 'side': 'guelph',
                          'args': {'lord_id': 'arezzo', 'choice': choice}})
    assert result['state_changes']['card_finished']
    assert 'F3' in s['decks']['guelph']['aow_held']
    assert not s.get('pending_besiege')


@pytest.mark.parametrize('action', ['cmd_end_card', 'cmd_pass', 'command_reveal', 'cmd_forage'])
def test_arrival_cannot_be_skipped_by_unrelated_actions(action):
    s = arrive()
    before = deepcopy(s)
    with pytest.raises(IllegalAction) as error:
        dispatch(s, {'action': action, 'side': 'guelph', 'args': {'lord_id': 'arezzo'}})
    assert error.value.code == 'PENDING_DECISION'
    assert s == before


def test_unrelated_siege_does_not_open_surprise_window():
    s = load_scenario('A', seed=42)
    active(s, 'guelph', 'arezzo')
    s['locales']['Firenze']['siege'] = [{'side': 'guelph', 'color': 'purple', 'count': 1}]
    before = deepcopy(s)
    assert not surprise_moves(s)
    with pytest.raises(IllegalAction) as error:
        dispatch(s, {'action': 'play_event', 'side': 'guelph', 'args': {'card_id': 'F3'}})
    assert error.value.code == 'NO_PLAY_WINDOW'
    assert s == before


@pytest.mark.parametrize('kind', ['commander_group', 'lieutenant', 'occupied_friendly', 'occupied_enemy'])
def test_surprise_rejects_groups_and_preoccupied_destinations(kind):
    s = load_scenario('A', seed=42)
    leader, follower = ('firenze', 'arezzo') if kind == 'commander_group' else ('arezzo', 'firenze')
    relocate(s, leader, 'Castiglione')
    active(s, 'guelph', leader)
    args = {'lord_id': leader, 'destination': 'Cortona', 'way_type': 'road'}
    if kind in ('commander_group', 'lieutenant'):
        relocate(s, follower, 'Castiglione')
        if kind == 'lieutenant':
            s['lords'][leader]['flags']['has_lower_lord'] = follower
            s['lords'][follower]['flags']['lower_lord_of'] = leader
        else:
            args['with_lords'] = [follower]
    else:
        relocate(s, 'siena' if kind == 'occupied_enemy' else follower, 'Cortona')
    dispatch(s, {'action': 'cmd_march', 'side': 'guelph', 'args': args})
    assert not surprise_moves(s)
    before = deepcopy(s)
    with pytest.raises(IllegalAction):
        dispatch(s, {'action': 'play_event', 'side': 'guelph', 'args': {'card_id': 'F3'}})
    assert s == before


def test_commander_with_comune_is_one_cylinder_and_may_surprise(monkeypatch):
    no_strikes(monkeypatch)
    s = load_scenario('A', seed=42)
    for lid in ('firenze', 'firenze_comune'):
        relocate(s, lid, 'Castiglione')
    s['lords']['firenze_comune']['forces'] = {'Armigieri': 1}
    active(s, 'guelph', 'firenze')
    result = dispatch(s, {'action': 'cmd_march', 'side': 'guelph',
                          'args': {'lord_id': 'firenze', 'destination': 'Cortona', 'way_type': 'road'}})
    assert set(result['state_changes']['group']) == {'firenze', 'firenze_comune'}
    assert len(surprise_moves(s)) == 1
    result = dispatch(s, surprise_moves(s)[0])
    assert 'firenze_comune' in result['state_changes']['auto_storm']['reserve_final']['attacker'] or any(
        'firenze_comune' in r['positions']['attacker'].values()
        for r in result['state_changes']['auto_storm']['rounds'])


def test_surprise_concession_stops_before_second_round(monkeypatch):
    no_strikes(monkeypatch)
    s = arrive()
    result = dispatch(s, {'action': 'play_event', 'side': 'guelph',
                          'args': {'card_id': 'F3', 'scripted_decisions': [
                              {'type': 'concede', 'side': 'attacker', 'choice': 'yes'}]}})
    assert result['state_changes']['auto_storm']['rounds_played'] == 1
    assert result['state_changes']['auto_storm']['conceded'] == 'attacker'


def test_normal_storm_still_has_two_round_limit(monkeypatch):
    no_strikes(monkeypatch)
    s = arrive()
    s.pop('pending_besiege')
    s['locales']['Cortona']['siege'] = [{'side': 'guelph', 'color': 'purple', 'count': 2}]
    result = resolve_storm(s, attackers=['arezzo'], defenders=[], active_id='arezzo', locale_name='Cortona')
    assert result['rounds_played'] == 2
    assert result['siege_count'] == 2


def test_surprise_uses_real_losses_and_is_deterministic_after_save_load():
    s = arrive(seed=42)
    restored = json.loads(json.dumps(s))
    action = surprise_moves(s)[0]
    r1, r2 = dispatch(s, action), dispatch(restored, action)
    assert s == restored and r1 == r2
    assert r1['state_changes']['auto_storm']['rounds_played'] == 3
    assert not s['lords']['arezzo']['routed_units']
    check_all_invariants(s)


def test_original_game_blocked_window_is_now_offered():
    actions = json.loads((Path(__file__).resolve().parents[1] / 'playtests/2026-10-09-scenario-a.actions.json').read_text())
    s = load_scenario('A', seed=42)
    for action in actions[:35]:
        dispatch(s, action)
        check_all_invariants(s)
    assert s['lords']['arezzo']['location'] == 'Cortona'
    assert len(surprise_moves(s)) == 1
    dispatch(s, surprise_moves(s)[0])
    check_all_invariants(s)


def grouped_state():
    s = load_scenario('A', seed=42)
    relocate(s, 'provenzano', 'Siena')
    active(s, 'ghibelline', 'siena')
    return s


def test_commander_group_march_is_offered_and_uses_shared_cart_preview():
    s = grouped_state()
    s['lords']['siena']['assets'].update(Cart=0, Provender=2, Loot=0)
    s['lords']['provenzano']['assets'].update(Cart=2, Provender=0, Loot=0)
    before = deepcopy(s)
    moves = [m for m in enumerate_legal(s) if m['action'] == 'cmd_march'
             and m['args'].get('destination') == 'Montalcino']
    assert moves and all('provenzano' in m['args'].get('with_lords', []) for m in moves)
    assert s == before
    for move in moves:
        snapshot = deepcopy(s)
        result = dispatch(snapshot, move)
        assert set(result['state_changes']['group']) == {'siena', 'provenzano'}
        assert result['state_changes']['cost'] == 1


def test_all_commander_subsets_are_offered_once_and_accepted():
    s = grouped_state()
    relocate(s, 'pisa', 'Siena')
    s['lords']['pisa']['assets'].update(Cart=2, Provender=0, Loot=0)
    moves = [m for m in enumerate_legal(s) if m['action'] == 'cmd_march'
             and m['args'].get('destination') == 'Montalcino']
    assert {tuple(m['args'].get('with_lords', [])) for m in moves} == {
        (), ('pisa',), ('provenzano',), ('pisa', 'provenzano')}
    assert len(moves) == 4
    for move in moves:
        dispatch(deepcopy(s), move)


def test_auto_lieutenant_pair_is_described_and_not_duplicated():
    s = load_scenario('A', seed=42)
    relocate(s, 'lucca', 'Arezzo')
    s['lords']['arezzo']['flags']['has_lower_lord'] = 'lucca'
    s['lords']['lucca']['flags']['lower_lord_of'] = 'arezzo'
    active(s, 'guelph', 'arezzo')
    moves = [m for m in enumerate_legal(s) if m['action'] == 'cmd_march'
             and m['args']['destination'] == 'Castiglione']
    assert len(moves) == 1
    assert 'lucca' in moves[0]['description']
    assert set(_march_preview(s, 'guelph', moves[0]['args'])['group']) == {'arezzo', 'lucca'}


def test_ordinary_lord_cannot_lead_and_besieged_members_are_not_offered():
    s = grouped_state()
    s['lords']['siena']['commander'] = False
    assert all(not m.get('args', {}).get('with_lords') for m in enumerate_legal(s) if m['action'] == 'cmd_march')
    s['lords']['siena']['commander'] = True
    s['lords']['provenzano']['flags']['in_stronghold'] = True
    s['locales']['Siena']['siege'] = [{'side': 'guelph', 'color': 'purple', 'count': 1}]
    assert all('provenzano' not in m.get('args', {}).get('with_lords', [])
               for m in enumerate_legal(s) if m['action'] == 'cmd_march')


def greek_fire_state():
    s = load_scenario('A', seed=42)
    s['meta']['levy_step'] = '3.2'
    hold(s, 'guelph', 'F7')
    relocate(s, 'siena', 'Montalcino')
    s['locales']['Montalcino']['siege'] = [{'side': 'ghibelline', 'color': 'gold', 'count': 3}]
    s['lords']['siena']['capabilities'] = ['S3', 'S5']
    s['lords']['siena']['forces'] = {'Armigieri': 2, 'Militia': 1}
    return s


def test_held_menu_includes_all_greek_fire_unit_and_capability_choices():
    s = greek_fire_state()
    before = deepcopy(s)
    moves = [m for m in enumerate_legal(s) if m['action'] == 'play_event' and m['args']['card_id'] == 'F7']
    assert len(moves) == 4
    assert s == before
    for move in moves:
        trial = deepcopy(s)
        effect = dispatch(trial, move)['state_changes']['effect']
        assert effect['removed_unit'] == move['args']['effect_args']['unit_to_remove']
        assert effect['discarded_capability'] == move['args']['effect_args']['capability_to_discard']


def test_held_menu_does_not_include_incomplete_targetless_plays():
    s = load_scenario('A', seed=42)
    s['meta']['levy_step'] = '3.2'
    hold(s, 'guelph', 'F7')
    assert not [m for m in enumerate_legal(s) if m['action'] == 'play_event' and m['args']['card_id'] == 'F7']


@pytest.mark.parametrize('side,cid,enemy_id', [('guelph', 'F3', 'S16'), ('ghibelline', 'S3', 'F16')])
@pytest.mark.parametrize('hidden_mats', [False, True])
def test_briefing_always_shows_own_hand_but_not_enemy_hand(side, cid, enemy_id, hidden_mats):
    s = load_scenario('F', seed=42)
    enemy = 'ghibelline' if side == 'guelph' else 'guelph'
    hold(s, side, cid); hold(s, enemy, enemy_id)
    s['history'] = [{'action': 'test', 'args': {'padding': 'x' * 1000}}] * 30
    before = deepcopy(s)
    text = build_briefing(s, side, hidden_mats=hidden_mats)
    assert f'{cid}: Surprise' in text
    assert enemy_id not in text
    assert 'Your Held Events' in text
    assert len(text) > 3500
    assert "soft target" in text
    assert "Acting player:" in text
    assert "Available kinds of action" in text
    assert s == before


def test_surprise_walls_and_siegeworks_use_two_not_three(monkeypatch):
    calls = []
    def inspect_step(*args, **kwargs):
        # _resolve_storm_step(..., garrison, walls_die, siegeworks_die, locale)
        calls.append((list(args[-3]), list(args[-2])))
    monkeypatch.setattr('inferno.battle._resolve_storm_step', inspect_step)
    s = arrive()
    dispatch(s, surprise_moves(s)[0])
    assert len(calls) == 12  # four Strike steps in each of three rounds
    assert set((tuple(w), tuple(sw)) for w, sw in calls) == {((1, 2), (1, 2))}


def test_rejected_surprise_combat_decision_is_atomic_and_retryable(monkeypatch):
    no_strikes(monkeypatch)
    s = arrive()
    before = deepcopy(s)
    with pytest.raises(IllegalAction) as error:
        dispatch(s, {'action': 'play_event', 'side': 'guelph', 'args': {
            'card_id': 'F3', 'scripted_decisions': [
                {'type': 'concede', 'side': 'attacker', 'choice': 'not-an-option'}]}})
    assert error.value.code == 'BAD_DECISION'
    assert s == before
    assert surprise_moves(s)
    dispatch(s, surprise_moves(s)[0])


@pytest.mark.parametrize('cid', ['F15', 'F18', 'F19', 'S13', 'S14'])
def test_held_duration_event_exists_in_one_card_zone_only(cid):
    from inferno.invariants import aow_card_total
    side = 'guelph' if cid.startswith('F') else 'ghibelline'
    s = load_scenario('A', seed=42)
    s['meta'].update(levy_step='3.2', active_player=side)
    hold(s, side, cid)
    assert aow_card_total(s, side) == 26
    dispatch(s, {'action': 'play_event', 'side': side, 'args': {'card_id': cid}})
    assert aow_card_total(s, side) == 26
    assert cid not in s['decks'][side]['aow_held']
    assert cid not in s['decks'][side]['aow_discard']


@pytest.mark.parametrize('cid', ['F11', 'F23'])
def test_held_treachery_menu_honors_selected_card_and_payments(cid):
    s = load_scenario('A', seed=42)
    s['meta']['levy_step'] = '3.4'
    s['locales']['Poggio Bonizio']['current_allegiance'] = []
    s['lords']['firenze']['assets']['Coin'] = 2
    s['lords']['arezzo']['assets']['Coin'] = 1
    hold(s, 'guelph', cid)
    before = deepcopy(s)
    moves = [m for m in enumerate_legal(s) if m['action'] == 'play_event'
             and m['args']['card_id'] == cid and m['args'].get('effect_args', {}).get('mode') == 'treachery']
    assert moves
    assert s == before
    cards = {m['args']['effect_args']['treachery_card'] for m in moves}
    assert cards == set(s['decks']['guelph']['treachery_set_aside'])
    for move in moves:
        trial = deepcopy(s)
        effect = dispatch(trial, move)['state_changes']['effect']
        assert effect['added'] == move['args']['effect_args']['treachery_card']
        if cid == 'F23':
            assert effect['paid'] == move['args']['effect_args']['coin_sources']
            assert sum(effect['paid'].values()) == 2


def test_menu_lists_own_held_cards_even_without_recent_draw_history():
    s = load_scenario('A', seed=42)
    assert s.get('history', []) == []
    text = build_briefing(s, 'guelph')
    assert 'F3: Surprise' in text


def test_original_game_grouped_march_is_available_from_the_menu():
    actions = json.loads((Path(__file__).resolve().parents[1] / 'playtests/2026-10-09-scenario-a.actions.json').read_text())
    s = load_scenario('A', seed=42)
    for action in actions[:39]:
        dispatch(s, action)
        check_all_invariants(s)
    actual = actions[39]
    moves = enumerate_legal(s)
    match = next(m for m in moves if m['action'] == actual['action']
                 and m.get('args') == actual['args'])
    dispatch(s, match)
    check_all_invariants(s)


@pytest.mark.parametrize('road_works,loot,prov,actions,expected', [
    (False, 1, 0, 1, None),
    (False, 1, 0, 2, 2),
    (False, 0, 3, 2, 2),
    (True, 1, 3, 1, 0),
    (True, 0, 5, 2, None),
])
def test_group_menu_tracks_laden_road_works_and_excess_provender(road_works, loot, prov, actions, expected):
    s = grouped_state()
    s['actions_remaining'] = actions
    s['lords']['siena']['assets'].update(Cart=0, Provender=0, Loot=0)
    s['lords']['provenzano']['assets'].update(Cart=2, Provender=prov, Loot=loot)
    if road_works:
        s['active_events'] = {'this_campaign': [{'id': 'S5', 'side': 'ghibelline'}]}
    moves = [m for m in enumerate_legal(s) if m['action'] == 'cmd_march'
             and m['args']['destination'] == 'Montalcino' and m['args'].get('with_lords') == ['provenzano']]
    if expected is None:
        assert not moves
    else:
        assert len(moves) == 1
        trial = deepcopy(s)
        result = dispatch(trial, moves[0])
        assert result['state_changes']['cost'] == expected


@pytest.mark.parametrize('side,lid,cid,args', [
    ('guelph', 'firenze', 'F11', {'mode': 'lordship', 'target_lord_id': 'firenze'}),
    ('ghibelline', 'siena', 'S21', {'mode': 'lordship', 'target': 'siena'}),
])
def test_held_lordship_bonus_can_be_spent_after_base_rating(side, lid, cid, args):
    s = load_scenario('A', seed=42)
    s['meta'].update(levy_step='3.4', active_player=side)
    s['locales']['Poggio Bonizio']['current_allegiance'] = []
    lord = s['lords'][lid]
    lord['flags']['lordship_used'] = lord['ratings']['L']
    hold(s, side, cid)
    dispatch(s, {'action': 'play_event', 'side': side, 'args': {'card_id': cid, 'effect_args': args}})
    action = {'action': 'levy_muster_transport', 'side': side, 'args': {'lord_id': lid, 'kind': 'Cart'}}
    for _ in range(3):
        assert any(m['action'] == action['action'] and m.get('args') == action['args'] for m in enumerate_legal(s))
        dispatch(s, action)
    assert not any(m['action'] == action['action'] and m.get('args') == action['args'] for m in enumerate_legal(s))
    before = deepcopy(s)
    with pytest.raises(IllegalAction) as error:
        dispatch(s, action)
    assert error.value.code == 'LORDSHIP_EXHAUSTED'
    assert s == before
    dispatch(s, {'action': 'levy_muster_done', 'side': side})
    assert not s['lords'][lid]['flags'].get('lordship_bonus_pending')


def test_persistent_lordship_capability_is_offered_and_not_hidden_by_base_limit():
    s = load_scenario('A', seed=42)
    s['meta']['levy_step'] = '3.4'
    s['capabilities_in_play'].append({'id': 'F22', 'side': 'guelph', 'scope': 'side_wide'})
    lord = s['lords']['firenze']
    lord['flags']['lordship_used'] = lord['ratings']['L']
    move = next(m for m in enumerate_legal(s) if m['action'] == 'levy_muster_transport'
                and m['args']['lord_id'] == 'firenze')
    dispatch(s, move)
    assert s['lords']['firenze']['flags']['lordship_used'] == lord['ratings']['L'] + 1
    assert not any(m['action'] == move['action'] and m.get('args') == move['args'] for m in enumerate_legal(s))


def test_held_and_this_levy_bonuses_stack_and_expire_at_their_own_boundaries():
    from inferno.actions import _lordship_limit
    from inferno.card_effects import apply_event_effect
    from inferno.flow import advance_to_next_side_or_step
    from inferno.rng import HarnessRNG
    s = load_scenario('A', seed=42)
    s['meta'].update(levy_step='3.4', active_player='ghibelline')
    apply_event_effect(s, 'S15', 'ghibelline', {'mode': 'lordship', 'target': 'siena'}, HarnessRNG(0))
    hold(s, 'ghibelline', 'S21')
    dispatch(s, {'action': 'play_event', 'side': 'ghibelline', 'args': {
        'card_id': 'S21', 'effect_args': {'mode': 'lordship', 'target': 'siena'}}})
    assert _lordship_limit(s, 'siena') == 8  # 3 printed + 2 this Levy + 3 this segment
    dispatch(s, {'action': 'levy_muster_done', 'side': 'ghibelline'})
    assert _lordship_limit(s, 'siena') == 5  # This-Levy grant survives into CtA
    s['meta']['active_player'] = 'ghibelline'
    advance_to_next_side_or_step(s)
    assert s['meta']['phase'] == 'campaign'
    assert _lordship_limit(s, 'siena') == 3


def test_robustness_scenario_c_seed_three_has_no_rejected_palette_move():
    import random
    s = load_scenario('C', seed=3, hidden_mats=True)
    policy = random.Random(3 * 131 + 5)
    for _ in range(250):
        if s['meta']['phase'] == 'victory':
            break
        moves = enumerate_legal(s)
        assert moves
        dispatch(s, policy.choice(moves))
        check_all_invariants(s)
    assert s['meta']['phase'] == 'victory'
