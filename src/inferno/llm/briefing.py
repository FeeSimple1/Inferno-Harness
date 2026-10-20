"""Structured, loss-aware briefings and focused, versioned information access.

The character budget is a SOFT target. Essential sections are always emitted in
full. Only whole optional sections can be deferred, with explicit retrieval
instructions. Full player-visible records (including unknown future fields) are
available from focused pages or the snapshot endpoint. No raw string slicing.
"""
from __future__ import annotations

import ast
import copy
from functools import lru_cache
from importlib.resources import files
import inspect
import json
import textwrap
from typing import Any

from ..actions import IllegalAction
from .. import card_data as cd, static_data as sd
from .menu import ActionCatalog
from .protocol import compact, page_records, query_position


@lru_cache(maxsize=1)
def _card_references() -> dict:
    return json.loads(files('inferno.data').joinpath('llm_card_reference.json').read_text(encoding='utf-8'))


@lru_cache(maxsize=None)
def _argument_reference(handler) -> dict:
    """Inspect argument grammar through helpers that actually receive args.

    No effects execute. Explicit forwarding matters for validation wrappers and
    mirrored Events; both top-level and helper documentation remain available.
    """
    fields = {}; documents = {}; visited = set()
    def walk(function, parameter='args'):
        key = (function, parameter)
        if key in visited:
            return
        visited.add(key)
        source = textwrap.dedent(inspect.getsource(function))
        tree = ast.parse(source)
        documentation = inspect.getdoc(function)
        if documentation:
            documents[function.__name__] = documentation
        namespace = function.__globals__
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == parameter
                    and node.func.attr in ('get', 'pop') and node.args
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                key = node.args[0].value
                default = None
                if len(node.args) > 1:
                    try:
                        default = ast.literal_eval(node.args[1])
                    except (ValueError, TypeError):
                        default = '<context-dependent default>'
                fields.setdefault(key, {'default': default})
            elif (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                  and node.value.id == parameter and isinstance(node.slice, ast.Constant)
                  and isinstance(node.slice.value, str)):
                fields.setdefault(node.slice.value, {'required_by_handler': True})
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if (node.func.id == '_int_arg' and len(node.args) >= 2
                    and isinstance(node.args[0], ast.Name) and node.args[0].id == parameter
                    and isinstance(node.args[1], ast.Constant)):
                fields.setdefault(node.args[1].value, {}).update(type='integer')
            callee = namespace.get(node.func.id)
            if not inspect.isfunction(callee) or callee.__module__ != handler.__module__:
                continue
            parameters = list(inspect.signature(callee).parameters)
            for index, arg in enumerate(node.args):
                if isinstance(arg, ast.Name) and arg.id == parameter and index < len(parameters):
                    walk(callee, parameters[index])
            for kw in node.keywords:
                if isinstance(kw.value, ast.Name) and kw.value.id == parameter and kw.arg in parameters:
                    walk(callee, kw.arg)
    walk(handler)
    return {'argument_fields': dict(sorted(fields.items())), 'handler_documentation': documents}


@lru_cache(maxsize=None)
def _action_reference(name: str) -> dict:
    from ..actions import _HANDLERS
    handler = _HANDLERS.get(name)
    if handler is None:
        raise IllegalAction('UNKNOWN_ACTION', f'Unknown action reference {name!r}.')
    return {'action': name, **_argument_reference(handler),
            'parameter_policy': 'Defaults are examples, not limits on choice. Supply complete args to choose any legal handler parameters. Full referenced helper documentation is included. Dispatch validates requirements atomically.',
            'combat_parameters': {
                'scripted_decisions': [{'type': '<advertised type>', 'side': '<owner>', 'choice': '<complete legal option>'}],
                'post_battle_decisions': [{'type': '<advertised aftermath type>', 'side': '<owner>', 'choice': '<complete legal option>'}],
                'transport': 'Bulk scripts are trusted-operator inputs, not permission for one player to control another. Player mode exposes ALL the same elections through owner-bound DecisionView pages.',
                'live_choices': 'play_with_interface / selection_session expose synchronous decisions to their owner without automatic fallback.'}}


