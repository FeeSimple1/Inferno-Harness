"""One-shot generator for src/inferno/static_data.py.

Reads nothing; the data is a hand-curated transcription from:
  reference/Inferno_Lords.txt
  reference/Inferno_Map.txt
  reference/Inferno_Forces_and_Strongholds.md

Run from repo root:
  python3 scripts/build_static_data.py
"""
from __future__ import annotations
import json
from pathlib import Path

OUT = Path(__file__).parent.parent / "src" / "inferno" / "static_data.py"

# ============================================================================
# UNITS (per Inferno_Forces_and_Strongholds.md)
# ============================================================================
UNITS = {
    "Ritter":      {"cat":"horse","battle_strikes":2,  "storm_strikes_attacker":1,  "storm_strikes_defender":1,  "archery":0,  "archery_kind":None,       "protection":[1,2,3,4], "notes":"Knights' Quarter eligible."},
    "Cavalieri":   {"cat":"horse","battle_strikes":1,  "storm_strikes_attacker":1,  "storm_strikes_defender":1,  "archery":0,  "archery_kind":None,       "protection":[1,2,3],   "notes":"Knights' Quarter eligible. Modifiable by Feditori or Army Reserve."},
    "Berrovieri":  {"cat":"horse","battle_strikes":0.5,"storm_strikes_attacker":1,  "storm_strikes_defender":0.5,"archery":0,  "archery_kind":None,       "protection":[1,2],     "notes":"Double Provender/Loot when they Ravage."},
    "Light Horse": {"cat":"horse","battle_strikes":0.5,"storm_strikes_attacker":0.5,"storm_strikes_defender":0.5,"archery":0,  "archery_kind":None,       "protection":[1],       "notes":""},
    "Men-at-Arms": {"cat":"foot", "battle_strikes":1,  "storm_strikes_attacker":1,  "storm_strikes_defender":1,  "archery":0.5,"archery_kind":"crossbow", "protection":[1,2,3],   "notes":"Half-Crossbow only when Garrison or Balestre Grosse in play."},
    "Armigieri":   {"cat":"foot", "battle_strikes":1,  "storm_strikes_attacker":1,  "storm_strikes_defender":1,  "archery":1,  "archery_kind":"crossbow", "protection":[1,2],     "notes":"Full Crossbow only when Garrison or Balestrieri in play. Palvasari card modifies."},
    "Militia":     {"cat":"foot", "battle_strikes":1,  "storm_strikes_attacker":1,  "storm_strikes_defender":1,  "archery":1,  "archery_kind":"archery",  "protection":[1],       "notes":"Archery only as Garrison or with Arcieri / Luceria capability."},
    "Villici":     {"cat":"foot", "battle_strikes":0.5,"storm_strikes_attacker":0.5,"storm_strikes_defender":0.5,"archery":0,  "archery_kind":None,       "protection":[],        "notes":"No armor. Automatically eliminated if hit."},
}

# ============================================================================
# STRONGHOLDS (Inferno_Forces_and_Strongholds.md and Siege Reference)
# ============================================================================
STRONGHOLDS = {
    "city":    {"size":3, "walls_die":[1,2,3,4], "surrender_dice":3, "garrison":{"Men-at-Arms":3,"Armigieri":3,"Cavalieri":3}},
    "town":    {"size":2, "walls_die":[1,2,3,4], "surrender_dice":2, "garrison":{"Men-at-Arms":2,"Armigieri":2,"Cavalieri":2}},
    "castle":  {"size":1, "walls_die":[1,2,3,4], "surrender_dice":1, "garrison":{"Men-at-Arms":1,"Militia":1,"Cavalieri":1}},
    "outpost": {"size":0, "walls_die":[],        "surrender_dice":0, "garrison":{},
                "notes":"Only owning Lord may enter; never Revolts, never Ruined."},
}

