"""Battle resolution (Inferno 4.4) — engine + decision context.

Per BRIEF "Engine / Operator Split":
  - The harness's combat resolution implements the rules faithfully.
  - Choice points flow through a BattleDecisionContext (BDC):
      1. scripted_decisions list (FIFO, consumed in order) — tests pin
         operator choices. A type mismatch raises immediately.
      2. callback (callable) — live play.
      3. deterministic fallback ("leftmost") — picks options[0].

  Decision types within Battle (per BRIEF):
    initial_placement_attacker — non-Active Attacker Lord into a slot
    initial_placement_defender — Defender Lord into a slot
    reserve_advance            — Reserve advances into empty Front slot
    center_fill                — Left/Right Lord slides to fill empty Center
    flanker_target             — Center Flanker tie-break (Left or Right)
    flanker_absorb             — Flanking Lord may absorb Hits aimed elsewhere
    hit_allocation             — Flanker vs directly-opposed when both reachable
    concede                    — side declares Concede at start of Round (>= 2)

  The full decision trace is returned under result["decisions"].
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from . import static_data as sd


# =====================================================================
# Decision context
# =====================================================================
@dataclass
class BattleDecisionContext:
    """Resolves player choice points during Battle.

    Priority: scripted -> callback -> leftmost fallback.
    """

    scripted: list[dict[str, Any]] = field(default_factory=list)
    callback: Callable[[dict[str, Any]], Any] | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)

    def decide(self, decision_type: str, side: str, options: list[Any],
               info: dict[str, Any] | None = None) -> Any:
        if not options:
            raise ValueError(f"No options for decision {decision_type!r}")
        info = info or {}
        choice: Any
        if self.scripted:
            d = self.scripted.pop(0)
            if d.get("type") != decision_type:
                raise ValueError(
                    f"Scripted decision type mismatch: expected {decision_type!r}, got {d.get('type')!r}"
                )
            choice = d.get("choice")
            if choice not in options:
                raise ValueError(
                    f"Scripted choice {choice!r} not in options {options!r} for {decision_type!r}"
                )
        elif self.callback is not None:
            choice = self.callback({
                "type": decision_type, "side": side,
                "options": list(options), "info": info,
            })
            if choice not in options:
                raise ValueError(
                    f"Callback returned {choice!r} not in options {options!r}"
                )
        else:
            choice = options[0]  # leftmost fallback
        self.trace.append({
            "type": decision_type, "side": side,
            "choice": choice, "options": list(options), "info": info,
        })
        return choice


# =====================================================================
# Battle field state
# =====================================================================
SLOTS = ("left", "center", "right")


def _empty_positions() -> dict[str, dict[str, str | None]]:
    return {
        "attacker": {s: None for s in SLOTS},
        "defender": {s: None for s in SLOTS},
    }


def _initial_array(state, attacker_ids: list[str], defender_ids: list[str],
                   active_id: str, bdc: BattleDecisionContext
                   ) -> tuple[dict[str, dict[str, str | None]],
                              dict[str, list[str]]]:
    """4.4.1 Battle Array.

    Attacker: ACTIVE Lord MUST start at Front Center; fill Left/Right
    from other Attacking Lords (BDC picks order). Remaining -> Reserve.

    Defender: place one Lord directly OPPOSITE each Front Attacker,
    filling Center first then Left/Right.
    """
    positions = _empty_positions()
    reserve: dict[str, list[str]] = {"attacker": [], "defender": []}

    # Active Lord at Front Center
    if active_id not in attacker_ids:
        raise ValueError(f"Active Lord {active_id} not in attacker list.")
    positions["attacker"]["center"] = active_id
    other_attackers = [a for a in attacker_ids if a != active_id]

    # Fill attacker Left/Right (up to 2) via BDC
    available_slots = ["left", "right"]
    while other_attackers and available_slots:
        slot = bdc.decide(
            "initial_placement_attacker", "attacker",
            options=available_slots,
            info={"lords_remaining": list(other_attackers)},
        )
        # Which Lord goes here?
        lord_choice = bdc.decide(
            "initial_placement_attacker", "attacker",
            options=list(other_attackers),
            info={"placing_at_slot": slot},
        )
        positions["attacker"][slot] = lord_choice
        other_attackers.remove(lord_choice)
        available_slots.remove(slot)
    reserve["attacker"] = list(other_attackers)

    # Defender: place opposite each filled attacker slot in order Center -> Left/Right
    filled_attacker_slots = [s for s in ("center", "left", "right")
                             if positions["attacker"][s] is not None]
    defenders_remaining = list(defender_ids)
    for slot in filled_attacker_slots:
        if not defenders_remaining:
            break
        if len(defenders_remaining) == 1:
            choice = defenders_remaining[0]
        else:
            choice = bdc.decide(
                "initial_placement_defender", "defender",
                options=list(defenders_remaining),
                info={"placing_at_slot": slot, "opposite_attacker": positions["attacker"][slot]},
            )
        positions["defender"][slot] = choice
        defenders_remaining.remove(choice)
    reserve["defender"] = list(defenders_remaining)

    return positions, reserve


def _reposition(positions, reserve, bdc: BattleDecisionContext) -> None:
    """4.4.2 Reposition (Round >= 2).

    ADVANCE: Attacker then Defender slides each Unrouted Reserve Lord
    into any EMPTY Front position (one each).

    CENTER FILL: If Front Center is empty after Advance, the side MUST
    select a Lord from Front Left or Right to slide into Center.
    """
    for side in ("attacker", "defender"):
        # ADVANCE
        for reserve_lord in list(reserve[side]):
            empty_slots = [s for s in SLOTS if positions[side][s] is None]
            if not empty_slots:
                break
            slot = bdc.decide(
                "reserve_advance", side,
                options=empty_slots,
                info={"reserve_lord": reserve_lord},
            )
            positions[side][slot] = reserve_lord
            reserve[side].remove(reserve_lord)
        # CENTER FILL
        if positions[side]["center"] is None:
            candidates = [s for s in ("left", "right") if positions[side][s] is not None]
            if candidates:
                slot = bdc.decide(
                    "center_fill", side,
                    options=candidates,
                    info={"reason": "front_center_empty"},
                )
                positions[side]["center"] = positions[side][slot]
                positions[side][slot] = None


# =====================================================================
# Hits and Protection
# =====================================================================
def _live_units(lord: dict) -> dict[str, int]:
    """Unrouted forces on a Lord's mat."""
    out = {}
    for unit, count in (lord.get("forces") or {}).items():
        if count > 0:
            out[unit] = count
    return out


