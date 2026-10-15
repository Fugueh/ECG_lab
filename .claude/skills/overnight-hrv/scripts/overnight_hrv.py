"""ADS1292R overnight record -> HRV, Poincare plot, rhythm screening.

Usage (ecg_env):
    python overnight_hrv.py RAW.parquet [--out DIR] [--fs 250] [--tz Asia/Shanghai]

Input parquet columns: time (unix s), ecg, hr, rr (device HR / resp rate; resp optional).
Writes into DIR: report.json, rr.csv, hrv_5min.csv, rhythm_windows.csv, candidates.csv,
poincare.png, tachogram.png, strips_XX.png, zoom_candidates.png
"""
import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Ellipse
from scipy.interpolate import CubicSpline
from scipy.signal import welch
import neurokit2 as nk

warnings.filterwarnings("ignore")

ap = argparse.ArgumentParser()
ap.add_argument("raw")
ap.add_argument("--out")
ap.add_argument("--fs", type=int, default=250)
ap.add_argument("--tz", default="Asia/Shanghai")
args = ap.parse_args()
RAW = Path(args.raw)
FS, TZ = args.fs, args.tz
rec_id = RAW.stem.replace("raw_record_ecgresp_", "").replace("raw_record_", "")
OUT = Path(args.out) if args.out else Path("playground") / f"overnight_hrv_{rec_id}"
OUT.mkdir(parents=True, exist_ok=True)
report = {"record": RAW.name, "out": str(OUT)}


def to_clock(sec):
    return pd.to_datetime(sec, unit="s", utc=True).tz_convert(TZ).tz_localize(None)


# ============ 1. load, mask lead-off / motion =============================================
df = pd.read_parquet(RAW)
ecg = df.ecg.to_numpy(float)
n = len(ecg)
t0 = float(df.time.iloc[0])
dur = float(df.time.iloc[-1] - t0)
report["start"] = str(to_clock(t0))
report["end"] = str(to_clock(df.time.iloc[-1]))
report["duration_h"] = round(dur / 3600, 3)
report["effective_fs"] = round(n / dur, 2)
if "packet_seq" in df:
    ps = df.packet_seq.to_numpy()
    seqs = ps[np.r_[True, ps[1:] != ps[:-1]]]
    step = np.diff(seqs) % 256
    report["lost_packets"] = int((step[step > 1] - 1).sum())
gaps = np.diff(df.time.to_numpy())
report["time_gaps_gt1s"] = int((gaps > 1).sum())

BLK = FS * 10
nb = n // BLK
blk = ecg[: nb * BLK].reshape(nb, BLK)
std = blk.std(1)
if {"hr", "rr"} <= set(df.columns):
    dhr = df.hr.to_numpy()[: nb * BLK].reshape(nb, BLK).mean(1)
    drr = df.rr.to_numpy()[: nb * BLK].reshape(nb, BLK).mean(1)
    devflag = (dhr >= 130) & (drr == 0)  # ADS1292R firmware lead-off signature
else:
    devflag = np.zeros(nb, bool)
ref = np.median(std[~devflag]) if (~devflag).any() else np.median(std)
leadoff = devflag | (std < 0.15 * ref)  # flat / railed
motion = (~leadoff) & (std > 5 * np.median(std[~leadoff]))
bad = leadoff | motion
bad = bad | np.r_[False, bad[:-1]] | np.r_[bad[1:], False]  # dilate +-10 s
good = np.r_[np.repeat(~bad, BLK), np.zeros(n - nb * BLK, bool)]
blk_clock = to_clock(t0 + np.arange(nb) * 10)


def runs(mask):
    d = np.diff(np.r_[0, mask.astype(int), 0])
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


# merge lead-off runs separated by <= 30 s for reporting
lo_runs = []
for a, b in runs(leadoff):
    if lo_runs and a - lo_runs[-1][1] <= 3:
        lo_runs[-1] = (lo_runs[-1][0], b)
    else:
        lo_runs.append((a, b))
