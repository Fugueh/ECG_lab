import pytest

from ecg_lab import cli
from ecg_lab.app import monitor as monitor_module
from ecg_lab.app import viewer as viewer_module


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


def test_build_parser_requires_viewer_file():
    parser = cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["viewer"])


def test_build_parser_accepts_viewer_file():
    parser = cli.build_parser()

    args = parser.parse_args(["viewer", "sample.parquet"])

    assert args.command == "viewer"
    assert args.ecg_file == "sample.parquet"


def test_cli_launch_monitor_dispatches_variant(monkeypatch):
    calls = {}

    def fake_launch(variant):
        calls["variant"] = variant

    monkeypatch.setattr(cli, "launch_monitor", fake_launch)

    cli.launch_monitor("250hz")

    assert calls["variant"] == "250hz"


def test_cli_launch_viewer_dispatches_file(monkeypatch):
    calls = {}

    def fake_launch(ecg_file):
        calls["ecg_file"] = ecg_file

    monkeypatch.setattr(cli, "launch_viewer", fake_launch)

    cli.launch_viewer("sample.parquet")

    assert calls["ecg_file"] == "sample.parquet"


def test_monitor_module_rejects_unknown_variant():
    with pytest.raises(ValueError):
        monitor_module.launch_monitor("missing")


def test_viewer_module_rejects_missing_script(monkeypatch):
    monkeypatch.setattr(viewer_module, "LEGACY_VIEWER_SCRIPT", viewer_module.LEGACY_VIEWER_SCRIPT.parent / "missing.py")

    with pytest.raises(FileNotFoundError):
        viewer_module.launch_viewer("sample.parquet")
