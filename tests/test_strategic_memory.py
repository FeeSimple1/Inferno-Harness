"""Decision continuity must never change legality, dice, or opponent visibility."""
from __future__ import annotations

from copy import deepcopy
import json
import sys
from types import SimpleNamespace

import pytest

from inferno.actions import dispatch
from inferno.llm import PlayerView, StrategicMemory, play_with_interface
from inferno.scenarios import load_scenario
from examples.play_with_claude import make_claude_callback
from benchmarks.strategy_ab import trial


def _action(view):
    entry = next(e for e in view._catalog.entries
                 if not e['parameterized'] and not e['move']['action'].startswith('<'))
    return {'action_id': entry['action_id'], 'state_version': view.version}


class MockProvider:
    """No network: record exactly what one faction's model is allowed to see."""
    def __init__(self, *, stop='end_turn', override=None):
        self.prompts=[]
        self.system_prompts=[]
        self.stop=stop
        self.override=override
    def messages_create(self, **kwargs):
        overview=json.loads(kwargs['messages'][0]['content'])
        self.prompts.append(overview)
        self.system_prompts.append(kwargs['system'])
        choice=self.override(overview) if self.override else overview['selection']
        if choice.get('action_id') == '<ID from an action page>':
            raise AssertionError('Test must supply a concrete action ID.')
        return SimpleNamespace(stop_reason=self.stop,
                               content=[SimpleNamespace(type='text', text=json.dumps(choice))],
                               usage=None)


def _patch_provider(monkeypatch, provider):
    monkeypatch.setitem(sys.modules,'anthropic',
                        SimpleNamespace(Anthropic=lambda: SimpleNamespace(messages=SimpleNamespace(create=provider.messages_create))))


def test_journal_commit_is_atomic_and_never_mutates_the_authoritative_state():
    state=load_scenario('A',seed=42);before=deepcopy(state)
    j=StrategicMemory()
    j.stage('guelph','Pressure Cortona; protect Service.','v1')
    assert j.read('guelph')['note'] is None
    assert j.read('ghibelline')['note'] is None
    with pytest.raises(ValueError, match='uncommitted'):
        j.save(state)
    j.abort()
    assert j.read('guelph')['note'] is None
    j.stage('guelph','Pressure Cortona; protect Service.','v1')
    j.commit(state)
    assert state==before
    assert 'Pressure Cortona' in j.read('guelph')['note']
    assert j.read('ghibelline')['note'] is None
    assert j.read('guelph')['written_after_revision']==len(state['history'])
    j.stage('guelph','','v2');j.commit(state)
    assert j.read('guelph')['note'] is None


def test_note_not_sliced_even_if_longer_than_old_briefing_budget():
    s=load_scenario('A',seed=7);j=StrategicMemory()
    large='Conserve Service, ' * 400
    j.stage('guelph',large,'v');j.commit(s)
    assert j.read('guelph')['note']==large
    assert j.read('ghibelline')['note'] is None


def test_load_requires_exact_save_and_does_not_accept_foreign_or_future_notes():
    s=load_scenario('A',seed=42);j=StrategicMemory()
    j.stage('guelph','Defend Siena.','v');j.commit(s)
    saved=json.loads(json.dumps(j.save(s)))
    assert StrategicMemory.load(saved,deepcopy(s)).read('guelph')['note']=='Defend Siena.'
    t=deepcopy(s);t['vp']['guelph']+=.5
    with pytest.raises(ValueError,match='exact'):
        StrategicMemory.load(saved,t)
    t=deepcopy(s);t['meta']['rng_seed']+=1
    with pytest.raises(ValueError,match='exact'):
        StrategicMemory.load(saved,t)
    u=deepcopy(saved);u['notes']['guelph']['revision']=99
    with pytest.raises(ValueError, match='future'):
        StrategicMemory.load(u,s)
    u=deepcopy(saved);u['notes']['ghibelline']=u['notes']['guelph']
    # Correct state pairing permits multiple notes but never conflates them.
    assert StrategicMemory.load(u,s).read('ghibelline')['note']=='Defend Siena.'


def test_invalid_side_and_types_rejected_without_touching_state():
    j=StrategicMemory()
    for side in ('outsider',None,[], 'Guelph'):
        with pytest.raises((TypeError,ValueError)):
            j.stage(side,'x','v')
    with pytest.raises(ValueError): j.stage('guelph',['x'],'v')
    with pytest.raises(ValueError): j.stage('guelph','x',None)
    assert j.read('guelph')['note'] is None


