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
                  routed_per_lord: dict, round_n: int = 1) -> None:
    """Resolve one Strike sub-step. Consults Phase-5 Battle hooks for
    F4 Sudden Clash, F6/S6 Hills, F8/S8 Swamp."""
    striking_side = "attacker" if step.startswith("atk") else "defender"
    target_side = "defender" if striking_side == "attacker" else "attacker"
    # Phase 5: F8/S8 Swamp — defender's effect, skips enemy Horse R1.
    if step.endswith("horse_melee") and _enemy_horse_skips_round_1(state, target_side, round_n):
        hit_log.append({"step": step, "skipped": "swamp_horse_no_strike_r1"})
        return
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
        # Phase 6: Capability strike modifiers (Feditori, Army Reserve,
        # Arcieri, Luceria, Balestrieri)
        h += _capability_strike_modifier(state, striker_id, units, step, round_n, "battle")
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

    # Phase 5: Hills (F6/S6) — double Archery Hits if striker is the Defending side.
    if step.endswith("archery") and striking_side == "defender":
        mult = _archery_hits_multiplier(state, "defender")
        if mult > 1:
            per_target_hits = {k: v * mult for k, v in per_target_hits.items()}
            hit_log.append({"step": step, "hills_doubled": True})
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
            # Phase 5: F16 Bloody Red Stream — first Lord to Rout this Battle
            # may pause and roll Protection on Routed units for recovery.
            rr = _check_rout_recovery(state, lord_id, rng_caller)
            if rr and rr["recovered"]:
                hit_log.append({"lord_id": lord_id, "bloody_red_stream_recovered": rr["recovered"]})
                continue  # re-pick absorbing unit now that some are unrouted
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
# Phase 5: in-Battle card-effect hooks
# =====================================================================
def _get_battle_modifiers(state) -> list[dict]:
    """All battle_modifiers_pending entries (in order)."""
    return list(state.get("battle_modifiers_pending", []))


def _consume_battle_modifier(state, effect_key: str, predicate=None) -> dict | None:
    """Find and remove a pending modifier matching effect_key (and
    optional predicate). Returns the entry or None."""
    pending = state.get("battle_modifiers_pending", [])
    for i, m in enumerate(pending):
        if m.get("effect") == effect_key:
            if predicate is None or predicate(m):
                return pending.pop(i)
    return None


def _has_battle_modifier(state, effect_key: str, predicate=None) -> bool:
    pending = state.get("battle_modifiers_pending", [])
    for m in pending:
        if m.get("effect") == effect_key:
            if predicate is None or predicate(m):
                return True
    return False


