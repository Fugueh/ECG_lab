from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from ecg_lab.core.rr_hr_hrv import get_dtime

from .config import DataPaths


LOGGER = logging.getLogger(__name__)
RECORD_ID_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}_\d{6}")


ECG_INFO_COLUMNS = [
    "record_id",
    "method_peaks",
    "method_fixpeaks",
    "ECG_R_Peaks",
    "ECG_R_Peaks_Uncorrected",
    "ECG_fixpeaks_ectopic",
    "ECG_fixpeaks_missed",
    "ECG_fixpeaks_extra",
    "ECG_fixpeaks_longshort",
    "ECG_fixpeaks_method",
    "ECG_fixpeaks_rr",
    "ECG_fixpeaks_drrs",
    "ECG_fixpeaks_mrrs",
    "ECG_fixpeaks_s12",
    "ECG_fixpeaks_s22",
    "ECG_fixpeaks_c1",
    "ECG_fixpeaks_c2",
    "sampling_rate",
    "ECG_P_Peaks",
    "ECG_P_Onsets",
    "ECG_P_Offsets",
    "ECG_Q_Peaks",
    "ECG_R_Onsets",
    "ECG_R_Offsets",
    "ECG_S_Peaks",
    "ECG_T_Peaks",
    "ECG_T_Onsets",
    "ECG_T_Offsets",
]

RECORD_REGISTRY_COLUMNS = [
    "record_id",
    "raw_record_path",
    "fs",
    "n_samples",
    "duration_s",
    "full_chunks",
    "tail_samples",
    "has_tail",
    "raw_chunk_path",
    "clean_record_path",
    "clean_chunk_path",
    "status_raw_chunks",
    "status_clean_record",
    "status_clean_chunks",
    "created_at",
    "note",
]

CHUNK_REGISTRY_COLUMNS = [
    "record_id",
    "chunk_idx",
    "begin_idx",
    "end_idx",
    "begin_time",
    "end_time",
]


def get_record_id_from_path(record_path: str | Path) -> str | None:
    match = RECORD_ID_PATTERN.search(str(record_path))
    return match.group() if match else None


def get_parquet_path(paths: DataPaths, key: str, record_id: str) -> Path | None:
    base = getattr(paths, key)
    filename = f"{key}_{record_id}.parquet"
    path = base / filename
    return path if path.exists() else None


def split_record_into_chunks(record: pd.DataFrame, fs: int = 250, chunk_length_s: int = 10) -> list[pd.DataFrame]:
    window_size = fs * chunk_length_s
    if window_size <= 0:
        raise ValueError("window_size must be positive")
    chunks = [record.iloc[i : i + window_size].copy() for i in range(0, len(record), window_size)]
    return [chunk for chunk in chunks if len(chunk) == window_size]


def build_raw_chunk_table(chunks: list[pd.DataFrame], record_id: str) -> pd.DataFrame:
    rows = []
    for chunk_idx, chunk in enumerate(chunks):
        rows.append(
            {
                "record_id": record_id,
                "chunk_idx": chunk_idx,
                "ecg_raw": chunk["ecg"].to_numpy(),
                "begin_idx": int(chunk.index.min()),
                "end_idx": int(chunk.index.max()),
                "begin_time": float(chunk["time"].min()),
                "end_time": float(chunk["time"].max()),
            }
        )
    return pd.DataFrame(rows)


def convert_csv_to_parquet(csv_file: str | Path, compression: str = "snappy") -> Path:
    csv_path = Path(csv_file).expanduser().resolve()
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    output_path = csv_path.with_suffix(".parquet")
    dataframe = pd.read_csv(csv_path)
    dataframe.to_parquet(output_path, engine="pyarrow", compression=compression)
    LOGGER.info("Converted %s -> %s", csv_path, output_path)
    return output_path


def run_raw_record_to_chunk(paths: DataPaths, fs: int = 250, chunk_length_s: int = 10) -> Path:
    paths.ensure_directories()
    registry_path = paths.registry / "chunk_registry.csv"
    if registry_path.exists():
        existing = pd.read_csv(registry_path)
        existing_ids = set(existing["record_id"].astype(str)) if not existing.empty else set()
    else:
        existing = pd.DataFrame()
        existing_ids = set()

    new_chunk_rows: list[pd.DataFrame] = []
    for raw_record in sorted(paths.raw_record.glob("raw_record_*.parquet")):
        record_id = get_record_id_from_path(raw_record)
        if record_id is None or record_id in existing_ids:
            continue

        record = pd.read_parquet(raw_record)
        chunks = split_record_into_chunks(record, fs=fs, chunk_length_s=chunk_length_s)
        chunk_table = build_raw_chunk_table(chunks, record_id)

        chunk_path = paths.raw_chunk / f"raw_chunks_{record_id}.parquet"
        chunk_table.to_parquet(chunk_path, index=False)

        registry_rows = chunk_table[CHUNK_REGISTRY_COLUMNS].copy()
        registry_rows["chunk_path"] = str(chunk_path)
        new_chunk_rows.append(registry_rows)
        LOGGER.info("Created %s chunks for %s", len(chunk_table), record_id)

    if new_chunk_rows:
        new_rows = pd.concat(new_chunk_rows, ignore_index=True)
        updated = pd.concat([existing, new_rows], ignore_index=True) if not existing.empty else new_rows
        updated = updated.sort_values(["record_id", "chunk_idx"]).reset_index(drop=True)
        updated.to_csv(registry_path, index=False)
    else:
        LOGGER.info("No new records found for chunking")
    return registry_path


