# Phase 2 validation — V2.0.0

必需验收项全部 PASS；race detector 为可选 NOT RUN（CGO_ENABLED=0，当前 PATH 未发现 C 编译器）。

## 1. 环境

- OS：Microsoft Windows 11 专业版 10.0.26300。
- CPU：Intel(R) Core(TM) Ultra 9 275HX，24 cores / 24 logical processors。
- RAM：31.38 GiB。
- Go：go version go1.27.1 windows/amd64；Gonum：v0.17.0。
- Python：3.13.14；NumPy：2.5.1；SciPy：1.18.0；pytest：8.4.2。
- Git 测试基线：`50b322ec381b9cf943ffa7920928d9144f78e7dc`，代码测试在 Phase 2 工作区执行；基线历史仅作隐私清理，计算代码和数据不变。
- Benchmark 为 5 trials × 3 iterations，预热后 median/p90；无 CPU affinity 或强制电源策略，环境干扰未完全隔离。

## 2. 实现内容

- psd：DefaultConfig / ComputeComplexPSD / ComputeRealPSD，完整 JSON result，Periodic Hann/Rectangle，Welch，正确单双边与 Full Scale。
- csvio：float/q15/hex_q15、BOM、列角色与顺序、header/索引/名称、三种分隔符及明确错误。
- CLI：文本摘要与机器-only JSON；null=-Inf；项目根目录路径解析；没有 Go 绘图。
- 测试：Gonum FFT 与解析/独立 DFT、窗参数、Parseval、DC/Nyquist、线性 Welch、边界长度和并发独立调用。
- 直接比较与 testing.B Benchmark；未修改 Python 三个 PSD 模块、已有 generated/golden 或原始 CSV。

## 3. 自动化与 Golden

- Go：16 个顶层测试函数、169 个叶级测试用例全部通过。
- Python：174 passed。go fmt、go vet、go test ./...、go test -v ./... 均通过。
- Golden：17/17 PASS，0 Failed；检查源/vector SHA256、全部数组及元数据。
- 直接比较：20/20 PASS，包含原始 CSV 完整频谱、65536 噪声、4096 多音、不同 fs/overlap/detrend、real/complex 和 1/2/3/255/256/333/999 点边界。
- 每向量和字段的 bin/frequency、actual/expected、容差、max abs/relative 与 PASS 详见 golden_statistics.json、direct_comparison.json 和 go_test_verbose.txt。

| 字段 | Golden max abs | Golden max relative（非零期望） | Direct max abs |
|---|---:|---:|---:|
| frequency_hz | 1.49011612e-08 | 3.52420929e-16 | 1.49011612e-08 |
| psd_linear | 2.96461532e-21 | 51.1437943 | 2.03287907e-20 |
| psd_dbfs_per_hz | 7.04858394e-09 | 3.53119057e-11 | 3.19744231e-12 |
| rbw_power_dbfs | 7.04858394e-09 | 4.99787539e-11 | 3.2471803e-12 |
| integrated_power | 8.8817842e-16 | 2.00456935e-15 | 5.32907052e-15 |
| enbw_hz | 9.02218744e-10 | 3.75548552e-15 | 9.31322575e-10 |
| coherent_gain | 4.4408921e-16 | 8.8817842e-16 | 1.88737914e-15 |
| window_power_sum | 6.25277607e-13 | 1.66907603e-15 | 8.36735126e-11 |

Golden 显著 bin 的最大 dB 误差为约 7.05e-9 dB，低于既有 1e-7 dB 容差。
极低功率 bin 的相对误差可很大；其正确判据是向量指定的线性 atol+rtol。dB 比较只在 expected PSD>1e-20 处进行，没有放宽已有容差。

## 4. 原始 CSV

- 8192 samples，header q,i，I=列1 / Q=列0；hex int16 / 32768。Go 所有样本与独立四样本解析周期逐点相同。
- 默认 160 MSPS / Hann / all / none：FFT=8192，Periodogram，1 segment。
- 主峰 +40 MHz；RBW peak=-9.087628044 dBFS；density peak=-53.755841025 dBFS/Hz。
- df=19531.25 Hz；ENBW=29296.875 Hz；Integrated Power=0.123377849348。
- Python-Go 全频谱 max absolute PSD error=9.31736e-21；显著 RBW dB error=3.55271e-15。
- 全部 33 个保护文件哈希不变，原 CSV SHA256 保持冻结值。

## 5. 性能 Benchmark

Core 的采样率=160e6、window=hann、detrend=none；Welch overlap=.5。
Python 时间保留自配对基线；Go 最终版本在相同输入和相同迭代设置下复测。