def _apply_pre_battle_modifiers(state, attackers, defenders) -> dict:
    """Apply pre-Battle Hold-Event modifiers at 4.4.1 Events phase.

    F12/S12 Camp Attack: R1 Asset transfer from each Enemy + remove 2 more.
    S16 Bocca degli Abati: Each Cavalieri on target Guelph Lord takes 1 Hit.
    """
    summary: dict = {"camp_attack": [], "bocca": []}
    # Camp Attack
    cap = _consume_battle_modifier(state, "camp_attack_r1_asset_transfer")
    if cap:
        playing_side = cap.get("side")
        enemy_side = "ghibelline" if playing_side == "guelph" else "guelph"
        enemy_ids = [a for a in attackers + defenders
                     if state["lords"].get(a, {}).get("side") == enemy_side]
        own_ids = [a for a in attackers + defenders
                   if state["lords"].get(a, {}).get("side") == playing_side]
        for eid in enemy_ids:
            elord = state["lords"].get(eid)
            if not elord:
                continue
            # Take up to 2 Assets (excluding Ship), distribute to own side.
            taken: dict[str, int] = {}
            assets = list(elord.get("assets", {}).items())
            to_take = 2
            for a, c in assets:
                if a == "Ship" or c <= 0:
                    continue
                t = min(to_take, c)
                if t > 0:
                    elord["assets"][a] = c - t
                    taken[a] = taken.get(a, 0) + t
                    to_take -= t
                if to_take == 0:
                    break
            # Distribute to own side (Ships allowed for "removed", not taken)
            i = 0
            for a, n in taken.items():
                for _ in range(n):
                    if own_ids:
                        recv = state["lords"][own_ids[i % len(own_ids)]]
                        recv["assets"][a] = recv["assets"].get(a, 0) + 1
                        i += 1
            # Remove 2 more (Ships allowed)
            removed: dict[str, int] = {}
            assets = list(elord.get("assets", {}).items())
            to_remove = 2
            for a, c in assets:
                if c <= 0:
                    continue
                t = min(to_remove, c)
                elord["assets"][a] = c - t
                removed[a] = removed.get(a, 0) + t
                to_remove -= t
                if to_remove == 0:
                    break
            summary["camp_attack"].append({
                "enemy": eid, "taken": taken, "removed": removed,
            })

    # S16 Bocca degli Abati: target Guelph Lord; each Cavalieri takes 1 Hit
    cap = _consume_battle_modifier(state, "bocca_cavalieri_auto_hit")
    if cap:
        target_id = cap.get("target_lord_id")
        if target_id and target_id in state["lords"]:
            tgt = state["lords"][target_id]
            cavs = tgt["forces"].get("Cavalieri", 0)
            from .rng import HarnessRNG
            rng = HarnessRNG(state["meta"]["rng_seed"],
                             advance=state["meta"].get("rng_advance", 0))
            rolls_before = rng.advance_count
            routed = 0
            for _ in range(cavs):
                r = rng.roll(f"bocca_{target_id}_Cavalieri")
                if r.value not in sd.UNITS["Cavalieri"]["protection"]:
                    routed += 1
                    tgt["forces"]["Cavalieri"] -= 1
                    if tgt["forces"]["Cavalieri"] <= 0:
                        tgt["forces"].pop("Cavalieri")
                    tgt.setdefault("routed_units", {})["Cavalieri"] = (
                        tgt["routed_units"].get("Cavalieri", 0) + 1
                    )
            state["meta"]["rng_advance"] = state["meta"].get("rng_advance", 0) + (rng.advance_count - rolls_before)
            # If any Routed, one transfers to a Ghibelline mat in the Battle
            if routed > 0:
                ghib_ids = [a for a in attackers + defenders
                            if state["lords"].get(a, {}).get("side") == "ghibelline"]
                if ghib_ids:
                    recv = state["lords"][ghib_ids[0]]
                    recv["forces"]["Cavalieri"] = recv["forces"].get("Cavalieri", 0) + 1
                    # The transferred Cavalieri counts as Unrouted on the receiver
                    tgt["routed_units"]["Cavalieri"] -= 1
                    if tgt["routed_units"]["Cavalieri"] <= 0:
                        tgt["routed_units"].pop("Cavalieri")
            summary["bocca"] = {"target": target_id, "routed_cavs": routed}
    return summary


def _archery_hits_multiplier(state, defender_side: str) -> int:
    """If Hills (F6/S6) is pending for defender_side, doubles Archery Hits.

    Returns the multiplier (1 normally, 2 if Hills active for defender)."""
    if _consume_battle_modifier(
        state, "hills_double_archery_defending",
        predicate=lambda m: m.get("side") == defender_side,
    ):
        # Re-add (Hills lasts the whole Battle); track via 'consumed_once' flag
        state.setdefault("battle_modifiers_pending", []).append({
            "id": "F6/S6", "side": defender_side,
            "effect": "hills_double_archery_defending", "active_for_battle": True,
        })
        return 2
    # Check if still active
    if _has_battle_modifier(
        state, "hills_double_archery_defending",
        predicate=lambda m: m.get("side") == defender_side and m.get("active_for_battle"),
    ):
        return 2
    return 1


def _enemy_horse_skips_round_1(state, defender_side: str, round_n: int) -> bool:
    """F8/S8 Swamp: enemy Horse don't Strike in R1 if Swamp Defending."""
    if round_n != 1:
        return False
    return _has_battle_modifier(
        state, "swamp_enemy_horse_no_strike_r1",
        predicate=lambda m: m.get("side") == defender_side,
    )


