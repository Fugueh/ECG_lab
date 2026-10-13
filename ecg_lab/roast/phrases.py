from __future__ import annotations


def hrv_roast(rmssd) -> str:
    """按 RMSSD 给一句 HRV 评语（和 RoastMonitor.hr_roast 的心率评语配对）"""
    if rmssd is None:
        return "HRV 还在攒"
    elif rmssd < 20:
        return "弦都快崩断了"
    elif rmssd < 35:
        return "绷得挺紧啊"
    elif rmssd < 50:
        return "还剩点弹性"
    elif rmssd < 80:
        return "松弛感拿捏了"
    else:
        return "松得像没睡醒"
