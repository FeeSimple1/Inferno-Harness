"""State model TypedDicts.

The state is a single JSON-serializable object. Loading a state file fully
reconstructs the game (BRIEF "Architecture Requirements").

These TypedDicts describe shape, not behaviour. The harness validates state
against this shape on load. Phase 1 fills in the basic fields; later phases
extend the optional fields as needed (e.g., per-Lord flags, deck state,
pending sub-decision structure).
"""

from __future__ import annotations

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
    history: list[ActionResult]
    vp: dict[str, float]
