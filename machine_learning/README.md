# ECG_lab / machine_learning

`machine_learning` 目录负责整理 ECG 数据的离线机器学习流水线。当前代码的重点不是在线推理，而是把原始记录切分、清洗、登记，并为后续人工标注和训练准备数据。

## 目录作用

- `preprocess/`
  - 从 `raw_record` 生成 `clean_record`
  - 把连续记录切成 10 秒 chunk
- `registry/`
  - 维护 record/chunk/stage 等注册表
  - 方便追踪每条记录当前处理到了哪一步
- `labling/`
  - 从人工挑出的 JPG 结果回写标签
  - 拼接最终训练样本
- `predict/`
  - 训练用脚本和数据集拆分逻辑

## 数据目录约定

当前脚本默认使用下面这组路径：

```python
base_paths = {
    "registry": Path("E:/ECG_data/250hz/registry"),
    "raw_record": Path("E:/ECG_data/250hz/records/raw_record"),
    "clean_record": Path("E:/ECG_data/250hz/records/clean_record"),
    "raw_chunk": Path("E:/ECG_data/250hz/chunks/raw_chunk"),
    "clean_chunk": Path("E:/ECG_data/250hz/chunks/clean_chunk"),
}
```

默认采样率是 `250 Hz`，默认 chunk 长度是 `10 s`，所以每个 chunk 的长度为 `2500` 个采样点。

## 当前主流程

### 1. 原始记录入库

原始数据文件放在：

- `E:/ECG_data/250hz/records/raw_record`

命名约定：

- `raw_record_YYYY-MM-DD_HHMMSS.parquet`

脚本会从文件名中提取 `record_id`，格式为 `YYYY-MM-DD_HHMMSS`。

### 2. 清洗 raw record

运行：

```powershell
python machine_learning\preprocess\nk_raw2clean.py
```

这个脚本会：

- 遍历所有 `raw_record_*.parquet`
- 跳过已经写入注册表的 `record_id`
- 使用 `neurokit2.ecg_process(...)` 对 `ecg` 列做清洗
- 输出 `clean_record_*.parquet`
- 更新 `registry/ecg_info.parquet`

输出物：

- `clean_record/clean_record_<record_id>.parquet`
- `registry/ecg_info.parquet`

### 3. 切分 raw record 为 10 秒 chunk

运行：

```powershell
python machine_learning\preprocess\raw_record2chunk.py
```

这个脚本会：

- 读取 `raw_record_*.parquet`
- 每 `2500` 个采样点切成一个 chunk
- 丢弃最后不足 10 秒的尾段
- 为每条记录生成一个 chunk parquet
- 增量更新 `registry/chunk_registry.csv`

输出物：

- `raw_chunk/raw_chunks_<record_id>.parquet`
- `registry/chunk_registry.csv`

`chunk_registry.csv` 里会记录：

- `record_id`
- `chunk_idx`
- `begin_idx`
- `end_idx`
- `begin_time`
- `end_time`
- `chunk_path`

### 4. 更新记录级注册表

运行：

```powershell
python machine_learning\registry\update_record_registry.py
```

这个脚本会扫描每条 `raw_record`，并汇总：

- 原始记录路径
- 采样率、时长、样本数
- 能切出多少个完整 chunk
- 是否存在尾段
- 对应的 `raw_chunk` / `clean_record` / `clean_chunk` 是否已经生成

输出物：

- `registry/record_registry.csv`

这个表更像是“记录处理状态总表”。

### 5. 重建 chunk 注册表

运行：

```powershell
python machine_learning\registry\update_chunk_registry.py
```

这个脚本会重新扫描所有 `raw_chunks*.parquet`，然后整表重建：

- `registry/chunk_registry.csv`

如果你已经通过 `raw_record2chunk.py` 增量更新过，一般不一定需要再跑它；它更适合做全量重建。

## 标注与训练

### `labling/`

当前 `labling/` 目录保留的是较早一版的人工标注流程，主要围绕：

- `b2g_from_jpg.py`
  - 根据人工筛出的 JPG 文件名，把 `bad` 中可保留的片段改标为 `bad2good`
- `b2g_concat.py`
  - 合并所有 `b2g_chunks_*.parquet`
  - 生成训练用总表 `all_samples.parquet`

这部分脚本目前仍然假定存在类似下面的旧目录结构：

- `./data_parquets/`
- `./ecg_figs/<timestamp>/bad2good/`

如果后面要继续使用这条链路，建议把路径配置和当前 `base_paths` 体系统一起来。

### `predict/`

`predict/split_and_train.py` 包含：

- ECG 数据集封装
- train/val/test 划分
- 类别不平衡采样
- 一个 `Conv1d` 二分类训练骨架

它依赖样本表里至少包含：

- ECG 序列列，例如 `ecg_raw`
- 标签列，例如 `label_int`

这部分更像训练实验脚本，而不是已经固定下来的生产训练入口。

## 推荐使用顺序

如果只是处理新到的原始记录，推荐顺序如下：

1. `python machine_learning\preprocess\nk_raw2clean.py`
2. `python machine_learning\preprocess\raw_record2chunk.py`
3. `python machine_learning\registry\update_record_registry.py`

如果怀疑 `chunk_registry.csv` 不完整，再补跑：

4. `python machine_learning\registry\update_chunk_registry.py`

如果需要进入人工标注和训练，再继续走：

5. `machine_learning\labling\*.py`
6. `machine_learning\predict\split_and_train.py`

## 现状说明

- README 现在以当前仓库里的脚本为准，不再描述已经删除的旧预处理脚本。
- `labling/` 文件夹名沿用了现有拼写，如果后续整理目录，建议统一改成 `labeling/`。
- `update_stage_registry.py` 目前是空文件，暂时没有纳入流程。
