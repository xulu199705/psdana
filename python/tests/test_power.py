import json
import math
import subprocess
import sys
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest
from psd import PSDConfig, analyze_band_power, compute_psd
from psd.core import power_to_db
from psd.csvio import CSVConfig, read_csv

ROOT = Path(__file__).resolve().parents[2]


def synthetic(n=4, real=False):
    r = compute_psd(
        np.zeros(n) if real else np.zeros(n, complex),
        PSDConfig(fs=2 * n, window="rectangle"),
    )
    return replace(r, psd_linear=np.arange(len(r.psd_linear), dtype=float) + 2)


@pytest.mark.parametrize(
    "left,right",
    [
        (-4.0000001, 0),
        (0, 4.0000001),
        (2, -2),
        (np.nan, 0),
        (0, np.inf),
        (-np.inf, 0),
        (True, 0),
    ],
)
def test_invalid_boundaries(left, right):
    with pytest.raises(ValueError, match="boundaries"):
        analyze_band_power(synthetic(), left, right)


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 255, 256, 333, 999])
@pytest.mark.parametrize("real", [False, True])
def test_full_band_and_points(n, real):
    r = synthetic(n, real)
    original = {
        name: value.copy()
        for name, value in vars(r).items()
        if isinstance(value, np.ndarray)
    }
    p = analyze_band_power(r, -r.fs_hz / 2, r.fs_hz / 2)
    assert p.band_power_linear == pytest.approx(r.integrated_power, rel=2e-14)
    assert p.contributing_bins == n
    for f in (-r.fs_hz / 2, 0, r.fs_hz / 2):
        point = analyze_band_power(r, f, f)
        assert point.is_point and point.contributing_bins == 1
        assert point.peak_power_dbfs == point.average_power_dbfs
    expected_highest = (n - 1 - n // 2) * r.frequency_resolution_hz
    assert (
        analyze_band_power(r, r.fs_hz / 2, r.fs_hz / 2).peak_frequency_hz
        == expected_highest
    )
    for name, expected in original.items():
        np.testing.assert_array_equal(getattr(r, name), expected)


@pytest.mark.parametrize(
    "left,right,power,bins,peak",
    [
        (-4, -3.5, 1, 1, -4),
        (3.5, 4, 1, 1, -4),
        (-4, 4, 28, 4, 2),
        (-2.25, -1.75, 1.5, 1, -2),
        (-3, -1, 6, 1, -2),
        (-3.5, -2.5, 2.5, 2, -2),
        (1.25, 1.75, 2.5, 1, 2),
    ],
)
def test_fractional_cells_and_periodic_nyquist(left, right, power, bins, peak):
    p = analyze_band_power(synthetic(), left, right)
    assert p.band_power_linear == pytest.approx(power, abs=2e-15)
    assert p.contributing_bins == bins
    assert p.peak_frequency_hz == peak


def exact_integral_reference(n, left, right):
    # Independent exact rational integration of repeated frequency cells.
    # This reference uses translated cells, rather than clipping/wrapping logic.
    total = Fraction(0)
    fs = 2 * n
    for i in range(n):
        center = 2 * (i - n // 2)
        for translate in (-fs, 0, fs):
            a, b = Fraction(center - 1 + translate), Fraction(center + 1 + translate)
            width = max(Fraction(0), min(right, b) - max(left, a))
            total += (i + 2) * width
    return float(total)


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 255, 333])
def test_exact_rational_reference(n):
    r = synthetic(n)
    edges = [
        -Fraction(n),
        -Fraction(n) + Fraction(1, 7),
        -Fraction(1, 3),
        Fraction(0),
        Fraction(1, 5),
        Fraction(n) - Fraction(1, 11),
        Fraction(n),
    ]
    edges = sorted({f for f in edges if -n <= f <= n})
    for left, right in zip(edges, edges[1:]):
        # Integrate the exact float64 boundaries supplied to the API, not the
        # nearby ideal rational numbers lost during conversion to float64.
        expected = exact_integral_reference(
            n, Fraction.from_float(float(left)), Fraction.from_float(float(right))
        )
        p = analyze_band_power(r, float(left), float(right))
        assert p.band_power_linear == pytest.approx(expected, rel=3e-14, abs=2e-14)


