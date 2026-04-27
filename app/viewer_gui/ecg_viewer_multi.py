import argparse
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PyQt5 import QtGui
from pyqtgraph.Qt import QtCore, QtWidgets


DATA_PATH = "../ecg_data/"
DEFAULT_FILE_NAME = "ecg_log_2025-11-17_130244.csv"
WINDOW_SEC = 40
DETAIL_SEC = 10
FS = 250
DETAIL_YMIN = -3
DETAIL_YMAX = 8
#YMIN = 250
#YMAX = 500
TICK_FONT = QtGui.QFont("Arial", 10)
LABEL_STYLE = {"font-size": "14pt", "font-family": "Arial"}
DETAIL_HR_HTML = (
    '<span style="font-family: Arial; font-size: 14pt; color: black;">'
    "{text}"
    "</span>"
)


def read_ecg_df(ecg_csv):
    """Load ECG data from CSV or Parquet."""
    if ecg_csv.endswith(".csv"):
        return pd.read_csv(ecg_csv)
    if ecg_csv.endswith(".parquet"):
        return pd.read_parquet(ecg_csv)
    raise ValueError(f"Unsupported file format: {ecg_csv}")


def parse_args():
    parser = argparse.ArgumentParser(description="Captain ECG Viewer")
    parser.add_argument(
        "ecg_csv",
        nargs="?",
        default=os.path.join(DATA_PATH, DEFAULT_FILE_NAME),
        help="Path to ECG CSV file (must include a time column and an ECG data column)",
    )
    parser.add_argument(
        "--column",
        default="ecg",
        help="Name of the ECG data column to plot (default: ecg)",
    )
    parser.add_argument(
        "--meanhr",
        action="store_true",
        help="Show mean heart rate in the detail panel",
    )
    return parser.parse_args()


def get_signal_columns(df, column):
    """Resolve required input columns and fail with a clear message when missing."""
    if "time" not in df.columns:
        raise KeyError("Missing required column: time")
    if column not in df.columns:
        raise KeyError(f"Missing required ECG column: {column}")
    return df["time"].to_numpy(), df[column].to_numpy()


def update_curve(curve, time_array, ecg_array, start_idx, window_size):
    """Render one time window onto a curve."""
    end_idx = min(start_idx + window_size, len(ecg_array))
    curve.setData(time_array[start_idx:end_idx], ecg_array[start_idx:end_idx])


def get_segment(time_array, ecg_array, start_idx, window_size):
    """Return a clipped ECG segment."""
    end_idx = min(start_idx + window_size, len(ecg_array))
    return time_array[start_idx:end_idx], ecg_array[start_idx:end_idx]


def clean_ecg_segment(ecg):
    """Clean an ECG segment with NeuroKit defaults."""
    try:
        import neurokit2 as nk
    except ImportError as exc:
        raise ImportError("Detail ECG display requires neurokit2 to be installed.") from exc

    return nk.ecg_clean(ecg, sampling_rate=FS)


def calc_avg_hr(timestamps, ecg_cleaned):
    """Estimate average heart rate from NeuroKit-detected R peaks."""
    try:
        import neurokit2 as nk
    except ImportError as exc:
        raise ImportError("Detail ECG display requires neurokit2 to be installed.") from exc

    _, info = nk.ecg_peaks(ecg_cleaned, sampling_rate=FS)

    peaks = np.asarray(info.get("ECG_R_Peaks", []), dtype=int)
    if len(peaks) < 2:
        return np.nan

    rr_intervals = np.diff(timestamps[peaks])
    valid_rr = rr_intervals[rr_intervals > 0]
    if len(valid_rr) == 0:
        return np.nan

    return 60 / np.mean(valid_rr)


def format_hr_text(avg_hr):
    """Create the text displayed in the detail panel."""
    if np.isnan(avg_hr):
        return "Avg HR: -- bpm"
    return f"Avg HR: {avg_hr:.1f} bpm"


def style_plot(plot, show_bottom_label=False):
    """Apply consistent axis styling to a plot."""
    #plot.setYRange(YMIN, YMAX)
    plot.getAxis("left").setStyle(tickFont=TICK_FONT, showValues=False)
    plot.getAxis("bottom").setStyle(tickFont=TICK_FONT)

    if show_bottom_label:
        plot.setLabel("bottom", "Time (s)", **LABEL_STYLE)


def position_text_relative(plot, text_item, x_ratio=0.98, y_ratio=0):
    """Position a text item by relative location within the current view range."""
    view_box = plot.getViewBox()
    x_min, x_max = view_box.viewRange()[0]
    y_min, y_max = view_box.viewRange()[1]

    x_pos = x_min + (x_max - x_min) * x_ratio
    y_pos = y_max - (y_max - y_min) * y_ratio
    text_item.setPos(x_pos, y_pos)


