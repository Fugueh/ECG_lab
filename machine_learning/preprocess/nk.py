import re
import pandas as pd
from pathlib import Path
import neurokit2 as nk

base_paths = {
    "registry": Path("E:/ECG_data/250hz/registry"),
    "raw_record": Path("E:/ECG_data/250hz/records/raw_record"),
    "clean_record": Path("E:/ECG_data/250hz/records/clean_record"),
    "raw_chunk": Path("E:/ECG_data/250hz/chunks/raw_chunk"),
    "clean_chunk": Path("E:/ECG_data/250hz/chunks/clean_chunk"),
}

raw_path = base_paths["raw_record"]
clean_path = base_paths["clean_record"]
registry_path = base_paths["registry"]

raw_records = sorted(raw_path.glob("raw_record_*.parquet"))

infos = {} 
for raw_record in raw_records:
    str_path = str(raw_record.name)
    record_idx = re.search(r"\d{4}-\d{2}-\d{2}_\d{6}", str_path).group()
    print(record_idx)

    ecg_raw = pd.read_parquet(raw_record)
    ecg_clean, info = nk.ecg_process(ecg_signal=ecg_raw["ecg"], sampling_rate=250)
    infos[record_idx] = info
    ecg_clean.to_parquet(clean_path / f"clean_record_{record_idx}.parquet")

infos_df = pd.DataFrame(infos).T
infos_df['record_id'] = infos_df.index
infos_df = infos_df[['record_id'] + list(infos_df.columns[:-1])]
infos_df.to_csv(registry_path/f"ecg_info.csv")


