from __future__ import annotations

import numpy as np

MIN_SECONDS = 10
BAD_BEAT_SCORE = 0.5
LEAD_OFF_DOMINANT_S = 30

# (最低分, 走样心拍占比上限, 标签, 名称, 吐槽)
GRADES = (
    (0.85, 0.08, "A", "优", "电极贴得比你的心态稳。"),
    (0.78, 0.15, "B", "良", "基本能看，偶尔手欠。"),
    (0.65, 0.30, "C", "凑合", "波形有点糊，你是不是在抖腿？"),
)
WORST_GRADE = ("D", "差", "这波形像在蹦迪，电极还好吗？")


def score_minute(samples, sampling_rate: int = 250) -> dict | None:
    """用 NeuroKit2 的 averageQRS 给一段原始 ECG 打分；数据太短时返回 None。

    averageQRS 衡量的是每一拍和这段信号平均心拍的相似度（0-1），
    反映形态一致性，不是绝对噪声水平。
    """
    signal = np.asarray(samples, dtype=float)
    if len(signal) < MIN_SECONDS * sampling_rate:
        return None

    import neurokit2 as nk

    cleaned = nk.ecg_clean(signal, sampling_rate=sampling_rate)
    _, info = nk.ecg_peaks(cleaned, sampling_rate=sampling_rate)
    rpeaks = info["ECG_R_Peaks"]
    quality = nk.ecg_quality(cleaned, rpeaks=rpeaks, sampling_rate=sampling_rate, method="averageQRS")
    beat_quality = quality[rpeaks]
    return {
        "score": float(np.mean(quality)),
        "bad_beat_ratio": float(np.mean(beat_quality < BAD_BEAT_SCORE)),
        "beats": int(len(rpeaks)),
        "rr_s": (np.diff(rpeaks) / sampling_rate).tolist(),
    }


def _grade(score: float, bad_ratio: float):
    for min_score, max_bad_ratio, label, name, quip in GRADES:
        if score >= min_score and bad_ratio <= max_bad_ratio:
            return label, name, quip
    return WORST_GRADE


def grade_label(score: float, bad_ratio: float) -> str:
    """只要标签（A/B/C/D），不要解释和吐槽"""
    return _grade(score, bad_ratio)[0]


def describe_quality(metrics: dict | None, beats_ok: int, beats_rejected: int, lead_off_s: float, error: str | None = None) -> dict:
    """把评分变成标签 + 自然语言解释（含吐槽）。"""
    if lead_off_s >= LEAD_OFF_DOMINANT_S:
        return {
            "label": "X",
            "score": None,
            "note": f"信号 X（脱落）：这一分钟导联脱落了 {lead_off_s:.0f} 秒。电极比你先下班。",
        }
    if metrics is None:
        reason = error or "数据不够一段完整的评估"
        return {"label": "?", "score": None, "note": f"信号 ?（没法评）：{reason}。烂到 nk2 都不肯打分。"}

    score = metrics["score"]
    bad_ratio = metrics["bad_beat_ratio"]
    label, name, quip = _grade(score, bad_ratio)

    reasons = [f"nk2 质量 {score:.2f}", f"{metrics['beats']} 拍中 {bad_ratio:.0%} 形态走样"]
    if abs(metrics["beats"] - beats_ok) >= 5:
        reasons.append(f"监视器只认了 {beats_ok} 拍")
    if beats_rejected:
        reasons.append(f"拒收 {beats_rejected} 拍")
    if lead_off_s >= 1:
        reasons.append(f"脱落 {lead_off_s:.0f} 秒")

    return {
        "label": label,
        "score": round(score, 2),
        "note": f"信号 {label}（{name}）：{'，'.join(reasons)}。{quip}",
    }
