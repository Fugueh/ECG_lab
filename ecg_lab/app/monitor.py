from __future__ import annotations

import colorsys
import os
import time
from collections import deque
from dataclasses import replace
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from dotenv import load_dotenv
from pyqtgraph.Qt import QtCore, QtWidgets
from PyQt5 import QtGui
from PyQt5.QtGui import QFont, QIcon
from scipy.signal import find_peaks

from ecg_lab.config import get_monitor_settings, get_repo_root


MONITOR_VARIANTS = ("250hz", "roast", "ecgresp")


def launch_monitor(variant: str = "250hz") -> None:
    if variant == "250hz":
        Monitor250Hz().run()
        return
    if variant == "roast":
        RoastMonitor().run()
        return
    if variant == "ecgresp":
        ECGRespMonitor().run()
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


class BaseMonitor:
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
        raise NotImplementedError

    def apply_display_values(self, rr, hr, lead_off):
        raise NotImplementedError

    def update_plot(self):
        if self.curve_ecg is None:
            return
        t_rel = self.runtime.timestamps - self.runtime.timestamps[-1]
        self.curve_ecg.setData(t_rel, self.runtime.data)

    def update_hrv_text(self):
        sdnn, rmssd = self.runtime.update_hrv()
        if sdnn is not None:
            self.sdnn_text.set_text(f"SDNN: {sdnn:.0f} ms")
            self.rmssd_text.set_text(f"RMSSD: {rmssd:.0f} ms")

    def update_hr_display(self):
        now = time.time()
        peaks, _ = find_peaks(self.runtime.data, height=350, distance=20)
        if len(peaks) < 2:
            return

        lead_off = self.runtime.lead_data[-1] == 1
        rr, hr = self.runtime.rr_hr_calc(self.runtime.timestamps, peaks)
        self.apply_display_values(rr, hr, lead_off)
        if lead_off:
            return

        last_peak_t = float(self.runtime.timestamps[peaks[-1]])
        if (self.runtime._prev_peak_abs_t is None) or (last_peak_t > self.runtime._prev_peak_abs_t + 1e-6):
            self.runtime.maybe_append_rr(last_peak_t, hr)

        if now - self.runtime._last_hrv_ui < 10.0:
            return

        self.runtime._last_hrv_ui = now
        self.update_hrv_text()

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


class Monitor250Hz(BaseMonitor):
    def __init__(self):
        super().__init__()

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

    def apply_display_values(self, rr, hr, lead_off):
        if lead_off:
            self.lead_text.set_text("LEAD OFF")
            self.lead_text.set_color((255, 0, 0))
            self.hr_text.set_text("--")
            self.rr_text.set_text("RR Interval: --")
            self.sdnn_text.set_text("SDNN: -- ms")
            self.rmssd_text.set_text("RMSSD: -- ms")
            self.hr_text.set_color((255, 0, 0))
            self.ecg_text.set_color((255, 0, 0))
            return

        self.lead_text.set_text("NORMAL")
        self.lead_text.set_color((0, 255, 0))

        color = self.text_color(hr)
        self.rr_text.set_text(f"RR Interval: {rr[-1]:.2f} s")
        self.hr_text.set_text(f"{hr:.0f}")
        self.hr_text.set_color(color)
        self.ecg_text.set_color(color)


class RoastMonitor(BaseMonitor):
    def __init__(self):
        super().__init__()
        self.roast_text = None
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
            return "上班时间不许睡觉！"
        elif hr < 70:
            return "你在摸鱼？"
        elif hr < 80:
            return "稳如老狗"
        elif hr < 90:
            return "急了？"
        elif hr < 100:
            return "咋还急眼了呢？"
        elif hr < 120:
            return "你已急哭"
        else:
            return "你没毛病吧？"

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

    def apply_display_values(self, rr, hr, lead_off):
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
        window_mean_hr = 60 / np.mean(rr)
        roast_color = self.hr_roast_color(window_mean_hr)
        self.hr_text.set_text(f"{hr:.0f}")
        self.rr_text.set_text(f"RR Interval: {rr[-1]:.2f} s")
        self.roast_text.set_text(f"[{window_mean_hr:0=.0f}] {self.hr_roast(window_mean_hr)}")
        self.hr_text.set_color(roast_color)
        self.ecg_text.set_color(roast_color)
        self.roast_text.set_color(roast_color)


