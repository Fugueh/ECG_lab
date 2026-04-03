# ECG Lab

ECG Lab 是一个面向 ECG 时序信号处理的工程化实验仓库，覆盖实时采集、离线清洗、固定窗口切片、指标提取、数据注册表维护和训练脚本。

这次整理后的目标不是把它包装成“论文复现仓”，而是让它更接近工业项目应有的形态：

- 统一依赖声明
- 统一配置入口
- 统一命令行入口
- 最小可测试核心模块
- 减少脚本中的硬编码路径

## What It Solves

项目围绕一条典型的工业时序数据链路展开：

1. 采集连续 ECG 信号
2. 计算 HR / RR / HRV 等指标
3. 保存原始日志并转换为 Parquet
4. 清洗原始记录
5. 将长记录切成固定长度 chunk
6. 构建 record / chunk registry
7. 为后续标注、训练和评估提供统一输入

## Repository Layout

```text
ECG_lab/
├─ app/
│  ├─ monitor/               # 实时采集与监控工具
│  └─ viewer_gui/            # 离线浏览与复核工具
├─ ecg_core/                 # RR/HR/HRV 等核心算法
├─ ecg_lab/                  # 共享配置、CLI、pipeline
├─ machine_learning/         # 预处理、注册表、训练脚本
├─ tests/                    # 最小测试集
├─ requirements.txt
├─ requirements-dev.txt
└─ pyproject.toml
```

## Installation

建议使用 Python 3.10+。

基础安装：

```bash
pip install -r requirements.txt
```

开发环境：

```bash
pip install -r requirements-dev.txt
```

或者直接按包安装：

```bash
pip install -e .[dev,ml,monitor]
```

## Configuration

项目现在支持通过环境变量统一配置数据根目录和监控参数。

常用变量：

```bash
ECG_LAB_DATA_ROOT=/path/to/data/250hz
ECG_LAB_SERIAL_PORT=COM3
ECG_LAB_BAUD=115200
ECG_LAB_MONITOR_FS=50
ECG_LAB_TIME_WINDOW=10
```

如果没有设置 `ECG_LAB_DATA_ROOT`，代码会优先尝试历史默认路径 `E:/ECG_data/250hz`，否则回退到仓库内的 `data/250hz`。

## CLI

现在可以通过统一命令行入口运行核心数据流程：

```bash
python -m ecg_lab.cli --help
```

示例：

```bash
python -m ecg_lab.cli csv2parquet app/monitor/ecg_log_2026-03-26_010000.csv
python -m ecg_lab.cli clean-raw --sampling-rate 250
python -m ecg_lab.cli build-chunks --fs 250 --chunk-length-s 10
python -m ecg_lab.cli update-record-registry --fs 250 --chunk-length-s 10
python -m ecg_lab.cli update-chunk-registry
```

安装为包后，也可以使用：

```bash
ecg-lab --help
```

## Backward-Compatible Scripts

为了不打断原有使用习惯，这些脚本仍然保留，但内部已经改为走共享配置和 pipeline：

- `app/monitor/csv2parquet.py`
- `machine_learning/preprocess/nk_raw2clean.py`
- `machine_learning/preprocess/raw_record2chunk.py`
- `machine_learning/registry/update_record_registry.py`
- `machine_learning/registry/update_chunk_registry.py`

## Tests

当前补了最小测试，覆盖：

- 数据路径配置解析
- record id 提取
- chunk 切分逻辑
- chunk 元数据构建
- RR/HR/HRV 核心逻辑中的基础行为

运行方式：

```bash
pytest -q
```

## Industrialization Improvements Included

本次工业化整理主要包含：

- 抽出共享配置模块 `ecg_lab/config.py`
- 抽出共享 pipeline 模块 `ecg_lab/pipeline.py`
- 提供统一 CLI `ecg_lab/cli.py`
- 增加 `pyproject.toml` 依赖和 console script
- 增加 `requirements.txt` / `requirements-dev.txt`
- 给关键数据流程补最小测试
- 修复 `ecg_core/rr_hr_hrv.py` 中会影响导入和测试的坏字符串问题

## Known Gaps

虽然仓库已经比原来更接近工业项目，但仍有一些值得继续补的地方：

- 训练模块还没有统一成单一入口
- 监控 GUI 仍然依赖串口和本地桌面环境
- 数据 schema 还没有完全形式化
- 缺少 CI、lint、格式化和实验结果报告
- 还没有在线推理或模型监控层

## Disclaimer

本项目用于时序信号处理研究、实验验证和工程练习，不构成医疗诊断系统。
