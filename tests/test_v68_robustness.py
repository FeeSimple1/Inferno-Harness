"""v6.8 — Adversarial-input robustness (round-3 #3, locked in).

Feeds dispatch malformed/illegal/mutated args and asserts the contract: every
bad action is rejected with IllegalAction (never a bare crash), a rejected
action leaves state byte-identical (validate-then-mutate), and any accepted
action keeps invariants. Backed by robustness_fuzz.py. This round fixed
CONF-018 (muster Lordship leak), CONF-019 (plan_add_card crash on None card_id),
CONF-020 (march Maremma-latch transactional leak), CONF-021 (int-arg crashes).
"""
from __future__ import annotations

import pytest
import robustness_fuzz as rf
from inferno.actions import _int_arg, IllegalAction


def test_robustness_sweep_clean():
    rf.ANOMALIES.clear()
    rf.KINDS.clear()
    for scen in "ABC":
        for seed in (1, 2):
            rf.run(scen, seed, max_steps=1500, probe_every=10)
    assert not rf.ANOMALIES, rf.ANOMALIES[:5]
    # Sanity: the probe actually exercised rejections (not a no-op sweep).
    assert rf.KINDS.get("clean_reject", 0) > 100


def test_int_arg_guard():
    assert _int_arg({"amount": "3"}, "amount", 1) == 3
    assert _int_arg({}, "amount", 7) == 7
    for bad in ("lots", None, [1], {}):
        with pytest.raises(IllegalAction):
            _int_arg({"amount": bad}, "amount", 1)


def test_plan_add_card_bad_card_id_is_illegalaction_not_crash():
    from inferno.scenarios import load_scenario
    from inferno.actions import _h_plan_add_card
    s = load_scenario("A", 1)
    # Force the plan step so the handler reaches the card_id check.
    from inferno import flow
    # Drive minimal: just assert the type guard fires before any .startswith.
    for bad in (None, 123, ""):
        with pytest.raises(IllegalAction):
            _h_plan_add_card(s, "guelph", {"card_id": bad}, None)
