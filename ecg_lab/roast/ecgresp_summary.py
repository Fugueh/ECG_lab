"""把 ecgresp 的每分钟记录压缩成一份短摘要：只有数据，没有吐槽文本。

越久远越粗：整体统计 + 按小时（更早按天）的表 + 信号差的时段 + 最近几分钟明细。
只依赖标准库，不需要 Qt 或 neurokit2。
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

from .context import HISTORY_HEADING, bucket_by_age, get_roast_context_dir, load_records

FILE_PREFIX = "ecgresp"
BAD_SIGNAL = {"D", "?"}
LEAD_OFF_MINUTE_S = 30
MAX_BAD_PERIODS = 10


def _stamp(moment: datetime) -> str:
    return f"{moment:%m-%d %H:%M}"


def _text(value) -> str:
    return "--" if value is None else str(value)


def _values(minutes: list[dict], key: str) -> list:
    return [m[key] for m in minutes if m.get(key) is not None]


def _mean(minutes: list[dict], key: str, spec: str = ".0f") -> str:
    values = _values(minutes, key)
    return format(sum(values) / len(values), spec) if values else "--"


def _range(minutes: list[dict], low_key: str, high_key: str) -> str:
    lows, highs = _values(minutes, low_key), _values(minutes, high_key)
    return f"{min(lows)}-{max(highs)}" if lows and highs else "--"


def _extreme_line(name: str, minutes: list[dict], key: str, unit: str = "") -> str:
    candidates = [m for m in minutes if m.get(key) is not None]
    if not candidates:
        return f"{name}: --"
    low = min(candidates, key=lambda m: m[key])
    high = max(candidates, key=lambda m: m[key])
    values = [m[key] for m in candidates]
    return (
        f"{name}: median {median(values):.0f}{unit} | lowest {low[key]} @ {_stamp(low['_t'])}"
        f" | highest {high[key]} @ {_stamp(high['_t'])}"
    )


def _is_bad(minute: dict) -> bool:
    return minute.get("sq") in BAD_SIGNAL or (minute.get("board_hr_zero_s") or 0) >= LEAD_OFF_MINUTE_S


def _bad_periods(minutes: list[dict]) -> list[str]:
    """把连续的坏分钟合并成时段，这些时段里的 HR/HRV 不可信"""
    periods = []
    start = previous = None
    for minute in minutes:
        if _is_bad(minute):
            contiguous = previous is not None and minute["_t"] - previous["_t"] <= timedelta(minutes=1.5)
            if not contiguous:
                if start is not None:
                    periods.append((start, previous))
                start = minute
            previous = minute
        elif start is not None:
            periods.append((start, previous))
            start = previous = None
    if start is not None:
        periods.append((start, previous))
    return [
        f"{_stamp(a['_t'])}" + ("" if a is b else f"-{b['_t']:%H:%M}") for a, b in periods
    ]


def _history_rows(minutes: list[dict], now: datetime) -> list[str]:
    buckets, omitted = bucket_by_age(minutes, now)
    lines = [HISTORY_HEADING]
    if omitted:
        lines.append(f"({omitted} older days omitted)")
    lines.append("| when | min | HR mean (lo-hi) | SDNN | RMSSD | resp mean (lo-hi) | nk2 score | bad min |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for key, group in buckets.items():
        lines.append(
            f"| {key} | {len(group)} | {_mean(group, 'hr_avg')} ({_range(group, 'hr_avg', 'hr_avg')})"
            f" | {_mean(group, 'sdnn')} | {_mean(group, 'rmssd')}"
            f" | {_mean(group, 'board_resp_avg')} ({_range(group, 'board_resp_min', 'board_resp_max')})"
            f" | {_mean(group, 'sq_score', '.2f')} | {sum(1 for m in group if _is_bad(m))} |"
        )
    return lines


def format_ecgresp_summary(records: list[dict], now: datetime, hours: float, tail: int = 10) -> str:
    minutes = [r for r in records if r.get("type") == "minute"]
    if not minutes:
        return (
            f"No ECG/RESP context in the last {hours:g} h. "
            "Run `python -m ecg_lab.cli monitor --variant ecgresp` for at least a minute first."
        )

    sessions = {r.get("session") for r in records if r.get("session")}
    ended = sum(1 for r in records if r.get("type") == "session_end")
    age_min = (now - minutes[-1]["_t"]).total_seconds() / 60
    lines = [
        f"# ECG/RESP context: last {hours:g} h, generated {now:%Y-%m-%d %H:%M} ({now:%A})",
        f"sessions: {len(sessions)} ({ended} closed cleanly) | recorded: {len(minutes)} min | "
        f"first {_stamp(minutes[0]['_t'])} | last {_stamp(minutes[-1]['_t'])} ({age_min:.0f} min ago)",
        "values are per-minute; HR/HRV from NeuroKit2 R-peaks (HRV only when clean RR covers >= half the minute), resp from the board",
        _extreme_line("hr", minutes, "hr_avg", " bpm"),
        f"board hr: mean {_mean(minutes, 'board_hr_avg')} | zero (lead off / not locked) "
        f"{sum(m.get('board_hr_zero_s') or 0 for m in minutes):.0f} s",
        _extreme_line("sdnn", minutes, "sdnn", " ms"),
        _extreme_line("rmssd", minutes, "rmssd", " ms"),
        _extreme_line("resp", minutes, "board_resp_avg", " /min"),
    ]

    grades = Counter(m.get("sq", "?") for m in minutes)
    lines.append(
        "signal quality (minutes): "
        + ", ".join(f"{g} x{c}" for g, c in sorted(grades.items()))
        + f" | mean nk2 score {_mean(minutes, 'sq_score', '.2f')}"
    )
    lines.append(
        f"link: seq gaps {sum(m.get('seq_gaps') or 0 for m in minutes)}, "
        f"bad frames {sum(m.get('bad_frames') or 0 for m in minutes)}"
    )
    bad = _bad_periods(minutes)
    if bad:
        shown = bad[-MAX_BAD_PERIODS:]
        more = f" (+{len(bad) - len(shown)} earlier)" if len(bad) > len(shown) else ""
        lines.append(f"unreliable periods (signal D/? or lead off): {', '.join(shown)}{more}")

    shown_minutes = minutes[-tail:] if tail > 0 else []
    if len(minutes) > len(shown_minutes):
        lines.append("")
        lines.extend(_history_rows(minutes, now))
    if shown_minutes:
        lines.append("")
        lines.append(f"## per minute (last {len(shown_minutes)})")
    for m in shown_minutes:
        lines.append(
            f"{m['_t']:%H:%M} HR {_text(m.get('hr_avg'))} (board {_text(m.get('board_hr_avg'))})"
            f" SDNN {_text(m.get('sdnn'))} RMSSD {_text(m.get('rmssd'))}"
            f" resp {_text(m.get('board_resp_avg'))} ({_text(m.get('board_resp_min'))}-{_text(m.get('board_resp_max'))})"
            f" | signal {m.get('sq', '?')} {_text(m.get('sq_score'))}"
        )
    return "\n".join(lines)


def summarize_ecgresp(hours: float = 24.0, tail: int = 10, directory: Path | None = None, now: datetime | None = None) -> str:
    now = now or datetime.now()
    directory = Path(directory) if directory is not None else get_roast_context_dir()
    records = load_records(directory, now - timedelta(hours=hours), now, prefix=FILE_PREFIX)
    return format_ecgresp_summary(records, now, hours, tail)
