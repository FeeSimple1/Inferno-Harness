"""Scenario loader.

Builds a fully-initialized State by merging:
  - static_data (Lords, Locales, Ways, Strongholds, Forces — scenario-independent)
  - data/scenarios/<id>_*.json (per-scenario setup block)

Per BRIEF: state files are portable JSON; loading reconstructs the game.
"""

from __future__ import annotations

import copy
import json
from importlib import resources
from typing import Any

from . import static_data as sd
from .state import (
    BoxState,
    Calendar,
    DeckState,
    LocaleState,
    LordState,
    Meta,
    State,
    VassalState,
)


SCENARIO_IDS = ["A", "B", "C", "D", "E", "F"]

SCENARIO_NAMES: dict[str, str] = {
    "A": "Dolenti Note",
    "B": "In Far Vendetta",
    "C": "Santafior Oscura",
    "D": "Arbia Colorata in Rosso",
    "E": "Lasciate Ogne Speranza",
    "F": "Di Sangue t'Empio",
}


def list_scenarios() -> list[dict[str, str]]:
    return [{"id": sid, "name": SCENARIO_NAMES[sid]} for sid in SCENARIO_IDS]


def load_scenario_data(scenario_id: str) -> dict[str, Any]:
    if scenario_id not in SCENARIO_IDS:
        raise ValueError(
            f"Unknown scenario {scenario_id!r}; expected one of {SCENARIO_IDS}."
        )
    filename = _scenario_filename(scenario_id)
    with resources.files("inferno.data.scenarios").joinpath(filename).open() as f:
        return json.load(f)


def _scenario_filename(scenario_id: str) -> str:
    name = SCENARIO_NAMES[scenario_id]
    slug = name.lower().replace(" ", "_").replace("'", "").replace(",", "")
    return f"{scenario_id}_{slug}.json"


# =====================================================================
# Loader
# =====================================================================
def load_scenario(scenario_id: str, seed: int) -> State:
    """Build a fully-initialized State from the given scenario id and RNG seed."""
    data = load_scenario_data(scenario_id)
    state: State = {
        "meta": _init_meta(scenario_id, seed, data),
        "calendar": _init_calendar(data),
        "lords": _init_lords(data),
        "locales": _init_locales(data),
        "decks": _init_decks(),
        "capabilities_in_play": list(data["map"].get("capabilities_in_play", [])),
        "pending": [],
        "history": [],
        "vp": {"guelph": 0.0, "ghibelline": 0.0},
    }
    _wire_lords_into_locales(state)
    return state


# ---------------------------------------------------------------- meta
def _init_meta(scenario_id: str, seed: int, data: dict[str, Any]) -> Meta:
    return Meta(
        scenario=scenario_id,
        rules_edition="living_rules_2023-04-10",
        rng_seed=seed,
        turn=data["calendar"]["levy_box"],
        phase="levy",
        levy_step="3.1",
        active_player="guelph",
        game_over=False,
        winner=None,
    )


# ---------------------------------------------------------------- calendar
def _init_calendar(data: dict[str, Any]) -> Calendar:
    cal = data["calendar"]
    boxes: dict[str, BoxState] = {}
    for n in sd.CALENDAR_BOXES:
        box: BoxState = BoxState(cylinders=[], services=[], victory=[], markers=[])
        # Cylinders waiting at this box
        for lid in cal.get("cylinders_on_calendar", {}).get(str(n), []):
            box["cylinders"].append(lid)
        # Service markers at this box
        for lid in cal.get("services_on_calendar", {}).get(str(n), []):
            box["services"].append(lid)
        # Victory markers
        box["victory"].extend(cal.get("victory_boxes", {}).get(str(n), []))
        # Levy / End markers
        if n == cal["levy_box"]:
            box["markers"].append("levy")
        if cal.get("end_box") and n == cal["end_box"]:
            box["markers"].append("end")
        boxes[str(n)] = box
    return Calendar(
        boxes=boxes,
        off_left=[],
        off_right=[],
        off_left_service=[],
        off_right_service=[],
        end_box=cal.get("end_box"),
        levy_box=cal["levy_box"],
    )