# ============================================================================
# LOCALES (60 total: 5 cities + 16 towns + 36 castles + 3 outposts)
# region: "north" (Guelph side of dashed line) / "south" (Ghibelline)
# allegiance: printed allegiance
# port: bool
# ============================================================================
def _city(region, allegiance, **kw):  return {"type":"city",   "region":region, "allegiance":allegiance, "port":False, **kw}
def _town(region, allegiance, **kw):  return {"type":"town",   "region":region, "allegiance":allegiance, "port":False, **kw}
def _castle(region, allegiance, **kw):return {"type":"castle", "region":region, "allegiance":allegiance, "port":False, **kw}
def _outpost(region, allegiance):     return {"type":"outpost","region":region, "allegiance":allegiance, "port":False}

LOCALES = {
    # Cities
    "Lucca":           _city("north","guelph"),
    "Firenze":         _city("north","guelph",     port=True,  leading_city="guelph"),
    "Pisa":            _city("south","ghibelline", port=True),
    "Siena":           _city("south","ghibelline",             leading_city="ghibelline"),
    "Arezzo":          _city("north","guelph"),

    # Towns
    "Altopascio":      _town("north","guelph"),
    "San Miniato":     _town("north","guelph",     port=True),
    "Prato":           _town("north","guelph"),
    "Montevarchi":     _town("north","guelph"),
    "San Gimignano":   _town("north","guelph"),
    "Colle":           _town("north","guelph"),
    "Poggio Bonizio":  _town("north","guelph"),
    "Cortona":         _town("north","guelph"),
    "Chiusi":          _town("north","guelph"),
    "Volterra":        _town("south","ghibelline"),
    "Asinalunga":      _town("south","ghibelline"),
    "Montalcino":      _town("south","ghibelline"),
    "Montepulciano":   _town("south","ghibelline"),
    "Grosseto":        _town("south","ghibelline"),
    "Santa Fiora":     _town("south","ghibelline"),
    "Massa Marittima": _town("south","ghibelline"),

    # Castles (Guelph north)
    "Vecliano":               _castle("north","guelph"),
    "Montecatini":            _castle("north","guelph"),
    "Empoli":                 _castle("north","guelph", port=True),
    "Montelupo":              _castle("north","guelph", port=True),
    "San Casciano":           _castle("north","guelph"),
    "Figline":                _castle("north","guelph"),
    "Ponte a Sieve":          _castle("north","guelph"),
    "Battifolle":             _castle("north","guelph"),
    "Poppi":                  _castle("north","guelph"),
    "Bibbiena":               _castle("north","guelph"),
    "Anghiari":               _castle("north","guelph"),
    "Castiglione":            _castle("north","guelph"),
    "San Giovanni":           _castle("north","guelph"),
    "Barberino":              _castle("north","guelph"),
    "Montespertoli":          _castle("north","guelph"),
    "Monte San Savino":       _castle("north","guelph"),
    "Castelnuovo Berardenga": _castle("north","guelph"),

    # Castles (Ghibelline south)
    "Vicopisano":               _castle("south","ghibelline"),
    "Pontedera":                _castle("south","ghibelline", port=True),
    "Pecciole":                 _castle("south","ghibelline"),
    "Borgo Livorno":            _castle("south","ghibelline", port=True),
    "Rosignano":                _castle("south","ghibelline"),
    "Rocca Sillana":            _castle("south","ghibelline"),
    "Monteriggioni":            _castle("south","ghibelline"),
    "Campiglia":                _castle("south","ghibelline"),
    "Monterotondo":             _castle("south","ghibelline"),
    "Radicondoli":              _castle("south","ghibelline"),
    "Montemassi":               _castle("south","ghibelline"),
    "Castiglione della Pescaia":_castle("south","ghibelline", port=True),
    "Montepescali":             _castle("south","ghibelline"),
    "San Quirico":              _castle("south","ghibelline"),
    "Radicofani":               _castle("south","ghibelline"),
    "Casole":                   _castle("south","ghibelline"),
    "Monticiano":               _castle("south","ghibelline"),
    "Asciano":                  _castle("south","ghibelline"),
    "Chianciano":               _castle("south","ghibelline"),

    # Outposts (all Guelph; only owning Lord may enter)
    "Lombardia-Bologna West": _outpost("north","guelph"),
    "Lombardia-Bologna East": _outpost("north","guelph"),
    "Orvieto":                _outpost("north","guelph"),
}

