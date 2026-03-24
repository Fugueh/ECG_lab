# ECG Lab

ECG Lab 是一个围绕心电信号构建的时序处理实验仓库，覆盖实时采集、信号清洗、节律特征提取、离线质检、样本构建和 1D CNN 训练。

如果你正在以“时间序列处理算法岗 / 信号处理算法岗 / 时序机器学习岗”的视角看这个项目，它重点体现的是：

- 连续生理信号的采集与流式处理能力
- 面向噪声时序的分段、清洗、规则过滤与特征提取能力
- 从原始记录到训练样本的完整数据 pipeline 搭建能力
- 将算法实验做成可复核工具链的工程落地能力

> 说明：本项目偏研发实验与原型验证，不是医疗诊断产品。

## 项目概览

这个仓库解决的是一个典型时序算法问题：如何把连续采集的 ECG 信号，转成可监控、可分析、可标注、可训练的数据资产。

完整链路包括：

1. 串口实时读取 ECG 数据
2. 在线计算 HR / RR / HRV 等时序指标
3. 保存 CSV / Parquet 供离线分析
4. 使用 GUI 工具进行波形复核和差异检查
5. 将长时记录切分为固定长度 chunk
6. 结合规则与人工回标构建 `good / bad / bad2good` 数据集
7. 训练 1D CNN 做片段质量分类

## 这个项目能体现的能力

### 1. 时序信号处理

- 基于采样时间戳估计采样率 `fs`
- 使用峰值检测提取 R-peak
- 从 RR interval 序列计算 HR、SDNN、RMSSD
- 对异常 RR 做物理边界过滤、跳变过滤和插值修复
- 将连续记录切成固定 10 秒窗口，方便建模与标注

对应代码：

- [ecg_core/rr_hr_hrv.py](/D:/GSB_projects/ECG_lab/ecg_core/rr_hr_hrv.py)
- [machine_learning/preprocess/raw_record2chunk.py](/D:/GSB_projects/ECG_lab/machine_learning/preprocess/raw_record2chunk.py)

### 2. 时序数据工程

- 原始记录、清洗记录、chunk、registry 分层管理
- 使用 `record_id` 跟踪数据流转状态
- 增量更新 record/chunk 注册表，避免重复处理
- 支持 CSV 到 Parquet 转换，便于大规模离线分析

对应代码：

- [app/monitor/csv2parquet.py](/D:/GSB_projects/ECG_lab/app/monitor/csv2parquet.py)
- [machine_learning/registry/update_record_registry.py](/D:/GSB_projects/ECG_lab/machine_learning/registry/update_record_registry.py)
- [machine_learning/registry/update_chunk_registry.py](/D:/GSB_projects/ECG_lab/machine_learning/registry/update_chunk_registry.py)

### 3. 时序建模

- 将 10 秒 ECG 片段组织成监督学习样本
- 对单条样本做 z-score 标准化
- 使用 `Conv1d` 建立一维卷积分类模型
- 用分层切分和 `WeightedRandomSampler` 处理类别不平衡

对应代码：

- [machine_learning/predict/split_and_train.py](/D:/GSB_projects/ECG_lab/machine_learning/predict/split_and_train.py)

### 4. 工具化与可解释分析

- 实时监控界面用于在线观察波形和指标变化
- 离线 viewer 支持多窗口浏览和差异定位
- 标注辅助工具帮助把人工复核反馈回写到训练集

对应代码：

- [app/monitor/monitor_50hz.py](/D:/GSB_projects/ECG_lab/app/monitor/monitor_50hz.py)
- [app/monitor/monitor_250hz.py](/D:/GSB_projects/ECG_lab/app/monitor/monitor_250hz.py)
- [app/viewer_gui/ecg_viewer_multi.py](/D:/GSB_projects/ECG_lab/app/viewer_gui/ecg_viewer_multi.py)
- [app/viewer_gui/ecg_viewer_diff.py](/D:/GSB_projects/ECG_lab/app/viewer_gui/ecg_viewer_diff.py)

## 仓库结构

```text
ECG_lab/
├─ app/
│  ├─ monitor/               # 实时采集、监控、日志导出
│  └─ viewer_gui/            # 波形浏览、差异查看、标注辅助
├─ ecg_core/                 # RR/HR/HRV 等核心时序指标计算
├─ machine_learning/         # 预处理、样本构建、registry、训练脚本
├─ debug_tools/              # 最小可运行调试脚本
└─ playground/               # 临时实验与辅助文件
```

