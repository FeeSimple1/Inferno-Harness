"""v2.3 — FPD optional Pay sub-step (4.8.2) is surfaced, not auto-skipped.

  #9 SMOKE-Inferno-057: after Feed, when either side can legally Pay, FPD parks a
     pending Pay decision (Guelphs then Ghibellines) and DEFERS Disband until both
     sides resolve Pay via cmd_fpd_pay / cmd_fpd_pay_done. Paying can save a Lord
     from Disband. When neither side can Pay, FPD runs straight through (unchanged).
"""
import inspect
import pytest

from inferno.scenarios import load_scenario
from inferno.legal_moves import enumerate_legal
import inferno.actions as A


def _put_on_service(s, lid, box):
    lord = s["lords"][lid]
    lord["status"] = "mustered"
    lord["service_box"] = box
    cb = s["calendar"]["boxes"].setdefault(str(box),
        {"cylinders": [], "services": [], "victory": [], "markers": []})
    if lid not in cb["services"]:
        cb["services"].append(lid)


class TestFpdPaySubStep:
    def test_no_pay_available_runs_synchronously(self):
        s = load_scenario("A", seed=1)
        # Strip ALL Coin so no side can Pay -> FPD must run straight through.
        for lord in s["lords"].values():
            lord.get("assets", {}).pop("Coin", None)
        out = A._run_fpd(s)
        assert out["pay_pending"] is False
        assert "pending_fpd" not in s
        assert "disband" in out  # Disband ran synchronously

    def test_parks_and_defers_disband_then_pay_saves_lord(self):
        s = load_scenario("A", seed=1)
        s["calendar"]["levy_box"] = 5
        # A Guelph Lord at service box 3 (< 5) would Disband Beyond Service.
        lid = next(l for l, ld in s["lords"].items()
                   if ld["side"] == "guelph" and ld.get("status") == "mustered")
        _put_on_service(s, lid, 3)
        s["lords"][lid].setdefault("assets", {})["Coin"] = 5
        s["lords"][lid].pop("podesta", None)

        out = A._run_fpd(s)
        # Pay sub-step parked; Disband deferred (Lord still Mustered).
        assert out["pay_pending"] is True
        assert s["pending_fpd"]["side"] == "guelph"
        assert s["lords"][lid]["status"] == "mustered"

        # Enumerator surfaces ONLY the FPD-Pay moves, pay_done listed first.
        moves = enumerate_legal(s)
        assert moves[0]["action"] == "cmd_fpd_pay_done"
        assert all(m["action"] in ("cmd_fpd_pay", "cmd_fpd_pay_done") for m in moves)
        assert any(m["action"] == "cmd_fpd_pay" for m in moves)

        # Pay 3 boxes (Coin) to push Service to 6 (> levy box 5) -> safe.
        A.dispatch(s, {"action": "cmd_fpd_pay", "side": "guelph",
                       "args": {"from_lord_id": lid, "target_lord_id": lid,
                                "asset": "Coin", "amount": 3}})
        assert s["lords"][lid]["service_box"] == 6

        # End Guelph Pay -> Ghibelline segment; then end Ghibelline -> Disband runs.
        A.dispatch(s, {"action": "cmd_fpd_pay_done", "side": "guelph", "args": {}})
        assert s["pending_fpd"]["side"] == "ghibelline"
        A.dispatch(s, {"action": "cmd_fpd_pay_done", "side": "ghibelline", "args": {}})
        assert "pending_fpd" not in s
        # The Lord was saved from Disband by Paying.
        assert s["lords"][lid]["status"] == "mustered"
        assert s["lords"][lid]["service_box"] == 6

    def test_declining_pay_lets_lord_disband(self):
        s = load_scenario("A", seed=1)
        s["calendar"]["levy_box"] = 5
        lid = next(l for l, ld in s["lords"].items()
                   if ld["side"] == "guelph" and ld.get("status") == "mustered")
        _put_on_service(s, lid, 3)
        s["lords"][lid].setdefault("assets", {})["Coin"] = 5
        A._run_fpd(s)
        # Decline to Pay on both sides -> Disband runs and the Lord is gone.
        A.dispatch(s, {"action": "cmd_fpd_pay_done", "side": "guelph", "args": {}})
        A.dispatch(s, {"action": "cmd_fpd_pay_done", "side": "ghibelline", "args": {}})
        assert "pending_fpd" not in s
        assert s["lords"][lid]["status"] != "mustered"  # Disbanded Beyond Service

    def test_fpd_pay_wrong_side_rejected(self):
        s = load_scenario("A", seed=1)
        s["calendar"]["levy_box"] = 5
        lid = next(l for l, ld in s["lords"].items()
                   if ld["side"] == "guelph" and ld.get("status") == "mustered")
        _put_on_service(s, lid, 3)
        s["lords"][lid].setdefault("assets", {})["Coin"] = 5
        A._run_fpd(s)
        # Guelph segment active; a Ghibelline FPD pay is out of segment. The
        # handler guards it (WRONG_FPD_PAY_SIDE); via dispatch the turn check
        # rejects it first (WRONG_TURN) since Ghibelline is not exempt yet.
        with pytest.raises(A.IllegalAction) as h_exc:
            A._h_cmd_fpd_pay_done(s, "ghibelline", {}, None)
        assert h_exc.value.code == "WRONG_FPD_PAY_SIDE"
        with pytest.raises(A.IllegalAction) as d_exc:
            A.dispatch(s, {"action": "cmd_fpd_pay_done", "side": "ghibelline", "args": {}})
        assert d_exc.value.code in ("WRONG_TURN", "WRONG_FPD_PAY_SIDE")

    def test_marker_present(self):
        assert "SMOKE-Inferno-057" in inspect.getsource(A._run_fpd)


