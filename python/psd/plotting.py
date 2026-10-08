"""Independent Matplotlib presentation; never reads CSV or computes FFT."""

import numpy as np
import matplotlib.pyplot as plt

from .core import PSDResult


def plot_psd(result: PSDResult, display: str = "dbfs", freq_unit: str = "MHz", show: bool = True):
    """Return (figure, axes). Zero-power bins use a presentation-only -300 dB floor."""
    if display not in ("dbfs", "dbfs_per_hz"):
        raise ValueError("display must be dbfs or dbfs_per_hz")
    scales = {"Hz": 1.0, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
    if freq_unit not in scales:
        raise ValueError("freq_unit must be Hz, kHz, MHz or GHz")
    values = result.rbw_power_dbfs if display == "dbfs" else result.psd_dbfs_per_hz
    plotted = np.maximum(values, -300.0)
    figure, axes = plt.subplots(figsize=(10, 5))
    axes.plot(result.frequency_hz / scales[freq_unit], plotted, linewidth=1.0)
    axes.set_xlabel(f"Frequency ({freq_unit})")
    axes.set_ylabel("RBW-calibrated power (dBFS)" if display == "dbfs" else "PSD density (dBFS/Hz)")
    axes.set_title(f"{result.method.title()} | FFT {result.fft_size} | {result.window} | "
                   f"ENBW {result.enbw_hz:.6g} Hz | {result.segment_count} segment(s)")
    axes.grid(True, alpha=0.3)
    figure.tight_layout()
    if show:
        plt.show()
    return figure, axes
