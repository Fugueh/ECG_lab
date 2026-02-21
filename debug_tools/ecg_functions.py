import numpy as np
from scipy.signal import butter, filtfilt, iirnotch, find_peaks

# ---------- 参数区 ----------
PORT = 'COM3'        # 改成舰长的实际串口号
BAUD = 9600
FS = 100             # 采样率（Hz），与 Arduino 的 delay 对应
WINDOW = 500         # 显示窗口长度（点数）
# ----------------------------

# ----- 带通滤波器 (0.5–40 Hz) ----- 
b, a = butter(2, [0.5/(FS/2), 40/(FS/2)], btype='band')
b_notch, a_notch = iirnotch(50.0 / (FS / 2), 30.0)

def prcs_filtered(b, a, b_notch, a_notch, data):
    filtered = filtfilt(b, a, data)                # 带通
    filtered = filtfilt(b_notch, a_notch, filtered)  # 陷波
    #filtered = medfilt(filtered, kernel_size=3)    # 中值
    b_hp, a_hp = butter(1, 0.7/(FS/2), 'highpass') # 高通去漂移
    filtered = filtfilt(b_hp, a_hp, filtered)
    return filtered
# -----------------------------

# ---------- 工具函数 ----------
def text_color(hr):
    if hr < 50:
        return (0, 180, 255)
    elif hr < 100:
        return (0, 255, 0)
    elif hr < 120:
        return (255, 255, 0)
    else:
        return (248, 47, 0)


def detect_r_peaks(filtered, fs=50):
    """
    简化版 Pan–Tompkins R峰检测
    适用于低采样率 (~50Hz) 的 AD8232 ECG 信号
    ----------------------------------------------------
    参数：
        filtered : np.array   # 已带通滤波的 ECG 信号
        fs       : int/float  # 采样率，默认 50 Hz
    返回：
        peaks : np.array      # 检测到的 R 峰索引
        integrated : np.array # 移动积分信号，可用于可视化
    """
    # Step 1: 一阶导数，突出R波上升沿
    diff_signal = np.diff(filtered, prepend=filtered[0])

    # Step 2: 平方放大能量
    squared = diff_signal ** 2

    # Step 3: 移动积分（窗口≈0.15秒）
    window_size = int(0.15 * fs)
    window = np.ones(window_size) / window_size
    integrated = np.convolve(squared, window, mode='same')

    # Step 4: 动态阈值 + 峰宽判别
    # prominence ~ 峰的“显著性”，可以根据数据噪声调整
    mean_level = np.mean(integrated)
    peaks, _ = find_peaks(
        integrated,
        distance=int(0.25 * fs),     # 相邻心搏最短间隔 ≈0.25s（240 bpm）
        prominence=1.2 * mean_level  # 动态阈值，抑制噪声峰
    )

    return peaks, integrated


def simple_peaks(data, threshold=100, distance=50):
    peaks = []
    last_peak = -distance
    for i in range(1, len(data)-1):
        if data[i] > data[i-1] and data[i] > data[i+1] and data[i] > threshold:
            if i - last_peak > distance:
                peaks.append(i)
                last_peak = i
    return np.array(peaks)




class ECGData(object):
    def __init__(self, data):
        self.peaks = get_peaks(data['ecg'])
        self.rr_intervals = np.diff(data['time'].loc[self.peaks])
        self.hr = 60 / self.rr_intervals