def _sudden_clash_target(state, side: str, round_n: int) -> str | None:
    """F4/S4 Sudden Clash: R1, named Lord's Horse Melee precedes all
    Archery. Returns the target Lord id, or None."""
    if round_n != 1:
        return None
    pending = state.get("battle_modifiers_pending", [])
    for m in pending:
        if (m.get("effect") == "sudden_clash_r1_horse_first_select_target"
                and m.get("side") == side):
            return m.get("lord_id")
    return None


def _check_rout_recovery(state, lord_id: str, rng_roll) -> dict | None:
    """F16 Bloody Red Stream: first Guelph Lord to Rout in Battle pauses;
    each Routed unit rolls Protection. Recoveries unrout.
    """
    cap = _consume_battle_modifier(
        state, "bloody_red_stream_first_rout",
        predicate=lambda m: state["lords"].get(lord_id, {}).get("side") == m.get("side"),
    )
    if not cap:
        return None
    lord = state["lords"][lord_id]
    recovered = {}
    routed = dict(lord.get("routed_units", {}))
    for unit, count in routed.items():
        if unit == "Villici":
            continue
        u = sd.UNITS.get(unit, {})
        prot = u.get("protection", [])
        for _ in range(count):
            r = rng_roll(f"bloody_red_stream_{lord_id}_{unit}")
            if r.value in prot:
                lord["routed_units"][unit] -= 1
                if lord["routed_units"][unit] <= 0:
                    lord["routed_units"].pop(unit, None)
                lord["forces"][unit] = lord["forces"].get(unit, 0) + 1
                recovered[unit] = recovered.get(unit, 0) + 1
    return {"recovered": recovered}


def _clear_battle_modifiers(state) -> None:
    """End-of-Battle cleanup per 4.4.6: discard all Hold Events used."""
    state["battle_modifiers_pending"] = [
        m for m in state.get("battle_modifiers_pending", [])
        if m.get("persist_beyond_battle")
    ]




# =====================================================================
# Phase 6: Per-Capability hooks (Battle / Storm strike modifiers)
# =====================================================================
def _lord_has_capability(state, lord_id: str, capability_name: str) -> bool:
    """True if Lord has the named Capability (via this_lord card or side-wide).

    Capability name matches card.capability_name from card_data, e.g.
    'Feditori', 'Balestrieri', 'Palvesari', 'Arcieri', 'Luceria',
    'Army Reserve', 'Trebuchets', 'Siege Towers', 'Astrologers',
    'Distringitores'.
    """
    from . import card_data as cd
    lord = state.get("lords", {}).get(lord_id) or {}
    side = lord.get("side")
    for cid in lord.get("capabilities", []) or []:
        card = cd.AOW_CARDS_BY_ID.get(cid, {})
        if card.get("capability_name") == capability_name:
            return True
    for c in state.get("capabilities_in_play", []):
        if c.get("side") != side or c.get("scope") != "side_wide":
            continue
        cid = c.get("id")
        card = cd.AOW_CARDS_BY_ID.get(cid, {})
        if card.get("capability_name") == capability_name:
            return True
    return False


# Lord IDs eligible for Army Reserve per Capability text:
#   F12 Army Reserve: Firenze, Arezzo, Lucca (plus Firenze Comune)
#   S12 Army Reserve: Siena, Provenzano, Pisa (plus Siena Comune)
ARMY_RESERVE_ELIGIBLE = {
    "guelph":     {"firenze", "firenze_comune", "arezzo", "lucca"},
    "ghibelline": {"siena", "siena_comune", "provenzano", "pisa"},
}

# Feditori eligible Lords (per S6 Tip: Siena, Provenzano, Pisa, Santa Fiora;
# F-side Feditori is "Any Guelph").
FEDITORI_S_ELIGIBLE = {"siena", "siena_comune", "provenzano", "pisa", "santa_fiora"}


