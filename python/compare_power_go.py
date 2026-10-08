"""V2.0.1 band power comparison: shared PSD and independently computed PSD."""

import argparse
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from go_support import ROOT, build_cli
from psd import PSDConfig, PSDResult, analyze_band_power, compute_psd
from psd.csvio import CSVConfig, read_csv

LINEAR_ATOL, LINEAR_RTOL, DB_ATOL, SIGNIFICANCE = 1e-18, 2e-11, 1e-7, 1e-18


def from_json(raw):
    values = {
        k: v for k, v in raw.items() if k not in ("power_metrics", "integrated_power")
    }
    for key in ("frequency_hz", "psd_linear", "psd_dbfs_per_hz", "rbw_power_dbfs"):
        values[key] = np.array([-math.inf if x is None else x for x in values[key]])
    return PSDResult(**values)


def differences(actual, expected, same_psd):
    expected = expected.to_dict()
    stats = []
    for key, value in expected.items():
        got = actual[key]
        error, skipped = 0.0, False
        if key in ("peak_power_dbfs", "average_power_dbfs"):
            significance = (
                expected["band_power_linear"]
                if key == "average_power_dbfs"
                else (10 ** (value / 10) if value is not None else 0)
            )
            skipped = significance <= SIGNIFICANCE and not same_psd
            if skipped:
                passed = True
            elif value is None or got is None:
                passed = value is None and got is None
            else:
                error = abs(got - value)
                passed = error <= DB_ATOL
        elif key == "band_power_linear":
            error = abs(got - value)
            passed = error <= LINEAR_ATOL + LINEAR_RTOL * abs(value)
        elif key == "peak_frequency_hz":
            peak_db = expected["peak_power_dbfs"]
            skipped = (
                not same_psd
                and not expected["is_point"]
                and (peak_db is None or 10 ** (peak_db / 10) <= SIGNIFICANCE)
            )
            if skipped:
                passed = True
            elif value is None or got is None:
                passed = value is None and got is None
            else:
                error = abs(got - value)
                passed = error <= 1e-7 + 1e-12 * abs(value)
        else:
            passed = got == value
        stats.append(
            {
                "field": key,
                "passed": bool(passed),
                "max_absolute_error": error,
                "actual": got,
                "expected": value,
                "deep_floor_skipped": skipped,
            }
        )
    return stats


