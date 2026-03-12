import os, re
import pandas as pd
from pathlib import Path
from ecg_core.rr_hr_hrv import get_dtime

base_paths = {
    'registry': Path('E:/ECG_data/250hz/registry'),
    'raw_record': Path('E:/ECG_data/250hz/records/raw_record'),
    'clean_record':Path('E:/ECG_data/250hz/records/clean_record'),
    'raw_chunk': Path('E:/ECG_data/250hz/chunks/raw_chunk'),
    'clean_chunk': Path('E:/ECG_data/250hz/chunks/clean_chunk')
}

def get_parquet_path(key, record_id):
    path = base_paths[key] / f"{key}_{record_id}.parquet"
    return path if path.exists() else None

def get_record_id(record_path):
    try:
        return re.search(r'\d{4}-\d{2}-\d{2}_\d{6}', record_path).group()
    except AttributeError:
        # None.group()
        print(f"Error: No record ID in '{record_path}'.")
        return None


key = 'raw_record'
records = os.listdir(base_paths[key])
record_ids = [get_record_id(filename) for filename in os.listdir(base_paths['raw_record'])]
record_id = record_ids[0]
record = pd.read_parquet(get_parquet_path(key, record_id))

fs = 250; chunk_length = 10
record_time = record['time'].values

n_samples = len(record)
duration_s = record_time[-1] - record_time[0]
full_chunks = n_samples // (fs*chunk_length)
tail_samples = n_samples % (fs*chunk_length)
has_tail = False if tail_samples == 0 else True

raw_record_path = get_parquet_path('raw_record', record_id)
raw_chunk_path = get_parquet_path('raw_chunk', record_id)
clean_record_path = get_parquet_path('clean_record', record_id)
clean_chunk_path = get_parquet_path('clean_chunk', record_id)

status_raw_chunks = 'Done' if raw_chunk_path else 'Missing'
status_clean_record = 'Done' if clean_record_path else 'Missing'
status_clean_chunks = 'Done' if clean_chunk_path else 'Missing'
created_at = get_dtime(record_time[0])
note = ''


features = {
    'record_id': record_id,
    'raw_record_path': raw_record_path,
    'fs': fs,
    'n_samples': n_samples,
    'duration_s': duration_s,
    'full_chunks': full_chunks,
    'tail_samples': tail_samples,
    'has_tail': has_tail,
    'raw_chunk_path': raw_chunk_path,
    'clean_record_path': clean_record_path,
    'clean_chunk_path': clean_chunk_path,
    'created_at': created_at,
    'note': note
}

rows = []

for record_file in os.listdir(base_paths['raw_record']):
    record_id = get_record_id(record_file)
    if record_id is None:
        continue

    record = pd.read_parquet(get_parquet_path('raw_record', record_id))
    record_time = record['time'].values

    n_samples = len(record)
    duration_s = record_time[-1] - record_time[0]
    full_chunks = n_samples // (fs * chunk_length)
    tail_samples = n_samples % (fs * chunk_length)
    has_tail = tail_samples != 0

    raw_record_path = get_parquet_path('raw_record', record_id)
    raw_chunk_path = get_parquet_path('raw_chunk', record_id)
    clean_record_path = get_parquet_path('clean_record', record_id)
    clean_chunk_path = get_parquet_path('clean_chunk', record_id)

    row = {
        'record_id': record_id,
        'raw_record_path': str(raw_record_path) if raw_record_path else '',
        'fs': fs,
        'n_samples': n_samples,
        'duration_s': float(duration_s),
        'full_chunks': full_chunks,
        'tail_samples': tail_samples,
        'has_tail': has_tail,
        'raw_chunk_path': str(raw_chunk_path) if raw_chunk_path else '',
        'clean_record_path': str(clean_record_path) if clean_record_path else '',
        'clean_chunk_path': str(clean_chunk_path) if clean_chunk_path else '',
        'status_raw_chunks': 'Done' if raw_chunk_path else 'Missing',
        'status_clean_record': 'Done' if clean_record_path else 'Missing',
        'status_clean_chunks': 'Done' if clean_chunk_path else 'Missing',
        'created_at': get_dtime(record_time[0]),
        'note': ''
    }
    rows.append(row)

record_registry = pd.DataFrame(rows)
record_registry.to_csv(base_paths['registry'] / 'record_registry.csv', index=False)