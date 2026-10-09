# Go API reference — PSD / Power / QAM Receiver (V2.1.2)

Module `github.com/xulu199705/psdana/go`。V2.1.2 新增独立 QAM Receiver，复用 V2.1.1 Foundation。
Go 函数不能省略参数；使用对应 DefaultConfig / DefaultQAMConfig，struct 零值不是完整配置。

## 函数参数与返回值

| 函数 | 必选参数 | 可选/默认行为 | 返回 |
|---|---|---|---|
| psd.DefaultConfig() | 无 | 返回下表默认 PSDConfig | PSDConfig |
| psd.ComputeComplexPSD(samples, config) | samples []complex128、config PSDConfig | 无可省略参数；用 DefaultConfig | (PSDResult,error) |
| psd.ComputeRealPSD(samples, config) | samples []float64、config PSDConfig | 同上 | (PSDResult,error) |
| psd.AnalyzeBandPower(result, left, right) | result PSDResult、left/right float64，Hz | 三个参数必选；相等即点频 | (PowerResult,error) |
| csvio.DefaultConfig() | 无 | 返回下表默认 CSVConfig | CSVConfig |
| csvio.ReadCSV(path, config) | path string、config CSVConfig | path 相对调用进程 cwd | (CSVData,error) |
| csvio.Read(stream, config) | stream io.Reader、config CSVConfig | 调用者管理 stream 生命周期 | (CSVData,error) |
| csvio.ParseColumn(value) | value string | 十进制索引，否则名称；有效性由读取器验证 | *Column |
| CSVData.SampleCount() | 已有 receiver 实例 | 无 | int |
| qam.DefaultScalarConfig() | 无 | 64QAM / 5 iterations / legacy_mean | ScalarConfig |
| qam.GenerateConstellation(order) | order int | 16 / 64 / 256，无省略默认值 | ([]complex128,error) |
| qam.SliceQAM(samples, order) | samples []complex128、order int | 最近点；精确距离相同选较低坐标 | ([]complex128,[]int,error) |
| qam.GenerateRRCTaps(beta, span, sps) | 三个参数均必选 | 单位能量，奇数 tap；无省略默认值 | ([]float64,error) |
| qam.ComputeQAMMetrics(samples, decisions) | 对应顺序的两个 []complex128 | 不拟合/判决/同步；参考符号非零 | (Metrics,error) |
| qam.ScalarQAMFit(samples, config) | samples []complex128、config ScalarConfig | 用 DefaultScalarConfig 明确取得默认配置 | (ScalarResult,error) |

所有普通非法输入返回 error，调用者必须检查，不能继续使用错误结果。
Core 不依赖 CSV/CLI/绘图。real/complex 由函数区分，虚部全零仍按 complex 处理。
每次计算拥有独立 FFT plan/buffer，可并发调用；不要假设自行共享可变 Gonum plan 安全。

### PSDConfig：字段均可用 DefaultConfig 默认值

| 字段 | 是否必须显式修改 | 默认值 | 类型/范围 |
|---|---|---|---|
| FS | 可选 | 160e6 | float64，有限正数 Hz |
| Window | 可选 | "hann" | "hann" / "rectangle" |
| FFTPoints | 可选 | FFTPoints{All:true} | all 或 FFTPoints{N:正整数}，不能同时设置 All/N |
| Overlap | 可选 | .5 | float64，[0,1) |
| Detrend | 可选 | "none" | "none" / "mean" |

`FFTPoints{}` 和 `PSDConfig{}` 无效。FFTPoints JSON 只接受 `"all"` 或正整数，不接受小数。
N=M 或 All 为 Periodogram；N<M 为 Welch，overlap=floor(N*Overlap)，尾部丢弃；N>M 报错。
支持任意长度，Hann N=1 非法，Rectangle N=1 合法；没有隐式补零。
Full Scale 为 complex=1、real=.5；输入不会按峰值归一化。

### CSVConfig 与列选择

| 字段 | 是否必须显式修改 | 默认值 | 类型/范围 |
|---|---|---|---|
| SampleFormat | 可选 | "float" | "float" / "q15" / "hex_q15"；API 没有 "auto" 数字格式 |
| InputType | 可选 | "auto" | "auto" / "real" / "iq" |
| Header | 可选 | "auto" | "auto" / "yes" / "no" |
| Delimiter | 可选 | nil | *string，nil 自动识别，显式一个字符 |
| RealColumn | 可选 | nil | *Column，实数列 |
| IColumn / QColumn | 条件必选 | nil / nil | 未识别 I/Q 表头时成对选择，或明确 InputType="iq" 声明无表头两列顺序 |

