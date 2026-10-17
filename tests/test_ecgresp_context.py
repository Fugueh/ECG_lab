import json

import numpy as np

from ecg_lab.roast.context import append_record
from ecg_lab.roast.ecgresp import ECGRespMinute, hrv_from_rr
from ecg_lab.roast.signal_quality import grade_label


def _packet(hr, rr):
    return np.column_stack([np.arange(5), np.zeros(5)]).astype(np.int32), hr, rr


def test_hrv_from_rr_drops_out_of_range_and_outliers():
    rr = [0.8, 0.82, 0.78] * 25 + [0.12, 2.5, 1.6]

    result = hrv_from_rr(rr)

    assert result["rr_used"] == 75
    assert result["rr_rejected"] == 3
    assert round(result["hr_avg"]) == 75
    assert result["sdnn"] is not None and result["rmssd"] is not None


def test_hrv_needs_enough_beats():
    result = hrv_from_rr([0.8] * 10)

    assert round(result["hr_avg"]) == 75
    assert result["sdnn"] is None and result["rmssd"] is None


def test_minute_record_has_board_and_pc_values_without_text():
    minute = ECGRespMinute()
    for hr, rr in [(80, 14), (0, 0), (84, 16), (82, 15)]:
        minute.add_packet(*_packet(hr, rr))
    metrics = {"score": 0.86, "bad_beat_ratio": 0.05, "beats": 78, "rr_s": [0.77] * 40}

    record = minute.build_record(0.0, "s1", metrics, None, {"seq_gaps": 1, "bad_frames": 0, "dropped_bytes": 3})

    assert record["samples"] == 20 and record["packets"] == 4
    assert (record["board_hr_avg"], record["board_hr_min"], record["board_hr_max"]) == (82, 80, 84)
    assert record["board_hr_zero_s"] == 0.0 or record["board_hr_zero_s"] == 0.02
    assert (record["board_resp_avg"], record["board_resp_min"], record["board_resp_max"]) == (15, 14, 16)
    assert (record["hr_avg"], record["beats"], record["sq"], record["sq_score"]) == (78, 78, "A", 0.86)
    assert record["seq_gaps"] == 1
    assert not any(isinstance(value, str) and len(value) > 20 for value in record.values())


def test_minute_record_without_score():
    record = ECGRespMinute().build_record(0.0, "s1", None, "ValueError", {})

    assert record["sq"] == "?" and record["sq_error"] == "ValueError"
    assert record["hr_avg"] is None and record["board_hr_avg"] is None


def test_grade_label_and_prefixed_file(tmp_path):
    assert grade_label(0.9, 0.04) == "A"
    assert grade_label(0.5, 0.4) == "D"

    append_record(tmp_path, {"type": "minute"}, 0.0, prefix="ecgresp")

    files = list(tmp_path.iterdir())
    assert len(files) == 1 and files[0].name.startswith("ecgresp_")
    assert json.loads(files[0].read_text(encoding="utf-8")) == {"type": "minute"}
