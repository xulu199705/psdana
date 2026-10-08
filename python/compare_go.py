"""Compare complete Python/Go results outside the fixed Golden vector set."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess

import numpy as np

from go_support import ROOT, build_cli
from psd import PSDConfig, compute_psd
from psd.csvio import CSVConfig, read_csv

THRESHOLD = 1e-20


def compare_arrays(name, actual, expected, frequency, mask=None):
    if len(actual) != len(expected):
        raise ValueError(f"{name}: array length mismatch")
    actual = np.asarray([-np.inf if v is None else v for v in actual], dtype=float)
    expected = np.asarray(expected, dtype=float)
    selected = np.ones(len(expected), dtype=bool) if mask is None else mask
    indices = np.flatnonzero(selected)
    if name == "frequency_hz":
        rtol, atol = 1e-12, 1e-7
    elif name == "psd_linear":
        rtol, atol = 2e-11, 1e-20
    else:
        rtol, atol = 0.0, 1e-7
    errors = np.abs(actual[indices] - expected[indices])
    allowed = atol + rtol * np.abs(expected[indices])
    nonzero = expected[indices] != 0
    relative = errors[nonzero] / np.abs(expected[indices][nonzero])
    peak = int(np.argmax(errors)) if len(errors) else None
    k = int(indices[peak]) if peak is not None else None
    passed = bool(np.all(np.isfinite(errors)) and np.all(errors <= allowed))
    return {"field": name, "passed": passed, "rtol": rtol, "atol": atol,
            "max_absolute_error": float(np.max(errors)) if len(errors) else 0.0,
            "max_relative_error_nonzero_expected": float(np.max(relative)) if len(relative) else 0.0,
            "bin": k, "frequency_hz": float(frequency[k]) if k is not None else None,
            "actual": float(actual[k]) if k is not None else None,
            "expected": float(expected[k]) if k is not None else None}


def compare_result(actual, result):
    expected = asdict(result)
    expected["integrated_power"] = result.integrated_power
    if set(actual) != set(expected):
        raise ValueError(f"PSDResult field mismatch: {set(actual) ^ set(expected)}")
    fields = []
    significant = result.psd_linear > THRESHOLD
    for name, value in expected.items():
        if isinstance(value, np.ndarray):
            fields.append(compare_arrays(name, actual[name], value, result.frequency_hz,
                                         significant if name in ("psd_dbfs_per_hz", "rbw_power_dbfs") else None))
        elif isinstance(value, (str, int)):
            fields.append({"field": name, "passed": actual[name] == value,
                           "actual": actual[name], "expected": value})
        else:
            atol = 1e-15 if name == "integrated_power" else 1e-12
            delta = abs(actual[name] - value)
            fields.append({"field": name, "passed": delta <= atol + 2e-12 * abs(value),
                           "max_absolute_error": delta, "rtol": 2e-12, "atol": atol,
                           "actual": actual[name], "expected": value})
    if np.all(result.psd_linear == 0):
        exact = all(p == 0 for p in actual["psd_linear"]) and all(v is None for v in actual["psd_dbfs_per_hz"] + actual["rbw_power_dbfs"])
        fields.append({"field": "true_zero_contract", "passed": exact})
    return fields


def run(go=None, output=None):
    binary = build_cli(go)
    scratch = ROOT / ".cache" / "compare"
    scratch.mkdir(parents=True, exist_ok=True)
    fs = 160e6
    rng = np.random.default_rng(20261008)
    cases = []
    original = ROOT / "data" / "sine_+40MHz_160MSPS.csv"
    original_samples = read_csv(original, CSVConfig(sample_format="hex_q15")).samples
    cases.append(("original8192", original_samples, PSDConfig(), original, "hex_q15"))
    n = np.arange(1024)
    tone = np.exp(2j * np.pi * n / 4)
    cases.extend((f"tone1024_{window}", tone, PSDConfig(window=window), None, "float") for window in ("hann", "rectangle"))
    n = np.arange(4096)
    multi = sum(a * np.exp(2j * np.pi * k * n / 4096) for a, k in ((0.7, 731), (0.2, -203), (0.1, 13)))
    cases.append(("multitone4096", multi, PSDConfig(), None, "float"))
    noise = (rng.standard_normal(65536) + 1j * rng.standard_normal(65536)) * 0.1
    for points, overlap, detrend, window in (("all", .5, "none", "hann"), (1024, .5, "none", "hann"),
                                            (333, .25, "mean", "rectangle"), (999, .75, "mean", "hann")):
        cases.append((f"noise65536_{points}_{overlap}_{detrend}", noise, PSDConfig(fs, window, points, overlap, detrend), None, "float"))
    for size in (1, 2, 3, 255, 256, 333, 999):
        x = rng.standard_normal(size) + 1j * rng.standard_normal(size)
        cases.append((f"complex_edge{size}", x, PSDConfig(125e6, "rectangle" if size == 1 else "hann"), None, "float"))
    real = rng.standard_normal(8193) * 0.2 + 0.1
    for points, overlap, window in (("all", .5, "hann"), (255, .5, "hann"), (256, .125, "rectangle"), (333, .8, "hann")):
        cases.append((f"real8193_{points}", real, PSDConfig(96e6, window, points, overlap, "mean"), None, "float"))
    cases.append(("zero_complex31", np.zeros(31, dtype=complex), PSDConfig(), None, "float"))
    reports = []
    for name, samples, config, source, sample_format in cases:
        if source is None:
            source = scratch / f"{name}.csv"
            iq = np.iscomplexobj(samples)
            values = np.column_stack((samples.real, samples.imag)) if iq else samples[:, None]
            np.savetxt(source, values, delimiter=",", header="i,q" if iq else "sample", comments="", fmt="%.17g")
        # Use decoded shared CSV samples for both implementations, including bitwise roundtrip.
        shared = read_csv(source, CSVConfig(sample_format=sample_format)).samples
        if not np.array_equal(samples, shared):
            raise ValueError(f"CSV roundtrip changed shared samples: {name}")
        result = compute_psd(shared, config)
        args = [str(binary), "--input", str(source), "--sample-format", sample_format, "--fs", str(config.fs),
                "--window", config.window, "--fft-points", str(config.fft_points), "--overlap", str(config.overlap),
                "--detrend", config.detrend, "--json"]
        completed = subprocess.run(args, check=True, capture_output=True, text=True)
        actual = json.loads(completed.stdout)
        fields = compare_result(actual, result)
        passed = all(f["passed"] for f in fields)
        reports.append({"id": name, "passed": passed, "config": asdict(config), "fields": fields})
        linear = next(f for f in fields if f["field"] == "psd_linear")
        db = next(f for f in fields if f["field"] == "rbw_power_dbfs")
        print(f"{'PASS' if passed else 'FAIL'} {name}: PSD max_abs={linear['max_absolute_error']:.6g}; significant dB max_abs={db['max_absolute_error']:.6g}")
        if not passed:
            print(json.dumps([f for f in fields if not f["passed"]], indent=2))
    report = {"case_count": len(reports), "passed": sum(r["passed"] for r in reports),
              "db_significance_psd_threshold": THRESHOLD, "cases": reports}
    destination = Path(output) if output else ROOT / "go" / "reports" / "direct_comparison.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run(args.go, args.output)
    raise SystemExit(0 if report["passed"] == report["case_count"] else 1)
