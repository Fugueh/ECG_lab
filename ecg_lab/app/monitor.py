from __future__ import annotations

import colorsys
import time
from collections import deque
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from dotenv import load_dotenv
from pyqtgraph.Qt import QtCore, QtWidgets
from PyQt5 import QtGui
from PyQt5.QtGui import QFont, QIcon
from scipy.signal import find_peaks

from ecg_lab.config import get_monitor_settings, get_repo_root


MONITOR_VARIANTS = ("250hz", "roast")


def launch_monitor(variant: str = "250hz") -> None:
    if variant == "250hz":
        Monitor250Hz().run()
        return
    if variant == "roast":
        RoastMonitor().run()
        return
    raise ValueError(f"Unknown monitor variant: {variant}")


class HUDText:
    def __init__(
        self,
        plot,
        text: str,
        pos: tuple[float, float],
        color=(255, 255, 255),
        anchor=(0, 0),
        font_family="Arial",
        font_size=12,
        bold=False,
    ):
        self.item = pg.TextItem(text=text, color=color, anchor=anchor)
        weight = QtGui.QFont.Bold if bold else QtGui.QFont.Normal
        self.item.setFont(QtGui.QFont(font_family, font_size, weight))
        self.item.setPos(*pos)
        plot.addItem(self.item)

    def set_text(self, text: str):
        self.item.setText(text)

    def set_color(self, color):
        self.item.setColor(color)


class MonitorRuntime:
    frame_header = b"\xAA\x55"
    frame_len = 17
    dt_raw = 0.004

    def __init__(self):
        load_dotenv(dotenv_path=get_repo_root() / ".env")
        self.settings = get_monitor_settings()
        now = time.time()
        self.timestamps = np.linspace(now - self.settings.time_window, now, self.settings.window)
        self.data = np.zeros(self.settings.window)
        self.lead_data = np.zeros(self.settings.window)
        self.rr_buf = deque(maxlen=int(5 * 60 * 4))
        self.beat_count = 0
        self._last_hrv_ui = 0.0
        self._prev_peak_abs_t = None
        self._rxbuf = bytearray()
        self.logfile = None
        self.serial = None

    def open_log(self) -> None:
        formatted_time = time.strftime("%Y-%m-%d_%H%M%S", time.localtime())
        logfile_path = Path.cwd() / f"raw_record_{formatted_time}.csv"
        self.logfile = logfile_path.open("w", encoding="utf-8", newline="")
        self.logfile.write("time,ecg,lead\n")

    def open_serial(self) -> None:
        import serial

        self.serial = serial.Serial(self.settings.serial_port, self.settings.baud, timeout=0)

    def close(self) -> None:
        if self.logfile is not None:
            self.logfile.close()
            self.logfile = None
        if self.serial is not None:
            self.serial.close()
            self.serial = None

    def read_frames_nb(self):
        if self.serial is None:
            return []

        n = self.serial.in_waiting
        if n:
            self._rxbuf += self.serial.read(n)

        frames = []
        while True:
            index = self._rxbuf.find(self.frame_header)
            if index < 0:
                if len(self._rxbuf) > 1:
                    self._rxbuf = self._rxbuf[-1:]
                break

            if index > 0:
                del self._rxbuf[:index]

            if len(self._rxbuf) < self.frame_len:
                break

            frame = bytes(self._rxbuf[: self.frame_len])
            del self._rxbuf[: self.frame_len]

            import struct

            t0_us, lead_off, p0, p1, p2, p3, p4 = struct.unpack("<IB5H", frame[2:])
            frames.append((time.time(), t0_us, lead_off, (p0, p1, p2, p3, p4)))

        return frames

    def push_sample(self, timestamp, ecg, lead_off):
        self.timestamps[:-1] = self.timestamps[1:]
        self.timestamps[-1] = timestamp
        self.data[:-1] = self.data[1:]
        self.data[-1] = np.nan if lead_off else ecg
        self.lead_data[:-1] = self.lead_data[1:]
        self.lead_data[-1] = lead_off

    def maybe_append_rr(self, last_peak_t, hr):
        rr_in_arr = False
        if self._prev_peak_abs_t is None:
            self._prev_peak_abs_t = last_peak_t
            return rr_in_arr

        last_rr = last_peak_t - self._prev_peak_abs_t
        if 0.3 <= last_rr <= 2.0:
            if len(self.rr_buf) >= 1:
                prev_rr = float(self.rr_buf[-1])
                if (0.5 * prev_rr) <= last_rr <= (1.8 * prev_rr):
                    self.rr_buf.append(last_rr)
                    rr_in_arr = True
            else:
                self.rr_buf.append(last_rr)
                rr_in_arr = True

            self.beat_count += 1
            if not rr_in_arr:
                print(
                    "Beat: %d," % self.beat_count,
                    f"RR: {last_rr:.2f} s,",
                    f"HR: {hr:.0f},",
                    "In Array:",
                    rr_in_arr,
                )

        self._prev_peak_abs_t = last_peak_t
        return rr_in_arr

    @staticmethod
    def rr_hr_calc(timestamps, peaks):
        rr = np.diff(timestamps[peaks])
        hr = 60 / rr[-1]
        return rr, hr

    @staticmethod
    def calc_sdnn_rmssd(rr_array):
        if len(rr_array) < 3:
            return None, None
        rr_ms = rr_array * 1000.0
        sdnn = np.std(rr_ms, ddof=1)
        rmssd = np.sqrt(np.mean(np.diff(rr_ms) ** 2))
        return sdnn, rmssd

    def update_hrv(self):
        rr_arr = np.array(self.rr_buf, dtype=float)
        if len(rr_arr) < 30:
            return None, None

        rr_win = rr_arr[-300:]
        med = np.median(rr_win)
        mad = np.median(np.abs(rr_win - med))
        if mad > 1e-12:
            rr_win = rr_win[np.abs(rr_win - med) <= 3.5 * 1.4826 * mad]

        rr_win = rr_win[(rr_win >= 0.3) & (rr_win <= 2.0)]
        if len(rr_win) < 30:
            return None, None

        return self.calc_sdnn_rmssd(rr_win)

    @staticmethod
    def frame_to_display(samples):
        return float(np.median(samples))