# ============================================================================
# WAYS — symmetric edges (a, b, type). Built from Inferno_Map.txt.
# ============================================================================
WAYS = [
    # ROADS
    ("Vecliano","Lucca","road"),
    ("Vecliano","Pisa","road"),
    ("Lucca","San Miniato","road"),
    ("Firenze","Figline","road"),
    ("Figline","San Giovanni","road"),
    ("San Giovanni","Montevarchi","road"),
    ("Montevarchi","Arezzo","road"),
    ("Arezzo","Bibbiena","road"),
    ("Bibbiena","Poppi","road"),
    ("Poppi","Battifolle","road"),
    ("Battifolle","Lombardia-Bologna East","road"),
    ("Arezzo","Castiglione","road"),
    ("Castiglione","Cortona","road"),
    ("Cortona","Chiusi","road"),
    ("Radicofani","San Quirico","road"),
    ("San Quirico","Siena","road"),
    ("Siena","Monteriggioni","road"),
    ("Monteriggioni","Colle","road"),
    ("San Miniato","San Gimignano","road"),
    ("San Gimignano","Colle","road"),
    ("Pisa","Rosignano","road"),
    ("Rosignano","Campiglia","road"),
    ("Campiglia","Massa Marittima","road"),
    ("Massa Marittima","Montemassi","road"),
    ("Montemassi","Grosseto","road"),

    # TRACKS — crossroads adjacencies (Track meeting Road)
    ("Vicopisano","Pisa","track"),
    ("Vicopisano","Vecliano","track"),
    ("Borgo Livorno","Pecciole","track"),
    ("Borgo Livorno","Pisa","track"),
    ("Borgo Livorno","Rosignano","track"),
    ("Pecciole","Pisa","track"),
    ("Pecciole","Rosignano","track"),
    ("Montalcino","Asciano","track"),
    ("Montalcino","Siena","track"),
    ("Montalcino","San Quirico","track"),
    ("Asciano","Siena","track"),
    ("Asciano","San Quirico","track"),
    ("Poggio Bonizio","Colle","track"),
    ("Poggio Bonizio","Monteriggioni","track"),
    ("Monte San Savino","Arezzo","track"),
    ("Monte San Savino","Castiglione","track"),
    ("Altopascio","Lucca","track"),
    ("Altopascio","San Miniato","track"),
    ("Orvieto","Cortona","track"),
    ("Orvieto","Chiusi","track"),
    # Direct tracks
    ("Lucca","Vicopisano","track"),
    ("Altopascio","Montecatini","track"),
    ("Montecatini","Prato","track"),
    ("Pisa","Pontedera","track"),
    ("Pontedera","San Miniato","track"),
    ("San Miniato","Empoli","track"),
    ("Empoli","Montelupo","track"),
    ("Montelupo","Firenze","track"),
    ("Empoli","Montespertoli","track"),
    ("Montelupo","Montespertoli","track"),
    ("Pontedera","Pecciole","track"),
    ("Prato","Firenze","track"),
    ("Firenze","Ponte a Sieve","track"),
    ("Ponte a Sieve","Lombardia-Bologna West","track"),
    ("Firenze","San Casciano","track"),
    ("San Casciano","Barberino","track"),
    ("Barberino","Poggio Bonizio","track"),
    ("Montespertoli","Poggio Bonizio","track"),
    ("Rosignano","Volterra","track"),
    ("Volterra","Colle","track"),
    ("Volterra","Rocca Sillana","track"),
    ("Colle","Casole","track"),
    ("Rocca Sillana","Monterotondo","track"),
    ("Monterotondo","Massa Marittima","track"),
    ("Massa Marittima","Castiglione della Pescaia","track"),
    ("Castiglione della Pescaia","Grosseto","track"),
    ("Grosseto","Montepescali","track"),
    ("Montepescali","Santa Fiora","track"),
    ("Santa Fiora","Radicofani","track"),
    ("Montemassi","Radicondoli","track"),
    ("Radicondoli","Casole","track"),
    ("Casole","Monticiano","track"),
    ("Monticiano","Siena","track"),
    ("Monticiano","Montalcino","track"),
    ("Monticiano","Montepescali","track"),
    ("Arezzo","Anghiari","track"),
    ("Castiglione","Anghiari","track"),
    ("Montevarchi","Castelnuovo Berardenga","track"),
    ("Castelnuovo Berardenga","Monte San Savino","track"),
    ("Monte San Savino","Asciano","track"),
    ("Monte San Savino","Asinalunga","track"),
    ("Asciano","Montepulciano","track"),
    ("Asinalunga","Cortona","track"),
    ("Asinalunga","Montepulciano","track"),
    ("Montepulciano","Chianciano","track"),
    ("Chianciano","Chiusi","track"),
]

