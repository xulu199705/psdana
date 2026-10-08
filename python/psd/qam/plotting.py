"""Constellation display from an already computed QAMResult."""

import matplotlib.pyplot as plt
import numpy as np


def plot_constellation(result, show=True):
    """Return figure/axes; show interactively by default, never save images."""
    figure, axes = plt.subplots(figsize=(7,7))
    axes.set_facecolor("#20252B")
    axes.scatter(result.constellation_i, result.constellation_q, s=9,
                 color="#FFE45C", marker="o", alpha=0.4, label="Recovered symbols")
    axes.scatter(result.ideal_i, result.ideal_q, s=75, edgecolors="#FF3B30",
                 facecolors="none", marker="o", linewidths=1.3, label="Ideal constellation")
    limit = 1.18*max(np.max(abs(result.ideal_i)), np.max(abs(result.ideal_q)))
    axes.set(xlim=(-limit,limit), ylim=(-limit,limit), xlabel="I", ylabel="Q")
    axes.set_aspect("equal", adjustable="box")
    axes.grid(alpha=0.25)
    cfo = "not estimated" if result.frequency_error_hz is None else f"{result.frequency_error_hz:.3f} Hz"
    axes.set_title(f"{result.qam_order}QAM — EVM {result.evm_pct_rms:.3f}% RMS\n"
                   f"CFO {cfo}; {result.recovered_symbol_count} valid symbols")
    axes.legend(loc="upper right")
    figure.tight_layout()
    if show:
        plt.show()
    return figure, axes
