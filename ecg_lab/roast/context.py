from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from ..config import get_repo_root

LATE_NIGHT_START_HOUR = 23
LATE_NIGHT_END_HOUR = 6
MAX_OBSERVE_GAP_S = 1.0
HOURLY_WINDOW_HOURS = 24
MAX_DAILY_ROWS = 14
MAX_EVENT_ROWS = 15
MAX_EVENT_TEXT = 80
MAX_TAGS = 10


def get_roast_context_dir() -> Path:
    """Roast 上下文目录：环境变量 > 仓库根目录下的 roast_context/"""
    env_dir = os.getenv("ECG_LAB_ROAST_CONTEXT_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    return get_repo_root() / "roast_context"


def append_record(directory: Path, record: dict, now: float, prefix: str = "roast") -> None:
    """往当天的 JSONL 追加一条记录（分钟数据和用户事件共用同一个文件；prefix 区分不同监视器）"""
    path = Path(directory) / f"{prefix}_{datetime.fromtimestamp(now):%Y-%m-%d}.jsonl"
    Path(directory).mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _iso(now: float) -> str:
    return datetime.fromtimestamp(now).isoformat(timespec="seconds")


def _round(value):
    return None if value is None else int(round(float(value)))


class RoastContextRecorder:
    """Collects per-minute roast metadata and appends it to a daily JSONL file."""

    def __init__(self, directory: Path | None = None):
        self.directory = Path(directory) if directory is not None else get_roast_context_dir()
        self.session = None
        self._session_started_at = None
        self._last_phrase = None
        self._last_observe = None
        self._lead_off = False
        self._write_failed = False
        self._reset_minute()

    def _reset_minute(self) -> None:
        self._hr_min = None
        self._hr_max = None
        self._flips = 0
        self._lead_off_s = 0.0
        self._lead_off_events = 0

    def _write(self, record: dict, now: float) -> None:
        try:
            append_record(self.directory, record, now)
        except OSError as exc:
            # 采集失败不应该把监视器带崩，只提示一次
            if not self._write_failed:
                print(f"Roast context write failed: {exc}", flush=True)
                self._write_failed = True

    def start_session(self, now: float) -> None:
        self.session = _iso(now)
        self._session_started_at = now
        self._write({"type": "session_start", "ts": self.session, "session": self.session}, now)

    def end_session(self, now: float) -> None:
        if self.session is None:
            return
        self._write(
            {
                "type": "session_end",
                "ts": _iso(now),
                "session": self.session,
                "duration_s": _round(now - self._session_started_at),
            },
            now,
        )
        self.session = None

    def observe(self, now: float, mean_hr, phrase: str, lead_off: bool) -> None:
        if lead_off:
            if not self._lead_off:
                self._lead_off_events += 1
            elif self._last_observe is not None:
                self._lead_off_s += min(now - self._last_observe, MAX_OBSERVE_GAP_S)
        else:
            if mean_hr is not None:
                self._hr_min = mean_hr if self._hr_min is None else min(self._hr_min, mean_hr)
                self._hr_max = mean_hr if self._hr_max is None else max(self._hr_max, mean_hr)
            if self._last_phrase is not None and phrase != self._last_phrase:
                self._flips += 1
            self._last_phrase = phrase

        self._lead_off = lead_off
        self._last_observe = now

    @property
    def lead_off_seconds(self) -> float:
        return self._lead_off_s

    def flush_minute(
        self, now: float, *, hr, sdnn, rmssd, roast: str, beats_ok: int, beats_rejected: int, hr_avg=None, **extra
    ) -> None:
        self._write(
            {
                "type": "minute",
                "ts": _iso(now),
                "session": self.session,
                "hr": _round(hr),
                "hr_avg": _round(hr_avg),
                "hr_min": _round(self._hr_min),
                "hr_max": _round(self._hr_max),
                "sdnn": _round(sdnn),
                "rmssd": _round(rmssd),
                "roast": roast,
                "flips": self._flips,
                "beats_ok": int(beats_ok),
                "beats_rejected": int(beats_rejected),
                "lead_off_s": _round(self._lead_off_s),
                "lead_off_events": self._lead_off_events,
                **extra,
            },
            now,
        )
        self._reset_minute()


def load_records(directory: Path, since: datetime, until: datetime, prefix: str = "roast") -> list[dict]:
    records = []
    day = since.date()
    while day <= until.date():
        path = Path(directory) / f"{prefix}_{day:%Y-%m-%d}.jsonl"
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    record = json.loads(line)
                    record["_t"] = datetime.fromisoformat(record["ts"])
                except (ValueError, KeyError, TypeError):
                    # 进程被杀时最后一行可能只写了一半
                    continue
                if since <= record["_t"] <= until:
                    records.append(record)
        day += timedelta(days=1)
    return records


def _stamp(moment: datetime) -> str:
    return f"{moment:%m-%d %H:%M}"


def _extreme(minutes: list[dict], key: str, pick):
    candidates = [m for m in minutes if m.get(key) is not None]
    if not candidates:
        return None
    return pick(candidates, key=lambda m: m[key])


def _longest_streak(minutes: list[dict]):
    best = None
    run = []
    for minute in minutes:
        if run and (minute["roast"] != run[-1]["roast"] or minute.get("session") != run[-1].get("session")):
            run = []
        run.append(minute)
        if best is None or len(run) > len(best):
            best = list(run)
    return best


def _trend(minutes: list[dict], key: str) -> str:
    values = [m for m in minutes if m.get(key) is not None]
    if not values:
        return f"{key} --"
    lowest = min(values, key=lambda m: m[key])
    return f"{key} {values[0][key]} -> {values[-1][key]} (min {lowest[key]} @ {_stamp(lowest['_t'])})"


def _minute_hr(minute: dict):
    return minute["hr_avg"] if minute.get("hr_avg") is not None else minute.get("hr")


def _mean_text(group: list[dict], key: str, spec: str = ".0f") -> str:
    values = [_minute_hr(m) if key == "hr" else m.get(key) for m in group]
    values = [value for value in values if value is not None]
    return format(sum(values) / len(values), spec) if values else "--"


HISTORY_HEADING = f"## history (per hour for the last {HOURLY_WINDOW_HOURS} h, per day before that)"


def bucket_by_age(minutes: list[dict], now: datetime) -> tuple[dict[str, list[dict]], int]:
    """越久远越粗：最近 HOURLY_WINDOW_HOURS 小时按小时分组，更早的按天，最多 MAX_DAILY_ROWS 天。

    返回 (分组, 被省略的天数)。
    """
    hourly_since = now - timedelta(hours=HOURLY_WINDOW_HOURS)
    daily: dict[str, list[dict]] = {}
    hourly: dict[str, list[dict]] = {}
    for minute in minutes:
        if minute["_t"] >= hourly_since:
            hourly.setdefault(f"{minute['_t']:%m-%d %H}h", []).append(minute)
        else:
            daily.setdefault(f"{minute['_t']:%m-%d}", []).append(minute)
    day_keys = list(daily)
    omitted = max(0, len(day_keys) - MAX_DAILY_ROWS)
    return {key: daily[key] for key in day_keys[omitted:]} | hourly, omitted


def _history_table(minutes: list[dict], now: datetime) -> list[str]:
    buckets, omitted = bucket_by_age(minutes, now)
    lines = [HISTORY_HEADING]
    if omitted:
        lines.append(f"({omitted} older days omitted)")
    keys = list(buckets)
    lines.append("| when | min | HR mean (lo-hi) | SDNN | RMSSD | top verdict | flips | rejected | lead off s | nk2 score |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for key in keys:
        group = buckets[key]
        lows = [m["hr_min"] for m in group if m.get("hr_min") is not None]
        highs = [m["hr_max"] for m in group if m.get("hr_max") is not None]
        hr_range = f"{min(lows)}-{max(highs)}" if lows and highs else "--"
        verdict, count = Counter(m["roast"] for m in group).most_common(1)[0]
        lines.append(
            f"| {key} | {len(group)} | {_mean_text(group, 'hr')} ({hr_range}) | {_mean_text(group, 'sdnn')} "
            f"| {_mean_text(group, 'rmssd')} | {verdict} {count}/{len(group)} "
            f"| {sum(m.get('flips', 0) for m in group)} | {sum(m.get('beats_rejected', 0) for m in group)} "
            f"| {sum(m.get('lead_off_s') or 0 for m in group)} | {_mean_text(group, 'sq_score', '.2f')} |"
        )
    return lines


def _event_lines(events: list[dict]) -> list[str]:
    """用户在事件面板里自己记的事件：最近 MAX_EVENT_ROWS 条给原文，更早的只体现在标签计数里"""
    shown = events[-MAX_EVENT_ROWS:]
    lines = [f"## events (logged by the user, last {len(shown)} of {len(events)})"]
    tags = Counter(tag for event in events for tag in event.get("tags", []))
    if tags:
        top = tags.most_common(MAX_TAGS)
        more = f" (+{len(tags) - len(top)} more tags)" if len(tags) > len(top) else ""
        lines.append("tags: " + ", ".join(f"#{tag} x{count}" for tag, count in top) + more)
    for event in shown:
        text = event.get("text", "")
        if len(text) > MAX_EVENT_TEXT:
            text = text[:MAX_EVENT_TEXT] + "…"
        row = f"{_stamp(event['_t'])} {text}"
        if event.get("hr") is not None:
            row += f" (HR {event['hr']}" + (f" {event['roast']}" if event.get("roast") else "") + ")"
        lines.append(row)
    return lines


def format_summary(records: list[dict], now: datetime, hours: float, tail: int = 10) -> str:
    minutes = [r for r in records if r.get("type") == "minute"]
    events = [r for r in records if r.get("type") == "event"]
    if not minutes and not events:
        return (
            f"No roast context in the last {hours:g} h. "
            "Run `python -m ecg_lab.cli monitor --variant roast` for at least a minute first."
        )

    lines = [f"# Roast context: last {hours:g} h, generated {now:%Y-%m-%d %H:%M} ({now:%A})"]
    if minutes:
        lines.extend(_minute_lines(records, minutes, now, tail))
    if events:
        lines.append("")
        lines.extend(_event_lines(events))
    return "\n".join(lines)


def _minute_lines(records: list[dict], minutes: list[dict], now: datetime, tail: int) -> list[str]:
    lines = []
    sessions = {r.get("session") for r in records if r.get("session")}
    ended = [r for r in records if r.get("type") == "session_end"]
    age_min = (now - minutes[-1]["_t"]).total_seconds() / 60
    lines.append(
        f"sessions: {len(sessions)} ({len(ended)} closed cleanly) | monitored: {len(minutes)} min | "
        f"first {_stamp(minutes[0]['_t'])} | last {_stamp(minutes[-1]['_t'])} ({age_min:.0f} min ago)"
    )

    # 优先用分钟平均心率；旧记录只有整分那一刻的快照
    hr_values = [_minute_hr(m) for m in minutes if _minute_hr(m) is not None]
    if hr_values:
        low = _extreme(minutes, "hr_min", min) or _extreme(minutes, "hr", min)
        high = _extreme(minutes, "hr_max", max) or _extreme(minutes, "hr", max)
        low_value = low["hr_min"] if low.get("hr_min") is not None else low["hr"]
        high_value = high["hr_max"] if high.get("hr_max") is not None else high["hr"]
        lines.append(
            f"hr: mean {sum(hr_values) / len(hr_values):.0f} bpm | "
            f"lowest {low_value} @ {_stamp(low['_t'])} | highest {high_value} @ {_stamp(high['_t'])}"
        )

    tiers = Counter(m["roast"] for m in minutes)
    lines.append("verdicts (minutes): " + ", ".join(f"{phrase} x{count}" for phrase, count in tiers.most_common()))

    streak = _longest_streak(minutes)
    lines.append(
        f"longest streak: {streak[0]['roast']} x{len(streak)} "
        f"({_stamp(streak[0]['_t'])} -> {_stamp(streak[-1]['_t'])})"
    )
    lines.append(f"verdict flips (live, within minutes): {sum(m.get('flips', 0) for m in minutes)}")
    lines.append(f"hrv: {_trend(minutes, 'sdnn')} | {_trend(minutes, 'rmssd')}")

    beats_ok = sum(m.get("beats_ok", 0) for m in minutes)
    beats_rejected = sum(m.get("beats_rejected", 0) for m in minutes)
    lines.append(f"beats: accepted {beats_ok}, rejected {beats_rejected} (rejected = detection artifacts, excluded from HR/HRV)")

    hrv_verdicts = Counter(m["hrv_roast"] for m in minutes if m.get("hrv_roast"))
    if hrv_verdicts:
        lines.append("hrv verdicts (minutes): " + ", ".join(f"{p} x{c}" for p, c in hrv_verdicts.most_common()))

    graded = [m for m in minutes if m.get("sq")]
    if graded:
        grades = Counter(m["sq"] for m in graded)
        signal_line = "signal quality (minutes): " + ", ".join(f"{g} x{c}" for g, c in sorted(grades.items()))
        scored = [m for m in graded if m.get("sq_score") is not None]
        if scored:
            worst = min(scored, key=lambda m: m["sq_score"])
            signal_line += (
                f" | mean nk2 score {sum(m['sq_score'] for m in scored) / len(scored):.2f}"
                f" | worst @ {_stamp(worst['_t'])}: {worst.get('sq_note', '')}"
            )
        lines.append(signal_line)

    lead_off_events = sum(m.get("lead_off_events", 0) for m in minutes)
    lead_off_s = sum(m.get("lead_off_s") or 0 for m in minutes)
    lines.append(f"lead off: {lead_off_events} time(s), {lead_off_s} s total")

    late = sum(1 for m in minutes if m["_t"].hour >= LATE_NIGHT_START_HOUR or m["_t"].hour < LATE_NIGHT_END_HOUR)
    weekend = sum(1 for m in minutes if m["_t"].weekday() >= 5)
    lines.append(f"odd hours: late night (23-06) {late} min, weekend {weekend} min")

    shown = minutes[-tail:] if tail > 0 else []
    if len(minutes) > len(shown):
        lines.append("")
        lines.extend(_history_table(minutes, now))
    if shown:
        lines.append("")
        lines.append(f"## per minute (last {len(shown)})")
    for m in shown:
        row = (
            f"{m['_t']:%H:%M} HR {m.get('hr') if m.get('hr') is not None else '--'}"
            f" avg {m.get('hr_avg') if m.get('hr_avg') is not None else '--'}"
            f" ({m.get('hr_min') if m.get('hr_min') is not None else '--'}"
            f"-{m.get('hr_max') if m.get('hr_max') is not None else '--'})"
            f" SDNN {m.get('sdnn') if m.get('sdnn') is not None else '--'}"
            f" RMSSD {m.get('rmssd') if m.get('rmssd') is not None else '--'}"
            f" | {m['roast']}"
        )
        if m.get("hrv_roast"):
            row += f"｜{m['hrv_roast']}"
        if m.get("sq"):
            row += f" | signal {m['sq']}" + (f" {m['sq_score']:.2f}" if m.get("sq_score") is not None else "")
        if m.get("flips"):
            row += f" | flips {m['flips']}"
        if m.get("beats_rejected"):
            row += f" | rejected {m['beats_rejected']}"
        if m.get("lead_off_events") or m.get("lead_off_s"):
            row += f" | lead off {m.get('lead_off_events', 0)}x {m.get('lead_off_s') or 0}s"
        lines.append(row)

    return lines


def summarize(hours: float = 24.0, tail: int = 10,directory: Path | None = None, now: datetime | None = None) -> str:
    now = now or datetime.now()
    directory = Path(directory) if directory is not None else get_roast_context_dir()
    records = load_records(directory, now - timedelta(hours=hours), now)
    return format_summary(records, now, hours, tail)
