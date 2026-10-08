"""Reproducible paired Python/Go benchmarks; large fixtures stay in .cache."""

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

import numpy as np

from go_support import ROOT, go_environment, go_executable
from psd import PSDConfig, compute_psd
from psd.csvio import read_csv


def create_fixtures():
    directory = ROOT / ".cache" / "bench"
    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20261008)
    cases = []
    for kind, sizes in (("complex", (999, 333, 1024, 8192, 65536, 1048576)), ("real", (8192, 65536))):
        for size in sizes:
            samples = rng.standard_normal(size) * 0.2
            if kind == "complex":
                samples = samples + 1j * rng.standard_normal(size) * 0.2
            path = directory / f"{kind}_{size}.csv"
            values = np.column_stack((samples.real, samples.imag)) if kind == "complex" else samples[:, None]
            np.savetxt(path, values, delimiter=",", header="i,q" if kind == "complex" else "sample", comments="", fmt="%.17g")
            config = PSDConfig()
            cases.append({"name": f"{kind}_{size}_all", "csv": path.name, "samples": size, "input_type": kind, "config": asdict(config)})
            if size > 1024:
                cases.append({"name": f"{kind}_{size}_welch1024", "csv": path.name, "samples": size,
                              "input_type": kind, "config": asdict(PSDConfig(fft_points=1024))})
    manifest = {"seed": 20261008, "cases": cases}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return directory, cases


def measure(function, repeats, iterations):
    function()  # untimed warmup
    values = []
    for _ in range(repeats):
        started = time.perf_counter()
        for _ in range(iterations):
            function()
        values.append((time.perf_counter() - started) * 1000 / iterations)
    return {"median_ms": float(np.median(values)), "p90_ms": float(np.percentile(values, 90)),
            "min_ms": min(values), "max_ms": max(values), "trials_ms": values}


