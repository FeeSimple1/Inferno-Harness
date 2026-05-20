"""v2.5 — Call to Arms (3.5) is reachable through the move enumerator.

  SMOKE-Inferno-059: _enum_cta was a skip-only stub even though all CtA handlers
  existed (an enumerator/handler round-trip gap). It now surfaces DECLARE (when a
  3.5 trigger is met) / DECLINE, and once active the four sub-steps
  (gather / commander_arms / comune / allies), each with a skip. The Gather
  destination-legality predicate is shared with the handler so the enumerator
  never emits a move dispatch would reject.
"""
import copy
import inspect
import pytest

from inferno.scenarios import load_scenario
from inferno.legal_moves import enumerate_legal
import inferno.actions as A
from inferno.actions import dispatch, IllegalAction
from inferno.flow import current_step


def _to_cta(scenario="B", seed=1):
    s = load_scenario(scenario, seed=seed)
    for name, side in [
        ("levy_aow_draw", "guelph"), ("levy_aow_draw", "ghibelline"),
        ("levy_pay_done", "guelph"), ("levy_pay_done", "ghibelline"),
        ("levy_disband_done", "guelph"), ("levy_disband_done", "ghibelline"),
        ("levy_muster_done", "guelph"), ("levy_muster_done", "ghibelline"),
    ]:
        dispatch(s, {"action": name, "side": side})
    assert current_step(s) == "3.5"
    return s


class TestCtAEnumeration:
    def test_only_decline_when_no_trigger(self):
        s = _to_cta()
        actions = {m["action"] for m in enumerate_legal(s)}
        assert actions == {"levy_cta_skip"}

    def test_declare_surfaced_when_eligible(self):
        s = _to_cta()
        s["war_declared_this_levy"] = ["guelph"]
        moves = enumerate_legal(s)
        actions = {m["action"] for m in moves}
        assert "levy_cta_declare" in actions
        assert "levy_cta_skip" in actions

    def test_substeps_surfaced_after_declare_and_round_trip(self):
        s = _to_cta()
        s["war_declared_this_levy"] = ["guelph"]
        dispatch(s, {"action": "levy_cta_declare", "side": "guelph"})
        assert s["meta"]["cta_active"] is True
        assert s["meta"]["cta_substep"] == "gather"
        moves = enumerate_legal(s)
        # The gather sub-step always offers a skip, and every surfaced move must
        # be accepted by dispatch (round-trip integrity).
        assert any(m["action"] == "cta_step_skip" for m in moves)
        for m in moves:
            snap = copy.deepcopy(s)
            act = {"action": m["action"], "side": m["side"]}
            if "args" in m:
                act["args"] = m["args"]
            dispatch(snap, act)  # must not raise

    def test_full_cta_drivable_via_enumerator(self):
        # Drive the entire CtA purely from enumerate_legal -> dispatch and confirm
        # it completes (exits step 3.5 into the Campaign) without illegal moves.
        s = _to_cta()
        s["war_declared_this_levy"] = ["guelph"]
        entered = False
        for _ in range(200):
            if s["meta"].get("cta_active"):
                entered = True
            if current_step(s) != "3.5" and not s["meta"].get("cta_active"):
                break
            moves = [m for m in enumerate_legal(s) if not m["action"].startswith("<")]
            if not moves:
                break
            a = moves[0]
            act = {"action": a["action"], "side": a["side"]}
            if "args" in a:
                act["args"] = a["args"]
            dispatch(s, act)
        assert entered is True
        # CtA closed out and the Levy advanced past 3.5.
        assert s["meta"].get("cta_active") in (False, None)
        assert current_step(s) != "3.5"

    def test_markers_present(self):
        assert "SMOKE-Inferno-059" in inspect.getsource(A._cta_gather_dest_legal)
        from inferno import legal_moves as LM
        assert "SMOKE-Inferno-059" in inspect.getsource(LM._enum_cta)
