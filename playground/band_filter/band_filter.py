import numpy as np
import matplotlib.pyplot as plt
from scipy import signal


# =========================
# 0. 准备数据
# =========================
fs = 250  # 采样率，单位 Hz
t = np.arange(0, 10, 1/fs)  # 10 秒时间轴

# ------- 方案A：如果你有自己的真实 ECG，就替换这里 -------
# ecg = your_ecg_array

# ------- 方案B：先构造一个“脏”的模拟 ECG 用来实验 -------
# 基础低频心电样波（不是严格生理模型，只用于演示）
clean_ecg = (
    0.05 * np.sin(2 * np.pi * 1.2 * t) +
    0.6 * np.sin(2 * np.pi * 1.2 * t) ** 15
)

baseline_drift = 0.25 * np.sin(2 * np.pi * 0.2 * t)       # 基线漂移，0.2 Hz
powerline_noise = 0.08 * np.sin(2 * np.pi * 50 * t)       # 工频噪声，50 Hz
muscle_noise = 0.04 * np.random.randn(len(t))             # 高频随机噪声

ecg = clean_ecg + baseline_drift + powerline_noise + muscle_noise


# =========================
# 1. 工具函数
# =========================
def plot_signal(x, fs, title, start_sec=0, end_sec=5):
    """画时间域波形"""
    n0 = int(start_sec * fs)
    n1 = int(end_sec * fs)
    tt = np.arange(len(x)) / fs
    plt.figure(figsize=(12, 4))
    plt.plot(tt[n0:n1], x[n0:n1])
    plt.xlabel("Time (s)")
    plt.ylabel("Amplitude")
    plt.title(title)
    plt.grid(True)
    plt.tight_layout()
    plt.show()


def plot_spectrum(x, fs, title):
    """画幅度谱，帮助理解滤波前后频率成分"""
    freqs = np.fft.rfftfreq(len(x), d=1/fs)
    fft_mag = np.abs(np.fft.rfft(x))
    plt.figure(figsize=(12, 4))
    plt.plot(freqs, fft_mag)
    plt.xlabel("Frequency (Hz)")
    plt.ylabel("Magnitude")
    plt.title(title)
    plt.xlim(0, 80)
    plt.grid(True)
    plt.tight_layout()
    plt.show()


def design_butter_filter(fs, cutoff, btype, order=4):
    """
    设计 Butterworth（巴特沃斯）滤波器
    cutoff:
        高通/低通时传 float，例如 0.5 或 40
        带通时传 tuple/list，例如 (0.5, 40)
    btype: 'lowpass', 'highpass', 'bandpass'
    """
    nyq = 0.5 * fs
    if isinstance(cutoff, (tuple, list)):
        wn = [c / nyq for c in cutoff]
    else:
        wn = cutoff / nyq

    b, a = signal.butter(order, wn, btype=btype)
    return b, a


def apply_zero_phase_filter(x, b, a):
    """
    零相位滤波：先正向，再反向。
    优点：不会把 R 峰整体拖后。
    缺点：只能离线用，不适合严格实时。
    """
    return signal.filtfilt(b, a, x)


def notch_filter(x, fs, f0=50.0, Q=30):
    """
    陷波滤波器（notch）
    f0: 要抑制的中心频率，比如 50 Hz
    Q: 品质因数，越大越窄
    """
    b, a = signal.iirnotch(w0=f0, Q=Q, fs=fs)
    y = signal.filtfilt(b, a, x)
    return y


def moving_average(x, window_size):
    """
    移动平均，主要用于演示“平滑”效果。
    ECG 里不建议拿它当主力预处理，因为会抹钝波形。
    """
    kernel = np.ones(window_size) / window_size
    return np.convolve(x, kernel, mode='same')


# =========================
# 2. 看原始信号
# =========================
plot_signal(ecg, fs, "Raw ECG (time domain)")
plot_spectrum(ecg, fs, "Raw ECG (spectrum)")


# =========================
# 3. 高通滤波：去基线漂移
# =========================
b_hp, a_hp = design_butter_filter(fs, cutoff=0.5, btype='highpass', order=4)
ecg_hp = apply_zero_phase_filter(ecg, b_hp, a_hp)

plot_signal(ecg_hp, fs, "After high-pass filter (0.5 Hz)")
plot_spectrum(ecg_hp, fs, "Spectrum after high-pass filter")


# =========================
# 4. 低通滤波：去高频噪声
# =========================
b_lp, a_lp = design_butter_filter(fs, cutoff=40, btype='lowpass', order=4)
ecg_lp = apply_zero_phase_filter(ecg, b_lp, a_lp)

plot_signal(ecg_lp, fs, "After low-pass filter (40 Hz)")
plot_spectrum(ecg_lp, fs, "Spectrum after low-pass filter")


# =========================
# 5. 带通滤波：高通 + 低通一起做
# =========================
b_bp, a_bp = design_butter_filter(fs, cutoff=(0.5, 40), btype='bandpass', order=4)
ecg_bp = apply_zero_phase_filter(ecg, b_bp, a_bp)

plot_signal(ecg_bp, fs, "After band-pass filter (0.5 - 40 Hz)")
plot_spectrum(ecg_bp, fs, "Spectrum after band-pass filter")


# =========================
# 6. 陷波滤波：去 50 Hz 工频
# =========================
ecg_notch = notch_filter(ecg, fs, f0=50.0, Q=30)

plot_signal(ecg_notch, fs, "After notch filter (50 Hz)")
plot_spectrum(ecg_notch, fs, "Spectrum after notch filter")


# =========================
# 7. 组合处理：先带通，再陷波
# =========================
ecg_combo = notch_filter(ecg_bp, fs, f0=50.0, Q=30)

plot_signal(ecg_combo, fs, "Band-pass + Notch")
plot_spectrum(ecg_combo, fs, "Spectrum after band-pass + notch")


# =========================
# 8. 移动平均：演示“平滑会把波形抹钝”
# =========================
# 例如 5 点窗口，在 250 Hz 下相当于 5 / 250 = 0.02 秒
ecg_ma = moving_average(ecg, window_size=5)

plot_signal(ecg_ma, fs, "After moving average (window=5)")
plot_spectrum(ecg_ma, fs, "Spectrum after moving average")


# =========================
# 9. 把几种结果画在一起比较
# =========================
start_sec, end_sec = 0, 5
n0, n1 = int(start_sec * fs), int(end_sec * fs)
tt = np.arange(len(ecg)) / fs

plt.figure(figsize=(14, 8))
plt.plot(tt[n0:n1], ecg[n0:n1], label="Raw", alpha=0.7)
plt.plot(tt[n0:n1], ecg_bp[n0:n1], label="Band-pass 0.5-40 Hz", linewidth=2)
plt.plot(tt[n0:n1], ecg_combo[n0:n1], label="Band-pass + Notch", linewidth=2)
plt.plot(tt[n0:n1], ecg_ma[n0:n1], label="Moving average", alpha=0.9)
plt.xlabel("Time (s)")
plt.ylabel("Amplitude")
plt.title("Comparison of different processing methods")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()
