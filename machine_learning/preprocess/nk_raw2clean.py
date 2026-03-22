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


OUTPUT_COLUMNS = [
    'record_id', 'method_peaks', 'method_fixpeaks', 'ECG_R_Peaks',
    'ECG_R_Peaks_Uncorrected', 'ECG_fixpeaks_ectopic',
    'ECG_fixpeaks_missed', 'ECG_fixpeaks_extra', 'ECG_fixpeaks_longshort',
    'ECG_fixpeaks_method', 'ECG_fixpeaks_rr', 'ECG_fixpeaks_drrs',
    'ECG_fixpeaks_mrrs', 'ECG_fixpeaks_s12', 'ECG_fixpeaks_s22',
    'ECG_fixpeaks_c1', 'ECG_fixpeaks_c2', 'sampling_rate', 'ECG_P_Peaks',
    'ECG_P_Onsets', 'ECG_P_Offsets', 'ECG_Q_Peaks', 'ECG_R_Onsets',
    'ECG_R_Offsets', 'ECG_S_Peaks', 'ECG_T_Peaks', 'ECG_T_Onsets',
    'ECG_T_Offsets'
]

def get_record_id_from_path(record_path: Path) -> str:
    str_path = str(record_path)
    record_id = re.search(r'\d{4}-\d{2}-\d{2}_\d{6}', str_path).group()
    return record_id


def get_new_rows(raw_records, existing_ids, clean_path):
    new_rows = []
    for raw_record in raw_records:
        record_id = get_record_id_from_path(raw_record)
        if record_id is None:
            print(f"[Skip] No record ID in {raw_record.name}")
            continue

        if record_id in existing_ids:
            continue

        try:
            # process
            ecg_raw = pd.read_parquet(raw_record)
            ecg_clean, info = nk.ecg_process(ecg_signal=ecg_raw["ecg"], sampling_rate=250)

            # save clean signals
            ecg_clean.to_parquet(clean_path / f"clean_record_{record_id}.parquet")

            # build info row
            info['record_id'] = record_id
            new_rows.append(info)
            print(f"[New] {record_id}")
        except Exception as e:
            print(f"[Fail] {record_id}: {e}")
    return new_rows


def get_updated(new_rows, existing):
    """
    1. concat new_df (of new_rows) and existing
    2. drop_duplicates to delete repeat rows
    3. sort updated by record_id and reset index
    """
    new_df = pd.DataFrame(new_rows, columns=OUTPUT_COLUMNS)
    if existing:
        updated = pd.concat([existing, new_df], ignore_index=True)
    else:
        updated = new_df
    updated = updated.drop_duplicates(subset="record_id", keep="last")
    updated = updated.sort_values("record_id").reset_index(drop=True)
    return updated


def main():
    # to read raw records
    raw_path = base_paths["raw_record"]
    raw_records = sorted(raw_path.glob("raw_record_*.parquet"))

    # to save cleaned records
    clean_path = base_paths["clean_record"]
    registry_path = base_paths["registry"]

    # to get existing ids
    info_path = registry_path/"ecg_info.parquet"
    if info_path.exists():
        existing = pd.read_parquet(info_path)
        existing_ids = set(existing["record_id"].astype(str)) if not existing.empty else set()
    else:
        existing = False
        existing_ids = []

    # to add new records and write
    new_rows = get_new_rows(raw_records, existing_ids, clean_path)
    if new_rows:
        updated = get_updated(new_rows, existing)
        updated.to_parquet(info_path, index=False)
        print(f"[Done] Added {len(new_rows)} new records -> {info_path}.")
    else:
        print("[Info] No new records found.")


if __name__ == "__main__":
    main()