def update_detail_plot(detail_plot, detail_curve, detail_hr_text, time_array, ecg_array, start_idx, window_size):
    """Refresh detail waveform and its average heart-rate label."""
    detail_x, detail_y = get_segment(time_array, ecg_array, start_idx, window_size)
    detail_y_cleaned = clean_ecg_segment(detail_y)
    detail_std = np.std(detail_y_cleaned)
    if np.isclose(detail_std, 0):
        detail_y_normalized = np.zeros_like(detail_y_cleaned)
    else:
        detail_y_normalized = (detail_y_cleaned - np.mean(detail_y_cleaned)) / detail_std
    detail_curve.setData(detail_x, detail_y_normalized)
    if len(detail_x) > 1:
        detail_plot.setXRange(detail_x[0], detail_x[-1], padding=0)

    if detail_hr_text is not None:
        avg_hr = calc_avg_hr(detail_x, detail_y_cleaned)
        detail_hr_text.setHtml(DETAIL_HR_HTML.format(text=format_hr_text(avg_hr)))
        position_text_relative(detail_plot, detail_hr_text)


def create_main_window():
    """Ensure a QApplication exists."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def build_plots(win, show_mean_hr=False):
    """Create four overview plots plus one detail plot."""
    curves = []

    for index in range(4):
        plot = win.addPlot(row=index, col=0)
        curve = plot.plot(pen=pg.mkPen((0, 204, 102), width=2))
        style_plot(plot, show_bottom_label=(index == 3))
        curves.append(curve)

    detail_plot = win.addPlot(row=4, col=0)
    detail_curve = detail_plot.plot(pen=pg.mkPen((200, 0, 0), width=2))
    style_plot(detail_plot)
    detail_plot.enableAutoRange(axis="y", enable=False)
    detail_plot.setYRange(DETAIL_YMIN, DETAIL_YMAX, padding=0)
    detail_plot.setLabel("bottom", f"Detail: t0 ~ t0 + {DETAIL_SEC} s", **LABEL_STYLE)

    detail_hr_text = None
    if show_mean_hr:
        detail_hr_text = pg.TextItem(anchor=(1, 0), color="k")
        detail_plot.addItem(detail_hr_text, ignoreBounds=True)

    return curves, detail_plot, detail_curve, detail_hr_text


def format_slider_timestamp(raw_time_array, start_idx):
    """Format the absolute timestamp for the current slider position."""
    if len(raw_time_array) == 0:
        return "--"

    clamped_idx = min(max(start_idx, 0), len(raw_time_array) - 1)
    timestamp = raw_time_array[clamped_idx]
    try:
        return datetime.fromtimestamp(float(timestamp)).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return str(timestamp)


def build_window_title(file_path, column, timestamp_text):
    """Build the main window title including the current slider timestamp."""
    return f"Captain ECG Viewer: {file_path} [{column}] | t0: {timestamp_text}"


def main():
    args = parse_args()
    df = read_ecg_df(args.ecg_csv)

    raw_time_array = df["time"].to_numpy()
    time_array, ecg_array = get_signal_columns(df, args.column)
    time_array = time_array - time_array[0]

    window_size = int(WINDOW_SEC * FS)
    detail_window_size = int(DETAIL_SEC * FS)
    max_start = max(0, len(ecg_array) - 4 * window_size)

    app = create_main_window()

    win = pg.GraphicsLayoutWidget()
    win.setBackground("w")

    curves, detail_plot, detail_curve, detail_hr_text = build_plots(win, show_mean_hr=args.meanhr)

    slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    slider.setMinimum(0)
    slider.setMaximum(max_start)
    slider.setValue(0)

    # Initialize overview rows with four consecutive windows starting at t0.
    for index, curve in enumerate(curves):
        start_idx = index * window_size
        update_curve(curve, time_array, ecg_array, start_idx, window_size)

    update_detail_plot(
        detail_plot,
        detail_curve,
        detail_hr_text,
        time_array,
        ecg_array,
        0,
        detail_window_size,
    )

    container = QtWidgets.QWidget()

    def update_window_title(t0):
        container.setWindowTitle(
            build_window_title(
                args.ecg_csv,
                args.column,
                format_slider_timestamp(raw_time_array, t0),
            )
        )

    def on_slider_change(t0):
        """Update all plots when the global start index changes."""
        for index, curve in enumerate(curves):
            start_idx = t0 + index * window_size
            update_curve(curve, time_array, ecg_array, start_idx, window_size)

        update_detail_plot(
            detail_plot,
            detail_curve,
            detail_hr_text,
            time_array,
            ecg_array,
            t0,
            detail_window_size,
        )
        update_window_title(t0)

    slider.valueChanged.connect(on_slider_change)

    layout = QtWidgets.QVBoxLayout()
    layout.addWidget(win)
    layout.addWidget(slider)

    container.setLayout(layout)
    container.setStyleSheet("background-color: white;")
    update_window_title(0)
    container.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
