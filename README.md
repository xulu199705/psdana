# psdana

**可复现的 PSD、频段功率与 QAM 分析工具：Python Golden Reference 与 Go PSD Core。**

psdana 面向离线采样数据分析和 DSP 算法移植，提供数学定义一致的 Periodogram / Welch、
实数及复数 IQ 输入、明确的 Full Scale 参考，以及可供其他语言复用的 Golden Vector。
Python 提供参考计算和独立频谱绘图；Go 提供计算库、CSV 适配和命令行 JSON 输出。
Python 还提供独立的 QAM 接收链、误差指标和星座图，可与同一 IQ 的 PSD/频段功率组合分析。

当前开发快照：**V2.1.0（未创建发布标签）**，基于 V2.0.1。项目遵循 **Correctness First，Performance Second**。

## 功能

- Periodogram 和 Welch，支持任意合法 FFT 长度，包括奇数及非 2 次幂。
- Periodic Hann / Rectangle；可选逐段 mean detrend。
- 复数 IQ 双边 fftshift 频谱；实数单边频谱，正确处理 DC 与 Nyquist。
- 同时输出绝对线性 PSD、dBFS/Hz 密度、ENBW 校准 dBFS 频谱和积分功率。
- 指定有符号频段的 Peak / Average Power；支持点频、部分 bin 积分和周期性 Nyquist 单元。
- float、decimal Q1.15、16-bit hexadecimal Q1.15 CSV；支持表头、列选择和 BOM。
- Python Matplotlib Line 绘图；Go CLI 文本摘要及机器可解析 JSON。
- 17 个冻结 Golden Vector、独立数学测试、SciPy 对照及直接 Python-Go 比较。
- 可复现的 Core / CSV Decode / End-to-End Benchmark，覆盖百万点输入。
- Python 64QAM：RRC matched filter、Fractional Timing Recovery、Residual CFO、Blind Scalar Fit。
- Decision-Directed EVM、径向/切向误差、相位角 RMS，独立发送真值验证及 13 组 QAM Golden。
- Python 星座图：红色空心理想点、半透明亮黄色恢复符号，默认直接 show。

当前不提供实时 PSD、GUI、Web 服务或 Go 绘图。

## 安装

### Python

需要 Python 3.9+。可使用现有 Python/Conda 环境；运行依赖 NumPy、SciPy、Matplotlib，
测试额外使用 pytest。PSD Core 仍仅依赖 NumPy，SciPy 用于 QAM 与独立验证。

```shell
git clone https://github.com/xulu199705/psdana.git
cd psdana
python -m pip install -r python/requirements-test.txt
```

仅运行 Python 时可安装 `python/requirements.txt`。

### Go

需要 Go 1.27.1+。Go module 位于 `go/`，计算依赖固定为 Gonum v0.17.0。

```shell
go -C go mod download
go -C go build -o bin/psdana ./cmd/psdana
```

如 Go 不在 PATH，可将其加入 PATH，或为 Python 辅助脚本使用 `--go` / `PSD_GO` 指定工具链。

## 使用方式

### Python CLI

```shell
# 默认原始 +40 MHz IQ，160 MSPS，Hann，全部样本的一次 FFT
python python/demo.py

# Welch，1024 点 FFT，50% overlap
python python/demo.py --fft-points 1024 --overlap 0.5

# 严格 PSD 密度显示，或禁用交互窗口
python python/demo.py --display dbfs_per_hz
python python/demo.py --no-show
python python/demo.py --freq-left 39000000 --freq-right 41000000 --no-show

# Q1.15 输入
python python/demo.py --input data/generated/T09_q15_iq.csv --sample-format q15

# 同一份真实 IQ：PSD + QAM，默认直接显示两张图，不保存
python python/demo.py --input data/qam64_20MSymPS_160MSPS_RRC0p25.csv --sample-format hex_q15 --qam --symbol-rate 20000000

# 合成 SPS2 QAM；同时指定频段并关闭交互显示
python python/demo.py --input data/generated/qam/Q11_sps2.csv --qam --symbol-rate 80000000 --freq-left -60000000 --freq-right 60000000 --no-show
```

正常绘图直接调用 `plt.show()`，不保存图像。绘图层不会重新读取 CSV 或计算 FFT。
默认输入和相对 `--input` 路径均以项目根目录解析。

### Go CLI

