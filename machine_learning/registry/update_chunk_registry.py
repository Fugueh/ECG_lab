import re
import pandas as pd
from pathlib import Path


base_paths = {
    "registry": Path("E:/ECG_data/250hz/registry"),
    "raw_record": Path("E:/ECG_data/250hz/records/raw_record"),
    "clean_record": Path("E:/ECG_data/250hz/records/clean_record"),
    "raw_chunk": Path("E:/ECG_data/250hz/chunks/raw_chunk"),
    "clean_chunk": Path("E:/ECG_data/250hz/chunks/clean_chunk"),
}


def get_parquet_path(key, record_id):
    path = base_paths[key] / f"{key}_{record_id}.parquet"
    return path if path.exists() else None

raw_chunks_paths = sorted(base_paths["raw_chunk"].glob("raw_chunks*.parquet"))

cols = [
    "record_id",
    "chunk_idx",
    "begin_idx",
    "end_idx",
    "begin_time",
    "end_time"
]

if __name__ == '__main__':
    dfs = []
    for chunks_file in raw_chunks_paths:
        df = pd.read_parquet(chunks_file, columns=cols)
        df["chunk_path"] = chunks_file
        dfs.append(df)
        print(re.search(r"\d{4}-\d{2}-\d{2}_\d{6}", chunks_file.name).group())
    chunk_registry = pd.concat(dfs, ignore_index=True)
    chunk_registry_path = base_paths["registry"] / "chunk_registry.csv"
    chunk_registry.to_csv(chunk_registry_path)