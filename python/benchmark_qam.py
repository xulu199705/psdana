"""Isolated-process QAM benchmark; generation, startup and I/O are not timed."""

import argparse
from dataclasses import asdict
import gc
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np
import scipy
from scipy import signal

from psd.qam import QAMConfig, analyze_qam, rrc_taps, scalar_qam_fit, qam_error_metrics
from psd.qam.carrier import search_residual_cfo
from psd.qam.receiver import _synchronize
from psd.qam.timing import search_timing_phases
from qam_gen import ROOT, generate_signal


def peak_working_set():
    """Windows process lifetime peak working set, not isolated DSP allocation."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb",wintypes.DWORD),("faults",wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in
            ("peak_working_set","working_set","peak_paged","paged","peak_nonpaged","nonpaged","pagefile","peak_pagefile")]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    process = ctypes.WinDLL("kernel32").GetCurrentProcess
    process.restype = wintypes.HANDLE
    query = ctypes.WinDLL("psapi").GetProcessMemoryInfo
    query.argtypes = [wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    query.restype = wintypes.BOOL
    return int(counters.peak_working_set) if query(process(),ctypes.byref(counters),counters.cb) else None


def measure(operation,repeats):
    operation()  # One untimed warmup.
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        operation()
        times.append(time.perf_counter()-start)
    return dict(median_ms=float(np.median(times)*1000),p90_ms=float(np.percentile(times,90)*1000),
                min_ms=min(times)*1000,max_ms=max(times)*1000,repeats=repeats)


def worker(samples,mode,repeats):
    cfg = QAMConfig()
    x,_,_ = generate_signal(symbol_count=samples//8,seed=12345)
    recovered = _synchronize(x,cfg,mode)
    raw = recovered["symbols_raw"].copy()
    eq,decisions = recovered["eq"].copy(),recovered["decisions"].copy()
    cfo = recovered["cfo_hz"]
    cfo_count = recovered.get("cfo_search_evaluations",122)
    count = len(eq)
    del recovered
    gc.collect()
    h = rrc_taps(cfg.rrc_beta,cfg.rrc_span_symbols,8)
    rows = []
    def record(stage,operation):
        stats = measure(operation,repeats)
        stats.update(stage=stage,input_samples=samples,analysis_symbols=count,mode=mode,
                     samples_per_second=samples/(stats["median_ms"]/1000),
                     symbols_per_second=count/(stats["median_ms"]/1000))
        rows.append(stats)
    record("matched_rrc",lambda:signal.fftconvolve(x,h,mode="same"))
    matched = signal.fftconvolve(x,h,mode="same")
    def interpolate():
        return signal.resample_poly(matched,16,1,window=("kaiser",8),padtype="constant")
    record("fractional_interpolation",interpolate)
    up = interpolate()
    def timing():
        search_timing_phases(up,cfg,dc_mode=mode)
        if mode == "decision_directed_joint":
            search_timing_phases(up,cfg,dc_mode=mode,cfo_hz=cfo)
    record("timing_search",timing)
    del up,matched
    gc.collect()
    record("cfo_search",lambda:search_residual_cfo(raw,cfg,dc_mode=mode))
    derotated = raw*np.exp(-2j*np.pi*cfo*np.arange(len(raw))/cfg.symbol_rate_hz)
    record("scalar_fit",lambda:scalar_qam_fit(derotated,dc_mode=mode))
    record("error_metrics",lambda:qam_error_metrics(eq,decisions))
    record("receiver_total",lambda:analyze_qam(x,cfg,dc_mode=mode))
    return dict(input_samples=samples,mode=mode,config=asdict(cfg),rows=rows,
                timing_candidates=128,timing_sweeps=2 if mode=="decision_directed_joint" else 1,
                cfo_search_evaluations=cfo_count,interpolation_array_bytes=samples*16*16,
                worker_peak_working_set_bytes=peak_working_set(),
                memory_scope="isolated worker lifetime peak, includes imports/generation/warmup/all stages; not receiver-only peak")


def run_benchmark(output,repeats=5):
    if repeats < 3:
        raise ValueError("at least three repeats required for median/p90")
    results = []
    for samples in (16384,65536,262144,1048576):
        for mode in ("legacy_mean","decision_directed_joint"):
            environment = os.environ.copy()
            environment.update(OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1",OMP_NUM_THREADS="1")
            completed = subprocess.run([sys.executable,str(Path(__file__).resolve()),"--worker",str(samples),
                "--mode",mode,"--repeats",str(repeats)],capture_output=True,text=True,check=True,env=environment)
            results.append(json.loads(completed.stdout))
            print(f"Benchmark {samples} samples / {mode} completed",flush=True)
    report = dict(environment=dict(os=platform.platform(),python=platform.python_version(),numpy=np.__version__,
                                  scipy=scipy.__version__,logical_cpus=os.cpu_count()),
                  seed=12345,worker_thread_environment=dict(OPENBLAS_NUM_THREADS=1,MKL_NUM_THREADS=1,OMP_NUM_THREADS=1),measurements=results,
                  stage_policy="prepared buffers outside timing; component times need not sum to total; RRC taps fixed for component test",
                  throughput_policy="sample rate uses captured N; symbol rate uses actual analyzed capped symbol count")
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    (output/"v2.1.1_qam_benchmark.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    lines = ["# QAM benchmark — V2.1.1", "", "One warmup, five repeats by default; median/p90; no I/O/startup/generation in timings.", "",
             "| N | Mode | Stage | Median ms | p90 ms | MSamples/s | Analysis symbols/s |",
             "|---:|---|---|---:|---:|---:|---:|"]
    for result in results:
        for row in result["rows"]:
            lines.append(f"| {result['input_samples']} | {result['mode']} | {row['stage']} | {row['median_ms']:.6f} | {row['p90_ms']:.6f} | {row['samples_per_second']/1e6:.6f} | {row['symbols_per_second']:.1f} |")
    lines += ["", "128 timing candidates; Joint runs two timing sweeps, Legacy one. CFO has 81+41 scores per search.",
              "Analysis capped at 30000 symbols; CFO subset capped at 12000. Stages are isolated, not additive profiling.", "",
              "| N | Mode | Interpolation MiB | Worker peak working set MiB |", "|---:|---|---:|---:|"]
    for r in results:
        peak = r["worker_peak_working_set_bytes"]
        lines.append(f"| {r['input_samples']} | {r['mode']} | {r['interpolation_array_bytes']/2**20:.1f} | {peak/2**20 if peak is not None else 'N/A'} |")
    lines += ["", "Working-set peak is the isolated worker lifetime high-water mark, including generation/imports/warmup; not a per-stage or receiver-only peak.",
              "Interpolation byte counts are exact complex128 array sizes. No tracemalloc/RSS equivalence is claimed.",
              "Throughput uses captured sample count and capped analyzed symbol count, respectively."]
    (output/"v2.1.1_qam_benchmark.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"python/reports")
    parser.add_argument("--repeats",type=int,default=5)
    parser.add_argument("--worker",type=int)
    parser.add_argument("--mode",choices=["legacy_mean","decision_directed_joint"],default="legacy_mean")
    args = parser.parse_args()
    if args.worker is not None:
        print(json.dumps(worker(args.worker,args.mode,args.repeats),allow_nan=False))
    else:
        run_benchmark(args.output,args.repeats)
