import pytest

from ecg_lab import cli
from ecg_lab.app import monitor as monitor_module


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


def test_cli_launch_monitor_dispatches_variant(monkeypatch):
    calls = {}

    def fake_launch(variant):
        calls["variant"] = variant

    monkeypatch.setattr(cli, "launch_monitor", fake_launch)

    cli.launch_monitor("250hz")

    assert calls["variant"] == "250hz"


def test_monitor_module_rejects_unknown_variant():
    with pytest.raises(ValueError):
        monitor_module.launch_monitor("missing")
