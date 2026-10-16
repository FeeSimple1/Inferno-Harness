"""Drive both factions through the complete, paginated player interface.

    python examples/play_with_claude.py --scenario A --seed 42 --stub
    # With the optional anthropic SDK and ANTHROPIC_API_KEY configured:
    python examples/play_with_claude.py --scenario F --seed 42 --model MODEL_ID

A callback receives a PlayerView (or synchronous combat DecisionView), not the
raw game state. It can make unlimited focused reads before choosing a stable
ID. Missing credentials never silently substitute a different player policy.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from inferno.actions import IllegalAction
from inferno.llm import PlayerView, play_with_interface, build_self_critique_prompt
from inferno.scenarios import load_scenario

SYSTEM_PROMPT = """You are playing Inferno as {side}.
You receive a complete essential briefing and an exhaustive action-category
index, not a strategic shortlist. The character target is soft. Sections marked
abbreviated or deferred remain available through focused reads. Your Held hand,
resources, Service and live conditions must inform your decisions.

Respond with exactly one JSON object per call. Either:
- Read: {{"request":"actions","category":"CATEGORY","page_size":12}}.
  Omit category for every choice. Filter by lord/card or exact dotted fields via
  where. A next_cursor means MORE choices exist: request that cursor to continue.
- Read: {{"request":"inspect","section":"SECTION","keys":["ID"]}}.
  Sections: index, lords, board, cards, calendar, pending, effects, context,
  history, card_reference, action_reference, snapshot. Omit keys for all records.
- Select: {{"action_id":"ID","state_version":"VERSION"}}.
  To fill a template or choose optional parameters, also include complete args.
  Read action_reference for accepted argument grammar; defaults are NOT the only
  legal choices. Read card_reference for full printed Event/Capability text.
- Only when can_yield is true: {{"yield":true,"state_version":"VERSION"}} to
  let the opponent continue instead of playing an optional reaction.

Any number of reads is allowed; queries do not consume game actions or dice.
Every page preserves whole descriptions and parameters, even if large. All
pages and IDs are bound to this position/perspective. Never reuse stale IDs.
Conditional templates check hidden target eligibility at submission; they do
not disclose opponents' secret mats. Combat elections likewise offer all options
on demand and identify the owner; do not replace them with automatic defaults.
"""


def _parse_action(text: str) -> dict:
    """Decode a complete JSON object, respecting quoted braces and escapes."""
    text = re.sub(r'^```(?:json)?|```$', '', text.strip(), flags=re.MULTILINE).strip()
    decoder = json.JSONDecoder()
    for i, char in enumerate(text):
        if char == '{':
            try:
                value, _ = decoder.raw_decode(text[i:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
    raise ValueError('Model response did not contain a complete JSON object; no action was applied.')


def make_claude_callback(model: str, *, response_tokens: int = 4096, meter: list | None = None):
    """callback(view) -> complete selection, with a JSON retrieval loop.

    A provider length stop raises, never parses or applies a partial choice.
    Increase response_tokens and resume the saved position if necessary.
    meter optionally records every request/response size, including lookups.
    """
    import anthropic
    client = anthropic.Anthropic()

    def callback(view):
        overview = json.dumps(view.overview(), ensure_ascii=False, separators=(',', ':'))
        messages = [{'role':'user', 'content':overview}]
        while True:
            response = client.messages.create(
                model=model, max_tokens=response_tokens,
                system=SYSTEM_PROMPT.format(side=view.side), messages=messages)
            text = ''.join(b.text for b in response.content if getattr(b,'type',None)=='text')
            if meter is not None:
                meter.append({'input_chars':len(json.dumps(messages,ensure_ascii=False)),
                              'output_chars':len(text),
                              'usage':response.usage.model_dump() if getattr(response,'usage',None) else None})
            if response.stop_reason == 'max_tokens':
                raise RuntimeError('Provider output limit reached. No partial selection was applied; increase --response-tokens and resume.')
            request = _parse_action(text)
            if 'request' not in request:
                # Validate envelope, ID and version before returning it.
                if request.get('yield') is not True:
                    view.resolve(request)
                return request
            try:
                answer = view.query(request)
            except IllegalAction as exc:
                answer = {'error':exc.code, 'message':str(exc), 'state_changed':False}
            messages.append({'role':'assistant','content':text})
            messages.append({'role':'user','content':json.dumps(answer,ensure_ascii=False,separators=(',',':'))})
    return callback


def make_stub_callback():
    """Explicit deterministic test policy using the SAME retrieval interface.

    This is not an LLM, not a recommendation, and not a restriction on the menu
    presented to real players. It scans pages in stable order and picks the first
    concrete choice. A parameter-only decision requires a human/model instead.
    """
    def callback(view):
        if view.can_yield:
            return {'yield':True,'state_version':view.version}
        request = {'request':'actions','page_size':12}
        while True:
            page = view.query(request)
            for entry in page['records']:
                if not entry['parameterized'] and not entry['move']['action'].startswith('<'):
                    return {'action_id':entry['action_id'],'state_version':view.version}
            if page['next_cursor'] is None:
                raise IllegalAction('PLAYER_CHOICE_REQUIRED','No concrete stub choice; fill the available parameterized template explicitly.')
            request = {'request':'actions','cursor':page['next_cursor'],'page_size':12}
    return callback


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--scenario',default='A')
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--model',default=os.environ.get('ANTHROPIC_MODEL'),help='Provider model ID; required for live play unless ANTHROPIC_MODEL is set.')
    parser.add_argument('--max-actions',type=int,default=400)
    parser.add_argument('--response-tokens',type=int,default=4096)
    parser.add_argument('--briefing-target',type=int,default=3500)
    parser.add_argument('--stub',action='store_true')
    parser.add_argument('--critique',action='store_true')
    parser.add_argument('--resume',type=Path)
    parser.add_argument('--save',type=Path,default=Path('inferno.state.json'))
    parser.add_argument('--metrics',type=Path)
    args=parser.parse_args(argv)
    if not args.stub and not os.environ.get('ANTHROPIC_API_KEY'):
        parser.error('Set ANTHROPIC_API_KEY, or explicitly use --stub for an offline test policy.')
    if not args.stub and not args.model:
        parser.error('Supply --model or ANTHROPIC_MODEL for live provider calls.')
    meter=[]
    try:
        callback=make_stub_callback() if args.stub else make_claude_callback(args.model,response_tokens=args.response_tokens,meter=meter)
    except ImportError:
        parser.error('Install the optional anthropic SDK, or explicitly use --stub.')
    state=json.loads(args.resume.read_text()) if args.resume else load_scenario(args.scenario,seed=args.seed)
    code=0
    try:
        for _ in range(args.max_actions):
            if state['meta'].get('phase')=='victory':
                break
            play_with_interface(state,callback,max_chars=args.briefing_target)
    except (IllegalAction,RuntimeError,ValueError) as exc:
        print(f'Play paused: {exc}',file=sys.stderr)
        code=1
    finally:
        args.save.write_text(json.dumps(state,ensure_ascii=False,indent=2))
        if args.metrics:
            args.metrics.write_text(json.dumps(meter,indent=2))
    print(f"phase={state['meta']['phase']} winner={state['meta'].get('winner')} VP={state['vp']}; saved {args.save}")
    if args.critique:
        print(build_self_critique_prompt(state,'guelph'))
    return code


if __name__=='__main__':
    raise SystemExit(main())