class Monitor250Hz:
    def __init__(self):
        self.runtime = MonitorRuntime()
        self.qt_app = None
        self.window = None
        self.plot = None
        self.timer = None
        self.curve_ecg = None
        self.rr_text = None
        self.sdnn_text = None
        self.rmssd_text = None
        self.hr_text = None
        self.ecg_text = None
        self.lead_text = None
        self.ymax = 860

    def setup_ui(self):
        self.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        self.window = pg.GraphicsLayoutWidget(show=True, title="Captain ECG Monitor")
        self.window.setBackground("k")
        self.plot = self.window.addPlot(title="ECG Signal (Lead I)")
        self.curve_ecg = self.plot.plot(pen=pg.mkPen((0, 255, 0), width=1.2))

        self.plot.setXRange(-self.runtime.settings.time_window, 0)
        self.plot.setYRange(150, self.ymax)
        self.plot.setLabel("left", "Amplitude")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setLabel("bottom", "Time (s)", **{"color": "#AAA", "font-size": "10pt"})

        time_window = self.runtime.settings.time_window
        self.rr_text = HUDText(self.plot, "RR Interval: -- s", (-time_window + 7, self.ymax - 200), anchor=(1, 0), font_size=20)
        self.sdnn_text = HUDText(self.plot, "SDNN: -- ms", (-time_window + 7, self.ymax - 230), anchor=(1, 0), font_size=20)
        self.rmssd_text = HUDText(self.plot, "RMSSD: -- ms", (-time_window + 7, self.ymax - 260), anchor=(1, 0), font_size=20)
        self.hr_text = HUDText(self.plot, "--", (0, self.ymax), color=(0, 255, 0), anchor=(1, 0), font_size=120, bold=True)
        self.ecg_text = HUDText(self.plot, "ECG\nbpm", (-1.4, self.ymax - 20), color=(0, 255, 0), anchor=(1, 0), font_size=20)
        self.lead_text = HUDText(self.plot, "NORMAL", (-1.4, self.ymax - 90), color=(0, 255, 0), anchor=(1, 0), font_size=20)

    @staticmethod
    def text_color(hr):
        if hr < 50:
            return (0, 180, 255)
        if hr < 100:
            return (0, 255, 0)
        if hr < 120:
            return (255, 255, 0)
        return (248, 47, 0)

    def update_plot(self):
        if self.curve_ecg is None:
            return
        t_rel = self.runtime.timestamps - self.runtime.timestamps[-1]
        self.curve_ecg.setData(t_rel, self.runtime.data)

    def update_hr_display(self):
        now = time.time()
        peaks, _ = find_peaks(self.runtime.data, height=350, distance=20)
        if len(peaks) < 2:
            return

        lead_off = self.runtime.lead_data[-1] == 1
        if lead_off:
            self.lead_text.set_text("LEAD OFF")
            self.lead_text.set_color((255, 0, 0))
            self.hr_text.set_text("--")
            self.rr_text.set_text("RR Interval: --")
            self.hr_text.set_color((255, 0, 0))
            self.ecg_text.set_color((255, 0, 0))
            return

        self.lead_text.set_text("NORMAL")
        self.lead_text.set_color((0, 255, 0))

        last_peak_t = float(self.runtime.timestamps[peaks[-1]])
        rr, hr = self.runtime.rr_hr_calc(self.runtime.timestamps, peaks)
        color = self.text_color(hr)
        self.rr_text.set_text(f"RR Interval: {rr[-1]:.2f} s")
        self.hr_text.set_text(f"{hr:.0f}")
        self.hr_text.set_color(color)
        self.ecg_text.set_color(color)

        if (self.runtime._prev_peak_abs_t is None) or (last_peak_t > self.runtime._prev_peak_abs_t + 1e-6):
            self.runtime.maybe_append_rr(last_peak_t, hr)

        if now - self.runtime._last_hrv_ui >= 10.0:
            self.runtime._last_hrv_ui = now
            sdnn, rmssd = self.runtime.update_hrv()
            if sdnn is not None:
                self.sdnn_text.set_text(f"SDNN: {sdnn:.0f} ms")
                self.rmssd_text.set_text(f"RMSSD: {rmssd:.0f} ms")

    def update(self):
        frames = self.runtime.read_frames_nb()
        if not frames:
            return

        for t_recv, _t0_us, lead_off, samples in frames:
            t0 = t_recv - 5 * self.runtime.dt_raw
            for i, ecg in enumerate(samples):
                ts = t0 + i * self.runtime.dt_raw
                self.runtime.logfile.write(f"{ts},{int(ecg)},{int(lead_off)}\n")

            self.runtime.push_sample(t_recv, self.runtime.frame_to_display(samples), int(lead_off))

        self.update_plot()
        self.update_hr_display()
        self.runtime.logfile.flush()

    def run(self):
        self.runtime.open_log()
        self.runtime.open_serial()
        self.setup_ui()
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(4)
        self.qt_app.aboutToQuit.connect(self.runtime.close)
        self.qt_app.exec_()


