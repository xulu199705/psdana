# Go PSD / Power / QAM Receiver

Module：`github.com/xulu199705/psdana/go`，复用既有 Go 1.27.1 配置，仅使用 Gonum v0.17.0。
核心、CSV、CLI 分离；没有 Go 绘图、TypeScript、GUI 或并行 Welch。

完整的必选/可选参数、DefaultConfig 默认值、返回字段及多个程序化/CLI 示例见
[Go API Reference](API.md)。V2.1.1 在Python Stage A Gate通过后新增独立QAM数学基础，原PSD/Power算法不变。

## QAM Foundation（V2.1.1）

`qam/` 提供16/64/256星座与Slicer、单位能量RRC、径向/切向/角度/EVM指标、
Legacy/Joint标量拟合。36组Python共享向量与独立解析/数值边界测试通过。
全部参数、默认值、返回值与多个调用示例见 [API](API.md#qam-foundationv211)。
V2.1.2 在该Foundation上完成 matched RRC、Kaiser Polyphase插值、Timing/CFO、完整Receiver及CLI JSON。
Scalar输入必须是已恢复符号。没有使用已知TX真值或多抽头均衡器。

```shell
go -C go test -v ./qam
python python/generate_qam_foundation.py
```

第二条仅用于明确更新独立foundation向量，不改旧PSD/QAM Golden。
Gate、已证实的误候选及数值差异见 [V2.1.1验证](../python/reports/v2.1.1_qam_refinement.md)。

## QAM Receiver（V2.1.2）

`qam.AnalyzeQAM(samples, qam.DefaultQAMConfig())` 独立执行接收链，无Python进程依赖。
默认Legacy；显式设置 config.DCMode=qam.DecisionDirectedJoint 使用联合DC/增益拟合与CFO-aware定时。
默认160 MSPS、20 MSym/s、64QAM、RRC β=.25/span10、16倍Timing、±5000 Hz CFO。

```shell
go -C go run ./cmd/psdana --input data/generated/qam/Q13_32768_q15.csv --sample-format q15 --fs 160000000 --fft-points 32768 --qam --qam-dc-mode decision_directed_joint --json
go -C go run ./cmd/psdana --input data/qam64_20MSymPS_160MSPS_RRC0p25.csv --sample-format hex_q15 --qam --qam-dc-mode legacy_mean --json
```

第一个文件是固定seed的32768点合成Q1.15；第二个保留原16384点真实捕获。
signed int16/32768，complex P_FS=1。FFT all/Periodogram/Welch/短输入报错语义保持。
JSON保持顶层PSD字段，新增qam_metrics；质量失败返回error，candidate/warning不是锁定证明。

```shell
go -C go build -o ../.cache/v212/qamcheck.exe ./cmd/qamcheck
go -C go build -o ../.cache/v212/qambench.exe ./cmd/qambench
go -C go build -o ../.cache/v212/psdana.exe ./cmd/psdana
python python/compare_qam_go.py
python python/validate_qam_go_v212.py
python python/benchmark_qam_v212.py
python python/benchmark_qam_v212.py --real-capture
```

以上开发工具在项目根目录运行；先创建.cache/v212。Go Benchmark排除编译、启动、CSV生成及JSON。
完整数值对比、性能、内存范围和实际限制见 [V2.1.2报告](reports/v2.1.2_qam_validation.md)。

## 接口与算法

```go
config := psd.DefaultConfig()
config.FFTPoints = psd.FFTPoints{N: 1024} // 或 {All:true}
result, err := psd.ComputeComplexPSD(iqSamples, config)
// 实数调用 ComputeRealPSD(realSamples, config)。
```

PSDConfig{} 和 FFTPoints{} 非法，不等价于默认配置。默认 fs=160e6、hann、all、overlap=.5、none。
JSON FFTPoints 只接受 "all" 或正整数。公开接口明确 real/complex，虚部为零不改变输入类型。
PSDResult 对应 Python 全部字段，integrated_power 为显式字段，DBValues 的 -Inf 使用 JSON null。

未归一化 forward FFT；Periodic Hann；PSD=|FFT(x*w)|²/(fs*sum(w²))。
CG=sum(w)/N，ENBW=fs*sum(w²)/sum(w)²；复数 fftshift 双边，实数正确合并奇偶端点。
复数 P_FS=1、实数 P_FS=.5。功率积分使用 df，Welch 在线性域平均，完整段之外的尾部丢弃。
N=M/all 为 Periodogram，N<M 为 Welch，N>M 报错；overlap_samples=floor(N*overlap)。
Hann N=1 报错，N=2 ENBW=fs；Rectangle N=1 合法。每次调用拥有 plan/buffers，Welch 段间复用。

默认采用 Gonum real FFT。v0.17.0 real general-radix 路径在 8193=3×2731 点不能满足原容差；
含质因子 >31 的实数长度保守选择 Gonum CmplxFFT，再取单边谱，不扩展 N 或改变归一化。
该工程选择由独立 Parseval 和跨语言回归验证，不代表所有长度的精度证明。

## CLI 与 CSV

从 go/ 执行：

```powershell
go build -o bin/psdana.exe ./cmd/psdana
go run ./cmd/psdana
go run ./cmd/psdana --fft-points 1024 --overlap .5 --detrend mean --json
```

仓库根目录使用 `go -C go run ./cmd/psdana`。从 cwd 或二进制位置向上定位项目根目录，
默认原始 CSV 与相对 --input 均按根目录解析；复制二进制到其他位置时使用绝对输入路径和明确格式。
auto sample-format 仅为原文件选择 hex_q15，其他文件使用 float。
JSON stdout 仅含完整结果，错误写入 stderr 并返回非零状态，不绘图、不保存图片。
参数：--input/--fs/--window/--fft-points/--overlap/--detrend/--sample-format/--json，
另支持 --input-type/--header/--delimiter/--real-column/--i-column/--q-column。

csvio.DefaultConfig() 默认 float、auto header/columns/delimiter。支持单列实数、明确 IQ、BOM、
逗号/Tab/分号、列名或零基索引。q15=int16/32768，hex_q15 先 two's complement 解码。
没有幅度自动归一化；未知双列顺序、非法数值、缺列或文件错误明确报错。

## 验证与 Benchmark

```powershell
go fmt ./...
go vet ./...
go test ./...
go test -v ./...
go test -run '^$' -bench=. -benchmem ./...
# 有兼容 C 编译器时：go test -race ./...
```

tests/ 直接读取原 data/golden/index.json，验证全部 17 组 vector/source SHA256 和完整结果，
使用向量自身容差。显著 PSD>1e-20 的 bin 比较 dB，深残差比较线性 PSD；全零必须精确零/null。
verbose 输出每字段 max abs/relative、bin/频率、实际/期望、容差和 PASS/FAIL。
relative 仅对非零期望定义；设置 PSD_REPORT_DIR 可导出 golden_statistics.json。

仓库根目录：

```powershell
python python/compare_go.py
python python/benchmark.py --repeats 5 --iterations 3
```

compare_go.py 只构建一次，固定 seed 共享输入，并比较全部数组及元信息，超限非零退出。
Benchmark 使用 .cache/bench/ 共享 CSV，包括百万点，不复制 Golden 或提交大型输入。
Core 包含验证/window/plan/FFT/PSD/dB/分配；CSV 为 open/read/decode；E2E 为 CSV+Core。
排除编译、启动、生成、绘图与 JSON。预热后报告每试验平均调用耗时的 median/p90/min/max。
Go testing.B 提供 B/op/allocs；B/op 非峰值 RSS，未与 Python tracemalloc 混比。
标准 Go Benchmark 默认复用缓存 manifest，否则生成独立临时信号；公平配对比较通过 Python 脚本执行。
PSD_BENCH_DIR 可显式指定 manifest 所在目录；固定迭代可用 -benchtime=3x -count=5。

Go 不在 PATH 时，通过 Python 脚本 --go / PSD_GO 指定工具链。
沙箱环境可设置 GOCACHE、GOTMPDIR、TEMP/TMP 到项目已建立的 .cache 子目录。
Python 使用现有 Conda 环境，没有修改依赖版本。

结果见 [工程报告](reports/phase2_validation.md) 和 [性能表](reports/performance.md)。

## V2.0.1：频段与点频功率

```go
// 先检查 PSD 计算错误，再调用；函数不修改 result。
power, err := psd.AnalyzeBandPower(result, 39e6, 41e6)
point, err := psd.AnalyzeBandPower(result, 40e6, 40e6)
```

PowerResult：FreqLeftHz/FreqRightHz、IsPoint、PeakFrequencyHz (*float64，零功率 nil)、
PeakPowerDBFS、AveragePowerDBFS、BandPowerLinear、ContributingBins；JSON tags 与 Python 同名。
MarshalJSON 将 -Inf dB 和无效峰值频率编码为 null，拒绝 NaN/+Inf。
BandPowerLinear 是绝对输入单位平方，点频时表示所选 bin 的 RBW 功率；ContributingBins 按 distinct signed bin 计数。

`-fs/2 <= left <= right <= fs/2` 严格检查，非有限值/逆序/越界返回 error。
非零频段为 `[left,right)`：宽度 df 的 centered bin 单元与该范围取重叠宽度，Nyquist 跨界部分以 fs 为周期折回。
FFT 网格由 bin 序号与 df 建立；PSDResult 轴一致性验证只允许与机器精度成比例的舍入差异，无固定 MHz epsilon。
Peak 为所有正宽度重叠 bin 的 max(Pxx*ENBW)，不按重叠宽度缩小 Peak；Average 为 sum(Pxx*width) 的 dBFS。
部分重叠或周期折回时，返回的 bin 中心可在请求范围外；正端 Nyquist 单元的中心表示为 -fs/2。
Average 是时间平均带内信号功率估计；不是 mean(PSD)、mean(dBFS) 或 sum(RBW)。密度仍以 dBFS/Hz 表示。
全 Nyquist 积分等于原 integrated_power，浮点加法次序只产生舍入差异。

点频按中心距离选最近 bin，等距或等功率选择较低频率；Peak=Average=该 bin RBW 功率。
`+fs/2` 点频特例选择 signed 频率表示中严格低于该边界的最高 bin，不增加虚构 bin。
偶数 Nyquist 中心表示为 -fs/2，单元在两端各占一半；right=+fs/2 为排除端点。

实数单边谱内部 bin 正负各一半，DC/偶数 Nyquist 唯一，奇数末正 bin 也拆分。
单侧实数峰值通常较原单边图低约 3 dB；Full Scale 不变：real=.5，complex=1。
Hann 相干单音单 bin 积分为总功率 2/3，完整主瓣恢复总功率；频段估计受 df、窗泄漏和 Welch 统计影响。
零功率返回 -Inf/nil，无任意噪声门限。核心拒绝使 FFT 平方、mean、PSD 累加、RBW 或积分溢出的有限输入，
以及不可表示的归一化尺度/df；普通输入的算法路径、归一化与 Golden 不变。float64 下溢可能成为零。

```shell
go -C go run ./cmd/psdana --freq-left 39000000 --freq-right 41000000
go -C go run ./cmd/psdana --freq-left 0 --freq-right 0 --json
python python/compare_power_go.py
```

参数必须成对；显式 0 合法。未提供时 JSON 完全保留 V2.0.0 的 22 个 PSDResult 字段；
提供时额外增加 power_metrics。零输入文本峰值显示 N/A，不再把第一个 bin 作为有效峰值。
安全扫描按 [Go 官方方式](https://go.dev/doc/security/vuln/) 安装并运行 govulncheck：

```shell
go install golang.org/x/vuln/cmd/govulncheck@latest
govulncheck ./...
```

复用已有工具即可。测试、跨语言误差及实际扫描状态见 [V2.0.1 验证报告](reports/v2.0.1_validation.md)。