def run_nk_raw_to_clean(paths: DataPaths, sampling_rate: int = 250) -> Path:
    import neurokit2 as nk

    paths.ensure_directories()
    info_path = paths.registry / "ecg_info.parquet"
    if info_path.exists():
        existing = pd.read_parquet(info_path)
        existing_ids = set(existing["record_id"].astype(str)) if not existing.empty else set()
    else:
        existing = pd.DataFrame(columns=ECG_INFO_COLUMNS)
        existing_ids = set()

    new_rows: list[dict] = []
    for raw_record in sorted(paths.raw_record.glob("raw_record_*.parquet")):
        record_id = get_record_id_from_path(raw_record)
        if record_id is None or record_id in existing_ids:
            continue

        ecg_raw = pd.read_parquet(raw_record)
        ecg_clean, info = nk.ecg_process(ecg_signal=ecg_raw["ecg"], sampling_rate=sampling_rate)
        output_path = paths.clean_record / f"clean_record_{record_id}.parquet"
        ecg_clean.to_parquet(output_path, index=False)
        info["record_id"] = record_id
        new_rows.append(info)
        LOGGER.info("Cleaned %s", record_id)

    if new_rows:
        new_df = pd.DataFrame(new_rows, columns=ECG_INFO_COLUMNS)
        updated = pd.concat([existing, new_df], ignore_index=True)
        updated = updated.drop_duplicates(subset="record_id", keep="last")
        updated = updated.sort_values("record_id").reset_index(drop=True)
        updated.to_parquet(info_path, index=False)
    else:
        LOGGER.info("No new records found for cleaning")
    return info_path


def load_existing_record_registry(registry_path: Path) -> pd.DataFrame:
    if registry_path.exists():
        dataframe = pd.read_csv(registry_path)
        for column in RECORD_REGISTRY_COLUMNS:
            if column not in dataframe.columns:
                dataframe[column] = ""
        return dataframe[RECORD_REGISTRY_COLUMNS]
    return pd.DataFrame(columns=RECORD_REGISTRY_COLUMNS)


def build_record_registry_row(paths: DataPaths, record_id: str, fs: int, chunk_length_s: int) -> dict:
    raw_record_path = get_parquet_path(paths, "raw_record", record_id)
    if raw_record_path is None:
        raise FileNotFoundError(f"raw_record not found for {record_id}")

    record = pd.read_parquet(raw_record_path, columns=["time"])
    record_time = record["time"].to_numpy()

    n_samples = len(record_time)
    chunk_size = fs * chunk_length_s
    duration_s = float(record_time[-1] - record_time[0]) if n_samples > 0 else 0.0
    full_chunks = n_samples // chunk_size
    tail_samples = n_samples % chunk_size

    raw_chunk_path = paths.raw_chunk / f"raw_chunks_{record_id}.parquet"
    clean_record_path = get_parquet_path(paths, "clean_record", record_id)
    clean_chunk_path = get_parquet_path(paths, "clean_chunk", record_id)

    return {
        "record_id": record_id,
        "raw_record_path": str(raw_record_path),
        "fs": fs,
        "n_samples": n_samples,
        "duration_s": duration_s,
        "full_chunks": full_chunks,
        "tail_samples": tail_samples,
        "has_tail": tail_samples != 0,
        "raw_chunk_path": str(raw_chunk_path) if raw_chunk_path.exists() else "",
        "clean_record_path": str(clean_record_path) if clean_record_path else "",
        "clean_chunk_path": str(clean_chunk_path) if clean_chunk_path else "",
        "status_raw_chunks": "Done" if raw_chunk_path.exists() else "Missing",
        "status_clean_record": "Done" if clean_record_path else "Missing",
        "status_clean_chunks": "Done" if clean_chunk_path else "Missing",
        "created_at": get_dtime(record_time[0]) if n_samples > 0 else "",
        "note": "",
    }


def run_update_record_registry(paths: DataPaths, fs: int = 250, chunk_length_s: int = 10) -> Path:
    paths.ensure_directories()
    registry_path = paths.registry / "record_registry.csv"
    existing = load_existing_record_registry(registry_path)
    existing_ids = set(existing["record_id"].astype(str)) if not existing.empty else set()

    new_rows = []
    for record_file in sorted(paths.raw_record.glob("raw_record_*.parquet")):
        record_id = get_record_id_from_path(record_file.name)
        if record_id is None or record_id in existing_ids:
            continue
        new_rows.append(build_record_registry_row(paths, record_id, fs=fs, chunk_length_s=chunk_length_s))
        LOGGER.info("Indexed %s", record_id)

    if new_rows:
        new_df = pd.DataFrame(new_rows, columns=RECORD_REGISTRY_COLUMNS)
        updated = pd.concat([existing, new_df], ignore_index=True)
        updated = updated.drop_duplicates(subset="record_id", keep="last")
        updated = updated.sort_values("record_id").reset_index(drop=True)
        updated.to_csv(registry_path, index=False)
    else:
        LOGGER.info("No new records found for record registry")
    return registry_path


def run_update_chunk_registry(paths: DataPaths) -> Path:
    paths.ensure_directories()
    dataframes = []
    for chunks_file in sorted(paths.raw_chunk.glob("raw_chunks_*.parquet")):
        dataframe = pd.read_parquet(chunks_file, columns=CHUNK_REGISTRY_COLUMNS)
        dataframe["chunk_path"] = str(chunks_file)
        dataframes.append(dataframe)
        LOGGER.info("Indexed chunk file %s", chunks_file.name)

    chunk_registry = pd.concat(dataframes, ignore_index=True) if dataframes else pd.DataFrame(
        columns=CHUNK_REGISTRY_COLUMNS + ["chunk_path"]
    )
    output_path = paths.registry / "chunk_registry.csv"
    chunk_registry.to_csv(output_path, index=False)
    return output_path

