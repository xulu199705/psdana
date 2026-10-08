"""Square QAM with I-major/Q-minor indices and only scalar compensation."""

import numpy as np

from .config import positive_int


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
    ii = np.argmin(abs(z.real[:,None]-levels), axis=1)
    qq = np.argmin(abs(z.imag[:,None]-levels), axis=1)
    indices = ii*root+qq
    return points[indices], indices


slicer = qam_slicer


def scalar_qam_fit(symbols, order=64, iterations=5):
    """Remove mean, normalize RMS, recover modulo-90 phase and fit one scalar."""
    positive_int(iterations, "iterations")
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
