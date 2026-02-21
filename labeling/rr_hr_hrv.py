import pandas as pd
import numpy as np
from scipy.signal import find_peaks

class BeatCalc:
    def __init__(self, df):
        ecg = df["ecg"].values
        time = df["time"].values
        dt = np.diff(time)

        self.df = df
        self.n_samples = len(df)
        self.fs = 1 / np.median(dt)
        self.duration = time[-1] - time[0]

        self.peaks, _ = find_peaks(ecg, height=350, distance=20)
        self.n_beats = len(self.peaks)
        self.r_series = time[self.peaks]
        self.rr_intervals = np.diff(self.r_series)

        if len(self.rr_intervals) > 0:
            self.hr = 60 / np.mean(self.rr_intervals)
        else:
            self.hr = np.nan

    def show_ecg_info(self):
        total_seconds = int(self.duration)
        h, remainder = divmod(total_seconds, 3600)
        m, s = divmod(remainder, 60)

        print(f"Duration: {h} h {m} m {s} s.")
        print(f"Samples: {self.n_samples}")
        print(f"Beats: {self.n_beats}")
        print(f"Estimated sampling rate: {self.fs:.2f} Hz")
        print(f"Mean HR: {self.hr:.2f} bpm")

    
