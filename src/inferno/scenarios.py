"""Scenario loader — Phase 0 stub.

Phase 1 implements the real loader against src/inferno/data/scenarios/*.json.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

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
    """Return [{id, name}, ...] for the six published scenarios."""
    return [{"id": sid, "name": SCENARIO_NAMES[sid]} for sid in SCENARIO_IDS]


def load_scenario_data(scenario_id: str) -> dict[str, Any]:
    """Load the raw scenario JSON for the given id.

    Phase 0 returns the stub data with only metadata filled in. Phase 1
    populates the setup block and adds validation.
    """
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
