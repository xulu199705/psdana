# PSDANA V2.2.0 — Local WebUI Demo

V2.2.0 新增可运行的本地 WebUI，完成拖入 HEX Q1.15 CSV → 配置参数 → ANALYZE → Go PSD/QAM → JSON → ECharts 6。

## 本版内容

- Go 标准库 net/http 单进程服务，直接复用 csvio、psd、qam；静态页面、ECharts 6.0.0 和 Noto 字体全部内嵌。
- 基于最新 Figma 的 PSD/QAM 页面；540×960 设计基准，9:16 整体等比缩放，最大 1215×2160 CSS px，暖白背景与四周留白一致。
- 全局文件拖入、文件选择、原位参数编辑、共享采样率、Stale 提示与 NO FILE / FILE READY / PROCESSING / COMPLETE / PARTIAL / ERROR 状态。
- PSD 采用真实 psd_dbfs_per_hz；功率指标来自 AnalyzeBandPower；QAM 采用真实星座与误差指标。
- **POWER BAND 允许相等边界进行单点频率测量**：直接使用最近 FFT bin 的 RBW 校准功率，Average 与 Peak 相同；倒置和超 Nyquist 仍拒绝。
- QAM 失败时保留 PSD 并返回 PARTIAL，不复用旧星座；旧请求不得覆盖新文件结果。

## 启动

Windows x64 用户下载 `psdana-V2.2.0-windows-amd64.zip`，解压并运行 `webdemo.exe`，打开：

http://127.0.0.1:8080

只需一个可执行文件，不需要 Go、Python、Node、Docker 或 CDN。包内 README 包含使用说明，`samples/` 提供两份真实示例 CSV。
源码启动：在仓库根目录执行 `go -C go run ./cmd/webdemo`。

## 验证

- `go -C go test ./...` 与 `go -C go vet ./...` 通过，包含既有 Golden 和新增 Handler 测试。
- 真实 64QAM 捕获：HTTP/CLI 全部 24 个既有 JSON 字段相等，Legacy EVM 2.5961906802% RMS。
- 真实 +40 MHz 单音：39–41 MHz 频段及 40→40 MHz 单点均通过；单点功率 −9.0876280440 dBFS，HTTP/CLI 全部 23 个既有字段相等。
- DC、±Nyquist、非 bin 对齐单点、非法输入、请求大小、PARTIAL、参数校验与请求隔离通过。
- 7 种视口、14 张 PSD/QAM 截图及浏览器交互验收通过；另附单点频率截图与 JSON。

完整报告与证据：[V2.2.0 REPORT](https://github.com/xulu199705/psdana/blob/V2.2.0/go/reports/v2.2.0/REPORT.md)。

## 范围与限制

固定 hex_q15、64QAM、FFT all、默认 Legacy DC；仅监听本机 127.0.0.1:8080，请求上限 16 MiB，同一时间执行一个分析。
Blind EVM 结果不构成绝对锁定或硬件物理 EVM 认证。
DSP 算法、既有 CLI 与 Golden 保持不变。FFT workspace、CSV/内存与 Benchmark/Profiling 优化整体后移至 V2.3.0。

`SHA256SUMS.txt` 用于校验 Windows 压缩包。GitHub 自动提供对应 tag 的源码 zip/tar.gz。
