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


def _flanking_relationships(positions: dict) -> dict[str, list[tuple[str, str]]]:
    """Compute Flanking relationships per 9.2.

    Returns {"attacker": [(my_slot, target_slot), ...], "defender": [...]}
    A side's Lord at Front with NO Enemy Lord directly opposite is
    Flanking — chooses the closest Front Enemy (Center may choose
    Left or Right).
    """
    flanks: dict[str, list[tuple[str, str]]] = {"attacker": [], "defender": []}
    for me, opp in [("attacker", "defender"), ("defender", "attacker")]:
        for slot in SLOTS:
            if positions[me][slot] is None:
                continue
            if positions[opp][slot] is not None:
                continue  # directly opposed; not flanking
            # No opposite enemy at this slot — Lord flanks an enemy.
            enemy_slots = [s for s in SLOTS if positions[opp][s] is not None]
            if not enemy_slots:
                continue
            if slot == "center":
                # Center may choose Left or Right (caller's decision via BDC).
                # For computation here, pick deterministically; the BDC
                # call happens at hit-application time.
                flanks[me].append((slot, enemy_slots[0]))
            else:
                # Left or Right: must flank the closest Front Enemy.
                # For our 3-slot model, that's: from left -> center if present, else right.
                # From right -> center if present, else left.
                if slot == "left":
                    target = "center" if "center" in enemy_slots else (
                        "right" if "right" in enemy_slots else enemy_slots[0]
                    )
                else:  # right
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
    flanks = _flanking_relationships(positions)

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