def run(go=None, output=None):
    binary = build_cli(go)
    scratch = ROOT / ".cache" / "power-compare"
    scratch.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20261008)
    cases = []
    original = ROOT / "data/sine_+40MHz_160MSPS.csv"
    samples = read_csv(original, CSVConfig(sample_format="hex_q15")).samples
    cases.append(("original", samples, PSDConfig(), original, "hex_q15"))
    for window in ("hann", "rectangle"):
        n = np.arange(1024)
        for sign in (1, -1):
            cases.append(
                (
                    f"tone_{sign}_{window}",
                    np.exp(sign * 2j * np.pi * n / 4),
                    PSDConfig(window=window),
                    None,
                    "float",
                )
            )
        cases.append(
            (
                f"multitone_{window}",
                0.8 * np.exp(2j * np.pi * n / 4) + 0.3 * np.exp(-2j * np.pi * n / 8),
                PSDConfig(window=window),
                None,
                "float",
            )
        )
        cases.append(
            (
                f"welch_{window}",
                np.exp(2j * np.pi * n / 4),
                PSDConfig(window=window, fft_points=255),
                None,
                "float",
            )
        )
        for size in (255, 256, 333):
            real = np.cos(2 * np.pi * 20 * np.arange(size) / size)
            cases.append(
                (
                    f"real{size}_{window}",
                    real,
                    PSDConfig(fs=float(size), window=window),
                    None,
                    "float",
                )
            )
    for size in (1, 2, 3, 999):
        for real in (True, False):
            values = rng.standard_normal(size)
            if not real:
                values = values + 1j * rng.standard_normal(size)
            cases.append(
                (
                    f"edge{size}_{real}",
                    values,
                    PSDConfig(fs=2 * float(size), window="rectangle"),
                    None,
                    "float",
                )
            )
    for name, values in (
        ("zero_real", np.zeros(31)),
        ("zero_complex", np.zeros(32, complex)),
        ("real_dc", np.ones(32)),
        ("real_nyquist", (-1.0) ** np.arange(32)),
    ):
        cases.append(
            (name, values, PSDConfig(fs=32, window="rectangle"), None, "float")
        )
    for real in (True, False):
        values = np.zeros(4) if real else np.zeros(4, complex)
        cases.append(
            (
                f"tiny_fs_zero_{real}",
                values,
                PSDConfig(fs=1e-310, window="rectangle"),
                None,
                "float",
            )
        )
    reports = []
    for name, samples, config, source, fmt in cases:
        if source is None:
            source = scratch / f"{name}.csv"
            values = (
                np.column_stack((samples.real, samples.imag))
                if np.iscomplexobj(samples)
                else samples[:, None]
            )
            np.savetxt(
                source,
                values,
                delimiter=",",
                header="i,q" if np.iscomplexobj(samples) else "sample",
                comments="",
                fmt="%.17g",
            )
        shared = read_csv(source, CSVConfig(sample_format=fmt)).samples
        reference = compute_psd(shared, config)
        args = [
            str(binary),
            "--input",
            str(source),
            "--sample-format",
            fmt,
            "--fs",
            str(config.fs),
            "--window",
            config.window,
            "--fft-points",
            str(config.fft_points),
            "--json",
        ]
        half, df = config.fs / 2, reference.frequency_resolution_hz
        ranges = [
            (-half, half),
            (-half, -half),
            (half, half),
            (0, 0),
            (-df / 2, -df / 2),
            (-half, -half + 0.375 * df),
            (half - 0.375 * df, half),
            (0.125 * df, 0.375 * df),
            (-0.137 * config.fs, 0.319 * config.fs),
            (config.fs / 4, config.fs / 4),
        ]
        if config.fs == 160e6:
            ranges.extend([(40e6 - 1.5 * df, 40e6 + 1.5 * df), (-10e6, 10e6)])
        for left, right in ranges:
            done = subprocess.run(
                args + ["--freq-left", str(left), "--freq-right", str(right)],
                capture_output=True,
                text=True,
                check=True,
            )
            raw = json.loads(done.stdout)
            actual = raw["power_metrics"]
            # Isolate the integration algorithm by passing Go's exact PSD arrays
            # to Python; also compare against a separately computed Python PSD.
            same = analyze_band_power(from_json(raw), left, right)
            independent = analyze_band_power(reference, left, right)
            fields = differences(actual, same, True)
            independent_fields = differences(actual, independent, False)
            passed = all(f["passed"] for f in fields + independent_fields)
            reports.append(
                {
                    "id": name,
                    "range_hz": [left, right],
                    "passed": passed,
                    "shared_psd": fields,
                    "independent_psd": independent_fields,
                }
            )
            if not passed:
                print(json.dumps(reports[-1], indent=2, allow_nan=False))
        print(f"{name}: {len(ranges)} ranges compared")
    invalid = [
        (-81e6, 0),
        (0, 81e6),
        (1, -1),
        (math.nan, 0),
        (0, math.inf),
        (-math.inf, 0),
    ]
    errors = []
    reference = compute_psd(cases[0][1])
    for left, right in invalid:
        try:
            analyze_band_power(reference, left, right)
            python_error = False
        except ValueError:
            python_error = True
        done = subprocess.run(
            [
                str(binary),
                "--json",
                "--freq-left",
                str(left),
                "--freq-right",
                str(right),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        errors.append(
            {
                "range_hz": [str(left), str(right)],
                "passed": python_error
                and done.returncode != 0
                and not done.stdout
                and bool(done.stderr),
            }
        )
    max_linear = max(
        f["max_absolute_error"]
        for r in reports
        for f in r["independent_psd"]
        if f["field"] == "band_power_linear"
    )
    max_db = max(
        f["max_absolute_error"]
        for r in reports
        for f in r["independent_psd"]
        if f["field"] in ("peak_power_dbfs", "average_power_dbfs")
    )
    result = {
        "case_count": len(reports),
        "passed": sum(r["passed"] for r in reports),
        "invalid_cases": errors,
        "max_absolute_linear_error": max_linear,
        "max_significant_db_error": max_db,
        "linear_atol": LINEAR_ATOL,
        "linear_rtol": LINEAR_RTOL,
        "db_atol": DB_ATOL,
        "significance_power": SIGNIFICANCE,
        "cases": reports,
    }
    destination = (
        Path(output) if output else ROOT / "go/reports/v2.0.1_power_comparison.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(
        f"Power comparison: {result['passed']}/{len(reports)}; max linear={max_linear:.6g}; max significant dB={max_db:.6g}"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(args.go, args.output)
    raise SystemExit(
        0
        if result["case_count"] == result["passed"]
        and all(r["passed"] for r in result["invalid_cases"])
        else 1
    )
