# Python API reference — V2.1.2

将仓库 `python/` 放入 Python import 搜索路径；下面的文件路径均相对仓库根目录。
API 的路径参数相对调用进程 cwd，只有 `demo.py --input` 相对项目根目录。
必选表示调用时必须传入；可选表示可以省略并使用所列默认值。配置类的全部字段均可选。
除读取文件会抛出 OSError 外，非法算法参数/样本通常抛出 ValueError。函数不吞掉异常。

## PSD、Power 与组合分析

| 函数 / 导入 | 必选参数 | 可选参数及默认值 | 返回 |
|---|---|---|---|
| `psd.compute_psd` | `samples`：一维非空实数/复数序列 | `config=PSDConfig()` | PSDResult |
| `psd.analyze_band_power` | `result`、`freq_left_hz`、`freq_right_hz` | 无 | PowerResult |
| `psd.analyze_iq` | `samples` | `psd_config=PSDConfig()`、`qam_config=None`、`power_band=None`、keyword-only `dc_mode="legacy_mean"` | IQAnalysis |
| `psd.csvio.read_csv` | `path`：str/Path | `config=CSVConfig()` | CSVData |
| `psd.plotting.plot_psd` | `result` | `display="dbfs"`、`freq_unit="MHz"`、`show=True` | `(figure, axes)` |
| `psd.core.power_to_db` | `power`：非负有限功率数组、`reference_power`：有限正数 | 无 | dB ndarray，零功率为 -Inf |
| `PowerResult.to_dict` | 已有实例 | 无 | 标准 JSON-ready dict；-Inf 和无峰值编码为 None |

`analyze_iq` 不读取文件、不绘图。返回对象的 `psd` 总有结果，`power_metrics` 与 `qam_metrics`
按请求存在或为 None。`power_band=(left,right)` 的两个值均必选，单位 Hz。
QAM 开启时输入必须为 complex，两个配置的采样率必须相等；未开启时仍支持 real。
PSD 不由 QAM 接收机的幅度归一化、DC 去除或 Q polarity 配置改变。

### PSDConfig

| 字段 | 必选/可选 | 默认值 | 类型、单位与范围 |
|---|---|---|---|
| fs | 可选 | 160e6 | finite float >0，Hz |
| window | 可选 | "hann" | "hann" / "rectangle" |
| fft_points | 可选 | "all" | "all" 或正整数 N，N<=样本数；不是浮点整数/数字字符串 |
| overlap | 可选 | 0.5 | finite float，[0,1)；Welch 生效 |
| detrend | 可选 | "none" | "none" / "mean"，每段加窗前处理 |

