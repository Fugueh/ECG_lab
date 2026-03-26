import numpy as np
import pandas as pd

from ecg_core.rr_hr_hrv import BeatCalc, random_time_slice


def test_random_time_slice_rejects_short_records():
    frame = pd.DataFrame({"time": np.linspace(0.0, 1.0, 10), "ecg": np.zeros(10)})

    try:
        random_time_slice(frame, 2.0)
    except ValueError as exc:
        assert "shorter than the requested slice length" in str(exc)
    else:
        raise AssertionError("random_time_slice should reject slices longer than the record")


def test_beatcalc_estimates_hr_and_hrv():
    fs = 250
    duration_s = 8
    times = np.arange(0, duration_s, 1 / fs)
    ecg = np.zeros_like(times)
    peak_positions = [125, 375, 625, 875, 1125, 1375, 1625, 1875]
    ecg[peak_positions] = 600
    frame = pd.DataFrame({"time": times, "ecg": ecg})

    result = BeatCalc(frame)

    assert result.n_beats == len(peak_positions)
    assert np.isclose(result.hr, 60.0, atol=0.5)
    assert np.isclose(result.sdnn, 0.0, atol=1e-6)