`Column{Name:"i"}` 按表头选列；`Column{Index:1,ByIndex:true}` 按零基索引选列。
Column{Name:"",Index:0,ByIndex:false} 不是合法默认选择。I/Q 顺序由角色决定，不由文件列位置猜测。
q15 解析十进制 signed int16 /32768；hex_q15 解析 unsigned 16-bit word 后 two's complement /32768。
BOM、逗号/分号/Tab 支持；歧义、缺列、非法数值、NaN/Inf、空输入和文件错误明确返回 error。
本 Go 版本不支持 packed64 解码。

CSVData 返回 `Real []float64` 或 `Complex []complex128`，由 `InputType`（real/complex）区分。
`Header []string`、`Columns []int`（按 I/Q 或 real 角色顺序）、`Delimiter rune` 保留解码信息。

## 返回结果与 JSON

| PSDResult Go 字段（JSON） | 类型/单位 |
|---|---|
| FrequencyHz (frequency_hz) | []float64，Hz；complex fftshift 双边，real 单边 |
| PSDLinear (psd_linear) | []float64，绝对输入单位平方/Hz，不除以 P_FS |
| PSDDBFSPerHz (psd_dbfs_per_hz) | DBValues，dBFS/Hz |
| RBWPowerDBFS (rbw_power_dbfs) | DBValues，dBFS，ENBW 校准 |
| FFTSize / FSHz | int / float64 Hz |
| FrequencyResolutionHz / ENBWHZ | float64 Hz，fs/N / equivalent noise bandwidth |
| CoherentGain / WindowPowerSum | float64，sum(w)/N / sum(w²) |
| SegmentCount / Window / InputType | int / string / real 或 complex |
| ReferencePower / Method | float64（.5 或 1）/ periodogram 或 welch |
| OverlapSamples / HopSize | int，Periodogram 分别为 0、N |
| InputSampleCount / UsedSampleCount / DiscardedTailSamples | int，输入长度 / 最后一段结束位置 / 丢弃尾部 |
| Detrend / IntegratedPower | none 或 mean / float64，sum(PSDLinear)*df |

其余字段 JSON 使用 Python 对应的 snake_case 名称，具体 tags 见 result.go。
`json.Marshal(result)` 使用 DBValues.MarshalJSON 将 -Inf 转成 null，拒绝 NaN/+Inf；
DBValues.UnmarshalJSON 将 null 恢复为 -Inf。不要把 null 当成 0 dB。

| PowerResult 字段 | 单位/语义 |
|---|---|
| FreqLeftHz / FreqRightHz | float64 Hz，请求范围 |
| IsPoint | bool，左右相等 |
| PeakFrequencyHz | *float64 Hz；零功率 nil |
| PeakPowerDBFS / AveragePowerDBFS | float64 dBFS，零功率 -Inf |
| BandPowerLinear | float64 绝对功率；点频是 RBW bin 功率 |
| ContributingBins | int，distinct signed bins，点频为 1 |

PowerResult.MarshalJSON 也将 -Inf/nil 编码为 null，拒绝其他非有限数值。
边界必须满足 `-fs/2<=left<=right<=fs/2`。非零带宽为 `[left,right)`，按周期性
centered bin 单元重叠宽度积分；Peak 为参与 bin 的最大 PSD*ENBW，Average 为带内积分的 dBFS。
点频使用最近中心，等距选低频；+fs/2 点频选择严格低于该边界的最高 signed 中心。
real 单边 PSD 拆分为等效双边，DC/Nyquist 不重复，单侧实数单音峰值通常低 3.0103 dB。
完整 Nyquist 带内功率等于 IntegratedPower。函数不修改 result，不重算 FFT。

## API 示例

以下示例置于该 module 中的 Go 程序。均检查错误，不假设错误结果可继续使用。

### 1. 满幅复数单音、默认 PSD、点频、JSON

