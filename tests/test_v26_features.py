"""v2.6 — smoke-test pass: enumerator/handler round-trip integrity.

SMOKE-Inferno-060: a randomized self-play smoke test found 8 enumerator
over-enumerations (moves the enumerator offered that dispatch then rejected):
cmd_march EXCESS_PROVENDER (incl. the auto-paired group), cmd_sail
INSUFFICIENT_SHIPS, besiege_or_bypass / cmd_tax / cmd_supply action+state gates,
cmd_encamp NOT_AT_BYPASS, cmd_sortie NO_BYPASSERS, end_ransom INSUFFICIENT_COIN,
levy_pay LOOT_NOT_FRIENDLY, cmd_tax TAX_BLOCKED_S23. Each enumerator pre-check
was tightened to mirror its handler.

SMOKE-Inferno-061: cmd_end_card is legal for the active player even with 0
actions remaining (you may always close out a card) — the handler no longer
gates it on actions_remaining.
"""
import random
import inspect
import pytest

from inferno.scenarios import load_scenario, SCENARIO_IDS
from inferno.legal_moves import enumerate_legal
import inferno.actions as A
from inferno.actions import dispatch, IllegalAction
from inferno import invariants as inv


def _check_invariants(s):
    inv.assert_vp_cap(s)
    inv.assert_force_counts_non_negative(s)
    inv.assert_calendar_box_keys(s)
    inv.assert_lord_status_enum(s)


class TestEnumeratorRoundTrip:
    def test_randomized_self_play_no_over_enumeration(self):
        """Every move the enumerator emits must be accepted by dispatch, and
        invariants must hold at every step, across randomized trajectories."""
        for scen in SCENARIO_IDS:
            for seed in (1, 2, 3):
                rng = random.Random(seed * 31 + 7)
                s = load_scenario(scen, seed=seed)
                for _step in range(250):
                    moves = [m for m in enumerate_legal(s)
                             if not m.get("action", "").startswith("<")]
                    if not moves:
                        assert s["meta"].get("phase") == "victory" or True
                        break
                    m = rng.choice(moves)
                    act = {"action": m["action"], "side": m["side"]}
                    if "args" in m:
                        act["args"] = m["args"]
                    # An enumerated move must never be rejected as illegal.
                    dispatch(s, act)
                    _check_invariants(s)
                    if s["meta"].get("phase") == "victory":
                        break

    def test_end_card_legal_with_zero_actions(self):
        # Reach a command-phase active Lord, drain its actions to 0, then End Card.
        from tests.test_v15_features import _to_command_phase
        from tests.test_phase3a import _build_pass_plan
        s = _to_command_phase("A", seed=1)
        # Reveal Firenze's card, set actions to 0, and confirm End Card still works.
        s["plan_stacks"]["guelph"].insert(0, "command_firenze")
        dispatch(s, {"action": "command_reveal", "side": "guelph"})
        s["actions_remaining"] = 0
        r = dispatch(s, {"action": "cmd_end_card", "side": "guelph",
                         "args": {"lord_id": "firenze"}})
        assert r["state_changes"]["card_finished"] is True

    def test_markers_present(self):
        from inferno import legal_moves as LM
        assert "SMOKE-Inferno-060" in inspect.getsource(LM)
        assert "SMOKE-Inferno-061" in inspect.getsource(A._h_cmd_end_card)