# ============================================================================
# LORDS — 14 mats (7 Ghibelline + 7 Guelph; 2 of each side are Comunes)
# ============================================================================
LORDS = {
    # ---- Ghibelline ----
    "Pisa Podestà": {
        "side":"ghibelline","podesta":True,"commander":False,
        "seats":["Pisa","Pontedera","Castiglione della Pescaia"],
        "ratings":{"F":3,"S":3,"L":3,"C":2},
        "forces":{"Cavalieri":1,"Men-at-Arms":2,"Militia":2},
        "assets":{"Coin":2,"Cart":2,"Ship":2,"Provender":2},
        "vassals":[
            {"name":"Pisa Commune","seat":"Pisa","service_rating":2,"forces":{"Cavalieri":1,"Armigieri":2}},
            {"name":"Gherardo della Gherardesca","seat":"Pontedera","service_rating":2,"forces":{"Cavalieri":1,"Men-at-Arms":1,"Militia":1}},
        ],
        "notes":"Only Lord with Ships; enables Sail (4.7.3) and Port Supply (4.6.1).",
    },
    "Walther von Astimberg": {
        "side":"ghibelline","podesta":False,"commander":False,
        "seats":["Siena","Casole"],
        "ratings":{"F":3,"S":3,"L":3,"C":3},
        "forces":{"Ritter":2,"Men-at-Arms":1},
        "assets":{"Cart":1},
        "vassals":[
            {"name":"Berchtold von Arras","seat":"Siena","service_rating":4,"forces":{"Ritter":1,"Men-at-Arms":1,"Militia":1}},
            {"name":"Heinrich von Astimberg","seat":"Siena","service_rating":4,"forces":{"Ritter":1,"Men-at-Arms":1}},
        ],
    },
    "Aldobrandino Aldobrandeschi": {
        "side":"ghibelline","podesta":False,"commander":False,
        "alt_names":["Santa Fiora"],
        "seats":["Santa Fiora","Grosseto"],
        "ratings":{"F":5,"S":2,"L":1,"C":2},
        "forces":{"Cavalieri":1,"Light Horse":1,"Berrovieri":1,"Men-at-Arms":1,"Armigieri":1},
        "assets":{"Coin":1,"Cart":1,"Provender":1},
        "vassals":[
            {"name":"Grosseto Commune","seat":"Grosseto","service_rating":2,"forces":{"Berrovieri":1,"Armigieri":1,"Militia":1}},
            {"name":"Uguccione Casali","seat":"Santa Fiora","service_rating":4,"forces":{"Cavalieri":1,"Militia":1}},
        ],
        "notes":"Count of Santa Fiora.",
    },
    "Count Giordano di Agliano": {
        "side":"ghibelline","podesta":False,"commander":False,
        "alt_names":["Giordano"],
        "seats":["Siena","Massa Marittima"],
        "ratings":{"F":4,"S":3,"L":3,"C":3},
        "forces":{"Ritter":3,"Men-at-Arms":2,"Militia":2},
        "assets":{"Cart":3},
        "vassals":[
            {"name":"Hohenstaufen - Royal Naples","seat":"Siena","service_rating":4,"forces":{"Cavalieri":1,"Armigieri":1,"Militia":1}},
            {"name":"Massa Marittima Commune","seat":"Massa Marittima","service_rating":2,"forces":{"Berrovieri":1,"Militia":2}},
        ],
    },
    "Siena Podestà": {
        "side":"ghibelline","podesta":True,"commander":True,
        "seats":["Siena","Asinalunga"],
        "ratings":{"F":5,"S":3,"L":3,"C":2},
        "forces":{"Cavalieri":1,"Men-at-Arms":2},
        "assets":{"Coin":2,"Cart":2,"Provender":2},
        "vassals":[
            {"name":"Buonincontro Guastelloni","seat":"Siena","service_rating":3,"forces":{"Men-at-Arms":1,"Militia":1}},
            {"name":"Cacciaconti","seat":"Asinalunga","service_rating":2,"forces":{"Light Horse":1,"Militia":1}},
        ],
        "notes":"Commander (Ghibelline Leading City). Can attach Siena Comune via CtA (3.5.3).",
    },
    "Provenzano Salvani": {
        "side":"ghibelline","podesta":False,"commander":False,
        "alt_names":["Provenzano"],
        "seats":["Siena","San Quirico"],
        "ratings":{"F":5,"S":3,"L":3,"C":2},
        "forces":{"Ritter":1,"Men-at-Arms":1,"Militia":1},
        "assets":{"Cart":1,"Provender":1},
        "vassals":[
            {"name":"Farinata degli Uberti","seat":"Siena","service_rating":5,"forces":{"Cavalieri":1,"Armigieri":1,"Militia":1}},
            {"name":"Guglielmino Ubertini","seat":"San Quirico","service_rating":2,"forces":{"Cavalieri":1,"Armigieri":1,"Men-at-Arms":1}},
            {"name":"Guido Novello Guidi","seat":"Siena","service_rating":2,"forces":{"Light Horse":1,"Men-at-Arms":1}},
        ],
        "notes":"Capitaneus.",
    },
    "Siena Comune": {
        "side":"ghibelline","podesta":False,"commander":False,"comune_of":"Siena Podestà",
        "seats":[],"ratings":{},
        "forces":{},
        "assets":{"Coin":2,"Cart":4},
        "vassals":[
            {"name":"Carroccio","special":True,"seat":"Siena","forces":{"Cavalieri":1,"Villici":1},"vp_if_captured":{"to":"guelph","value":2}},
            {"name":"Terzo di Camollia","special":True,"seat":"Siena","service_rating":2,"muster_die":4,"forces":{"Cavalieri":1,"Armigieri":1,"Villici":1}},
            {"name":"Terzo di San Martino","special":True,"seat":"Siena","service_rating":2,"muster_die":4,"forces":{"Cavalieri":1,"Armigieri":1,"Villici":1}},
            {"name":"Terzo di Città","special":True,"seat":"Siena","service_rating":2,"muster_die":5,"forces":{"Cavalieri":1,"Armigieri":1,"Villici":1}},
        ],
        "notes":"Enters via CtA only (3.5.3). Must include Carroccio + at least one Terzo.",
    },

    # ---- Guelph ----
    "Orvieto Capitaneus": {
        "side":"guelph","podesta":False,"commander":False,
        "alt_names":["Orvieto"],
        "seats":["Orvieto","Chiusi"],
        "ratings":{"F":5,"S":3,"L":2,"C":3},
        "forces":{"Cavalieri":1,"Light Horse":1,"Men-at-Arms":1,"Armigieri":1},
        "assets":{"Cart":2},
        "vassals":[
            {"name":"Sinibaldo Rubini di Orvieto","seat":"Orvieto","service_rating":3,"forces":{"Cavalieri":1,"Men-at-Arms":1}},
            {"name":"Orvietani & Perugini Reserve","seat":"Orvieto","service_rating":2,"forces":{"Militia":2}},
        ],
        "notes":"Main Seat is an Outpost. Excluded from F23 Via Francigena.",
    },
    "Guido Guerra Guidi": {
        "side":"guelph","podesta":False,"commander":False,
        "alt_names":["Guido Guerra"],
        "seats":["Poppi","Lombardia-Bologna East","Lombardia-Bologna West"],
        "ratings":{"F":3,"S":4,"L":2,"C":2},
        "forces":{"Cavalieri":1,"Armigieri":1,"Militia":1},
        "assets":{"Cart":3},
        "vassals":[
            {"name":"Pistoia Comune","seat":"Lombardia-Bologna West","service_rating":2,"forces":{"Berrovieri":1,"Men-at-Arms":1,"Militia":1}},
            {"name":"Lombardia (Guelph League)","seats":["Lombardia-Bologna East","Lombardia-Bologna West"],"service_rating":2,"forces":{"Cavalieri":1,"Men-at-Arms":2}},
            {"name":"Bologna Comune","seats":["Lombardia-Bologna East","Lombardia-Bologna West"],"service_rating":2,"forces":{"Light Horse":1,"Armigieri":1,"Militia":1}},
        ],
        "notes":"Capitaneus pro Ecclesia. Not a Podestà. Excluded from F23 Via Francigena.",
    },
    "Arezzo Podestà": {
        "side":"guelph","podesta":True,"commander":False,
        "alt_names":["Arezzo"],
        "seats":["Arezzo","Montevarchi"],
        "ratings":{"F":3,"S":3,"L":2,"C":2},
        "forces":{"Cavalieri":1,"Berrovieri":1,"Men-at-Arms":1,"Armigieri":1,"Militia":1},
        "assets":{"Coin":1,"Cart":2,"Provender":2},
        "vassals":[
            {"name":"Bishop Donatello Tarlati","seat":"Arezzo","service_rating":2,"forces":{"Berrovieri":2,"Armigieri":1,"Militia":1}},
            {"name":"Montevarchi Comune","seat":"Montevarchi","service_rating":2,"forces":{"Armigieri":1,"Militia":1}},
        ],
    },
    "Firenze Podestà": {
        "side":"guelph","podesta":True,"commander":True,
        "alt_names":["Firenze"],
        "seats":["Firenze","Prato","Poggio Bonizio"],
        "ratings":{"F":5,"S":3,"L":3,"C":2},
        "forces":{"Cavalieri":2,"Men-at-Arms":2},
        "assets":{"Coin":2,"Cart":2,"Provender":2},
        "vassals":[
            {"name":"Cerchi Family","seat":"Firenze","service_rating":2,"forces":{"Light Horse":1,"Militia":1}},
            {"name":"Prato Comune","seat":"Prato","service_rating":2,"forces":{"Men-at-Arms":1,"Militia":1}},
            {"name":"Adimari Family","seat":"Firenze","service_rating":2,"forces":{"Cavalieri":1,"Armigieri":1,"Militia":1}},
        ],
        "notes":"Commander (Guelph Leading City). Can attach Firenze Comune via CtA (3.5.3).",
    },
    "Colle Podestà": {
        "side":"guelph","podesta":True,"commander":False,
        "alt_names":["Colle"],
        "seats":["Colle","San Gimignano"],
        "ratings":{"F":4,"S":3,"L":2,"C":2},
        "forces":{"Cavalieri":1,"Armigieri":1,"Militia":1},
        "assets":{"Coin":1,"Cart":1,"Provender":1},
        "vassals":[
            {"name":"San Gimignano Comune","seat":"San Gimignano","service_rating":3,"forces":{"Men-at-Arms":1}},
            {"name":"San Miniato Comune","seat":"San Miniato","service_rating":3,"forces":{"Berrovieri":1,"Armigieri":1}},
            {"name":"Antonio Incontri","seat":"Colle","service_rating":3,"forces":{"Light Horse":1,"Armigieri":2}},
            {"name":"Aldobrandino Rosso","seat":"Colle","service_rating":2,"forces":{"Berrovieri":1,"Militia":1}},
        ],
    },
    "Lucca Podestà": {
        "side":"guelph","podesta":True,"commander":False,
        "alt_names":["Lucca"],
        "seats":["Lucca","Altopascio"],
        "ratings":{"F":4,"S":2,"L":2,"C":2},
        "forces":{"Cavalieri":1,"Men-at-Arms":1,"Militia":1},
        "assets":{"Coin":2,"Cart":2,"Provender":2},
        "vassals":[
            {"name":"Tommaso & Anfrione degli Obizzi","seat":"Lucca","service_rating":4,"forces":{"Berrovieri":1,"Armigieri":2}},
        ],
    },
    "Firenze Comune": {
        "side":"guelph","podesta":False,"commander":False,"comune_of":"Firenze Podestà",
        "seats":[],"ratings":{},
        "forces":{},
        "assets":{"Coin":2,"Cart":4},
        "vassals":[
            {"name":"Carroccio","special":True,"seat":"Firenze","forces":{"Cavalieri":1,"Villici":1},"vp_if_captured":{"to":"ghibelline","value":2}},
            {"name":"Sixth of Porta San Piero","special":True,"seat":"Firenze","service_rating":2,"muster_die":3,"forces":{"Cavalieri":2,"Villici":1}},
            {"name":"Sixth of Porta del Duomo","special":True,"seat":"Firenze","service_rating":2,"muster_die":3,"forces":{"Cavalieri":1,"Armigieri":1,"Villici":1}},
            {"name":"Sixth of San Brancazio","special":True,"seat":"Firenze","service_rating":2,"muster_die":3,"forces":{"Cavalieri":1,"Armigieri":1,"Villici":1}},
            {"name":"Sixth of Borgo SS. Apostoli","special":True,"seat":"Firenze","service_rating":2,"muster_die":3,"forces":{"Cavalieri":1,"Armigieri":1,"Villici":1}},
            {"name":"Sixth of San Pier Scheraggio","special":True,"seat":"Firenze","service_rating":2,"muster_die":3,"forces":{"Cavalieri":1,"Armigieri":1,"Villici":1}},
            {"name":"Sixth of Oltrarno","special":True,"seat":"Firenze","service_rating":2,"muster_die":3,"forces":{"Cavalieri":1,"Armigieri":1,"Villici":1}},
        ],
        "notes":"Enters via CtA only (3.5.3). Must include Carroccio + at least one Sestiere.",
    },
}