report["leadoff"] = [dict(start=blk_clock[a].strftime("%H:%M:%S"),
                          end=blk_clock[min(b, nb - 1)].strftime("%H:%M:%S"),
                          minutes=round((b - a) / 6, 1)) for a, b in lo_runs if b - a >= 3]
report["leadoff_total_min"] = round(leadoff.sum() / 6, 1)
report["motion_blocks_10s"] = int(motion.sum())
report["usable_h"] = round(good.sum() / FS / 3600, 2)

# ============ 2. clean + R peaks + kubios artifact classes ================================
clean = nk.ecg_clean(ecg, sampling_rate=FS, method="neurokit")
clean[~good] = 0.0
_, inverted = nk.ecg_invert(clean[good][: FS * 600], sampling_rate=FS)
if inverted:
    clean = -clean
report["inverted"] = bool(inverted)

peaks, seg_id = [], []
art = {k: [] for k in ("ectopic", "missed", "extra", "longshort")}
for sid, (a, b) in enumerate(runs(good)):
    if b - a < FS * 30:
        continue
    _, info = nk.ecg_peaks(clean[a:b], sampling_rate=FS, method="neurokit", correct_artifacts=False)
    pk = np.asarray(info["ECG_R_Peaks"])
    if len(pk) < 10:
        continue
    artifacts, _ = nk.signal_fixpeaks(pk, sampling_rate=FS, method="kubios", iterative=False)
    off = sum(len(p) for p in peaks)
    for k in art:
        art[k].extend(np.asarray(artifacts[k], int) + off)
    peaks.append(pk + a)
    seg_id.append(np.full(len(pk), sid))
peaks = np.concatenate(peaks)
seg = np.concatenate(seg_id)
N = len(peaks)
report["beats"] = N
report["kubios_flags"] = {k: len(v) for k, v in art.items()}

# ============ 3. RR / NN ===================================================================
rr = np.r_[np.nan, np.diff(peaks) / FS * 1000]
rr[np.r_[True, seg[1:] != seg[:-1]]] = np.nan
flag = np.zeros(N, bool)
for k in art:
    idx = np.array(art[k], int)
    if len(idx):
        flag[idx] = True
        flag[np.clip(idx + 1, 0, N - 1)] = True
nn_ok = np.isfinite(rr) & ~flag & (rr > 300) & (rr < 2000)
tsec = peaks / FS
bclock = to_clock(t0 + tsec)
report["nn_kept_pct"] = round(100 * nn_ok.sum() / np.isfinite(rr).sum(), 1)
pd.DataFrame({"clock": bclock.strftime("%H:%M:%S.%f").str[:-3], "seg": seg, "rr_ms": rr,
              "flag": flag, "nn_ok": nn_ok}).to_csv(OUT / "rr.csv", index=False)


def time_dom(x):
    succ = np.diff(x)
    sd1 = np.sqrt(0.5) * succ.std(ddof=1)
    return dict(meanNN=x.mean(), HR=60000 / x.mean(), SDNN=x.std(ddof=1),
                RMSSD=np.sqrt(np.mean(succ ** 2)), pNN50=100 * np.mean(np.abs(succ) > 50),
                SD1=sd1, SD2=np.sqrt(max(2 * x.std(ddof=1) ** 2 - sd1 ** 2, 0)))


def freq_dom(tb, x):
    ti = np.arange(tb[0], tb[-1], 0.25)
    xi = CubicSpline(tb, x)(ti)
    f, p = welch(xi - xi.mean(), fs=4, nperseg=min(len(xi), 512))
    band = lambda lo, hi: np.trapezoid(p[(f >= lo) & (f < hi)], f[(f >= lo) & (f < hi)])
    lf, hf = band(0.04, 0.15), band(0.15, 0.4)
    return dict(LF=lf, HF=hf, LF_HF=lf / hf, HFnu=100 * hf / (lf + hf))


