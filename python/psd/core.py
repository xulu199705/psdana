"""NumPy-only PSD Golden API. All powers retain the input's absolute scale."""

from dataclasses import dataclass
from numbers import Integral, Real
from typing import Union

import numpy as np


@dataclass(frozen=True)
class PSDConfig:
    fs: float = 160e6
    window: str = "hann"
    fft_points: Union[str, int] = "all"
    overlap: float = 0.5
    detrend: str = "none"


@dataclass(frozen=True)
class PSDResult:
    frequency_hz: np.ndarray
    psd_linear: np.ndarray  # input-unit squared / Hz; NOT divided by P_FS
    psd_dbfs_per_hz: np.ndarray
    rbw_power_dbfs: np.ndarray
    fft_size: int
    fs_hz: float
    frequency_resolution_hz: float
    enbw_hz: float
    coherent_gain: float
    window_power_sum: float
    segment_count: int
    window: str
    input_type: str
    reference_power: float
    method: str
    overlap_samples: int
    hop_size: int
    input_sample_count: int
    used_sample_count: int
    discarded_tail_samples: int
    detrend: str

    @property
    def integrated_power(self) -> float:
        """Absolute estimated power, integrating density with df (not ENBW)."""
        return float(np.sum(self.psd_linear) * self.frequency_resolution_hz)


def _validate(config: PSDConfig, sample_count: int) -> int:
    if (isinstance(config.fs, bool) or not isinstance(config.fs, Real)
            or not np.isfinite(config.fs) or config.fs <= 0):
        raise ValueError("fs must be a finite positive number in Hz")
    if config.window not in ("hann", "rectangle"):
        raise ValueError("window must be 'hann' or 'rectangle'")
    if config.detrend not in ("none", "mean"):
        raise ValueError("detrend must be 'none' or 'mean'")
    if (isinstance(config.overlap, bool) or not isinstance(config.overlap, Real)
            or not np.isfinite(config.overlap) or not 0 <= config.overlap < 1):
        raise ValueError("overlap must be finite and in [0, 1)")
    points = config.fft_points
    if isinstance(points, str) and points == "all":
        size = sample_count
    elif isinstance(points, Integral) and not isinstance(points, (bool, np.bool_)) and points > 0:
        size = int(points)
    else:
        raise ValueError("fft_points must be 'all' or a positive integer")
    if size > sample_count:
        raise ValueError("fft_points exceeds input sample count; implicit zero padding is disabled")
    if config.window == "hann" and size == 1:
        raise ValueError("Periodic Hann at N=1 has zero window energy; use rectangle or N>=2")
    return size


def power_to_db(power: np.ndarray, reference_power: float) -> np.ndarray:
    """Zero power maps to -inf; the plotting layer may use a finite floor."""
    power = np.asarray(power, dtype=np.float64)
    if not np.isfinite(reference_power) or reference_power <= 0 or not np.all(np.isfinite(power)) or np.any(power < 0):
        raise ValueError("power must be finite and nonnegative; reference must be finite and positive")
    # Preserve the normal path exactly; use log-domain division only at limits.
    with np.errstate(over="ignore", under="ignore"):
        values = power / reference_power
    output = np.full(values.shape, -np.inf, dtype=np.float64)
    np.log10(values, out=output, where=values > 0)
    exceptional = (power > 0) & ((values == 0) | ~np.isfinite(values))
    output[exceptional] = np.log10(power[exceptional]) - np.log10(reference_power)
    return 10.0 * output


def compute_psd(samples, config: PSDConfig = PSDConfig()) -> PSDResult:
    """Compute the Golden PSD contract, rejecting unrepresentable intermediates.

    Extreme finite inputs may exceed float64 FFT/power arithmetic. Such inputs
    raise ValueError instead of silently returning NaN/+Inf or invalid units.
    """
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            return _compute_psd(samples, config)
    except (FloatingPointError, OverflowError, ZeroDivisionError) as exc:
        raise ValueError("PSD computation exceeds supported float64 range") from exc