ALTOPASCIO_VASSAL = {
    "name":"Altopascio","special":True,"side":"guelph","seat":"Altopascio",
    "forces":{"Cavalieri":1},
    "muster_when":"F22 Tau Company in play",
    "musterable_by":["Firenze Podestà","Lucca Podestà"],
    "notes":"Discard of Tau Company Capability Disbands Altopascio. Cannot be Bribed.",
}

LORD_IDS = {
    "Pisa Podestà": "pisa",
    "Walther von Astimberg": "astimberg",
    "Aldobrandino Aldobrandeschi": "santa_fiora",
    "Count Giordano di Agliano": "giordano",
    "Siena Podestà": "siena",
    "Provenzano Salvani": "provenzano",
    "Siena Comune": "siena_comune",
    "Orvieto Capitaneus": "orvieto",
    "Guido Guerra Guidi": "guido_guerra",
    "Arezzo Podestà": "arezzo",
    "Firenze Podestà": "firenze",
    "Colle Podestà": "colle",
    "Lucca Podestà": "lucca",
    "Firenze Comune": "firenze_comune",
}

CALENDAR_BOXES = list(range(1, 17))  # 16 boxes
OFF_EDGES = ["off_left", "off_right", "off_left_service", "off_right_service"]
SIDES = ("guelph", "ghibelline")



