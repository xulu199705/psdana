# Python Golden Reference

## 模块与安装

`psd/core.py` 是仅依赖 NumPy 的计算层；`csvio.py` 负责文本解码和固定数字格式转换；
`plotting.py` 仅接受 PSDResult，用 Matplotlib 绘制 Line。导入 `psd` 不会导入 Matplotlib。
`demo.py` 是命令行入口；两个生成脚本分别负责测试 CSV 和标准 JSON Golden Vector。

Python 3.9+，运行依赖 `requirements.txt`（NumPy、SciPy、Matplotlib）；
测试依赖 `requirements-test.txt`（额外 pytest）。SciPy 用于 QAM 卷积/插值和测试交叉验证，
不参与 PSD Core 计算。完整必选/可选参数、默认值和多种调用示例见 [API Reference](API.md)。

从项目根目录安装与验证：

```powershell
python -m pip install -r python/requirements-test.txt
python python/generate_test_data.py
python python/generate_golden.py
python -m pytest python/tests -q
```

仓库随附生成的数据和向量，可直接执行测试。若临时目录权限受限，使用
`python -m pytest python/tests -q -p no:cacheprovider --basetemp=.pytest-tmp`。
pytest 会清空 `.pytest-tmp`，该目录只用于测试。
生成器可重复运行；固定 PCG64 seed=20261008，CSV 使用 17 位有效数字，不使用下载和时间戳。
清单记录输入 SHA256，可验证同一 NumPy 环境内的逐字节复现；不同 NumPy/FFT 实现仍以数值容差比较。

## Golden API

当 Python 的 import 搜索路径包含本目录时：

```python
import numpy as np
from psd import PSDConfig, compute_psd
from psd.csvio import CSVConfig, read_csv
from psd.plotting import plot_psd

x = np.exp(2j * np.pi * 40e6 * np.arange(1024) / 160e6)
result = compute_psd(x, PSDConfig())
print(result.integrated_power)   # 1.0
plot_psd(result)                 # 调用 plt.show()，不保存

capture = read_csv("data/sine_+40MHz_160MSPS.csv", CSVConfig(sample_format="hex_q15"))
result = compute_psd(capture.samples, PSDConfig(fft_points=1024))
```

`compute_psd` 接受一维非空 numeric sequence，内部转换为 float64 或 complex128。
输入 dtype 为 complex 即采用复数双边谱，即使 imag 全为零；实数 dtype 采用单边谱。
bool、字符串、二维数组、NaN/Inf 输入报错。整数序列在核心中只做浮点类型转换；
需要 Q1.15 时应在 CSV 适配层使用 `q15` / `hex_q15`，或由调用者明确除以 32768。
核心不根据数据最大值自动归一化。

PSDConfig：

| 字段 | 默认 | 规则 |
|---|---|---|
| fs | 160e6 | 有限正数，Hz |
| window | hann | hann / rectangle |
| fft_points | all | `all` 或正整数；拒绝 bool、浮点整数与数字字符串 |
| overlap | 0.5 | 有限值，`0 <= overlap < 1` |
| detrend | none | none / mean，每段加窗前去均值 |

输入长度 M，FFT 长度 N：

- `all` 或 N=M：一次 Periodogram，overlap 不参与分段。
- N<M：Welch，`overlap_samples=floor(N*overlap)`，`hop=N-overlap_samples`。
- 分段起点为 `0, hop, 2*hop, ...`，只使用起点满足 `start+N<=M` 的完整段。
- 段数 `1+floor((M-N)/hop)`。尾部不足整段的数据丢弃，不进行隐式补零。
- N>M 报错。N 不要求 2 的幂。
- N=1 Rectangle 合法；N=1 Periodic Hann 的窗口全为零，报错。
- N=2 Hann 按公式计算，ENBW=fs（即 2 个 bin）；常用 Hann 的 1.5-bin ENBW 对 N>=3 成立。

PSDResult 的数组都是 float64，顺序与 frequency_hz 完全一致：