def information_sections(view: dict) -> dict[str, list[dict]]:
    """All dynamic visible fields belong to a named, inspectable section."""
    pending_keys = [k for k in view if k.startswith('pending') or k == 'aow_resolution']
    card_keys = [k for k in ('decks', 'capabilities_in_play', 'active_events', 'plan_stacks') if k in view]
    handled = {'meta', 'lords', 'locales', 'calendar', 'history', '_filtered_for', '_hidden_mats'} | set(pending_keys + card_keys)
    sections = {
        'context': [{'key': 'meta', 'value': view.get('meta', {})}],
        'pending': [{'key': k, 'value': view[k]} for k in sorted(pending_keys)],
        'lords': [{'key': k, 'value': v} for k, v in sorted(view.get('lords', {}).items())],
        'board': [{'key': k, 'value': v, 'ways': [{'destination': n, 'way_type': w} for n, w in sorted(sd.adjacent_to(k))]}
                  for k, v in sorted(view.get('locales', {}).items())],
        'calendar': [{'key': k, 'value': v} for k, v in sorted(view.get('calendar', {}).items())],
        'cards': [{'key': k, 'value': view[k]} for k in card_keys],
        'effects': [{'key': k, 'value': view[k]} for k in sorted(set(view) - handled)],
        'history': [{'key': str(i), 'value': h} for i, h in enumerate(view.get('history', []), 1)],
    }
    return sections


def information_page(catalog: ActionCatalog, section: str, *, keys: list[str] | None = None,
                     cursor: str | None = None, page_size: int = 12,
                     max_chars: int | None = None) -> dict:
    if not isinstance(section, str):
        raise IllegalAction('BAD_SECTION', 'section must be a string.')
    if keys is not None and (not isinstance(keys, list) or not all(isinstance(k, str) for k in keys)):
        raise IllegalAction('BAD_FILTER', 'keys must be an array of complete record identifiers.')
    offset, filters = query_position(cursor, catalog.version, 'info:' + section,
                                     {'keys': keys} if keys is not None else ({} if cursor is None else None))
    if set(filters) - {'keys'}:
        raise IllegalAction('BAD_FILTER', 'Unknown information filter.')
    if 'keys' in filters and (not isinstance(filters['keys'], list)
                             or not all(isinstance(k, str) for k in filters['keys'])):
        raise IllegalAction('BAD_FILTER', 'Cursor keys must be an array of strings.')
    sections = information_sections(catalog.view)
    if section == 'index':
        records = [{'key': k, 'records': len(v), 'identifiers': [r['key'] for r in v]}
                   for k, v in sections.items()]
        records += [{'key': 'card_reference', 'records': 52},
                    {'key': 'action_reference', 'description': 'Handler argument grammar and complete documentation.'},
                    {'key': 'snapshot', 'description': 'The entire filtered state as one unsplit record.'}]
    elif section == 'snapshot':
        records = [{'key': 'snapshot', 'value': catalog.view}]
    elif section == 'card_reference':
        from .. import card_effects as ce
        records = [{'key': cid, 'value': {**cd.AOW_CARDS_BY_ID[cid],
                     'printed_reference': ref,
                     'capability_trigger': ce.CAPABILITY_TRIGGERS.get(cid, {}),
                     'event_parameters': _argument_reference(ce.EVENT_EFFECTS[cid])}}
                   for cid, ref in sorted(_card_references().items())]
    elif section == 'action_reference':
        from ..actions import _HANDLERS
        wanted = filters.get('keys', sorted(_HANDLERS))
        records = [{'key': name, 'value': _action_reference(name)} for name in wanted]
    elif section in sections:
        records = sections[section]
    else:
        raise IllegalAction('BAD_SECTION', f'Unknown section {section!r}; inspect index for available sections.')
    if 'keys' in filters:
        wanted = filters['keys']
        available = {r['key'] for r in records}
        if set(wanted) - available:
            raise IllegalAction('UNKNOWN_RECORD', 'Some requested records do not exist in this visible section.')
        records = [r for r in records if r['key'] in wanted]
    return page_records(records, catalog.version, 'info:' + section, filters, offset, page_size, max_chars)


