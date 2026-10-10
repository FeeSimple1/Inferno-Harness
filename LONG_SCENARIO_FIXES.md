# Scenario F long-game corrections

Base: `60da72b8265e4d5e797d56499dec88046a852853` (published `main`).
The unmodified local source tree was verified to match GitHub's tree
`e5f3c6a17729d41b421219e827f4ebec121d696b` exactly before editing.

These changes address the eight findings in the Scenario F long-game report.
Rules sources are the repository's Call to Arms, Rules, Battle and Storm,
Sequence of Play, and Scenario references. This is targeted regression repair,
not an assertion of exhaustive rules correctness.

| Finding | Correction and regression evidence |
| --- | --- |
| F-LONG-01: Allies extra Muster cannot be spent | Keep the current player and Allies substep active, expose ordinary Muster actions for the selected eligible Lord, and end the segment with `levy_muster_done`. Reject a second selection, other Lords' expenditure, or a new Call to Arms while that segment remains open. |
| F-LONG-02: War permission survives into later Levies | Clear `war_declared_this_levy` on leaving Levy, with defensive cleanup at the next-turn Reset. Current-Levy War Events still grant permission normally. |
| F-LONG-03: Sack leaves removed Allegiance points in the running score | Subtract the removed enemy Allegiance values before adding Ruins points. The original Surprise at Poggio Bonizio now produces Guelph 4, Ghibelline 2.5. |
| F-LONG-04: Gather splits Commander and Comune | Shared validation and execution automatically include the Commander's mustered Comune. Neither a separated nor besieged pair may use Gather to evade its restrictions. A Comune cannot lead Gather independently. |
| F-LONG-05: Existing Comune setup duplicates troops and replenishes assets | Distinguish first setup from reinforcing an existing mat. Only newly Mustered Special Vassals add Forces. Existing casualties, Assets, Capabilities, and captured Carroccio records remain intact. Menus include each valid new selection. |
| F-LONG-06: Commander recall strands and later duplicates the Comune | Both Commander disband paths remove the accompanying Comune and clear its complete mat and board/calendar occupancy. The actual action-641 onward mirrored recall/setup sequence now passes invariants after every action. |
| F-LONG-07: Final turn ends after Repair/Waste instead of at Game End | Treat box 16 as the maximum when no End marker is present. Earlier End markers still apply. Game End stops immediately, closes its phase, and rejects post-game Repair, Waste, and Reset. |
| F-LONG-08: Fresh-process replay differs only because sets become unordered lists | Canonicalize War permissions and completed Call to Arms sides. Full serialized state/results agree in fresh processes with `PYTHONHASHSEED=0`, `1`, and `42`. |

## Correction to the original report's extra-Muster example

Arezzo was besieging hostile Cortona in the saved action-105 position and was
not eligible for a Muster segment under 3.4. The old handler should not have
accepted that selection. The underlying extra-segment problem is real: an
eligible Lord must be allowed to use the grant. Tests reject Arezzo in that
position and exercise the full grant with Firenze at Firenze instead. The
Commander is eligible for **extra Muster**; the non-Commander restriction
belongs to the distinct **automatic Muster** alternative.

## Related removal cleanup

Disband clears Routed units as well as Forces. Replaying the long game's battle
at action 459 exposed why this matters: the previous code performed loss/recovery
rolls on Colle after removing him. The repair prevents those extra rolls and any
recovery onto a removed mat. Knights' Quarter still occurs before Battle removal.
A regression checks the actual position and verifies that no `loss_colle_*` rolls
occur after removal.

That correction changes subsequent dice consumption in the old endurance action
record. The original record therefore is **not** claimed to replay unchanged or
to finish with the same result under these fixes. The exact saved turn-16
position is tested independently: it now ends on its Game End check, before any
Repair or Waste. No game state, die roll, or rules were altered to force an old
replay outcome.

## Tests and evidence

`tests/test_long_scenario_fixes.py` contains 52 cases, including both sides,
invalid-action rollback, save/load during extra Muster, menu/executor agreement,
Comune losses and asset conservation, the original failure positions, and
cross-process serialization. The compact mechanical fixtures live under
`tests/fixtures/long_scenario/`; their manifest records source and fixture hashes.
Only historical transcripts were removed from saved positions.

Run the complete suite and existing stress tools with the normal development
requirements installed:

```sh
python -m pytest -q
for scenario in A B C D E F; do
  PYTHONPATH=src python selfplay_bughunt.py "$scenario" --seed 11 --max-steps 8000
done
PYTHONPATH=src python cardfx_fuzz.py --seeds 6
PYTHONPATH=src python saveload_fuzz.py --seeds 8 --max-steps 8000
PYTHONPATH=src python robustness_fuzz.py --seeds 3 --max-steps 6000 --probe-every 8
PYTHONPATH=src python state_injection_fuzz.py --seeds 2 --max-steps 400 --probe-every 60
```

The repository CI already installs `.[dev]` and discovers the added tests.
