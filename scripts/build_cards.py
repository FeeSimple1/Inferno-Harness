"""Extract card metadata for Phase 2 deck setup.

Phase 2 needs card IDs, names, side, is_war flag, and a hold/immediate hint
for the draw flow. Per-card EFFECTS are deferred to Phase 4 per BRIEF.

Source: reference/Inferno_Arts_of_War_Reference.txt (designer-clarified).
"""
from __future__ import annotations
import json
from pathlib import Path

OUT = Path(__file__).parent.parent / "src" / "inferno" / "card_data.py"

# Card list compiled from the AoW reference (F1-F26 + S1-S26 each have both
# an Event half and a Capability half; only one is in effect at a time).
# is_war flag from 3.5 trigger conditions and Playbook p.64:
#   Guelph War events: F25 Val d'Orcia, F26 Montalcino
#   Ghibelline War events: S25 Maremma, S26 Montepulciano
# event_kind from AoW reference (hold/immediate/this_levy/this_campaign):
#   - extracted by reading each card's event text. "Hold:" prefix = hold.
#   - "This Levy" / "This Campaign" prefix = those.
#   - everything else = immediate.

GUELPH_CARDS = [
    # (n, event_name,                                          capability_name,                      is_war, event_kind)
    (1,  "Ambush",                                             "Stores & Well Water",                False,  "hold"),
    (2,  "Betrayals",                                          "Guastatori",                         False,  "immediate"),
    (3,  "Surprise",                                           "Siege Towers",                       False,  "hold"),
    (4,  "Sudden Clash",                                       "Trebuchets",                         False,  "hold"),
    (5,  "Road Works",                                         "War Engineers",                      False,  "this_campaign"),
    (6,  "Hills",                                              "Hills",                              False,  "hold"),
    (7,  "Greek Fire",                                         "Greek Fire",                         False,  "hold"),
    (8,  "Swamp",                                              "Balestre Grosse",                    False,  "hold"),
    (9,  "Genova breaks Pisan blockade",                       "Genova breaks Pisan blockade",       False,  "immediate"),
    (10, "Closed Gates",                                       "Closed Gates",                       False,  "this_campaign"),
    (11, "Poggio Bonizio answers Firenze's call",              "Poggio Bonizio answers Firenze's call", False, "immediate"),
    (12, "Camp Attack",                                        "Army Reserve",                       False,  "hold"),
    (13, "No Time for Cowards",                                "No Time for Cowards",                False,  "hold"),
    (14, "Provenzano sent as ambassador",                      "Provenzano sent as ambassador",      False,  "this_campaign"),
    (15, "Casole",                                             "Casole",                             False,  "immediate"),
    (16, "A Bloody Red Stream",                                "A Bloody Red Stream",                False,  "hold"),
    (17, "Foreign Help",                                       "Foreign Help",                       False,  "immediate"),
    (18, "Grosseto",                                           "La Cavallata",                       False,  "immediate"),
    (19, "Volterra",                                           "Gualdana",                           False,  "immediate"),
    (20, "Heat & Frost",                                       "Masnadieri",                         False,  "this_levy"),
    (21, "Primo Popolo",                                       "Distringitores",                     False,  "immediate"),
    (22, "Manfredi holds back",                                "Tau Company",                        False,  "immediate"),
    (23, "Treasurers",                                         "Via Francigena",                     False,  "hold"),
    (24, "Doctors",                                            "Astrologers",                        False,  "hold"),
    (25, "Val d'Orcia",                                        "Reinforced Walls",                   True,   "immediate"),
    (26, "Montalcino",                                         "Costruttori",                        True,   "immediate"),
]

GHIBELLINE_CARDS = [
    (1,  "Ambush",                                             "Stores & Well Water",                False,  "hold"),
    (2,  "Betrayals",                                          "Guastatori",                         False,  "immediate"),
    (3,  "Surprise",                                           "Siege Towers",                       False,  "hold"),
    (4,  "Sudden Clash",                                       "Trebuchets",                         False,  "hold"),
    (5,  "Road Works",                                         "War Engineers",                      False,  "this_campaign"),
    (6,  "Feditori",                                           "Feditori",                           False,  "hold"),
    (7,  "Greek Fire",                                         "Luceria",                            False,  "hold"),
    (8,  "Swamp",                                              "Balestre Grosse",                    False,  "hold"),
    (9,  "Pope at Bay flees to Viterbo",                       "Pope at Bay flees to Viterbo",       False,  "immediate"),
    (10, "A Better Paid Death",                                "A Better Paid Death",                False,  "immediate"),
    (11, "Volterra",                                           "Volterra",                           False,  "immediate"),
    (12, "Camp Attack",                                        "Army Reserve",                       False,  "hold"),
    (13, "Gentle Usilia ransoms prisoners",                    "Gentle Usilia",                      False,  "immediate"),
    (14, "Friars sent to deceive Florentines",                 "Friars",                             False,  "hold"),
    (15, "War Loans",                                          "War Loans",                          False,  "immediate"),
    (16, "Bocca degli Abati",                                  "Bocca degli Abati",                  False,  "hold"),
    (17, "Ghibelline Refugees",                                "Ghibelline Refugees",                False,  "immediate"),
    (18, "Cortona",                                            "La Cavallata",                       False,  "immediate"),
    (19, "Brigands",                                           "Gualdana",                           False,  "immediate"),
    (20, "Heat & Frost",                                       "Masnadieri",                         False,  "this_levy"),
    (21, "Constituto",                                         "Sovrintendente",                     False,  "this_campaign"),
    (22, "Closed Gates",                                       "Manfredi",                           False,  "this_campaign"),
    (23, "Economic Sanctions",                                 "Taglia",                             False,  "immediate"),
    (24, "Doctors",                                            "Astrologers",                        False,  "hold"),
    (25, "Maremma",                                            "Reinforced Walls",                   True,   "immediate"),
    (26, "Montepulciano",                                      "Costruttori",                        True,   "immediate"),
]

