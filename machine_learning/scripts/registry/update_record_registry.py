import re
from pathlib import Path
import pandas as pd
from ecg_core.rr_hr_hrv import get_dtime

base_paths = {
    "registry": Path("E:/ECG_data/250hz/registry"),
    "raw_record": Path("E:/ECG_data/250hz/records/raw_record"),
    "clean_record": Path("E:/ECG_data/250hz/records/clean_record"),
    "raw_chunk": Path("E:/ECG_data/250hz/chunks/raw_chunk"),
    "clean_chunk": Path("E:/ECG_data/250hz/chunks/clean_chunk"),
}

fs = 250
chunk_length = 10
chunk_size = fs * chunk_length

OUTPUT_COLUMNS = [
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

def get_record_id(record_path: str):
    m = re.search(r"\d{4}-\d{2}-\d{2}_\d{6}", record_path)
    return m.group() if m else None

def get_parquet_path(key: str, record_id: str):
    path = base_paths[key] / f"{key}_{record_id}.parquet"
    return path if path.exists() else None

def load_existing_registry(registry_path: Path) -> pd.DataFrame:
    if registry_path.exists():
        df = pd.read_csv(registry_path)
        # 保证列齐全，避免旧表结构不完整
        for col in OUTPUT_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df[OUTPUT_COLUMNS]
    return pd.DataFrame(columns=OUTPUT_COLUMNS)

def build_row(record_id: str) -> dict:
    raw_record_path = get_parquet_path("raw_record", record_id)
    if raw_record_path is None:
        raise FileNotFoundError(f"raw_record not found for {record_id}")

    record = pd.read_parquet(raw_record_path, columns=["time"])
    record_time = record["time"].to_numpy()

    n_samples = len(record_time)
    duration_s = float(record_time[-1] - record_time[0]) if n_samples > 0 else 0.0
    full_chunks = n_samples // chunk_size
    tail_samples = n_samples % chunk_size
    has_tail = tail_samples != 0

    raw_chunk_path = get_parquet_path("raw_chunk", record_id)
    clean_record_path = get_parquet_path("clean_record", record_id)
    clean_chunk_path = get_parquet_path("clean_chunk", record_id)

    return {
        "record_id": record_id,
        "raw_record_path": str(raw_record_path),
        "fs": fs,
        "n_samples": n_samples,
        "duration_s": duration_s,
        "full_chunks": full_chunks,
        "tail_samples": tail_samples,
        "has_tail": has_tail,
        "raw_chunk_path": str(raw_chunk_path) if raw_chunk_path else "",
        "clean_record_path": str(clean_record_path) if clean_record_path else "",
        "clean_chunk_path": str(clean_chunk_path) if clean_chunk_path else "",
        "status_raw_chunks": "Done" if raw_chunk_path else "Missing",
        "status_clean_record": "Done" if clean_record_path else "Missing",
        "status_clean_chunks": "Done" if clean_chunk_path else "Missing",
        "created_at": get_dtime(record_time[0]) if n_samples > 0 else "",
        "note": "",
    }

def main():
    registry_path = base_paths["registry"] / "record_registry.csv"

    existing = load_existing_registry(registry_path)
    existing_ids = set(existing["record_id"].astype(str)) if not existing.empty else set()

    new_rows = []
    for record_file in sorted(base_paths["raw_record"].glob("raw_record_*.parquet")):
        record_id = get_record_id(record_file.name)
        if record_id is None:
            print(f"[Skip] No record ID in {record_file.name}")
            continue

        if record_id in existing_ids:
            continue

        try:
            row = build_row(record_id)
            new_rows.append(row)
            print(f"[New] {record_id}")
        except Exception as e:
            print(f"[Fail] {record_id}: {e}")

    if new_rows:
        new_df = pd.DataFrame(new_rows, columns=OUTPUT_COLUMNS)
        updated = pd.concat([existing, new_df], ignore_index=True)
        updated = updated.drop_duplicates(subset="record_id", keep="last")
        updated = updated.sort_values("record_id").reset_index(drop=True)
        updated.to_csv(registry_path, index=False)
        print(f"[Done] Added {len(new_rows)} new records -> {registry_path}")
    else:
        print("[Info] No new records found.")

if __name__ == "__main__":
    main()