class ECGRespRuntime:
    frame_header = b"\xA5\x5A"
    frame_tail = b"\x55\xAA"
    frame_len = 35
    payload_len = 30
    packet_type = 0x03
    samples_per_packet = 5
    dt_raw = 0.004
    fs = 250

    def __init__(self):
        load_dotenv(dotenv_path=get_repo_root() / ".env")
        self.settings = self._get_ecgresp_settings()
        now = time.time()
        self.window = self.fs * self.settings.time_window
        self.timestamps = np.linspace(now - self.settings.time_window, now, self.window)
        self.ecg = np.zeros(self.window)
        self.resp = np.zeros(self.window)
        self.packet_seq = -1
        self.last_hr = 0
        self.last_rr = 0
        self.last_packet_at = 0.0
        self._rxbuf = bytearray()
        self.logfile = None
        self.serial = None
        self.total_packets = 0
        self.total_samples = 0
        self.dropped_bytes = 0
        self.bad_tail = 0
        self.bad_payload_len = 0
        self.bad_packet_type = 0
        self.bad_sample_count = 0
        self.packet_loss_events = 0
        self.last_packet_debug_at = 0.0
        self.last_no_packet_warning_at = 0.0
        self.last_sync_debug_at = 0.0

    def _get_ecgresp_settings(self):
        settings = get_monitor_settings()
        serial_port = os.getenv("ECG_LAB_SERIAL_PORT", settings.serial_port or "COM10")
        if isinstance(serial_port, int):
            serial_port = f"COM{serial_port}"
        elif isinstance(serial_port, str) and serial_port.isdigit():
            serial_port = f"COM{serial_port}"
        baud = 57600
        time_window = int(os.getenv("ECG_LAB_TIME_WINDOW", str(settings.time_window)))
        return replace(settings, fs=self.fs, serial_port=serial_port, baud=baud, time_window=time_window)

    def _debug(self, message: str) -> None:
        print(f"[ECGRESP] {message}")

    def _maybe_debug(self, key: str, message: str, interval_s: float = 1.0) -> None:
        now = time.time()
        attr = f"_debug_last_{key}"
        last_at = getattr(self, attr, 0.0)
        if now - last_at >= interval_s:
            self._debug(message)
            setattr(self, attr, now)

    def open_log(self) -> None:
        formatted_time = time.strftime("%Y-%m-%d_%H%M%S", time.localtime())
        logfile_path = Path.cwd() / f"raw_record_ecgresp_{formatted_time}.csv"
        self.logfile = logfile_path.open("w", encoding="utf-8", newline="")
        self.logfile.write("time,packet_seq,ecg,resp,hr,rr\n")
        self._debug(f"Logging ECG/RESP CSV to {logfile_path}")

    def open_serial(self) -> None:
        import serial

        self.serial = serial.Serial()
        self.serial.port = self.settings.serial_port
        self.serial.baudrate = self.settings.baud
        self.serial.timeout = 0
        self.serial.rtscts = False
        self.serial.dsrdtr = False
        try:
            self.serial.dtr = False
            self.serial.rts = False
        except Exception:
            pass
        self.serial.open()
        self._debug(
            f"Opened serial {self.settings.serial_port}@{self.settings.baud} "
            f"(protocol: {self.fs} SPS, {self.samples_per_packet} samples/packet, frame_len={self.frame_len})"
        )

    def close(self) -> None:
        if self.logfile is not None:
            self.logfile.close()
            self.logfile = None
        if self.serial is not None:
            self.serial.close()
            self.serial = None

    @staticmethod
    def decode_int24_samples(samples_blob: bytes) -> np.ndarray:
        samples = np.empty((ECGRespRuntime.samples_per_packet, 2), dtype=np.int32)
        offset = 0
        for i in range(ECGRespRuntime.samples_per_packet):
            ecg_raw = samples_blob[offset] | (samples_blob[offset + 1] << 8) | (samples_blob[offset + 2] << 16)
            if ecg_raw & 0x800000:
                ecg_raw -= 1 << 24
            offset += 3

            resp_raw = samples_blob[offset] | (samples_blob[offset + 1] << 8)
            if resp_raw & 0x8000:
                resp_raw -= 1 << 16
            offset += 2

            samples[i, 0] = ecg_raw
            samples[i, 1] = resp_raw
        return samples

    def read_packets_nb(self):
        if self.serial is None:
            return []

        n = self.serial.in_waiting
        if n:
            self._rxbuf += self.serial.read(n)

        packets = []
        while True:
            index = self._rxbuf.find(self.frame_header)
            if index < 0:
                if len(self._rxbuf) > 1:
                    self.dropped_bytes += len(self._rxbuf) - 1
                    self._rxbuf = self._rxbuf[-1:]
                break

            if index > 0:
                self.dropped_bytes += index
                self._maybe_debug("sync_drop", f"Dropped {index} non-frame byte(s) before header while resyncing", 2.0)
                del self._rxbuf[:index]

            if len(self._rxbuf) < self.frame_len:
                break

            frame = bytes(self._rxbuf[: self.frame_len])
            if frame[-2:] != self.frame_tail:
                self.bad_tail += 1
                self._maybe_debug("bad_tail", "Discarding candidate frame: bad tail", 1.0)
                del self._rxbuf[0]
                continue

            payload_len = frame[2]
            packet_type = frame[3]
            packet_seq = frame[4]
            sample_count = frame[5]
            if payload_len != self.payload_len:
                self.bad_payload_len += 1
                self._maybe_debug("bad_payload", f"Discarding candidate frame: bad payload_len={payload_len}", 1.0)
                del self._rxbuf[0]
                continue
            if packet_type != self.packet_type:
                self.bad_packet_type += 1
                self._maybe_debug("bad_type", f"Discarding candidate frame: bad packet_type={packet_type}", 1.0)
                del self._rxbuf[0]
                continue
            if sample_count != self.samples_per_packet:
                self.bad_sample_count += 1
                self._maybe_debug("bad_count", f"Discarding candidate frame: bad sample_count={sample_count}", 1.0)
                del self._rxbuf[0]
                continue

            samples_blob = frame[6:31]
            samples = self.decode_int24_samples(samples_blob)
            hr = frame[31]
            rr = frame[32]
            packets.append((time.time(), packet_seq, samples, hr, rr))
            del self._rxbuf[: self.frame_len]

        return packets

    def push_sample(self, timestamp: float, ecg_sample: float, resp_sample: float) -> None:
        self.timestamps[:-1] = self.timestamps[1:]
        self.timestamps[-1] = timestamp
        self.ecg[:-1] = self.ecg[1:]
        self.ecg[-1] = ecg_sample
        self.resp[:-1] = self.resp[1:]
        self.resp[-1] = resp_sample

    @staticmethod
    def ecg_frame_to_display(samples: np.ndarray) -> float:
        return float(np.median(samples[:, 0]))

    @staticmethod
    def resp_frame_to_display(samples: np.ndarray) -> float:
        return float(np.mean(samples[:, 1]))