```shell
go -C go run ./cmd/psdana
go -C go run ./cmd/psdana --fft-points 1024 --overlap 0.5 --detrend mean
go -C go run ./cmd/psdana --json
go -C go run ./cmd/psdana --freq-left 40000000 --freq-right 40000000 --json
go -C go run ./cmd/psdana --input data/generated/T09_q15_iq.csv --sample-format q15 --json
```

也可进入 `go/` 后执行 `go run ./cmd/psdana`，或运行编译后的二进制。
Go 不打开窗口；`--json` 时 stdout 仅含完整 PSDResult，错误写入 stderr 并返回非零退出码。
同时提供 `--freq-left` / `--freq-right`（Hz）时，JSON 增加 `power_metrics`；未提供时保持 V2.0.0 结构。
默认输入及相对路径从 cwd 或二进制所在位置向上定位项目根目录。
独立分发二进制时，可使用绝对输入路径和明确的 sample-format。

两种 CLI 均支持采样率、window、FFT points、overlap、detrend、输入格式、header、delimiter、
real/I/Q 列选择。未知的双列顺序必须显式指定，不能自动猜测 I/Q。

## 公开接口

### Python API

将 `python/` 加入 import 搜索路径，或在该目录运行：

```python
import numpy as np
from psd import PSDConfig, compute_psd, analyze_band_power
from psd.csvio import CSVConfig, read_csv
from psd.plotting import plot_psd

samples = np.exp(2j * np.pi * np.arange(1024) / 4)
result = compute_psd(samples, PSDConfig(fs=160e6))
print(result.integrated_power)  # 约 1.0
power = analyze_band_power(result, 39e6, 41e6)
print(power.peak_power_dbfs, power.average_power_dbfs)  # 约 0 dBFS
plot_psd(result, display="dbfs", freq_unit="MHz", show=True)

# capture = read_csv(path, CSVConfig(sample_format="hex_q15"))
# result = compute_psd(capture.samples, PSDConfig(fft_points=1024))
```

### Go API

导入 `github.com/xulu199705/psdana/go/psd` 与可选的 `.../csvio`：

```go
config := psd.DefaultConfig()
config.FFTPoints = psd.FFTPoints{N: 1024} // 或 FFTPoints{All: true}
result, err := psd.ComputeComplexPSD(iqSamples, config)
// 检查 err 后可调用：
power, err := psd.AnalyzeBandPower(result, 39e6, 41e6)
// 实数：psd.ComputeRealPSD(realSamples, config)
// CSV：csvio.ReadCSV(path, csvio.DefaultConfig())
```

Go 的零值配置不表示默认值；请使用 DefaultConfig。
real / complex 由公开接口明确区分，complex128 虚部全零仍按复数处理。
完整必选/可选参数、默认值、返回字段、错误行为与多个示例见
[Python API Reference](python/API.md) 与 [Go API Reference](go/API.md)。

| 接口 | 必选参数 | 可选参数 / 默认值 |
|---|---|---|
| Python compute_psd | samples | config=PSDConfig() |
| Python read_csv | path | config=CSVConfig()，默认 float |
| Python analyze_band_power | result、freq_left_hz、freq_right_hz | 无 |
| Python analyze_qam | complex samples | config=QAMConfig()，64QAM / 160 MSPS / 20 MSym/s |
| Python analyze_iq | samples | psd_config=PSDConfig()、qam_config=None、power_band=None |
| Python plot_psd / plot_constellation | 对应 result | show=True；PSD 另有 display="dbfs"、freq_unit="MHz" |
| Go ComputeRealPSD / ComputeComplexPSD | 对应 samples、config | 无可省略参数；使用 psd.DefaultConfig() |
| Go AnalyzeBandPower | result、left、right | 无 |
| Go ReadCSV / Read | path 或 io.Reader、config | 无可省略参数；使用 csvio.DefaultConfig() |

Python QAM 程序化组合示例（在 python/ import 路径下）：

```python
from psd import analyze_iq, PSDConfig
from psd.csvio import read_csv, CSVConfig
from psd.qam import QAMConfig
x = read_csv("data/qam64_20MSymPS_160MSPS_RRC0p25.csv",CSVConfig(sample_format="hex_q15")).samples
analysis = analyze_iq(x,PSDConfig(),QAMConfig(),(-15e6,15e6))
print(analysis.qam_metrics.evm_pct_rms,analysis.power_metrics.average_power_dbfs)
```