def test_provider_note_is_host_metadata_only_and_effects_identical(monkeypatch):
    s=load_scenario('A',seed=42);t=deepcopy(s)
    v=PlayerView(s,'guelph')
    selection=_action(v)
    response=selection | {'strategy_note':'Approach Cortona cautiously.'}
    provider=MockProvider(override=lambda _:response)
    _patch_provider(monkeypatch,provider)
    memory=StrategicMemory()
    callback=make_claude_callback('mock',strategic_memory=memory)
    chosen=callback(v)
    assert chosen==selection
    assert memory.read('guelph')['note'] is None
    before=deepcopy(s)
    assert s==before
    accepted_action=v.resolve(chosen)
    actual=dispatch(s,accepted_action)
    expected=dispatch(t,accepted_action)
    memory.commit(s)
    assert s==t and actual==expected
    assert memory.read('guelph')['note']=='Approach Cortona cautiously.'
    assert not any('strategy_note' in str(h) for h in s['history'])
    assert 'prior_strategy' not in provider.prompts[0]
    assert 'strategy_note' in provider.system_prompts[0]


@pytest.mark.parametrize('hidden_mats',[False,True])
def test_private_strategic_intentions_not_sent_to_other_faction(monkeypatch,hidden_mats):
    s=load_scenario('A',seed=10,hidden_mats=hidden_mats)
    # The records contain secrets known ONLY to the faction that wrote them.
    j=StrategicMemory()
    j.stage('guelph','SECRET_GUELPH_PLAN','g-version');j.commit(s)
    j.stage('ghibelline','SECRET_GHIBELLINE_PLAN','h-version');j.commit(s)
    provider=MockProvider(override=lambda _: {'yield': True, 'state_version':'placeholder'})
    _patch_provider(monkeypatch,provider)
    callback=make_claude_callback('mock',strategic_memory=j)
    # Inject an invalid selection; the prompt is still captured and a failure
    # cannot commit notes or modify the engine position.
    for side in ('guelph','ghibelline'):
        with pytest.raises(ValueError):
            callback(PlayerView(s,side))
    g,h=provider.prompts
    assert g['prior_strategy']['note']=='SECRET_GUELPH_PLAN'
    assert h['prior_strategy']['note']=='SECRET_GHIBELLINE_PLAN'
    assert 'SECRET_GHIBELLINE_PLAN' not in json.dumps(g)
    assert 'SECRET_GUELPH_PLAN' not in json.dumps(h)


def test_failed_provider_response_and_bad_note_do_not_enter_notebook(monkeypatch):
    s=load_scenario('A',seed=4);v=PlayerView(s,'guelph');sel=_action(v)
    j=StrategicMemory()
    provider=MockProvider(stop='max_tokens',override=lambda _:sel|{'strategy_note':'BAD_UNCOMMITTED'})
    _patch_provider(monkeypatch,provider)
    cb=make_claude_callback('mock',strategic_memory=j)
    with pytest.raises(RuntimeError,match='output limit'):cb(v)
    assert j.read('guelph')['note'] is None
    provider.stop='end_turn';provider.override=lambda _:sel|{'strategy_note':['wrong type']}
    with pytest.raises(ValueError):cb(v)
    j.abort()
    assert j.read('guelph')['note'] is None


def test_direct_dispatch_and_model_selection_have_identical_mechanics():
    s=load_scenario('A',seed=11)
    t=deepcopy(s);v=PlayerView(s,'guelph');sel=_action(v)
    note=StrategicMemory()
    def choose(view):
        if view.side=='guelph':note.stage(view.side,'Maintain pressure.','v')
        return _action(view)
    accepted_action=v.resolve(sel)
    a=play_with_interface(s,choose)
    b=dispatch(t,accepted_action)
    note.commit(s)
    assert s==t and a.applied==b


def test_paired_stub_trial_stays_mechanically_identical_with_factions_swapped():
    a=trial('A',42,'guelph',200,stub=True,model=None)
    b=trial('A',42,'ghibelline',200,stub=True,model=None)
    assert a['status']==b['status']=='completed'
    assert a['vp']==b['vp'] and a['winner']==b['winner']
    assert a['accepted_actions']==b['accepted_actions']
    assert a['notebook_chars']==b['notebook_chars']==0


def test_stateless_ab_control_has_no_note_instruction_or_payload(monkeypatch):
    s=load_scenario('A',seed=42);v=PlayerView(s,'guelph');sel=_action(v)
    provider=MockProvider(override=lambda _:sel)
    _patch_provider(monkeypatch,provider)
    assert make_claude_callback('mock',strategic_memory=None)(v)==sel
    assert 'prior_strategy' not in provider.prompts[0]
    assert 'strategy_note' not in provider.system_prompts[0]
    assert 'strategy_note' not in str(provider.prompts[0])