def _strike_hits(units: dict[str, int], step: str, is_storm: bool = False) -> float:
    """Compute total Hits from a Lord's units for one Strike step.

    step is one of:
      'def_archery', 'atk_archery',
      'def_horse_melee', 'atk_horse_melee',
      'def_foot_melee', 'atk_foot_melee'

    Per 4.4.2 + Forces table: each unit's Hits/Strike depends on type.
    For BATTLE: Horse and Foot Melee steps are separate; Archery uses
    the unit's Archery rating.

    Storm initiative collapses Horse+Foot Melee into one step per side;
    callers can flag is_storm=True for that variant (Phase 3c).
    """
    archery_step = step.endswith("archery")
    horse_step = "horse" in step
    foot_step = "foot" in step
    total = 0.0
    for unit, count in units.items():
        u = sd.UNITS.get(unit)
        if not u:
            continue
        cat = u.get("cat")
        if archery_step:
            # Archery only fires when Garrison or capability — Phase 3b
            # treats Lord-mat archery as ZERO unless a capability mods
            # (capabilities are Phase 4). So archery_hits = 0 here for
            # Lord units in Battle.
            continue
        if horse_step and cat == "horse":
            total += count * u.get("battle_strikes", 0)
        elif foot_step and cat == "foot":
            total += count * u.get("battle_strikes", 0)
    return total


# Standard Battle strike order (Section 8)
BATTLE_STRIKE_ORDER = [
    "def_archery",
    "atk_archery",
    "def_horse_melee",
    "atk_horse_melee",
    "def_foot_melee",
    "atk_foot_melee",
]


def _flanking_relationships(positions: dict, bdc: "BattleDecisionContext | None" = None
                            ) -> dict[str, list[tuple[str, str]]]:
    """Compute Flanking relationships per 9.2.

    A Lord at Front with NO Enemy directly opposite Flanks the closest
    Front Enemy. For Center Flankers with both Left and Right Enemy
    options, the owner chooses (BDC decision type 'flanker_target').
    """
    flanks: dict[str, list[tuple[str, str]]] = {"attacker": [], "defender": []}
    for me, opp in [("attacker", "defender"), ("defender", "attacker")]:
        for slot in SLOTS:
            if positions[me][slot] is None:
                continue
            if positions[opp][slot] is not None:
                continue
            enemy_slots = [s for s in SLOTS if positions[opp][s] is not None]
            if not enemy_slots:
                continue
            if slot == "center":
                # Center Flanker — choose Left or Right if both present
                if "left" in enemy_slots and "right" in enemy_slots:
                    if bdc is not None:
                        target = bdc.decide(
                            "flanker_target", me,
                            options=["left", "right"],
                            info={"flanker_at": "center"},
                        )
                    else:
                        target = "left"
                else:
                    target = "left" if "left" in enemy_slots else "right"
                flanks[me].append((slot, target))
            else:
                if slot == "left":
                    target = "center" if "center" in enemy_slots else (
                        "right" if "right" in enemy_slots else enemy_slots[0]
                    )
                else:
                    target = "center" if "center" in enemy_slots else (
                        "left" if "left" in enemy_slots else enemy_slots[0]
                    )
                flanks[me].append((slot, target))
    return flanks


