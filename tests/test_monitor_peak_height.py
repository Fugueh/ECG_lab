import numpy as np
from scipy.signal import find_peaks

from ecg_lab.app.monitor import MonitorRuntime


def _runtime_with(data):
    runtime = MonitorRuntime.__new__(MonitorRuntime)
    runtime.data = np.asarray(data, dtype=float)
    return runtime


def _beats(baseline, p_wave, r_wave, count=14):
    beat = np.full(38, float(baseline))
    beat[10] = baseline + p_wave
    beat[17] = baseline + r_wave
    return np.tile(beat, count)


def test_peak_height_follows_baseline_shift():
    # 基线抬高后 P 波越过了旧的固定阈值 350，自适应阈值仍然只留下 R 波
    data = _beats(baseline=332, p_wave=25, r_wave=150)
    height = _runtime_with(data).peak_height()

    assert 332 + 25 < height < 332 + 150

    # 实时情况：最新一拍的 P 波刚出现、R 波还没到
    live = data[: 13 * 38 + 12]
    last_fixed = find_peaks(live, height=350, distance=20)[0][-1]
    last_adaptive = find_peaks(live, height=_runtime_with(live).peak_height(), distance=20)[0][-1]

    assert last_fixed % 38 == 10  # 固定阈值把 P 波当成了最新的心搏
    assert last_adaptive % 38 == 17  # 自适应阈值仍然停在上一个 R 波


def test_peak_height_falls_back_until_buffer_has_data():
    startup = np.zeros(2500)
    startup[-50:] = 330
    lead_off = np.full(2500, np.nan)

    assert _runtime_with(startup).peak_height() == MonitorRuntime.peak_height_fallback
    assert _runtime_with(lead_off).peak_height() == MonitorRuntime.peak_height_fallback