| 字段 | 定义 / 单位 |
|---|---|
| frequency_hz | 实数单边 / 复数 fftshift 双边，Hz |
| psd_linear | 绝对 PSD 密度，normalized input-unit squared/Hz，未除以 P_FS |
| psd_dbfs_per_hz | `10*log10(psd_linear/P_FS)`，dBFS/Hz |
| rbw_power_dbfs | `10*log10(psd_linear*ENBW/P_FS)`，dBFS |
| fft_size, fs_hz | 当前 FFT 点数、采样率 |
| frequency_resolution_hz | `df=fs/N`，Hz |
| enbw_hz | Equivalent Noise Bandwidth，Hz |
| coherent_gain | `sum(w)/N` |
| window_power_sum | `sum(w^2)` |
| segment_count | 完整段数 |
| window, input_type | 窗名称、real / complex |
| reference_power | 实数 0.5、复数 1.0 |
| method, detrend | periodogram / welch、none / mean |
| overlap_samples, hop_size | 生效的重叠点数、步长；Periodogram 为 0、N |
| input_sample_count, used_sample_count | 输入长度、最后一完整段结束位置 |
| discarded_tail_samples | 输入长度减 used_sample_count |
| integrated_power | 属性：`sum(psd_linear)*df`，绝对平均功率估计 |

## PSD、窗口和 Full Scale 定义

采用未归一化的 forward DFT：

```text
X[k] = sum_n x[n]*w[n]*exp(-j*2*pi*k*n/N)
Pxx[k] = |X[k]|^2 / (fs*sum_n w[n]^2)
Periodic Hann: w[n] = 0.5-0.5*cos(2*pi*n/N)
Rectangle: w[n] = 1
CG = sum(w)/N
ENBW = fs*sum(w^2)/sum(w)^2
```

N>=3 的 Hann：CG=0.5，窗口平方和=3N/8，ENBW=1.5fs/N。
Rectangle：CG=1，窗口平方和=N，ENBW=fs/N。

复数输入保持双边功率，经 fftshift 排序；`I+jQ=exp(+j*2*pi*f*n/fs)` 对应正频率。
偶数 N 轴含 -fs/2，不含 +fs/2；奇数 N 范围是 `±floor(N/2)*fs/N`。

实数输入保留 `k=0..floor(N/2)`：偶数 N 只对 `k=1..N/2-1` 翻倍，
DC 和 Nyquist 保持原功率；奇数 N 对所有 `k>=1` 翻倍（没有 Nyquist bin）。

Full Scale 是固定的功率参考：

- 复数满幅单音 `|x|=1`，平均功率 P_FS=1。
- 实数满幅正弦峰值 A=1，平均功率 P_FS=0.5。
- Q1.15：signed int16 / 32768，范围 [-1, 32767/32768]。
- 不使用当前文件最大值归一化；超过 0 dBFS 的结果不裁剪。

密度输出和显示输出具有不同物理量：

```text
PSD_dBFS/Hz[k] = 10*log10(Pxx[k]/P_FS)
RBW_power_dBFS[k] = 10*log10(Pxx[k]*ENBW/P_FS)
P_est = sum_k Pxx[k] * df
```

对于相干、bin-centered 单音，复数峰值或普通实数正弦峰值经 ENBW 校准为 0 dBFS，
Hann / Rectangle 校准一致。实数正弦须具有正常分离的正负频率主峰；
DC、Nyquist 不是此处定义的普通实数正弦，单位幅度的实数 DC/Nyquist 总功率为 1，
以 P_FS=0.5 参考得到 +3.0103 dBFS。极短奇数 FFT 的边缘 bin 可能发生 Hann 正负主瓣重叠。
非相干单音存在 scalloping loss；半 bin 偏移时 Hann 约损失 1.424 dB，Rectangle 约 3.922 dB。

不能对 RBW 校准 bin 直接相加恢复功率（Hann 的 ENBW/df=1.5），也不能将 dBFS/Hz 当成 dBFS。
Welch 逐段 detrend、加窗、FFT、算线性 PSD、线性平均，最后才转换成 dB。

Parseval 的严格关系为每段 `sum(|x_detrended*w|^2)/sum(w^2)`，Welch 再按段平均。
Rectangle 未 detrend 且无尾部丢弃的单次 Periodogram 严格恢复原平均功率；
一般 Hann 输入不保证等于未加窗平均功率。对白噪声验证 ensemble mean，按样本数设置统计容差。
零密度对应 -inf dB；核心保留 -inf，不产生 NaN。绘图使用 -300 dB 有限显示下限，不修改结果。

