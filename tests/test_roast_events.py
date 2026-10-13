from datetime import datetime

from ecg_lab.roast.context import summarize
from ecg_lab.roast.events import (
    get_event_buttons,
    load_recent_events,
    load_tag_history,
    log_event,
    parse_tags,
    save_event_buttons,
    tag_prefix_at,
)


def _ts(hour, minute):
    return datetime(2026, 10, 13, hour, minute).timestamp()


def test_parse_tags_handles_chinese_and_duplicates():
    assert parse_tags("第三杯 #咖啡 了 #续命#咖啡") == ["咖啡", "续命"]
    assert parse_tags("没有标签") == []


def test_tag_prefix_at_only_inside_a_tag():
    assert tag_prefix_at("喝 #咖", 4) == (2, "咖")
    assert tag_prefix_at("喝 #", 3) == (2, "")
    assert tag_prefix_at("喝 #咖啡 完了", 8) is None
    assert tag_prefix_at("没有标签", 4) is None


def test_log_event_and_tag_history(tmp_path):
    log_event("第三杯 #咖啡", _ts(16, 45), directory=tmp_path, context={"hr": 82, "roast": "急了？"})
    log_event("#开会 #咖啡", _ts(16, 50), source="button", directory=tmp_path)

    assert log_event("   ", _ts(16, 51), directory=tmp_path) is None
    assert load_tag_history(tmp_path) == ["咖啡", "开会"]


def test_summarize_lists_events_without_minute_data(tmp_path):
    log_event("第三杯 #咖啡", _ts(16, 45), directory=tmp_path, context={"hr": 82, "roast": "急了？"})
    log_event("#开会", _ts(16, 50), source="button", directory=tmp_path)

    text = summarize(hours=24, directory=tmp_path, now=datetime(2026, 10, 13, 17, 0))

    assert "## events (logged by the user, last 2 of 2)" in text
    assert "tags: #咖啡 x1, #开会 x1" in text
    assert "10-13 16:45 第三杯 #咖啡 (HR 82 急了？)" in text
    assert "10-13 16:50 #开会" in text


def test_event_buttons_saved_file_beats_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ECG_LAB_ROAST_EVENTS", "喝水, #组会，午睡")

    assert get_event_buttons(tmp_path) == ["喝水", "组会", "午睡"]

    save_event_buttons(["喝水", "被老板叫走"], tmp_path)

    assert get_event_buttons(tmp_path) == ["喝水", "被老板叫走"]


def test_load_recent_events_returns_latest_in_order(tmp_path):
    for minute in range(7):
        log_event(f"事件{minute}", _ts(16, minute), directory=tmp_path)

    assert [event["text"] for event in load_recent_events(5, tmp_path)] == [f"事件{i}" for i in range(2, 7)]
