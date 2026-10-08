"""Bounded residual CFO search, positive input slope => positive estimate."""

import numpy as np

from .constellation import complex_vector, scalar_qam_fit


def search_residual_cfo(symbols, config):
    symbols = complex_vector(symbols, config.min_analysis_symbols)
    if not config.enable_cfo_correction:
        fit = scalar_qam_fit(symbols, config.qam_order, config.scalar_fit_iterations)
        fit.update(cfo_hz=None, cfo_boundary_hit=False, cfo_search_symbols=0, cfo_grid_resolution_hz=None)
        return fit
    length = min(len(symbols), config.cfo_search_max_symbols)
    start = (len(symbols)-length)//2
    subset = symbols[start:start+length]
    n = np.arange(length)/config.symbol_rate_hz

    def score(frequency):
        corrected = subset*np.exp(-2j*np.pi*frequency*n)
        return scalar_qam_fit(corrected, config.qam_order, config.scalar_fit_iterations)["evm_pct"]

    bound = config.max_residual_cfo_hz
    coarse = np.linspace(-bound, bound, config.cfo_coarse_steps)
    scores = np.array([score(f) for f in coarse])
    best = float(coarse[np.argmin(scores)])
    step = float(coarse[1]-coarse[0])
    fine = np.linspace(max(-bound,best-step), min(bound,best+step), config.cfo_fine_steps)
    fine_scores = np.array([score(f) for f in fine])
    frequency = float(fine[np.argmin(fine_scores)])
    resolution = float(fine[1]-fine[0])
    full_n = np.arange(len(symbols))/config.symbol_rate_hz
    fit = scalar_qam_fit(symbols*np.exp(-2j*np.pi*frequency*full_n), config.qam_order, config.scalar_fit_iterations)
    # One coarse grid interval defines "near boundary". Fine search clipping
    # halves its step near the edge, so a fine-step threshold would miss it.
    fit.update(cfo_hz=frequency, cfo_boundary_hit=abs(frequency) >= bound-step,
               cfo_search_symbols=length, cfo_grid_resolution_hz=resolution)
    return fit
