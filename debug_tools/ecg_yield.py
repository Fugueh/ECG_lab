import time
import numpy as np 
import pandas as pd
from scipy.signal import find_peaks
from pyqtgraph.Qt import QtCore, QtWidgets
from PyQt5 import QtGui
import pyqtgraph as pg

formatted_time = time.strftime("%Y-%m-%d_%H%M%S", time.localtime())
logfile = open("ecg_log_%s.csv"%formatted_time, "w")
logfile.write(f"time,ecg\n")

df = pd.read_csv('ecg_data-1110.csv')
fs = 50
WINDOW = 10 * fs

timestamps = np.linspace(df.loc[0,'time'] - 10, df.loc[0,'time'], WINDOW)
data = np.zeros(WINDOW)

gen = ((df.loc[i,'time'], df.loc[i,'ecg']) for i in df.index)

# ---------- PyQtGraph 初始化 ----------
app = QtWidgets.QApplication([])
win = pg.GraphicsLayoutWidget(show=True, title="Captain ECG Monitor")
win.setBackground('k')
plot = win.addPlot(title="ECG Signal (Lead I)")
curve = plot.plot(pen=pg.mkPen((0, 255, 0), width=1.2)) 

# 绘图初始化
plot.setXRange(-10, 0)
plot.setYRange(250, 660)
plot.setLabel('left', 'Amplitude')
plot.showGrid(x=True, y=True, alpha=0.3)

# Xticklabels 时间单位
plot.getAxis('bottom')
plot.setLabel('bottom', 'Time (s)', **{'color': '#AAA', 'font-size': '10pt'})

# 心率文本
rr_text = pg.TextItem(text="RR Interval: -- s", color=(255, 255, 255), anchor=(0,0))
rr_text.setFont(QtGui.QFont("Arial", 12))
rr_text.setPos(-10, 660)
plot.addItem(rr_text)

hr_text = pg.TextItem(text="--", color=(0,255,0), anchor=(1,0))
hr_text.setFont(QtGui.QFont("Arial", 60, QtGui.QFont.Bold))
hr_text.setPos(-0.5, 700)
plot.addItem(hr_text)

ecg_text = pg.TextItem(text="ECG\nbpm", color=(0,255,0), anchor=(1,0))
ecg_text.setFont(QtGui.QFont("Arial", 12))
ecg_text.setPos(-2, 660)
plot.addItem(ecg_text)


# ---------- 心率计算 ----------
def rr_hr_calc(peaks):
    rr = np.diff(timestamps[peaks])
    hr = 60 / rr[-1]
    return rr, hr

# ---------- 心率文本颜色 ----------
def text_color(hr):
    if hr < 50:
        return (0, 180, 255)
    elif hr < 100:
        return (0, 255, 0)
    elif hr < 120:
        return (255, 255, 0)
    else:
        return (248, 47, 0)

# ---------- 更新函数 ----------
def read_sample():
    try:
        return next(gen)
    except StopIteration:
        return None, None

def push_sample(timestamp, val):
    global data, timestamps
    timestamps = np.append(timestamps, timestamp)[-WINDOW:]
    data = np.append(data, val)[-WINDOW:]

def update_plot():
    t_rel = timestamps - timestamps[-1]
    curve.setData(t_rel, data)

def update_hr_display():
    peaks, _ = find_peaks(data, height=350, distance=20)
    if len(peaks) > 1:
        rr, hr = rr_hr_calc(peaks)
        color = text_color(hr)
        rr_text.setText(f"RR Interval: {rr[-1]:.2f} s")
        hr_text.setText(f"{hr:.0f}")
        hr_text.setColor(color)
        ecg_text.setColor(color)

def update():
    timestamp, val = read_sample()
    if timestamp is None:
        return
    
    push_sample(timestamp, val)
    logfile.write(f"{timestamp},{val}\n")
    logfile.flush()

    update_plot()
    update_hr_display()

timer = QtCore.QTimer()
timer.timeout.connect(update)
timer.start(int(1000/fs))

app.aboutToQuit.connect(lambda: logfile.close())
app.exec_()
