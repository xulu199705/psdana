"""Single-channel reference receiver; synchronization and one scalar only."""

from dataclasses import asdict, dataclass
from typing import Optional

import numpy as np

from .carrier import search_residual_cfo
from .config import QAMConfig
from .constellation import complex_vector, qam_constellation, validate_dc_mode
from .metrics import qam_error_metrics
from .timing import recover_timing, search_timing_phases

ALGORITHM_VERSION = "qam-blind-scalar-1"
JOINT_ALGORITHM_VERSION = "qam-blind-scalar-2"


class QAMRecoveryError(ValueError):
    """Rejected decisions; diagnostics are evidence, not a valid QAMResult."""

    def __init__(self, message, diagnostics):
        super().__init__(message)
        self.diagnostics = {"status":"unreliable", **diagnostics}


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


def _synchronize(samples, config, dc_mode):
    """Internal bounded computation; quality acceptance is a separate check."""
    raw = complex_vector(samples)
    validate_dc_mode(dc_mode)
    # Polarity correction is explicit and confined to QAM; PSD sees original IQ.
    x = raw.real+1j*config.q_sign*raw.imag
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            timing = recover_timing(x, config, dc_mode=dc_mode)
            fit = search_residual_cfo(timing["symbols_raw"], config, dc_mode=dc_mode)
            if dc_mode == "decision_directed_joint":
                initial_phase = timing["timing_phase_up"]
                initial_evm = timing["timing_evm_pct"]
                evaluations = config.cfo_coarse_steps+config.cfo_fine_steps if config.enable_cfo_correction else 0
                up = timing.pop("interpolated_samples")
                if config.enable_cfo_correction:
                    refined = search_timing_phases(up, config, dc_mode=dc_mode, cfo_hz=fit["cfo_hz"])
                    changed = refined["timing_phase_up"] != initial_phase
                    timing.update(refined)
                    if changed:
                        fit = search_residual_cfo(timing["symbols_raw"], config, dc_mode=dc_mode)
                        evaluations *= 2
                timing.update(timing_initial_phase_up=initial_phase, timing_initial_evm_pct=initial_evm,
                              timing_cfo_refinement_enabled=config.enable_cfo_correction,
                              cfo_search_evaluations=evaluations)
    except (FloatingPointError, OverflowError) as exc:
        raise ValueError("QAM receiver exceeds supported float64 range") from exc
    return {**timing, **fit}


def recover_symbols(samples, config: QAMConfig = QAMConfig(), *, dc_mode="legacy_mean") -> dict:
    """Return accepted symbols; reject unreliable fits with structured evidence."""
    recovered = _synchronize(samples, config, dc_mode)
    if recovered["evm_pct"] > config.max_decision_evm_pct or np.unique(recovered["indices"]).size < 8:
        raise QAMRecoveryError("QAM decisions unreliable: EVM/constellation occupancy failed; no equalizer applied",
            dict(evm_pct_rms=recovered["evm_pct"], occupied_decision_points=int(np.unique(recovered["indices"]).size),
                 frequency_error_hz=recovered["cfo_hz"], timing_offset_symbols=recovered["timing_phase_up"]/(config.samples_per_symbol*config.timing_interp),
                 dc_estimation_mode=dc_mode, cfo_search_boundary_hit=recovered["cfo_boundary_hit"]))
    return recovered


def analyze_qam(samples, config: QAMConfig = QAMConfig(), *, dc_mode="legacy_mean") -> QAMResult:
    """Compute decision-directed errors and return deterministic plot samples."""
    recovered = recover_symbols(samples, config, dc_mode=dc_mode)
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
    if dc_mode == "decision_directed_joint":
        if not recovered["joint_fit_converged"]:
            warnings.append("Joint decisions did not stabilize within the iteration limit")
        diagnostics.update(
            algorithm_version=JOINT_ALGORITHM_VERSION, dc_estimation_mode=dc_mode,
            forward_gain=split(recovered["forward_gain"]),
            joint_fit_iterations=recovered["joint_fit_iterations"],
            joint_fit_converged=recovered["joint_fit_converged"],
            dc_reference="symbol_domain_after_CFO_derotation_before_scalar",
            cfo_estimation_uncertainty_hz=None, cfo_estimation_error_hz=None,
            cfo_search_evaluations=recovered["cfo_search_evaluations"],
            timing_initial_offset_symbols=recovered["timing_initial_phase_up"]/period,
            timing_initial_evm_pct=recovered["timing_initial_evm_pct"],
            timing_cfo_refinement_enabled=recovered["timing_cfo_refinement_enabled"],
            timing_search_sweeps=2 if config.enable_cfo_correction else 1,
            timing_fit_mode=dc_mode, cfo_fit_mode=dc_mode,
            status="warning" if warnings else "candidate")
    return QAMResult(config.qam_order, config.sample_rate_hz, config.symbol_rate_hz,
                     config.samples_per_symbol, **metrics,
                     frequency_error_hz=recovered["cfo_hz"], timing_offset_symbols=phase/period,
                     recovered_symbol_count=count, constellation_i=points.real.copy(),
                     constellation_q=points.imag.copy(), ideal_i=ideal.real.copy(), ideal_q=ideal.imag.copy(),
                     diagnostics=diagnostics)