def _capability_strike_modifier(state, lord_id: str, units: dict[str, int],
                                 step: str, round_n: int, mode: str = "battle") -> float:
    """Compute Capability-driven extra Strike Hits for this Lord's units.

    Returns the ADDITIONAL hits to add on top of base _strike_hits.

    Capabilities implemented:
      Feditori   — up to 4 (Guelph) / 3 (Ghib) Cavalieri Strike x2 in
                   Battle Melee R1-R2 (extra +1 each).
      Army Reserve — eligible Lord's Cavalieri Strike x2 in Battle Melee
                   from R3 on (extra +1 each).
      Balestrieri — up to 3 Armigeri get x1 Crossbow Archery.
      Arcieri    — Militia get x1 (Bowman) Archery.
      Luceria    — up to 3 Militia get x1.5 Archery (replaces Arcieri).
      Balestre Grosse — Men-at-Arms get x0.5 Crossbow Archery in Storm.
    """
    if not lord_id:
        return 0.0
    lord = state["lords"].get(lord_id) or {}
    side = lord.get("side")
    extra = 0.0

    # === Melee Steps (Battle / Storm) ===
    if "horse_melee" in step or "all_melee" in step:
        cavs = units.get("Cavalieri", 0)
        # Feditori: +1 per Cavalieri (up to cap) in R1-R2 Battle.
        if mode == "battle" and round_n <= 2 and cavs > 0:
            if _lord_has_capability(state, lord_id, "Feditori"):
                cap = 4 if side == "guelph" else 3
                extra += min(cavs, cap)
        # Army Reserve: +1 per Cavalieri R3+ Battle.
        if mode == "battle" and round_n >= 3 and cavs > 0:
            if (_lord_has_capability(state, lord_id, "Army Reserve")
                    and lord_id in ARMY_RESERVE_ELIGIBLE.get(side or "", set())):
                extra += cavs

    # === Archery Steps ===
    if "archery" in step:
        # Lord-mat Militia get Archery x1 with Arcieri, x1.5 with Luceria.
        militia = units.get("Militia", 0)
        if militia > 0:
            if _lord_has_capability(state, lord_id, "Luceria"):
                extra += min(militia, 3) * 1.5
            elif _lord_has_capability(state, lord_id, "Arcieri"):
                extra += militia * 1.0
        # Lord-mat Armigeri get Crossbow Archery x1 (Balestrieri).
        arms = units.get("Armigieri", 0)
        if arms > 0 and _lord_has_capability(state, lord_id, "Balestrieri"):
            extra += min(arms, 3) * 1.0
        # Storm-only: Men-at-Arms get Crossbow x0.5 (Balestre Grosse).
        if mode == "storm" and units.get("Men-at-Arms", 0) > 0:
            if _lord_has_capability(state, lord_id, "Balestre Grosse"):
                extra += units["Men-at-Arms"] * 0.5

    return extra


def _siege_towers_strike_first_in_storm(state, side_label: str, round_n: int,
                                         positions) -> str | None:
    """F3/S3 Siege Towers Capability: Lord Attacking in Storm from R2 on
    Strikes first with Archery and Melee. Returns the lord_id if active,
    else None."""
    if round_n < 2 or side_label != "attacker":
        return None
    for slot in SLOTS:
        lid = positions[side_label][slot]
        if lid and _lord_has_capability(state, lid, "Siege Towers"):
            return lid
    return None


