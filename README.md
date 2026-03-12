# ECG Lab

ECG Lab 是一个以实验为导向的心电（ECG）工作仓，覆盖从实时采集、监控、离线复核到训练数据构建与模型训练的完整链路。

## 1. 项目目标

- 实时读取串口 ECG 数据并显示关键指标（HR / RR / HRV）。
- 将采集日志保存为 CSV/Parquet 供离线分析。
- 通过可视化工具对信号质量进行复核与差异标注。
- 构建 `good / bad / bad2good` 数据集并训练 1D CNN。

## 2. 仓库结构

```text
ECG_lab/
├─ app/
│  ├─ monitor/               # 实时监控与串口读取
│  └─ viewer_gui/            # 离线查看与标注辅助
├─ ecg_core/                 # RR/HR/HRV 核心计算逻辑
├─ machine_learning/         # 数据切片、样本构建、训练脚本
├─ debug_tools/              # 最小可运行与调试脚本
└─ playground/               # 临时实验/notebook
```

## 3. 关键模块说明

### `app/monitor`

- `monitor_50hz.py`: 50Hz 流程，读取单点串口数据并实时显示。
- `monitor_250hz.py`: 250Hz 帧读取流程（每帧 5 点），并压缩到显示点。
- `functions.py`: 串口读取、画图更新、RR/HR/HRV 工具函数。
- `configuration.py`: 串口与缓存窗口配置（如 `COM3`、`115200`、`fs`）。

### `app/viewer_gui`

- `ecg_viewer.py`: 单窗口滑块浏览 ECG。
- `ecg_viewer_multi.py`: 多窗口联动浏览（4 段 + 细节段）。
- `ecg_viewer_diff.py` / `ecg_viewer_label.py`: 显示 `nk_miss` 与 `my_extra` 差异标记。

### `ecg_core`

- `rr_hr_hrv.py`: `BeatCalc` 等类，基于峰值检测计算 HR、SDNN、RMSSD。

### `machine_learning`

- `good_bad_split_by_threshold.ipynb`: 阈值粗分 `good/bad`。
- `save_good_bad_jpg.ipynb`: 导出图像用于人工复核。
- `b2g_from_jpg.py`: 从人工挑选图片回写 `bad2good`。
- `b2g_concat.py`: 汇总多个 `b2g_chunks` 形成训练集。
- `split_and_train.py` / `predict/split_and_train.py`: 数据切分与二分类训练工具。
- `cnn_3classes.py`: 简化 1D CNN 结构与训练循环。

## 4. 环境要求

建议 Python 3.10+，并安装以下常用依赖：

```bash
pip install numpy pandas scipy pyqtgraph pyqt5 pyserial pyarrow scikit-learn torch rich
```

> 说明：仓库当前未提供完整依赖锁定文件；以脚本实际 import 为准。

## 5. 快速开始

### 5.1 实时监控（串口）

1. 打开并修改 `app/monitor/configuration.py`：
- `SERIAL_PORT`（如 `COM3`）
- `BAUD`（默认 `115200`）
- `fs` 与 `time_window`

2. 运行监控：

```bash
cd app/monitor
python monitor_50hz.py
# 或
python monitor_250hz.py
```

程序会生成 `ecg_log_YYYY-MM-DD_HHMMSS.csv`。

### 5.2 CSV 转 Parquet

```bash
cd app/monitor
python csv2parquet.py ecg_log_2026-03-05_120000.csv
```

### 5.3 离线查看

```bash
cd app/viewer_gui
python ecg_viewer_multi.py <你的csv或parquet路径>
# 或
python ecg_viewer_diff.py <包含 time/ecg/(可选 nk_miss,my_extra) 的 parquet>
```

### 5.4 训练数据流程（machine_learning）

建议顺序：

1. `10s_chunks.ipynb`：切片
2. `good_bad_split_by_threshold.ipynb`：粗分
3. `save_good_bad_jpg.ipynb`：导出待人工复核图片
4. `b2g_from_jpg.py`：回写 bad2good
5. `b2g_concat.py`：汇总样本
6. `split_and_train.py` 或 `cnn_3classes.py`：训练

## 6. 数据约定

常见字段：

- 采集日志：`time`, `ecg`, `lead`
- 差异标注：`nk_miss`, `my_extra`
- 训练样本：`ecg_raw`, `label`, `label_int`

标签语义：

- `good`: 可用高质量信号
- `bad`: 明显不可用信号
- `bad2good`: 从 bad 中人工纠正出的可用片段

## 7. 当前状态与已知问题

- 仓库中代码、notebook 和数据文件混放，偏实验形态。
- `machine_learning/split_and_train.py` 与 `machine_learning/predict/split_and_train.py` 存在重复代码。
- 根目录缺少统一 CLI 与自动化测试。
- `pyproject.toml` 仅包含最小打包信息，依赖声明不完整。

## 8. 建议下一步

- 抽取统一配置（串口参数、采样率、路径）到单独配置层。
- 将训练与推理脚本去重并模块化。
- 增加 `requirements.txt` 或锁文件（如 `poetry.lock`/`uv.lock`）。
- 补充最小回归测试（峰值检测、HRV 指标、数据切片）。

## 9. 免责声明

本仓库用于研发与实验，不构成医疗诊断系统。