## CSV 与 CLI

CSVConfig 的格式是显式配置：

- `float`：归一化实数浮点（允许超过 Full Scale，不自动归一化）。
- `q15`：十进制 signed int16，必须在 [-32768,32767]。
- `hex_q15`：1–4 位 hexadecimal word（允许 0x 前缀），two's complement 解码。
- `header=auto/yes/no`；`delimiter=None` 自动识别逗号、分号、Tab，或显式给定一个分隔符。
- `real_column` 或同时指定 `i_column/q_column`：表头名称或从零开始的整数列索引。
- 无表头的单列数据可自动读取；名为 i/q 的列可自动识别并按 I/Q 角色重排。
- 无表头两列不自动猜测顺序；`input_type=iq` 可明确声明第一列 I、第二列 Q，或指定两列索引。
- 多列缺乏 I/Q 标签时必须指定数据列；列数不一致、缺值、歧义或非法数值均报错。
- header auto 对第一行进行数字解析，不推断 ADC 格式；十六进制看起来像数字的列名应指定 header=yes。
- 若列名为纯数字/十六进制字符串，或第一行意图不明确，应显式指定 header 和列选择。
- 注释行、嵌套元信息、packed ADC words 和复数字符串不属于此读取器的格式。

原始 `data/sine_+40MHz_160MSPS.csv`：表头 `q,i`，列索引 I=1、Q=0，
8192 个样本，每个 I/Q 字段是 4 位 16-bit hexadecimal word，需使用 `hex_q15`。

```powershell
python python/demo.py
python python/demo.py --no-show
python python/demo.py --input data/generated/T01_complex_positive_tone.csv --fft-points 256
python python/demo.py --input data/generated/T09_q15_iq.csv --sample-format q15 --i-column i --q-column q
python python/demo.py --input data/sine_+40MHz_160MSPS.csv --sample-format hex_q15 --fft-points 1000 --detrend mean
python python/demo.py --display dbfs_per_hz --window rectangle --overlap 0.5
```

`--input` 相对路径按项目根目录解析；两个生成器默认输出目录也由自身位置确定。
正常调用绘图执行 `plt.show()`，不保存文件。`--no-show` 仍构建频谱图但不阻塞；
测试使用 Agg backend，并验证 show 行为、单位、Line 绘图及计算层隔离。
绘图 API：`plot_psd(result, display="dbfs", freq_unit="MHz", show=True)`，返回 `(figure, axes)`。
允许 freq_unit=Hz/kHz/MHz/GHz，不重新读取输入或计算 FFT。

## 生成数据与独立验证

`data/generated/manifest.json` 记录 Sample Rate、Sample Count、Sample Format、频率、幅度、
解析功率、实际离散平均功率、随机种子以及 CSV SHA256。

| ID | 输入 | 点数 | 解析平均功率 / 用途 |
|---|---|---:|---|
| T01 | +40 MHz 复数，A=1 | 1024 | 1；频率、0 dBFS |
| T02 | -40 MHz 复数，A=1 | 1024 | 1；方向 |
| T03 | 40 MHz 实数，A=1 | 1024 | 0.5；实数 Full Scale |
| T04 | +40 MHz A=.75，-25 MHz A=.25 | 1024 | .625；双音相对功率 |
| T05 | 复高斯白噪声 | 8192 | ensemble mean .04；归一化、Welch |
| T06 | 40.078125 MHz 复数，A=.8 | 1024 | .64；半 bin 偏移、泄漏 |
| T07 | 复数零输入 | 512 | 0；-inf 和 JSON null |
| T08 | 20 MHz A=.5，加 .25+j*.125 DC | 1024 | .328125；detrend 后 .25 |
| T09 | 40 MHz 复数，A=.8，decimal Q1.15 | 1024 | .64（量化前）；转换 |
| T10 | 137/999*fs 复数，A=.6 | 999 | .36；奇数非 2 的幂 FFT |

测试结构：

- `test_core.py`：解析窗参数、满幅单音、Parseval、DC/Nyquist/奇数最后 bin、线性 Welch、
  overlap/tail、异常参数、零输入、NaN/Inf，及 SciPy Periodogram/Welch 参数化对照。