def run(go=None, repeats=5, iterations=3, reuse_python=False):
    if repeats < 2 or iterations < 1:
        raise ValueError("repeats>=2 and iterations>=1 required")
    reports = ROOT / "go" / "reports"
    reports.mkdir(exist_ok=True)
    python_results = []
    if reuse_python:
        previous = json.loads((reports / "benchmark_results.json").read_text(encoding="utf-8"))
        if previous["repeats"] != repeats or previous["iterations_per_trial"] != iterations:
            raise ValueError("reused Python measurements must have identical repeat/iteration settings")
        directory = ROOT / ".cache" / "bench"
        cases = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))["cases"]
        python_results = previous["python"]
    else:
        directory, cases = create_fixtures()
    csv_results = {}
    for entry in ([] if reuse_python else cases):
        path = directory / entry["csv"]
        samples = read_csv(path).samples
        config = PSDConfig(**entry["config"])
        result = compute_psd(samples, config)
        row = {**entry, "fft_size": result.fft_size, "method": result.method, "segment_count": result.segment_count}
        for scope, function in (("Core", lambda: compute_psd(samples, config)),
                                ("E2E", lambda: compute_psd(read_csv(path).samples, config))):
            metrics = measure(function, repeats, iterations)
            python_results.append({"case": entry["name"], "scope": scope, **row, **metrics})
            print(f"Python {scope}/{entry['name']}: median={metrics['median_ms']:.4f} ms", flush=True)
        if entry["csv"] not in csv_results:
            metrics = measure(lambda: read_csv(path), repeats, iterations)
            csv_results[entry["csv"]] = entry["name"]
            python_results.append({"case": entry["name"], "scope": "CSV", **row, **metrics})
            print(f"Python CSV/{entry['name']}: median={metrics['median_ms']:.4f} ms", flush=True)
    env = go_environment()
    env["PSD_BENCH_DIR"] = str(directory)
    executable = go_executable(go)
    args = [executable, "test", "-run", "^$", "-bench=.", "-benchmem", f"-benchtime={iterations}x", f"-count={repeats}", "./..."]
    print("Running Go testing.B benchmarks...", flush=True)
    completed = subprocess.run(args, cwd=ROOT / "go", env=env, check=True, capture_output=True, text=True)
    (reports / "go_benchmark_raw.txt").write_text(completed.stdout, encoding="utf-8")
    pattern = re.compile(r"^BenchmarkPSD/(Core|CSV|E2E)/([^\s]+?)-\d+\s+\d+\s+([\d.]+) ns/op\s+(\d+) B/op\s+(\d+) allocs/op", re.MULTILINE)
    groups = {}
    for scope, name, ns, bytes_op, allocs in pattern.findall(completed.stdout):
        groups.setdefault((scope, name), []).append((float(ns) / 1e6, int(bytes_op), int(allocs)))
    go_results = []
    for (scope, name), trials in groups.items():
        times = [t[0] for t in trials]
        if len(times) != repeats:
            raise ValueError(f"incomplete Go repetitions for {scope}/{name}: {len(times)}")
        go_results.append({"case": name, "scope": scope, "median_ms": float(np.median(times)),
                           "p90_ms": float(np.percentile(times, 90)), "min_ms": min(times), "max_ms": max(times),
                           "trials_ms": times, "bytes_per_op": float(np.median([t[1] for t in trials])),
                           "allocations_per_op": float(np.median([t[2] for t in trials]))})
    if len(go_results) != len(python_results):
        raise ValueError(f"benchmark result count mismatch Python={len(python_results)} Go={len(go_results)}")
    environment = {"platform": platform.platform(), "python": sys.version, "numpy": np.__version__,
                   "go": subprocess.check_output([executable, "version"], text=True).strip(),
                   "gonum": subprocess.check_output([executable, "list", "-m", "gonum.org/v1/gonum"], cwd=ROOT / "go", env=env, text=True).strip(),
                   "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                   "GOMAXPROCS": env.get("GOMAXPROCS", "runtime default"), "OMP_NUM_THREADS": env.get("OMP_NUM_THREADS", "unset")}
    payload = {"environment": environment, "repeats": repeats, "iterations_per_trial": iterations,
               "python_measurements_reused": reuse_python,
               "statistic": "median/p90 of per-trial mean time; each trial uses identical iteration count",
               "memory_policy": "Go B/op=allocated bytes/op, not resident/peak RSS; Python RSS/tracemalloc not measured",
               "python": python_results, "go": go_results}
    (reports / "benchmark_results.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lookup = {(r["scope"], r["case"]): r for r in go_results}
    lines = ["# Phase 2 paired performance measurements", "", f"{repeats} trials × {iterations} iterations; untimed warmup. Speedup = Python / Go.", "",
             "| Scope | Case | N / FFT | Python median ms (p90) | Go median ms (p90) | Speedup | Python / Go MSamples/s | Go B/op / allocs/op |",
             "|---|---|---|---|---|---|---|---|"]
    for py in python_results:
        g = lookup[(py["scope"], py["case"])]
        speed = py["median_ms"] / g["median_ms"]
        py_rate, go_rate = py["samples"] / py["median_ms"] / 1000, py["samples"] / g["median_ms"] / 1000
        lines.append(f"| {py['scope']} | {py['case']} | {py['samples']} / {py['fft_size']} | {py['median_ms']:.4f} ({py['p90_ms']:.4f}) | {g['median_ms']:.4f} ({g['p90_ms']:.4f}) | {speed:.3f} | {py_rate:.3f} / {go_rate:.3f} | {g['bytes_per_op']:.0f} / {g['allocations_per_op']:.0f} |")
    lines.extend(["", "Core includes input validation, window construction, FFT plan/setup, FFT, PSD, normalization and result allocation. Welch reuses its plan within each call.",
                  "CSV includes file open/read and decode; E2E includes file decode plus PSD. Compilation, process launch, fixture generation, plots and JSON are excluded.",
                  "Shared CSV fixtures use 17-digit float roundtrip; both core measurements consume decoded identical samples. Fixed seed 20261008.",
                  "CSV runs use a warm filesystem cache; this is not a cold-storage benchmark. Runs are sequential without affinity, process isolation or forced power policy.",
                  "Go allocated B/op and allocs/op are not peak RSS; uniform peak RSS and Python native allocations are NOT MEASURED.",
                  "Go and Python repeat methods use per-trial mean timing; median/p90 summarize trials, not individual-call latency."])
    if reuse_python:
        lines.append("Python timings are retained from the paired baseline; Go was rerun after buffer reuse with identical shared fixtures and iteration settings.")
    (reports / "performance.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--reuse-python", action="store_true", help="rerun Go using previous Python timings and existing shared fixtures")
    args = parser.parse_args()
    run(args.go, args.repeats, args.iterations, args.reuse_python)
