import sys, argparse, os
import numpy as np
from pyqtgraph.Qt import QtCore, QtWidgets
import pyqtgraph as pg
import pandas as pd
from PyQt5 import QtGui


# ---------- 数据加载 ----------
data_path = '../ecg_data/'
file_name = 'ecg_nk_my_diff.parquet'

def parse_args():
    parser = argparse.ArgumentParser(description="Captain ECG Viewer")
    parser.add_argument(
        "ecg_df",
        nargs="?",
        default=os.path.join(data_path, file_name),
        help="Path to ECG file (columns: time, ecg, lead)"
    )
    return parser.parse_args()

args = parse_args()
df = pd.read_parquet(args.ecg_df)
time_array = df["time"].values
ecg_array = df["ecg"].values

# ---------- 差异标签（可选列） ----------
nk_mask = df["nk_miss"].values.astype(bool) if "nk_miss" in df.columns else None
my_mask = df["my_extra"].values.astype(bool) if "my_extra" in df.columns else None

window_sec = 40; fs = 250
window_size = int(window_sec * fs)
detail_sec = 10
detail_window_size = int(detail_sec * fs)

max_start = len(ecg_array) - 4 * window_size
time_array -= time_array[0]

# ---------- curve更新函数 ----------
def update_view(curve, time_array, ecg_array, start_idx, window_size):
    end_idx = min(start_idx + window_size, len(ecg_array))
    x = time_array[start_idx:end_idx]
    y = ecg_array[start_idx:end_idx]
    curve.setData(x, y)

# ⭐ QApplication
app = QtWidgets.QApplication.instance()
if app is None:
    app = QtWidgets.QApplication([])

# ----------marker更新函数 ----------
def update_markers(scatter_item, time_array, ecg_array, mask, start_idx, window_size):
    if mask is None:
        scatter_item.setData([], [])
        return

    end_idx = min(start_idx + window_size, len(ecg_array))

    # 取窗口内 True 的位置
    sub = mask[start_idx:end_idx]
    if not np.any(sub):
        scatter_item.setData([], [])
        return

    idx = np.flatnonzero(sub) + start_idx
    x = time_array[idx]
    y = ecg_array[idx]
    scatter_item.setData(x, y)

# ---------- GraphicsLayoutWidget ----------
win = pg.GraphicsLayoutWidget()
win.setBackground('k') # switch black or white

ymin = 250; ymax = 500

plots = []
curves = []
nk_scatters = []
my_scatters = []

for i in range(4):
    plot = win.addPlot(row=i, col=0)
    curve = plot.plot(pen=pg.mkPen((0, 204, 102), width=2))

    plot.setYRange(ymin, ymax)

    axis_y = plot.getAxis('left')
    axis_y.setStyle(tickFont=QtGui.QFont('Arial', 10))

    # y axis
    axis_y = plot.getAxis('left')
    axis_y.setStyle(
        tickFont=QtGui.QFont('Arial', 10),
        showValues=False
    )

    # x axis
    axis_x = plot.getAxis('bottom')
    axis_x.setStyle(tickFont=QtGui.QFont('Arial', 10))

    if i == 3:
        plot.setLabel(
            'bottom',
            'Time (s)',
            **{'font-size': '14pt', 'font-family': 'Arial'}
        )

    plots.append(plot)
    curves.append(curve)

    # 两层 scatter：蓝点标 nk_miss，橙点标 my_extra
    nk_scatter = pg.ScatterPlotItem(
        pen=pg.mkPen(None),
        brush=pg.mkBrush(0, 102, 255, 220),  # 蓝
        size=10
    )
    my_scatter = pg.ScatterPlotItem(
        pen=pg.mkPen(None),
        brush=pg.mkBrush(255, 140, 0, 220),  # 橙
        size=10
    )

    plot.addItem(nk_scatter)
    plot.addItem(my_scatter)
    nk_scatters.append(nk_scatter)
    my_scatters.append(my_scatter)

# ---------- 详情行 ----------
detail_plot = win.addPlot(row=4, col=0)
detail_curve = detail_plot.plot(pen=pg.mkPen((200, 0, 0), width=2))

detail_plot.setYRange(ymin, ymax)
detail_plot.setLabel(
    'bottom',
    'Detail: t0 ~ t0 + 10 s',
    **{'font-size': '14pt', 'font-family': 'Arial'}
)

detail_nk_scatter = pg.ScatterPlotItem(
    pen=pg.mkPen(None),
    brush=pg.mkBrush(0, 102, 255, 220),
    size=7
)
detail_my_scatter = pg.ScatterPlotItem(
    pen=pg.mkPen(None),
    brush=pg.mkBrush(255, 140, 0, 220),
    size=7
)
detail_plot.addItem(detail_nk_scatter)
detail_plot.addItem(detail_my_scatter)

axis_y = detail_plot.getAxis('left')
axis_y.setStyle(showValues=False)

axis_x = detail_plot.getAxis('bottom')
axis_x.setStyle(tickFont=QtGui.QFont('Arial', 10))

# ---------- Slider ----------
slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
slider.setMinimum(0)
slider.setMaximum(max_start)
slider.setValue(0)

# 初始渲染（4 个一起）
# 当 t0 = 0 时，四个子图依次显示连续的四个时间窗
for i, curve in enumerate(curves):
    start_idx = i * window_size
    update_view(curve, time_array, ecg_array, start_idx, window_size)

    update_markers(nk_scatters[i], time_array, ecg_array, nk_mask, start_idx, window_size)
    update_markers(my_scatters[i], time_array, ecg_array, my_mask, start_idx, window_size)

update_view(detail_curve, time_array, ecg_array, 0, detail_window_size)
update_markers(detail_nk_scatter, time_array, ecg_array, nk_mask, 0, detail_window_size)
update_markers(detail_my_scatter, time_array, ecg_array, my_mask, 0, detail_window_size)

# slider 回调，控制全局时间原点 t0
def on_slider_change(t0):
    for i, curve in enumerate(curves):
        start_idx = t0 + i * window_size
        update_view(curve, time_array, ecg_array, start_idx, window_size)

        update_markers(nk_scatters[i], time_array, ecg_array, nk_mask, start_idx, window_size)
        update_markers(my_scatters[i], time_array, ecg_array, my_mask, start_idx, window_size)

    update_view(detail_curve, time_array, ecg_array, t0, detail_window_size)
    update_markers(detail_nk_scatter, time_array, ecg_array, nk_mask, t0, detail_window_size)
    update_markers(detail_my_scatter, time_array, ecg_array, my_mask, t0, detail_window_size)

slider.valueChanged.connect(on_slider_change)


# ---------- Layout ----------
layout = QtWidgets.QVBoxLayout()
layout.addWidget(win)
layout.addWidget(slider)

container = QtWidgets.QWidget()
container.setLayout(layout)
container.setWindowTitle('Captain ECG Viewer: %s'%args.ecg_df)
container.setStyleSheet("background-color: black;")
container.show()

# ---------- 事件循环 ----------
sys.exit(app.exec_())
