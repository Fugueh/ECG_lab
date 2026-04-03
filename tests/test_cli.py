from pathlib import Path

import pytest

from ecg_lab import cli


def test_build_parser_accepts_monitor_defaults():
    parser = cli.build_parser()

    args = parser.parse_args(["monitor"])

    assert args.command == "monitor"
    assert args.variant == "250hz"


def test_build_parser_accepts_monitor_variant():
    parser = cli.build_parser()

    args = parser.parse_args(["monitor", "--variant", "roast"])

    assert args.command == "monitor"
    assert args.variant == "roast"


def test_launch_monitor_runs_script_from_monitor_dir(monkeypatch):
    calls = {}

    def fake_run(cmd, cwd, check):
        calls["cmd"] = cmd
        calls["cwd"] = cwd
        calls["check"] = check

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    cli.launch_monitor("250hz")

    expected_dir = Path(__file__).resolve().parents[1] / "app" / "monitor"
    assert calls["cmd"][1] == "monitor_250hz.py"
    assert calls["cwd"] == str(expected_dir)
    assert calls["check"] is True


def test_launch_monitor_raises_if_script_missing(monkeypatch):
    monkeypatch.setitem(cli.MONITOR_SCRIPTS, "missing", Path("app") / "monitor" / "not_here.py")

    with pytest.raises(FileNotFoundError):
        cli.launch_monitor("missing")