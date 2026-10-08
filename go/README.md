# Go PSD Core — Phase 2

Module：`github.com/xulu199705/psdana/go`，复用既有 Go 1.27.1 配置，仅使用 Gonum v0.17.0。
核心、CSV、CLI 分离；没有 Go 绘图、TypeScript、GUI 或并行 Welch。

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
