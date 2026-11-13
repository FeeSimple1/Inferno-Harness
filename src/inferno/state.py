"""State model TypedDicts.

The state is a single JSON-serializable object. Loading a state file fully
reconstructs the game (BRIEF "Architecture Requirements").

These TypedDicts describe shape, not behaviour. The harness validates state
against this shape on load. Phase 1 fills in the basic fields; later phases
extend the optional fields as needed (e.g., per-Lord flags, deck state,
pending sub-decision structure).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal, TypedDict

Side = Literal["guelph", "ghibelline"]
WayType = Literal["road", "track"]
LordStatus = Literal["mustered", "on_calendar", "in_levy_pool", "disbanded", "removed"]
PhaseName = Literal["levy", "campaign", "feed_pay_disband", "end_campaign", "victory"]
StrongholdType = Literal["city", "town", "castle", "outpost"]


# -----------------------------------------------------------------
class Meta(TypedDict, total=False):
    scenario: str
    rules_edition: str
    rng_seed: int
    turn: int
    phase: PhaseName
    levy_step: str | None
    active_player: Side
    game_over: bool
    winner: Side | None
    reset_started: bool


# -----------------------------------------------------------------
class VassalState(TypedDict, total=False):
    name: str
    seat: str | None
    seats: list[str]
    service_rating: int
    forces: dict[str, int]
    special: bool
    muster_die: int | None
    vp_if_captured: dict[str, Any] | None
    # Per-Lord runtime state (Phase 2+ extends):
    on_mat: bool         # has the Vassal been Mustered onto the Lord's mat
    ready: bool          # Vassal Service marker face up (Ready) vs face down (Used)
    service_box: int | None  # Calendar box if advanced Vassal Service rule active


class LordState(TypedDict, total=False):
    name: str
    side: Side
    podesta: bool
    commander: bool
    comune_of: str | None
    seats: list[str]
    ratings: dict[str, int]   # F/S/L/C
    status: LordStatus        # "mustered" | "on_calendar" | "in_levy_pool" | "disbanded" | "removed"
    location: str | None      # locale name when mustered on map; None otherwise
    calendar_box: int | None  # box where Lord's cylinder waits to enter (status="on_calendar")
    service_box: int | None   # current Service marker box (None if off-Calendar)
    forces: dict[str, int]
    assets: dict[str, int]
    vassals: list[VassalState]
    capabilities: list[str]   # card ids tucked under this Lord's mat (this_lord scope)
    routed_units: dict[str, int]
    flags: dict[str, Any]     # moved_fought, in_stronghold, etc. — populated in Phase 3+
    notes: str


# -----------------------------------------------------------------
class AllegianceMarker(TypedDict):
    side: Side
    value: int


class SiegeMarker(TypedDict, total=False):
    side: Side
    color: str   # "gold" / "purple"
    count: int


class BypassMarker(TypedDict, total=False):
    side: Side


class StrongholdArrival(TypedDict, total=False):
    side: Side
    lord_id: str
    locale: str
    group: list[str]
    empty_on_arrival: bool
    after_battle: bool


class LocaleState(TypedDict, total=False):
    name: str
    type: StrongholdType
    region: Literal["north", "south"]
    allegiance: Side             # printed
    port: bool
    leading_city: Side | None
    current_allegiance: list[AllegianceMarker]
    ravaged: str | None          # color of the Ravaged marker, or None
    ruins: str | None            # color of the Ruins marker, or None
    siege: list[SiegeMarker]
    bypass: list[BypassMarker]
    siegeworks: int              # Walls+1 (Reinforced Walls or Costruttori)
    walls_plus_one: Side | None  # which side placed the Walls+1 overlay, if any
    castle_overlay: Side | None  # Stonemasons-equivalent overlay (none in Inferno; reserved)
    lords_present: list[str]     # lord_ids currently here


# -----------------------------------------------------------------
class Calendar(TypedDict, total=False):
    boxes: dict[str, BoxState]   # "1".."16"
    off_left: list[str]
    off_right: list[str]
    off_left_service: list[str]
    off_right_service: list[str]
    end_box: int | None          # box where End marker sits (None until placed)
    levy_box: int                # current Levy/Campaign marker box


class BoxState(TypedDict, total=False):
    cylinders: list[str]         # lord_ids waiting in this box
    services: list[str]          # lord_ids with Service marker in this box
    victory: list[str]           # ["gold", "purple", "yellow"]
    markers: list[str]           # ["levy", "end", ...]


# -----------------------------------------------------------------
class DeckState(TypedDict, total=False):
    aow_deck: list[str]
    aow_discard: list[str]
    aow_held: list[str]
    command_deck: list[str | None]      # lord_id OR None for Treachery cards
    treachery_set_aside: list[str]


class CapabilityInPlay(TypedDict, total=False):
    id: str
    name: str
    side: Side
    scope: Literal["this_lord", "side_wide"]
    lord_id: str | None    # for this_lord scope


# -----------------------------------------------------------------
class PendingDecision(TypedDict, total=False):
    """A decision the engine is waiting on from a player.

    See BRIEF "Non-Combat Pending Decisions" for the list of types Phase 3
    introduces. Phase 1 doesn't generate any pending decisions but the
    schema slot is reserved.
    """
    type: str        # e.g. "besiege_or_bypass", "approach_response"
    side: Side       # who owes the response
    options: list[Any]
    info: dict[str, Any]


class ActionResult(TypedDict, total=False):
    action: str
    side: Side
    args: dict[str, Any]
    rolls: list[dict[str, Any]]
    state_changes: dict[str, Any]
    rule_citation: str | None


# -----------------------------------------------------------------
class State(TypedDict, total=False):
    meta: Meta
    calendar: Calendar
    lords: dict[str, LordState]
    locales: dict[str, LocaleState]
    decks: dict[str, DeckState]
    capabilities_in_play: list[CapabilityInPlay]
    pending: list[PendingDecision]
    pending_besiege: StrongholdArrival
    bypass_this_card: str
    history: list[ActionResult]
    vp: dict[str, float]


def same_lieutenant_position(first: LordState, second: LordState) -> bool:
    """Two cylinders can stack only at the same position within a Locale."""
    return (first.get("location") is not None
            and first.get("location") == second.get("location")
            and bool(first.get("flags", {}).get("in_stronghold"))
            == bool(second.get("flags", {}).get("in_stronghold")))


def valid_lieutenant_pairs(state: State) -> dict[str, str]:
    """Return the unambiguous reciprocal upper-to-lower links (4.1.3)."""
    lords = state.get("lords", {})
    candidates = {}
    for upper_id, upper in lords.items():
        lower_id = upper.get("flags", {}).get("has_lower_lord")
        if not isinstance(lower_id, str) or lower_id == upper_id or lower_id not in lords:
            continue
        lower = lords[lower_id]
        if (lower.get("flags", {}).get("lower_lord_of") == upper_id
                and upper.get("status") == lower.get("status") == "mustered"
                and upper.get("side") == lower.get("side")
                and same_lieutenant_position(upper, lower)
                and not any(lord.get("commander") or lord.get("comune_of") for lord in (upper, lower))):
            candidates[upper_id] = lower_id
    memberships = Counter(lid for pair in candidates.items() for lid in pair)
    return {upper: lower for upper, lower in candidates.items()
            if memberships[upper] == memberships[lower] == 1}


def restore_lieutenant_links(state: State) -> None:
    """Clear stale links from a loaded save while retaining intact pairs."""
    lowers = valid_lieutenant_pairs(state)
    uppers = {lower: upper for upper, lower in lowers.items()}
    for lid, lord in state.get("lords", {}).items():
        flags = lord.get("flags", {})
        if flags.get("has_lower_lord") != lowers.get(lid):
            flags.pop("has_lower_lord", None)
        if flags.get("lower_lord_of") != uppers.get(lid):
            flags.pop("lower_lord_of", None)


def clear_bypass(state: State, locale_name: str) -> None:
    """Remove a Bypass and the corresponding flags on Lords at the Locale."""
    loc = state["locales"][locale_name]
    loc["bypass"] = []
    for lid in loc.get("lords_present", []):
        flags = state["lords"][lid].get("flags", {})
        if flags.get("bypassing") == locale_name:
            flags.pop("bypassing")


def load_saved_state(path: Path) -> State:
    """Read a saved game and repair stale links and Bypass markers."""
    state = json.loads(path.read_text(encoding="utf-8"))
    restore_lieutenant_links(state)
    for name, loc in state.get("locales", {}).items():
        if loc.get("siege") and loc.get("bypass"):
            # Older Sail arrivals left the Bypass behind after placing Siege.
            clear_bypass(state, name)
    return state