```go
package main

import (
    "encoding/json"
    "fmt"
    "math"
    "math/cmplx"
    "github.com/xulu199705/psdana/go/psd"
)

func run() error {
    x := make([]complex128, 1024)
    for n := range x { x[n] = cmplx.Exp(complex(0, 2*math.Pi*float64(n)/4)) }
    r, err := psd.ComputeComplexPSD(x, psd.DefaultConfig())
    if err != nil { return err }
    p, err := psd.AnalyzeBandPower(r, 40e6, 40e6)
    if err != nil { return err }
    payload, err := json.Marshal(p)
    if err != nil { return err }
    fmt.Println(string(payload)) // Peak 和 Average 约 0 dBFS
    return nil
}
func main() { if err := run(); err != nil { panic(err) } }
```

### 2. Q/I HEX CSV、非 2 次幂 Welch、全频段

```go
reader := csvio.DefaultConfig()
reader.SampleFormat = "hex_q15"
reader.IColumn = &csvio.Column{Name:"i"}
reader.QColumn = &csvio.Column{Name:"q"}
capture, err := csvio.ReadCSV("../data/sine_+40MHz_160MSPS.csv", reader)
if err != nil { return err }
config := psd.DefaultConfig()
config.FFTPoints = psd.FFTPoints{N:999}
config.Overlap = .25
config.Detrend = "mean"
r, err := psd.ComputeComplexPSD(capture.Complex, config)
if err != nil { return err }
power, err := psd.AnalyzeBandPower(r,-config.FS/2,config.FS/2)
if err != nil { return err }
fmt.Println(power.BandPowerLinear,r.IntegratedPower)
```

示例 2 的读取路径按 `go/` cwd；片段需要 fmt、csvio、psd 导入并放在返回 error 的函数内。

### 3. Reader 输入、无表头显式索引、实数单边 PSD

```go
reader := csvio.DefaultConfig()
reader.Header = "no"
reader.InputType = "real"
reader.RealColumn = &csvio.Column{Index:0,ByIndex:true}
capture, err := csvio.Read(strings.NewReader("0\n1\n0\n-1\n"),reader)
if err != nil { return err }
config := psd.DefaultConfig()
config.Window = "rectangle"
r, err := psd.ComputeRealPSD(capture.Real,config)
if err != nil { return err }
fmt.Println(r.InputType,r.IntegratedPower) // real, .5
```

示例 3 另导入 strings；不将实数偷偷当成 complex。无表头 IQ 可改用
InputType="iq"、IColumn=&Column{Index:0,ByIndex:true}、QColumn=&Column{Index:1,ByIndex:true}。

## CLI 参数与示例

所有 CLI 参数可选；freq-left/right 在使用频段时成对条件必选。CLI 路径相对项目根目录，
与库函数路径规则不同。Go CLI 不绘图；JSON stdout 不混入诊断，错误输出 stderr。

| 参数 | 默认值 | 说明 |
|---|---|---|
| --input | data/sine_+40MHz_160MSPS.csv | 根目录相对路径或绝对路径 |
| --fs / --window / --fft-points / --overlap / --detrend | 160e6 / hann / all / .5 / none | 同 PSDConfig |
| --sample-format | auto | 仅原默认 sine 选择 hex_q15，其他 float；可明确 float/q15/hex_q15 |
| --input-type / --header | auto / auto | 同 CSVConfig |
| --delimiter | 空串，自动识别 | comma / semicolon / tab 或一个字面字符 |
| --real-column / --i-column / --q-column | 空串，不选择 | 名称或零基索引 |
| --freq-left / --freq-right | 未提供（内部 flag 默认 0） | Hz；显式 0 是有效请求，不等同未提供 |
| --json | false | PSDResult JSON；提供范围时额外 power_metrics |

```shell
# 默认 Periodogram
go -C go run ./cmd/psdana
# Welch + strict PSD JSON
go -C go run ./cmd/psdana --fft-points 1024 --overlap .5 --detrend mean --json
# 十进制 Q1.15 IQ，固定列名
go -C go run ./cmd/psdana --input data/generated/T09_q15_iq.csv --sample-format q15 --i-column i --q-column q
# 点频 DC / 非对齐频段
go -C go run ./cmd/psdana --freq-left 0 --freq-right 0 --json
go -C go run ./cmd/psdana --freq-left 39990000 --freq-right 40010000 --json
```