def _resolve_step(state, step: str, positions, reserve, conceded: str | None,
                  bdc, rng_caller, hit_log: list, removed_lords: set,
                  routed_per_lord: dict) -> None:
    """Resolve one Strike sub-step (e.g., 'atk_horse_melee').

    Sums Hits from striking side's Front Lords (and Flanking Lords),
    applies Protection rolls to assigned units in the target Lord's mat,
    tracks Routs. Conceding side halves its Hits this Round.
    """
    striking_side = "attacker" if step.startswith("atk") else "defender"
    target_side = "defender" if striking_side == "attacker" else "attacker"
    flanks = _flanking_relationships(positions, bdc)

    # For each potential target slot, compute total Hits aimed at the Lord there
    # from (a) directly-opposed striker, (b) Flanking strikers.
    per_target_hits: dict[str, float] = {s: 0.0 for s in SLOTS}
    for slot in SLOTS:
        striker_id = positions[striking_side][slot]
        if striker_id is None:
            continue
        striker_lord = state["lords"][striker_id]
        units = _live_units(striker_lord)
        h = _strike_hits(units, step)
        # Flanking? If yes, target is the flank target; else direct opposite.
        opposite_slot = slot
        if positions[target_side][slot] is not None:
            per_target_hits[opposite_slot] = per_target_hits.get(opposite_slot, 0) + h
        else:
            # Find flank entry
            for my_slot, target_slot in flanks[striking_side]:
                if my_slot == slot:
                    per_target_hits[target_slot] = per_target_hits.get(target_slot, 0) + h
                    break

    # Halve hits if striking side is conceded
    if conceded == striking_side:
        per_target_hits = {k: v / 2 for k, v in per_target_hits.items()}

    # Round up per target
    per_target_hits = {k: math.ceil(v) for k, v in per_target_hits.items()}

    # Apply hits to each target Lord
    for slot, n_hits in per_target_hits.items():
        if n_hits <= 0:
            continue
        target_id = positions[target_side][slot]
        if target_id is None:
            continue
        _absorb_hits(state, target_id, int(n_hits), rng_caller, hit_log, routed_per_lord)
        # Check if target lord routs entirely
        if _all_units_routed(state["lords"][target_id]):
            removed_lords.add(target_id)
            positions[target_side][slot] = None


def _absorb_hits(state, lord_id: str, n_hits: int, rng_caller,
                 hit_log: list, routed_per_lord: dict) -> None:
    """Apply n_hits to lord_id's units. Owner picks; Phase 3b uses a
    simple priority (Villici first since they auto-remove, then
    Light Horse/Militia, then armored).
    """
    lord = state["lords"][lord_id]
    forces = lord.setdefault("forces", {})
    routed = lord.setdefault("routed_units", {})
    # Phase 3b absorption order: Villici, Unarmored (Light Horse, Militia),
    # Armored (Berrovieri, Armigieri, Men-at-Arms, Cavalieri, Ritter)
    absorb_order = ["Villici", "Light Horse", "Militia",
                    "Berrovieri", "Armigieri", "Men-at-Arms",
                    "Cavalieri", "Ritter"]
    hits_remaining = n_hits
    while hits_remaining > 0:
        # Find a unit to absorb
        absorbing_unit = None
        for u in absorb_order:
            if forces.get(u, 0) > 0:
                absorbing_unit = u
                break
        if absorbing_unit is None:
            break  # nothing left
        # Apply 1 hit to this unit
        if absorbing_unit == "Villici":
            forces["Villici"] -= 1
            if forces["Villici"] <= 0:
                forces.pop("Villici", None)
            hit_log.append({"lord_id": lord_id, "unit": "Villici", "removed": True})
            hits_remaining -= 1
            continue
        # Roll Protection
        u = sd.UNITS[absorbing_unit]
        prot_range = u.get("protection", [])
        r = rng_caller(f"protect_{lord_id}_{absorbing_unit}")
        survived = r.value in prot_range
        hit_log.append({
            "lord_id": lord_id, "unit": absorbing_unit,
            "die": r.value, "protection": prot_range, "survived": survived,
        })
        if survived:
            # Unit absorbed the hit and is fine; can absorb more
            hits_remaining -= 1
        else:
            # Routed: slide to routed_units
            forces[absorbing_unit] -= 1
            if forces[absorbing_unit] <= 0:
                forces.pop(absorbing_unit, None)
            routed[absorbing_unit] = routed.get(absorbing_unit, 0) + 1
            routed_per_lord.setdefault(lord_id, []).append(absorbing_unit)
            hits_remaining -= 1


def _all_units_routed(lord: dict) -> bool:
    return sum((lord.get("forces") or {}).values()) == 0