rows = []
for w0 in np.arange(0, tsec[-1], 300):
    m = (tsec >= w0) & (tsec < w0 + 300)
    ok = m & nn_ok
    if ok.sum() < 2 or rr[ok].sum() / 1000 < 240 or len(np.unique(seg[ok])) > 1:
        continue
    x, tb = rr[ok], tsec[ok]
    r = dict(clock=bclock[np.argmax(m)].strftime("%H:%M"), n=int(ok.sum()), **time_dom(x), **freq_dom(tb, x))
    r["DFA_a1"] = nk.fractal_dfa(x, scale=np.arange(4, 17), show=False)[0]
    r["n_flag"] = int((m & flag).sum())
    r["_t"] = bclock[np.argmax(m)] + pd.Timedelta(minutes=2.5)
    rows.append(r)
w = pd.DataFrame(rows)
w.drop(columns="_t").to_csv(OUT / "hrv_5min.csv", index=False)

nn = rr[nn_ok]
succ_nn = np.diff(rr)[nn_ok[1:] & nn_ok[:-1]]
hrv = time_dom(nn)
hrv["RMSSD"] = np.sqrt(np.mean(succ_nn ** 2))
hrv["pNN50"] = 100 * np.mean(np.abs(succ_nn) > 50)
hrv["SD1"] = np.sqrt(0.5) * succ_nn.std(ddof=1)
hrv["SD2"] = np.sqrt(2 * nn.std(ddof=1) ** 2 - hrv["SD1"] ** 2)
hrv["SD1_SD2"] = hrv["SD1"] / hrv["SD2"]
for k in ("LF_HF", "HFnu", "DFA_a1", "SDNN", "RMSSD"):
    hrv[f"w5_median_{k}"] = w[k].median()
report["hrv"] = {k: round(float(v), 3) for k, v in hrv.items()}
report["hr_5min_min"] = [round(w.HR.min(), 1), w.clock[w.HR.idxmin()]]
report["hr_5min_max"] = [round(w.HR.max(), 1), w.clock[w.HR.idxmax()]]
# deep-sleep-like (vagal) windows: HF-dominant & low DFA a1
deep = w[(w.LF_HF < 0.5) & (w.DFA_a1 < 0.75)]
report["vagal_windows"] = deep.clock.tolist()
lowhrv = w[w.RMSSD < 0.6 * w.RMSSD.median()]
report["low_hrv_windows"] = lowhrv.clock.tolist()

# ============ 4. plots: Poincare + tachogram ==============================================
pair = np.isfinite(rr[:-1]) & np.isfinite(rr[1:]) & (seg[:-1] == seg[1:])
a, b = rr[:-1][pair], rr[1:][pair]
pf = (flag[:-1] | flag[1:])[pair]
pnn = (nn_ok[:-1] & nn_ok[1:])[pair]
hh = ((tsec[1:][pair]) / 3600)
lo_, hi_ = np.nanpercentile(np.r_[a, b], [0.2, 99.8])
lim = (max(250, lo_ - 100), min(2000, hi_ + 150))
fig, ax = plt.subplots(1, 3, figsize=(18, 6.2), constrained_layout=True)
ax[0].scatter(a[~pf], b[~pf], s=2, c="0.55", alpha=0.35, lw=0, label="normal pairs")
ax[0].scatter(a[pf], b[pf], s=12, c="crimson", alpha=0.8, lw=0, label=f"flagged pairs (n={pf.sum()})")
ax[0].set_title("All RR (incl. flagged beats)"); ax[0].legend(loc="upper left", markerscale=2)
hb = ax[1].hexbin(a[pnn], b[pnn], gridsize=90, bins="log", cmap="viridis", mincnt=1, extent=(*lim, *lim))
fig.colorbar(hb, ax=ax[1], label="log count")
mu = nn.mean()
for k_, ls in ((1, "-"), (2, "--")):
    ax[1].add_patch(Ellipse((mu, mu), 2 * k_ * hrv["SD2"], 2 * k_ * hrv["SD1"], angle=45,
                            fill=False, ec="w", lw=1.4, ls=ls))
