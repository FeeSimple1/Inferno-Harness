"""Curated ~3 KB briefing builder.

Per CROSS_PROJECT_LESSONS §5: "Curated ~3 KB briefing beats dumping the
full rulebook into the system prompt. Game state, current phase, recent
history, and on-demand lookups for cards/strategy/rules references is
enough context for competent play."

build_briefing(state, side) returns a compact text summary suitable for
inclusion in an LLM system prompt. The LLM gets:
  - Scenario, turn, phase, side perspective
  - VP and Calendar bounds
  - Own Mustered Lords with Forces, Assets, Location
  - Enemy Lords visible on map (name, location, rough strength)
  - Locales with markers
  - Pending decisions owed by this side
  - Recent history (last N actions)
  - 5-10 relevant tactical priors from STRATEGY_DIGEST
"""

from __future__ import annotations

from typing import Any

from .. import static_data as sd
from .filter import hide_for_side


def build_briefing(state: dict[str, Any], side: str,
                   max_chars: int = 3500,
                   include_history_lines: int = 10,
                   hidden_mats: bool = False) -> str:
    """Build a ~3 KB briefing for `side` from a (presumed full) state."""
    filtered = hide_for_side(state, side, hidden_mats=hidden_mats)
    out: list[str] = []
    meta = filtered["meta"]
    out.append(f"=== Inferno Harness — side: {side.upper()} ===")
    out.append(f"Scenario {meta.get('scenario')}  Turn {meta.get('turn')}  "
               f"Phase {meta.get('phase')}"
               + (f"/{meta.get('levy_step')}" if meta.get('levy_step') else "")
               + (f"/{meta.get('campaign_step')}" if meta.get('campaign_step') else "")
               + f"  Active: {meta.get('active_player')}")
    out.append(f"VP  Guelph={filtered['vp'].get('guelph', 0)}  "
               f"Ghibelline={filtered['vp'].get('ghibelline', 0)}")
    cal = filtered["calendar"]
    out.append(f"Calendar  Levy@{cal.get('levy_box')}  "
               f"End@{cal.get('end_box') or 'variable'}")
    out.append("")

    # Own Mustered Lords with Forces/Assets
    out.append(f"-- {side.upper()} Mustered Lords --")
    own_count = 0
    for lid, lord in filtered["lords"].items():
        if lord.get("side") != side or lord.get("status") != "mustered":
            continue
        own_count += 1
        forces_str = _fmt_forces(lord.get("forces", {}))
        assets_str = _fmt_assets(lord.get("assets", {}))
        ratings = lord.get("ratings", {})
        lord_ratings = (f"F:{ratings.get('F','-')}/S:{ratings.get('S','-')}/"
                        f"L:{ratings.get('L','-')}/C:{ratings.get('C','-')}")
        loc = lord.get("location", "<none>")
        out.append(f"  {lord.get('name')} @ {loc}  [{lord_ratings}]")
        out.append(f"    Forces: {forces_str}")
        out.append(f"    Assets: {assets_str}")
        if lord.get("capabilities"):
            out.append(f"    Capabilities: {', '.join(lord['capabilities'])}")
    if own_count == 0:
        out.append("  (no Mustered Lords)")
    out.append("")

    # Enemy Lords on map (positions visible)
    enemy = "ghibelline" if side == "guelph" else "guelph"
    out.append(f"-- {enemy.upper()} Lords on Map --")
    enemy_count = 0
    for lid, lord in filtered["lords"].items():
        if lord.get("side") != enemy or lord.get("status") != "mustered":
            continue
        enemy_count += 1
        loc = lord.get("location", "<none>")
        # When hidden_mats is on, force_count is the only revealed strength
        force_total = sum(v for k, v in lord.get("forces", {}).items() if isinstance(v, int))
        out.append(f"  {lord.get('name')} @ {loc}  (~{force_total} units)")
    if enemy_count == 0:
        out.append("  (no enemy Lords on map)")
    out.append("")

    # Locales with markers
    out.append("-- Locales with markers --")
    marked = []
    for name, loc in filtered.get("locales", {}).items():
        bits = []
        if loc.get("current_allegiance"):
            bits.append("+".join(f"{m['value']}{m['side'][0].upper()}"
                                  for m in loc["current_allegiance"]))
        if loc.get("ravaged"):
            bits.append(f"Rav({loc['ravaged']})")
        if loc.get("ruins"):
            bits.append(f"Ruin({loc['ruins']})")
        if loc.get("siege"):
            bits.append("Siege:" + "+".join(f"{s.get('count',1)}{s['side'][0].upper()}"
                                              for s in loc["siege"]))
        if loc.get("bypass"):
            bits.append("Bypass")
        if bits:
            marked.append(f"  {name}: {' '.join(bits)}")
    if marked:
        out.extend(marked[:20])  # cap
    else:
        out.append("  (none)")
    out.append("")

    # Pending decisions owed by this side
    owed = [p for p in filtered.get("pending", []) if p.get("side") == side]
    if owed:
        out.append(f"-- Pending decisions owed by {side.upper()} --")
        for p in owed[:5]:
            out.append(f"  {p.get('type')}: options={p.get('options')}  info={p.get('info')}")
        out.append("")

    # Recent history
    history = filtered.get("history", [])
    if history:
        out.append(f"-- Recent actions (last {min(include_history_lines, len(history))}) --")
        for h in history[-include_history_lines:]:
            out.append(f"  [{h.get('side')}] {h.get('action')}  "
                       f"args={_truncate(str(h.get('args', {})), 60)}")
        out.append("")

    # Truncate if exceeded budget
    text = "\n".join(out)
    if len(text) > max_chars:
        text = text[: max_chars - 100] + "\n... [truncated to fit ~3 KB briefing budget]"
    return text


def _fmt_forces(forces: dict[str, int]) -> str:
    if not forces:
        return "-"
    bits = [f"{c} {u}" for u, c in sorted(forces.items()) if isinstance(c, int) and c > 0]
    return ", ".join(bits) if bits else "-"


def _fmt_assets(assets: dict[str, int]) -> str:
    if not assets:
        return "-"
    bits = [f"{k}:{v}" for k, v in sorted(assets.items())
            if isinstance(v, int) and v > 0]
    return " ".join(bits) if bits else "-"


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 3] + "..."
