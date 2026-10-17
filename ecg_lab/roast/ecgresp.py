"""ecgresp 监视器的每分钟上下文：只记数据，不带界面和吐槽文本。

写到吐槽上下文目录下的 ecgresp_YYYY-MM-DD.jsonl，原始 CSV 照旧保存。
"""

from __future__ import annotations

import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import numpy as np

from ecg_lab.app.monitor import ECGRespMonitor, ECGRespRuntime

from .context import append_record, get_roast_context_dir
from .signal_quality import grade_label, score_minute

FILE_PREFIX = "ecgresp"
MINUTE_SECONDS = 60.0
RR_MIN_S = 0.3
RR_MAX_S = 2.0
RR_JUMP_LIMIT = 0.2
MIN_RR_FOR_HRV = 20
MIN_RR_COVERAGE = 0.5


def launch_ecgresp_monitor() -> None:
    ContextECGRespMonitor().run()


def _iso(now: float) -> str:
    return datetime.fromtimestamp(now).isoformat(timespec="seconds")


def _round(value, digits: int = 0):
    if value is None:
        return None
    return int(round(float(value))) if digits == 0 else round(float(value), digits)


def _stats(values: list[int]) -> tuple:
    """板端 HR/呼吸率的均值、最小、最大，0 表示板子没算出来，不参与统计"""
    valid = [value for value in values if value > 0]
    if not valid:
        return None, None, None
    return float(np.mean(valid)), min(valid), max(valid)


def clean_rr(rr_s: list[float]) -> np.ndarray:
    """去掉生理范围外的间期，再用 20% 规则去掉和前一个正常间期相差过大的（漏检、多检）"""
    rr = np.asarray(rr_s, dtype=float)
    rr = rr[(rr >= RR_MIN_S) & (rr <= RR_MAX_S)]
    if len(rr) < 3:
        return rr
    kept = []
    reference = float(np.median(rr))
    for value in rr:
        if abs(value - reference) <= RR_JUMP_LIMIT * reference:
            kept.append(value)
            reference = value
    return np.asarray(kept)


def hrv_from_rr(rr_s: list[float], minute_s: float = MINUTE_SECONDS) -> dict:
    """用这一分钟 nk2 检出的 RR 算平均心率和 HRV。

    干净间期覆盖不到这一分钟的一半时，说明漏检太多，不出 HRV。
    """
    rr = clean_rr(rr_s)
    result = {
        "hr_avg": None,
        "rr_used": int(len(rr)),
        "rr_rejected": int(len(rr_s) - len(rr)),
        "rr_coverage": round(float(rr.sum()) / minute_s, 2),
        "sdnn": None,
        "rmssd": None,
    }
    if len(rr):
        result["hr_avg"] = 60 / float(np.mean(rr))
    if len(rr) >= MIN_RR_FOR_HRV and result["rr_coverage"] >= MIN_RR_COVERAGE:
        rr_ms = rr * 1000
        result["sdnn"] = float(np.std(rr_ms, ddof=1))
        result["rmssd"] = float(np.sqrt(np.mean(np.diff(rr_ms) ** 2)))
    return result


class ECGRespMinute:
    """攒一分钟的包：原始 ECG 样本、板端 HR/呼吸率。"""

    def __init__(self):
        self.ecg = []
        self.board_hr = []
        self.board_rr = []
        self.packets = 0

    def add_packet(self, samples: np.ndarray, hr: int, rr: int) -> None:
        self.ecg.extend(samples[:, 0].tolist())
        self.board_hr.append(int(hr))
        self.board_rr.append(int(rr))
        self.packets += 1

    def build_record(self, now: float, session, metrics: dict | None, error: str | None, link: dict) -> dict:
        hr_avg, hr_min, hr_max = _stats(self.board_hr)
        rr_avg, rr_min, rr_max = _stats(self.board_rr)
        packet_s = ECGRespRuntime.samples_per_packet * ECGRespRuntime.dt_raw
        record = {
            "type": "minute",
            "ts": _iso(now),
            "session": session,
            "samples": len(self.ecg),
            "packets": self.packets,
            **link,
            "board_hr_avg": _round(hr_avg),
            "board_hr_min": hr_min,
            "board_hr_max": hr_max,
            # 板端 HR 为 0 的时长：导联脱落或板子还没锁定心搏
            "board_hr_zero_s": _round(sum(1 for hr in self.board_hr if hr == 0) * packet_s, 1),
            "board_resp_avg": _round(rr_avg),
            "board_resp_min": rr_min,
            "board_resp_max": rr_max,
        }
        if metrics is None:
            record.update({"hr_avg": None, "beats": None, "sdnn": None, "rmssd": None, "sq": "?", "sq_score": None})
            if error:
                record["sq_error"] = error
            return record

        # 覆盖率按这一段实际收到的时长算，丢包或首尾不满一分钟时也公平
        hrv = hrv_from_rr(metrics["rr_s"], len(self.ecg) * ECGRespRuntime.dt_raw)
        record.update(
            {
                "hr_avg": _round(hrv["hr_avg"]),
                "beats": metrics["beats"],
                "rr_rejected": hrv["rr_rejected"],
                "rr_coverage": hrv["rr_coverage"],
                "sdnn": _round(hrv["sdnn"]),
                "rmssd": _round(hrv["rmssd"]),
                "sq": grade_label(metrics["score"], metrics["bad_beat_ratio"]),
                "sq_score": _round(metrics["score"], 2),
                "bad_beat_ratio": _round(metrics["bad_beat_ratio"], 2),
            }
        )
        return record


