import importlib.util
from pathlib import Path
import sys
import types

import numpy as np


def load_viewer_module():
    script_path = Path(__file__).resolve().parents[1] / "app" / "viewer_gui" / "ecg_viewer_multi.py"
    spec = importlib.util.spec_from_file_location("test_ecg_viewer_multi", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_calc_avg_hr_uses_neurokit_r_peaks(monkeypatch):
    module = load_viewer_module()
    calls = {}

    def fake_ecg_clean(ecg):
        calls["ecg_clean_input"] = np.array(ecg)
        return np.array(ecg) + 1

    def fake_ecg_peaks(cleaned, sampling_rate):
        calls["ecg_peaks_input"] = np.array(cleaned)
        calls["sampling_rate"] = sampling_rate
        return None, {"ECG_R_Peaks": np.array([10, 60, 110])}

    fake_nk = types.SimpleNamespace(ecg_clean=fake_ecg_clean, ecg_peaks=fake_ecg_peaks)
    monkeypatch.setitem(sys.modules, "neurokit2", fake_nk)

    timestamps = np.arange(0, 2.0, 1 / module.FS)
    ecg = np.linspace(100, 200, len(timestamps))

    avg_hr = module.calc_avg_hr(timestamps, ecg)

    assert np.isclose(avg_hr, 300.0)
    np.testing.assert_array_equal(calls["ecg_clean_input"], ecg)
    np.testing.assert_array_equal(calls["ecg_peaks_input"], ecg + 1)
    assert calls["sampling_rate"] == module.FS


def test_calc_avg_hr_returns_nan_when_fewer_than_two_peaks(monkeypatch):
    module = load_viewer_module()

    fake_nk = types.SimpleNamespace(
        ecg_clean=lambda ecg: ecg,
        ecg_peaks=lambda cleaned, sampling_rate: (None, {"ECG_R_Peaks": np.array([25])}),
    )
    monkeypatch.setitem(sys.modules, "neurokit2", fake_nk)

    timestamps = np.arange(0, 1.0, 1 / module.FS)
    ecg = np.ones(len(timestamps))

    assert np.isnan(module.calc_avg_hr(timestamps, ecg))
