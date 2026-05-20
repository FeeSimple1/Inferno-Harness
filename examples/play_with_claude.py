"""Example: drive the Inferno harness with an LLM via the Anthropic SDK.

This wires `inferno.llm.play_with_callback` to Claude. It is intentionally
framework-thin: the callback builds a briefing + legal-moves list, calls
the model, parses one JSON action from the response, and returns it. The
harness handles retry + safe fallback so a malformed/illegal suggestion
never deadlocks the game.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python examples/play_with_claude.py --scenario A --seed 42 \
        --model claude-sonnet-4-6 --max-actions 400

If the SDK or API key is unavailable, the script falls back to a
deterministic 'first legal move' stub callback so the example is still
runnable (and CI-testable) without network access. Pass --stub to force
the stub.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from inferno.actions import dispatch  # noqa: E402
from inferno.legal_moves import enumerate_legal  # noqa: E402
from inferno.llm import (  # noqa: E402
    build_briefing,
    build_self_critique_prompt,
    play_with_callback,
)
from inferno.scenarios import load_scenario  # noqa: E402


SYSTEM_PROMPT = """\
You are playing Inferno (GMT Games, Levy & Campaign Vol. III) as {side}.
You are a calculating medieval Italian commander.

Each turn you receive:
  (a) A briefing of the current game state from your perspective.
      Opposing-side secrets are redacted.
  (b) A JSON array of legal moves. Every listed move is currently legal.
      You MUST respond with EXACTLY ONE of these moves verbatim — copy its
      "action" and "args" fields. Do not invent actions or args.

Respond with a single JSON object and nothing else (no prose, no fences).

Strategic priors (advisory):
  - Firenze and Siena are the Leading Cities; capturing either is often
    the winning theme.
  - Forage at Friendly Strongholds is automatic; Forage elsewhere is
    seasonal (none in Winter outside friendly).
  - Sail (Pisa only, non-Winter) is the fastest map traversal.
  - Sieges and any Battle/Storm end the current Command card.
  - Treachery cards enable Revolt/Bribe — high upside but Coin-intensive.
If unsure, prefer a move that cleanly ends the current step
(*_done / cmd_pass / plan_add_card PASS / *_skip).
"""


def make_claude_callback(model: str):
    """Returns a callback(state, legal_moves) -> action dict using Claude."""
    import anthropic  # imported lazily so --stub path needs no SDK
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

    def callback(state, legal_moves):
        side = state["meta"]["active_player"]
        briefing = build_briefing(state, side, hidden_mats=state["meta"].get("hidden_mats", False))
        user = (
            f"{briefing}\n\nLegal moves (choose exactly one, return its JSON):\n"
            f"{json.dumps(legal_moves, indent=2, ensure_ascii=False)}"
        )
        resp = client.messages.create(
            model=model,
            max_tokens=400,
            system=SYSTEM_PROMPT.format(side=side),
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        return _parse_action(text)

    return callback


def make_stub_callback():
    """Deterministic 'first non-placeholder legal move' callback — no network."""
    def callback(state, legal_moves):
        for m in legal_moves:
            if not m.get("action", "").startswith("<"):
                action = {"action": m["action"], "side": m["side"]}
                if "args" in m:
                    action["args"] = m["args"]
                return action
        return {"action": "<none>", "side": state["meta"]["active_player"]}
    return callback


def _parse_action(text: str) -> dict:
    """Extract the first JSON object from a model response."""
    text = text.strip()
    # Strip code fences if present
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    # Find first {...} block
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object in response: {text[:200]!r}")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError(f"Unbalanced JSON in response: {text[:200]!r}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="A")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--max-actions", type=int, default=400)
    parser.add_argument("--stub", action="store_true",
                        help="Use the deterministic stub callback (no network).")
    parser.add_argument("--critique", action="store_true",
                        help="Print a post-game self-critique prompt at the end.")
    args = parser.parse_args()

    use_stub = args.stub or not os.environ.get("ANTHROPIC_API_KEY")
    try:
        callback = make_stub_callback() if use_stub else make_claude_callback(args.model)
    except ImportError:
        print("anthropic SDK not installed — falling back to stub callback.")
        use_stub = True
        callback = make_stub_callback()

    print(f"Playing scenario {args.scenario} (seed {args.seed}); "
          f"{'STUB' if use_stub else 'Claude ' + args.model}")
    s = load_scenario(args.scenario, seed=args.seed)
    fallbacks = 0
    for i in range(args.max_actions):
        if s["meta"].get("phase") == "victory":
            break
        result = play_with_callback(s, callback, max_strikes=3)
        if result.fallback:
            fallbacks += 1

    winner = s["meta"].get("winner")
    print(f"Terminal: phase={s['meta'].get('phase')} winner={winner} "
          f"VP G={s['vp'].get('guelph')} H={s['vp'].get('ghibelline')} "
          f"fallbacks={fallbacks}")

    if args.critique:
        print("\n--- Self-critique prompt (feed back to the model) ---\n")
        print(build_self_critique_prompt(s, "guelph"))


if __name__ == "__main__":
    main()