# =====================================================================
# Top-level Battle resolution
# =====================================================================
def resolve_battle(state, attacker_ids: list[str], defender_ids: list[str],
                   active_id: str, locale_name: str,
                   approach_way_type: str | None = None,
                   scripted_decisions: list[dict] | None = None,
                   callback: Callable | None = None) -> dict[str, Any]:
    """Resolve a Battle at `locale_name`. Returns a result dict with the
    full decision trace, per-round Hit log, final positions, winner,
    losing-side fate (Retreat / Withdraw / Removed), and Aftermath flags.

    Per BRIEF: tests must use scripted_decisions for any Battle they
    assert outcomes on. Leftmost fallback is acceptable only for
    structural-property tests.
    """
    bdc = BattleDecisionContext(scripted=list(scripted_decisions or []),
                                callback=callback)

    # Capture pre-Battle Forces snapshot for Spoils + audit
    pre_forces = {lid: dict(state["lords"][lid].get("forces", {}))
                  for lid in attacker_ids + defender_ids}

    positions, reserve = _initial_array(
        state, attacker_ids, defender_ids, active_id, bdc,
    )

    # RNG helper that delegates back to the harness RNG via dispatch.
    # In testing we'll inject the rolls via state.meta.rng_seed + advance.
    from .rng import HarnessRNG
    rng = HarnessRNG(state["meta"]["rng_seed"],
                     advance=state["meta"].get("rng_advance", 0))
    rolls_before = rng.advance_count
    def _rng_roll(ctx: str):
        return rng.roll(ctx)

    conceded: str | None = None
    pursuit_marker: str | None = None
    rounds: list[dict] = []
    removed_lords: set = set()
    routed_per_lord: dict = {}
    max_rounds = 12  # safety bound

    for round_n in range(1, max_rounds + 1):
        round_log: dict[str, Any] = {"round": round_n}
        # Concede check at start of each Round (>= 2 to actually halve;
        # SoP says Concede declarations apply to current Round's resolution,
        # and "Battles last AT LEAST ONE Round" — Phase 3b allows Concede
        # from Round 2 onward.
        if round_n >= 2 and conceded is None:
            for side in ("attacker", "defender"):
                # BDC may pick Concede or not.
                choice = bdc.decide(
                    "concede", side,
                    options=["no", "yes"],
                    info={"round": round_n, "positions": positions},
                )
                if choice == "yes":
                    conceded = side
                    pursuit_marker = "attacker" if side == "defender" else "defender"
                    round_log["concede"] = side
                    break

        # Reposition (Round >= 2)
        if round_n >= 2:
            _reposition(positions, reserve, bdc)
            round_log["positions_after_reposition"] = _snapshot_positions(positions)

        # 6-step Strike
        hit_log_round: list = []
        for step in BATTLE_STRIKE_ORDER:
            _resolve_step(state, step, positions, reserve, conceded,
                          bdc, _rng_roll, hit_log_round, removed_lords, routed_per_lord)
        round_log["hit_log"] = hit_log_round
        round_log["positions"] = _snapshot_positions(positions)
        rounds.append(round_log)

        # End check (11.1)
        if conceded is not None:
            break  # Concede: Battle ends this Round
        atk_alive = any(positions["attacker"][s] is not None for s in SLOTS) or reserve["attacker"]
        def_alive = any(positions["defender"][s] is not None for s in SLOTS) or reserve["defender"]
        if not atk_alive or not def_alive:
            break

    # Determine winner / loser
    atk_alive = any(positions["attacker"][s] is not None for s in SLOTS) or reserve["attacker"]
    def_alive = any(positions["defender"][s] is not None for s in SLOTS) or reserve["defender"]
    if conceded == "attacker":
        winner, loser = "defender", "attacker"
    elif conceded == "defender":
        winner, loser = "attacker", "defender"
    elif atk_alive and not def_alive:
        winner, loser = "attacker", "defender"
    elif def_alive and not atk_alive:
        winner, loser = "defender", "attacker"
    else:
        winner, loser = "attacker", "defender"  # both alive after max rounds (rare)

    # Persist RNG advance
    rolls_consumed = rng.advance_count - rolls_before
    state["meta"]["rng_advance"] = state["meta"].get("rng_advance", 0) + rolls_consumed

    # Mark Moved/Fought on all Lords involved (per 4.4.6).
    for lid in attacker_ids + defender_ids:
        state["lords"][lid].setdefault("flags", {})["moved_fought"] = True

    return {
        "locale": locale_name,
        "winner": winner,
        "loser": loser,
        "conceded": conceded,
        "pursuit_marker": pursuit_marker,
        "rounds_played": len(rounds),
        "rounds": rounds,
        "positions_final": _snapshot_positions(positions),
        "reserve_final": dict(reserve),
        "removed_lords": sorted(removed_lords),
        "routed_per_lord": routed_per_lord,
        "pre_forces": pre_forces,
        "decisions": bdc.trace,
        "rolls": [{"context": r.context, "value": r.value} for r in rng.drain_log()],
    }


def _snapshot_positions(positions) -> dict:
    return {side: dict(positions[side]) for side in ("attacker", "defender")}


