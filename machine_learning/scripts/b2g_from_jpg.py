import os, re
import pandas as pd

data_path = './data_parquets/'
gb_files = [file for file in os.listdir(data_path) if 'gb_chunks_' in file]

for file in gb_files:
    time_str = re.search(r'\d{4}-\d{2}-\d{2}_\d{6}', file).group()
    gb = pd.read_parquet(data_path+file)
    if time_str == '2026-02-25_095337':
        b2g = gb.copy()
    else:
        jpg_path = f"./ecg_figs/{time_str}/bad2good/"
        bad2good_idxs = [int(jpg.split('_')[0]) for jpg in os.listdir(jpg_path)]
        b2g = gb.copy()
        b2g.loc[bad2good_idxs, 'label'] = 'bad2good'
    b2g.to_parquet(f"{data_path}b2g_chunks_{time_str}.parquet")