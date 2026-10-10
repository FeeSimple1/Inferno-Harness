"""Rules 4.1.1: findings from actual Scenario A play, not random smoke."""
from copy import deepcopy
import pytest
from inferno.actions import dispatch, IllegalAction
from inferno.scenarios import load_scenario
from inferno.legal_moves import enumerate_legal
from inferno.llm.briefing import build_briefing


def plan(side):
    state = load_scenario('A', seed=42)
    state['meta'].update(phase='campaign', campaign_step='plan', levy_step=None,
                         active_player=side)
    return state


@pytest.mark.parametrize('side,lord', [('guelph','arezzo'),('ghibelline','siena')])
def test_three_command_copies_are_offered_and_accepted_but_fourth_is_atomic_rejection(side,lord):
    state = plan(side)
    cid = 'command_' + lord
    action = {'action':'plan_add_card','side':side,'args':{'card_id':cid}}
    for count in range(3):
        offered = [m for m in enumerate_legal(state) if m['action']=='plan_add_card'
                   and m.get('args',{}).get('card_id')==cid]
        assert len(offered)==1
        dispatch(state,action)
        assert state['plan_stacks'][side].count(cid)==count+1
    assert not any(m['action']=='plan_add_card' and m.get('args',{}).get('card_id')==cid
                   for m in enumerate_legal(state))
    before=deepcopy(state)
    with pytest.raises(IllegalAction) as error:
        dispatch(state,action)
    assert error.value.code=='CARD_NOT_AVAILABLE'
    assert state==before
    dispatch(state,{'action':'plan_add_card','side':side,'args':{'card_id':'PASS'}})
    dispatch(state,{'action':'plan_done','side':side})


def test_treachery_still_has_only_one_copy():
    state=plan('guelph');cid='treachery_arezzo'
    state['decks']['guelph']['command_deck'].append(cid)
    action={'action':'plan_add_card','side':'guelph','args':{'card_id':cid}}
    dispatch(state,action)
    before=deepcopy(state)
    with pytest.raises(IllegalAction) as error: dispatch(state,action)
    assert error.value.code=='TREACHERY_NOT_AVAILABLE'
    assert state==before


def test_opposing_allegiance_markers_are_distinguishable_in_briefing():
    text=build_briefing(load_scenario('A',seed=42),'guelph')
    assert 'Cortona: 1 Ghibelline+1 Ghibelline' in text
    assert 'Montalcino: 1 Guelph+1 Guelph' in text