# Treachery cards — one per non-Comune Lord. Per 1.4.3: each Lord has 1
# Treachery Command card (starts set aside).
TREACHERY_LORD_IDS = [
    "pisa", "astimberg", "santa_fiora", "giordano", "siena", "provenzano",
    "orvieto", "guido_guerra", "arezzo", "firenze", "colle", "lucca",
]

# Command cards — one per non-Comune Lord; carries the Command Rating
# from the Lord's mat. (For Phase 2 we just need the card IDs; the rating
# is on the Lord mat in static_data.)


def main() -> None:
    g_cards = []
    for n, ev, cap, is_war, kind in GUELPH_CARDS:
        g_cards.append({
            "id": f"F{n}", "side": "guelph",
            "event_name": ev, "capability_name": cap,
            "is_war": is_war, "event_kind": kind,
        })
    s_cards = []
    for n, ev, cap, is_war, kind in GHIBELLINE_CARDS:
        s_cards.append({
            "id": f"S{n}", "side": "ghibelline",
            "event_name": ev, "capability_name": cap,
            "is_war": is_war, "event_kind": kind,
        })
    by_id = {}
    for c in g_cards + s_cards:
        by_id[c["id"]] = c

    text = []
    text.append('"""Arts of War, Treachery, and Command card data.')
    text.append('')
    text.append('Auto-generated by scripts/build_cards.py from')
    text.append('reference/Inferno_Arts_of_War_Reference.txt (event/capability names,')
    text.append('event_kind hint) and Inferno Playbook p.64 (War-event flags).')
    text.append('')
    text.append('Per BRIEF: per-card EFFECTS are Phase 4 deferred. Phase 2 needs only')
    text.append('IDs, names, side, is_war (for CtA trigger), and event_kind (for the')
    text.append('3.1.3 draw flow).')
    text.append('"""')
    text.append('')
    text.append('from __future__ import annotations')
    text.append('')
    text.append(f'GUELPH_CARDS = {json.dumps(g_cards, indent=4, ensure_ascii=False)}')
    text.append('')
    text.append(f'GHIBELLINE_CARDS = {json.dumps(s_cards, indent=4, ensure_ascii=False)}')
    text.append('')
    text.append('AOW_CARDS_BY_ID = {c["id"]: c for c in GUELPH_CARDS + GHIBELLINE_CARDS}')
    text.append('')
    text.append(f'TREACHERY_LORD_IDS = {TREACHERY_LORD_IDS!r}')
    text.append('# Treachery card ids — per 1.4.3, one Treachery Command card per Lord.')
    text.append('TREACHERY_CARDS = {')
    for lid in TREACHERY_LORD_IDS:
        text.append(f'    "treachery_{lid}": {{"lord_id": "{lid}", "kind": "treachery"}},')
    text.append('}')
    text.append('')
    text.append('# Command cards — one per non-Comune Lord, command rating on the')
    text.append('# Lord mat in static_data.')
    text.append('COMMAND_CARDS = {')
    for lid in TREACHERY_LORD_IDS:
        text.append(f'    "command_{lid}": {{"lord_id": "{lid}", "kind": "command"}},')
    text.append('}')
    text.append('')
    text.append('# Convenience: card sides by id')
    text.append('CARDS_BY_SIDE = {')
    text.append('    "guelph":     [c["id"] for c in GUELPH_CARDS],')
    text.append('    "ghibelline": [c["id"] for c in GHIBELLINE_CARDS],')
    text.append('}')
    text.append('')
    text.append('# War-event flag (for CtA trigger detection — 3.5)')
    text.append('WAR_EVENT_IDS = {c["id"] for c in GUELPH_CARDS + GHIBELLINE_CARDS if c["is_war"]}')
    text.append('')

    final = "\n".join(text)
    # Convert JSON literals to Python literals (json.dumps emits null/true/false)
    final = final.replace(": false", ": False").replace(": true", ": True").replace(": null", ": None")
    OUT.write_text(final)
    print(f"Wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
