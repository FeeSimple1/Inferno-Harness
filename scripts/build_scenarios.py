"""Populate scenario JSON setup blocks A-F from Inferno_Scenario_Reference.txt.

Each scenario lists:
  - mustered: lord_id -> initial Locale
  - calendar: box_number -> {markers, cylinders, services}
  - map_markers: locale -> {allegiance_markers, ravaged, ruins, siege}
  - removed: [lord_id, ...]
  - special_rules: [strings]
  - end_box: int
  - levy_box: int (starting Levy box)

Phase 1 captures the data faithfully but does not yet enforce game logic
(that's Phase 2+). The state loader uses this to populate State.

Run from repo root:
  python3 scripts/build_scenarios.py
"""
from __future__ import annotations
import json
from pathlib import Path

OUT_DIR = Path(__file__).parent.parent / "src" / "inferno" / "data" / "scenarios"


# Each scenario keyed by its single-letter id.
SCENARIOS = {
    # =====================================================================
    # A. DOLENTI NOTE — "Notes of Pain"
    # =====================================================================
    "A": {
        "scenario_id": "A",
        "name": "Dolenti Note",
        "subtitle": "Notes of Pain",
        "length_note": "Introductory, two Turns; Feb-Mar 1259 (box 1) Levy through Apr-May 1259 (box 2)",
        "calendar": {
            "first_turn_box": 1,
            "last_turn_box": 2,
            "end_box": 3,
            "levy_box": 1,
            "victory_boxes": {"4": ["purple", "gold"]},
            "cylinders_on_calendar": {"1": ["provenzano"]},
            "services_on_calendar": {"3": ["firenze", "arezzo", "siena"]},
        },
        "map": {
            "lord_locations": {
                "firenze": "Firenze",
                "arezzo": "Arezzo",
                "siena": "Siena",
            },
            "allegiance_markers": {
                "Montalcino": [{"side": "guelph", "value": 1}, {"side": "guelph", "value": 1}],
                "Montepulciano": [{"side": "guelph", "value": 1}, {"side": "guelph", "value": 1}],
                "Poggio Bonizio": [{"side": "ghibelline", "value": 1}, {"side": "ghibelline", "value": 1}],
                "Cortona": [{"side": "ghibelline", "value": 1}, {"side": "ghibelline", "value": 1}],
            },
            "ravaged": {},
            "ruins": {},
            "siege": {},
            "bypass": {},
            "capabilities_in_play": [],
            "held_events": {"guelph": ["F3"]},  # Night March
        },
        "mustered": {
            "guelph": ["firenze", "arezzo"],
            "ghibelline": ["siena"],
        },
        "removed_from_play": [
            "pisa", "astimberg", "santa_fiora", "giordano",
            "siena_comune", "orvieto", "guido_guerra", "colle", "lucca",
            "firenze_comune",
        ],
        "special_rules": [
            "night_march",       # Guelphs begin Holding F3 Surprise
            "sudden_campaign",   # First Levy AoW: draw 1 Capability + 1 Event
            "preamble",          # Skip all Call to Arms (3.5)
        ],
    },

    # =====================================================================
    # B. IN FAR VENDETTA — "[Honor] in Vengeance"
    # =====================================================================
    "B": {
        "scenario_id": "B",
        "name": "In Far Vendetta",
        "subtitle": "[Honor] in Vengeance",
        "length_note": "Medium, up to five Turns; Aug-Sep 1259 (box 4) Levy through end of Apr-May 1260 (box 8)",
        "calendar": {
            "first_turn_box": 4,
            "last_turn_box": 8,
            "end_box": 9,
            "levy_box": 4,
            "victory_boxes": {"5": ["gold"], "6": ["purple"]},
            "cylinders_on_calendar": {
                "4": ["colle", "santa_fiora"],
                "5": ["giordano"],
                "7": ["guido_guerra", "astimberg"],
                "8": ["orvieto"],
                "9": ["lucca", "pisa"],
            },
            "services_on_calendar": {
                "6": ["firenze", "arezzo", "siena", "provenzano"],
            },
        },
        "map": {
            "lord_locations": {
                "firenze": "Firenze",
                "arezzo": "Arezzo",
                "siena": "Siena",
                "provenzano": "Siena",
            },
            "allegiance_markers": {
                "Volterra": [{"side": "guelph", "value": 1}, {"side": "guelph", "value": 1}],
                "Montalcino": [{"side": "guelph", "value": 1}, {"side": "guelph", "value": 1}],
                "Montepulciano": [{"side": "guelph", "value": 1}, {"side": "guelph", "value": 1}],
                "Poggio Bonizio": [{"side": "ghibelline", "value": 1}, {"side": "ghibelline", "value": 1}],
            },
            "ravaged": {
                "Monte San Savino": "gold",
                "Castelnuovo Berardenga": "gold",
                "Cortona": "gold",
            },
            "ruins": {
                "Monte San Savino": "gold",
                "Castelnuovo Berardenga": "gold",
                "Cortona": "gold",
            },
            "siege": {},
            "bypass": {},
            "capabilities_in_play": [],
            "held_events": {},
        },
        "mustered": {
            "guelph": ["firenze", "arezzo"],
            "ghibelline": ["siena", "provenzano"],
        },
        "removed_from_play": [],
        "special_rules": [
            "reprisal_war",  # Ghibellines assign S18/S19/S20, skip Grow step of Turn 5
        ],
        "scenario_notes": [
            "Reprisal War: Before first AoW draw, Ghibellines assign S18 La Cavallata, S19 Gualdana, S20 Masnadieri to their Lords; then draw two more as usual. Skip the Grow step (4.9.2) of Autumn 1259 (Turn 5) only.",
        ],
    },

    # =====================================================================
    # C. SANTAFIOR OSCURA — "Dark Santa Fiora"
    # =====================================================================
    "C": {
        "scenario_id": "C",
        "name": "Santafior Oscura",
        "subtitle": "Dark Santa Fiora",
        "length_note": "Short, three Turns; Winter 1259-1260 Levy (box 6) through Apr-May 1260 (box 8)",
        "calendar": {
            "first_turn_box": 6,
            "last_turn_box": 8,
            "end_box": 9,
            "levy_box": 6,
            "victory_boxes": {"9": ["gold"], "10": ["purple"]},
            "cylinders_on_calendar": {
                "6": ["firenze", "siena", "provenzano"],
                "8": ["guido_guerra", "santa_fiora"],
                "9": ["lucca", "pisa"],
            },
            "services_on_calendar": {
                "8": ["colle", "giordano"],
            },
        },
        "map": {
            "lord_locations": {
                "colle": "Colle",
                "giordano": "Siena",
            },
            "allegiance_markers": {
                "Volterra": [{"side": "guelph", "value": 1}, {"side": "guelph", "value": 1}],
                "Montalcino": [{"side": "guelph", "value": 1}, {"side": "guelph", "value": 1}],
                "Montepulciano": [{"side": "guelph", "value": 1}, {"side": "guelph", "value": 1}],
                "Grosseto": [{"side": "guelph", "value": 1}, {"side": "guelph", "value": 1}],
                "Montemassi": [{"side": "guelph", "value": 1}],
                "Montepescali": [{"side": "guelph", "value": 1}],
                "Poggio Bonizio": [{"side": "ghibelline", "value": 1}, {"side": "ghibelline", "value": 1}],
            },
            "ravaged": {
                "Colle": "gold",
                "Montespertoli": "gold",
                "San Casciano": "gold",
                "Barberino": "gold",
                "Castelnuovo Berardenga": "gold",
                "Monte San Savino": "gold",
            },
            "ruins": {
                "Castelnuovo Berardenga": "gold",
                "Monte San Savino": "gold",
            },
            "siege": {},
            "bypass": {},
            "capabilities_in_play": [
                {"id": "S22", "name": "Manfredi", "side": "ghibelline", "scope": "side_wide"},
            ],
            "held_events": {},
        },
        "mustered": {
            "guelph": ["colle"],
            "ghibelline": ["giordano"],
        },
        "removed_from_play": ["arezzo", "orvieto", "astimberg"],
        "special_rules": [
            "alliance_treaty",  # S22 Manfredi adds +3 VP to Ghibellines
            "maremma_war",      # Ghib-only CtA first Levy; no other CtA; line cross rule; Grosseto rapid-surrender
        ],
        "scenario_notes": [
            "Alliance Treaty: S22 Manfredi Capability adds 3 VP to the Ghibelline score.",
            "Maremma War: Ghibellines (only) conduct CtA in first Levy; skip all other CtA. Ghibelline Lords may not cross the dashed line until Guelphs place a Siege or Ravage marker. Grosseto with 2 Siege markers and no Lord inside Surrenders at once.",
        ],
    },

    # =====================================================================
    # D. ARBIA COLORATA IN ROSSO — "Arbia Dyed Red"
    # =====================================================================
    "D": {
        "scenario_id": "D",
        "name": "Arbia Colorata in Rosso",
        "subtitle": "Arbia Dyed Red",
        "length_note": "Three Turns; Jun-Jul 1260 (box 9) through Oct-Nov 1260 (box 11)",
        "calendar": {
            "first_turn_box": 9,
            "last_turn_box": 11,
            "end_box": 12,
            "levy_box": 9,
            "victory_boxes": {"5": ["gold"], "7": ["purple"]},
            "cylinders_on_calendar": {
                "9": ["firenze", "lucca", "siena", "pisa"],
            },
            "services_on_calendar": {
                "10": ["santa_fiora"],
                "11": ["arezzo", "colle", "orvieto", "giordano", "provenzano", "astimberg"],
                "12": ["guido_guerra"],
            },
        },
        "map": {
            "lord_locations": {
                "guido_guerra": "Lombardia-Bologna West",
                "arezzo": "Arezzo",
                "orvieto": "Arezzo",
                "colle": "Colle",
                "astimberg": "Siena",
                "provenzano": "Montepulciano",
                "santa_fiora": "Montepulciano",
                "giordano": "Massa Marittima",
            },
            "allegiance_markers": {
                "Volterra": [{"side": "guelph", "value": 1}, {"side": "guelph", "value": 1}],
                "Montalcino": [{"side": "guelph", "value": 1}, {"side": "guelph", "value": 1}],
                "Montepulciano": [{"side": "guelph", "value": 1}, {"side": "guelph", "value": 1}],
                "Casole": [{"side": "guelph", "value": 1}],
                "Poggio Bonizio": [{"side": "ghibelline", "value": 1}, {"side": "ghibelline", "value": 1}],
            },
            "ravaged": {
                "Montespertoli": "gold",
                "Barberino": "gold",
                "San Casciano": "gold",
                "Monte San Savino": "gold",
            },
            "ruins": {
                "Castelnuovo Berardenga": "gold",
                "Monte San Savino": "gold",
            },
            "siege": {
                "Montepulciano": [{"side": "ghibelline", "color": "gold", "count": 2}],
            },
            "bypass": {},
            "capabilities_in_play": [],
            "held_events": {},
        },
        "mustered": {
            "guelph": ["arezzo", "colle", "guido_guerra", "orvieto"],
            "ghibelline": ["giordano", "provenzano", "astimberg", "santa_fiora"],
        },
        "removed_from_play": [],
        "special_rules": [
            "escalation",  # First Levy: either side may trigger CtA as if it had drawn a WAR Event
        ],
    },

    # =====================================================================
    # E. LASCIATE OGNE SPERANZA — "Abandon All Hope"
    # =====================================================================
    "E": {
        "scenario_id": "E",
        "name": "Lasciate Ogne Speranza",
        "subtitle": "Abandon All Hope",
        "length_note": "Three Turns; Dec 1260 (box 12) through May 1261 (box 14)",
        "calendar": {
            "first_turn_box": 12,
            "last_turn_box": 14,
            "end_box": 15,
            "levy_box": 12,
            "victory_boxes": {"6": ["purple"], "7": ["yellow"]},
            "cylinders_on_calendar": {
                "12": ["siena", "pisa"],
                "13": ["firenze", "colle", "orvieto"],
            },
            "services_on_calendar": {
                "14": ["arezzo", "lucca", "giordano", "astimberg"],
            },
        },
        "map": {
            "lord_locations": {
                "lucca": "Lucca",
                "arezzo": "Arezzo",
                "giordano": "Firenze",
                "astimberg": "Siena",
            },
            "allegiance_markers": {
                "Firenze": [
                    {"side": "ghibelline", "value": 1},
                    {"side": "ghibelline", "value": 1},
                    {"side": "ghibelline", "value": 1},
                ],
                "San Casciano": [{"side": "ghibelline", "value": 1}],
                "Barberino": [{"side": "ghibelline", "value": 1}],
            },
            "ravaged": {
                "San Casciano": "gold",
                "Barberino": "gold",
                "Castelnuovo Berardenga": "gold",
                "Castiglione": "gold",
                "Monteriggioni": "purple",
                "Casole": "purple",
                "Montemassi": "purple",
                "Montepulciano": "purple",
            },
            "ruins": {
                "Monteriggioni": "purple",
                "Casole": "purple",
                "Montemassi": "purple",
                "Montepulciano": "purple",
            },
            "siege": {},
            "bypass": {},
            "capabilities_in_play": [
                {"id": "S23", "name": "Taglia", "side": "ghibelline", "scope": "side_wide"},
            ],
            "held_events": {},
        },
        "mustered": {
            "guelph": ["lucca", "arezzo"],
            "ghibelline": ["giordano", "astimberg"],
        },
        "removed_from_play": [
            "guido_guerra",
            "provenzano", "santa_fiora",
            "siena_comune", "firenze_comune",
        ],
        "special_rules": [
            "league",            # Ghibellines begin with S23 Taglia Capability
            "spoils_of_victory", # Giordano starts with two Coin
            "resistance",        # Before first Levy: Lucca and Arezzo each conduct an extra Muster; double Guelph VP except for Ravaged
            "exhaustion",        # Skip all Call to Arms
        ],
        "starting_assets_override": {
            "giordano": {"Coin": 2},
        },
        "scenario_notes": [
            "Resistance: Before first Levy, Lucca and Arezzo each conduct an extra Muster (3.4). Double Guelph VP except for Ravaged (5.1).",
        ],
    },

    # =====================================================================
    # F. DI SANGUE T'EMPIO — "Your Fill of Blood"
    # =====================================================================
    "F": {
        "scenario_id": "F",
        "name": "Di Sangue t'Empio",
        "subtitle": "Your Fill of Blood",
        "length_note": "Full-length; Feb-Mar 1259 (box 1) through end of Aug-Sep 1261 (up to 16 Turns), variable Exhaustion end",
        "calendar": {
            "first_turn_box": 1,
            "last_turn_box": 16,
            "end_box": None,           # Set by Exhaustion rolls
            "levy_box": 1,
            "victory_boxes": {"4": ["gold"], "6": ["purple"]},
            "cylinders_on_calendar": {
                "1": ["provenzano"],
                "3": ["colle"],
                "4": ["santa_fiora"],
                "5": ["giordano"],
                "7": ["guido_guerra", "astimberg"],
                "8": ["orvieto"],
                "9": ["lucca", "pisa"],
            },
            "services_on_calendar": {
                "3": ["firenze", "arezzo", "siena"],
            },
        },
        "map": {
            "lord_locations": {
                "firenze": "Firenze",
                "arezzo": "Arezzo",
                "siena": "Siena",
            },
            "allegiance_markers": {
                "Volterra": [{"side": "guelph", "value": 1}, {"side": "guelph", "value": 1}],
                "Montalcino": [{"side": "guelph", "value": 1}, {"side": "guelph", "value": 1}],
                "Montepulciano": [{"side": "guelph", "value": 1}, {"side": "guelph", "value": 1}],
                "Poggio Bonizio": [{"side": "ghibelline", "value": 1}, {"side": "ghibelline", "value": 1}],
                "Cortona": [{"side": "ghibelline", "value": 1}, {"side": "ghibelline", "value": 1}],
            },
            "ravaged": {},
            "ruins": {},
            "siege": {},
            "bypass": {},
            "capabilities_in_play": [],
            "held_events": {"guelph": ["F3"]},  # Night March
        },
        "mustered": {
            "guelph": ["firenze", "arezzo"],
            "ghibelline": ["siena"],
        },
        "removed_from_play": [],
        "special_rules": [
            "night_march",   # Guelphs begin Holding F3 Surprise
            "exhaustion",    # From Turn 9 onward, roll 1d6 each Levy; on 1-3, place/slide End marker
        ],
    },
}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    slugs = {
        "A": "dolenti_note",
        "B": "in_far_vendetta",
        "C": "santafior_oscura",
        "D": "arbia_colorata_in_rosso",
        "E": "lasciate_ogne_speranza",
        "F": "di_sangue_tempio",
    }
    for sid, data in SCENARIOS.items():
        data["$schema"] = "../state_schema.json"
        path = OUT_DIR / f"{sid}_{slugs[sid]}.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        print(f"  wrote {path.name}: {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