## QAM Foundation（V2.1.1）

导入 `github.com/xulu199705/psdana/go/qam`。仅数学基础，输入须已是符号而非原 ADC IQ。
没有 AnalyzeQAM、完整 QAMConfig/QAMResult 或自动同步接口，不能把原始采样直接当成正式 EVM。
所有函数使用独立工作数组，不修改输入，无共享可变状态，不依赖 CSV/绘图。

### ScalarConfig

三个字段均可通过 DefaultScalarConfig 获得默认值，直接 struct 零值非法。

| 字段 | 是否必选显式修改 | 默认 | 约束 |
|---|---|---|---|
| Order | 可选 | 64 | 16 / 64 / 256 |
| Iterations | 可选 | 5 | 正整数；Legacy执行该次数，Joint初始化另执行同次数并至多再迭代该次数 |
| DCMode | 可选 | legacy_mean | legacy_mean / decision_directed_joint |

ScalarQAMFit 至少32符号；空、常量零功率、NaN/Inf及不可表示的累积量返回error。
Joint 使用 `z=a*d+c` centered LS。不是 TX-aided fit，没有均衡或锁定认证。
GenerateRRCTaps 所有参数必选；beta有限[0,1]、span/sps正整数，单位能量，
tap数=span*sps+1（偶数再加1），群延时=(tap数−1)/2。明确限制最多1048576 taps避免异常内存请求。
SliceQAM 用 I-major/Q-minor索引，有限坐标超出边缘饱和到最外理想点，精确距离平局选较低坐标。

### 返回字段

| 类型/字段 | 单位/含义 |
|---|---|
| Metrics.EVMPctRMS | 100 sqrt(sum|y-d|² / sum|d|²) |
| Metrics.AmplitudeErrorPctRMS | 径向误差，% RMS |
| Metrics.PhaseErrorPctRMS | 切向误差，% RMS；不是相位角百分比 |
| Metrics.PhaseErrorDegRMS | principal angle(y conj(d))，deg RMS |
| ScalarResult.Equalized / Decisions / Indices | 对应顺序的完整校正符号/判决/I-major索引 |
| EVMPct | 使用最终相同y/d的decision-directed EVM % RMS |
| DC / ComplexGain | 符号域偏置 / 去偏置后校正增益；不是ADC绝对增益或DC |
| ForwardGain | Joint的a；Legacy不提供此诊断，Go字段零值不能解释为测量 |
| CoarsePhaseDeg | 四阶矩粗相位，模90°；不是绝对发送相位 |
| DCMode | 实际模式 |
| JointIterations / JointConverged | Joint执行次数/判决是否稳定；Legacy不适用 |

ScalarResult 实现 json.Marshaler，输出 Python primitive 名称：eq/decisions以
`{"real":[...],"imag":[...]}` 表示，dc/complex_gain以real/imag标量表示。
Legacy不导出Joint字段，Joint额外forward_gain/joint_fit_iterations/joint_fit_converged。
非有限值返回JSON编码错误，不输出NaN/Infinity；foundation没有“未估计CFO”字段。
EVM平方分解保持成立。**判决稳定或Blind EVM较低不证明锁定，也不证明真实物理EVM更低。**
偏斜256QAM测试已确认可能稳定在错误判决。

### 程序化示例

```go
// 1. 生成标准星座并判决，所有参数必选。
points, err := qam.GenerateConstellation(64)
if err != nil { panic(err) }
decisions, indices, err := qam.SliceQAM(points, 64)
if err != nil { panic(err) }
// decisions等于points；indices为0..63，先I后Q。
_, _ = decisions, indices
```

```go
// 2. RRC不是PSD窗；MatchedFilter可用于接收IQ。
taps, err := qam.GenerateRRCTaps(0.25, 10, 8)
if err != nil { panic(err) }
// 81 taps、单位能量、群时延40 samples。
_ = taps
```

```go
// 3. 对已恢复符号显式Joint fit，不进行timing/CFO。
config := qam.DefaultScalarConfig()
config.DCMode = qam.DecisionDirectedJoint
fit, err := qam.ScalarQAMFit(recoveredSymbols, config)
if err != nil { panic(err) }
metrics, err := qam.ComputeQAMMetrics(fit.Equalized, fit.Decisions)
if err != nil { panic(err) }
encoded, err := json.Marshal(fit)
if err != nil { panic(err) }
_, _ = metrics, encoded
```