该例路径相对进程 cwd；库函数不执行 I/O 或显示。qam_config=None 时只保留原 PSD/Power 流程。
QAMResult JSON 使用 to_dict()；Python CLI 当前为文本输出，Go CLI 保留原 JSON 结构。
当前没有 Go QAM API。

### 配置与结果

| 配置 | 默认值 | 含义 |
|---|---|---|
| fs | 160e6 | 采样率 Hz |
| window | hann | hann / rectangle |
| fft_points | all | 全部输入或指定正整数 N |
| overlap | 0.5 | Welch overlap，范围 [0,1) |
| detrend | none | none / mean |

输入长度 M：`all` 或 N=M 使用 Periodogram；N<M 使用 Welch；N>M 报错，不隐式补零。
重叠点数为 `floor(N*overlap)`，只使用完整段，尾部丢弃，在线性 PSD 域平均后转换为 dB。

PSDResult 提供 `frequency_hz`、`psd_linear`、`psd_dbfs_per_hz`、`rbw_power_dbfs`、
FFT/采样率/df、ENBW/Coherent Gain/窗口平方和、分段/尾部计数、输入类型和积分功率。
JSON 的 dB 数组用 `null` 表示零功率的负无穷，不使用非标准 Infinity/NaN。

## 数学定义与单位

```text
Periodic Hann: w[n] = 0.5 - 0.5*cos(2*pi*n/N)
Pxx[k] = |FFT(x*w)[k]|² / (fs*sum(w²))
CG = sum(w)/N
ENBW = fs*sum(w²)/sum(w)²
PSD_dBFS/Hz = 10*log10(Pxx/P_FS)
RBW_power_dBFS = 10*log10(Pxx*ENBW/P_FS)
Integrated power = sum(Pxx)*(fs/N)
```

FFT 为未归一化 forward FFT。复数 Full Scale 是单位模单音，P_FS=1；
实数 Full Scale 是单位峰值正弦，P_FS=0.5。Q1.15 按 signed int16/32768 转换。
不按当前文件峰值归一化，不裁剪超过 0 dBFS 的结果。

默认显示 RBW 校准 dBFS；噪声密度和功率积分使用严格 PSD。
不能将 dBFS/Hz 与 dBFS 混用，也不能直接相加 ENBW 校准 bin 替代 PSD 积分。
普通相干满幅单音的校准峰值约为 0 dBFS；非相干单音存在 scalloping loss。
一般加窗序列的 PSD 积分恢复窗加权功率估计，不保证等于未加窗平均功率。
Hann N=1 非法；N=2 及 DC/Nyquist 等边界详见 API 文档。

### 频段与点频功率

`analyze_band_power` / `AnalyzeBandPower` 接收已算好的 PSDResult，不读取 CSV、不重算 FFT、不修改输入。
频率边界严格满足 `-fs/2 <= left <= right <= fs/2`。

- **Peak Power**：所有与频段有正宽度重叠的 bin 中，最大的 `Pxx*ENBW`，转换为 dBFS。
- **Average Power**：时间平均带内功率估计，`sum(Pxx*overlap_width)`，转换为 dBFS；不是 bin/dB 的算术平均。
- **点频**：left=right，选择最近的 bin，Peak 和 Average 均使用其 RBW 校准功率；距离或功率相同选较低频率。

积分单元以 FFT 网格中心为中心，宽度 df；Nyquist 单元超出边界的部分周期性折回。
右边界为排除端，`right=+fs/2` 不增加 +fs/2 bin；`left=right=+fs/2` 特例选择严格小于该边界的最高中心。
全带积分恢复 PSDResult.integrated_power。实数单边 PSD 拆为等效双边谱，内部正负频点各承担一半，DC/偶数 Nyquist 唯一。
因此实数单音在单侧频段中的峰值通常比原单边图低约 3 dB，P_FS=0.5 未改变。

PowerResult 提供边界、点频标志、峰值频率、Peak/Average dBFS、绝对线性功率和参与 bin 数。
零功率时峰值频率无效，dB 为 -Inf；标准 JSON 使用 null。点频的 band_power_linear 表示所选 bin 的 RBW 功率。
非零频段的功率估计依赖 df 和窗函数：Hann 相干单音的单 bin 积分为总功率的 2/3，包含完整主瓣才恢复总功率。
极端输入导致 float64 中间值溢出时明确报错；未引入幅度归一化或功率裁剪。

## 数据与验证