# ---------------------------------------------------------------- lords
def _init_lords(data: dict[str, Any]) -> dict[str, LordState]:
    mustered = set(data["mustered"]["guelph"] + data["mustered"]["ghibelline"])
    removed = set(data["removed_from_play"])
    # Which Lords have cylinders waiting on the Calendar?
    on_calendar: dict[str, int] = {}
    for box_str, lids in data["calendar"].get("cylinders_on_calendar", {}).items():
        for lid in lids:
            on_calendar[lid] = int(box_str)
    # Locations for Mustered Lords
    lord_locations = data["map"].get("lord_locations", {})
    assets_override = data.get("starting_assets_override", {})

    out: dict[str, LordState] = {}
    for canonical_name, lord_data in sd.LORDS.items():
        lid = sd.LORD_IDS[canonical_name]
        if lid in on_calendar:
            status = "on_calendar"
            location: str | None = None
            cylinder_box: int | None = on_calendar[lid]
            forces: dict[str, int] = {}
            assets: dict[str, int] = {}
            vassals: list[VassalState] = []
            capabilities: list[str] = []
        elif lid in removed:
            status = "removed"
            location = None
            cylinder_box = None
            forces = {}
            assets = {}
            vassals = []
            capabilities = []
        elif lid in mustered:
            status = "mustered"
            location = lord_locations.get(lid)
            cylinder_box = None
            forces = copy.deepcopy(lord_data.get("forces", {}))
            assets = copy.deepcopy(lord_data.get("assets", {}))
            # Per-scenario asset overrides (add to base, do not replace)
            for asset, delta in assets_override.get(lid, {}).items():
                assets[asset] = assets.get(asset, 0) + delta
            vassals = _init_vassals_for(lord_data)
            capabilities = []
        else:
            status = "in_levy_pool"
            location = None
            cylinder_box = None
            forces = {}
            assets = {}
            vassals = []
            capabilities = []

        # Service box: for Mustered Lords whose Service marker is on Calendar
        service_box: int | None = None
        for box_str, lids in data["calendar"].get("services_on_calendar", {}).items():
            if lid in lids:
                service_box = int(box_str)
                break

        out[lid] = LordState(
            name=canonical_name,
            side=lord_data["side"],
            podesta=lord_data.get("podesta", False),
            commander=lord_data.get("commander", False),
            comune_of=lord_data.get("comune_of"),
            seats=list(lord_data.get("seats", [])),
            ratings=copy.deepcopy(lord_data.get("ratings", {})),
            status=status,
            location=location,
            calendar_box=cylinder_box,
            service_box=service_box,
            forces=forces,
            assets=assets,
            vassals=vassals,
            capabilities=capabilities,
            routed_units={},
            flags={},
            notes=lord_data.get("notes", ""),
        )
    return out


def _init_vassals_for(lord_data: dict[str, Any]) -> list[VassalState]:
    vassals_out: list[VassalState] = []
    for v in lord_data.get("vassals", []):
        vassal: VassalState = VassalState(
            name=v["name"],
            seat=v.get("seat"),
            seats=v.get("seats", []),
            service_rating=v.get("service_rating", 0),
            forces=copy.deepcopy(v.get("forces", {})),
            special=v.get("special", False),
            muster_die=v.get("muster_die"),
            vp_if_captured=v.get("vp_if_captured"),
            # Default: non-Special Vassals are on the mat, Ready (3.4.1).
            # Special Vassals (Carroccio/Sestieri/Terzi) Muster only via CtA.
            on_mat=not v.get("special", False),
            ready=not v.get("special", False),
            service_box=None,
        )
        vassals_out.append(vassal)
    return vassals_out


# ---------------------------------------------------------------- locales
def _init_locales(data: dict[str, Any]) -> dict[str, LocaleState]:
    out: dict[str, LocaleState] = {}
    map_block = data["map"]
    for name, base in sd.LOCALES.items():
        ravaged = map_block.get("ravaged", {}).get(name)
        ruins = map_block.get("ruins", {}).get(name)
        siege_markers = map_block.get("siege", {}).get(name, [])
        bypass_markers = map_block.get("bypass", {}).get(name, [])
        allegiance_markers = list(map_block.get("allegiance_markers", {}).get(name, []))
        out[name] = LocaleState(
            name=name,
            type=base["type"],
            region=base["region"],
            allegiance=base["allegiance"],
            port=base.get("port", False),
            leading_city=base.get("leading_city"),
            current_allegiance=allegiance_markers,
            ravaged=ravaged,
            ruins=ruins,
            siege=list(siege_markers),
            bypass=list(bypass_markers),
            siegeworks=0,
            walls_plus_one=None,
            castle_overlay=None,
            lords_present=[],
        )
    return out


def _wire_lords_into_locales(state: State) -> None:
    """Push Mustered Lord locations into the locales[*].lords_present list."""
    for lid, lord in state["lords"].items():
        if lord["status"] == "mustered" and lord.get("location"):
            loc = state["locales"].get(lord["location"])
            if loc is None:
                continue
            loc["lords_present"].append(lid)


# ---------------------------------------------------------------- decks
def _init_decks() -> dict[str, DeckState]:
    """Phase 1: deck composition is a stub. Phase 2 (Levy) populates the
    real AoW and Command decks from card data.
    """
    return {
        "guelph": DeckState(
            aow_deck=[],
            aow_discard=[],
            aow_held=[],
            command_deck=[],
            treachery_set_aside=[],
        ),
        "ghibelline": DeckState(
            aow_deck=[],
            aow_discard=[],
            aow_held=[],
            command_deck=[],
            treachery_set_aside=[],
        ),
    }