- `test_csvio.py`：单列、IQ 顺序、表头/无表头、索引/名称、分隔符、Q1.15 和错误行为。
- `test_regression.py`：T01–T10 端到端、原始 CSV 哈希/幅度、噪声与泄漏、可重复生成、
  CLI 跨工作目录、绘图隔离及每个 Golden Vector 的独立 SciPy 对照。

SciPy 使用 Periodic window (`get_window(..., fftbins=True)`)、density scaling、匹配单双边和 detrend、
相同 N/noverlap；复数结果经 fftshift。测试不依赖 GUI，也不只凭自身 Golden 数据证明正确性。

## Golden JSON 与后续移植

`data/golden/index.json` 列出 17 个向量及其 SHA256，覆盖全部 T01–T10、两个窗口、
Periodogram/Welch、mean detrend、real odd FFT、非 2 次幂和零输入。
不为原始 8192 点 CSV 导出完整频谱 JSON。

每个向量包含：

- schema/algorithm version，源 CSV 相对路径（**相对于向量文件目录**）、SHA256、CSVConfig、输入描述。
- PSDConfig（fft_points 使用 JSON string `all` 或整数），Full Scale、FFT 和窗公式及单位。
- expected 中的全部 PSDResult 字段和 integrated_power。
- frequency_hz、psd_linear、psd_dbfs_per_hz、rbw_power_dbfs 数组，以及窗口与分段元信息。
- tolerances 与 nonfinite_policy。

复数以 CSV 的 i/q 两列表达，绝不使用 Python complex 字面量。
JSON 的 dB 数组中 `null` 表示零功率的负无穷；线性 PSD 和频率始终为有限 JSON number。
禁止非标准 `Infinity` / `NaN`；导出使用 `allow_nan=False`。

后续 Go/TypeScript 验证步骤：

1. 读取 index/vector，通过相对路径找到 CSV，验证 SHA256，再按 CSVConfig 转换样本。
2. 使用原样 PSDConfig，复现 forward FFT 符号、Periodic Hann、floor overlap、完整段选择和功率归一化。
3. 比较频率和线性 PSD：`abs(actual-expected) <= atol + rtol*abs(expected)`。
4. 元信息字符串/整数精确比较；浮点元信息按单独容差比较。
5. 对 expected PSD 大于 `1e-20` 的 bin 比较 dB，绝对容差 `1e-7 dB`。
   更小的 bin 往往由浮点 FFT 消去误差决定，只比较线性 PSD，不强求极深噪声底的 dB 一致。
6. `null` 解码为 -inf；跨 FFT 库若零附近产生数值残余，按线性容差判断。
   T07 真正全零输入必须输出精确零 PSD 和对应 null/-inf。
7. 使用 `sum(psd_linear)*df` 验证功率，保留独立解析测试和目标语言参考库对照。

固定向量是 Phase 1 的数值契约；未来算法变更应明确更新版本与向量，而非偷偷改变 Full Scale 或列含义。

## 范围与限制

未覆盖极限性能、大型流式文件、多线程实时 PSD、GUI、通道组合、校准到 dBm 或硬件验证。
当前只提供 Hann/Rectangle 和 mean/none detrend，不做抗混叠、采样率推断或仪器幅度修正。
统计验证使用一个固定噪声 seed，不等同于广泛 Monte Carlo 统计资格验证。
极端动态范围受 float64 溢出/下溢限制；超出 Nyquist 的信号会按采样理论 alias。
不实现隐式补零、补尾、自动幅度归一化或实数信号强制双边选择。
Go 已完成对应 Core；TypeScript 尚未实现。移植应保持 FFT 归一化、实数偶/奇端点和 JSON null 语义一致。

## V2.0.1：频段与点频功率

```python
from psd import PowerResult, analyze_band_power

power = analyze_band_power(result, 39e6, 41e6)
print(power.peak_frequency_hz, power.peak_power_dbfs, power.average_power_dbfs)
# 标准 JSON：json.dumps(power.to_dict(), allow_nan=False)
point = analyze_band_power(result, 40e6, 40e6)
```

函数只消费已有 PSDResult；不重算 FFT、不读取 CSV、不修改数组、不依赖 Matplotlib。
验证 fs/df/ENBW、输入类型、Full Scale、数组维度、非负有限 PSD 和 FFT 频率轴；非法输入抛出 ValueError。

