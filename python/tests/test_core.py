import sys
import subprocess
from pathlib import Path

import numpy as np
import pytest
from scipy import signal

from psd import PSDConfig, compute_psd

FS = 160e6


@pytest.mark.parametrize("window,gain,enbw_bins", [("hann", 0.5, 1.5), ("rectangle", 1.0, 1.0)])
@pytest.mark.parametrize("size", [3, 255, 256, 999])
def test_window_metrics(window, gain, enbw_bins, size):
    result = compute_psd(np.zeros(size), PSDConfig(window=window))
    assert result.coherent_gain == pytest.approx(gain, abs=1e-15)
    assert result.enbw_hz == pytest.approx(enbw_bins * FS / size, rel=1e-14)
    expected_energy = size * (3 / 8 if window == "hann" else 1)
    assert result.window_power_sum == pytest.approx(expected_energy, rel=1e-14)


@pytest.mark.parametrize("window", ["hann", "rectangle"])
@pytest.mark.parametrize("kind,frequency,power", [("complex", 40e6, 1.0), ("complex", -40e6, 1.0), ("real", 40e6, 0.5)])
def test_full_scale_frequency_power(window, kind, frequency, power):
    n = np.arange(1024)
    samples = np.exp(2j * np.pi * frequency * n / FS)
    if kind == "real":
        samples = samples.real
    result = compute_psd(samples, PSDConfig(window=window))
    peak = np.argmax(result.psd_linear)
    assert abs(result.frequency_hz[peak] - frequency) <= result.frequency_resolution_hz / 2
    assert result.rbw_power_dbfs[peak] == pytest.approx(0, abs=1e-11)
    assert result.integrated_power == pytest.approx(power, abs=1e-13)
    assert result.reference_power == power
    assert result.input_type == kind
    assert result.psd_dbfs_per_hz[peak] == pytest.approx(-10 * np.log10(result.enbw_hz), abs=1e-11)


@pytest.mark.parametrize("size", [1, 2, 3, 4, 31, 32, 255, 256])
@pytest.mark.parametrize("window", ["hann", "rectangle"])
@pytest.mark.parametrize("complex_input", [False, True])
def test_scipy_periodogram(size, window, complex_input):
    if size == 1 and window == "hann":
        with pytest.raises(ValueError, match="zero window energy"):
            compute_psd([1], PSDConfig(window=window))
        return
    rng = np.random.default_rng(18)
    x = rng.standard_normal(size)
    if complex_input:
        x = x + 1j * rng.standard_normal(size)
    result = compute_psd(x, PSDConfig(window=window))
    w = signal.get_window("hann" if window == "hann" else "boxcar", size, fftbins=True)
    frequency, density = signal.periodogram(x, fs=FS, window=w, detrend=False,
                                            return_onesided=not complex_input, scaling="density")
    if complex_input:
        frequency, density = np.fft.fftshift(frequency), np.fft.fftshift(density)
    np.testing.assert_allclose(result.frequency_hz, frequency, rtol=1e-14, atol=1e-8)
    np.testing.assert_allclose(result.psd_linear, density, rtol=2e-13, atol=1e-22)
    assert result.integrated_power == pytest.approx(float(np.sum(np.abs(x * w)**2) / np.sum(w**2)), rel=2e-14)


@pytest.mark.parametrize("window", ["hann", "rectangle"])
@pytest.mark.parametrize("complex_input", [False, True])
@pytest.mark.parametrize("detrend", ["none", "mean"])
@pytest.mark.parametrize("size,overlap", [(255, 0.5), (256, 0.0), (333, 0.75)])
def test_scipy_welch(window, complex_input, detrend, size, overlap):
    rng = np.random.default_rng(27)
    x = rng.standard_normal(1025) + 2
    if complex_input:
        x = x + 1j * (rng.standard_normal(1025) + 1)
    result = compute_psd(x, PSDConfig(window=window, fft_points=size, overlap=overlap, detrend=detrend))
    w = signal.get_window("hann" if window == "hann" else "boxcar", size, fftbins=True)
    frequency, density = signal.welch(x, fs=FS, window=w, nperseg=size,
                                     noverlap=int(np.floor(size * overlap)),
                                     detrend=False if detrend == "none" else "constant",
                                     return_onesided=not complex_input, scaling="density", average="mean")
    if complex_input:
        frequency, density = np.fft.fftshift(frequency), np.fft.fftshift(density)
    np.testing.assert_allclose(result.frequency_hz, frequency, rtol=1e-14, atol=1e-8)
    np.testing.assert_allclose(result.psd_linear, density, rtol=4e-13, atol=1e-22)
    assert result.method == "welch"
    assert result.segment_count == 1 + (len(x) - size) // (size - int(size * overlap))


