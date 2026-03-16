import time
import numpy as np
from scipy.signal import find_peaks
from pyqtgraph.Qt import QtCore, QtWidgets
from PyQt5 import QtGui
from PyQt5.QtGui import QIcon, QFont
import pyqtgraph as pg
import colorsys

from configuration import *
from functions import *

# ---------- 日志文件 ----------
formatted_time = time.strftime("%Y-%m-%d_%H%M%S", time.localtime())
logfile = open("raw_record_%s.csv"%formatted_time, "w")
logfile.write(f"time,ecg,lead\n")


# ---------- PyQtGraph 初始化 ----------
app = QtWidgets.QApplication([])
app.setWindowIcon(QIcon("roast.ico"))
win = pg.GraphicsLayoutWidget(title="急眼监视器 - Mini")
# Always on the top
win.setWindowFlags(win.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
win.resize(600, 250)
win.show()

win.setBackground('k')
plot = win.addPlot()
curve_ecg = plot.plot(pen=pg.mkPen((0, 255, 0), width=1.2)) 

plot.setXRange(-time_window, 0)
ymin = 150; ymax = 860
plot.setYRange(ymin, ymax)
plot.showGrid(x=True, y=True, alpha=0.3)

yaxis = plot.getAxis('left')
yaxis.setStyle(showValues=False)
yaxis.setTicks([])

xaxis = plot.getAxis('bottom')
xticks_font = QFont("Arial", 10)
xaxis.setStyle(tickFont=xticks_font)
xaxis.setLabel(
    text='Time',
    units='s',
    **{'color': '#AAA', 'font-size': '10pt', 'font-family': 'Arial'}
)

# ---------- 文本显示 ----------
distance = 85
yloc = ymax+30
roast_text = HUDText(
    plot, text="[--] Are you ok?", pos=(-time_window, yloc), 
    color=(0, 255, 0), anchor=(0, 0), font_size=10
)

rr_text = HUDText(
    plot, text="RR Interval: -- s", pos=(-time_window, yloc-distance),
    color=(255, 255, 255), anchor=(0, 0), font_size=10
)

sdnn_text = HUDText(
    plot, text="SDNN: -- ms", pos=(-time_window, yloc-2*distance),
    color=(255, 255, 255), anchor=(0, 0), font_size=10
)

rmssd_text = HUDText(
    plot, text="RMSSD: -- ms", pos=(-time_window, yloc-3*distance),
    color=(255, 255, 255), anchor=(0, 0), font_size=10
)


hr_text = HUDText(
    plot, text="--", pos=(0, yloc+50),
    color=(0, 255, 0), anchor=(1, 0),
    font_size=50, bold=True
)

ecg_text = HUDText(
    plot, text="ECG\nbpm", pos=(-3, yloc), 
    color=(0, 255, 0), anchor=(1, 0), font_size=10
)

lead_text = HUDText(
    plot, text="NORMAL", pos=(-3, yloc - 200), 
    color=(0, 255, 0), anchor=(1, 0), font_size=10
)

# ------------ 嘲讽字体 ------------
def hr_roast(hr):
    if hr < 60:
        return "上班时间不许睡觉！"
    elif hr >= 60 and hr < 70:
        return "你在摸鱼？"
    elif hr >= 70 and hr < 80:
        return "稳如老狗"
    elif hr >=80 and hr < 90:
        return "急了？"
    elif hr >= 90 and hr < 100:
        return "咋还急眼了呢？"
    elif hr >= 100 and hr < 120:
        return "你已急哭"
    elif hr > 120:
        return "你没毛病吧？"


def hr_roast_color(hr):
    hr_min, hr_max = 60, 120
    ratio = (hr - hr_min) / (hr_max - hr_min)
    ratio = max(0, min(1, ratio))
    hue = (120 * (1 - ratio)) / 360
    r, g, b = colorsys.hsv_to_rgb(hue, 1, 1)
    if hr >= 60:
        return int(r*255), int(g*255), int(b*255)
    else:
        return (0, 180, 255)


def set_text(rr, hr, lead_off, rr_text, hr_text, ecg_text, roast_text, window_mean_hr):
    if lead_off:
        lead_text.set_text("LEAD OFF")
        lead_text.set_color((255, 0, 0))

        hr_text.set_text("-?-")
        rr_text.set_text("RR Interval: --")
        roast_text.set_text("[-?-] 你人呢？")
        sdnn_text.set_text("SDNN: -- ms")
        rmssd_text.set_text("RMSSD: -- ms")

        hr_text.set_color((255, 0, 0))
        ecg_text.set_color((255, 0, 0))
        roast_text.set_color((255, 0, 0))
        
    else:
        lead_text.set_text("NORMAL")
        lead_text.set_color((0, 255, 0))

        #color = text_color(hr)
        roast_color = hr_roast_color(window_mean_hr)

        hr_text.set_text(f"{hr:.0f}")
        rr_text.set_text(f"RR Interval: {rr[-1]:.2f} s")
        roast_text.set_text(f"[{window_mean_hr:0=.0f}] "+hr_roast(window_mean_hr))

        hr_text.set_color(roast_color)
        ecg_text.set_color(roast_color)
        roast_text.set_color(roast_color)

        
# ============= 更新函数 =============

def update_hr_display(data, lead_data):
    '''心率计算与显示（受 lead 状态约束）'''
    global _last_hr_ui, _last_hrv_ui, _prev_peak_abs_t
    global beat_count
    now = time.time()

    # ECG 上找峰
    peaks, _ = find_peaks(data, height=350, distance=20)

    if len(peaks) < 2:
        return

    # 取当前窗口最后一个 lead 状态
    lead_off = lead_data[-1] == 1

    rr, hr = rr_hr_calc(timestamps, peaks)
    window_mean_hr = 60 / np.mean(rr)
    set_text(rr, hr, lead_off, rr_text, hr_text, ecg_text, roast_text, window_mean_hr)

    if lead_off:
        return

    # ---------- 储存RR，计算 HRV ----------
    last_peak_t = float(timestamps[peaks[-1]])

    # 新 peak 出现时，记录RR：rr_buf
    if (_prev_peak_abs_t is None) or (last_peak_t > _prev_peak_abs_t + 1e-6):
        rr_in_arr = False
        if _prev_peak_abs_t is not None:
            last_rr = last_peak_t - _prev_peak_abs_t

            if 0.3 <= last_rr <= 2.0:  # 30~200 bpm
                # 伪迹通常表现为“突然跳变”，RSA通常是“连续变化”·
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
                    print("Beat: %d,"%beat_count, f"RR: {last_rr:.2f} s,", f"HR: {hr:.0f},", "In Array:",rr_in_arr)

        _prev_peak_abs_t = last_peak_t

    
    if now - _last_hrv_ui < 10.0:
        return
    _last_hrv_ui = now

    # 使用过去300个RR计算HRV
    rr_arr = np.array(rr_buf, dtype=float)
    if len(rr_arr) >= 30:
        rr_win = rr_arr[-300:]

        # --- 简单鲁棒清洗 ---
        med = np.median(rr_win)
        mad = np.median(np.abs(rr_win - med))
        if mad > 1e-12:
            # 3.5 比较宽，不容易误伤RSA
            rr_win = rr_win[np.abs(rr_win - med) <= 3.5 * 1.4826 * mad]

        # 再保底一次生理范围（防止上面没滤干净）
        rr_win = rr_win[(rr_win >= 0.3) & (rr_win <= 2.0)]

        if len(rr_win) >= 30:
            sdnn, rmssd = calc_sdnn_rmssd(rr_win)
            if sdnn is not None:
                sdnn_text.set_text(f"SDNN: {sdnn:.0f} ms")
                rmssd_text.set_text(f"RMSSD: {rmssd:.0f} ms")



# ---------- 主 update ----------
DT_RAW = 0.004   # 250Hz
DT_DISP = 0.020  # 50Hz（每帧一个点）

def update():
    frames = read_frames_nb(ser)
    if not frames:
        return

    for t_recv, t0_us, lead_off, samples in frames:
        # 先写 raw：5 点全写（真·数据质量）
        # 这里时间戳先用近似，够用；你以后要严谨再对齐 t0_us
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


# ---------- 定时器 ----------
timer = QtCore.QTimer()
timer.timeout.connect(update)
timer.start(4)  # 每 ~4ms 更新一次，适应 200–250Hz 采样

# ---------- 清理 ----------
def cleanup():
    logfile.close()
    ser.close()
app.aboutToQuit.connect(cleanup)

_last_hr_ui = 0.0
_last_hrv_ui = 0.0
_prev_peak_abs_t = None

app.exec_()
