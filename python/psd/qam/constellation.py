"""Square QAM with I-major/Q-minor indices and only scalar compensation."""

import numpy as np

from .config import positive_int
from ._slicer import nearest_level_indices


def qam_constellation(order: int = 64) -> np.ndarray:
    """Return unit-average-power points ordered by I, then Q, ascending."""
    positive_int(order, "order")
    if order not in (16, 64, 256):
        raise ValueError("order must be 16, 64 or 256")
    root = int(np.sqrt(order))
    levels = np.arange(-(root-1), root, 2, dtype=float)/np.sqrt(2*(order-1)/3)
    return np.repeat(levels, root)+1j*np.tile(levels, root)


def complex_vector(values, min_count=1):
    raw = np.asarray(values)
    if raw.ndim != 1 or raw.size < min_count or raw.dtype.kind != "c":
        raise ValueError(f"IQ must be a one-dimensional complex sequence with >= {min_count} samples")
    out = np.asarray(raw, dtype=np.complex128)
    if not np.all(np.isfinite(out)):
        raise ValueError("IQ contains NaN/Inf")
    return out


def qam_slicer(symbols, order=64):
    """Return nearest points and I-major indices; ties select lower levels."""
    z = complex_vector(symbols)
    points = qam_constellation(order)
    root = int(np.sqrt(order))
    levels = points[::root].real
    ii = nearest_level_indices(z.real, levels)
    qq = nearest_level_indices(z.imag, levels)
    indices = ii*root+qq
    return points[indices], indices


slicer = qam_slicer


DC_MODES = ("legacy_mean", "decision_directed_joint")


def validate_dc_mode(dc_mode):
    if dc_mode not in DC_MODES:
        raise ValueError("dc_mode must be legacy_mean or decision_directed_joint")


def _joint_fit(symbols, order, iterations):
    """Fit z=a*d+c to fixed input z; no TX reference or multi-tap compensation."""
    z = complex_vector(symbols, 32)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            initial = scalar_qam_fit(z, order, iterations)
    except FloatingPointError as exc:
        raise ValueError("joint initialization exceeds supported numeric range") from exc
    decisions = initial["decisions"]
    z_mean = np.mean(z)
    centered_z = z-z_mean
    converged = False
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        try:
            for used in range(1, iterations+1):
                d_mean = np.mean(decisions)
                centered_d = decisions-d_mean
                energy = float(np.sum(abs(centered_d)**2))
                if not np.isfinite(energy) or energy <= 0:
                    raise ValueError("joint fit requires nonzero centered decision energy")
                forward_gain = np.vdot(centered_d, centered_z)/energy
                if not np.isfinite(forward_gain) or abs(forward_gain) == 0:
                    raise ValueError("joint fit requires finite nonzero gain")
                dc = z_mean-forward_gain*d_mean
                y = (z-dc)/forward_gain
                updated, indices = qam_slicer(y, order)
                converged = bool(np.array_equal(updated, decisions))
                decisions = updated
                if converged:
                    break
            gain = 1/forward_gain
            evm = float(100*np.sqrt(np.sum(abs(y-decisions)**2)/np.sum(abs(decisions)**2)))
        except FloatingPointError as exc:
            raise ValueError("joint fit exceeds supported numeric range") from exc
    if not np.isfinite(evm) or not np.isfinite(gain) or not np.isfinite(dc):
        raise ValueError("joint fit is nonfinite")
    return dict(eq=y, decisions=decisions, indices=indices, evm_pct=evm, dc=dc,
                complex_gain=gain, coarse_phase_deg=initial["coarse_phase_deg"],
                forward_gain=forward_gain, joint_fit_iterations=used,
                joint_fit_converged=converged)


def scalar_qam_fit(symbols, order=64, iterations=5, *, dc_mode="legacy_mean"):
    """Blind scalar fit: legacy mean removal or explicit affine decision LS.

    No TX truth is used. Phase is identifiable only modulo 90 degrees.
    Joint DC is measured in the supplied symbol domain, before scalar correction.
    """
    positive_int(iterations, "iterations")
    validate_dc_mode(dc_mode)
    if dc_mode == "decision_directed_joint":
        return _joint_fit(symbols, order, iterations)
    y = complex_vector(symbols, 32).copy()
    dc = np.mean(y)
    y -= dc
    rms = np.sqrt(np.mean(abs(y)**2))
    if not np.isfinite(rms) or rms <= 0:
        raise ValueError("zero or invalid QAM power")
    y /= rms
    moment = np.mean(y**4)
    phase = float(np.angle(-moment)/4) if abs(moment) > 1e-15 else 0.0
    y *= np.exp(-1j*phase)
    total_gain = np.exp(-1j*phase)/rms
    for _ in range(iterations):
        decisions, _ = qam_slicer(y, order)
        denominator = np.vdot(y, y)
        if not np.isfinite(denominator) or abs(denominator) <= 1e-30:
            raise ValueError("invalid scalar fit energy")
        gain = np.vdot(y, decisions)/denominator
        y *= gain
        total_gain *= gain
    decisions, indices = qam_slicer(y, order)
    evm = float(100*np.sqrt(np.sum(abs(y-decisions)**2)/np.sum(abs(decisions)**2)))
    if not np.isfinite(evm) or not np.isfinite(total_gain):
        raise ValueError("QAM fit exceeds supported numeric range")
    return {"eq":y, "decisions":decisions, "indices":indices, "evm_pct":evm,
            "dc":dc, "complex_gain":total_gain, "coarse_phase_deg":float(np.degrees(phase))}