ax[1].set_title(f"NN density  SD1={hrv['SD1']:.1f}  SD2={hrv['SD2']:.1f} ms  SD1/SD2={hrv['SD1_SD2']:.2f}")
sc = ax[2].scatter(a[pnn], b[pnn], s=2, c=hh[pnn], cmap="plasma", alpha=0.5, lw=0)
fig.colorbar(sc, ax=ax[2], label="hours since start")
ax[2].set_title("NN coloured by time")
for x_ in ax:
    x_.plot(lim, lim, c="k", lw=0.6, alpha=0.5)
    x_.set(xlim=lim, ylim=lim, xlabel="RR$_n$ (ms)", ylabel="RR$_{n+1}$ (ms)", aspect="equal")
fig.suptitle(f"Poincaré — {RAW.name}  ({report['start'][:16]} → {report['end'][11:16]}, lead-off excluded)")
fig.savefig(OUT / "poincare.png", dpi=130); plt.close(fig)

fig, ax = plt.subplots(3, 1, figsize=(16, 9), sharex=True, constrained_layout=True)
bc = bclock.to_pydatetime()
fr = flag & np.isfinite(rr)
ax[0].plot(bc[nn_ok], rr[nn_ok], ".", ms=1, c="0.3")
ax[0].plot(bc[fr], rr[fr], ".", ms=4, c="crimson", label="flagged")
ax[0].set(ylabel="RR (ms)", ylim=(300, 1800)); ax[0].legend(loc="upper right")
ax[1].plot(w._t, w.HR, "o-", ms=3); ax[1].set_ylabel("HR (bpm)")
ax[2].plot(w._t, w.RMSSD, "o-", ms=3, label="RMSSD"); ax[2].plot(w._t, w.SDNN, "s-", ms=3, label="SDNN")
ax2 = ax[2].twinx(); ax2.plot(w._t, w.LF_HF, "^-", ms=3, c="tab:green", alpha=0.6, label="LF/HF")
ax2.set_ylabel("LF/HF"); ax[2].set_ylabel("ms"); ax[2].legend(loc="upper left"); ax2.legend(loc="upper right")
for x_ in ax:
    for a_, b_ in lo_runs:
        x_.axvspan(blk_clock[a_], blk_clock[min(b_, nb - 1)], color="orange", alpha=0.15)
ax[2].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax[2].set_xlabel("clock time (orange = lead-off)")
fig.savefig(OUT / "tachogram.png", dpi=110); plt.close(fig)

# ============ 5. rhythm screening ==========================================================
loc = pd.Series(rr).groupby(seg).transform(
    lambda s: s.rolling(21, center=True, min_periods=5).median()).to_numpy()
QW = int(0.12 * FS)


def beat(i):
    p = peaks[i]
    return clean[p - QW:p + QW] if p - QW >= 0 and p + QW <= len(clean) else None


def width_ms(x):
    a_ = np.abs(x - np.median(x)); thr = 0.3 * a_[QW]
    l_, r_ = QW, QW
    while l_ > 0 and a_[l_] > thr: l_ -= 1
    while r_ < len(a_) - 1 and a_[r_] > thr: r_ += 1
    return (r_ - l_) / FS * 1000