class ECGRespContextRuntime(ECGRespRuntime):
    """原有运行时 + 把每个合法包同时交给当前这一分钟的累加器。"""

    def __init__(self):
        super().__init__()
        self.minute = ECGRespMinute()

    def read_packets_nb(self):
        packets = super().read_packets_nb()
        for _t_recv, _seq, samples, hr, rr in packets:
            self.minute.add_packet(samples, hr, rr)
        return packets

    def link_counters(self) -> dict:
        return {
            "seq_gaps": self.packet_loss_events,
            "bad_frames": self.bad_tail + self.bad_payload_len + self.bad_packet_type + self.bad_sample_count,
            "dropped_bytes": self.dropped_bytes,
        }


class ContextECGRespMonitor(ECGRespMonitor):
    """ECGRespMonitor + 每分钟数据记录。界面和 CSV 都是原来的。"""

    def __init__(self, directory=None):
        super().__init__()
        self.runtime = ECGRespContextRuntime()
        self.directory = directory if directory is not None else get_roast_context_dir()
        self.session = None
        self._minute_started = None
        self._last_link = self.runtime.link_counters()
        self._scoring = deque()
        self._pool = ThreadPoolExecutor(max_workers=1)
        # neurokit2 冷启动 import 要十来秒，提前在后台热身
        self._pool.submit(__import__, "neurokit2")

    def setup_ui(self):
        super().setup_ui()
        now = time.time()
        self.session = _iso(now)
        self._minute_started = now
        self._write({"type": "session_start", "ts": self.session, "session": self.session}, now)
        self.qt_app.aboutToQuit.connect(self._end_session)

    def _end_session(self):
        now = time.time()
        self._write({"type": "session_end", "ts": _iso(now), "session": self.session}, now)
        self._pool.shutdown(wait=False)

    def _write(self, record: dict, now: float) -> None:
        try:
            append_record(self.directory, record, now, prefix=FILE_PREFIX)
        except OSError as exc:
            self.runtime._maybe_debug("context_write", f"Context write failed: {exc}", 60.0)

    def update(self):
        super().update()
        self._emit_scored_minutes()
        now = time.time()
        if self._minute_started is None or now - self._minute_started < MINUTE_SECONDS:
            return
        self._minute_started = now

        link = self.runtime.link_counters()
        link_delta = {key: link[key] - self._last_link[key] for key in link}
        self._last_link = link
        minute = self.runtime.minute
        self.runtime.minute = ECGRespMinute()
        # nk2 评分和 HRV 要一两百毫秒，放后台线程算，免得界面卡顿
        future = self._pool.submit(score_minute, np.asarray(minute.ecg, dtype=float), self.runtime.fs)
        self._scoring.append((future, minute, now, link_delta))

    def _emit_scored_minutes(self):
        while self._scoring and self._scoring[0][0].done():
            future, minute, now, link_delta = self._scoring.popleft()
            try:
                metrics, error = future.result(), None
            except ImportError:
                metrics, error = None, "neurokit2 not installed"
            except Exception as exc:
                metrics, error = None, type(exc).__name__
            record = minute.build_record(now, self.session, metrics, error, link_delta)
            self._write(record, now)
            self.runtime._debug(
                f"{time.strftime('%H:%M', time.localtime(now))} HR {record['hr_avg']} (board {record['board_hr_avg']}) "
                f"SDNN {record['sdnn']} RMSSD {record['rmssd']} RESP {record['board_resp_avg']} "
                f"signal {record['sq']} {record['sq_score']}"
            )
