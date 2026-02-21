import numpy as np
import pandas as pd
from pyqtgraph.Qt import QtWidgets, QtCore
import pyqtgraph as pg

df = pd.read_csv('ecg_data-1110.csv')
fs = 50
WINDOW = 10 * fs

app = QtWidgets.QApplication([])
win = pg.GraphicsLayoutWidget(show=True, title="Captain ECG Monitor")
win.setBackground('k')
plot = win.addPlot(title="ECG Signal (Lead I)")
curve = plot.plot(pen=pg.mkPen((0,255,0), width=1.2))

timestamps = np.linspace(df.loc[0,'time'] - 10, df.loc[0,'time'], WINDOW)
data = np.zeros(WINDOW)

gen = ((df.loc[i,'time'], df.loc[i,'ecg']) for i in df.index)

def update():
    global timestamps, data
    try:
        timestamp, val = next(gen)
    except StopIteration:
        return
    timestamps = np.append(timestamps, timestamp)[-WINDOW:]
    data = np.append(data, val)[-WINDOW:]
    t_rel = timestamps - timestamps[-1]
    curve.setData(t_rel, data)

# 每 20ms 取一个点 = 50 Hz
timer = QtCore.QTimer()
timer.timeout.connect(update)
timer.start(int(1000/fs))

app.exec_()