def test_ties_and_zero_regions():
    r = replace(synthetic(), psd_linear=np.ones(4))
    assert analyze_band_power(r, -4, 4).peak_frequency_hz == -4
    assert analyze_band_power(r, -1, -1).peak_frequency_hz == -2
    r = replace(r, psd_linear=np.array([0.0, 0.0, 1.0, 0.0]))
    p = analyze_band_power(r, -3, -1)
    assert p.peak_frequency_hz is None and p.band_power_linear == 0
    assert p.peak_power_dbfs == p.average_power_dbfs == -math.inf
    assert (
        json.loads(json.dumps(p.to_dict(), allow_nan=False))["peak_power_dbfs"] is None
    )


@pytest.mark.parametrize("window", ["hann", "rectangle"])
@pytest.mark.parametrize("points", ["all", 256])
def test_full_scale_tone_and_hann_main_lobe(window, points):
    r = compute_psd(
        np.exp(2j * np.pi * np.arange(1024) / 4),
        PSDConfig(window=window, fft_points=points),
    )
    f, df = 40e6, r.frequency_resolution_hz
    full = analyze_band_power(r, -80e6, 80e6)
    point = analyze_band_power(r, f, f)
    lobe = analyze_band_power(r, f - 1.5 * df, f + 1.5 * df)
    one = analyze_band_power(r, f - df / 2, f + df / 2)
    assert full.peak_frequency_hz == point.peak_frequency_hz == f
    assert full.average_power_dbfs == pytest.approx(0, abs=1e-11)
    assert (
        point.peak_power_dbfs == point.average_power_dbfs == pytest.approx(0, abs=1e-11)
    )
    assert lobe.band_power_linear == pytest.approx(1, abs=2e-13)
    assert one.band_power_linear == pytest.approx(
        2 / 3 if window == "hann" else 1, abs=2e-13
    )


@pytest.mark.parametrize("window", ["hann", "rectangle"])
def test_two_tones_linear_sum(window):
    n = np.arange(1024)
    x = 0.8 * np.exp(2j * np.pi * n / 4) + 0.3 * np.exp(-2j * np.pi * n / 8)
    r = compute_psd(x, PSDConfig(window=window))
    both = analyze_band_power(r, -25e6, 45e6)
    one = analyze_band_power(r, -21e6, -19e6)
    assert both.peak_frequency_hz == 40e6
    assert both.band_power_linear == pytest.approx(0.64 + 0.09, abs=2e-13)
    assert both.peak_power_dbfs == pytest.approx(20 * math.log10(0.8), abs=1e-11)
    assert one.band_power_linear == pytest.approx(0.09, abs=2e-13)


@pytest.mark.parametrize("n", [255, 256, 333, 999])
@pytest.mark.parametrize("window", ["hann", "rectangle"])
def test_real_mirrors_and_full_power(n, window):
    fs, k = float(n), 20
    x = np.cos(2 * np.pi * k * np.arange(n) / n)
    r = compute_psd(x, PSDConfig(fs=fs, window=window))
    positive = analyze_band_power(r, k - 1.5, k + 1.5)
    negative = analyze_band_power(r, -k - 1.5, -k + 1.5)
    assert positive.band_power_linear == pytest.approx(0.25, abs=2e-14)
    assert positive.band_power_linear == negative.band_power_linear
    assert positive.peak_frequency_hz == k and negative.peak_frequency_hz == -k
    assert positive.peak_power_dbfs == pytest.approx(-10 * math.log10(2), abs=1e-11)
    full = analyze_band_power(r, -fs / 2, fs / 2)
    assert full.band_power_linear == pytest.approx(0.5, abs=2e-14)


@pytest.mark.parametrize("n", [1, 2, 3, 256])
def test_real_dc_and_nyquist(n):
    r = compute_psd(np.ones(n), PSDConfig(fs=n, window="rectangle"))
    assert analyze_band_power(r, -n / 2, n / 2).band_power_linear == pytest.approx(1)
    assert analyze_band_power(r, 0, 0).average_power_dbfs == pytest.approx(
        10 * math.log10(2)
    )
    if n % 2 == 0:
        r = compute_psd((-1.0) ** np.arange(n), PSDConfig(fs=n, window="rectangle"))
        assert analyze_band_power(r, -n / 2, n / 2).band_power_linear == pytest.approx(
            1
        )
        assert analyze_band_power(r, -n / 2, -n / 2).band_power_linear == pytest.approx(
            1
        )
        # Half of the Nyquist cell belongs to each edge of the signed interval.
        assert analyze_band_power(
            r, n / 2 - 0.5, n / 2
        ).band_power_linear == pytest.approx(0.5)


