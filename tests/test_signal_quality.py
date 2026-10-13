import numpy as np

from ecg_lab.roast.signal_quality import describe_quality, score_minute


def test_score_minute_skips_short_segments():
    assert score_minute(np.zeros(100), sampling_rate=250) is None


def test_describe_quality_grades_by_score_and_bad_beats():
    good = describe_quality({"score": 0.9, "bad_beat_ratio": 0.04, "beats": 80}, 80, 0, 0)
    noisy_beats = describe_quality({"score": 0.9, "bad_beat_ratio": 0.2, "beats": 80}, 80, 0, 0)
    bad = describe_quality({"score": 0.5, "bad_beat_ratio": 0.4, "beats": 80}, 80, 0, 0)

    assert (good["label"], good["score"]) == ("A", 0.9)
    assert good["note"] == "信号 A（优）：nk2 质量 0.90，80 拍中 4% 形态走样。电极贴得比你的心态稳。"
    assert noisy_beats["label"] == "C"
    assert bad["label"] == "D"


def test_describe_quality_explains_beat_mismatch_and_rejections():
    quality = describe_quality({"score": 0.8, "bad_beat_ratio": 0.1, "beats": 83}, 70, 6, 3)

    assert quality["label"] == "B"
    assert "监视器只认了 70 拍，拒收 6 拍，脱落 3 秒" in quality["note"]


def test_describe_quality_without_score():
    lead_off = describe_quality({"score": 0.9, "bad_beat_ratio": 0.0, "beats": 30}, 30, 0, 42)
    failed = describe_quality(None, 0, 0, 0, error="没装 neurokit2")

    assert lead_off["label"] == "X"
    assert "脱落了 42 秒" in lead_off["note"]
    assert failed["label"] == "?"
    assert "没装 neurokit2" in failed["note"]
