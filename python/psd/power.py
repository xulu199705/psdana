"""Band/point power from an existing PSD, using periodic, centered bin cells."""

import math
from dataclasses import asdict, dataclass
from numbers import Real
from typing import Optional

import numpy as np

from .core import PSDResult


@dataclass(frozen=True)
class PowerResult:
    freq_left_hz: float
    freq_right_hz: float
    is_point: bool
    peak_frequency_hz: Optional[float]
    peak_power_dbfs: float
    average_power_dbfs: float
    band_power_linear: float  # absolute input-unit squared; RBW power in point mode
    contributing_bins: (
        int  # distinct signed bins with positive overlap; one for a point
    )

    def to_dict(self) -> dict:
        """Standard JSON-ready scalars: -Inf dB and absent peak become null."""
        values = asdict(self)
        for key in ("peak_power_dbfs", "average_power_dbfs"):
            if values[key] == -math.inf:
                values[key] = None
            elif not math.isfinite(values[key]):
                raise ValueError("power result contains nonfinite dB")
        return values


def _positive(value, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{name} must be finite and positive")


def _signed_spectrum(result):
    n, fs, df = result.fft_size, result.fs_hz, result.frequency_resolution_hz
    if isinstance(n, bool) or not isinstance(n, (int, np.integer)) or n < 1:
        raise ValueError("PSDResult fft_size must be a positive integer")
    for value, name in (
        (fs, "fs_hz"),
        (df, "frequency_resolution_hz"),
        (result.enbw_hz, "enbw_hz"),
        (result.reference_power, "reference_power"),
    ):
        _positive(value, name)
    if (
        fs / 2 == 0
        or fs / n == 0
        or abs(df - fs / n) > 16 * np.finfo(float).eps * (fs / n)
    ):
        raise ValueError(
            "PSDResult frequency resolution is inconsistent or unrepresentable"
        )
    if result.input_type not in ("real", "complex"):
        raise ValueError("PSDResult input_type must be real or complex")
    expected_ref = 0.5 if result.input_type == "real" else 1.0
    if result.reference_power != expected_ref:
        raise ValueError(
            "PSDResult Full Scale reference is inconsistent with input_type"
        )
    frequency = np.asarray(result.frequency_hz, dtype=float)
    density = np.asarray(result.psd_linear, dtype=float)
    length = n if result.input_type == "complex" else n // 2 + 1
    if frequency.shape != (length,) or density.shape != (length,):
        raise ValueError("PSDResult frequency/PSD arrays have invalid dimensions")
    if (
        not np.all(np.isfinite(frequency))
        or not np.all(np.isfinite(density))
        or np.any(density < 0)
    ):
        raise ValueError("PSDResult frequency/PSD must be finite and PSD nonnegative")
    expected = (
        (np.arange(n) - n // 2) * df
        if result.input_type == "complex"
        else np.arange(length) * df
    )
    if np.any(np.abs(frequency - expected) > 16 * np.finfo(float).eps * fs):
        raise ValueError("PSDResult frequency axis is inconsistent with FFT size")
    if result.input_type == "complex":
        return frequency, density
    # DC and even Nyquist are unique; every other one-sided bin splits in half.
    bins = np.arange(n) - n // 2
    signed_density = density[np.abs(bins)].copy()
    internal = (bins != 0) & ~((n % 2 == 0) & (bins == -n // 2))
    signed_density[internal] *= 0.5
    signed_frequency = np.sign(bins) * frequency[np.abs(bins)]
    return signed_frequency, signed_density


def _overlap(center, df, fs, left, right):
    half = fs / 2
    lo, hi = center - df / 2, center + df / 2
    width = max(0.0, min(right, hi, half) - max(left, lo, -half))
    if lo < -half:
        width += max(0.0, min(right, half) - max(left, half - (-half - lo)))
    if hi > half:
        width += max(0.0, min(right, -half + (hi - half)) - max(left, -half))
    return width


def _db(power, reference):
    if power == 0:
        return -math.inf
    # Log-domain division also handles a finite power/reference ratio overflow.
    return 10 * (math.log10(power) - math.log10(reference))


def analyze_band_power(
    result: PSDResult, freq_left_hz: float, freq_right_hz: float
) -> PowerResult:
    """Integrate centered PSD cells, or select nearest bin for equal boundaries.

    Band peaks use whole-bin RBW power even for fractional overlap. Real PSD is
    unfolded into an equivalent signed spectrum. Neither input arrays nor FFT
    are modified. Equal-distance/equal-power ties select the lower frequency.
    """
    frequency, density = _signed_spectrum(result)
    half = result.fs_hz / 2
    for value in (freq_left_hz, freq_right_hz):
        if (
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(value)
        ):
            raise ValueError("frequency boundaries must be finite numbers in Hz")
    left, right = float(freq_left_hz), float(freq_right_hz)
    if not -half <= left <= right <= half:
        raise ValueError("frequency boundaries require -fs/2 <= left <= right <= fs/2")
    point = left == right
    if point:
        grid = (
            np.arange(result.fft_size) - result.fft_size // 2
        ) * result.frequency_resolution_hz
        index = (
            len(frequency) - 1 if left == half else int(np.argmin(np.abs(grid - left)))
        )
        selected = [index]
        band = float(density[index]) * result.enbw_hz
    else:
        # Full Nyquist cells have exactly df total width, including wrapped ends.
        widths = [
            result.frequency_resolution_hz
            if left == -half and right == half
            else _overlap(
                (i - result.fft_size // 2) * result.frequency_resolution_hz,
                result.frequency_resolution_hz,
                result.fs_hz,
                left,
                right,
            )
            for i in range(result.fft_size)
        ]
        selected = [i for i, width in enumerate(widths) if width > 0]
        try:
            band = math.fsum(float(density[i]) * widths[i] for i in selected)
        except OverflowError as exc:
            raise ValueError("band power exceeds supported float64 range") from exc
    if not math.isfinite(band):
        raise ValueError("band power exceeds supported float64 range")
    index = max(selected, key=lambda i: density[i]) if selected else None
    peak = float(density[index]) * result.enbw_hz if index is not None else 0.0
    if not math.isfinite(peak):
        raise ValueError("RBW power exceeds supported float64 range")
    peak_frequency = float(frequency[index]) if peak > 0 else None
    return PowerResult(
        left,
        right,
        point,
        peak_frequency,
        _db(peak, result.reference_power),
        _db(band, result.reference_power),
        band,
        len(selected),
    )
