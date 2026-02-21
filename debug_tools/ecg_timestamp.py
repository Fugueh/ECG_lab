from ecg_functions import *
import time, threading, queue, serial, numpy as np
from pyqtgraph.Qt import QtCore, QtWidgets
from PyQt5 import QtGui
import pyqtgraph as pg

# --------- 参数区 ---------
fs = 50           # 实测采样率 Hz
WINDOW = 10 * fs   # 10 秒窗口长度

# ---------- 串口读取线程 ----------
def serial_reader():
    while True:
        raw = ser.readline().decode(errors='ignore').strip()
        if raw.isdigit():
            data_q.put(int(raw))


# 初始化串口
ser = serial.Serial(PORT, BAUD)
print(f"正在监听 {PORT} ...")

# 队列通信
data_q = queue.Queue()

# 生成过去 10s 的时间戳
t0 = time.time()
timestamps = np.linspace(t0 - 10, t0, WINDOW)

# 对应的初始信号
data = np.zeros(WINDOW) 
threading.Thread(target=serial_reader, daemon=True).start()


# ---------- PyQtGraph 初始化 ----------
app = QtWidgets.QApplication([])
win = pg.GraphicsLayoutWidget(show=True, title="Captain ECG Monitor")
win.setBackground('k')

# 绘图初始化
plot = win.addPlot(title="ECG Signal (Lead I)")
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
hr_text.setFont(QtGui.QFont("Arial", 40, QtGui.QFont.Bold))
hr_text.setPos(-0.5, 700)
plot.addItem(hr_text)

ecg_text = pg.TextItem(text="ECG\nbpm", color=(0,255,0), anchor=(1,0))
ecg_text.setFont(QtGui.QFont("Arial", 12))
ecg_text.setPos(-2, 660)
plot.addItem(ecg_text)

curve = plot.plot(pen=pg.mkPen((0, 255, 0), width=1.2)) 


# ---------- 心率计算 ----------
def rr_hr_calc(peaks):
    rr = np.diff(timestamps[peaks])
    hr = 60 / rr[-1]
    return rr, hr

# ---------- 更新函数 ----------
def update():
    global data, timestamps

    while not data_q.empty():
        val = data_q.get()
        timestamp = time.time()
        timestamps = np.append(timestamps, timestamp)[-WINDOW:]
        data = np.append(data, val)[-WINDOW:]
        peaks, _ = find_peaks(data, height=350, distance=20)
        if len(peaks) > 1:
            rr, hr = rr_hr_calc(peaks)
            color = text_color(hr)
            rr_text.setText(f"RR Interval: {rr[-1]:.2f} s")
            hr_text.setText(f"{hr:.0f}")
            hr_text.setColor(color)
            ecg_text.setColor(color)
        t_rel = timestamps - timestamps[-1]
        curve.setData(t_rel, data)

# 定时器：以固定间隔调用 update()
timer = QtCore.QTimer()
timer.timeout.connect(update)
timer.start(5)  # 每5 ms刷新一次

# ---------- 主循环 ----------
if __name__ == '__main__':
    QtWidgets.QApplication.instance().exec_()
    ser.close()