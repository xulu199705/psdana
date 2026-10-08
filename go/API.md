# Go API reference — PSD / Power

Module `github.com/xulu199705/psdana/go`。V2.1.0 只扩展 Python QAM，Go 的公开实现仍为 V2.0.1。
本页说明已有接口，不引入 Go QAM 或改变算法。Go 函数不能省略参数；配置字段的默认值由
DefaultConfig 显式提供，不能将 struct 零值当成完整默认配置。

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

Go QAM 尚未实现；未来移植参考独立 `data/golden/qam/index.json`，不能调用当前 Go PSD API 获得 EVM。