cand = []
for i in range(2, N - 2):
    if not (np.isfinite(rr[i]) and np.isfinite(rr[i + 1]) and np.isfinite(rr[i - 1]) and np.isfinite(loc[i])):
        continue
    # abrupt (vs previous beat AND local median) and followed by a longer interval;
    # gradual sinus accelerations (arousals) fail the first or last test
    if not (rr[i] < 0.8 * loc[i] and rr[i] < 0.8 * rr[i - 1] and rr[i + 1] > 1.15 * rr[i]):
        continue
    nb_ = [j for j in range(max(1, i - 20), min(N, i + 20))
           if j != i and seg[j] == seg[i] and np.isfinite(rr[j]) and abs(rr[j] - loc[j]) < 0.15 * loc[j]]
    bs = [x for x in (beat(j) for j in nb_) if x is not None]
    x = beat(i)
    if x is None or len(bs) < 5:
        continue
    tpl = np.median(bs, 0)
    corr = np.corrcoef(x, tpl)[0, 1]
    ctx = [beat(j) for j in (i - 2, i - 1, i + 1, i + 2)]
    ctx_corr = np.mean([np.corrcoef(c_, tpl)[0, 1] for c_ in ctx if c_ is not None])
    # refractory test: an undetected R-like spike 150 ms after the candidate that keeps the
    # sinus rhythm regular means the candidate is not a beat (ventricles would be refractory)
    p, pn, pp = peaks[i], peaks[i + 1], peaks[i - 1]
    hidden = False
    if pn - p > int(0.3 * FS):
        s0 = p + int(0.15 * FS)
        q = s0 + int(np.argmax(clean[s0:pn - int(0.15 * FS)]))
        L = rr[i - 1] / 1000 * FS  # current sinus cycle; local median lags during HR drifts
        rpk_amp = np.median(clean[peaks[nb_]])
        hidden = (clean[q] > 0.6 * rpk_amp and abs((q - pp) - L) < 0.15 * L and abs((pn - q) - L) < 0.15 * L)
    cand.append(dict(i=i, clock=bclock[i].strftime("%H:%M:%S.%f")[:-3], rr_prev=rr[i - 1], rr_pre=rr[i],
                     rr_post=rr[i + 1], loc_med=loc[i], prematurity=rr[i] / loc[i],
                     sum_ratio=(rr[i] + rr[i + 1]) / loc[i], corr=corr, ctx_corr=ctx_corr,
                     amp_ratio=np.ptp(x) / np.ptp(tpl), w_beat=width_ms(x), w_tpl=width_ms(tpl),
                     hidden_regular_beat=hidden))
c = pd.DataFrame(cand)


def classify(r):
    if r.sum_ratio < 1.25:
        return "artifact: extra detection"
    if r.hidden_regular_beat:
        return "artifact: rhythm uninterrupted"
    if r.ctx_corr < 0.85:
        return "artifact?: noisy context"
    if r["corr"] < 0.8 or r.w_beat > r.w_tpl + 40:
        return "PVC-like (aberrant QRS)"
    return "PAC-like (normal QRS)"


if len(c):
    c["auto_class"] = c.apply(classify, axis=1)
c.to_csv(OUT / "candidates.csv", index=False)
report["premature_candidates"] = c.auto_class.value_counts().to_dict() if len(c) else {}

report["max_rr_ms"] = [float(np.nanmax(rr)), bclock[np.nanargmax(rr)].strftime("%H:%M:%S")]
report["pauses_gt2s"] = int(np.sum(rr > 2000))
hr10 = 60000 / pd.Series(rr).rolling(10).mean()
report["hr10_min"] = [round(hr10.min(), 1), bclock[hr10.idxmin()].strftime("%H:%M:%S")]
report["hr10_max"] = [round(hr10.max(), 1), bclock[hr10.idxmax()].strftime("%H:%M:%S")]
report["brady_lt45_beats"] = int((hr10 < 45).sum())
tachy = hr10 > 100
report["tachy_gt100_episodes"] = [bclock[a_].strftime("%H:%M:%S") + f" ({b_ - a_} beats)"
                                  for a_, b_ in runs(tachy.to_numpy())]

excl = np.zeros(N, bool)
if len(c):
    excl[c.i.to_numpy()] = True; excl[np.clip(c.i.to_numpy() + 1, 0, N - 1)] = True