| PowerResult 字段 | 语义 |
|---|---|
| freq_left_hz / freq_right_hz | 原请求边界，Hz |
| is_point | 两边界相等 |
| peak_frequency_hz | 实际选中 signed bin 中心；零功率为 None |
| peak_power_dbfs | max(Pxx*ENBW) 相对 P_FS 的 dB |
| average_power_dbfs | 带内积分功率相对 P_FS 的 dB；点频时与 Peak 相等 |
| band_power_linear | 绝对输入单位平方；点频时为 RBW 功率 |
| contributing_bins | 正重叠宽度的 distinct signed bin 数；点频为 1，零功率 bin 仍计数 |

边界严格满足 `-fs/2 <= left <= right <= fs/2`；NaN/Inf、逆序、越界报错，没有固定 MHz epsilon。
非零带宽采用 `[left,right)`，bin 单元为 `[center-df/2,center+df/2)`，以 fs 为周期折回 Nyquist 两端。
网格由 FFT bin 序号与 df 建立，频率轴一致性检查仅允许与 float64 精度成比例的舍入误差。
带内功率为 `sum(Pxx*overlap_width)`；Peak 对参与 bin 的完整 RBW 功率取最大，不按重叠比例缩小 Peak。
部分重叠或周期折回时，返回的 bin 中心可以位于请求范围外；例如正端 Nyquist 单元的中心表示为 -fs/2。
全 Nyquist 积分与原 integrated_power 一致。Average 是时间平均信号功率估计，不是 mean(PSD)、mean(dB) 或 sum(RBW)。

点频按网格中心距离选最近 bin，等距选较低频率；功率并列也选较低频率。
`left=right=+fs/2` 从左侧逼近，选择当前 signed 表示中严格低于 +fs/2 的最高 bin，不创建 +fs/2 bin。
偶数 Nyquist 中心表示为 -fs/2，其积分单元在两个边界各占一半；点频 -fs/2 可直接选择该中心。

实数输入先构建等效双边谱：内部单边 PSD 正负各一半，DC/偶数 Nyquist 不分裂，奇数最后正频率仍需分裂。
正负实数单音频段互为镜像；单侧 Peak 常比原单边图低 3.0103 dB，Full Scale 仍为 P_FS=0.5。
PSD 密度单位 dBFS/Hz；Peak 和带内 Average 单位 dBFS。Hann 相干单音的单 bin 积分只有总功率的 2/3；
包含完整主瓣或全带才能恢复总功率。非相干信号、窄带和噪声结果受 FFT 分辨率、窗泄漏及 Welch 估计影响。

零功率输出 -Inf，峰值频率 None；PowerResult.to_dict() 将这两种情况转换为标准 JSON null。
极端有限输入若使 PSD/功率中间值溢出、归一化尺度或 df 无法表示，compute_psd 明确抛出 ValueError。
极小 fs 下使用等价 bin*df 频率轴，避免 NumPy 的 N/fs 中间值溢出；正常参数保持原计算路径。
float64 功率下溢可能成为精确零；没有额外噪声门限，也不裁剪超过 0 dBFS 的值。

CLI 支持成对的 Hz 参数，显式 0 与未提供区分：

```shell
python python/demo.py --freq-left 40000000 --freq-right 40000000 --no-show
python python/compare_power_go.py
python -m pytest python/tests -q
```

test_power.py 使用解析单音/双音、精确有理数周期积分和真实 CSV 验证；比较脚本同时执行
共享 PSD 与独立 PSD 两种跨语言验证，并检查异常边界。原 17 组 Golden 保持冻结。
结果见 [V2.0.1 报告](../go/reports/v2.0.1_validation.md)。

## V2.1.0：Python QAM Golden Reference

