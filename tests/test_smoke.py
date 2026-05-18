"""Phase 0 smoke tests.

Asserts: package imports, scenario data loads, CLI is invokable end to
end, RNG is seedable and logs context.

Per BRIEF "Test Discipline": every rule encoded in code must have at
least one test, with a docstring citing the rule section. Phase 0 has
no game rules yet, so these tests assert structural properties only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from inferno import __version__
from inferno.actions import IllegalAction, dispatch
from inferno.legal_moves import enumerate_legal
from inferno.rng import HarnessRNG
from inferno.scenarios import SCENARIO_IDS, SCENARIO_NAMES, list_scenarios, load_scenario_data


# ----------------------------------------------------------------- imports
def test_package_imports():
    assert __version__ == "0.0.0"


def test_all_six_scenarios_listed():
    """Per BRIEF 'LLM-Consumer Interface' new: all six scenarios A-F supported."""
    ids = {s["id"] for s in list_scenarios()}
    assert ids == {"A", "B", "C", "D", "E", "F"}


@pytest.mark.parametrize("sid", SCENARIO_IDS)
def test_each_scenario_loads(sid: str):
    """Scenario JSON must be loadable and self-identifying."""
    data = load_scenario_data(sid)
    assert data["scenario_id"] == sid
    assert data["name"] == SCENARIO_NAMES[sid]
    assert "calendar" in data
    assert "map" in data
    assert "mustered" in data


def test_unknown_scenario_raises():
    with pytest.raises(ValueError):
        load_scenario_data("Z")


# ----------------------------------------------------------------- RNG
def test_rng_is_seedable_and_logs_context():
    """Per BRIEF 'Dice and Mechanical Resolution': every roll is logged
    with context."""
    rng = HarnessRNG(seed=1234)
    r1 = rng.roll("protection_cavalieri")
    r2 = rng.roll("walls_storm")
    assert 1 <= r1.value <= 6
    assert r1.context == "protection_cavalieri"
    log = rng.drain_log()
    assert [r.context for r in log] == ["protection_cavalieri", "walls_storm"]
    # drain_log clears the buffer
    assert rng.drain_log() == []


def test_rng_is_deterministic_for_a_given_seed():
    a = HarnessRNG(seed=99)
    b = HarnessRNG(seed=99)
    assert [a.roll("x").value for _ in range(10)] == [b.roll("x").value for _ in range(10)]


# ----------------------------------------------------------------- action stubs
def test_dispatch_raises_phase_0():
    """Phase 0 dispatcher is a placeholder — Phase 2+ implements it."""
    with pytest.raises(NotImplementedError):
        dispatch({}, {"action": "cmd_march"})


def test_illegal_action_includes_citation():
    """Per BRIEF: error messages MUST include rule citations."""
    err = IllegalAction("BAD_LADEN", "Lord exceeds 2x Provender per Cart", citation="4.3.2")
    assert "4.3.2" in str(err)
    assert err.code == "BAD_LADEN"
    assert err.citation == "4.3.2"


# ----------------------------------------------------------------- legal-moves
def test_legal_moves_returns_phase_0_stub_marker():
    moves = enumerate_legal({})
    assert isinstance(moves, list)
    assert len(moves) == 1
    assert moves[0]["action"] == "<phase_0_stub>"


# ----------------------------------------------------------------- CLI end-to-end
def _run_cli(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "inferno.cli", *args],
        capture_output=True, text=True, check=False, cwd=cwd,
    )


def test_cli_help_runs():
    r = _run_cli(["--help"])
    assert r.returncode == 0
    assert "inferno" in r.stdout.lower()


def test_cli_version_runs():
    r = _run_cli(["--version"])
    assert r.returncode == 0
    assert __version__ in r.stdout


def test_cli_scenarios_lists_all_six():
    r = _run_cli(["scenarios"])
    assert r.returncode == 0
    for sid in SCENARIO_IDS:
        assert sid in r.stdout
        assert SCENARIO_NAMES[sid] in r.stdout


def test_cli_new_writes_state_file(tmp_path: Path):
    out = tmp_path / "x.state.json"
    r = _run_cli(["new", "A", "--seed", "42", "--out", str(out)])
    assert r.returncode == 0
    assert out.exists()
    import json
    state = json.loads(out.read_text())
    assert state["meta"]["scenario"] == "A"


def test_cli_state_summary_on_synthetic_stub(tmp_path: Path):
    """Phase 0 helper synthesizes a stub state when file is missing — keeps
    the CLI exercisable end-to-end before the loader exists."""
    r = _run_cli(["state", str(tmp_path / "missing.state.json"), "--mode", "summary"])
    assert r.returncode == 0
    assert "Scenario" in r.stdout or "scenario" in r.stdout.lower()


def test_cli_legal_moves_returns_stub(tmp_path: Path):
    r = _run_cli(["legal-moves", str(tmp_path / "missing.state.json")])
    assert r.returncode == 0
    moves = json.loads(r.stdout)
    assert moves[0]["action"] == "<phase_0_stub>"


def test_cli_pending_history_empty(tmp_path: Path):
    state_file = tmp_path / "missing.state.json"
    r = _run_cli(["pending", str(state_file)])
    assert r.returncode == 0
    assert json.loads(r.stdout) == []

    r = _run_cli(["history", str(state_file)])
    assert r.returncode == 0
    assert json.loads(r.stdout) == []


def test_cli_save_round_trips(tmp_path: Path):
    src = tmp_path / "x.state.json"
    src.write_text(json.dumps({"meta": {"scenario": "A"}, "calendar": {}, "lords": {},
                                "locales": {}, "decks": {}, "capabilities_in_play": [],
                                "pending": [], "history": [], "vp": {"guelph": 0, "ghibelline": 0}}))
    dst = tmp_path / "y.state.json"
    r = _run_cli(["save", str(src), str(dst)])
    assert r.returncode == 0
    assert dst.exists()
    assert json.loads(dst.read_text())["meta"]["scenario"] == "A"


def test_cli_load_validates(tmp_path: Path):
    src = tmp_path / "x.state.json"
    src.write_text(json.dumps({"meta": {"scenario": "A"}}))
    r = _run_cli(["load", str(src)])
    assert r.returncode == 0
    assert "Scenario" in r.stdout or "scenario" in r.stdout.lower()