class ECGRespMonitor:
    ECG_Y_RANGE = (-200000, 200000)
    HUD_LEFT_PAD_RATIO = 0.012
    HUD_RIGHT_PAD_RATIO = 0.75
    HUD_TOP_PAD_RATIO = 0.04
    HUD_LINE_GAP_RATIO = 0.07

    def __init__(self):
        self.runtime = ECGRespRuntime()
        self.qt_app = None
        self.window = None
        self.plot_ecg = None
        self.plot_resp = None
        self.curve_ecg = None
        self.curve_resp = None
        self.timer = None
        self.status_text = None
        self.ecg_text = None
        self.hr_text = None
        self.rr_text = None
        self.info_text = None
        self.last_packet_text = None

    def setup_ui(self):
        self.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        self.window = pg.GraphicsLayoutWidget(show=True, title="Captain ECG/RESP Monitor")
        self.window.resize(1200, 700)
        self.window.setBackground("k")

        self.plot_ecg = self.window.addPlot(title="ECG")
        self.curve_ecg = self.plot_ecg.plot(pen=pg.mkPen((0, 255, 0), width=1.2))
        self.plot_ecg.setXRange(-self.runtime.settings.time_window, 0)
        self.plot_ecg.setYRange(*self.ECG_Y_RANGE, padding=0)
        self.plot_ecg.showGrid(x=True, y=True, alpha=0.3)
        self.plot_ecg.setLabel("left", "ECG")
        self.plot_ecg.setLabel("bottom", "Time (s)", **{"color": "#AAA", "font-size": "10pt"})

        self.status_text = HUDText(
            self.plot_ecg,
            f"ADS1292R 250 SPS | 5 samples/packet | 50 Hz UART | {self.runtime.settings.serial_port}@{self.runtime.settings.baud}",
            (0, 0),
            color=(180, 180, 180),
            anchor=(0, 0),
            font_size=11,
        )
        self.ecg_text = HUDText(self.plot_ecg, "ECG\nbpm", (0, 0), color=(0, 255, 0), anchor=(0, 0), font_size=20)
        self.hr_text = HUDText(self.plot_ecg, "--", (0, 0), color=(0, 255, 0), anchor=(0, 0), font_size=120, bold=True)
        #self.rr_text = HUDText(self.plot_ecg, "RR: -- rpm", (-2.2, 0), color=(0, 220, 255), anchor=(1, 0), font_size=18, bold=True)
        self.last_packet_text = HUDText(
            self.plot_ecg,
            "Last packet: --",
            (0, 0),
            color=(180, 180, 180),
            anchor=(0, 0),
            font_size=11,
        )

        self.window.nextRow()
        self.plot_resp = self.window.addPlot(title="RESP")
        self.curve_resp = self.plot_resp.plot(pen=pg.mkPen((0, 220, 255), width=1.2))
        self.plot_resp.setXRange(-self.runtime.settings.time_window, 0)
        self.plot_resp.showGrid(x=True, y=True, alpha=0.3)
        self.plot_resp.setLabel("left", "RESP")
        self.plot_resp.setLabel("bottom", "Time (s)", **{"color": "#AAA", "font-size": "10pt"})
        self.info_text = HUDText(self.plot_resp, "Waiting for packets...", (0, 0), color=(180, 180, 180), anchor=(0, 0), font_size=11)

    def update_hud_positions(self):
        x_min, x_max = self.plot_ecg.viewRange()[0]
        y_min, y_max = self.plot_ecg.viewRange()[1]
        x_span = x_max - x_min
        y_span = y_max - y_min

        left_x = x_min + x_span * self.HUD_LEFT_PAD_RATIO
        right_x = x_min + x_span * self.HUD_RIGHT_PAD_RATIO
        top_y = y_max - y_span * self.HUD_TOP_PAD_RATIO
        line_gap = y_span * self.HUD_LINE_GAP_RATIO

        if self.status_text is not None:
            self.status_text.item.setPos(left_x, top_y)
        if self.last_packet_text is not None:
            self.last_packet_text.item.setPos(left_x, top_y - line_gap)
        if self.ecg_text is not None:
            self.ecg_text.item.setPos(right_x, top_y - 0.5 * line_gap)
        if self.hr_text is not None:
            self.hr_text.item.setPos(right_x + x_span * 0.07, top_y + 0.5 * line_gap)

        resp_x_min, resp_x_max = self.plot_resp.viewRange()[0]
        resp_y_min, resp_y_max = self.plot_resp.viewRange()[1]
        resp_x_span = resp_x_max - resp_x_min
        resp_y_span = resp_y_max - resp_y_min
        resp_left_x = resp_x_min + resp_x_span * self.HUD_LEFT_PAD_RATIO
        resp_top_y = resp_y_max - resp_y_span * self.HUD_TOP_PAD_RATIO
        if self.info_text is not None:
            self.info_text.item.setPos(resp_left_x, resp_top_y)

    def update_plot(self):
        t_rel = self.runtime.timestamps - self.runtime.timestamps[-1]
        self.curve_ecg.setData(t_rel, self.runtime.ecg)
        self.curve_resp.setData(t_rel, self.runtime.resp)

        ecg_valid = self.runtime.ecg[np.isfinite(self.runtime.ecg)]
        if ecg_valid.size:
            ecg_min = float(np.min(ecg_valid))
            ecg_max = float(np.max(ecg_valid))
            ecg_pad = max(1000.0, (ecg_max - ecg_min) * 0.15)
            self.plot_ecg.setYRange(ecg_min - ecg_pad, ecg_max + ecg_pad, padding=0)

        resp_valid = self.runtime.resp[np.isfinite(self.runtime.resp)]
        if resp_valid.size:
            resp_min = float(np.min(resp_valid))
            resp_max = float(np.max(resp_valid))
            resp_pad = max(50.0, (resp_max - resp_min) * 0.15)
            self.plot_resp.setYRange(resp_min - resp_pad, resp_max + resp_pad, padding=0)

        self.update_hud_positions()

    def update(self):
        packets = self.runtime.read_packets_nb()
        if not packets:
            now = time.time()
            if not self.runtime.last_packet_at:
                self.info_text.set_text("Waiting for first valid packet...")
                self.info_text.set_color((180, 180, 180))
                if self.last_packet_text is not None:
                    self.last_packet_text.set_text("Last packet: waiting for stream sync")
                return
            if now - self.runtime.last_packet_at > 1.0:
                self.info_text.set_text("No packets received for >1 s")
                self.info_text.set_color((255, 200, 0))
                self.runtime._maybe_debug("no_packets", "No valid ECG/RESP packets received for >1 s", 1.0)
            return

        for t_recv, packet_seq, samples, hr, rr in packets:
            if self.runtime.packet_seq >= 0:
                expected_seq = (self.runtime.packet_seq + 1) % 256
                if packet_seq != expected_seq:
                    self.runtime.packet_loss_events += 1
                    self.runtime._debug(f"Packet sequence gap: expected {expected_seq}, got {packet_seq}")
            self.runtime.packet_seq = packet_seq
            self.runtime.last_hr = hr
            self.runtime.last_rr = rr
            self.runtime.last_packet_at = t_recv
            ecg_display = self.runtime.ecg_frame_to_display(samples)
            resp_display = self.runtime.resp_frame_to_display(samples)
            self.runtime.push_sample(t_recv, ecg_display, resp_display)

            t0 = t_recv - (self.runtime.samples_per_packet - 1) * self.runtime.dt_raw
            for i in range(self.runtime.samples_per_packet):
                ts = t0 + i * self.runtime.dt_raw
                ecg_sample = int(samples[i, 0])
                resp_sample = int(samples[i, 1])
                self.runtime.logfile.write(f"{ts},{packet_seq},{ecg_sample},{resp_sample},{int(hr)},{int(rr)}\n")
                self.runtime.total_samples += 1

            self.runtime.total_packets += 1

        self.hr_text.set_text(f"{self.runtime.last_hr:.0f}")
        #self.rr_text.set_text(f"RR: {self.runtime.last_rr:03d} rpm")
        packet_age_ms = (time.time() - self.runtime.last_packet_at) * 1000
        self.last_packet_text.set_text(
            f"Last packet: {self.runtime.last_packet_at:.3f} | Age: {packet_age_ms:.0f} ms"
        )
        self.info_text.set_text(
            f"Seq: {self.runtime.packet_seq} | Packets: {self.runtime.total_packets} | Samples: {self.runtime.total_samples} | Samples shown: {self.runtime.window}"
        )
        self.info_text.set_color((180, 180, 180))
        self.update_plot()
        self.runtime.logfile.flush()

    def run(self):
        self.runtime.open_log()
        self.runtime.open_serial()
        self.setup_ui()
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(10)
        self.qt_app.aboutToQuit.connect(self.runtime.close)
        self.qt_app.exec_()