# =====================================================================
# Storm / Sally (Phase 3c)
# =====================================================================
STORM_STRIKE_ORDER = [
    "def_archery",
    "atk_archery",
    "def_all_melee",   # ALL Defending Melee (Horse + Foot)
    "atk_all_melee",   # ALL Attacking Melee
]


def _strike_hits_storm(units: dict[str, int], step: str) -> float:
    """Storm initiative collapses Horse+Foot Melee. Archery only for
    units that have it (Garrison rules let Foot units use their Archery
    rating in Storm)."""
    if step.endswith("archery"):
        total = 0.0
        for unit, count in units.items():
            u = sd.UNITS.get(unit)
            if not u:
                continue
            # In a Garrison context Archery fires for Foot units.
            # Phase 3c: Garrison units always Archery-eligible per 4.5.2.
            total += count * u.get("archery", 0)
        return total
    if step.endswith("all_melee"):
        total = 0.0
        for unit, count in units.items():
            u = sd.UNITS.get(unit)
            if not u:
                continue
            # Use storm-specific melee strikes per Forces table:
            # 'storm_strikes_attacker' for attacking units, 'storm_strikes_defender' for defending.
            # Caller passes appropriate units dict; here we use the side hint via step.
            field = "storm_strikes_attacker" if step.startswith("atk") else "storm_strikes_defender"
            total += count * u.get(field, 0)
        return total
    return 0.0


def _garrison_for(stronghold_type: str) -> dict[str, int]:
    """Per 4.5.2: Garrisons by Stronghold tier (see STRONGHOLDS table).
    Castle has Militia (1) instead of Armigieri.
    """
    g = dict(sd.STRONGHOLDS.get(stronghold_type, {}).get("garrison", {}))
    return g


