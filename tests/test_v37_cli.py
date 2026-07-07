"""v3.7 — exercise the CLI (src/inferno/cli.py), previously at 0% coverage.

Drives every subcommand through `cli.main(argv)` against real state files in a
tmp dir, plus the error/exit-code paths (bad JSON, missing key, IllegalAction,
missing file stub, --version, no-cmd help).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from inferno import cli
from inferno.legal_moves import enumerate_legal


@pytest.fixture
def state_file(tmp_path) -> Path:
    out = tmp_path / "g.state.json"
    rc = cli.main(["new", "A", "--seed", "1", "--out", str(out)])
    assert rc == 0 and out.exists()
    return out


def _load(p: Path):
    return json.loads(p.read_text())


# ----------------------------------------------------------- meta
def test_no_command_prints_help(capsys):
    assert cli.main([]) == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_version_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0


def test_scenarios_lists_six(capsys):
    assert cli.main(["scenarios"]) == 0
    out = capsys.readouterr().out
    for sid in ("A", "B", "C", "D", "E", "F"):
        assert f"{sid}:" in out


# ----------------------------------------------------------- new / load / save
def test_new_creates_valid_state(tmp_path, capsys):
    out = tmp_path / "n.state.json"
    rc = cli.main(["new", "A", "--seed", "1", "--out", str(out)])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "Lords Mustered" in printed
    st = _load(out)
    assert st["meta"]["scenario"] == "A" and st["meta"]["rng_seed"] == 1


def test_load_reports_meta(state_file, capsys):
    assert cli.main(["load", str(state_file)]) == 0
    assert "scenario=A" in capsys.readouterr().out


def test_load_missing_file_uses_stub(tmp_path, capsys):
    # Non-existent path -> synthetic stub, still returns 0.
    assert cli.main(["load", str(tmp_path / "nope.json")]) == 0
    assert "<unset>" in capsys.readouterr().out


def test_save_pretty_prints(state_file, tmp_path):
    out = tmp_path / "saved.json"
    assert cli.main(["save", str(state_file), str(out)]) == 0
    assert _load(out)["meta"]["scenario"] == "A"


# ----------------------------------------------------------- state renders
@pytest.mark.parametrize("extra", [
    ["--mode", "summary"],
    ["--mode", "verbose"],
    ["--calendar"],
    ["--decks"],
    ["--lord", "firenze"],
    ["--locale", "Firenze"],
])
def test_state_render_modes(state_file, capsys, extra):
    assert cli.main(["state", str(state_file)] + extra) == 0
    assert capsys.readouterr().out.strip() != ""


# ----------------------------------------------------------- legal-moves / pending / history
def test_legal_moves_outputs_json(state_file, capsys):
    assert cli.main(["legal-moves", str(state_file)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list) and len(data) >= 1


def test_pending_and_history(state_file, capsys):
    assert cli.main(["pending", str(state_file)]) == 0
    assert isinstance(json.loads(capsys.readouterr().out), list)
    assert cli.main(["history", str(state_file), "-n", "5"]) == 0
    assert isinstance(json.loads(capsys.readouterr().out), list)


# ----------------------------------------------------------- do (success + errors)
def test_do_executes_legal_action(state_file, capsys):
    move = enumerate_legal(_load(state_file))[0]
    action = {"action": move["action"], "side": move.get("side", "guelph"),
              "args": move.get("args", {})}
    rc = cli.main(["do", str(state_file), json.dumps(action)])
    assert rc == 0
    assert "Updated state at" in capsys.readouterr().out
    # History grew by one.
    assert len(_load(state_file)["history"]) >= 1


def test_do_invalid_json_returns_2(state_file, capsys):
    assert cli.main(["do", str(state_file), "{not json"]) == 2
    assert "Invalid action JSON" in capsys.readouterr().out


def test_do_missing_action_key_returns_2(state_file, capsys):
    assert cli.main(["do", str(state_file), '{"side":"guelph"}']) == 2


def test_do_illegal_action_returns_1(state_file, capsys):
    # Wrong-turn / unknown action -> IllegalAction -> exit 1.
    bad = json.dumps({"action": "cmd_storm", "side": "ghibelline", "args": {}})
    assert cli.main(["do", str(state_file), bad]) == 1
    assert "IllegalAction" in capsys.readouterr().out


def test_do_writes_to_out_path(state_file, tmp_path, capsys):
    move = enumerate_legal(_load(state_file))[0]
    action = {"action": move["action"], "side": move.get("side", "guelph"),
              "args": move.get("args", {})}
    out = tmp_path / "after.json"
    assert cli.main(["do", str(state_file), json.dumps(action), "--out", str(out)]) == 0
    assert out.exists()


# ----------------------------------------------------------- briefing / play-event / replay
def test_briefing_emits_text(state_file, capsys):
    assert cli.main(["briefing", str(state_file), "--side", "guelph"]) == 0
    assert capsys.readouterr().out.strip() != ""


def test_play_event_dispatches_and_persists(state_file, capsys):
    # SMOKE-Inferno-094: F3 'Surprise' needs an open Besiege/combat window.
    st = json.loads(state_file.read_text())
    fl = st["lords"]["firenze"]
    st["locales"][fl["location"]].setdefault("siege", []).append(
        {"side": "guelph", "color": "purple", "count": 1})
    state_file.write_text(json.dumps(st))
    rc = cli.main(["play-event", str(state_file), "--side", "guelph", "--card", "F3"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "played" in out and "Updated state at" in out


def test_replay_lists_history(state_file, capsys):
    # Execute one action so there's history to replay.
    move = enumerate_legal(_load(state_file))[0]
    action = {"action": move["action"], "side": move.get("side", "guelph"),
              "args": move.get("args", {})}
    cli.main(["do", str(state_file), json.dumps(action)])
    capsys.readouterr()
    assert cli.main(["replay", str(state_file)]) == 0
    assert "Replaying" in capsys.readouterr().out
