---
name: overnight-hrv
description: 对 ADS1292R 整夜记录（raw_record_ecgresp_*.parquet）做 HRV 计算、Poincaré 图和异常心律筛查，并用中文出报告。用户说「分析一下这晚的数据」「算 HRV」「画 Poincaré」「有没有早搏/房颤/停搏」「看看睡眠时心率」，或给出一个 raw_record_ecgresp_*.parquet 要求汇报时使用。
---

# Overnight HRV

一条龙：屏蔽导联脱落和体动 → 检测 R 波 → 计算 NN 间期 → 算 HRV（时域、频域、非线性）→ 画 Poincaré 图和整夜趋势图 → 筛查早搏、停搏、心动过缓/过速、房颤样不规则 → **人工看波形复核** → 用中文汇报。

## 步骤

1. **找文件**。仓库根目录可能有，归档在 `E:/ECG_data/ADS1292R/raw_records/`。

2. **跑脚本**。在仓库根目录、用 `ecg_env` 运行。8 小时的记录大约需要 2–4 分钟，命令超时设成 10 分钟：

   ```bash
   D:/Softwares/Miniconda/envs/ecg_env/python.exe .claude/skills/overnight-hrv/scripts/overnight_hrv.py <parquet> [--out DIR] [--fs 250] [--tz Asia/Shanghai]
   ```

   默认输出到 `playground/overnight_hrv_<记录ID>/`。这个目录**不进 git**：`.git/info/exclude` 里已经有 `playground/overnight_hrv_*/`，如果没有就补上。不要改 `.gitignore`，也不要提交输出。

3. **先读 stdout 打印的 report.json 和候选表**，然后**必须用 Read 看图**：
   - `poincare.png` 和 `tachogram.png`：整体形态、脱落段、整夜趋势。
   - `strips_XX.png`：每个早搏候选前后各 4 s 的波形。
   - `zoom_candidates.png`：没有被自动判为伪迹的候选，前 2.5 s、后 1.5 s 的放大图。

   自动分类只是初筛。最终结论以看波形为准，判断规则见下面「复核早搏候选」。

4. **用中文汇报**。格式参照下面「汇报模板」。

## report.json 字段

- `lost_packets` / `time_gaps_gt1s`：传输是否完整。
- `leadoff`：合并后的脱落段（≥30 s），给出起止时间和分钟数。判定条件是固件特征（设备 HR≥130 且 RR=0），或者 10 s 标准差小于正常段的 15%（信号贴平或打满）。
- `usable_h`：剔除脱落和体动后剩下的小时数。
- `kubios_flags`：NeuroKit Kubios 算法的伪迹分类。其中 `longshort` 大多只是呼吸性窦性心律不齐带来的正常波动，**不要当成早搏数量**。
- `hrv`：整夜时域指标（只用 NN 间期）、SD1/SD2，以及 `w5_median_*`（各 5 分钟窗口指标的中位数；频域和 DFA 只在 5 分钟窗口里才有意义）。
- `vagal_windows`：LF/HF<0.5 且 DFA α1<0.75 的窗口，是迷走神经占主导的特征，通常对应深睡眠（N3）。
- `low_hrv_windows`：RMSSD 低于中位数 60% 的窗口，常见于 REM 睡眠、觉醒、翻身，或者脱落前后。
- `premature_candidates`：早搏候选的自动分类计数（明细在 `candidates.csv`）。
- `pauses_gt2s`、`max_rr_ms`、`hr10_min/max`、`brady_lt45_beats`、`tachy_gt100_episodes`：分别对应停搏、最长 RR、10 拍滑动心率的最小/最大值、心动过缓和心动过速。
- `af_windows`：2 分钟窗口里按 nRMSSD>0.1、香农熵>0.7、|TPR−0.667|<0.1 三条同时满足判为房颤样的窗口数。`irregular_not_af_windows` 是不规则、但 TPR 不像房颤的窗口，一般是深睡眠时的呼吸性窦性心律不齐。

## 复核早搏候选

候选条件：RR 比局部中位数和前一个 RR 都短 20% 以上，并且后面跟着一个更长的 RR。

| auto_class | 含义 | 看图时确认什么 |
|---|---|---|
| `artifact: extra detection` | 短 RR 和后一个 RR 之和约等于 1 个周期 | 是 T 波或噪声被误检成 R 波 |
| `artifact: rhythm uninterrupted` | 候选之后 150 ms 以上出现一个未检出的、类似 R 波的尖峰，并且这个尖峰让窦性节律保持等间距（容差 15%） | 心室在 200–300 ms 内处于不应期，不可能再正常传导一次 QRS，所以候选不是心搏 |
| `artifact?: noisy context` | 候选前后各 2 拍和模板的形态相关性低于 0.85 | 是否有体动或基线乱跳 |
| `PVC-like (aberrant QRS)` | 形态和模板相关性低于 0.8，或 QRS 明显变宽 | QRS 是否宽大畸形、T 波是否反向、代偿间歇是否接近完全（RR 之和约等于 2 个周期）。还要排除邻近的体动 |
| `PAC-like (normal QRS)` | 形态正常，但提前出现 | 前面有没有提前的或异常的 P 波（可能埋在前一个 T 波里），代偿间歇是否不完全。还要排除觉醒带来的突然加速：前几秒有没有体动 |

单导联、业余电极，很多情况分不清。说法分三档：「确认为伪迹」「可疑 PAC/PVC」「无法判断」。**不要给出临床诊断。**

## 汇报模板

先用一两句话给结论，然后：

1. **数据概况**：起止时间、时长、丢包情况、脱落段（时间和时长）、可用时长、心搏数、NN 保留比例。
2. **整夜 HRV**：用表格列出平均心率、SDNN、RMSSD、pNN50、SD1/SD2、LF/HF、DFA α1。
3. **睡眠结构线索**：迷走主导窗口（深睡样）、低 HRV 窗口（REM 样或觉醒样）、心率最低的时段。这些只是**线索**，没有脑电，不能说成睡眠分期。
4. **Poincaré 形态**：彗星形（正常）、扇形或复杂形（房颤或频发早搏）、离群点在哪里。
5. **异常心律筛查**：分早搏、停搏、心动过缓、心动过速、房颤五项。早搏要写清楚每个可疑候选的时间、RR 序列和判断依据，伪迹只给个数。心动过速要说明是渐升渐降的窦性加速（多为觉醒）还是突发突止。
6. **结尾说明**：单导联、业余设备，不能替代临床 Holter。只有发现真正可疑的情况（比如成串的宽 QRS、超过 2 s 的停搏、房颤样窗口）时，才建议就医复查。
7. 给出输出目录链接，并用 SendUserFile 把 poincare.png、tachogram.png 和 zoom_candidates.png（如果有）发给用户。

## 已知局限

- 脱落判定用到了固件特征（设备 HR=135、RR=0）。换了别的板子要检查 `leadoff` 是否合理（看 tachogram 上的橙色区域）。
- 频域指标基于 5 分钟窗口、4 Hz 三次样条重采样和 Welch 方法。窗口里 NN 覆盖不足 80% 时直接跳过。
- `ecg_clean.npy` 这类大中间文件不落盘。需要的话在脚本里自行导出。