单路接收链为：原始 IQ → 单位能量 RRC matched filter → polyphase 分数定时搜索 →
粗/细 residual CFO 搜索 → DC/RMS/固定相位和复数 scalar fit → 最终判决及指标。
没有自适应均衡器、DFE、CMA/LMS 或 image cancellation。QAM 的符号归一化不改变原始 PSD。
Core 不读取 CSV，不加载 Matplotlib；绘图只消费 QAMResult，不重新解调。
公开 QAMConfig/QAMResult、全部参数和数学公式见 [QAM API](API.md#qam-api)。

EVM 是 Decision-Directed RMS EVM，不是有发送参考的实测 Data-Aided EVM。
Amplitude Error 和 Phase Error 分别为误差矢量的径向/切向归一化 RMS，满足
`EVM²=AmplitudeError²+PhaseError²`。Phase Error (%) 不是 Phase Error (deg RMS)，
后者是主值角度误差的 RMS。全部指标用相同的正式有效符号及判决；绘图抽样不影响指标。

64QAM levels=±1/±3/±5/±7，除以 sqrt(42)，平均理想星座功率 1。
Blind receiver 具有 90° 相位模糊，不恢复 bit 序列；gain/phase/DC 是同步诊断，
不应解释为 ADC 绝对增益或绝对载波相位。默认 CFO 范围 ±5000 Hz，正输入旋转对应正 Frequency Error。
关闭 CFO 时输出 None，不能解释为 0 Hz。边界告警按一个粗网格间隔定义，
超范围频偏可能落入内部局部最小，未必触发边界告警。高残余 EVM/低星座占用/短捕获明确报错。

真实输入 `data/qam64_20MSymPS_160MSPS_RRC0p25.csv` 已检查为：
表头 q,i，逗号分隔，每行一个 IQ，16384 样本，16-bit HEX two's complement Q1.15；
I=列 1，Q=列 0。无 valid、序号或时间戳，CSV 本身不能证明无丢样。
应显式使用 hex_q15，不能根据文件名猜测数字格式。

```shell
# 真实捕获，PSD + 星座先创建 figure，再统一一次 show；不保存图片
python python/demo.py --input data/qam64_20MSymPS_160MSPS_RRC0p25.csv --sample-format hex_q15 --qam --symbol-rate 20000000 --rrc-beta .25 --rrc-span 10
# 增加频段功率并禁止交互窗口
python python/demo.py --input data/qam64_20MSymPS_160MSPS_RRC0p25.csv --sample-format hex_q15 --qam --freq-left -15000000 --freq-right 15000000 --no-show
# SPS=2 合成数据
python python/demo.py --input data/generated/qam/Q11_sps2.csv --qam --symbol-rate 80000000 --no-show
# 关闭 CFO / 调整绘图点数
python python/demo.py --input data/generated/qam/Q01_ideal.csv --qam --no-cfo-correction --constellation-points 300
```

程序化组合 `analyze_iq(samples, psd_config=PSDConfig(), qam_config=None, power_band=None)`
返回 IQAnalysis(psd,power_metrics,qam_metrics)，共享同一份 IQ，不把 QAM 加入 compute_psd。
QAMResult.to_dict 可导出标准 JSON；复杂诊断分离 real/imag，未估计 CFO 为 null，非有限结果拒绝。
当前 Python CLI 仍为文本模式。Packed64 可由新增 iqio.read_packed64 明确读取，不改变 csvio 既有语义。

星座图 `plot_constellation(result,show=True)` 返回 figure/axes；
完整理想点是 #FF3B30 红色空心圆，恢复符号是 #FFE45C 亮黄色、alpha=.4 小圆点，I/Q 比例 1:1。
show=False 支持自动测试，默认 plt.show，不 save；绘图坐标是恢复后的符号，而不是 ADC 样本。

### QAM 数据、真值与 Golden

```shell
python python/qam_gen.py
python python/generate_qam_golden.py
python -m pytest python/tests -q
```

生成器只写 `data/generated/qam/`，12 组 Q01–Q12 覆盖理想、AWGN、正负 CFO、固定相位、
gain、IQ imbalance、DC、综合损伤、Q1.15、SPS2、SPS8/分数定时。
采用固定 seed、三周期 RRC 成形后提取中间周期，保留未修改的发送符号 CSV。
manifest 记录所有注入量、SHA256、样本功率、32767 量化乘数与 32768 解码除数及 clipping 数。
Q10 另提供 packed64，两采样字的时序/IQ 布局见 API；不进行隐式补样。
不同 fixture seed 的有限样本 DC 估计与 RRC 截断 ISI 会使理想信号有非零 EVM，
注入 AWGN 的百分比是设定的噪声比，不是强制的接收 EVM Golden。

独立 qam_reference.py 仅用于合成真值验证：整数符号时移及 90° 象限对齐，
对同一盲接收输出用 Cartesian 公式独立计算 Data-Aided 指标，不重新做 scalar/reference fitting。
RRC 连续公式/直接 FIR、解析误差分解、已知 CFO/定时及不可靠输入测试提供独立依据。

独立 `data/golden/qam/index.json` 当前含 13 组向量（12 组合成 + REAL64），
输入路径相对向量目录，验证源 CSV/vector SHA256，保存完整配置/指标、128 个绘图点、
全部理想点和诊断/容差。旧 PSD index 与 17 组向量不变。
生成 Golden 是显式维护操作；日常回归不要重写向量以绕过失败。
没有真实捕获时相关测试明确 skip/BLOCKED，不以合成样本代替真实验收。

真实默认结果、全部测试与限制见 [V2.1.0 验证报告](reports/v2.1.0_qam_validation.md)。

## V2.1.1：显式 Joint-fit 与可靠性评估

默认 Legacy 原样保留，仍使用 qam-blind-scalar-1，旧13组QAM及17组PSD Golden不变。
新增可选 keyword-only `dc_mode="decision_directed_joint"`，适用于 analyze_qam、recover_symbols、
scalar_qam_fit、search_residual_cfo、analyze_iq；QAMConfig 不添加字段，保持 Legacy JSON 兼容。
新算法版本 qam-blind-scalar-2，对同一输入符号 z 联合估计 z=a*d+c，再用 (z-c)/a 校正。
DC 在符号域定义，不是 ADC 绝对电压；初始化和每轮判决仍为 Blind，不使用发送真值。
定时/CFO评分使用同一模式，新模式额外做一次 CFO-aware 全相位复查，仅相位改变时再次搜索CFO。

```shell
python python/demo.py --input data/qam64_20MSymPS_160MSPS_RRC0p25.csv --sample-format hex_q15 --qam --qam-dc-mode decision_directed_joint --no-show
python python/validate_qam_refinement.py
python python/benchmark_qam.py --repeats 5
python -m pytest python/tests -q
```

Q01 Legacy=2.551702%，Joint=1.052249%；一次独立已知符号联合LS得到1.052249%。
真实输入 Legacy=2.596191%，Joint=1.736166%，与用户补充的频谱仪“2%以下”一致；
真实数据没有 TX truth，**更低的 Blind EVM 不一定代表更接近真实物理 EVM**。
不能把 CFO fine grid 步长当成精度，新模式未知估计误差/不确定度均为 None。
保留 candidate/warning，拒绝结果通过 QAMRecoveryError 提供 unreliable 诊断。
纯噪声等反例、超范围CFO、错RRC/时序/极性均有实际扫描记录，不把低EVM作为绝对锁定证明。

新 `data/golden/qam/v2/` 有18个Joint receiver向量，另有5组短/长记录数据在 generated/qam/v2。
生成脚本 generate_qam_v2.py 只写新目录，不重新生成原Golden。
qam_joint_reference.py 用已知CFO与单次lstsq独立验证 a/c，同时报告同一接收输出的TX真值EVM及判决错误。
时移/90°模糊仅作对齐，TX符号不修改，无额外自适应均衡。

Benchmark覆盖16384、65536、262144、1048576 IQ，七项组件/整体，预热后5次median/p90。
每规模/模式独立进程，BLAS线程数1，输入生成/启动/I/O不计时；插值数组精确增长到256 MiB。
Windows working-set peak是整个worker历史峰值，含导入/生成/预热，不是单阶段或接收机专属峰值。
测试矩阵、实际性能及条件Go Gate见 [V2.1.1报告](reports/v2.1.1_qam_refinement.md)
和 [Benchmark明细](reports/v2.1.1_qam_benchmark.md)。

Stage A Gate已通过，Go本版仅新增数学Foundation；36组共享向量由
`python/generate_qam_foundation.py` 写入独立 `data/golden/qam/v2/foundation/`。
完整Go QAM receiver仍未实现。已确认偏斜256QAM可在错误判决处稳定，
因此 joint_fit_converged 不能解释为 TX truth 锁定。

根README展示的PSD与星座PNG由真实CSV实际计算，重建命令：
`python python/render_readme.py`。这是明确的文档导出功能，库绘图默认仍仅show。
