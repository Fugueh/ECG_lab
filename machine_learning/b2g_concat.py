import os, re
import pandas as pd
data_path = './data_parquets/'

files = [file for file in os.listdir(data_path) if 'b2g_chunks' in file]

new_dfs = []
for file in files:
    time_str = re.search(r'\d{4}-\d{2}-\d{2}_\d{6}', file).group()
    df = pd.read_parquet(data_path+file)
    df['begin_time'] = time_str
    df['sample_id'] = df.index
    new_dfs.append(df)

all_samples = pd.concat(new_dfs, ignore_index=True)

good = all_samples[all_samples['label'] == 'good']
bad = all_samples[all_samples['label'] == 'bad']
bad2good = all_samples[all_samples['label'] == 'bad2good']
print(good.shape[0], bad.shape[0], bad2good.shape[0])

all_samples.to_parquet('all_samples.parquet')