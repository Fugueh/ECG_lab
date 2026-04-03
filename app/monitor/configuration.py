#import queue
import time
from collections import deque
import numpy as np

from dotenv import load_dotenv
from ecg_lab.config import get_repo_root, get_monitor_settings

env_path = get_repo_root() / ".env" # env at repo root
load_dotenv(dotenv_path=env_path) # load env variables
monitor_settings = get_monitor_settings() # get config

# serial and gui configuration
fs = monitor_settings.fs
time_window = monitor_settings.time_window
WINDOW = monitor_settings.window
SERIAL_PORT = monitor_settings.serial_port
BAUD = monitor_settings.baud

# data containers
timestamps = np.linspace(time.time() - time_window, time.time(), WINDOW)
data = np.zeros(WINDOW)
lead_data = np.zeros(WINDOW)

# buffer and count
#data_q = queue.Queue(maxsize=2000)
rr_buf = deque(maxlen=int(5 * 60 * 4))
beat_count = 0
