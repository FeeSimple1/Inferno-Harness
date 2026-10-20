# Vassal component and rules audit — 2026-10-20

Baseline: `bab21ae` (v6.15.0). This audit uses the published Vassal
module as an independent component/setup source, then checks disagreements
against the repository's rules and errata. Vassal is a manual tabletop
module, not a rules engine capable of certifying this harness.

## Sources and reproducibility

- [Official Vassal project](https://vassalengine.org/library/projects/Inferno):
  Brian Reynolds's **Inferno 1.0**, released January 2023.
- [Module download](https://obj.vassalengine.org/images/b/bb/Inferno_1.0.vmod).
  SHA-256: `cbe05ecd23f63859d675a6fe27b027fc2c3ac3dfacf4e1987da6a067c2535464`.
- In-module `buildFile.xml`, predefined scenarios A–F, Lord mats, Vassal
  counters, `PAC-Forces.jpg`, `PAC-Guelphs.jpg`, and `PAC-Ghibellines.jpg`.
- `reference/Inferno_Official_Errata.txt`, relevant curated references,
  and `sources/Inferno_Rules_of_Play.pdf`, especially 1.5.1, 1.5.3,
  2.2.3, 3.4.2, 3.5.3, 4.4, 4.5, and 4.8.

Run the read-only extractor against a separately downloaded module:

```sh
PYTHONPATH=src python scripts/audit_vassal.py /path/Inferno_1.0.vmod
```

It performs **291 named comparisons** covering Lord Service/Lordship/Command,
starting Forces and Assets, Vassal Force/Service multisets, Altopascio,
available Locale type/allegiance properties, and principal Lord starting
locations, removal status, cylinder positions, and Service positions in all
six scenarios. A comparison may contain several component values. The hash
gate prevents silently interpreting a different module with this extractor.
No artwork or module saved games are redistributed in this repository.

## Confirmed defects and corrections

| Finding | Evidence and impact | Correction |
| --- | --- | --- |
| Militia struck twice as hard in melee | Printed Forces chart gives **1/2**, while the harness used **1** in Battle and both Storm roles, including Garrisons. | Half-hit values restored; Archery unchanged. |
| Pisa Lordship too high | Printed Pisa mat and module Stats give **2**, not **3**. | Corrected runtime data, generator, and curated roster; prevents an extra Levy action. |
| Lucca Service too low | Printed Lucca mat and module Stats give **3**, not **2**. | Corrected all three data sources, including return timing after Disband. |
| Altopascio unavailable | Printed counter has Service **2**; F22 permits a free Muster by Firenze or Lucca. The definition lacked its rating and no normal action could obtain the set-aside Vassal. | Added the rating, unique free Muster, legal-menu entry, Seat/card checks, and Disband on Tau Company discard. |
| Enemy Vassal Seats accepted | 3.4.2 explicitly requires a Friendly Vassal Seat. | Handler and menu enforce allegiance while allowing a Friendly Seat to be Ravaged, Ruined, Besieged, or Bypassed. |
| Advanced Vassal Service incomplete | 3.4.2 requires independent initial clocks, matching shifts, expiry in both Disband steps, and temporary Unready status. | Added the lifecycle, remaining-force removal, empty-Lord consequences, and readiness after the Levy. Carroccio and Turncoats remain exempt. |
| Off-calendar Service could not participate | 2.2.3 permits return from either edge; 3.4.2 still shifts Vassals when their Lord is off-board. | Shared Service movement handles both edges and is used by Pay, Events, Feed, and Retreat. Menus recognize edge markers. |
| Comune subdivisions inaccessible after setup | 3.4.2 allows a Commander inside the Leading City to attempt a Ready Sestiere/Terzo on his in-play Comune. Unselected subdivisions started not Ready and were absent from the menu. | Correct readiness and menu exposure; advanced clocks follow the Commander. |
| Commander/Comune overcharged for Feed | 1.5.1 explicitly counts both mats as one Lord for Feed; separate calculations could require two provisions for six total units. | Combined Force count and provisions, with one Service penalty for an unfed army. |
| Public advanced Service hidden from opponent | 3.4.2 explicitly reveals these Calendar markers even with Hidden Mats. | Public Vassal names/Service boxes retained in filtered state and briefing. |

Regression coverage is in `tests/test_vassal_module_audit.py`. A pre-existing
Garrison test expected the incorrect Militia value and is corrected. The
historical Sack/VP fixture now uses a documented deterministic RNG stream
that still reaches Sack after the combat correction; its VP assertions remain.

## Module discrepancies deliberately not imported

| Module content | Resolution |
| --- | --- |
| Orvieto's internal `Stats Guelphs4` says Command 2. | His printed mat and player aid say **3**. Harness remains 3; extractor explicitly uses the printed value. |
| Scenario D places Provenzano and Santa Fiora at Montalcino. | Official Scenario D, Rules p28, specifies **Montepulciano**. Harness remains there. Extractor reports these two exact, version-bound exceptions separately. |
| Ghibelline player aid depicts Militia for Guido Novello. | His actual Vassal counter and module placement use **Light Horse and Men-at-Arms**. Harness matches the counter. |
| Comune mat automation places Carroccio Forces immediately. | Harness adds them during explicit 3.5.3 selection. This is a representation difference, not a missing starting-force correction. |

After fixes, the extractor reports **zero unexplained differences** and the
two documented Scenario D setup exceptions.

## Verification

- Baseline suite: **1,094 passed** before changes.
- Final suite: **1,121 passed**, including **27 new regression cases**.
- Component extractor: **291 comparisons**, zero unexplained differences;
  two documented Scenario D setup exceptions.
- Standard self-play A–F, seed 11: all reached the victory phase with
  **zero detected anomalies** (1,247 actions).
- Advanced Vassal Service self-play A and F, seed 11: both reached the
  victory phase with **zero detected anomalies** (408 actions).
- Card-effect integration fuzz: **52 cards × 6 seeds**, zero anomalies.
- Illegal-state injection fuzz: **2 seeds, 400-step cap, probes every 60**,
  zero anomalies. All applicable injected corruptions were detected;
  `c_inside_at_ruins` did not arise in these runs.
- Whitespace/diff check passed with the existing CRLF roster convention.

Reproduce the automated checks:

```sh
PYTHONPATH=src python -m pytest -q
bash scripts/ci.sh
PYTHONPATH=src python selfplay_bughunt.py A --seed 11 --max-steps 8000 --advanced-vassal-service
PYTHONPATH=src python selfplay_bughunt.py F --seed 11 --max-steps 8000 --advanced-vassal-service
```

The self-play driver now accepts `--advanced-vassal-service` so the optional
rule can be exercised end to end. The initial advanced F run exposed an
offered-but-illegal `levy_disband_done`; the menu now withholds it until expired
Vassals are resolved.

## Limits and saved games

This is a component/setup comparison plus targeted rules regressions and
automated simulations. It is not a proof of every rule, every card text,
every route on the printed map, every die stream, or strategic play quality.
The extractor compares Vassal Force/Service multisets, not each printed name
or every Vassal Seat. Artwork findings were visually inspected separately.

Existing JSON saves retain serialized Lord ratings. Old advanced-rule saves
also cannot recover missing Vassal clocks or past shifts from current state
alone. They are **not silently migrated**; start a fresh game or reconstruct
the position from its action history/source position for the audited behavior.

The required source hedge-word scan was reviewed. Most hits describe history,
pagination, or resolved defects. Pre-existing phase-era documentation remains
in `actions.py`, `card_data.py`, and `flow.py`; the single-Lord/group-Sortie
deferral in `_h_cmd_sortie` is logged here as an unverified follow-up outside
this component/Vassal audit, not certified as implemented by this work.