def _compute_psd(samples, config: PSDConfig) -> PSDResult:
    """Auto Periodogram (N=M) / Welch (N<M); real one-sided, IQ shifted two-sided.

    overlap_samples=floor(N*overlap); hop=N-overlap_samples. Incomplete trailing
    segments are discarded. Each segment is detrended before applying its window.
    """
    raw = np.asarray(samples)
    if raw.ndim != 1 or raw.size == 0:
        raise ValueError("samples must be a nonempty one-dimensional numeric sequence")
    if raw.dtype.kind not in "fciu":
        raise ValueError("samples must contain real or complex numeric values")
    is_complex = np.iscomplexobj(raw)
    x = np.asarray(raw, dtype=np.complex128 if is_complex else np.float64)
    if not np.all(np.isfinite(x)):
        raise ValueError("samples contain NaN or Inf")
    size = _validate(config, x.size)
    fs = float(config.fs)
    if config.window == "hann":
        window = 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(size) / size)
    else:
        window = np.ones(size, dtype=np.float64)
    window_power_sum = float(np.dot(window, window))
    window_sum = float(np.sum(window))
    enbw = fs * window_power_sum / window_sum**2
    denominator = fs * window_power_sum
    if (not np.isfinite(denominator) or denominator <= 0 or not np.isfinite(enbw)
            or enbw <= 0 or fs / size == 0 or fs / 2 == 0):
        raise ValueError("sample rate/window normalization exceeds supported float64 range")
    gain = window_sum / size
    welch = size < x.size
    overlap_samples = int(np.floor(size * config.overlap)) if welch else 0
    hop = size - overlap_samples
    segment_count = 1 + (x.size - size) // hop
    density = np.zeros(size, dtype=np.float64)
    for start in range(0, x.size - size + 1, hop):
        segment = x[start:start + size]
        if config.detrend == "mean":
            segment = segment - np.mean(segment)
        spectrum = np.fft.fft(segment * window)
        density += np.abs(spectrum)**2 / denominator
    density /= segment_count  # average linear PSD, then convert to dB
    # NumPy fftfreq computes 1/(N*d). Its N/fs intermediate can overflow
    # for a tiny finite fs even when the final df and signed axis are valid.
    direct_axis = not np.isfinite(size * (1.0 / fs))
    if is_complex:
        density = np.fft.fftshift(density)
        frequency = ((np.arange(size) - size // 2) * (fs / size) if direct_axis
                     else np.fft.fftshift(np.fft.fftfreq(size, d=1.0 / fs)))
        reference_power = 1.0
    else:
        density = density[:size // 2 + 1].copy()
        if size % 2 == 0:
            density[1:-1] *= 2.0
        else:
            density[1:] *= 2.0
        frequency = (np.arange(size // 2 + 1) * (fs / size) if direct_axis
                     else np.fft.rfftfreq(size, d=1.0 / fs))
        reference_power = 0.5
    used_count = (segment_count - 1) * hop + size
    if not np.isfinite(np.sum(density) * (fs / size)):
        raise ValueError("integrated power exceeds supported float64 range")
    return PSDResult(
        frequency_hz=frequency, psd_linear=density,
        psd_dbfs_per_hz=power_to_db(density, reference_power),
        rbw_power_dbfs=power_to_db(density * enbw, reference_power),
        fft_size=size, fs_hz=fs, frequency_resolution_hz=fs / size,
        enbw_hz=enbw, coherent_gain=gain, window_power_sum=window_power_sum,
        segment_count=segment_count, window=config.window,
        input_type="complex" if is_complex else "real", reference_power=reference_power,
        method="welch" if welch else "periodogram", overlap_samples=overlap_samples,
        hop_size=hop, input_sample_count=int(x.size), used_sample_count=used_count,
        discarded_tail_samples=int(x.size - used_count), detrend=config.detrend,
    )