def _service(view: dict, lid: str, lord: dict) -> str:
    cal = view.get('calendar', {})
    for edge in ('off_left_service', 'off_right_service'):
        if lid in cal.get(edge, []):
            return edge.replace('_', ' ')
    return str(lord.get('service_box'))


def _card_name(cid: str, half: str) -> str:
    return f"{cid}: {cd.AOW_CARDS_BY_ID.get(cid, {}).get(half + '_name', '')}".strip()


def _lord_summary(view: dict) -> str:
    lines = []
    for lid, l in sorted(view.get('lords', {}).items()):
        position = l.get('location') or (f"Calendar {l.get('calendar_box')}" if l.get('status') == 'on_calendar' else l.get('status'))
        line = f"{lid} ({l.get('name')}; {l.get('side')}): {position}; Service {_service(view, lid, l)}"
        if l.get('status') == 'mustered' or l.get('assets') or l.get('capabilities'):
            line += f"; Forces {compact(l.get('forces', {}))}; Assets {compact(l.get('assets', {}))}"
            if l.get('routed_units'):
                line += f"; Routed {compact(l['routed_units'])}"
            if l.get('capabilities'):
                line += '; Capabilities ' + ', '.join(_card_name(c, 'capability') for c in l['capabilities'])
            if l.get('flags'):
                line += '; Flags ' + compact(l['flags'])
        lines.append(line + '.')
    return '\n'.join(lines) or '(No Lords.)'


def _board_summary(view: dict) -> str:
    static = {'name', 'type', 'region', 'allegiance', 'port', 'leading_city', 'notes'}
    lines = []; deferred = []
    for name, loc in sorted(view.get('locales', {}).items()):
        dynamic = {k: v for k, v in loc.items() if k not in static and v not in (None, False, [], {})}
        if dynamic:
            # Keep the distinctive existing allegiance notation human-readable.
            alleg = loc.get('current_allegiance', [])
            label = '+'.join(f"{m['value']} {m['side'].title()}" for m in alleg)
            dynamic.pop('current_allegiance', None)
            desc = (label + ' ' if label else '') + compact(dynamic)
            lines.append(f"{name}: {desc}; printed {loc.get('allegiance')}, {loc.get('type')}.")
        else:
            deferred.append(name)
    if deferred:
        lines.append(f'{len(deferred)} additional locales have no dynamic markers or occupants; all static records and ways are available in board/index lookups.')
    return '\n'.join(lines) or '(No board locales.)'


def render_briefing(document: dict) -> str:
    out = []
    for section in document['sections']:
        out.append(f"-- {section['title']} [{section['status']}] --")
        out.append(section['text'])
        if section.get('retrieval'):
            r = section['retrieval']
            path = r['request'] + (('/' + r['section']) if 'section' in r else '')
            if r.get('keys'):
                path += ' keys=' + compact(r['keys'])
            out.append('Retrieve: ' + path + '.')
    if document['soft_target_exceeded']:
        out.append(f"Essential briefing exceeds the {document['target_chars']}-character soft target; it is returned intact.")
    return '\n'.join(out)


def _change_summary(value: Any, path: str = '') -> tuple[Any, list[dict]]:
    deferred = []
    if path == '/args':
        return copy.deepcopy(value), deferred
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            here = path + '/' + key
            if (key in ('rolls', 'rounds', 'decisions', 'decision_trace') and isinstance(item, list) and item
                    and (not path or '/battle' in path or '/storm' in path or '/sally' in path
                         or {'loser', 'winner'} & set(value))):
                deferred.append({'path': here, 'records': len(item)})
                # Decisions keep all elected choices, without repeating all
                # rejected options and position maps at each strike.
                if key in ('decisions', 'decision_trace'):
                    result[key] = [{k: d[k] for k in ('type', 'side', 'choice') if k in d}
                                   for d in item if isinstance(d, dict)]
                else:
                    result[key] = {'records_deferred': len(item)}
            else:
                result[key], more = _change_summary(item, here)
                deferred.extend(more)
        return result, deferred
    if isinstance(value, list):
        result = []
        for i, item in enumerate(value):
            short, more = _change_summary(item, path + '/' + str(i))
            result.append(short); deferred.extend(more)
        return result, deferred
    return value, deferred


