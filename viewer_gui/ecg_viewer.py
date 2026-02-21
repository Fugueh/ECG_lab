import sys
import numpy as np
from pyqtgraph.Qt import QtCore, QtWidgets
import pyqtgraph as pg
import pandas as pd
from PyQt5 import QtGui

# ---------- 数据加载 ----------
data_path = '../ecg_data/'
file_name = 'ecg_log_2025-11-17_130244.csv'
df = pd.read_csv(data_path + file_name)   # 你的两列：time, ecg

time_array = df["time"].values
ecg_array = df["ecg"].values

window_sec = 30; fs = 50
window_size = int(window_sec * fs)
max_start = len(ecg_array) - window_size
time_array -= time_array[0]

# ---------- curve更新函数 ----------
def update_view(curve, time_array, ecg_array, start_idx, window_size):
    end_idx = min(start_idx + window_size, len(ecg_array))
    x = time_array[start_idx:end_idx]
    y = ecg_array[start_idx:end_idx]
    curve.setData(x, y)



# ⭐ 通过 QApplication 实例启动 GUI 事件响应
app = QtWidgets.QApplication.instance()
if app is None:
    app = QtWidgets.QApplication([])

# ---------- 定义 Widget ----------
'''
通过 GraphicsLayoutWidget 创建 pyqtgraph 对象。
这是 PyQtGraph 提供的特殊 Widget，继承自 QWidget，
所以它可以作为一个独立的窗口显示 (show=True)。
win 本质上是一个自带了绘图布局能力的窗口 Widget.
'''
win = pg.GraphicsLayoutWidget()
win.setBackground('white')
ymin = 200; ymax = 700
plot = win.addPlot()
curve = plot.plot(pen=pg.mkPen((0, 204, 102), width=2))

#plot.showGrid(x=True, y=True)
plot.setYRange(ymin, ymax)
plot.setLabel(
    'bottom',
    'Time (s)',
    **{'font-size': '14pt', 'font-family': 'Arial'}
)
plot.setLabel(
    'left',
    'Amplitude',
    **{'font-size': '14pt', 'font-family': 'Arial'}
)

axis_x = plot.getAxis('bottom')
axis_y = plot.getAxis('left')
axis_x.setStyle(tickFont=QtGui.QFont('Arial', 10))
axis_y.setStyle(tickFont=QtGui.QFont('Arial', 10))

# ---------- 创建滑块 ----------
# 范围：x极小值到（极大值-窗口长度）
slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
slider.setMinimum(0)
slider.setMaximum(max_start)
slider.setValue(0)

# 初始渲染
update_view(curve, time_array, ecg_array, 0, window_size)

'''
⭐ slider更新事件使用信号与槽 (Signals & Slots) 机制。
首先定义槽函数（slot，或称回调函数），
然后操作事件信号（signal）通过connect传递。
'''
def on_slider_change(val):
    update_view(curve, time_array, ecg_array, val, window_size)

slider.valueChanged.connect(on_slider_change)

# ---------- 布局（layout）与容器（widget） ----------
layout = QtWidgets.QVBoxLayout()
layout.addWidget(win)
layout.addWidget(slider)

container = QtWidgets.QWidget()
container.setLayout(layout)
container.setWindowTitle("Captain ECG Viewer")
container.show()

# ---------- 退出app执行 ----------
sys.exit(app.exec_())