wr = []
for w0 in np.arange(0, tsec[-1], 120):
    m = (tsec >= w0) & (tsec < w0 + 120) & np.isfinite(rr) & ~excl
    if m.sum() < 60 or len(np.unique(seg[m])) > 1:
        continue
    x = rr[m]
    nrmssd = np.sqrt(np.mean(np.diff(x) ** 2)) / x.mean()
    h_, _ = np.histogram(x, bins=16); p_ = h_[h_ > 0] / h_.sum()
    se = -np.sum(p_ * np.log(p_)) / np.log(16)
    tp = np.mean((x[1:-1] - x[:-2]) * (x[1:-1] - x[2:]) > 0)
    wr.append(dict(clock=bclock[np.argmax(m)].strftime("%H:%M"), n=int(m.sum()), nRMSSD=nrmssd, ShE=se, TPR=tp,
                   af_like=bool((nrmssd > 0.1) & (se > 0.7) & (abs(tp - 0.667) < 0.1))))
wr = pd.DataFrame(wr)
wr.to_csv(OUT / "rhythm_windows.csv", index=False)
report["af_windows"] = f"{int(wr.af_like.sum())}/{len(wr)}"
report["irregular_not_af_windows"] = wr[(wr.nRMSSD > 0.1) & ~wr.af_like].clock.tolist()

# strips (8 s) for every candidate, 12 per page
for old in OUT.glob("strips_*.png"):
    old.unlink()
per = 12
for pg in range(int(np.ceil(len(c) / per))):
    sub = c.iloc[pg * per:(pg + 1) * per]
    fig, ax = plt.subplots(len(sub), 1, figsize=(16, 1.7 * len(sub)), constrained_layout=True, squeeze=False)
    for a_, (_, r) in zip(ax[:, 0], sub.iterrows()):
        p = peaks[r.i]; lo, hi = p - 4 * FS, p + 4 * FS
        a_.plot(np.arange(lo, hi) / FS - p / FS, clean[lo:hi], lw=0.7, c="k")
        pk = peaks[(peaks >= lo) & (peaks < hi)]
        a_.plot((pk - p) / FS, clean[pk], "o", ms=3, c="tab:blue")
        a_.plot(0, clean[p], "o", ms=6, c="crimson")
        a_.set_title(f"#{r.i} {r.clock}  RR {r.rr_prev:.0f}/{r.rr_pre:.0f}->{r.rr_post:.0f} (med {r.loc_med:.0f})  "
                     f"sum/med {r.sum_ratio:.2f}  corr {r['corr']:.2f} ctx {r.ctx_corr:.2f}  "
                     f"w {r.w_beat:.0f}/{r.w_tpl:.0f} ms  -> {r.auto_class}", fontsize=8, loc="left")
        a_.set_yticks([]); a_.set_xlim(-4, 4)
    fig.savefig(OUT / f"strips_{pg:02d}.png", dpi=90); plt.close(fig)

# zoom (4 s, grid) on candidates not already explained as artifacts
z = c[~c.auto_class.str.startswith("artifact")] if len(c) else c
if (OUT / "zoom_candidates.png").exists():
    (OUT / "zoom_candidates.png").unlink()
if len(z):
    z = z.head(10)
    fig, ax = plt.subplots(len(z), 1, figsize=(15, 3 * len(z)), constrained_layout=True, squeeze=False)
    for a_, (_, r) in zip(ax[:, 0], z.iterrows()):
        p = peaks[r.i]; lo, hi = p - int(2.5 * FS), p + int(1.5 * FS)
        a_.plot(np.arange(lo, hi) / FS - p / FS, clean[lo:hi], c="k", lw=0.9)
        for q in peaks[(peaks >= lo) & (peaks < hi)]:
            a_.axvline((q - p) / FS, c="tab:blue", lw=0.5, alpha=0.5)
        a_.axvline(0, c="crimson", lw=1)
        a_.set_xticks(np.arange(-2.5, 1.51, 0.2)); a_.grid(alpha=0.3)
        a_.set_title(f"#{r.i} {r.clock}  {r.auto_class}", loc="left")
    fig.savefig(OUT / "zoom_candidates.png", dpi=95); plt.close(fig)

(OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
pd.set_option("display.width", 250)
if len(c):
    print(c.drop(columns=["amp_ratio"]).round(2).to_string())