36组跨语言数学向量位于 `data/golden/qam/v2/foundation/`，独立index及SHA256。
旧13组Legacy、新18组Joint与新增两组32768点Golden同时验证Go全接收链。
测试：`go -C go test -v ./qam`；端点/异常/解析指标、输入不变和Example函数同时验证。

## QAM Receiver（V2.1.2）

Core 无 CSV、CLI、绘图或 Python 进程依赖。所有输入均为独立的 `[]complex128`，调用不修改输入。

| 公开入口 | 返回值 | 含义 |
|---|---|---|
| DefaultQAMConfig() | QAMConfig | Python 当前默认；Legacy 模式 |
| QAMConfig.Validate() | error | 校验整数 SPS、所有接收参数与数值范围 |
| QAMConfig.SamplesPerSymbol() | int | 验证配置后的整数 SPS |
| MatchedFilter(samples, taps) | ([]complex128,error) | scipy fftconvolve same 对齐语义，直接 FIR；长度保持为 IQ 长度 |
| InterpolationTaps(up, beta) | ([]float64,error) | firwin Kaiser 系数乘 up；up=1 为 identity |
| Interpolate(samples, up, beta) | ([]complex128,error) | resample_poly(up,1)，zero padding，补偿 FIR 延迟 |
| SearchTimingPhases(up, config, cfo) | (TimingResult,error) | cfo 为 *float64；nil 为初始搜索，否则按该 CFO 评分 |
| SearchResidualCFO(symbols, config) | (CFOResult,error) | 粗/细网格与完整 ScalarResult，disabled CFO 为 nil |
| RecoverSymbols(samples, config) | (RecoveryResult,error) | 完整恢复符号；质量不合格返回 RecoveryError |
| AnalyzeQAM(samples, config) | (QAMResult,error) | 正式结果与有界诊断 |
| BuildQAMResult(recovery, inputCount, config) | (QAMResult,error) | 格式化已有通过质量检查的 recovery；调用者必须先检查 RecoverSymbols 的 error |

RecoverSymbols 在质量拒绝时同时保留 RecoveryResult 供调试；它不属于接受结果。
其他参数/数值错误可能返回零结果。RecoveryError.Diagnostics.status 为 unreliable。
TimingResult 包含 SymbolsRaw、PhaseUp、EVMPct、CurveEVMPct、TrimSymbols、FirstSymbolIndex。
CFOResult 包含 FrequencyHz、BoundaryHit、SearchSymbols、GridResolutionHz 及粗细评分网格。

### QAMConfig 默认与约束

| 字段 | 默认 | 单位/约束 |
|---|---:|---|
| SampleRateHz / SymbolRateHz | 160e6 / 20e6 | Hz；比例必须为整数 SPS≥2 |
| QAMOrder | 64 | 16 / 64 / 256；本版端到端重点64QAM |
| RRCBeta / RRCSpanSymbols | 0.25 / 10 | β∈[0,1]；span 正整数 |
| TimingInterp / TimingKaiserBeta | 16 / 8 | 整数倍插值；Kaiser β≥0 |
| ExtraEdgeTrimSymbols | 6 | 每边裁剪 span/2 floor + extra |
| EnableCFOCorrection | true | false 时 FrequencyErrorHz=nil，JSON null |
| MaxResidualCFOHz | 5000 | Hz，范围小于 symbol_rate/2；启用时>0 |
| CFOCoarseSteps / CFOFineSteps | 81 / 41 | 奇数≥3，first-minimum tie |
| CFOSearchMaxSymbols | 12000 | CFO 中心子集，上限≥MinAnalysisSymbols |
| MaxAnalysisSymbols | 30000 | Timing 符号中心截取，上限≥MinAnalysisSymbols |
| ConstellationPoints | 5000 | 仅影响图示/JSON抽样，正整数 |
| QSign | +1 | +1 / -1，仅QAM使用，PSD仍使用原始IQ |
| ScalarFitIterations | 5 | 正整数，Joint 初始化后有界迭代 |
| MinAnalysisSymbols | 200 | ≥32，短于边缘裁剪要求时报错 |
| MaxDecisionEVMPct | 12 | 正有限数，百分比 RMS |
| DCMode | legacy_mean | 显式可选 decision_directed_joint |

