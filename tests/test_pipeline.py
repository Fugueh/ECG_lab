import numpy as np
import pandas as pd

from ecg_lab.pipeline import build_raw_chunk_table, get_record_id_from_path, split_record_into_chunks


def test_get_record_id_from_path_extracts_timestamp():
    record_id = get_record_id_from_path("raw_record_2026-03-24_003727.parquet")
    assert record_id == "2026-03-24_003727"


def test_split_record_into_chunks_drops_tail():
    frame = pd.DataFrame(
        {
            "time": np.arange(0, 12, 0.5),
            "ecg": np.arange(24),
        }
    )

    chunks = split_record_into_chunks(frame, fs=2, chunk_length_s=5)

    assert len(chunks) == 2
    assert all(len(chunk) == 10 for chunk in chunks)


def test_build_raw_chunk_table_keeps_metadata():
    chunks = [
        pd.DataFrame({"time": [0.0, 0.5, 1.0], "ecg": [1, 2, 3]}, index=[10, 11, 12]),
        pd.DataFrame({"time": [1.5, 2.0, 2.5], "ecg": [4, 5, 6]}, index=[13, 14, 15]),
    ]

    table = build_raw_chunk_table(chunks, "2026-03-24_003727")

    assert list(table["record_id"]) == ["2026-03-24_003727", "2026-03-24_003727"]
    assert list(table["chunk_idx"]) == [0, 1]
    assert table.loc[0, "begin_idx"] == 10
    assert table.loc[1, "end_time"] == 2.5