| 输入 | 方法 / FFT / segments | Python median ms | Go median ms | Speedup | Python / Go MSamples/s | Go B/op / allocs/op |
|---|---|---:|---:|---:|---:|---:|
| complex 999 | periodogram / 999 / 1 | 0.0718 | 0.0556 | 1.292 | 13.920 / 17.978 | 106496 / 8 |
| complex 333 | periodogram / 333 / 1 | 0.0539 | 0.0183 | 2.938 | 6.182 / 18.164 | 35072 / 8 |
| complex 1024 | periodogram / 1024 / 1 | 0.0627 | 0.0412 | 1.521 | 16.323 / 24.834 | 106496 / 8 |
| complex 8192 | periodogram / 8192 / 1 | 0.2279 | 0.3997 | 0.570 | 35.940 / 20.495 | 851968 / 8 |
| complex 8192 | welch / 1024 / 15 | 0.4831 | 0.2036 | 2.373 | 16.958 / 40.236 | 106496 / 8 |
| complex 65536 | periodogram / 65536 / 1 | 4.8548 | 3.5837 | 1.355 | 13.499 / 18.287 | 6815744 / 8 |
| complex 65536 | welch / 1024 / 127 | 1.5482 | 1.4991 | 1.033 | 42.330 / 43.716 | 106496 / 8 |
| complex 1048576 | periodogram / 1048576 / 1 | 95.8345 | 72.2662 | 1.326 | 10.942 / 14.510 | 109051904 / 8 |
| complex 1048576 | welch / 1024 / 2047 | 25.8597 | 26.3365 | 0.982 | 40.549 / 39.815 | 106496 / 8 |
| real 8192 | periodogram / 8192 / 1 | 0.1941 | 0.2957 | 0.657 | 42.198 / 27.704 | 565248 / 9 |
| real 8192 | welch / 1024 / 15 | 0.2016 | 0.1879 | 1.073 | 40.628 / 43.598 | 69888 / 9 |
| real 65536 | periodogram / 65536 / 1 | 3.1304 | 2.5773 | 1.215 | 20.935 / 25.428 | 4235264 / 9 |
| real 65536 | welch / 1024 / 127 | 1.4493 | 1.4061 | 1.031 | 45.218 / 46.608 | 69888 / 9 |

CSV 与 E2E 的各规模 median/p90 和吞吐见 [完整性能表](performance.md)；原始 Go 输出见 go_benchmark_raw.txt。
- Go CSV/E2E 在这些实测输入上明显更快；不能将该优势解释为 FFT 在所有规模上更快。
- 8192 点 complex/real Periodogram 的 Go Core 慢于 NumPy；百万点 Welch Core 与 Python 接近，本次略慢。
- Go 百万点 complex CSV 约有百万次分配，CSV/样本切片增长仍是可优化的实际分配来源。
- 不对单次机器结果推广到其他 CPU。CSV 为热文件系统缓存，未测冷盘；无统一 peak RSS，Python native allocations 未测。

### 低风险优化与回归

- 先通过 Golden/解析/直接比较和性能基线，再复用线性 PSD accumulator 作为结果数组。complex 在每次调用结束时原位 fftshift，仅旋转一次。
- Welch plan/window/input/output buffer 段间复用，不引入共享可变实例。
- 最终更改后重新通过全部 Golden、数学测试、直接比较，并重新实测全部 Go scopes。

| Core case | Baseline B/op / allocs | Final B/op / allocs | Baseline / Final median ms |
|---|---:|---:|---:|
| complex_1024_all | 114688 / 9 | 106496 / 8 | 0.0464 / 0.0412 |
| complex_1048576_all | 117440512 / 9 | 109051904 / 8 | 82.5797 / 72.2662 |
| complex_1048576_welch1024 | 114688 / 9 | 106496 / 8 | 28.5611 / 26.3365 |
| real_65536_all | 4505600 / 10 | 4235264 / 9 | 1.8348 / 2.5773 |

分配减少是稳定、可解释的结果；耗时存在跨轮波动，没有仅凭两轮数据声称所有规模稳定加速。

## 6. 实际问题与边界

- Gonum real FFT v0.17.0 在 8193=3×2731 点的 general-radix 路径出现约 9.63e-19 PSD max abs、5.10e-10 max relative、2.28e-12 积分误差，超出既有契约。
- 相同输入的 Python 与独立窗加权 Parseval 一致；Go CmplxFFT 路径满足既有容差，因此 real 大质因子长度采用该路径。新增 127/257/509/1009/8193/5462 Parseval 回归。
- 修正后该直接用例 PSD max abs=5.79e-23；当前 Python Golden 未发现需修改的数学问题。
- >31 的 factor 判据是保守工程选择。尚未穷举全部 FFT 长度，也未对大质因子长度完成独立公平性能矩阵。
- float64 极端溢出/下溢未作为本阶段保证；单 seed 噪声不是 Monte Carlo 资格验证。
- Race detector NOT RUN：默认 CGO_ENABLED=0，当前 PATH 未发现兼容 C 编译器；未安装新 C 工具链。独立调用的并发确定性测试 PASS。

## 7. Phase 3 优先级

1. 先做 Go CPU/heap profile，评估显式 workspace/plan 的跨调用复用 API；每个 goroutine 使用独立工作区。
2. 降低 CSV 每行分配和动态切片增长；在同一 CSV decode 口径下回归测量。
3. 针对 large-prime-factor 长度建立解析精度、Python/SciPy 和性能矩阵，再评估 FFT 后端或算法选项。
4. 扩展低功率容差和极端动态范围测试；具备 C 工具链后运行 race detector。
5. 多段并行 Welch 与其他应用层扩展留作独立设计，保持 Full Scale/整数分段/JSON 契约。

## 8. 发布与隐私审查

主 README 已改为正式项目介绍、Python/Go 使用、公开接口和路线图。
历史基线的本机用户路径与私人 author/committer 信息已清理，当前文件与待提交内容执行同样扫描。
发布使用 Vx.x.x；V2.0.0 上传后删除旧版本标签。敏感信息审查见 [privacy_audit.md](privacy_audit.md)。
