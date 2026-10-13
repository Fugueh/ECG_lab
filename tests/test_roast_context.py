import json
from datetime import datetime, timedelta

from ecg_lab.roast.context import RoastContextRecorder, summarize
from ecg_lab.roast.events import log_event


def _ts(hour, minute, second=0):
    return datetime(2026, 10, 13, hour, minute, second).timestamp()


def _read(tmp_path):
    path = tmp_path / "roast_2026-10-13.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_recorder_writes_minute_record(tmp_path):
    recorder = RoastContextRecorder(tmp_path)
    recorder.start_session(_ts(15, 44, 57))
    recorder.observe(_ts(15, 45, 0), 79.4, "稳如老狗", False)
    recorder.observe(_ts(15, 45, 30), 86.2, "急了？", False)
    recorder.flush_minute(_ts(15, 45, 57), hr=83.0, sdnn=70.2, rmssd=None, roast="急了？", beats_ok=80, beats_rejected=2, hr_avg=81.6, sq="B", sq_score=0.82)
    recorder.end_session(_ts(15, 46, 57))

    start, minute, end = _read(tmp_path)

    assert start["type"] == "session_start"
    assert minute["hr"] == 83
    assert minute["hr_avg"] == 82
    assert (minute["hr_min"], minute["hr_max"]) == (79, 86)
    assert minute["sdnn"] == 70
    assert minute["rmssd"] is None
    assert minute["flips"] == 1
    assert minute["beats_ok"] == 80
    assert minute["beats_rejected"] == 2
    assert (minute["sq"], minute["sq_score"]) == ("B", 0.82)
    assert end["duration_s"] == 120


def test_recorder_tracks_lead_off_and_resets_each_minute(tmp_path):
    recorder = RoastContextRecorder(tmp_path)
    recorder.start_session(_ts(9, 0))
    recorder.observe(_ts(9, 0, 1), 70.0, "稳如老狗", False)
    for second in (2.0, 2.5, 3.0):
        recorder.observe(_ts(9, 0) + second, None, "稳如老狗", True)
    # 长时间没有帧（比如休眠）不应该全算进脱落时长
    recorder.observe(_ts(9, 0, 50), None, "稳如老狗", True)
    assert recorder.lead_off_seconds == 2.0
    recorder.flush_minute(_ts(9, 1), hr=None, sdnn=None, rmssd=None, roast="你人呢？", beats_ok=0, beats_rejected=0)
    recorder.flush_minute(_ts(9, 2), hr=None, sdnn=None, rmssd=None, roast="你人呢？", beats_ok=0, beats_rejected=0)

    _, first, second = _read(tmp_path)

    assert first["lead_off_events"] == 1
    assert first["lead_off_s"] == 2
    assert second["lead_off_events"] == 0
    assert second["lead_off_s"] == 0
    assert second["hr_min"] is None


def test_summarize_reports_roast_material(tmp_path):
    recorder = RoastContextRecorder(tmp_path)
    recorder.start_session(_ts(15, 45))
    rows = [(83, 70, "急了？", 1, "B", 0.8), (84, 61, "急了？", 0, "A", 0.9), (79, 58, "稳如老狗", 1, "C", 0.7)]
    for index, (hr, sdnn, roast, rejected, sq, sq_score) in enumerate(rows):
        now = _ts(15, 46 + index)
        recorder.observe(now, hr, roast, False)
        recorder.flush_minute(
            now, hr=hr, hr_avg=hr - 2, sdnn=sdnn, rmssd=sdnn, roast=roast, beats_ok=80, beats_rejected=rejected,
            hrv_roast="松弛感拿捏了", sq=sq, sq_score=sq_score, sq_note=f"信号 {sq}",
        )
    (tmp_path / "roast_2026-10-13.jsonl").open("a", encoding="utf-8").write('{"type": "minute", "ts"')

    text = summarize(hours=24, directory=tmp_path, now=datetime(2026, 10, 13, 16, 0))

    assert "monitored: 3 min" in text
    assert "急了？ x2, 稳如老狗 x1" in text
    assert "longest streak: 急了？ x2" in text
    assert "sdnn 70 -> 58 (min 58 @ 10-13 15:48)" in text
    assert "accepted 240, rejected 2" in text
    assert "fake HR" not in text
    assert "hrv verdicts (minutes): 松弛感拿捏了 x3" in text
    assert "signal quality (minutes): A x1, B x1, C x1 | mean nk2 score 0.80 | worst @ 10-13 15:48: 信号 C" in text
    assert "15:48 HR 79 avg 77 (79-79) SDNN 58 RMSSD 58 | 稳如老狗｜松弛感拿捏了 | signal C 0.70 | flips 1 | rejected 1" in text
    assert "lowest 79 @ 10-13 15:48" in text


def test_summarize_rolls_history_into_hourly_table(tmp_path):
    recorder = RoastContextRecorder(tmp_path)
    recorder.start_session(_ts(14, 0))
    for hour, hr, roast in ((14, 72, "稳如老狗"), (15, 86, "急了？")):
        for minute in range(1, 21):
            now = _ts(hour, minute)
            recorder.observe(now, hr, roast, False)
            recorder.flush_minute(now, hr=hr, sdnn=60, rmssd=50, roast=roast, beats_ok=70, beats_rejected=0, sq_score=0.8)

    text = summarize(hours=24, tail=5, directory=tmp_path, now=datetime(2026, 10, 13, 16, 0))

    assert "## history (per hour for the last 24 h, per day before that)" in text
    assert "| 10-13 14h | 20 | 72 (72-72) | 60 | 50 | 稳如老狗 20/20 | 0 | 0 | 0 | 0.80 |" in text
    assert "| 10-13 15h | 20 | 86 (86-86) | 60 | 50 | 急了？ 20/20 | 1 | 0 | 0 | 0.80 |" in text
    assert "## per minute (last 5)" in text
    assert text.count(" HR 86 ") == 5
    assert " HR 72 " not in text


def test_summarize_without_records(tmp_path):
    text = summarize(hours=2, directory=tmp_path, now=datetime(2026, 10, 13, 16, 0))

    assert text.startswith("No roast context in the last 2 h")


def test_summarize_stays_short_and_coarsens_with_age(tmp_path):
    now = datetime(2026, 10, 13, 16, 0)
    recorder = RoastContextRecorder(tmp_path)
    recorder.start_session(now.timestamp())
    # 30 天、每天 10:00-18:00 每分钟一条，外加 300 条很长的事件
    for day in range(30):
        for minute in range(8 * 60):
            moment = (now - timedelta(days=day)).replace(hour=10, minute=0) + timedelta(minutes=minute)
            if moment > now:
                continue
            recorder.flush_minute(
                moment.timestamp(), hr=80, hr_avg=81, sdnn=60, rmssd=45, roast="急了？", beats_ok=80,
                beats_rejected=1, hrv_roast="还剩点弹性", sq="B", sq_score=0.8, sq_note="信号 B",
            )
    for index in range(300):
        log_event(f"#标签{index % 40} " + "很长的备注" * 60, (now - timedelta(minutes=index * 100)).timestamp(), directory=tmp_path)

    text = summarize(hours=24 * 30, directory=tmp_path, now=now)
    history = text.split("## history")[1].split("## per minute")[0]

    assert len(text) < 8000
    assert "(15 older days omitted)" in history
    assert "| 10-12 |" in history and "| 10-13 15h |" in history
    assert "| 10-12 17h |" in history and "| 10-11 17h |" not in history
    assert text.count(" HR 80 avg 81 ") == 10
    assert "last 15 of 300" in text and "(+30 more tags)" in text