Go 实现资源边界：SPS≤1e6、RRC span*SPS≤1e6、TimingInterp≤4096、Kaiser β≤700、
ExtraEdgeTrimSymbols≤1e6、每个 CFO grid≤1000001、ScalarFitIterations≤1e6、MinAnalysisSymbols≤1e9。
这些限制用于防止异常整数或不可表示 FIR，并非性能或实时保证。Foundation 原接口保持兼容。
DCMode 的 JSON 配置字段省略以对应 Python config；实际模式另在 diagnostics.dc_estimation_mode 中保存。

Joint 流程：初始 timing → CFO → CFO-aware timing；相位变化时再搜索一次 CFO，至此结束。
迭代未收敛时，gain/DC 是最后一次对**上一次判决**的 LS；输出 decisions 是该 LS 输出的重新切片。
本版保留此 V2.1.1 契约，不做额外隐藏拟合。JointConverged=false 会产生 warning。

### QAMResult / JSON

QAMResult 使用 Python 字段名：qam_order、sample_rate_hz、symbol_rate_hz、samples_per_symbol、
evm_pct_rms、amplitude_error_pct_rms、phase_error_pct_rms、phase_error_deg_rms、frequency_error_hz、
timing_offset_symbols、recovered_symbol_count、constellation_i/q、ideal_i/q、diagnostics。
指标对全部有效恢复符号计算，满足 EVM²=AmplitudeError²+PhaseError²。
抽样采用 uniform_indices_inclusive_endpoints；星座固定 I-major/Q-minor，90°相位模糊不进行额外对齐。
diagnostics 保留算法版本、配置、Scalar/DC、Timing curve、CFO range/resolution、收敛及 warnings，
新增 timing_phase_up、cfo_estimate_hz、Legacy 的显式 dc_estimation_mode；完整插值数组不进入正式 JSON。
复数诊断使用 real/imag。非有限计算返回 error，标准 json.Marshal 拒绝任何 NaN/Infinity。
candidate/warning 表示盲候选，不能证明绝对锁定；占用<8或 EVM>门限则 unreliable/error。

```go
// iq来自调用者解码，signed int16必须除以32768，不依赖当前峰值。
config := qam.DefaultQAMConfig()
config.DCMode = qam.DecisionDirectedJoint
result, err := qam.AnalyzeQAM(iq, config)
if err != nil { panic(err) }
encoded, err := json.Marshal(result)
if err != nil { panic(err) }
_ = encoded
```

### QAM CLI

新增 --qam、--qam-order、--symbol-rate、--rrc-beta、--rrc-span、--timing-interp、--max-cfo、
--max-analysis-symbols、--constellation-points、--qam-dc-mode、--no-cfo-correction、--q-sign。
fs、格式、FFT、频段边界仍复用原旗标；不会根据QAM文件名猜测格式。

```shell
go -C go run ./cmd/psdana --input data/generated/qam/Q13_32768_q15.csv --sample-format q15 --fs 160000000 --fft-points 32768 --qam --qam-order 64 --symbol-rate 20000000 --rrc-beta 0.25 --qam-dc-mode decision_directed_joint --json
```

未启用QAM时原 JSON 完全保持；启用增加 qam_metrics，传频段增加 power_metrics，PSD字段仍在顶层。
stdout 仅JSON，错误写stderr/非零退出；既不绘图也不调用Python。

逐级验证、相同IQ的Benchmark入口和实际数据见 [V2.1.2报告](reports/v2.1.2_qam_validation.md)。

## WebUI HTTP Adapter（V2.2.0）

启动：仓库根目录 `go -C go run ./cmd/webdemo`；只绑定 `127.0.0.1:8080`。
原 CLI、csvio、psd、qam 公共接口保持不变，以下限制只适用于 Web Demo。

| 路由 | 行为 |
|---|---|
| `GET /` | 内嵌 WebUI；同源提供所有 JS/CSS、字体和 ECharts |
| `GET /api/health` | `{"status":"ok","version":"2.2.0"}` |
| `POST /api/analyze` | multipart 上传一个 CSV，同步计算并返回完整 JSON |

六个必填且不得重复的 multipart 字段：

