import queue
import time
from collections import deque

import numpy as np
import serial

from ecg_lab.config import get_monitor_settings


monitor_settings = get_monitor_settings()

# ---------- Serial configuration ----------
fs = monitor_settings.fs
time_window = monitor_settings.time_window
WINDOW = monitor_settings.window
SERIAL_PORT = monitor_settings.serial_port
BAUD = monitor_settings.baud

# ser = serial.Serial(SERIAL_PORT, BAUD, timeout=1)
ser = serial.Serial(SERIAL_PORT, BAUD, timeout=0)
data_q = queue.Queue(maxsize=2000)

timestamps = np.linspace(time.time() - time_window, time.time(), WINDOW)
data = np.zeros(WINDOW)
lead_data = np.zeros(WINDOW)

rr_buf = deque(maxlen=int(5 * 60 * 4))
beat_count = 0
