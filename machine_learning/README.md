# ECG_lab / machine_learning

<u>Last updated at 2026-03-01, 19:50</u>

这个目录用于把连续 ECG 日志切成 10 秒片段，并生成用于训练的标注数据集。核心目标是做三类数据：

- `good`：质量好

- `bad`：明显坏段（导联脱落/大幅漂移/强噪声等）

- `bad2good (b2g)`：从 `bad` 里人工<mark>平反</mark>出来的可用片段（用于提升阈值粗分的精度）

整体思路：先用简单阈值把数据粗分，再对 `bad` 做人工筛选，把“误杀”的片段写回 `b2g`，最后把所有 `b2g` 拼成训练集。

## 目录结构

> 使用 `tree -L 2 -I "*.csv|*.parquet|*.jpg|*.png|*.npy|__pycache__|*.pyc"` 查看

```plaintext
.
├── 10s_chunks.ipynb               # 连续日志切片机
├── README.md                      # 就是我，别视而不见
├── b2g_concat.py                  # 战果汇总（拼接所有平反数据）
├── b2g_from_jpg.py                # 自动平反工具（从图片名提取 ID）
├── cnn_3classes.py                # 三分类 CNN 训练主炉
├── data_parquets/                 # [禁止同步] 存放所有 .parquet 数据
├── ecg_figs/                      # [禁止同步] 存放可视化的 JPG 质检图
├── good_bad_split_by_threshold.ipynb # 阈值粗分逻辑
└── save_good_bad_jpg.ipynb        # 将片段批量转为 JPG 的渲染器
```



- `data_parquets/`  
  输入/中间数据（parquet）。常见命名：
  
  - `ecg_log_YYYY-MM-DD_HHMMSS.parquet`：原始日志（连续数据）
  
  - `gb_chunks_YYYY...parquet`：阈值粗分后的 10s chunks（good/bad）
  
  - `b2g_chunks_YYYY...parquet`：人工从 bad 里挑出的 b2g chunks

- `ecg_figs/`  
  输出图片（按一次日志时间戳建子目录）。常见结构：
  
  - `ecg_figs/<timestamp>/bad/`：坏段图
  
  - `ecg_figs/<timestamp>/bad2good/`：被<mark>平反</mark>的图（可选）
  
  

## Pipeline

1. 从 `ecg_log.parquet` 切 10 秒片段并画图

2. 用阈值把片段粗分为 `good/bad`，得到 `gb_chunks.parquet`

3. 把 `bad` 片段全部画成 jpg，方便人工扫一遍

4. 人工把“bad 里其实还行的”挑出来，写回 `b2g_chunks.parquet`

5. 拼接所有 `b2g_chunks`，得到最终训练用的数据集（例如 `all_samples.parquet`）

## 文件的用途

| **步骤** | **脚本名称**            | **主要输入**              | **主要输出**               | **备注**              |
| ------ | ------------------- | --------------------- | ---------------------- | ------------------- |
| 1      | `10s_chunks.ipynb`  | `ecg_log_*.parquet`   | 10s fragments          | 记得对齐 NeuroKit2 的采样率 |
| 2      | `good_bad_split...` | `ecg_log_*.parquet`   | `gb_chunks_*.parquet`  | 粗分阈值在脚本顶部修改         |
| 3      | `save_good_bad_jpg` | `gb_chunks_*.parquet` | `/bad/*.jpg`           | 扫图才是最费眼睛的           |
| 4      | `b2g_from_jpg.py`   | `bad2good/` 里的图       | `b2g_chunks_*.parquet` | 靠文件名里的 Chunk ID 匹配  |
| 5      | `b2g_concat.py`     | 所有的 `b2g_chunks`      | `all_samples.parquet`  | 最终训练集               |

> 注：文件名里的 `ts`/`timestamp` 指一次采集日志的时间戳（如 `2026-02-20_010744`），用于把数据、图片、chunk 对齐。

## 最小使用流程

1. 先准备好 `data_parquets/ecg_log_*.parquet`（上游 monitor 或转换脚本生成）

2. 依次跑：
   
   - `10s_chunks.ipynb`  
   
   - `good_bad_split_by_threshold.ipynb`  
   
   - `save_good_bad_jpg.ipynb`

3. 打开 `ecg_figs/<timestamp>/bad/`，人工扫图，把“误杀的 bad”挑出来

4. 运行：
   
   - `python b2g_from_jpg.py`（把挑出的结果写回 `b2g_chunks`）  
   
   - `python b2g_concat.py`（拼接所有 b2g）

5. 训练：
   
   - `python cnn_3classes.py`