def build_briefing_document(state: dict[str, Any], side: str, max_chars: int | None = 3500,
                            include_history_lines: int = 10, hidden_mats: bool | None = None,
                            *, catalog: ActionCatalog | None = None) -> dict:
    if max_chars is not None and (type(max_chars) is not int or max_chars < 1):
        raise IllegalAction('BAD_BUDGET', 'max_chars must be positive or null.')
    if type(include_history_lines) is not int or include_history_lines < 0:
        raise IllegalAction('BAD_HISTORY_COUNT', 'include_history_lines must be nonnegative.')
    catalog = catalog or ActionCatalog(state, side, hidden_mats)
    view = catalog.view; meta = view.get('meta', {}); cal = view.get('calendar', {})
    info = information_sections(view)
    sections = []
    def add(key, title, text, status='complete', retrieval=None, essential=True):
        sections.append({'id': key, 'title': title, 'status': status, 'essential': essential,
                         'text': text, **({'retrieval': retrieval} if retrieval else {})})
    add('situation', f'Inferno — {side.upper()}',
        f"Scenario {meta.get('scenario')}  Turn {meta.get('turn')}  Phase {meta.get('phase')}/{meta.get('levy_step') or meta.get('campaign_step')}\n"
        f"Acting player: {catalog.acting_player}; perspective: {side}; phase active player: {meta.get('active_player')}.\n"
        f"State version: {catalog.version}. VP {compact(view.get('vp', {}))}; Calendar Levy@{cal.get('levy_box')} End@{cal.get('end_box') or 'variable'}.\n"
        f"Current card: {view.get('current_card')}; Lord: {view.get('current_lord_id')}; actions remaining: {view.get('actions_remaining')}.\n"
        f"Additional phase context: {compact({k:v for k,v in meta.items() if k not in ('scenario','turn','phase','levy_step','campaign_step','active_player')})}")
    pending = [r for r in info['pending'] if r['value']]
    add('pending', 'Pending decisions — complete for their owner',
        '\n'.join(compact(r) for r in pending) if pending else '(None.)')
    overview = catalog.overview()
    kinds = []
    for cat in overview['categories']:
        detail = f"{cat['category']}: {cat['count']} entries"
        if cat['parameterized']:
            detail += f" ({cat['parameterized']} parameterized templates)"
        if cat['decision_channels']:
            detail += '; tactical choices ' + compact(cat['decision_channels'])
        kinds.append(detail + '.')
    add('actions', 'Available kinds of action — none ranked or omitted',
        '\n'.join(kinds) + ('\n' if kinds else '(No actions for this perspective.)\n') +
        'Page any category or all entries. Optional args and tactical choices are not limited to defaults; inspect action_reference.',
        retrieval={'request':'actions','page_size':12})
    if any(p.get('type') == 'approach_response' for p in view.get('pending', [])):
        add('reactions', 'Approach reaction window',
            'The attacker must also be offered their private reaction view before the defender commits a response. An opponent hand or reaction count is never included in this view.')
    held = view.get('decks', {}).get(side, {}).get('aow_held', [])
    add('held', 'Your Held Events — complete hand',
        '\n'.join(_card_name(cid, 'event') + '.' for cid in held) or '(None.)',
        retrieval={'request':'inspect','section':'card_reference','keys':held} if held else None)
    caps = view.get('capabilities_in_play', [])
    add('capabilities', 'Side-wide Capabilities and duration Events',
        '\n'.join(f"{c.get('side')}: {_card_name(c.get('id', ''), 'capability')}; {compact(c)}" for c in caps)
        + '\nDuration Events: ' + compact(view.get('active_events', {})),
        retrieval={'request':'inspect','section':'cards'})
    add('lords', 'Lords, Forces, resources, Service and mat Capabilities', _lord_summary(view), 'abbreviated',
        {'request':'inspect','section':'lords'})
    # Vassal readiness and Service are decision-relevant, not optional prose.
    vassals = []
    for lid, l in sorted(view.get('lords', {}).items()):
        if l.get('status') != 'mustered':
            continue
        groups = {}
        for public in l.get('public_vassal_service', []):
            vassals.append(f"{lid}: {public['name']} — public Service={public['service_box']}.")
        for v in l.get('vassals', []):
            if '<hidden_vassal_count>' in v:
                vassals.append(lid + ': ' + compact(v))
                continue
            key = (v.get('on_mat'), v.get('ready'), v.get('service_box'))
            groups.setdefault(key, []).append(v.get('name'))
        for (on_mat, ready, service), names in groups.items():
            vassals.append(f"{lid}: {', '.join(names)} — on_mat={on_mat}, ready={ready}, Service={service}.")
    add('vassals', 'Vassal readiness and Service', '\n'.join(vassals) or '(None.)', 'abbreviated',
        {'request':'inspect','section':'lords'})
    add('board', 'Board changes and positions', _board_summary(view), 'abbreviated',
        {'request':'inspect','section':'board'})
    extras = [r for r in info['effects'] if r['key'] not in ('vp','current_card','current_lord_id','actions_remaining') and r['value'] not in (None, False, [], {})]
    add('effects', 'Other live conditions and bookkeeping', '\n'.join(compact(r) for r in extras) or '(None.)',
        retrieval={'request':'inspect','section':'effects'})
    history = view.get('history', [])
    change, deferred_traces = _change_summary(history[-1]) if history else (None, [])
    add('changes', 'Most recent accepted action and changes',
        (compact({'revision': len(history), 'action': change})
         + ('\nDetailed dice, round traces and decision options deferred: ' + compact(deferred_traces)
            if deferred_traces else '')) if history else '(Initial position.)',
        status='abbreviated' if deferred_traces else 'complete',
        retrieval={'request':'inspect','section':'history','keys':[str(len(history))]} if history else None)
    # Entire old history records are optional; the latest changes above never are.
    n = min(max(include_history_lines - 1, 0), max(len(history) - 1, 0))
    older = info['history'][-(n+1):-1] if n else []
    older_text = '\n'.join(compact(r) for r in older)
    current_chars = sum(len(s['text']) for s in sections)
    if older and (max_chars is None or current_chars + len(older_text) < max_chars):
        add('recent_history', 'Earlier recent actions', older_text, essential=False)
    else:
        add('recent_history', 'Earlier history',
            f"{max(len(history)-1,0)} earlier complete records deferred. No history record was cut; inspect history to retrieve any or all pages.",
            'deferred', {'request':'inspect','section':'history'}, essential=False)
    add('access', 'Abbreviations and focused access',
        'Static ratings, seats, Vassal forces, map ways and notes are abbreviated above. Inspect index for every full visible section; focus with keys, or page all. snapshot returns the complete filtered state. History uses 1-based record keys. No lookup limit.',
        retrieval={'request':'inspect','section':'index'})
    document = {'state_version': catalog.version, 'perspective':side,
                'acting_player':catalog.acting_player, 'target_chars':max_chars,
                'sections':sections, 'soft_target_exceeded':False}
    text = render_briefing(document)
    document['soft_target_exceeded'] = max_chars is not None and len(text) > max_chars
    document['returned_chars'] = len(render_briefing(document))
    return document


def build_briefing(state: dict[str, Any], side: str, max_chars: int | None = 3500,
                   include_history_lines: int = 10, hidden_mats: bool | None = None) -> str:
    return render_briefing(build_briefing_document(state, side, max_chars,
                            include_history_lines, hidden_mats))
