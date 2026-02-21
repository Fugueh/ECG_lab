import time
import numpy as np
from scipy.signal import find_peaks
from PyQt5 import QtGui
import pyqtgraph as pg

# ---------- 文本显示 ----------
class HUDText:
    def __init__(
        self, plot,
        text: str, pos: tuple[float, float],
        color=(255, 255, 255), anchor=(0, 0),
        font_family="Arial", font_size=12, bold=False,
    ):
        self.item = pg.TextItem(text=text, color=color, anchor=anchor)
        self.item.setFont(QtGui.QFont(font_family, font_size, QtGui.QFont.Bold if bold else QtGui.QFont.Normal))
        self.item.setPos(*pos)
        plot.addItem(self.item)

    def set_text(self, text: str):
        self.item.setText(text)

    def set_color(self, color):
        self.item.setColor(color)

    def set_pos(self, x: float, y: float):
        self.item.setPos(x, y)


# ------------ 指标计算 -------------
# 心率计算
def rr_hr_calc(timestamps, peaks):
    rr = np.diff(timestamps[peaks])
    hr = 60 / rr[-1]
    return rr, hr

# 心率文本颜色
def text_color(hr):
    if hr < 50:
        return (0, 180, 255)
    elif hr < 100:
        return (0, 255, 0)
    elif hr < 120:
        return (255, 255, 0)
    else:
        return (248, 47, 0)
    
# 计算HRV 指标   
def calc_sdnn_rmssd(rr_array):
    # rr_array: seconds
    if len(rr_array) < 3:
        return None, None
    rr_ms = rr_array * 1000.0
    sdnn = np.std(rr_ms, ddof=1)  # ms
    rmssd = np.sqrt(np.mean(np.diff(rr_ms) ** 2))  # ms
    return sdnn, rmssd



# ---------- 更新函数 ----------
def read_sample(ser):
    """Read from serial port: ecg,lead_off"""
    try:
        line = ser.readline().decode(errors='ignore').strip()
        if not line:
            return None

        parts = line.split(',')
        if len(parts) < 2:
            return None

        ecg = float(parts[0])
        lead_off = int(parts[1])  # 0/1
        timestamp = time.time()
        return timestamp, ecg, lead_off
    except Exception:
        return None


def read_frame(ser):
    """Read one frame from serial: t0_us, lead_off, p0..p4"""
    try:
        line = ser.readline().decode(errors='ignore').strip()
        if not line:
            return None

        parts = line.split(',')
        if len(parts) != 7:
            return None

        t0_us = int(parts[0])
        lead_off = int(parts[1])
        samples = [int(x) for x in parts[2:7]]  # 5 points

        # 用本机时间当基准也行，但更稳是用 t0_us 重建相对时间
        # 这里先给“能跑就行”的版本：用接收时刻作为帧结束时刻
        t_recv = time.time()
        return t_recv, t0_us, lead_off, samples
    except Exception:
        return None

import struct
import time


FRAME_HDR = b"\xAA\x55"
FRAME_LEN = 17  # 2 + 4 + 1 + 10

_rxbuf = bytearray()

def read_frames_nb(ser):
    """
    Non-blocking: 从串口读入当前所有可用字节，解析出0~N帧。
    返回 list[ (t_recv, t0_us, lead_off, samples5_uint16) ]
    """
    global _rxbuf

    n = ser.in_waiting
    if n:
        _rxbuf += ser.read(n)

    frames = []

    while True:
        # 找帧头
        i = _rxbuf.find(FRAME_HDR)
        if i < 0:
            # 没有帧头：为了避免缓冲无限长，保留最后1字节（可能是0xAA）
            if len(_rxbuf) > 1:
                _rxbuf = _rxbuf[-1:]
            break

        # 丢弃帧头前的垃圾
        if i > 0:
            del _rxbuf[:i]

        # 缓冲不足一整帧，等下次再读
        if len(_rxbuf) < FRAME_LEN:
            break

        # 取一帧
        frame = bytes(_rxbuf[:FRAME_LEN])
        del _rxbuf[:FRAME_LEN]

        # 解包：< 小端；I=uint32；B=uint8；5H=5个uint16
        # frame: AA 55 | t0(4) | lead(1) | 5*uint16(10)
        t0_us, lead_off, p0, p1, p2, p3, p4 = struct.unpack("<IB5H", frame[2:])
        t_recv = time.time()
        frames.append((t_recv, t0_us, lead_off, (p0, p1, p2, p3, p4)))

    return frames



def push_sample(timestamps, data, lead_data, timestamp, ecg, lead_off):
    """Overwrite write cache (fixed window)"""

    timestamps[:-1] = timestamps[1:]
    timestamps[-1] = timestamp

    data[:-1] = data[1:]
    data[-1] = np.nan if lead_off else ecg

    lead_data[:-1] = lead_data[1:]
    lead_data[-1] = lead_off



def update_plot(timestamps, curve_ecg, data):
    """curve 画图：x 轴用相对时间，右侧为 0"""
    if timestamps.size < 2:
        return

    t_rel = timestamps - timestamps[-1]
    curve_ecg.setData(t_rel, data)



def frame_to_display(samples5):
    # 平均：更平滑；中位数：更抗尖刺。二选一。
    return float(np.median(samples5))
    # return float(np.mean(samples5))