def resolve_storm(state, attackers: list[str], defenders: list[str],
                  active_id: str, locale_name: str,
                  scripted_decisions: list[dict] | None = None,
                  callback: Callable | None = None) -> dict[str, Any]:
    """4.5.2 Storm. Attacker outside Besieged Stronghold attacks; Defender
    uses Walls 1-4 (+Walls+1), Garrison units, Attacker uses Siegeworks
    (= Siege markers) as own Walls.

    Phase 3c implementation:
      - Front row capped at 1 Lord per side (Storm Array per 2.2).
      - 4-step initiative: Def Archery, Atk Archery, Def All-Melee,
        Atk All-Melee (per 4.5.2 STRONGHOLD EFFECTS).
      - Walls/Siegeworks rolled before assigning Hits to units.
      - Storm runs at most # Siege markers rounds.
      - Only Attacker may Concede (Round >= 2).
      - On Defender loss: SACK outcome flag (Ruins + Spoils + revolts
        — applied by the action handler, not here).
      - On Attacker loss: Attackers neither Retreat nor give Spoils;
        Siege markers remain; flag for action handler to handle.
    """
    bdc = BattleDecisionContext(scripted=list(scripted_decisions or []),
                                callback=callback)
    locale = state["locales"][locale_name]
    stronghold_type = locale.get("type")
    siege_count = sum(s.get("count", 1) for s in locale.get("siege", []))
    siegeworks_die = list(range(1, siege_count + 1))  # 1..N nullifies a hit
    walls_die = list(sd.STRONGHOLDS.get(stronghold_type, {}).get("walls_die", []))
    # Capability: storm_walls_minus reduces effective Walls for the Attacker
    # (e.g., F3 Siege Towers, F5 War Engineers). Phase 4: applied as Attacker's
    # adjusted Siegeworks die range.
    from . import card_effects as ce
    storm_walls_minus = sum(c["value"] for c in ce.active_capabilities_for(state, "storm_walls_minus"))
    if storm_walls_minus and walls_die:
        walls_die = walls_die[:-storm_walls_minus] if len(walls_die) > storm_walls_minus else []
    if locale.get("walls_plus_one"):
        walls_die = walls_die + [max(walls_die) + 1 if walls_die else 5]

    # Garrison Forces (separate from Defending Lord(s))
    garrison = _garrison_for(stronghold_type)
    state.setdefault("storm_garrison", {})[locale_name] = dict(garrison)

    # Storm Array: 1 Lord per side at Center; others Reserve.
    positions = _empty_positions()
    positions["attacker"]["center"] = active_id
    reserve = {"attacker": [a for a in attackers if a != active_id],
               "defender": list(defenders)}
    if defenders:
        positions["defender"]["center"] = defenders[0]
        reserve["defender"] = defenders[1:]

    from .rng import HarnessRNG
    rng = HarnessRNG(state["meta"]["rng_seed"],
                     advance=state["meta"].get("rng_advance", 0))
    rolls_before = rng.advance_count

    conceded: str | None = None
    rounds: list[dict] = []
    removed_lords: set = set()
    routed_per_lord: dict = {}
    max_rounds = max(1, siege_count)  # Storm lasts at most # Siege markers rounds

    for round_n in range(1, max_rounds + 1):
        round_log: dict[str, Any] = {"round": round_n}

        # Concede (Attacker only, Round >= 2)
        if round_n >= 2 and conceded is None:
            choice = bdc.decide(
                "concede", "attacker",
                options=["no", "yes"],
                info={"round": round_n, "siege_count": siege_count},
            )
            if choice == "yes":
                conceded = "attacker"
                round_log["concede"] = "attacker"

        # Storm Reposition (Round >= 2): each side MAY add ONE Lord from
        # Reserve to Front, capped at Stronghold Size (Castle=1).
        # Phase 3c: Castle size=1 means no additional Lords; Town/City
        # can add up to Size total.
        if round_n >= 2:
            size = sd.STRONGHOLDS.get(stronghold_type, {}).get("size", 1)
            for side in ("attacker", "defender"):
                front_count = sum(1 for s in SLOTS if positions[side][s] is not None)
                if reserve[side] and front_count < size:
                    add = bdc.decide(
                        "storm_reserve_add", side,
                        options=["yes", "no"],
                        info={"front_count": front_count, "stronghold_size": size},
                    )
                    if add == "yes":
                        empty = [s for s in SLOTS if positions[side][s] is None]
                        slot = empty[0] if empty else None
                        if slot:
                            positions[side][slot] = reserve[side].pop(0)

        # 4-step Storm Strike
        hit_log_round: list = []
        for step in STORM_STRIKE_ORDER:
            _resolve_storm_step(state, step, positions, reserve, conceded,
                                bdc, rng.roll, hit_log_round, removed_lords,
                                routed_per_lord, garrison, walls_die, siegeworks_die,
                                locale_name)
        round_log["hit_log"] = hit_log_round
        round_log["positions"] = _snapshot_positions(positions)
        rounds.append(round_log)

        # End check (4.5.2):
        #   - Rounds completed = Siege markers (handled by loop max)
        #   - A side has all units there Routed
        #   - Attacker Concedes
        atk_alive = any(positions["attacker"][s] is not None for s in SLOTS) or reserve["attacker"]
        def_alive = (any(positions["defender"][s] is not None for s in SLOTS)
                     or reserve["defender"]
                     or sum(state["storm_garrison"][locale_name].values()) > 0)
        if conceded == "attacker":
            break
        if not atk_alive or not def_alive:
            break

    # Determine outcome (4.5.2):
    # Unless ALL Defenders Routed, Storm Attackers LOSE.
    def_completely_routed = (
        not any(positions["defender"][s] is not None for s in SLOTS)
        and not reserve["defender"]
        and sum(state["storm_garrison"][locale_name].values()) == 0
    )
    atk_alive = any(positions["attacker"][s] is not None for s in SLOTS) or reserve["attacker"]
    if def_completely_routed and atk_alive:
        winner, loser = "attacker", "defender"
        outcome = "sack"  # 4.5.2: Sack on Defender loss
    else:
        winner, loser = "defender", "attacker"
        outcome = "attacker_loss"  # Siege markers stay

    # Persist RNG advance
    state["meta"]["rng_advance"] = state["meta"].get("rng_advance", 0) + (rng.advance_count - rolls_before)

    # Mark Moved/Fought on all Lords involved (including Reserve per 4.5 Aftermath).
    for lid in attackers + defenders:
        if lid in state["lords"]:
            state["lords"][lid].setdefault("flags", {})["moved_fought"] = True

    return {
        "locale": locale_name,
        "mode": "storm",
        "winner": winner,
        "loser": loser,
        "outcome": outcome,
        "conceded": conceded,
        "rounds_played": len(rounds),
        "rounds": rounds,
        "positions_final": _snapshot_positions(positions),
        "reserve_final": dict(reserve),
        "removed_lords": sorted(removed_lords),
        "routed_per_lord": routed_per_lord,
        "garrison_final": dict(state["storm_garrison"].get(locale_name, {})),
        "siege_count": siege_count,
        "decisions": bdc.trace,
        "rolls": [{"context": r.context, "value": r.value} for r in rng.drain_log()],
    }


