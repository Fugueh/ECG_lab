# ECG_lab / app

`app` 目录放的是两类桌面侧工具：

- `monitor/`
  - 从串口实时接收 ECG 数据
  - 实时显示波形、心率和部分 HRV 指标
  - 同时把原始数据落盘成 CSV
- `viewer_gui/`
  - 离线查看已经保存的 ECG 文件
  - 用滑块按时间窗口浏览长记录
  - 用于人工检查、标注辅助和差异对比

这部分代码偏“实验室桌面工具”，重点是能快速接设备、看信号、存日志，而不是做成完整的安装包应用。

## 目录结构

```text
app/
├─ monitor/
│  ├─ configuration.py
│  ├─ functions.py
│  ├─ monitor_50hz.py
│  ├─ monitor_250hz.py
│  ├─ roast_monitor.py
│  ├─ csv2parquet.py
│  ├─ all_csv2parquet.sh
│  └─ roast.ico
└─ viewer_gui/
   ├─ ecg_viewer.py
   ├─ ecg_viewer_multi.py
   ├─ ecg_viewer_diff.py
   └─ ecg_viewer_label.py
```

## 依赖

常用依赖包括：

- `pyserial`
- `numpy`
- `pandas`
- `scipy`
- `pyqtgraph`
- `PyQt5`
- `pyarrow`

如果要运行 monitor 或 viewer，建议先确认当前 Python 环境里这些包都已经装好。

## monitor

`monitor/` 负责实时采集和显示。

### 共享模块

- `configuration.py`
  - 串口配置
  - 采样率
  - 窗口长度
  - 共享缓存变量
- `functions.py`
  - 串口读取
  - frame 解析
  - RR / HR / HRV 计算
  - 曲线更新与文本 HUD 辅助函数

当前 `configuration.py` 默认配置里最关键的是：

- 串口：`COM3`
- 波特率：`115200`
- 默认采样率：`50 Hz`

如果接入设备不是这个串口，通常先改这里。

### `monitor_50hz.py`

适用于逐点读取的串口流。

主要行为：

- 从串口按 `ecg,lead_off` 格式读取样本
- 实时显示最近一个时间窗口的 ECG 曲线
- 用峰值检测估计 RR interval 和心率
- 计算并显示 `SDNN` / `RMSSD`
- 落盘为：

```text
ecg_log_YYYY-MM-DD_HHMMSS.csv
```

输出列：

- `time`
- `ecg`
- `lead`

运行方式：

```powershell
python app\monitor\monitor_50hz.py
```

### `monitor_250hz.py`

适用于按 frame 接收的高采样率数据。

当前逻辑假定一帧包含：

- 帧头
- `t0_us`
- `lead_off`
- 5 个采样点

主要行为：

- 非阻塞读取串口字节流
- 解析 frame
- 把 frame 中的 5 个点全部写入原始日志
- 用每帧的中位数生成较平滑的显示点
- 实时计算 HR / HRV
- 落盘为：

```text
raw_record_YYYY-MM-DD_HHMMSS.csv
```

运行方式：

```powershell
python app\monitor\monitor_250hz.py
```

### `roast_monitor.py`

这是一个更轻量、带“吐槽文案”的 mini monitor。

特点：

- 窗口更小
- 常驻顶层显示
- 会根据心率区间显示不同文案和颜色
- 也会把实时数据写到 `raw_record_*.csv`

运行方式：

```powershell
python app\monitor\roast_monitor.py
```

### `csv2parquet.py`

把 monitor 生成的 CSV 转成 parquet，便于后续分析和压缩存储。

运行方式：

```powershell
python app\monitor\csv2parquet.py path\to\file.csv
```

对应的批量版本是：

- `all_csv2parquet.sh`

## viewer_gui

`viewer_gui/` 负责离线浏览 ECG 文件。

目前 viewer 主要支持：

- `csv`
- `parquet`

常见输入列至少需要：

- `time`
- `ecg`

某些差异可视化脚本还会额外使用：

- `nk_miss`
- `my_extra`

### `ecg_viewer.py`

最基础的单窗 viewer。

特点：

- 支持从命令行传入 ECG 文件路径
- 支持 `csv/parquet`
- 默认按 `10 s @ 250 Hz` 窗口显示
- 用滑块浏览整段记录

运行方式：

```powershell
python app\viewer_gui\ecg_viewer.py path\to\ecg.parquet
```

如果不传路径，会使用脚本里写死的默认示例文件。

### `ecg_viewer_multi.py`

多窗 viewer，用 4 个连续窗口加一个 detail 窗口查看长记录。

特点：

- 上方 4 个主图按时间顺序连续排开
- 下方 1 个 detail 图固定显示当前起点后的 10 秒
- 适合快速扫长时间 ECG

运行方式：

```powershell
python app\viewer_gui\ecg_viewer_multi.py path\to\ecg.parquet
```

### `ecg_viewer_diff.py`

用于查看算法差异标记。

主要约定：

- 蓝色点：`nk_miss`
- 橙色点：`my_extra`

适合拿来对比 NeuroKit 与自定义逻辑之间的差异位置。

运行方式：

```powershell
python app\viewer_gui\ecg_viewer_diff.py path\to\diff.parquet
```

### `ecg_viewer_label.py`

这也是一个差异可视化 viewer，功能上和 `ecg_viewer_diff.py` 有重叠，但结构更旧、更偏脚本化。

如果只是日常使用，优先考虑：

- `ecg_viewer.py`
- `ecg_viewer_multi.py`
- `ecg_viewer_diff.py`

## 数据流关系

一个常见流程是：

1. 用 `monitor_50hz.py` 或 `monitor_250hz.py` 接设备并保存 CSV
2. 用 `csv2parquet.py` 转成 parquet
3. 用 `viewer_gui/` 下的脚本离线检查数据质量
4. 再把记录送到 `machine_learning/` 目录下的预处理和训练流水线

## 现状说明

- 这套工具明显带有实验脚本风格，路径和默认文件名里还保留了一些本地使用习惯。
- 多个文件里有中文注释编码不一致的问题，但不影响脚本主逻辑理解。
- monitor 侧很多参数现在直接写在脚本或 `configuration.py` 里，还没有统一成配置文件或命令行参数。
