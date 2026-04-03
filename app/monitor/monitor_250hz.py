import time
import numpy as np
from scipy.signal import find_peaks
from pyqtgraph.Qt import QtCore, QtWidgets
from PyQt5 import QtGui
import pyqtgraph as pg

from configuration import *
from functions import *


# ---------- 日志文件 ----------
formatted_time = time.strftime("%Y-%m-%d_%H%M%S", time.localtime())
logfile = open("raw_record_%s.csv"%formatted_time, "w")
logfile.write(f"time,ecg,lead\n")


# ---------- PyQtGraph 初始化 ----------
app = QtWidgets.QApplication([])
win = pg.GraphicsLayoutWidget(show=True, title="Captain ECG Monitor")
win.setBackground('k')
plot = win.addPlot(title="ECG Signal (Lead I)")
curve_ecg = plot.plot(pen=pg.mkPen((0, 255, 0), width=1.2)) 

plot.setXRange(-time_window, 0)
ymin = 150; ymax = 860
plot.setYRange(ymin, ymax)
plot.setLabel('left', 'Amplitude')
plot.showGrid(x=True, y=True, alpha=0.3)

plot.getAxis('bottom')
plot.setLabel('bottom', 'Time (s)', **{'color': '#AAA', 'font-size': '10pt'})


# ---------- 文本显示 ----------
rr_text = HUDText(
    plot, text="RR Interval: -- s", pos=(-time_window+7, ymax-200),
    color=(255, 255, 255), anchor=(1, 0), font_size=20
)

sdnn_text = HUDText(
    plot, text="SDNN: -- ms", pos=(-time_window+7, ymax-230),
    color=(255, 255, 255), anchor=(1, 0), font_size=20
)

rmssd_text = HUDText(
    plot, text="RMSSD: -- ms", pos=(-time_window+7, ymax-260),
    color=(255, 255, 255), anchor=(1, 0), font_size=20
)


hr_text = HUDText(
    plot, text="--", pos=(0, ymax),
    color=(0, 255, 0), anchor=(1, 0),
    font_size=120, bold=True
)

ecg_text = HUDText(
    plot, text="ECG\nbpm", pos=(-1.4, ymax - 20), 
    color=(0, 255, 0), anchor=(1, 0), font_size=20
)

lead_text = HUDText(
    plot, text="NORMAL", pos=(-1.4, ymax - 90), 
    color=(0, 255, 0), anchor=(1, 0), font_size=20
)


def maybe_append_rr(last_peak_t, hr):
    '''通过RR间隔的阈值跳变决定是否将最新RR间隔加入缓冲区'''
    global _prev_peak_abs_t, beat_count

    rr_in_arr = False

    if _prev_peak_abs_t is None:
        _prev_peak_abs_t = last_peak_t
        return rr_in_arr

    last_rr = last_peak_t - _prev_peak_abs_t

    if 0.3 <= last_rr <= 2.0:  # 30~200 bpm
        # 伪迹通常表现为“突然跳变”，RSA通常是“连续变化”
        if len(rr_buf) >= 1:
            prev_rr = float(rr_buf[-1])
            # 阈值放宽，尽量不误杀RSA
            if (0.5 * prev_rr) <= last_rr <= (1.8 * prev_rr):
                rr_buf.append(last_rr)
                rr_in_arr = True
        else:
            rr_buf.append(last_rr)
            rr_in_arr = True

        beat_count += 1

        if not rr_in_arr:
            print(
                "Beat: %d," % beat_count,
                f"RR: {last_rr:.2f} s,",
                f"HR: {hr:.0f},",
                "In Array:",
                rr_in_arr
            )

    _prev_peak_abs_t = last_peak_t
    return rr_in_arr


def update_hr_display(data, lead_data):
    '''心率计算与显示（受 lead 状态约束）'''
    global _last_hrv_ui, _prev_peak_abs_t

    now = time.time()
    peaks, _ = find_peaks(data, height=350, distance=20)

    if len(peaks) < 2:
        return

    lead_off = lead_data[-1] == 1

    # ---------- 导联状态文本 ----------
    if lead_off:
        lead_text.set_text("LEAD OFF")
        lead_text.set_color((255, 0, 0))
    else:
        lead_text.set_text("NORMAL")
        lead_text.set_color((0, 255, 0))

    # ---------- 导联脱落处理 ----------
    if lead_off:
        hr_text.set_text("--")
        rr_text.set_text("RR Interval: --")
        hr_text.set_color((255, 0, 0))
        ecg_text.set_color((255, 0, 0))
        return

    # ---------- 正常心电分支 ----------
    last_peak_t = float(timestamps[peaks[-1]])

    rr, hr = rr_hr_calc(timestamps, peaks)
    color = text_color(hr)
    rr_text.set_text(f"RR Interval: {rr[-1]:.2f} s")
    hr_text.set_text(f"{hr:.0f}")
    hr_text.set_color(color)
    ecg_text.set_color(color)

    # ---------- 储存RR ----------
    if (_prev_peak_abs_t is None) or (last_peak_t > _prev_peak_abs_t + 1e-6):
        maybe_append_rr(last_peak_t, hr)

    # ---------- 每 10s 更新 HRV ----------
    if now - _last_hrv_ui >= 10.0:
        _last_hrv_ui = now
        sdnn, rmssd = update_hrv(rr_buf)
        if sdnn is not None:
            sdnn_text.set_text(f"SDNN: {sdnn:.0f} ms")
            rmssd_text.set_text(f"RMSSD: {rmssd:.0f} ms")



# ---------- 主 update ----------
DT_RAW = 0.004   # 250Hz
DT_DISP = 0.020  # 50Hz（每帧一个点）

def update(ser):
    frames = read_frames_nb(ser)
    if not frames:
        return

    for t_recv, t0_us, lead_off, samples in frames:
        # 先写 raw：5 点全写（真·数据质量）
        # 这里时间戳先用近似；以后要严谨再对齐 t0_us
        t0 = t_recv - 5*DT_RAW
        for i, ecg in enumerate(samples):
            ts = t0 + i*DT_RAW
            logfile.write(f"{ts},{int(ecg)},{int(lead_off)}\n")

        # 再喂 display：一帧折成一个点（真·界面质量）
        ecg_disp = frame_to_display(samples)
        ts_disp = t_recv  # 或者用 t0 + 4*DT_RAW，当帧末尾
        push_sample(timestamps, data, lead_data, ts_disp, ecg_disp, int(lead_off))

    update_plot(timestamps, curve_ecg, data)
    update_hr_display(data, lead_data)

    logfile.flush()

# 清理
def cleanup(ser):
    logfile.close()
    ser.close()


def main():
    import serial
    global _last_hrv_ui, _prev_peak_abs_t

    _last_hrv_ui = 0.0
    _prev_peak_abs_t = None

    ser = serial.Serial(SERIAL_PORT, BAUD, timeout=0)

    # 定时器
    timer = QtCore.QTimer()
    timer.timeout.connect(lambda: update(ser))
    timer.start(4)  # 每 ~4ms 更新一次，适应 200–250Hz 采样

    app.aboutToQuit.connect(lambda: cleanup(ser))
    app.exec_()


if __name__ == "__main__":
    main()