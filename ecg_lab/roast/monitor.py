from __future__ import annotations

import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from pyqtgraph.Qt import QtWidgets

from ecg_lab.app.monitor import MonitorRuntime, RoastMonitor

from .context import RoastContextRecorder
from .event_panel import EventPanel, set_always_on_top
from .phrases import hrv_roast
from .signal_quality import describe_quality, score_minute


LEAD_OFF_COLOR = (255, 0, 0)


def _hex_color(rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def launch_roast_monitor(save_csv: bool = False) -> None:
    ContextRoastMonitor(save_csv=save_csv).run()


class RoastRuntime(MonitorRuntime):
    """在原有运行时之上多记三样东西：这一分钟的原始样本、心拍接受/拒收数、过滤后的近期心率。"""

    rr_resync_after = 5
    verdict_beats = 30

    def __init__(self):
        super().__init__()
        self.raw_buf = deque(maxlen=int(60 / self.dt_raw))
        self.rr_accepted = 0
        self.rr_accepted_sum = 0.0
        self.rr_rejected = 0
        self._rr_reject_streak = 0

    def read_frames_nb(self):
        frames = super().read_frames_nb()
        for _t_recv, _t0_us, _lead_off, samples in frames:
            self.raw_buf.extend(samples)
        return frames

    def maybe_append_rr(self, last_peak_t, hr):
        if self._prev_peak_abs_t is None:
            return super().maybe_append_rr(last_peak_t, hr)

        last_rr = last_peak_t - self._prev_peak_abs_t
        in_range = 0.3 <= last_rr <= 2.0
        if in_range and self._rr_reject_streak >= self.rr_resync_after:
            # 连续拒收说明参考 RR 本身是坏的，放行一拍重新对齐，否则评语会一直卡在旧值上
            self.rr_buf.append(last_rr)
            self.beat_count += 1
            self._prev_peak_abs_t = last_peak_t
            accepted = True
        else:
            accepted = super().maybe_append_rr(last_peak_t, hr)

        if accepted:
            self.rr_accepted += 1
            self.rr_accepted_sum += last_rr
            self._rr_reject_streak = 0
        else:
            self.rr_rejected += 1
            if in_range:
                self._rr_reject_streak += 1
        return accepted

    def recent_mean_hr(self):
        """最近若干个通过校验的 RR 的平均心率，不受假峰影响"""
        if not self.rr_buf:
            return None
        recent = list(self.rr_buf)[-self.verdict_beats :]
        return 60 / float(np.mean(recent))

    def drain_beat_stats(self):
        # 区间平均心率 = 接受的拍数 / 这些 RR 的总时长
        mean_hr = 60 * self.rr_accepted / self.rr_accepted_sum if self.rr_accepted_sum > 0 else None
        stats = (self.rr_accepted, self.rr_rejected, mean_hr)
        self.rr_accepted = 0
        self.rr_accepted_sum = 0.0
        self.rr_rejected = 0
        return stats


class ContextRoastMonitor(RoastMonitor):
    """RoastMonitor + 吐槽上下文采集 + 信号质量评分 + 事件面板。

    界面和原有的状态行都由 RoastMonitor 负责，这里只追加内容。
    """

    def __init__(self, save_csv: bool = False):
        super().__init__()
        self.runtime = RoastRuntime()
        self.save_csv = save_csv
        self.csv_path = None
        self.event_panel = None
        self.container = None
        self.roast_context = RoastContextRecorder()
        self._scoring_minutes = deque()
        self._quality_pool = ThreadPoolExecutor(max_workers=1)
        # neurokit2 冷启动 import 要十来秒，提前在后台热身
        self._quality_pool.submit(__import__, "neurokit2")

    def setup_ui(self):
        super().setup_ui()
        self.csv_path = Path(self.runtime.logfile.name)
        self.roast_context.start_session(time.time())
        self.qt_app.aboutToQuit.connect(lambda: self.roast_context.end_session(time.time()))
        self.qt_app.aboutToQuit.connect(lambda: self._quality_pool.shutdown(wait=False))

        # 把原有的波形窗口和事件面板装进同一个固定大小的窗口，方便一起拖动
        self.event_panel = EventPanel(
            context_provider=self._event_context,
            hr_color=lambda hr: _hex_color(self.hr_roast_color(hr)),
        )
        self.container = QtWidgets.QWidget()
        self.container.setWindowTitle(self.window.windowTitle())
        set_always_on_top(self.container, True)
        self.event_panel.pin_toggled.connect(lambda on: set_always_on_top(self.container, on))
        self.window.setFixedSize(self.event_panel.width(), self.window.height())
        layout = QtWidgets.QVBoxLayout(self.container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.window)
        layout.addWidget(self.event_panel)
        self._refit_container()
        self.event_panel.resized.connect(self._refit_container)
        self.container.show()

    def _refit_container(self):
        self.container.layout().activate()
        self.container.setFixedSize(self.container.sizeHint())

    def run(self):
        super().run()
        # 窗口正常关闭后才会走到这里；原始 CSV 默认不留，--save-csv 才保留
        if self.save_csv:
            print(f"Raw CSV kept: {self.csv_path}", flush=True)
        else:
            self.csv_path.unlink(missing_ok=True)
            print(f"Raw CSV deleted: {self.csv_path.name} (use --save-csv to keep it)", flush=True)

    def window_mean_hr(self, rr):
        # 评语只看通过校验的 RR，窗口里的假峰不参与
        recent = self.runtime.recent_mean_hr()
        return recent if recent is not None else super().window_mean_hr(rr)

    def _displayed_mean_hr(self):
        return None if getattr(self.hr_text, "text", "--") in {"--", "-?-"} else self.current_mean_hr

    def _event_context(self) -> dict:
        context = {"session": self.roast_context.session}
        mean_hr = self._displayed_mean_hr()
        if mean_hr is not None:
            context["hr"] = int(round(mean_hr))
            context["roast"] = self.current_roast_text
            # 和界面上心率数字此刻的颜色一致，事件面板用它给时间戳上色
            context["color"] = _hex_color(self.hr_roast_color(mean_hr))
        elif self.runtime.lead_data[-1] == 1:
            context["color"] = _hex_color(LEAD_OFF_COLOR)
        return context

    def maybe_print_status(self):
        now = time.time()
        lead_off = self.runtime.lead_data[-1] == 1
        self.roast_context.observe(
            now,
            None if lead_off else self.current_mean_hr,
            self.current_roast_text,
            lead_off,
        )
        self._emit_scored_minutes()

        last_print = self._last_status_print
        super().maybe_print_status()
        if self._last_status_print == last_print:
            return

        # 原有的状态行刚打印完，这里把同一时刻的补充信息攒起来，等 nk2 评分算完再输出
        sdnn, rmssd = self.runtime.update_hrv()
        beats_ok, beats_rejected, minute_mean_hr = self.runtime.drain_beat_stats()
        minute = {
            "now": self._last_status_print,
            "hr": self._displayed_mean_hr(),
            "hr_avg": minute_mean_hr,
            "sdnn": sdnn,
            "rmssd": rmssd,
            "roast": self._roast_phrase(getattr(self.roast_text, "text", self.current_roast_text)),
            "hrv_roast": hrv_roast(rmssd),
            "beats_ok": beats_ok,
            "beats_rejected": beats_rejected,
            "lead_off_s": self.roast_context.lead_off_seconds,
        }
        # nk2 评分要一两百毫秒，放后台线程算，免得界面卡顿
        raw = np.array(self.runtime.raw_buf, dtype=float)
        self.runtime.raw_buf.clear()
        future = self._quality_pool.submit(score_minute, raw, int(round(1 / self.runtime.dt_raw)))
        self._scoring_minutes.append((future, minute))

    def _emit_scored_minutes(self):
        while self._scoring_minutes and self._scoring_minutes[0][0].done():
            future, minute = self._scoring_minutes.popleft()
            try:
                metrics, error = future.result(), None
            except ImportError:
                metrics, error = None, "没装 neurokit2"
            except Exception as exc:
                metrics, error = None, f"nk2 评分失败（{type(exc).__name__}）"
            quality = describe_quality(
                metrics, minute["beats_ok"], minute["beats_rejected"], minute["lead_off_s"], error
            )

            timestamp = time.strftime("%H:%M:%S", time.localtime(minute["now"]))
            print(
                f"[{timestamp}] 分钟均 {self._metric_text(minute['hr_avg'])} bpm｜{minute['hrv_roast']}\n"
                f"[{timestamp}] {quality['note']}",
                flush=True,
            )
            self.roast_context.flush_minute(
                minute["now"],
                hr=minute["hr"],
                hr_avg=minute["hr_avg"],
                sdnn=minute["sdnn"],
                rmssd=minute["rmssd"],
                roast=minute["roast"],
                beats_ok=minute["beats_ok"],
                beats_rejected=minute["beats_rejected"],
                hrv_roast=minute["hrv_roast"],
                sq=quality["label"],
                sq_score=quality["score"],
                sq_note=quality["note"],
            )
