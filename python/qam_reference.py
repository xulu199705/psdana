"""Independent data-aided metric check for synthetic fixtures only.

No receiver refitting, equalization or alteration of TX symbols. Only integer
alignment and four possible quadrant rotations are searched. The corrected RX
symbols come from the blind receiver unchanged.
"""

import numpy as np


def data_aided_check(recovered, transmitted):
    y = recovered["eq"]
    first = recovered["first_symbol_index"]
    n = len(y)
    best = None
    for shift in range(-2,3):
        indices = (first+shift+np.arange(n))%len(transmitted)
        reference = transmitted[indices]
        for quadrant in range(4):
            d = reference*(1j**quadrant)
            error_power = float(np.dot((y-d).real,(y-d).real)+np.dot((y-d).imag,(y-d).imag))
            if best is None or error_power < best[0]:
                best = (error_power,d,shift,quadrant)
    error_power,d,shift,quadrant = best
    energy = float(np.dot(d.real,d.real)+np.dot(d.imag,d.imag))
    e = y-d
    mag = np.sqrt(d.real*d.real+d.imag*d.imag)
    radial = (e.real*d.real+e.imag*d.imag)/mag
    tangential = (e.imag*d.real-e.real*d.imag)/mag
    # Explicit Cartesian arithmetic is independent of qam_error_metrics.
    return dict(evm_pct_rms=100*np.sqrt(error_power/energy),
                amplitude_error_pct_rms=100*np.sqrt(np.dot(radial,radial)/energy),
                phase_error_pct_rms=100*np.sqrt(np.dot(tangential,tangential)/energy),
                phase_error_deg_rms=np.sqrt(np.mean(np.degrees(np.arctan2(
                    y.imag*d.real-y.real*d.imag,y.real*d.real+y.imag*d.imag))**2)),
                integer_symbol_shift=shift, quadrant_rotation=quadrant,
                decision_mismatch_count=int(np.count_nonzero(abs(recovered["decisions"]-d)>1e-12)))
