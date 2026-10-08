"""Single-channel reference receiver; synchronization and one scalar only."""

from dataclasses import asdict, dataclass
from typing import Optional

import numpy as np

from .carrier import search_residual_cfo
from .config import QAMConfig
from .constellation import complex_vector, qam_constellation
from .metrics import qam_error_metrics
from .timing import recover_timing

ALGORITHM_VERSION = "qam-blind-scalar-1"


@dataclass(frozen=True)
class QAMResult:
    qam_order: int
    sample_rate_hz: float
    symbol_rate_hz: float
    samples_per_symbol: int
    evm_pct_rms: float
    amplitude_error_pct_rms: float
    phase_error_pct_rms: float
    phase_error_deg_rms: float
    frequency_error_hz: Optional[float]
    timing_offset_symbols: float
    recovered_symbol_count: int
    constellation_i: np.ndarray
    constellation_q: np.ndarray
    ideal_i: np.ndarray
    ideal_q: np.ndarray
    diagnostics: dict

    def to_dict(self):
        values = asdict(self)
        for name in ("constellation_i", "constellation_q", "ideal_i", "ideal_q"):
            values[name] = values[name].tolist()
        # Receiver rejects nonfinite results. None denotes disabled/unestimated CFO.
        import json
        json.dumps(values, allow_nan=False)
        return values


def recover_symbols(samples, config: QAMConfig = QAMConfig()) -> dict:
    """Return full valid symbols/decisions and diagnostics, before plot thinning."""
    raw = complex_vector(samples)
    # Polarity correction is explicit and confined to QAM; PSD sees original IQ.
    x = raw.real+1j*config.q_sign*raw.imag
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            timing = recover_timing(x, config)
            fit = search_residual_cfo(timing["symbols_raw"], config)
    except (FloatingPointError, OverflowError) as exc:
        raise ValueError("QAM receiver exceeds supported float64 range") from exc
    if fit["evm_pct"] > config.max_decision_evm_pct or np.unique(fit["indices"]).size < 8:
        raise ValueError("QAM decisions unreliable: EVM/constellation occupancy failed; no equalizer applied")
    return {**timing, **fit}


def analyze_qam(samples, config: QAMConfig = QAMConfig()) -> QAMResult:
    """Compute decision-directed errors and return deterministic plot samples."""
    recovered = recover_symbols(samples, config)
    metrics = qam_error_metrics(recovered["eq"], recovered["decisions"])
    count = len(recovered["eq"])
    selected = np.linspace(0,count-1,min(count,config.constellation_points),dtype=int)
    points = recovered["eq"][selected]
    ideal = qam_constellation(config.qam_order)
    phase = recovered["timing_phase_up"]
    period = config.samples_per_symbol*config.timing_interp
    warnings = ["CFO estimate is near search boundary; out-of-range recovery is not guaranteed"] if recovered["cfo_boundary_hit"] else []
    def split(value):
        return {"real":float(np.real(value)), "imag":float(np.imag(value))}
    diagnostics = {
        "algorithm_version":ALGORITHM_VERSION, "config":asdict(config),
        "metric_reference":"decision_directed", "phase_ambiguity_degrees":90,
        "status":"warning" if warnings else "candidate", "warnings":warnings,
        "complex_gain":split(recovered["complex_gain"]), "dc_offset":split(recovered["dc"]),
        "coarse_phase_deg":recovered["coarse_phase_deg"],
        "timing_offset_samples":phase/config.timing_interp,
        "timing_evm_pct":recovered["timing_evm_pct"], "timing_candidates":period,
        "timing_curve_evm_pct":recovered["timing_curve_evm_pct"].tolist(),
        "trim_symbols_per_edge":recovered["trim_symbols"],
        "analysis_first_symbol_index":recovered["first_symbol_index"],
        "valid_symbol_count":count, "input_sample_count":len(samples),
        "rrc_tap_count":recovered["rrc_tap_count"],
        "rrc_group_delay_samples":recovered["rrc_group_delay_samples"],
        "cfo_correction_enabled":config.enable_cfo_correction,
        "cfo_search_boundary_hit":recovered["cfo_boundary_hit"],
        "cfo_search_range_hz":[-config.max_residual_cfo_hz,config.max_residual_cfo_hz],
        "cfo_search_symbol_count":recovered["cfo_search_symbols"],
        "cfo_grid_resolution_hz":recovered["cfo_grid_resolution_hz"],
        "observation_seconds":(count-1)/config.symbol_rate_hz,
        "occupied_decision_points":int(np.unique(recovered["indices"]).size),
        "constellation_selection":"uniform_indices_inclusive_endpoints",
    }
    return QAMResult(config.qam_order, config.sample_rate_hz, config.symbol_rate_hz,
                     config.samples_per_symbol, **metrics,
                     frequency_error_hz=recovered["cfo_hz"], timing_offset_symbols=phase/period,
                     recovered_symbol_count=count, constellation_i=points.real.copy(),
                     constellation_q=points.imag.copy(), ideal_i=ideal.real.copy(), ideal_q=ideal.imag.copy(),
                     diagnostics=diagnostics)
