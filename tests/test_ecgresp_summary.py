from datetime import datetime, timedelta

from ecg_lab.roast.context import append_record
from ecg_lab.roast.ecgresp_summary import summarize_ecgresp


def _minute(moment, hr=60, sq="A", zero_s=0.0):
    return {
        "type": "minute",
        "ts": moment.isoformat(timespec="seconds"),
        "session": "night",
        "hr_avg": hr,
        "board_hr_avg": hr,
        "board_hr_zero_s": zero_s,
        "board_resp_avg": 14,
        "board_resp_min": 12,
        "board_resp_max": 16,
        "sdnn": 60,
        "rmssd": 50,
        "sq": sq,
        "sq_score": 0.85,
        "seq_gaps": 0,
        "bad_frames": 0,
    }


def test_overnight_summary_is_short_and_layered(tmp_path):
    start = datetime(2026, 10, 17, 0, 30)
    now = start + timedelta(hours=8)
    append_record(tmp_path, {"type": "session_start", "ts": start.isoformat(), "session": "night"}, start.timestamp(), prefix="ecgresp")
    for index in range(8 * 60):
        moment = start + timedelta(minutes=index)
        hr = 52 if moment.hour == 4 else 60
        sq = "D" if 200 <= index < 205 else "A"
        zero_s = 45.0 if index == 300 else 0.0
        append_record(tmp_path, _minute(moment, hr, sq, zero_s), moment.timestamp(), prefix="ecgresp")

    text = summarize_ecgresp(hours=12, directory=tmp_path, now=now)

    assert len(text) < 3000
    assert "recorded: 480 min" in text
    assert "hr: median 60 bpm | lowest 52 @ 10-17 04:00" in text
    assert "unreliable periods (signal D/? or lead off): 10-17 03:50-03:54, 10-17 05:30" in text
    assert text.count("| 10-17 ") == 9  # 00h 到 08h，每小时一行
    assert "## per minute (last 10)" in text
    assert "吐槽" not in text and "急了" not in text


def test_summary_without_ecgresp_data(tmp_path):
    text = summarize_ecgresp(hours=8, directory=tmp_path, now=datetime(2026, 10, 17, 8, 0))

    assert text.startswith("No ECG/RESP context in the last 8 h")