# =====================================================================
# SMOKE-Inferno-058 — FPD Beyond-Service Disband triggers Revolt & Treachery
# (4.8.2 Errata / 3.3.1), via the shared trigger; At-Service-Limit does not.
# =====================================================================
class TestFpdDisbandRevolt:
    def _one_beyond(self, side="guelph", podesta=False, at_limit=False):
        s = load_scenario("A", seed=1)
        s["calendar"]["levy_box"] = 5
        # Make every mustered Lord safe (Service 10) and strip Coin/Loot so FPD
        # runs synchronously (no Pay sub-step), isolating one Disband.
        for ld in s["lords"].values():
            if ld.get("status") == "mustered":
                ld["service_box"] = 10
            ld.get("assets", {}).pop("Coin", None)
            ld.get("assets", {}).pop("Loot", None)
        lid = next(l for l, ld in s["lords"].items()
                   if ld["side"] == side and ld.get("status") == "mustered")
        s["lords"][lid]["service_box"] = 5 if at_limit else 3
        s["lords"][lid].pop("comune_of", None)
        if podesta:
            s["lords"][lid]["podesta"] = True
        else:
            s["lords"][lid].pop("podesta", None)
        return s, lid

    def test_beyond_disband_triggers_one_revolt_and_treachery(self):
        s, lid = self._one_beyond()
        cmd_before = len(s["decks"]["ghibelline"]["command_deck"])
        out = A._run_fpd(s)
        assert out["pay_pending"] is False                 # synchronous
        assert s["lords"][lid]["status"] != "mustered"     # Disbanded Beyond
        assert len(out.get("disband_treachery", [])) == 1
        assert len(s["decks"]["ghibelline"]["command_deck"]) == cmd_before + 1
        assert len(out.get("disband_revolts", [])) >= 1

    def test_podesta_beyond_disband_triggers_three(self):
        s, lid = self._one_beyond(podesta=True)
        out = A._run_fpd(s)
        assert len(out.get("disband_treachery", [])) == 3

    def test_at_service_limit_disband_no_revolt(self):
        s, lid = self._one_beyond(at_limit=True)
        out = A._run_fpd(s)
        assert s["lords"][lid]["status"] != "mustered"     # Disbanded At limit
        assert "disband_treachery" not in out              # no Revolt/Treachery

    def test_shared_trigger_used_by_fpd_and_combat(self):
        assert "_trigger_disband_revolt_and_treachery" in inspect.getsource(A._fpd_run_disband)
        assert "_trigger_disband_revolt_and_treachery" in inspect.getsource(A._apply_post_battle)

    def test_marker_present(self):
        assert "SMOKE-Inferno-058" in inspect.getsource(A._fpd_run_disband)
