import os, re
import pandas as pd
from pathlib import Path

base_paths = {
    "registry": Path("E:/ECG_data/250hz/registry"),
    "raw_record": Path("E:/ECG_data/250hz/records/raw_record"),
    "clean_record": Path("E:/ECG_data/250hz/records/clean_record"),
    "raw_chunk": Path("E:/ECG_data/250hz/chunks/raw_chunk"),
    "clean_chunk": Path("E:/ECG_data/250hz/chunks/clean_chunk"),
}


OUTPUT_COLUMNS = [
    "record_id",
    "chunk_idx",
    "begin_idx",
    "end_idx",
    "begin_time",
    "end_time"
]

def split_record_into_chunks(record_path: Path) -> list:
    data = pd.read_parquet(record_path)
    window_size = 10 * 250
    chunks = [data[i:i + window_size] for i in range(0, len(data), window_size)][:-1]
    return chunks


def build_raw_chunk_table(chunks: list, record_id: str) -> pd.DataFrame:
    chunk_dict = {}
    for i, chunk in enumerate(chunks):
        chunk = chunk.copy()
        begin_idx = min(chunk.index)
        end_idx = max(chunk.index)
        begin_time = min(chunk['time'])
        end_time = max(chunk['time'])
        ecg = chunk['ecg'].values
        chunk_dict[i] = [ecg, begin_idx, end_idx, begin_time, end_time]
    chunk_df = pd.DataFrame(chunk_dict).T
    chunk_df.columns = ['ecg_raw', 'begin_idx', 'end_idx', 'begin_time', 'end_time']
    chunk_df['record_id'] = f"{record_id}"
    chunk_df['chunk_idx'] = chunk_df.index
    chunk_df = chunk_df[
        ['record_id', 'chunk_idx', 'ecg_raw',
        'begin_idx', 'end_idx', 'begin_time', 'end_time']
    ]
    return chunk_df


def get_record_id_from_path(record_path: Path) -> str:
    str_path = str(record_path)
    record_id = re.search(r'\d{4}-\d{2}-\d{2}_\d{6}', str_path).group()
    return record_id


def raw_record_file_to_chunk_table(record_path: Path) -> pd.DataFrame:
    chunks = split_record_into_chunks(record_path)
    record_id = get_record_id_from_path(record_path)
    chunks_df = build_raw_chunk_table(chunks, record_id)
    return chunks_df


def get_new_rows(raw_records, existing_ids, raw_chunk_path):
    new_chunks = []
    for raw_record in raw_records:
        record_id = get_record_id_from_path(raw_record)
        if record_id is None:
            print(f"[Skip] No record ID in {raw_record.name}")
            continue

        if record_id in existing_ids:
            continue
        
        try:
            # to split chunks and save chunk parquet
            chunk = raw_record_file_to_chunk_table(raw_record)
            chunk_path = raw_chunk_path/f"raw_chunks_{record_id}.parquet"
            chunk.to_parquet(chunk_path)
            chunk = chunk[OUTPUT_COLUMNS]
            chunk["chunk_path"] = str(chunk_path)
            new_chunks.append(chunk)
            print(f"[New] {record_id} into {len(chunk)} 10s chunks.")
        except Exception as e:
            print(f"[Fail] {record_id}: {e}")
    return new_chunks
        
    

def main():
    raw_data_path = base_paths["raw_record"]
    raw_records = sorted(raw_data_path.glob("raw_record_*.parquet"))

    raw_chunk_path = base_paths["raw_chunk"]
    registry_path = base_paths["registry"]

    chunk_reg_path = registry_path / "chunk_registry.csv"
    if chunk_reg_path.exists():
        existing = pd.read_csv(chunk_reg_path)
        existing_ids = set(existing["record_id"].astype(str)) if not existing.empty else set()
    else:
        existing = False
        existing_ids = set([])

    # to add new records and write
    new_chunks = get_new_rows(raw_records, existing_ids, raw_chunk_path)

    if new_chunks:
        new_rows = pd.concat(new_chunks)
        if existing:
            updated = pd.concat([existing, new_rows], ignore_index=True)
        else:
            updated = new_rows
        updated = updated.sort_values("record_id").reset_index(drop=True)
        updated.to_csv(chunk_reg_path, index=False)
        print(f"[Done] Added {len(new_chunks)} new records ({len(new_chunks)} chunks)-> {chunk_reg_path}.")
    else:
        print("[Info] No new records found.")


if __name__ == '__main__':
    main()
    

