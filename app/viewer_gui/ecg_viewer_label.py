# ecg_viewer_diff.py
# Captain ECG Viewer (NK miss / My extra markers) + Theme switch
# Columns expected: time, ecg, (optional) nk_miss, my_extra

import sys, argparse, os
import numpy as np
import pandas as pd

from pyqtgraph.Qt import QtCore, QtWidgets
import pyqtgraph as pg
from PyQt5 import QtGui


# =========================
# 0) Theme control (ONE place)
# =========================
THEME = "dark"   # "dark" or "light"

THEMES = {
    "dark": {
        "pg_bg": "k",
        "pg_fg": "w",
        "win_bg": "k",
        "container_bg": "black",
        "grid_alpha": 0.15,
        "ecg_pen": (0, 204, 102, 180),      # green-ish, slightly transparent
        "detail_pen": (220, 80, 80, 220),   # red-ish
        "nk_brush": (0, 102, 255, 180),     # blue
        "my_brush": (255, 140, 0, 180),     # orange
    },
    "light": {
        "pg_bg": "w",
        "pg_fg": "k",
        "win_bg": "w",
        "container_bg": "white",
        "grid_alpha": 0.25,
        "ecg_pen": (0, 140, 70, 200),
        "detail_pen": (200, 0, 0, 220),
        "nk_brush": (0, 102, 255, 200),
        "my_brush": (255, 140, 0, 200),
    }
}

if THEME not in THEMES:
    raise ValueError(f"THEME must be one of {list(THEMES.keys())}, got {THEME}")

T = THEMES[THEME]


# =========================
# 1) Args / data loading
# =========================
data_path = "../ecg_data/"
default_file = "ecg_nk_my_diff.parquet"

def parse_args():
    parser = argparse.ArgumentParser(description="Captain ECG Viewer")
    parser.add_argument(
        "ecg_df",
        nargs="?",
        default=os.path.join(data_path, default_file),
        help="Path to ECG parquet (columns: time, ecg, optional: nk_miss, my_extra)"
    )
    return parser.parse_args()


# =========================
# 2) Utilities (plot updates)
# =========================
def update_view(curve, time_array, ecg_array, start_idx, window_size):
    end_idx = min(start_idx + window_size, len(ecg_array))
    curve.setData(time_array[start_idx:end_idx], ecg_array[start_idx:end_idx])

def update_markers(scatter_item, time_array, ecg_array, mask, start_idx, window_size):
    if mask is None:
        scatter_item.setData([], [])
        return

    end_idx = min(start_idx + window_size, len(ecg_array))
    sub = mask[start_idx:end_idx]

    if not np.any(sub):
        scatter_item.setData([], [])
        return

    idx = np.flatnonzero(sub) + start_idx
    scatter_item.setData(time_array[idx], ecg_array[idx])


# =========================
# 3) App / theme init
# =========================
def ensure_qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app

def apply_theme():
    # Global pyqtgraph theme
    pg.setConfigOption("background", T["pg_bg"])
    pg.setConfigOption("foreground", T["pg_fg"])


