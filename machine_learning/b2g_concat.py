import os, re
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()
# 创建表格：去掉所有边框，定义两列的默认样式
table = Table(box=None, show_header=False, pad_edge=False)
table.add_column("label")
table.add_column("value", justify="right") # 数值右对齐

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

counts = all_samples['label'].value_counts()
good_count = counts.get('good', 0)
bad_count = counts.get('bad', 0)
b2g_count = counts.get('bad2good', 0)

# 仅在第一列写颜色标签，第二列保持原色
table.add_row("[bold green]Good:[/]", str(good_count))
table.add_row("[bold red]Bad:[/]", str(bad_count))
table.add_row("[bold yellow]Bad2good:[/]", str(b2g_count))
console.print(table)

all_samples.to_parquet('all_samples.parquet')