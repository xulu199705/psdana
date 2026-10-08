"""Assemble the V2.1.2 engineering report from completed measured evidence."""
import json
from pathlib import Path
from qam_gen import ROOT

REPORTS=ROOT/'go/reports'
def load(name):return json.loads((REPORTS/name).read_text(encoding='utf-8'))
def run():
    stages=load('v2.1.2_stage_validation.json');benchmark=load('v2.1.2_qam_benchmark.json')
    reliability=load('v2.1.2_reliability_validation.json');audit=load('v2.1.2_audit.json')
    real_benchmark=load('v2.1.2_real_benchmark.json')
    assert len(real_benchmark['measurements'])==4
    baseline=json.loads((ROOT/'.cache/v212/benchmark-preoptimization.json').read_text())
    meta=json.loads((ROOT/'data/generated/qam/manifest_v2.1.2.json').read_text())
    assert len(benchmark['measurements'])==28,'incomplete benchmark matrix'
    benchmark['policy']='Python one warmup; Go untimed batch calibration >=50ms, operations_per_repeat records batch size; p90 for Go short stages is per-batch average; startup, generation, CSV and JSON excluded; stage buffers prepared; Joint timing includes two sweeps; CFO one search; max 30000 analysis/12000 CFO symbols'
    benchmark['input_policy']='synthetic qam_gen for length trends; 32768 uses decoded Q13 Q1.15 fixture'
    (REPORTS/'v2.1.2_qam_benchmark.json').write_text(json.dumps(benchmark,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    assert audit['protected_files_changed']==[]
    results=stages['receiver_cases']
    lines=['# psdana V2.1.2 QAM validation','',
        '## 1. 实现范围与状态','',
        '**PASS：本版约定的 Go Receiver、逐级数值验证、CLI/JSON、两类工程输入、Benchmark及完整回归。**',
        '盲接收可靠性保留既有边界；已拒绝双音的对称近似并列候选属于下述明确数值例外，不声称全部反例逐候选等价。','',
        '- 基线 HEAD：`f71da2918f50edd362725d9c11022c36fa0ded5f`，初始工作区干净，tag仅V2.0.0。交付按用户追加指令commit/push到GitHub，不创建V2.1.2标签。',
        '- 新增 config/filter/interpolator/timing/carrier/receiver/result；公开AnalyzeQAM、RecoverSymbols及分阶段接口。',
        '- Foundation复用；Core无CSV、绘图、Python或进程依赖。直接FIR保持fftconvolve same对齐，包含偶数tap和任意输入长度。',
        '- Polyphase使用Kaiser sinc FIR、归一化及延迟补偿，完整插值数组保留；Joint refinement最多两次timing和两次CFO。',
        '- CLI增加12个QAM开关，PSD仍位于JSON顶层；qam_metrics可选、power_metrics保持原行为。disabled CFO为null。',
        '- QAMErrorMetrics公式和Full Scale不变；相位模糊90°，比较不额外旋转/拟合来减小误差。','',
        '## 2. 基线与最终测试','',
        '| 验证 | 实际结果 |','|---|---|',
        '| Python默认临时目录首轮 | 391 passed / 47 setup errors；默认临时目录不可写 |',
        '| Python V2.1.1重跑 | 438 passed / 108.70 s；仓库内basetemp，原BLAS设置 |',
        '| Go V2.1.1 | 全部原package PASS |',
        f"| Python最终 | {audit['python_final_summary']} |",
        '| Go fmt / vet / test -count=1 ./... | PASS |',
        '| PSD / Legacy / Joint / Foundation旧Golden | 17/17、13/13、18/18、36/36 PASS，原容差 |',
        '| 32768 Q1.15新Golden | 2/2 PASS，独立v2.1.2 index |',
        f"| 完整数组跨语言 | {len(results)}组Receiver、60组FIR/插值矩阵 PASS |",
        '| 可靠性/CFO/CLI | 26可靠性 + 22 CFO + 4 CLI比较；双音Joint例外有量化证据 |',
        '| API examples | Python 6/6、Go 7/7文档代码块；Go全部既有Example及新增AnalyzeQAM示例PASS |',
        f"| 字节保护 | {audit['protected_file_count']}个既有数据/PSD/Power/CSV/module文件与HEAD内容核对，无更改 |",
        '| Go race | NOT RUN；本任务未引入共享全局workspace，未把普通测试当成race验收 |','',
        '可重跑命令（仓库根目录）：','',
        '```shell',
        'python -m pytest python/tests -q --basetemp .cache/v212/pytest-final',
        'go -C go fmt ./...', 'go -C go vet ./...', 'go -C go test -count=1 ./...',
        'go -C go build -o ../.cache/v212/qamcheck.exe ./cmd/qamcheck',
        'go -C go build -o ../.cache/v212/qambench.exe ./cmd/qambench',
        'go -C go build -o ../.cache/v212/psdana.exe ./cmd/psdana',
        'python python/compare_qam_go.py','python python/validate_qam_go_v212.py',
        'python python/benchmark_qam_v212.py','python python/benchmark_qam_v212.py --real-capture','```','',
        '## 3. 分阶段数值证据','',
        'SciPy 1.18.0本机resample_poly/firwin/upfirdn设计与索引经源码复核；[官方语义](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html)。',
        'FIR设计20*up+1 taps、cutoff=1/up、Kaiser β=8、系数乘up；down=1的预填充与切片抵消，输出N*up。',
        '矩阵包含impulse/tone/random，N=31/127/1023/32768，FIR长度1/2/7/16/81；每组完整逐样本比较。',
        'Receiver覆盖两模式×真实/Q13/SPS2/SPS8分数偏移、非symbol-period整倍数长度、255点星座抽样、关闭CFO/Q反号及up=1；比较tap、完整matched/up、全部timing评分、粗细CFO评分、全部raw/eq/decisions/indices、gain/DC及全部Python诊断字段。',
        '有界证据见[Stage JSON](v2.1.2_stage_validation.json)。正式Golden不存巨大中间数组。','',
        '| 阶段 | 所有Receiver组最大绝对误差 |','|---|---:|']
    names=sorted({s['stage'] for r in results for s in r['stages']})
    for name in names:
        error=max(s['max_absolute_error'] for r in results for s in r['stages'] if s['stage']==name)
        lines.append(f'| {name} | {error:.12g} |')
    lines += ['',f"60组任意FIR矩阵最大绝对误差：matched={max(r['matched']['max_absolute_error'] for r in stages['filter_cases']):.12g}，interpolated={max(r['interpolated']['max_absolute_error'] for r in stages['filter_cases']):.12g}。"]
    lines+=['','浮点数组使用逐元素绝对/相对阈值；decision index、Timing phase、恢复数量严格一致；CFO按同一粗细网格检查。所有既有Golden容差未改。',
        '非收敛契约：最后LS的gain/DC拟合上一组decisions，最终decisions是最后输出eq的重新切片。',
        'Python/Go新增独立one-iteration回归验证该关系；没有增加隐藏LS或改算法版本。','',
        '## 4. 32768点Q1.15工程输入','',
        '合成qam_gen输入与真实捕获分开。Q13包含AWGN2%、CFO+1000Hz、相位23°、DC .01+.005j与0.5 sample delay，固定seed21232768。',
        '32768 complex samples、4096 TX symbols，160 MSPS、20 MSym/s、64QAM、SPS8、RRC β=.25/span10。',
        f"量化乘数/解码除数：32768/32768；溢出组件{meta['clipped_component_count']}。输入均方功率{meta['quantized_sample_power']:.15g}。",
        f"Input SHA256：`{meta['input_sha256']}`。",f"TX SHA256：`{meta['truth_sha256']}`。",'',
        'FFT32768+Hann：Periodogram，df=4882.8125 Hz，ENBW=7324.21875 Hz，complex P_FS=1。',
        '4074个有效符号参与所有统计，默认每边裁剪11 symbols；不会无条件使用4096 periods。',
        '输入>FFT用Welch、输入<FFT报错、fft_points=all仍使用全部样本；Python/Go新增测试覆盖。','',
        '## 5. 实际16384点捕获及最终指标','',
        '真实qam64_20MSymPS_160MSPS_RRC0p25.csv仍为16384点hex_q15，没有重复、截断或补零。',
        '| 输入 | 模式 | Python EVM % | Go EVM % | 差值百分点 | CFO Hz | Phase up | 有效符号 |','|---|---|---:|---:|---:|---:|---:|---:|']
    for r in results[:4]:
        p,g=r['python'],r['go'];phase=g['diagnostics']['timing_phase_up']
        lines.append(f"| {r['id']} | {r['mode']} | {p['evm_pct_rms']:.12f} | {g['evm_pct_rms']:.12f} | {r['metric_differences']['evm_pct_rms']:.3g} | {g['frequency_error_hz']:.9g} | {phase} | {g['recovered_symbol_count']} |")
    lines+=['','| 输入/模式 | Gain real,imag | DC real,imag | Amplitude % | Phase % | Angle deg |','|---|---|---|---:|---:|---:|']
    for r in results[:4]:
        g=r['go'];d=g['diagnostics'];a,dc=d['complex_gain'],d['dc_offset']
        lines.append(f"| {r['id']}/{r['mode']} | {a['real']:.12g}, {a['imag']:.12g} | {dc['real']:.12g}, {dc['imag']:.12g} | {g['amplitude_error_pct_rms']:.12g} | {g['phase_error_pct_rms']:.12g} | {g['phase_error_deg_rms']:.12g} |")
    lines+=['','PSD/Power/QAM CLI完整对照见[Reliability JSON](v2.1.2_reliability_validation.json)，真实与合成各两模式。',
        'JSON集成测试还直接比较启用QAM前后的所有顶层PSD字段字节，额外字段只有qam_metrics及已请求的power_metrics。','',
        '## 6. 性能与低风险优化','',
        '以下实测使用相同complex128输入SHA256、单线程BLAS环境、独立Python/Go worker；没有重叠运行本任务的数值测试。',
        'Python1次预热、3次重复；Go通过非计时校准把短stage批量至≥50ms，再3次批量重复。',
        'Go短stage median/p90是每批均摊时间的分位数，非单次调用尾延迟；operations_per_repeat记录每批次数。',
        '排除编译、启动、CSV生成/读取、绘图和JSON；包含receiver本身的结果数组生成。component时间不是可相加profiling。',
        'Timing Joint基准包含两次sweep，CFO component包含一次search；total按算法实际是否重搜。Scalar component输入为各语言恢复eq，均来自同一IQ，数值一致性已验证。',
        'P1：等间隔Slicer只比较邻级真实距离，门限/nextafter/边界/三种阶数对照旧实现；Python极大有限数保留argmin舍入并列。',
        'P2：Go Scalar候选只计算EVM，不重复计算最终才需要的径向/切向/相位角；接收调用内RRC/插值各生成一次。',
        '未引入全局可变缓存，未改polyphase内存路径，未改变拟合次序。','',
        '### 32768点所有stage','',
        '| 模式 | Stage | Python median/p90 ms | Go median/p90 ms | Speedup | Go B/op | Go allocs/op |','|---|---|---:|---:|---:|---:|---:|']
    measurements=benchmark['measurements']
    for mode in ('legacy_mean','decision_directed_joint'):
        pair={r['language']:r for r in measurements if r['input_samples']==32768 and r['mode']==mode}
        assert pair['go']['input_complex128_sha256']==pair['python']['input_complex128_sha256']
        for py,go in zip(pair['python']['rows'],pair['go']['rows']):
            assert py['stage']==go['stage'];lines.append(f"| {mode} | {py['stage']} | {py['median_ms']:.6f}/{py['p90_ms']:.6f} | {go['median_ms']:.6f}/{go['p90_ms']:.6f} | {py['median_ms']/go['median_ms']:.3f} | {go['bytes_per_op']:.1f} | {go['allocations_per_op']:.1f} |")
    lines+=['','### 优化前后32768点Receiver','', '| 模式 | Python before/after ms | Go before/after ms |','|---|---:|---:|']
    for mode in ('legacy_mean','decision_directed_joint'):
        values=[]
        for lang in ('python','go'):
            b=next(s['median_ms'] for r in baseline['measurements'] if r['language']==lang and r['mode']==mode for s in r['rows'] if s['stage']=='receiver_total')
            a=next(s['median_ms'] for r in measurements if r['input_samples']==32768 and r['language']==lang and r['mode']==mode for s in r['rows'] if s['stage']=='receiver_total');values.append(f'{b:.6f}/{a:.6f}')
        lines.append(f'| {mode} | {values[0]} | {values[1]} |')
    lines+=['','优化前原始数据另保存为[v2.1.2 preoptimization JSON](v2.1.2_preoptimization_benchmark.json)。时间变化是本机实测，不保证其他机器相同。','',
        '### 输入规模趋势','',
        '| N | FFT | 模式 | Python total median/p90 ms | Go total median/p90 ms | Speedup | Go samples/s | Go symbols/s | Go B/op | Go allocs/op | Python peak MiB |','|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for py in measurements:
        if py['language']!='python':continue
        go=next(r for r in measurements if r['language']=='go' and all(r[k]==py[k] for k in ('input_samples','fft_points','mode')))
        assert py['input_complex128_sha256']==go['input_complex128_sha256']
        a=next(s for s in py['rows'] if s['stage']=='receiver_total');b=next(s for s in go['rows'] if s['stage']=='receiver_total');peak=py['worker_peak_working_set_bytes']/2**20 if py['worker_peak_working_set_bytes'] else None
        lines.append(f"| {py['input_samples']} | {py['fft_points']} | {py['mode']} | {a['median_ms']:.3f}/{a['p90_ms']:.3f} | {b['median_ms']:.3f}/{b['p90_ms']:.3f} | {a['median_ms']/b['median_ms']:.3f} | {b['samples_per_second']:.1f} | {b['symbols_per_second']:.1f} | {b['bytes_per_op']:.1f} | {b['allocations_per_op']:.1f} | {peak:.2f} |")
    lines+=['','全部10 stages×14配置×2语言的median/p90/吞吐量/Go分配见[Benchmark JSON](v2.1.2_qam_benchmark.json)。',
        '长度趋势除Q13外使用固定seed的合成ideal IQ；16384点真实捕获另行测量，不能混用或称趋势行是硬件数据。',
        'Python峰值为Windows worker生命期working-set高水位，包括导入/输入解码/准备buffer/预热/全部stage。',
        'Go峰值内存NOT MEASURED（null）；B/op为runtime累计分配差额，不是驻留或峰值内存，allocs/op为Mallocs差额。',
        '完整插值精确大小N*16*16 bytes，32768点8 MiB、1048576点256 MiB；大输入仍有额外IQ/FIR/workspace及GC开销。',
        '262144/1048576输入触及30000 analysis/12000 CFO符号上限，samples/s不能解读为全部TX符号吞吐。','',
        '### 16384点真实捕获性能','',
        '| 模式 | Python Receiver median/p90 ms | Go Receiver median/p90 ms | Speedup |','|---|---:|---:|---:|']
    for mode in ('legacy_mean','decision_directed_joint'):
        pair={r['language']:r for r in real_benchmark['measurements'] if r['mode']==mode}
        assert pair['python']['input_complex128_sha256']==pair['go']['input_complex128_sha256']
        p=next(s for s in pair['python']['rows'] if s['stage']=='receiver_total');g=next(s for s in pair['go']['rows'] if s['stage']=='receiver_total')
        lines.append(f"| {mode} | {p['median_ms']:.6f}/{p['p90_ms']:.6f} | {g['median_ms']:.6f}/{g['p90_ms']:.6f} | {p['median_ms']/g['median_ms']:.3f} |")
    lines+=['','真实IQ独立worker所有stage、分配及进程峰值见[Real Benchmark JSON](v2.1.2_real_benchmark.json)。','',
        '## 7. 实际问题、风险与资格边界','',
        '- 默认pytest临时目录权限错误已用仓库内basetemp解决；没有修改旧测试或Golden。',
        '- Go短stage计时零值导致Benchmark早期JSON失败；批量校准后完整矩阵通过，失败批次未混入正式报告。',
        '- 真实捕获没有TX truth；Blind EVM、Joint收敛、占用/CFO门限均不能证明绝对锁定。',
        '- 错RRC、极性/IQ交换、样本顺序异常和超范围CFO可以形成candidate，维持Python语义，未增加可信概率/认证。',
        '- 偏斜256QAM Foundation保留640符号中608错误判决、Joint收敛且EVM约3.25%的反例。',
        '- 原始Standalone Slicer极大有限正坐标存在继承差异：Go Foundation显式饱和到最外level；Python argmin在所有距离舍入相同时取最早level。优化分别保留旧行为，没有暗改Foundation兼容契约。本版不声称原始Slicer全float64域跨语言一致；Q1.15/接收机先归一化后的路径不触及该边界。',
        '- FIR采用低风险直接卷积；大N的FFT-FIR和插值内存优化未实施。本版无均衡器、tracking loop、pilot/TX-lock、BER、Go绘图或Web。','']
    for row in reliability['reliability']:
        if 'near_tie_evidence' not in row:continue
        e=row['near_tie_evidence'];lines += [f"### 明确数值例外：{row['id']}/{row['mode']}",'',
            f"两端unreliable。Python CFO={e['python_cfo_hz']} Hz、Go CFO={e['go_cfo_hz']} Hz，竞争评分差={e['competing_score_gap_pct']:.12g}个百分点。",
            f"Timing phase Python={e['python_timing_phase_up']}、Go={e['go_timing_phase_up']}；在同一Python评分曲线上，Go候选与最小值差={e['timing_selected_gap_pct']:.12g}个百分点。",
            f"最终Timing曲线最大误差={e['timing_curve_comparison']['max_absolute_error']:.12g}，raw符号最大误差={e['raw_symbols_comparison']['max_absolute_error']:.12g}。",
            f"raw centered/total power比={e['raw_centered_power_ratio']:.12g}，双音按symbol period采样接近常量；均值消除/离散判决评分对舍入敏感。",
            '非获胜Scalar分支评分差并非全部机器精度；完整网格及各最大误差在Reliability JSON保留：']
        for s in e['scoring_comparisons']:lines.append(f"- {s['stage']}最大差{s['max_absolute_error']:.12g}个百分点；Go选中评分到Python最小值差{s['go_selected_score_gap_to_python_min_pct']:.12g}。")
        lines+=['','没有用这个负例降低旧Golden容差或略过Timing/CFO；正例、真实采样、新32768Golden的索引/网格保持严格一致。','']
    lines+=['## 8. V2.1.3建议','',
        '1. 先实现独立可验证的polyphase按相位/分析区间计算，保留滤波历史与边缘语义，降低大输入内存。',
        '2. 在固定评分契约下复用Scalar workspace、星座/索引buffer，研究Timing/CFO候选评分加速与FFT-FIR。',
        '3. Streaming input与窗口/有限capture契约单独设计，不能把当前离线receiver当成tracking receiver。',
        '4. 先验/pilot/TX aided认证、错误符号率/RRC/极性诊断与已拒绝非QAM退化候选报告。',
        '5. 如需TypeScript前端，保持当前顶层PSD JSON，并另设计明确版本化的展示接口。','']
    (REPORTS/'v2.1.2_preoptimization_benchmark.json').write_text(json.dumps(baseline,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    (REPORTS/'v2.1.2_qam_validation.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Report generated from complete measured evidence')

if __name__=='__main__':run()