def _resolve_storm_step(state, step, positions, reserve, conceded,
                        bdc, rng_roll, hit_log, removed_lords,
                        routed_per_lord, garrison, walls_die, siegeworks_die,
                        locale_name):
    """One Storm Strike step. Garrison contributes to Defender Strikes
    and absorbs Hits aimed at Defender first per 4.5.2."""
    striking_side = "attacker" if step.startswith("atk") else "defender"
    target_side = "defender" if striking_side == "attacker" else "attacker"

    per_target_hits: dict[str, float] = {s: 0.0 for s in SLOTS}
    for slot in SLOTS:
        striker_id = positions[striking_side][slot]
        if striker_id is None:
            continue
        striker_lord = state["lords"][striker_id]
        units = _live_units(striker_lord)
        # If defender, add Garrison Strikes (Storm Array has Garrison defending).
        if striking_side == "defender":
            units = dict(units)
            for u, c in state["storm_garrison"][locale_name].items():
                units[u] = units.get(u, 0) + c
        h = _strike_hits_storm(units, step)
        # In Storm Array, only Center is used; direct opposite.
        per_target_hits[slot] = per_target_hits.get(slot, 0) + h
    if conceded == striking_side:
        per_target_hits = {k: v / 2 for k, v in per_target_hits.items()}
    per_target_hits = {k: math.ceil(v) for k, v in per_target_hits.items()}

    for slot, n_hits in per_target_hits.items():
        if n_hits <= 0:
            continue
        target_id = positions[target_side][slot]
        if target_id is None:
            continue
        # Apply Walls/Siegeworks roll before unit-Protection.
        if target_side == "defender" and walls_die:
            n_hits = _apply_walls(int(n_hits), walls_die, rng_roll, f"walls_{locale_name}")
        elif target_side == "attacker" and siegeworks_die:
            n_hits = _apply_walls(int(n_hits), siegeworks_die, rng_roll, f"siegeworks_{locale_name}")
        # Defender: assign Hits to GARRISON first until exhausted.
        if target_side == "defender" and locale_name in state["storm_garrison"]:
            n_hits = _absorb_garrison_hits(state, locale_name, int(n_hits), rng_roll, hit_log)
        if n_hits > 0:
            _absorb_hits(state, target_id, int(n_hits), rng_roll, hit_log, routed_per_lord)
            if _all_units_routed(state["lords"][target_id]):
                removed_lords.add(target_id)
                positions[target_side][slot] = None


def _apply_walls(n_hits: int, walls_range: list[int], rng_roll, ctx: str) -> int:
    """Roll a die per Hit; cancel one Hit per roll within walls_range."""
    surviving = 0
    for i in range(n_hits):
        r = rng_roll(f"{ctx}_{i}")
        if r.value not in walls_range:
            surviving += 1
    return surviving


def _absorb_garrison_hits(state, locale_name: str, n_hits: int, rng_roll, hit_log) -> int:
    """Per 4.5.2: Defender MUST assign Hits to Garrison units until they
    are Routed; then to Lord units. Returns hits remaining after Garrison."""
    garrison = state["storm_garrison"][locale_name]
    # Same absorption order as Lord units
    order = ["Villici", "Light Horse", "Militia", "Berrovieri", "Armigieri",
             "Men-at-Arms", "Cavalieri", "Ritter"]
    while n_hits > 0:
        absorbing = None
        for u in order:
            if garrison.get(u, 0) > 0:
                absorbing = u
                break
        if absorbing is None:
            break
        if absorbing == "Villici":
            garrison["Villici"] -= 1
            n_hits -= 1
            hit_log.append({"garrison_unit": "Villici", "removed": True, "locale": locale_name})
            continue
        u = sd.UNITS[absorbing]
        prot = u.get("protection", [])
        r = rng_roll(f"garrison_{absorbing}_{locale_name}")
        survived = r.value in prot
        hit_log.append({
            "garrison_unit": absorbing, "die": r.value,
            "protection": prot, "survived": survived, "locale": locale_name,
        })
        if survived:
            n_hits -= 1
        else:
            garrison[absorbing] -= 1
            if garrison[absorbing] <= 0:
                garrison.pop(absorbing, None)
            n_hits -= 1
    return n_hits


# =====================================================================
# Phase 3d: post-Battle Loss rolls, Service shifts, Spoils, Knights' Quarter
# =====================================================================
def loss_roll_for_routed(state, lord_id: str, harsh_recovery: bool, rng_caller) -> dict:
    """4.4.4 Roll for each Routed unit after Battle/Storm/Sally.

    Standard: roll 1d6; if within unit's INHERENT Protection range, unit
    recovers (return to mat); else LOST.
    Harsh Recovery: applies to (a) Retreated without Concede, (b) Storm
    Attackers. Unit fails UNLESS roll == 1.

    Knights' Quarter (4.4.4): Cavalieri / Ritter that were Routed AND
    LOST on a 3-6 are CAPTURED to OWNER'S Captured Knights box (used
    for 4.9.2 Ransom). Captured-by-side recorded separately.

    Villici don't roll (already removed when Hit).
    """
    lord = state["lords"][lord_id]
    routed = dict(lord.get("routed_units", {}))
    recovered: dict[str, int] = {}
    lost: dict[str, int] = {}
    captured: dict[str, int] = {}
    for unit, count in routed.items():
        if unit == "Villici":
            continue
        u = sd.UNITS.get(unit, {})
        prot = u.get("protection", [])
        for _ in range(count):
            r = rng_caller(f"loss_{lord_id}_{unit}")
            if harsh_recovery:
                survives = r.value == 1
            else:
                survives = r.value in prot
            if survives:
                recovered[unit] = recovered.get(unit, 0) + 1
            else:
                # Knights' Quarter for Cavalieri/Ritter on 3-6 (Battle only,
                # via the standard 4.4.4 Capture trigger; Storm Garrison
                # capture is handled separately).
                if unit in ("Cavalieri", "Ritter") and r.value >= 3:
                    captured[unit] = captured.get(unit, 0) + 1
                else:
                    lost[unit] = lost.get(unit, 0) + 1
    # Apply: recovered -> forces, lost -> pool, captured -> Captured Knights box
    forces = lord.setdefault("forces", {})
    for u, c in recovered.items():
        forces[u] = forces.get(u, 0) + c
    # Captured units belong to the OWNER for Ransom — store in side ledger
    if captured:
        state.setdefault("captured_knights", {}).setdefault(lord["side"], {})
        for u, c in captured.items():
            cap = state["captured_knights"][lord["side"]]
            cap[u] = cap.get(u, 0) + c
    # Clear routed pile (recovered/lost/captured all leave)
    lord["routed_units"] = {}
    return {"lord_id": lord_id, "recovered": recovered, "lost": lost,
            "captured": captured, "harsh_recovery": harsh_recovery}