def _trebuchets_walls_reduction(state, locale_name: str, defenders: list[str],
                                  attackers: list[str], mode: str) -> int:
    """F4/S4 Trebuchets Capability: 'This Lord Unrouted at Storm or Sally
    where 3-4 Siege reduces Enemy Siegeworks or Walls -1.' Returns 1 if
    Trebuchets is in effect for the appropriate side AND there are 3-4
    Siege markers, else 0.

    mode: 'storm' (defender Walls reduced) or 'sally' (besieger Siegeworks reduced).
    """
    locale = state["locales"].get(locale_name, {})
    siege_count = sum(s.get("count", 1) for s in locale.get("siege", []))
    if siege_count < 3 or siege_count > 4:
        return 0
    # In Storm: Attacker's Trebuchets reduces defender Walls.
    # In Sally: Attacker (sallying) Trebuchets reduces defender (besieger) Siegeworks.
    pool = attackers if mode in ("storm", "sally") else []
    for lid in pool:
        if _lord_has_capability(state, lid, "Trebuchets"):
            lord = state["lords"].get(lid) or {}
            # Must be Unrouted: at least one unit remaining
            if sum(lord.get("forces", {}).values()) > 0:
                return 1
    return 0


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
    # Phase 5: pre-Battle Hold Event modifiers (4.4.1 Events).
    pre_modifiers = _apply_pre_battle_modifiers(state, attacker_ids, defender_ids)

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
        # Phase 5: F4/S4 Sudden Clash inserts a special Strike before Archery in R1.
        sc_atk = _sudden_clash_target(state, "attacker", round_n)
        sc_def = _sudden_clash_target(state, "defender", round_n)
        if round_n == 1 and (sc_atk or sc_def):
            # Defender's special Sudden Clash horse melee first, then Attacker's
            if sc_def:
                _resolve_step(state, "def_horse_melee", positions, reserve, conceded,
                              bdc, _rng_roll, hit_log_round, removed_lords, routed_per_lord, round_n)
                hit_log_round.append({"sudden_clash": sc_def, "side": "defender"})
            if sc_atk:
                _resolve_step(state, "atk_horse_melee", positions, reserve, conceded,
                              bdc, _rng_roll, hit_log_round, removed_lords, routed_per_lord, round_n)
                hit_log_round.append({"sudden_clash": sc_atk, "side": "attacker"})
        for step in BATTLE_STRIKE_ORDER:
            # Skip horse_melee if already done by Sudden Clash this round
            if round_n == 1:
                if step == "def_horse_melee" and sc_def:
                    continue
                if step == "atk_horse_melee" and sc_atk:
                    continue
            _resolve_step(state, step, positions, reserve, conceded,
                          bdc, _rng_roll, hit_log_round, removed_lords, routed_per_lord, round_n)
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

    # Phase 5: clear consumed Hold Events per 4.4.6 Aftermath.
    _clear_battle_modifiers(state)
    return {
        "locale": locale_name,
        "winner": winner,
        "pre_modifiers": pre_modifiers,
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
    pending_wm = [m for m in state.get("battle_modifiers_pending", [])
                  if m.get("effect") == "storm_walls_minus"]
    for m in pending_wm:
        storm_walls_minus += m.get("value", 1)
        state["battle_modifiers_pending"].remove(m)
    if storm_walls_minus and walls_die:
        walls_die = walls_die[:-storm_walls_minus] if len(walls_die) > storm_walls_minus else []
    # Phase 6: Trebuchets — Storm Attacker reduces Defender Walls by 1 if
    # the attackers control a Lord with Trebuchets and there are 3-4 Sieges.
    trebuchets_reduction = _trebuchets_walls_reduction(
        state, locale_name, defenders, attackers, "storm",
    )
    if trebuchets_reduction and walls_die:
        walls_die = walls_die[:-trebuchets_reduction] if len(walls_die) > trebuchets_reduction else []
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
        if striking_side == "defender":
            units = dict(units)
            for u, c in state["storm_garrison"][locale_name].items():
                units[u] = units.get(u, 0) + c
        h = _strike_hits_storm(units, step)
        # Phase 6: Capability strike modifiers in Storm context
        h += _capability_strike_modifier(state, striker_id, units, step, 1, "storm")
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
        # SMOKE-Inferno-048: Concede+Retreat Spoils transfer Provender BEYOND
        # what the loser could carry Unladen (Battle&Storm 11.3 / 4.4.3). The
        # Unladen carry is up to 2x Provender per Cart on Road (Commands 4.3.2),
        # so the excess given as Spoils is prov - 2*Carts (was prov - Carts).
        carts = loser["assets"].get("Cart", 0)
        prov = loser["assets"].get("Provender", 0)
        excess_prov = max(0, prov - 2 * carts)
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
