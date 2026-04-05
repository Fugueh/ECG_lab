from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from ecg_lab.config import get_repo_root


LEGACY_VIEWER_SCRIPT = get_repo_root() / "app" / "viewer_gui" / "ecg_viewer_multi.py"


def _load_legacy_viewer_module(script_path: Path):
    """Load the legacy viewer script as a module without editing the script itself."""
    spec = importlib.util.spec_from_file_location("ecg_lab_legacy_viewer_multi", script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load viewer script: {script_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def launch_viewer(ecg_file: str) -> None:
    """Launch the legacy multi-view ECG viewer through the package entry point."""
    script_path = LEGACY_VIEWER_SCRIPT
    if not script_path.exists():
        raise FileNotFoundError(f"Viewer script not found: {script_path}")

    module = _load_legacy_viewer_module(script_path)
    if not hasattr(module, "main"):
        raise AttributeError(f"Viewer script does not expose a main() entry point: {script_path}")

    old_argv = sys.argv[:]
    try:
        sys.argv = [str(script_path), ecg_file]
        module.main()
    finally:
        sys.argv = old_argv