| 字段 | 类型与校验 |
|---|---|
| file | 一个 CSV 文件；识别 I/Q 表头（大小写不敏感，Q/I 顺序也可），或一个实数列 |
| sample_rate_hz | 有限正数 Hz |
| power_band_left_hz | 有限数 Hz，`-Fs/2 <= lower <= upper <= Fs/2` |
| power_band_right_hz | 同上；上下界相等时测量单点频率 |
| symbol_rate_hz | 有限正数 Hz；整数 SPS≥2，满足原 QAMConfig.Validate |
| rrc_beta | 有限数 `[0,1]` |

固定 `csvio.DefaultConfig().SampleFormat="hex_q15"`、64QAM、FFT all、Hann、Legacy DC；
其他接收参数来自 DefaultQAMConfig。前端不提交 sample_format，额外字段返回 400。
默认 RRC span=10 导致可接受 SPS≤100000；默认 CFO 搜索 ±5000 Hz 要求 symbol_rate_hz>10000。
即使只看 PSD Tab，也校验 QAM 参数，因为每次请求都执行完整分析链。
相等边界直接传给现有 AnalyzeBandPower：返回 `is_point=true`、`contributing_bins=1`，
Average 与 Peak 均为最近 FFT bin 的 RBW 校准功率（dBFS）。等距选择低频 bin，+Fs/2 选择严格低于该边界的最高中心。
前端仍绘制完整 PSD（dBFS/Hz），不把单点测量结果当作 PSD 密度。

HEX 词法完全复用 csvio：1–4 个十六进制数字，可选 `0x` 前缀，按 unsigned 16-bit word 转 signed Q1.15。
不自动回退到 float/q15/packed。`1234` 同时是合法十六进制文本，固定解释为 0x1234；
无法从无格式元数据的数字文本判断作者原意是 decimal。无表头两列的 I/Q 歧义按原 csvio 规则拒绝。

成功响应仍使用顶层 PSDResult 字段；额外包含：

| 字段 | 含义 |
|---|---|
| power_metrics | AnalyzeBandPower 的完整结果，边界为实际请求 Hz |
| qam_metrics | 成功时的原 QAMResult，含星座数组与 diagnostics.warnings |
| qam_error | QAM 失败时的说明；同时省略 qam_metrics |
| rrc_beta | 实际使用的 RRC roll-off |
| status | COMPLETE 或 PARTIAL |

PSD/QAM 数值均由现有 Go Core 提供。`psd_dbfs_per_hz` 的 null 表示 −Inf，前端按缺口处理；
功率 null 显示 −∞，峰值频率 null 显示 N/A，Frequency Error null 显示 N/A。
相位百分比使用 `phase_error_pct_rms`，不是 `phase_error_deg_rms`。

| HTTP 状态 | 语义 |
|---|---|
| 200 COMPLETE | PSD、频段功率、QAM 全部成功；warnings 仍需阅读 |
| 200 PARTIAL | PSD 和功率有效，QAM 不可用；真实单音与实数输入会走此路径 |
| 400 | multipart、CSV 格式、字段或参数错误 |
| 403 | 浏览器 Origin 与本服务不同 |
| 413 | 完整请求超过 16 MiB（包括 multipart 开销） |
| 422 | PSD 或频段功率计算失败 |
| 500 | JSON 序列化失败 |
| 503 | 另一个分析占用计算入口，请稍后重试 |

错误响应为 `{"status":"ERROR","error":"..."}`。先完成 JSON 编码再写响应，避免半段 JSON。
请求体使用 MaxBytesReader 限制，multipart 临时文件和流在请求结束释放；不长期保存上传文件。
Header 超时 5 秒，读取请求超时 60 秒；计算没有虚构进度，也没有硬中断现有 DSP 函数。
浏览器替换文件或修改参数会废弃旧请求；Go 在阶段边界检查取消，已进入的同步计算仍可执行到返回。

示例（从仓库根目录；Windows 可使用 curl.exe）：

```shell
curl http://127.0.0.1:8080/api/analyze -F "file=@data/qam64_20MSymPS_160MSPS_RRC0p25.csv" -F "sample_rate_hz=160000000" -F "power_band_left_hz=-20000000" -F "power_band_right_hz=20000000" -F "symbol_rate_hz=20000000" -F "rrc_beta=0.25"
```
