import numpy as np
import serial, queue
from collections import deque
import time

# ---------- 串口配置 ----------
fs = 50
time_window = 7
WINDOW = time_window * fs
SERIAL_PORT = "COM3"
BAUD = 115200 

#ser = serial.Serial(SERIAL_PORT, BAUD, timeout=1)
ser = serial.Serial(SERIAL_PORT, BAUD, timeout=0) 
data_q = queue.Queue(maxsize=2000)

timestamps = np.linspace(time.time() - time_window, time.time(), WINDOW)
data = np.zeros(WINDOW)
lead_data = np.zeros(WINDOW)

rr_buf = deque(maxlen=int(5*60*4))
beat_count = 0