def test_original_capture_analytic_power():
    x = read_csv(
        ROOT / "data/sine_+40MHz_160MSPS.csv", CSVConfig(sample_format="hex_q15")
    ).samples
    r = compute_psd(x)
    expected = (814**2 + 11481**2) / 32768**2
    for left, right in ((40e6, 40e6), (39e6, 41e6), (-80e6, 80e6)):
        p = analyze_band_power(r, left, right)
        assert p.band_power_linear == pytest.approx(expected, abs=2e-15)
        assert p.peak_frequency_hz == 40e6
    assert analyze_band_power(r, -10e6, 10e6).band_power_linear < 1e-28


@pytest.mark.parametrize("real", [True, False])
def test_zero_all_modes(real):
    r = compute_psd(np.zeros(9) if real else np.zeros(9, complex))
    for left, right in ((-80e6, 80e6), (0, 0), (80e6, 80e6)):
        p = analyze_band_power(r, left, right)
        assert p.peak_frequency_hz is None
        assert p.peak_power_dbfs == p.average_power_dbfs == -math.inf
        assert (
            json.loads(json.dumps(p.to_dict(), allow_nan=False))["peak_frequency_hz"]
            is None
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("fs_hz", 0),
        ("enbw_hz", math.inf),
        ("fft_size", 0),
        ("frequency_resolution_hz", 3),
        ("reference_power", 0),
        ("input_type", "iq"),
        ("psd_linear", np.array([])),
        ("psd_linear", np.array([0.0, -1.0, 0.0, 0.0])),
        ("psd_linear", np.array([0.0, math.nan, 0.0, 0.0])),
        ("frequency_hz", np.array([0.0, 1.0, 2.0, 3.0])),
    ],
)
def test_malformed_results(field, value):
    with pytest.raises(ValueError, match="PSDResult|must be finite"):
        analyze_band_power(replace(synthetic(), **{field: value}), 0, 0)


@pytest.mark.parametrize("real", [True, False])
@pytest.mark.parametrize("case", ["samples", "mean", "fs_high", "fs_low"])
def test_numeric_range_rejected(real, case):
    x = np.ones(4) if real else np.ones(4, complex)
    config = PSDConfig(window="rectangle")
    if case in ("samples", "mean"):
        x *= np.finfo(float).max
        config = replace(config, detrend="mean" if case == "mean" else "none")
    else:
        config = replace(
            config,
            fs=np.finfo(float).max if case == "fs_high" else np.nextafter(0.0, 1.0),
        )
    with pytest.raises(ValueError, match="float64 range"):
        compute_psd(x, config)


def test_large_finite_power_and_small_frequency_scale():
    r = compute_psd(np.full(4, 1e100, dtype=complex), PSDConfig(window="rectangle"))
    assert r.integrated_power == pytest.approx(1e200, rel=2e-14)
    assert analyze_band_power(r, 0, 0).average_power_dbfs == pytest.approx(2000)
    assert np.isfinite(power_to_db(np.array([np.finfo(float).max]), 0.5)).all()
    r = compute_psd(np.ones(4, complex), PSDConfig(fs=1e-9, window="rectangle"))
    with pytest.raises(ValueError):
        analyze_band_power(r, 0, np.nextafter(r.fs_hz / 2, math.inf))
    assert analyze_band_power(
        r, -r.fs_hz / 2, r.fs_hz / 2
    ).band_power_linear == pytest.approx(1)


@pytest.mark.parametrize("fs", [1e-308, 1e-310])
@pytest.mark.parametrize("real", [True, False])
def test_tiny_fs_axis_without_reciprocal_overflow(fs, real):
    r = compute_psd(
        np.zeros(4) if real else np.zeros(4, complex),
        PSDConfig(fs=fs, window="rectangle"),
    )
    expected = np.arange(3) * (fs / 4) if real else np.array([-2, -1, 0, 1]) * (fs / 4)
    np.testing.assert_array_equal(r.frequency_hz, expected)
    assert analyze_band_power(r, -fs / 2, fs / 2).band_power_linear == 0


def test_python_cli_pair_and_zero():
    base = [sys.executable, str(ROOT / "python/demo.py"), "--no-show"]
    bad = subprocess.run(
        base + ["--freq-left", "0"], capture_output=True, text=True, check=False
    )
    assert bad.returncode != 0 and "provided together" in bad.stderr
    good = subprocess.run(
        base
        + [
            "--input",
            "data/generated/T07_zero_iq.csv",
            "--freq-left",
            "0",
            "--freq-right",
            "0",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert good.returncode == 0, good.stderr
    assert "Peak: N/A" in good.stdout and "Band Peak Frequency: N/A" in good.stdout
