import os, re
import pandas as pd

def split_record_into_chunks(record_path):
    data = pd.read_parquet(record_path)
    window_size = 10 * 250
    chunks = [data[i:i + window_size] for i in range(0, len(data), window_size)][:-1]
    return chunks


def build_raw_chunk_table(chunks, record_id):
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
    chunk_df['record_id'] = f"record_{record_id}"
    chunk_df['chunk_idx'] = chunk_df.index
    chunk_df = chunk_df[
        ['record_id', 'chunk_idx', 'ecg_raw',
        'begin_idx', 'end_idx', 'begin_time', 'end_time']
    ]
    return chunk_df


def get_record_id_from_path(record_path):
    record_id = re.search(r'\d{4}-\d{2}-\d{2}_\d{6}', record_path).group()
    return record_id


def raw_record_file_to_chunk_table(record_path):
    chunks = split_record_into_chunks(record_path)
    record_id = get_record_id_from_path(record_path)
    chunks_df = build_raw_chunk_table(chunks, record_id)
    return chunks_df


if __name__ == '__main__':
    raw_chunk_path = 'E:/ECG_data/250hz/chunks/raw_chunks/'
    raw_data_path = 'E:/ECG_data/250hz/records/raw/'
    records = os.listdir(raw_data_path)
    record_paths = [raw_data_path+record for record in records]

    for record_path in record_paths:
        record_id = get_record_id_from_path(record_path)
        chunk_table = raw_record_file_to_chunk_table(record_path)
        chunk_table.to_parquet(raw_chunk_path+f"raw_chunks_{record_id}.parquet")
        print('Chunk tables split:', record_id)