# =========================
# 4) UI construction
# =========================
def build_viewer(df: pd.DataFrame, file_title: str):
    # ---- arrays ----
    time_array = df["time"].values.astype(float)
    ecg_array = df["ecg"].values.astype(float)

    # Normalize time to start at 0s for display
    time_array = time_array - time_array[0]

    # Optional masks
    nk_mask = df["nk_miss"].values.astype(bool) if "nk_miss" in df.columns else None
    my_mask = df["my_extra"].values.astype(bool) if "my_extra" in df.columns else None

    # ---- window params ----
    window_sec = 40
    fs = 250
    window_size = int(window_sec * fs)

    detail_sec = 10
    detail_window_size = int(detail_sec * fs)

    max_start = len(ecg_array) - 4 * window_size
    max_start = max(0, max_start)

    ymin, ymax = 250, 500

    # ---- main widget ----
    win = pg.GraphicsLayoutWidget()
    win.setBackground(T["win_bg"])   # switch black or white

    # ---- top 4 plots ----
    plots, curves = [], []
    nk_scatters, my_scatters = [], []

    for i in range(4):
        plot = win.addPlot(row=i, col=0)
        plot.setYRange(ymin, ymax)
        plot.showGrid(x=True, y=True, alpha=T["grid_alpha"])

        # ECG curve
        curve = plot.plot(pen=pg.mkPen(T["ecg_pen"], width=1))

        # Axis styling
        axis_y = plot.getAxis("left")
        axis_y.setStyle(tickFont=QtGui.QFont("Arial", 10), showValues=False)

        axis_x = plot.getAxis("bottom")
        axis_x.setStyle(tickFont=QtGui.QFont("Arial", 10))

        if i == 3:
            plot.setLabel("bottom", "Time (s)", **{"font-size": "14pt", "font-family": "Arial"})

        # Markers
        nk_scatter = pg.ScatterPlotItem(
            symbol="o",
            size=7,
            pen=pg.mkPen(None),
            brush=pg.mkBrush(*T["nk_brush"]),
            pxMode=True
        )
        my_scatter = pg.ScatterPlotItem(
            symbol="o",
            size=7,
            pen=pg.mkPen(None),
            brush=pg.mkBrush(*T["my_brush"]),
            pxMode=True
        )
        plot.addItem(nk_scatter)
        plot.addItem(my_scatter)

        plots.append(plot)
        curves.append(curve)
        nk_scatters.append(nk_scatter)
        my_scatters.append(my_scatter)

    # ---- detail plot ----
    detail_plot = win.addPlot(row=4, col=0)
    detail_plot.setYRange(ymin, ymax)
    detail_plot.showGrid(x=True, y=True, alpha=T["grid_alpha"])

    detail_curve = detail_plot.plot(pen=pg.mkPen(T["detail_pen"], width=1))
    detail_plot.setLabel("bottom", "Detail: t0 ~ t0 + 10 s", **{"font-size": "14pt", "font-family": "Arial"})

    axis_y = detail_plot.getAxis("left")
    axis_y.setStyle(showValues=False)

    axis_x = detail_plot.getAxis("bottom")
    axis_x.setStyle(tickFont=QtGui.QFont("Arial", 10))

    detail_nk_scatter = pg.ScatterPlotItem(
        symbol="o",
        size=8,
        pen=pg.mkPen(None),
        brush=pg.mkBrush(*T["nk_brush"]),
        pxMode=True
    )
    detail_my_scatter = pg.ScatterPlotItem(
        symbol="o",
        size=8,
        pen=pg.mkPen(None),
        brush=pg.mkBrush(*T["my_brush"]),
        pxMode=True
    )
    detail_plot.addItem(detail_nk_scatter)
    detail_plot.addItem(detail_my_scatter)

    # ---- slider ----
    slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    slider.setMinimum(0)
    slider.setMaximum(max_start)
    slider.setValue(0)

    # ---- initial render ----
    for i, curve in enumerate(curves):
        start_idx = i * window_size
        update_view(curve, time_array, ecg_array, start_idx, window_size)
        update_markers(nk_scatters[i], time_array, ecg_array, nk_mask, start_idx, window_size)
        update_markers(my_scatters[i], time_array, ecg_array, my_mask, start_idx, window_size)

    update_view(detail_curve, time_array, ecg_array, 0, detail_window_size)
    update_markers(detail_nk_scatter, time_array, ecg_array, nk_mask, 0, detail_window_size)
    update_markers(detail_my_scatter, time_array, ecg_array, my_mask, 0, detail_window_size)

    # ---- slider callback ----
    def on_slider_change(t0):
        t0 = int(t0)
        for i, curve in enumerate(curves):
            start_idx = t0 + i * window_size
            update_view(curve, time_array, ecg_array, start_idx, window_size)
            update_markers(nk_scatters[i], time_array, ecg_array, nk_mask, start_idx, window_size)
            update_markers(my_scatters[i], time_array, ecg_array, my_mask, start_idx, window_size)

        update_view(detail_curve, time_array, ecg_array, t0, detail_window_size)
        update_markers(detail_nk_scatter, time_array, ecg_array, nk_mask, t0, detail_window_size)
        update_markers(detail_my_scatter, time_array, ecg_array, my_mask, t0, detail_window_size)

    slider.valueChanged.connect(on_slider_change)

    # ---- layout container ----
    layout = QtWidgets.QVBoxLayout()
    layout.addWidget(win)
    layout.addWidget(slider)

    container = QtWidgets.QWidget()
    container.setLayout(layout)
    container.setWindowTitle(f"Captain ECG Viewer [{THEME}]: {file_title}")
    container.setStyleSheet(f"background-color: {T['container_bg']};")
    container.show()

    return container


# =========================
# 5) Main
# =========================
def main():
    args = parse_args()

    apply_theme()
    ensure_qapp()

    df = pd.read_parquet(args.ecg_df)
    required = {"time", "ecg"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}. Found columns: {list(df.columns)}")

    build_viewer(df, os.path.basename(args.ecg_df))
    sys.exit(QtWidgets.QApplication.instance().exec_())


if __name__ == "__main__":
    main()