"""Fractional phase search reuses one matched filter and one polyphase interpolator."""

import numpy as np
from scipy import signal

from .constellation import scalar_qam_fit, validate_dc_mode
from .rrc import rrc_taps


def recover_timing(samples, config, *, dc_mode="legacy_mean"):
    validate_dc_mode(dc_mode)
    sps = config.samples_per_symbol
    taps = rrc_taps(config.rrc_beta, config.rrc_span_symbols, sps)
    matched = signal.fftconvolve(samples, taps, mode="same")
    up = signal.resample_poly(matched, config.timing_interp, 1,
                              window=("kaiser",config.timing_kaiser_beta), padtype="constant")
    best = search_timing_phases(up, config, dc_mode=dc_mode)
    best.update(rrc_tap_count=len(taps), rrc_group_delay_samples=(len(taps)-1)//2)
    if dc_mode != "legacy_mean":
        best["interpolated_samples"] = up
    return best


def search_timing_phases(up, config, *, dc_mode="legacy_mean", cfo_hz=None):
    """Score a prepared interpolation array; optional known CFO for refinement."""
    validate_dc_mode(dc_mode)
    sps = config.samples_per_symbol
    period = sps*config.timing_interp
    trim = config.rrc_span_symbols//2+config.extra_edge_trim_symbols
    if len(up) < (2*trim+config.min_analysis_symbols+1)*period:
        raise ValueError("capture too short after matched-filter edge trimming")
    curve = np.empty(period)
    best = None
    for phase in range(period):
        syms = up[trim*period+phase:len(up)-trim*period:period]
        limit_start = max(0,(len(syms)-config.max_analysis_symbols)//2)
        syms = syms[limit_start:limit_start+config.max_analysis_symbols]
        scored = syms if cfo_hz is None else syms*np.exp(-2j*np.pi*cfo_hz*np.arange(len(syms))/config.symbol_rate_hz)
        fit = scalar_qam_fit(scored, config.qam_order, config.scalar_fit_iterations, dc_mode=dc_mode)
        curve[phase] = fit["evm_pct"]
        if best is None or curve[phase] < best["timing_evm_pct"]:
            best = {"symbols_raw":syms, "timing_phase_up":phase,
                    "timing_evm_pct":float(curve[phase]),
                    "first_symbol_index":trim+limit_start}
    best.update(timing_curve_evm_pct=curve, trim_symbols=trim)
    return best