class RoastMonitor:
    def __init__(self):
        self.runtime = MonitorRuntime()
        self.qt_app = None
        self.window = None
        self.plot = None
        self.timer = None
        self.curve_ecg = None
        self.roast_text = None
        self.rr_text = None
        self.sdnn_text = None
        self.rmssd_text = None
        self.hr_text = None
        self.ecg_text = None
        self.lead_text = None
        self.ymax = 860
        self.time_window = 10

    def setup_ui(self):
        self.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        icon_path = get_repo_root() / "app" / "monitor" / "roast.ico"
        self.qt_app.setWindowIcon(QIcon(str(icon_path)))
        self.window = pg.GraphicsLayoutWidget(title="Captain ECG Monitor - Mini")
        self.window.setWindowFlags(self.window.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        self.window.resize(600, 250)
        self.window.show()
        self.window.setBackground("k")

        self.plot = self.window.addPlot()
        self.curve_ecg = self.plot.plot(pen=pg.mkPen((0, 255, 0), width=1.2))
        self.plot.setXRange(-self.time_window, 0)
        self.plot.setYRange(150, self.ymax)
        self.plot.showGrid(x=True, y=True, alpha=0.3)

        yaxis = self.plot.getAxis("left")
        yaxis.setStyle(showValues=False)
        yaxis.setTicks([])

        xaxis = self.plot.getAxis("bottom")
        xaxis.setStyle(tickFont=QFont("Arial", 10))
        xaxis.setLabel(text="Time", units="s", **{"color": "#AAA", "font-size": "10pt", "font-family": "Arial"})

        distance = 85
        yloc = self.ymax + 30
        self.roast_text = HUDText(self.plot, "[--] Are you ok?", (-self.time_window, yloc), color=(0, 255, 0), anchor=(0, 0), font_size=10)
        self.rr_text = HUDText(self.plot, "RR Interval: -- s", (-self.time_window, yloc - distance), anchor=(0, 0), font_size=10)
        self.sdnn_text = HUDText(self.plot, "SDNN: -- ms", (-self.time_window, yloc - 2 * distance), anchor=(0, 0), font_size=10)
        self.rmssd_text = HUDText(self.plot, "RMSSD: -- ms", (-self.time_window, yloc - 3 * distance), anchor=(0, 0), font_size=10)
        self.hr_text = HUDText(self.plot, "--", (0, yloc + 50), color=(0, 255, 0), anchor=(1, 0), font_size=50, bold=True)
        self.ecg_text = HUDText(self.plot, "ECG\nbpm", (-3, yloc), color=(0, 255, 0), anchor=(1, 0), font_size=10)
        self.lead_text = HUDText(self.plot, "NORMAL", (-3, yloc - 200), color=(0, 255, 0), anchor=(1, 0), font_size=10)

    @staticmethod
    def hr_roast(hr):
        if hr < 60:
            return "Too calm"
        if hr < 70:
            return "Still chilling"
        if hr < 80:
            return "Steady"
        if hr < 90:
            return "Warming up"
        if hr < 100:
            return "A little stressed"
        if hr < 120:
            return "Pretty anxious"
        return "That is intense"

    @staticmethod
    def hr_roast_color(hr):
        hr_min, hr_max = 60, 120
        ratio = (hr - hr_min) / (hr_max - hr_min)
        ratio = max(0, min(1, ratio))
        hue = (120 * (1 - ratio)) / 360
        r, g, b = colorsys.hsv_to_rgb(hue, 1, 1)
        if hr >= 60:
            return int(r * 255), int(g * 255), int(b * 255)
        return (0, 180, 255)

    def set_text(self, rr, hr, lead_off, window_mean_hr):
        if lead_off:
            self.lead_text.set_text("LEAD OFF")
            self.lead_text.set_color((255, 0, 0))
            self.hr_text.set_text("-?-")
            self.rr_text.set_text("RR Interval: --")
            self.roast_text.set_text("[-?-] Lead off")
            self.sdnn_text.set_text("SDNN: -- ms")
            self.rmssd_text.set_text("RMSSD: -- ms")
            self.hr_text.set_color((255, 0, 0))
            self.ecg_text.set_color((255, 0, 0))
            self.roast_text.set_color((255, 0, 0))
            return

        self.lead_text.set_text("NORMAL")
        self.lead_text.set_color((0, 255, 0))
        roast_color = self.hr_roast_color(window_mean_hr)
        self.hr_text.set_text(f"{hr:.0f}")
        self.rr_text.set_text(f"RR Interval: {rr[-1]:.2f} s")
        self.roast_text.set_text(f"[{window_mean_hr:0=.0f}] {self.hr_roast(window_mean_hr)}")
        self.hr_text.set_color(roast_color)
        self.ecg_text.set_color(roast_color)
        self.roast_text.set_color(roast_color)

    def update_plot(self):
        if self.curve_ecg is None:
            return
        t_rel = self.runtime.timestamps - self.runtime.timestamps[-1]
        self.curve_ecg.setData(t_rel, self.runtime.data)

    def update_hr_display(self):
        now = time.time()
        peaks, _ = find_peaks(self.runtime.data, height=350, distance=20)
        if len(peaks) < 2:
            return

        lead_off = self.runtime.lead_data[-1] == 1
        rr, hr = self.runtime.rr_hr_calc(self.runtime.timestamps, peaks)
        window_mean_hr = 60 / np.mean(rr)
        self.set_text(rr, hr, lead_off, window_mean_hr)
        if lead_off:
            return

        last_peak_t = float(self.runtime.timestamps[peaks[-1]])
        if (self.runtime._prev_peak_abs_t is None) or (last_peak_t > self.runtime._prev_peak_abs_t + 1e-6):
            self.runtime.maybe_append_rr(last_peak_t, hr)

        if now - self.runtime._last_hrv_ui < 10.0:
            return

        self.runtime._last_hrv_ui = now
        sdnn, rmssd = self.runtime.update_hrv()
        if sdnn is not None:
            self.sdnn_text.set_text(f"SDNN: {sdnn:.0f} ms")
            self.rmssd_text.set_text(f"RMSSD: {rmssd:.0f} ms")

    def update(self):
        frames = self.runtime.read_frames_nb()
        if not frames:
            return

        for t_recv, _t0_us, lead_off, samples in frames:
            t0 = t_recv - 5 * self.runtime.dt_raw
            for i, ecg in enumerate(samples):
                ts = t0 + i * self.runtime.dt_raw
                self.runtime.logfile.write(f"{ts},{int(ecg)},{int(lead_off)}\n")

            self.runtime.push_sample(t_recv, self.runtime.frame_to_display(samples), int(lead_off))

        self.update_plot()
        self.update_hr_display()
        self.runtime.logfile.flush()

    def run(self):
        self.runtime.open_log()
        self.runtime.open_serial()
        self.setup_ui()
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(4)
        self.qt_app.aboutToQuit.connect(self.runtime.close)
        self.qt_app.exec_()