def _py(obj) -> str:
    """JSON-dump then patch booleans/null to Python literals for static_data.py."""
    raw = json.dumps(obj, indent=4, ensure_ascii=False)
    # Order matters: replace ` null` before any partial-word collisions.
    out_lines = []
    for line in raw.split("\n"):
        # Only swap when the token sits at the value position (preceded by whitespace
        # or after a `:` or at line start) and followed by a non-alphanumeric.
        line = line.replace(": null", ": None")
        line = line.replace(": true", ": True")
        line = line.replace(": false", ": False")
        line = line.replace(", null", ", None")
        line = line.replace(", true", ", True")
        line = line.replace(", false", ", False")
        # Also handle null/true/false at start of array elements
        line = line.replace("[null", "[None")
        line = line.replace("[true", "[True")
        line = line.replace("[false", "[False")
        out_lines.append(line)
    return "\n".join(out_lines)


def _render() -> str:
    parts = ['"""Static (scenario-independent) Inferno data — catalog of Lords, Locales,',
             'Ways, Forces/Units, Strongholds, Calendar boxes.',
             '',
             'Auto-generated by scripts/build_static_data.py from the curated',
             'reference files (Inferno_Lords.txt, Inferno_Map.txt,',
             'Inferno_Forces_and_Strongholds.md). The references win on conflict.',
             '"""',
             '',
             'from __future__ import annotations',
             '',
             '# ' + '='*75,
             '# UNITS',
             '# ' + '='*75,
             f'UNITS = {_py(UNITS)}',
             '',
             '# ' + '='*75,
             '# STRONGHOLDS',
             '# ' + '='*75,
             f'STRONGHOLDS = {_py(STRONGHOLDS)}',
             '',
             '# ' + '='*75,
             '# LOCALES (60 total: 5 cities + 16 towns + 36 castles + 3 outposts)',
             '# ' + '='*75,
             f'LOCALES = {_py(LOCALES)}',
             '',
             '# ' + '='*75,
             '# WAYS (symmetric edges as (a, b, way_type))',
             '# ' + '='*75,
             f'WAYS = {_py([list(w) for w in WAYS])}',
             '',
             '# ' + '='*75,
             '# LORDS (14 mats: 7 Ghibelline + 7 Guelph; 2 are Comunes)',
             '# ' + '='*75,
             f'LORDS = {_py(LORDS)}',
             '',
             f'ALTOPASCIO_VASSAL = {_py(ALTOPASCIO_VASSAL)}',
             '',
             f'LORD_IDS = {_py(LORD_IDS)}',
             '',
             '# Reverse lookup: slug -> canonical name',
             'LORD_NAMES = {v: k for k, v in LORD_IDS.items()}',
             '',
             f'CALENDAR_BOXES = {CALENDAR_BOXES!r}  # 1..16',
             f'OFF_EDGES = {OFF_EDGES!r}',
             f'SIDES = {SIDES!r}',
             '',
             '',
             'def adjacent_to(locale: str) -> list[tuple[str, str]]:',
             '    """Return [(neighbour, way_type), ...] for the given Locale."""',
             '    out: list[tuple[str, str]] = []',
             '    for a, b, way in WAYS:',
             '        if a == locale:',
             '            out.append((b, way))',
             '        elif b == locale:',
             '            out.append((a, way))',
             '    return out',
             '']
    return "\n".join(parts)


if __name__ == "__main__":
    OUT.write_text(_render())
    print(f"Wrote {OUT} ({OUT.stat().st_size:,} bytes)")