```text
data/       原始 CSV、10 组 PSD 输入、17 组冻结 PSD Golden；另有 generated/qam 与 golden/qam
python/     PSD/Power、QAM、CSV/packed IQ、Matplotlib、pytest、比较和性能脚本
go/         Gonum Core、CSV、CLI、数学/Golden/集成测试、Benchmark、报告
```

随附原始 capture 为表头 `q,i`、8192 点、16-bit hexadecimal IQ。
默认配置得到 +40 MHz 主峰，约 -9.087628044 dBFS，积分功率约 0.123377849348。
Golden 是跨语言回归契约；解析测试和 SciPy 作为独立正确性依据。

真实 QAM 捕获是 q,i 表头的 16-bit HEX IQ，共 16384 样本；明确选择 hex_q15。
默认 160 MSPS / 20 MSym/s、β=.25、span10 得到 EVM 2.596190680% RMS、CFO 0 Hz、
定时 .0625 symbol、2026 个有效符号。此真实捕获无发送符号参考，结果属于 Blind Decision-Directed EVM。
幅度与相位百分比是残余误差矢量的正交分量，满足 EVM²=Amplitude²+Phase²；
Phase Error (%) 与角度 RMS 不同。固定 gain/phase/CFO 被规定的同步步骤补偿，没有自适应均衡器。
有限 RRC、短记录均值去除、超范围 CFO 及未知信道会影响结果，详见 Python API 的限制说明。

```shell
python python/qam_gen.py
python python/generate_qam_golden.py
```

只生成 QAM 子目录；12 组固定 seed 合成数据保存发送真值，QAM Golden 独立 index，
不替换 17 组 PSD Golden。日常测试应复用冻结向量，不重新生成以掩盖差异。

```shell
python -m pytest python/tests -q
go -C go fmt ./...
go -C go vet ./...
go -C go test ./...
go -C go test -v ./...
python python/compare_go.py
python python/compare_power_go.py
```

原数据与 Golden 已随仓库提供。需要复现 Phase 1 数据时，可运行 `generate_test_data.py` 和
`generate_golden.py`；移植验证期间应保持冻结文件不变。
有兼容 C 工具链时可额外运行 `go -C go test -race ./...`。

## 性能评估

```shell
python python/benchmark.py --repeats 5 --iterations 3
go -C go test -run '^$' -bench=. -benchmem ./...
```

配对脚本用固定 seed 的同一输入测量 Core、CSV Decode 和 End-to-End，排除编译、
进程启动、输入生成、绘图和 JSON，输出 median/p90、吞吐量及 Go 分配统计。
百万点临时 CSV 位于忽略的 `.cache/bench/`，不会作为发布数据提交。
Go B/op 表示分配字节，不能与峰值 RSS 或 Python tracemalloc 直接等同。

实际数值误差、性能结果和已发现边界见 [工程报告](go/reports/phase2_validation.md)
与 [完整性能表](go/reports/performance.md)。性能结论与输入规模、FFT 方法和环境有关。
V2.0.1 数值边界、频段分析和安全检查见 [验证报告](go/reports/v2.0.1_validation.md)。
V2.1.0 QAM 算法、真实输入、独立真值验证和实测指标见 [QAM 验证报告](python/reports/v2.1.0_qam_validation.md)。

## 开发路线图

| 阶段 | 状态 | 范围 |
|---|---|---|
| Phase 1 | 完成 | Python 数学参考、CSV、绘图、独立验证、Golden Vector |
| Phase 2 | 完成 | Go Core/CSV/CLI、完整跨语言比较、实测性能与 V2.0.0 |
| V2.0.1 | 完成 | 频段/点频功率分析、零输入峰值及数值边界修复 |
| V2.1.0 | 开发验证完成，未打 tag | Python QAM Golden、同步/误差分析/星座图、真实捕获验收；Go 代码不变 |
| Go QAM | 规划 | 移植冻结的 QAMConfig/Result、RRC/插值/CFO/scalar 数学契约，复用独立 QAM Golden |
| Phase 3 | 规划 | FFT workspace/跨调用复用、CSV 分配优化、性能剖析、大质因子精度与性能覆盖 |
| 后续 | 评估 | 在保持数学契约的前提下扩展其他语言及应用层 |

Phase 3 优先根据实测瓶颈优化，并在每次更改后复跑 Golden、解析测试和直接比较。
并行 Welch、实时处理与前端属于后续独立设计，不是当前接口的既有能力。
