from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from .context import append_record, get_roast_context_dir

DEFAULT_EVENT_BUTTONS = ("咖啡", "吃饭", "起身活动", "开会", "被打断", "摸鱼", "改bug")
TAG_PATTERN = re.compile(r"#([^\s#]+)")
TAG_HISTORY_FILES = 60
BUTTONS_FILE = "event_buttons.json"


def _buttons_file(directory: Path | None) -> Path:
    return (Path(directory) if directory is not None else get_roast_context_dir()) / BUTTONS_FILE


def get_event_buttons(directory: Path | None = None) -> list[str]:
    """事件按钮：面板里改过的 event_buttons.json > 环境变量 ECG_LAB_ROAST_EVENTS（逗号分隔）> 默认列表"""
    try:
        saved = json.loads(_buttons_file(directory).read_text(encoding="utf-8"))
        # 存过就以文件为准，包括用户把按钮全删光的情况
        if isinstance(saved, list) and all(isinstance(label, str) for label in saved):
            return saved
    except (OSError, ValueError):
        pass
    configured = os.getenv("ECG_LAB_ROAST_EVENTS", "")
    labels = [label.strip().lstrip("#") for label in configured.replace("，", ",").split(",")]
    labels = [label for label in labels if label]
    return labels or list(DEFAULT_EVENT_BUTTONS)


def save_event_buttons(labels: list[str], directory: Path | None = None) -> None:
    path = _buttons_file(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")


def load_recent_events(limit: int = 5, directory: Path | None = None) -> list[dict]:
    """最近的几条事件，按时间从旧到新"""
    directory = Path(directory) if directory is not None else get_roast_context_dir()
    events: list[dict] = []
    for path in sorted(directory.glob("roast_*.jsonl"), reverse=True):
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            if '"event"' not in line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("type") == "event":
                events.append(record)
                if len(events) >= limit:
                    return events[::-1]
    return events[::-1]


def parse_tags(text: str) -> list[str]:
    tags = []
    for tag in TAG_PATTERN.findall(text):
        if tag not in tags:
            tags.append(tag)
    return tags


def tag_prefix_at(text: str, cursor: int):
    """光标正处在一个 #标签 里时，返回 (# 的位置, 已输入的前缀)，否则返回 None"""
    start = text.rfind("#", 0, cursor)
    if start < 0:
        return None
    prefix = text[start + 1 : cursor]
    if any(char.isspace() for char in prefix):
        return None
    return start, prefix


def log_event(text: str, now: float, source: str = "input", context: dict | None = None, directory: Path | None = None):
    """把一条用户事件写进当天的吐槽上下文；空文本返回 None"""
    text = text.strip()
    if not text:
        return None
    record = {
        "type": "event",
        "ts": datetime.fromtimestamp(now).isoformat(timespec="seconds"),
        "text": text,
        "tags": parse_tags(text),
        "source": source,
        **(context or {}),
    }
    append_record(directory if directory is not None else get_roast_context_dir(), record, now)
    return record


def load_tag_history(directory: Path | None = None) -> list[str]:
    """历史标签，按使用次数从多到少（只看最近 TAG_HISTORY_FILES 天的文件）"""
    directory = Path(directory) if directory is not None else get_roast_context_dir()
    counts: Counter[str] = Counter()
    for path in sorted(directory.glob("roast_*.jsonl"))[-TAG_HISTORY_FILES:]:
        for line in path.read_text(encoding="utf-8").splitlines():
            if '"event"' not in line:
                continue
            try:
                counts.update(json.loads(line).get("tags", []))
            except ValueError:
                continue
    return [tag for tag, _ in counts.most_common()]