`all` 或 N=M 为 Periodogram；N<M 为 Welch，floor(N*overlap)，不足整段尾部丢弃，不补零。
复数 `I+jQ` 为双边 fftshift PSD，实数为单边。P_FS 分别为 1、0.5。
完整 PSDResult 字段及窗口/归一化公式见 [README](README.md#golden-api)。

### CSVConfig 与 CSVData

| 字段 | 必选/可选 | 默认值 | 类型、语义 |
|---|---|---|---|
| sample_format | 可选 | "float" | "float" / "q15" / "hex_q15"；后两种 int16/32768 |
| input_type | 可选 | "auto" | "auto" / "real" / "iq" |
| header | 可选 | "auto" | "auto" / "yes" / "no" |
| delimiter | 可选 | None | 自动识别逗号/分号/Tab；或一个分隔字符 |
| real_column | 可选 | None | 名称或零基整数索引，声明 real 数据 |
| i_column | 条件必选 | None | 不存在可识别 I/Q 表头时与 q_column 一同指定，或用 input_type="iq" 明确无表头顺序 |
| q_column | 条件必选 | None | 与 i_column 同时使用；自动识别不猜测未知列顺序 |

CSVData 返回 `samples`、`path`、`header`（tuple 或 None）、`delimiter`、`columns`
（按 real 或 I/Q 角色排序的索引 tuple）、`sample_format` 和 `sample_count` 属性。
没有基于文件峰值的自动归一化。Packed IQ 使用独立适配器：

```python
from psd.iqio import read_packed64
# path 必选；以下参数均可选且为默认值，关键字传参。
samples = read_packed64("data/generated/qam/Q10_packed64.csv",
                        column=0, header=True, valid_column=None)
```

`column` 为非负整数索引；`header` 必须明确为 bool；`valid_column` 可选非负索引且不同于
数据列，只接受十进制 0/1，0 行丢弃。每行恰好 16 个 HEX digits，允许 0x 前缀。
低 32-bit 是较早样本，高 32-bit 是较晚样本；每个样本 I 在低 16-bit，Q 在高 16-bit。
返回 complex128；不补齐奇数样本，不猜测 valid、表头、字节序或数据格式。

### PowerResult 与绘图

`-fs/2 <= left <= right <= fs/2`，NaN/Inf 与越界非法。
非零频段 `[left,right)` 以周期性 centered bin 单元的重叠宽度积分：
`band_power_linear=sum(Pxx*width)`。Peak 使用参与 bin 的最大 `Pxx*ENBW`。
两边相等时选最近中心，Peak=Average=RBW 校准功率；等距选较低频率。
点频 +fs/2 选 signed 频率表示中严格低于边界的最高中心。

| PowerResult 字段 | 单位/含义 |
|---|---|
| freq_left_hz / freq_right_hz | 请求边界，Hz |
| is_point | bool，边界相等 |
| peak_frequency_hz | bin 中心 Hz；零功率 None |
| peak_power_dbfs / average_power_dbfs | dBFS，零功率 -Inf |
| band_power_linear | 输入单位平方；点频为该 bin RBW 功率 |
| contributing_bins | 参与的 distinct signed bin 数，点频为 1 |

real 单边 PSD 在功率分析中拆成等效双边：内部正负各一半，DC/Nyquist 唯一；单侧实数
单音 Peak 通常比原单边图低 3.0103 dB，P_FS 未改变。完整带积分等于 integrated_power。
Average 不是 mean(PSD) 或 mean(dB)。严格 PSD 密度是 dBFS/Hz，RBW/带内功率是 dBFS。

绘图 `display="dbfs"/"dbfs_per_hz"`，`freq_unit="Hz"/"kHz"/"MHz"/"GHz"`。
`show=False` 可自动化测试；默认 plt.show，不保存，不重新读取或计算。

## QAM API

| 函数（`psd.qam`） | 必选参数 | 可选参数及默认值 | 返回 |
|---|---|---|---|
| analyze_qam | samples：一维非空有限 complex IQ | config=QAMConfig()、keyword-only dc_mode="legacy_mean" | QAMResult |
| recover_symbols | samples | config=QAMConfig()、keyword-only dc_mode="legacy_mean" | 全量有效符号、判决及诊断 dict，未做绘图抽样 |
| rrc_taps | beta、span_symbols、sps | 无 | 单位能量实数 FIR ndarray |
| qam_constellation | 无 | order=64 | 完整 complex 标准星座 ndarray |
| qam_slicer / slicer | symbols：complex 序列 | order=64 | `(decisions, indices)` |
| scalar_qam_fit | symbols：至少 32 个 complex 符号 | order=64、iterations=5、keyword-only dc_mode="legacy_mean" | eq/decisions/indices/evm_pct/dc/complex_gain/coarse_phase_deg dict |
| search_residual_cfo | symbols、config：QAMConfig | keyword-only dc_mode="legacy_mean" | scalar fit dict + cfo_hz/boundary/search count/grid resolution |
| qam_error_metrics | symbols、decisions：同形非空 complex 数组，decisions 非零 | 无 | 四个 RMS 指标 dict |
| QAMResult.to_dict | 已有实例 | 无 | 标准 JSON-ready dict |
| `psd.qam.plotting.plot_constellation` | result：QAMResult | show=True | `(figure, axes)` |

`recover_symbols` 中 `eq` 是全量校正符号，`decisions` 是最终理想判决；
`symbols_raw` 是匹配滤波/定时后但尚未 CFO/标量补偿的符号。
`first_symbol_index` 是裁剪/中心截取后的首符号周期索引；`timing_phase_up` 是插值相位索引。
返回中间数组供诊断使用，不保证共享内存数组可安全修改；正式结果使用 analyze_qam。
scalar gain 应用于 CFO 校正后、已去 DC 的符号，不是 ADC 绝对增益校准。

### QAMConfig

所有字段可选，frozen dataclass；SPS=sample_rate/symbol_rate 必须为整数 >=2。
不支持通过隐式重采样修正非整数 SPS。

| 字段 | 默认值 | 类型/单位/约束 |
|---|---|---|
| sample_rate_hz | 160e6 | 有限正数，Hz |
| symbol_rate_hz | 20e6 | 有限正数，Sym/s |
| qam_order | 64 | 整数 16/64/256，主验收为 64QAM |
| rrc_beta | 0.25 | 有限数，[0,1] |
| rrc_span_symbols | 10 | 正整数，symbols；taps 长度 span*SPS+1，偶数长度补到奇数 |
| timing_interp | 16 | 正整数，每符号候选相位数 SPS*timing_interp |
| timing_kaiser_beta | 8.0 | 有限非负数，resample_poly 的 Kaiser β |
| extra_edge_trim_symbols | 6 | 非负整数；每侧总 trim=span//2+extra |
| enable_cfo_correction | True | bool；False 时 Frequency Error 为 None，未估计 |
| max_residual_cfo_hz | 5000.0 | 有限非负数且 <symbol_rate/2；开启搜索时必须 >0 |
| cfo_coarse_steps | 81 | 奇整数 >=3 |
| cfo_fine_steps | 41 | 奇整数 >=3 |
| cfo_search_max_symbols | 12000 | 整数 >=min_analysis_symbols；中心子集，仅用于搜索 |
| max_analysis_symbols | 30000 | 整数 >=min_analysis_symbols；中心截取，正式指标使用全部选中符号 |
| constellation_points | 5000 | 正整数，仅用于绘图数据均匀抽样，不改变统计 |
| q_sign | 1 | +1/-1；只影响 QAM 的 Q polarity，不改变 PSD |
| scalar_fit_iterations | 5 | 正整数；复数单标量 LS 迭代次数 |
| min_analysis_symbols | 200 | 整数 >=32；不足时报错 |
| max_decision_evm_pct | 12.0 | 有限正数，超过阈值拒绝输出；不是误差缩放系数 |

min/max 值以配置验证和观测长度检查为准；有限但不能表示的中间运算也明确报错。
零功率、非有限输入、real 输入、短捕获、低星座占用或高 Decision EVM 均不输出可信分析。
占用/残差检查不能证明盲接收机对任意信号锁定，diagnostics.status 为 candidate 或 warning。

### QAMResult、单位与数学契约

| 字段 | 单位/含义 |
|---|---|
| qam_order / sample_rate_hz / symbol_rate_hz / samples_per_symbol | 调制阶数、Hz、Sym/s、整数 SPS |
| evm_pct_rms | Decision-Directed EVM，% RMS |
| amplitude_error_pct_rms | 误差矢量径向分量，% RMS；不是 ADC 绝对增益误差 |
| phase_error_pct_rms | 误差矢量切向分量，% RMS；不是角度 RMS |
| phase_error_deg_rms | angle(y*conj(d)) 主值角度的 RMS，degree |
| frequency_error_hz | 有符号 residual CFO，Hz；未估计 None |
| timing_offset_symbols | 选中定时相位 / (SPS*interp)，[0,1) symbol |
| recovered_symbol_count | 正式统计的有效符号总数 |
| constellation_i/q | 最终校正星座的可复现均匀抽样，实数 ndarray |
| ideal_i/q | 全部标准理想星座点，实数 ndarray |
| diagnostics | 完整 config、gain/DC、timing curve、裁剪、CFO 范围/边界/搜索点数、状态与告警 |

64QAM levels=±1,±3,±5,±7，除以 sqrt(42)，完整星座平均功率为 1。
顺序 I-major/Q-minor：从低 I 到高 I，每个 I 内从低 Q 到高 Q；index=i_index*sqrt(M)+q_index。
最近点等距时选较低 level。四阶矩粗相位只能恢复模 90°，不恢复发送 bit mapping。

```text
e=y-d; D=sum(|d|²)
EVM(%)=100*sqrt(sum(|e|²)/D)
radial=real(e*conj(d))/|d|
tangential=imag(e*conj(d))/|d|
Amplitude(%)=100*sqrt(sum(radial²)/D)
Phase(%)=100*sqrt(sum(tangential²)/D)
EVM²=Amplitude²+Phase²
AngleRMS(deg)=sqrt(mean((angle(y*conj(d))*180/pi)²))
```

接收机执行一次 RRC 匹配滤波和一次 polyphase 插值，相位搜索评分采用 Blind Scalar Fit；
随后在中心符号子集进行粗/细 CFO 搜索，再对全部选中符号校正、去 DC、归一化、判决和标量拟合。
正 CFO 模型为 exp(+j*2π*df*k/symbol_rate)，接收端负号去旋转。
靠近范围边界（一个 coarse grid interval 内）告警；超范围频偏可能收敛到局部最小，
不保证一定触发边界告警。未实现 CFO 跟踪、定时跟踪、自适应 FIR/CMA/LMS/DFE 或 image cancellation。
观察时间短、噪声、IQ/信道失真会影响 CFO 与判决；不要把频谱峰值当成 QAM CFO。

QAM 符号归一化只服务解调度量，不改变原始 IQ 或 PSD 的 Full Scale。
正式 EVM 基于最终判决，真实采样没有 TX truth，不能称为 Data-Aided EVM。
合成真值验证只搜索整数符号对齐和 90° 象限，使用盲接收机同一输出；不再次拟合参考来降低误差。
有限记录均值去除会把非零样本均值也视为 DC，有限 span RRC 留下 ISI，因此理想输入不保证 EVM=0。

JSON 使用 `result.to_dict()` 和 `json.dumps(...,allow_nan=False)`。
复数诊断分离为 real/imag，未估计 CFO 为 null；其余非有限计算结果拒绝，不生成 NaN/Infinity。
新 QAM Golden 位于 `data/golden/qam/index.json`，输入路径相对向量目录；不修改旧 PSD index。

## 可执行 API 示例

### 1. 复数相干单音、完整带及点频

```python
import numpy as np
from psd import PSDConfig, compute_psd, analyze_band_power
x = np.exp(2j*np.pi*np.arange(1024)/4)
r = compute_psd(x)                      # 全部默认配置
full = analyze_band_power(r,-80e6,80e6)  # Average 约 0 dBFS
point = analyze_band_power(r,40e6,40e6)  # Peak=Average 约 0 dBFS
```

### 2. 实数、非 2 次幂 Welch、显式无表头列索引

```python
from psd import PSDConfig, compute_psd
from psd.csvio import CSVConfig, read_csv
capture = read_csv("data/generated/T03_real_full_scale_sine.csv")
r = compute_psd(capture.samples,PSDConfig(fft_points=333,window="rectangle",overlap=.25,detrend="mean"))
# 无表头双列：明确第一列 I、第二列 Q，而非猜测。
# capture = read_csv("capture.csv",CSVConfig(header="no",input_type="iq",i_column=0,q_column=1))
```

### 3. 真实 QAM + PSD + 带内功率、统一一次显示

```python
import matplotlib.pyplot as plt
from psd import analyze_iq, PSDConfig
from psd.csvio import read_csv, CSVConfig
from psd.qam import QAMConfig
from psd.plotting import plot_psd
from psd.qam.plotting import plot_constellation
x = read_csv("data/qam64_20MSymPS_160MSPS_RRC0p25.csv",
             CSVConfig(sample_format="hex_q15",i_column="i",q_column="q")).samples
r = analyze_iq(x,PSDConfig(),QAMConfig(),(-15e6,15e6))
print(r.qam_metrics.evm_pct_rms,r.power_metrics.average_power_dbfs)
plot_psd(r.psd,show=False)
plot_constellation(r.qam_metrics,show=False)
plt.show()   # 不 save
```

### 4. SPS=2、关闭 CFO、标准 JSON 与不显示图形

```python
import json
from psd.csvio import read_csv
from psd.qam import QAMConfig, analyze_qam
from psd.qam.plotting import plot_constellation
x = read_csv("data/generated/qam/Q11_sps2.csv").samples
r = analyze_qam(x,QAMConfig(symbol_rate_hz=80e6,enable_cfo_correction=False,constellation_points=300))
assert r.frequency_error_hz is None
payload = json.dumps(r.to_dict(),allow_nan=False)
fig,axes = plot_constellation(r,show=False)
```

## CLI 参数

所有 CLI 参数均可选，只有频段两个参数为成对条件必选。默认未指定 --qam 时兼容 V2.0.1。

| 参数 | 默认值 | 说明 |
|---|---|---|
| --input | data/sine_+40MHz_160MSPS.csv | 项目根目录相对路径或绝对路径 |
| --fs / --window / --fft-points / --overlap / --detrend | 160e6 / hann / all / .5 / none | 同 PSDConfig |
| --sample-format | 未指定 | 仅原默认 sine 文件选择 hex_q15，其他输入 float；真实 QAM 明确指定 hex_q15 |
| --input-type / --header / --delimiter | auto / auto / 未指定 | 同 CSVConfig；delimiter 为字面字符 |
| --real-column / --i-column / --q-column | 未指定 | 名称或零基索引 |
| --freq-left / --freq-right | 未指定 | Hz，必须成对，显式 0 合法 |
| --display / --no-show | dbfs / False | 密度可选 dbfs_per_hz；no-show 禁止 plt.show |
| --qam | False | 开启 QAM |
| --qam-order / --symbol-rate | 64 / 20e6 | modulation / Sym/s |
| --rrc-beta / --rrc-span / --timing-interp | .25 / 10 / 16 | 同 QAMConfig |
| --max-cfo / --max-analysis-symbols / --constellation-points | 5000 / 30000 / 5000 | 同 QAMConfig |
| --no-cfo-correction / --q-sign | False / 1 | 关闭 CFO 或显式 Q polarity |
| --qam-dc-mode | legacy_mean | legacy_mean / decision_directed_joint，显式选择新的符号域联合拟合 |

Python CLI 使用文本输出；标准 JSON 使用上述程序化 API，未增加 --json。
Packed64 通过 read_packed64 程序化读取，现有 CLI 的 sample-format 语义保持不变。

## V2.1.1：Legacy 与 Joint-fit

默认 `legacy_mean` 保留 V2.1.0 数值、diagnostics.config 与完整旧 JSON 结构，算法版本
`qam-blind-scalar-1`。QAMConfig 不添加 DC 字段，旧13组 Golden 不重新生成。
新增 keyword-only `dc_mode="decision_directed_joint"` 明确选择 `qam-blind-scalar-2`：

```text
z=a*d+c+e
a=sum(conj(d-mean(d))*(z-mean(z)))/sum(|d-mean(d)|²)
c=mean(z)-a*mean(d)
y=(z-c)/a
```

先用 Legacy Scalar Fit 初始化判决，再至多 iterations 次联合 LS/判决。
每次对同一原始符号 z 拟合，不累积多轮偏置补偿；分母与增益必须非零且有限。
最终判决不再改变时 joint_fit_converged=True；不收敛则有限次结束并给 warning。
没有 TX truth 参与接收机，没有多抽头均衡。新模式所有定时/CFO候选都使用 Joint 评分。
开启 CFO 时进行一次 CFO-aware 全相位复查；仅相位改变时再搜索一次 CFO。
这是有界的两次 timing sweep，不是 PLL 或跟踪环。关闭 CFO 时不复查。

新增诊断仅存在于 Joint 模式，不改变 Legacy Golden：

| 字段 | 单位/参考位置 |
|---|---|
| dc_estimation_mode | decision_directed_joint |
| dc_offset | c，CFO 去旋转后的符号域常数，不是 ADC 绝对 DC 电压 |
| forward_gain | a，符号域理想点到接收点的复数增益，模90° |
| complex_gain | 1/a，对去 c 后的符号校正；不是误差指标 |
| joint_fit_iterations / joint_fit_converged | 实际联合 LS 次数 / 判决稳定布尔值；初始化另执行 iterations 次 Legacy fit |
| cfo_grid_resolution_hz | 最后 fine grid 的间隔，**不等于估计精度或不确定度** |
| cfo_estimation_error_hz / cfo_estimation_uncertainty_hz | None，运行时没有发送真值或可信的不确定度模型 |
| cfo_search_evaluations | 所有 CFO 搜索候选总数，默认122或244；关闭为0 |
| timing_initial_offset_symbols / timing_initial_evm_pct | 未 CFO-aware 复查的初始定时结果 |
| timing_cfo_refinement_enabled / timing_search_sweeps | 是否复查 / 2或1 |
| timing_fit_mode / cfo_fit_mode | 当前评分模式，均为 decision_directed_joint |

candidate 只表示残差/占用门限通过，不是锁定证明；warning 表示边界或不收敛。
明显不可靠的残差/占用返回 `QAMRecoveryError`（ValueError 子类），其 diagnostics.status=unreliable，
带有限指标/定时/CFO证据，不返回合法 QAMResult。非法输入仍可能直接抛 ValueError。
平方QAM的 I/Q交换或 Q取反可映射成另一合法星座，单靠 Blind EVM 无法认证极性/bit顺序。
超范围 CFO、错符号率/RRC和非QAM信号也可能通过 candidate 门限，须结合先验或TX参考验证。

**更低的 Blind EVM 不一定代表更接近真实物理 EVM。** Joint LS 可以消除有限符号均值偏差，
但同时定义了不同的允许补偿项；未知信道、低SNR或错误判决时不能依据低EVM宣称链路更好。
正式指标公式/分母、PSD Full Scale与Power积分均不变。

```python
from psd.csvio import read_csv, CSVConfig
from psd.qam import analyze_qam
x = read_csv("data/qam64_20MSymPS_160MSPS_RRC0p25.csv",CSVConfig(sample_format="hex_q15")).samples
legacy = analyze_qam(x)  # 2.596190680%，兼容基线
joint = analyze_qam(x,dc_mode="decision_directed_joint")  # 新模式，真实数据没有TX参考
```

```shell
python python/demo.py --input data/qam64_20MSymPS_160MSPS_RRC0p25.csv --sample-format hex_q15 --qam --qam-dc-mode decision_directed_joint --no-show
python python/validate_qam_refinement.py
python python/benchmark_qam.py --repeats 5
```

独立TX参考仅用于测试：同一个接收采样/对齐、已知 CFO、一次 numpy.linalg.lstsq 求 a/c。
同时报告在真实 CFO 与接收估计 CFO 两个参考下的结果，不能把不同 CFO 下的 LS 差当成数值错误。
新 receiver Golden 在 `data/golden/qam/v2/`，18组，旧13组不变。复数表示仍为分离 real/imag。
相位比较模90°，定时相位模1 symbol；正确判决对齐只搜索整数时移/象限，不改TX真值。
新配置和所有诊断、数组/标量容差保存在向量中，深残差不要求逐bit一致。
Stage A实测矩阵、性能及Go Gate见 [V2.1.1报告](reports/v2.1.1_qam_refinement.md)。

判决收敛表示相邻迭代的decisions不变，不是与TX真值一致。
已验证的偏斜256QAM（完整星座两轮再加负I半星座）可在608个错误判决处稳定，
Joint EVM3.251%仍低于Legacy4.004%；因此不要把该标志当作锁定认证。
V2.1.2完成 [Go Receiver](../go/API.md#qam-receiverv212)，Python公开函数、默认值与数学定义不变。
36组基础数学向量位于 `data/golden/qam/v2/foundation/`，生成器为generate_qam_foundation.py。
旧13组与新18组receiver index保持分离，算法2的配置和返回字段已固定。

README两张真实数据展示图可显式运行 `python python/render_readme.py` 重建；
只有该文档导出脚本保存PNG，库plot_psd/plot_constellation仍默认show。

## V2.1.2 验证入口

`generate_qam_v212.py` 仅创建32768点合成Q1.15/4096 TX truth、独立版本manifest与两组Golden，
不覆盖旧13/18/36组或真实捕获。`compare_qam_go.py` 比较完整中间数组，报告只保存有界取样与误差统计。
`validate_qam_go_v212.py` 对比可靠性反例和Go CLI的PSD/Power/QAM JSON；
`benchmark_qam_v212.py` 对同一IQ比较两种语言，排除启动、编译、CSV生成、绘图及JSON。
开发命令/参数见 [Go README](../go/README.md#qam-receiverv212)，结果见 [V2.1.2报告](../go/reports/v2.1.2_qam_validation.md)。

Slicer内部改为等间隔网格的相邻距离比较，16/64/256QAM在门限及相邻浮点值上对照旧argmin。
极大有限值的距离舍入并列仍保留原argmin首索引语义；没有改变星座次序或测量公式。
迭代上限处Joint gain/DC对应上一组decisions，最终输出decisions是最后LS输出的重新切片；
该V2.1.1行为保持，新增独立回归说明此关系。
