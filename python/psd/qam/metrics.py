"""Decision-directed or supplied-reference metrics; no fitting performed here."""

import numpy as np

from .constellation import complex_vector


def qam_error_metrics(symbols, decisions) -> dict:
    y, d = complex_vector(symbols), complex_vector(decisions)
    if y.shape != d.shape or np.any(abs(d) == 0):
        raise ValueError("metric reference must have matching nonzero symbols")
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        try:
            error = y-d
            energy = float(np.sum(abs(d)**2))
            radial = np.real(error*np.conj(d))/abs(d)
            tangential = np.imag(error*np.conj(d))/abs(d)
            angle = np.degrees(np.angle(y*np.conj(d)))
            values = {
                "evm_pct_rms":float(100*np.sqrt(np.sum(abs(error)**2)/energy)),
                "amplitude_error_pct_rms":float(100*np.sqrt(np.sum(radial**2)/energy)),
                "phase_error_pct_rms":float(100*np.sqrt(np.sum(tangential**2)/energy)),
                "phase_error_deg_rms":float(np.sqrt(np.mean(angle**2))),
            }
        except FloatingPointError as exc:
            raise ValueError("QAM metrics exceed supported numeric range") from exc
    if not all(np.isfinite(v) for v in values.values()):
        raise ValueError("QAM metrics are nonfinite")
    return values
