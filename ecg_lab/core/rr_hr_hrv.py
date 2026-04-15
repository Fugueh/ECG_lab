import datetime
import time

import numpy as np
import pandas as pd
from scipy.signal import find_peaks


def get_dtime(timestamp):
    dt_object = datetime.datetime.fromtimestamp(timestamp)
    return dt_object.strftime("%Y-%m-%d %H:%M:%S")


def get_dtime_nospace(timestamp):
    dt_object = datetime.datetime.fromtimestamp(timestamp)
    return dt_object.strftime("%Y%m%d%H%M%S")


class BeatCalc:
    def __init__(self, df):
        ecg = df["ecg"].values
        time_values = df["time"].values
        dt = np.diff(time_values)

        self.df = df
        self.n_samples = len(df)
        self.fs = 1 / np.median(dt)
        self.duration = time_values[-1] - time_values[0]
        self.begin_time = self.df.time.values[0]
        self.end_time = self.df.time.values[-1]

        distance = int(self.fs * 60 / 200)
        self.peaks, _ = find_peaks(ecg, height=450, distance=distance)
        self.n_beats = len(self.peaks)
        self.r_series = time_values[self.peaks]
        self.rr_intervals = np.diff(self.r_series)
        self.rr_s, self.rr_clean = self.get_clean_rr()
        self.hr, self.sdnn, self.rmssd = self.calc_hrv()

    def get_clean_rr(self):
        rr = self.rr_intervals.copy()
        t_rr = self.r_series[1:]
        rr_s = pd.Series(rr, index=t_rr, dtype=float)

        rr_s[(rr_s < 0.50) | (rr_s > 2.00)] = np.nan

        drr = rr_s.diff().abs()
        rr_s[drr > 0.20] = np.nan
        rel = (rr_s.diff().abs() / rr_s.shift(1)).abs()
        rr_s[rel > 0.25] = np.nan

        rr_clean = rr_s.interpolate(limit=3).dropna()
        return rr_s, rr_clean

    def calc_hrv(self):
        if len(self.rr_clean) > 0:
            hr = 60 / np.mean(self.rr_clean)
            sdnn = np.std(self.rr_clean * 1000, ddof=1)
            rmssd = np.sqrt(np.mean(np.diff(self.rr_clean * 1000) ** 2))
        else:
            hr = np.nan
            sdnn = np.nan
            rmssd = np.nan
        return hr, sdnn, rmssd

    def ecg_info(self):
        formatted_duration = time.strftime("%H:%M:%S", time.gmtime(self.duration))
        begin_dtime = get_dtime(self.begin_time)
        end_dtime = get_dtime(self.end_time)

        info_text = (
            f"{begin_dtime} - {end_dtime}  |  {formatted_duration}\n"
            f"Samples: {self.n_samples}  |  fs: {self.fs:.2f} Hz  |  Beats: {self.n_beats}\n"
            f"Mean HR: {self.hr:.0f} bpm  |  SDNN: {int(self.sdnn)} ms  |  RMSSD: {int(self.rmssd)} ms"
        )
        return info_text


class BeatCalcFS:
    def __init__(self, df, ecg, fs):
        self.ecg = df[ecg]
        self.fs = fs
        distance = int(self.fs * 60 / 200)
        self.peaks, _ = find_peaks(self.ecg, height=450, distance=distance)
        self.rr_intervals = np.diff(self.peaks) / self.fs


def random_time_slice(df, s, time_col="time", seed=None):
    """Randomly slice a dataframe into a sub-window of s seconds."""
    if seed is not None:
        np.random.seed(seed)

    t = df[time_col].to_numpy()
    t_min = t.min()
    t_max = t.max()

    if (t_max - t_min) < s:
        raise ValueError("Data duration is shorter than the requested slice length.")

    t_start = np.random.uniform(t_min, t_max - s)
    t_end = t_start + s
    mask = (t >= t_start) & (t < t_end)
    slice_df = df.loc[mask].copy()
    return slice_df, t_start, t_end