def test_welch_averages_linear_power_not_db():
    tone = np.exp(2j * np.pi * 8 * np.arange(32) / 32)
    result = compute_psd(np.concatenate([tone, 0.1 * tone]), PSDConfig(window="rectangle", fft_points=32, overlap=0))
    peak = np.argmax(result.psd_linear)
    assert result.rbw_power_dbfs[peak] == pytest.approx(10 * np.log10((1 + 0.01) / 2), abs=1e-12)
    assert result.integrated_power == pytest.approx(0.505, abs=1e-14)


def test_overlap_floor_tail_and_no_padding():
    result = compute_psd(np.arange(15.0), PSDConfig(fft_points=5))
    assert (result.overlap_samples, result.hop_size, result.segment_count) == (2, 3, 4)
    assert (result.used_sample_count, result.discarded_tail_samples) == (14, 1)
    same = compute_psd(np.arange(15.0), PSDConfig(fft_points=15))
    all_points = compute_psd(np.arange(15.0))
    assert same.method == "periodogram" and same.segment_count == 1
    np.testing.assert_array_equal(same.psd_linear, all_points.psd_linear)
    with pytest.raises(ValueError, match="zero padding"):
        compute_psd(np.ones(15), PSDConfig(fft_points=16))


@pytest.mark.parametrize("size", [31, 32])
def test_real_dc_nyquist_and_last_odd_bin(size):
    dc = compute_psd(np.ones(size), PSDConfig(window="rectangle"))
    assert dc.psd_linear[0] == pytest.approx(size / FS)
    assert dc.integrated_power == pytest.approx(1)
    # Real unit DC has twice the real sine's reference power: +3.0103 dBFS.
    assert dc.rbw_power_dbfs[0] == pytest.approx(10 * np.log10(2))
    n = np.arange(size)
    x = np.cos(2 * np.pi * (size // 2) * n / size)
    result = compute_psd(x, PSDConfig(window="rectangle"))
    assert result.integrated_power == pytest.approx(1 if size % 2 == 0 else 0.5)
    expected = size / FS if size % 2 == 0 else size / (2 * FS)
    assert result.psd_linear[-1] == pytest.approx(expected)


@pytest.mark.parametrize("complex_input", [False, True])
def test_zero_and_mean_removal(complex_input):
    zero = np.zeros(32, dtype=np.complex128 if complex_input else np.float64)
    result = compute_psd(zero)
    assert np.all(result.psd_linear == 0)
    assert np.all(np.isneginf(result.psd_dbfs_per_hz))
    assert np.all(np.isneginf(result.rbw_power_dbfs))
    detrended = compute_psd(zero + (2 + 1j if complex_input else 2), PSDConfig(fft_points=16, detrend="mean"))
    assert np.all(detrended.psd_linear == 0)


def test_no_input_normalization_or_peak_clipping():
    x = 2 * np.exp(2j * np.pi * np.arange(64) / 4)
    result = compute_psd(x)
    assert np.max(result.rbw_power_dbfs) == pytest.approx(10 * np.log10(4))


@pytest.mark.parametrize("changes", [
    {"fs": 0}, {"fs": -1}, {"fs": float("inf")}, {"fs": float("nan")}, {"fs": True},
    {"window": "hamming"}, {"detrend": "linear"}, {"overlap": -0.1}, {"overlap": 1},
    {"overlap": float("nan")}, {"overlap": True}, {"fft_points": 0}, {"fft_points": -1},
    {"fft_points": 2.5}, {"fft_points": True}, {"fft_points": "32"},
])
def test_invalid_config(changes):
    with pytest.raises(ValueError):
        compute_psd(np.ones(32), PSDConfig(**changes))


@pytest.mark.parametrize("samples", [[], [[1, 2]], [float("nan")], [float("inf")],
                                       [complex(0, float("inf"))], ["1", "2"], [True]])
def test_invalid_samples(samples):
    with pytest.raises(ValueError):
        compute_psd(samples)


def test_core_import_does_not_load_matplotlib():
    package = str(Path(__file__).resolve().parents[1])
    code = f"import sys; sys.path.insert(0, {package!r}); import psd; assert 'matplotlib' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