## 核心方案

### 1. 在线监控

`app/monitor` 负责从串口读取 ECG 数据并实时显示。项目里同时保留了 50 Hz 和 250 Hz 两套流程，便于适配不同采样方式。

在这个阶段，系统会：

- 读取连续 ECG 点或帧
- 更新可视化窗口
- 在线计算 HR / RR / HRV
- 将采集结果持久化为日志文件

这部分比较接近真实时序系统中的“数据接入 + 流式指标计算”。

### 2. 离线清洗与切片

离线阶段会把长时间原始记录转换为适合分析与训练的固定窗口样本。

当前实现里，核心策略是：

- 对原始记录做清洗
- 以 `10 s x 250 Hz = 2500` 点为单位切 chunk
- 保留 chunk 的起止索引、起止时间和来源记录
- 通过 registry 跟踪处理状态

这部分体现的是典型时间序列任务中的窗口化建模思路。

### 3. 规则 + 人工回标的数据构建

项目不是直接把原始切片拿去训练，而是先做信号质量筛选，再把人工复核结果并回样本集。

当前标签体系：

- `good`：可用片段
- `bad`：明显不可用片段
- `bad2good`：原先被判为 bad、后经人工纠正为可用的片段

这说明项目考虑过真实数据里的噪声、边界样本和弱标签问题，而不是只处理“干净数据集”。

### 4. 一维时序分类

建模部分使用较轻量的 `Conv1d` 网络做 ECG 片段分类，重点不在追求复杂模型，而在于先把数据流、采样策略和训练入口打通。

当前训练脚本中可以看到：

- 单样本标准化
- train/val/test 分层拆分
- 类别不平衡重采样
- 面向一维信号的卷积结构

对于校招 / 社招初中级岗位，这样的项目更容易体现你对“完整时序任务闭环”的理解。

## 适合在简历里怎么描述

可以直接提炼成下面这种风格：

`心电时序处理项目：独立搭建 ECG 从实时采集、信号清洗、R 峰检测、HRV 指标提取、固定窗口切片、人工复核回标到 1D CNN 训练的完整 pipeline，支持连续生理信号的质量评估与离线建模。`

如果你希望更偏算法岗，也可以强调：

- 连续时序信号清洗与异常片段处理
- 滑窗/定窗切片与样本构建
- 一维卷积网络在生理信号分类中的应用
- 类别不平衡处理与数据闭环迭代

如果你希望更偏工程岗，也可以强调：

- 实时采集监控工具开发
- 数据注册表与增量处理流程设计
- CSV/Parquet 数据链路搭建
- 标注辅助与离线分析工具开发

## 快速开始

### 环境

建议 Python 3.10+。

常用依赖包括：

```bash
pip install numpy pandas scipy pyqtgraph pyqt5 pyserial pyarrow scikit-learn torch rich
```

> 仓库当前没有完整依赖锁文件，安装时以实际脚本 import 为准。

### 运行实时监控

先修改 [app/monitor/configuration.py](/D:/GSB_projects/ECG_lab/app/monitor/configuration.py) 中的串口和采样配置，再运行：

```bash
cd app/monitor
python monitor_50hz.py
# 或
python monitor_250hz.py
```

### 运行离线切片

```bash
python machine_learning/preprocess/raw_record2chunk.py
```

### 运行训练脚本

```bash
python machine_learning/predict/split_and_train.py
```

## 当前不足

这部分如果面试官问到，反而是很好的展开点：

- 代码当前仍偏实验仓，配置和路径有硬编码
- 训练脚本与预处理脚本还可以进一步模块化
- 缺少统一 CLI、自动化测试和可复现实验配置
- 目前更偏原型验证，模型评估与部署链路还不够完整

## 下一步优化方向

如果你打算继续把这个项目打磨成求职作品，最值得补的几项是：

- 去掉硬编码路径，统一成配置文件或命令行参数
- 补一个最小 `requirements.txt` 或 `environment.yml`
- 给 `RR/HR/HRV` 和 chunk 切分逻辑补单元测试
- 在 README 里补一张流程图和一组结果图
- 补充实验结果，如样本规模、分类指标、典型错误案例

## 免责声明

本项目用于时序信号处理研究、实验验证和工程练习，不构成医疗诊断系统。