def service_shift_for_retreated(state, lord_id: str, conceded_with_carroccio: bool,
                                 rng_caller) -> dict:
    """4.4.3 Service shifts on Retreat. 1d6: 1-2 -> 1 box left, 3-4 -> 2
    boxes, 5-6 -> 3 boxes. Conceded + retained Carroccio = exactly 1 box."""
    if conceded_with_carroccio:
        shift = 1
        r_val = None
    else:
        r = rng_caller(f"retreat_shift_{lord_id}")
        r_val = r.value
        shift = 1 if r_val <= 2 else (2 if r_val <= 4 else 3)
    lord = state["lords"][lord_id]
    cur = lord.get("service_box")
    if cur is not None:
        boxes = state["calendar"]["boxes"]
        if str(cur) in boxes and lord_id in boxes[str(cur)]["services"]:
            boxes[str(cur)]["services"].remove(lord_id)
        new = cur - shift
        if new < 1:
            state["calendar"]["off_left_service"].append(lord_id)
            lord["service_box"] = None
        else:
            lord["service_box"] = new
            boxes.setdefault(str(new), {"cylinders": [], "services": [], "victory": [], "markers": []})
            boxes[str(new)]["services"].append(lord_id)
    return {"lord_id": lord_id, "die": r_val, "shift_left": shift}


def transfer_spoils(state, loser_id: str, winners: list[str],
                    retreated: bool, conceded: bool,
                    withdrew: bool) -> dict:
    """4.4.3 Post-Battle Spoils transfer.

    - REMOVED or RETREATED-WITHOUT-CONCEDE: transfer ALL Assets except
      Ships. If Lord has Mustered Carroccio, winner captures it (+2 VP).
    - CONCEDED + RETREATED: transfer Loot + Provender BEYOND Unladen
      carry. Loser keeps Carroccio.
    - WITHDREW into Stronghold: keep ALL.
    """
    if not winners:
        return {"loser_id": loser_id, "transferred": {}, "carroccio_captured": False}
    loser = state["lords"][loser_id]
    transferred: dict[str, int] = {}
    carroccio_cap = False
    if withdrew:
        return {"loser_id": loser_id, "transferred": {}, "carroccio_captured": False,
                "reason": "withdrew"}
    elif conceded and retreated:
        # Concede+Retreat: Loot + (Provender beyond Unladen carry).
        carts = loser["assets"].get("Cart", 0)
        prov = loser["assets"].get("Provender", 0)
        excess_prov = max(0, prov - carts)  # Unladen carry on Road = up to 2*Carts; conservative
        loot = loser["assets"].get("Loot", 0)
        transferred["Loot"] = loot
        transferred["Provender"] = excess_prov
        loser["assets"]["Loot"] = 0
        loser["assets"]["Provender"] = prov - excess_prov
    else:
        # Removed OR retreated-without-concede: transfer ALL except Ships.
        for asset, count in list(loser["assets"].items()):
            if asset == "Ship":
                continue
            if count > 0:
                transferred[asset] = transferred.get(asset, 0) + count
                loser["assets"][asset] = 0
        # Carroccio capture
        carroccio = next((v for v in loser.get("vassals", [])
                          if v.get("special") and v.get("name") == "Carroccio"
                          and v.get("on_mat")), None)
        if carroccio:
            carroccio_cap = True
            # +2 VP to winning side
            winner_side = state["lords"][winners[0]]["side"]
            state["vp"][winner_side] = min(state["vp"].get(winner_side, 0) + 2, 17.5)
            # Remove Carroccio Vassal from loser
            loser["vassals"] = [v for v in loser["vassals"] if v.get("name") != "Carroccio"]
    # Distribute to winners: round-robin starting with first
    if transferred:
        winner_idx = 0
        for asset, total in transferred.items():
            for _ in range(total):
                w = state["lords"][winners[winner_idx % len(winners)]]
                w["assets"][asset] = w["assets"].get(asset, 0) + 1
                winner_idx += 1
    return {"loser_id": loser_id, "transferred": transferred,
            "carroccio_captured": carroccio_cap}
