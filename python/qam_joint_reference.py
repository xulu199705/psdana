"""One independent TX-aided LS fit; never called by the blind receiver."""

import numpy as np

from qam_reference import data_aided_check


def data_aided_scalar_reference(recovered, transmitted, symbol_rate_hz, true_cfo_hz=0):
    """Align unchanged TX truth, remove known CFO, solve one affine LS system.

    Also evaluate one zero-offset scalar reference. No iterative TX refitting,
    equalizer or timing optimization. Both references use the receiver's selected
    samples, so this does not claim optimal data-aided timing recovery.
    """
    comparison = data_aided_check(recovered, transmitted)
    count = len(recovered["eq"])
    start = recovered["first_symbol_index"]+comparison["integer_symbol_shift"]
    d = transmitted[(start+np.arange(count))%len(transmitted)]*(1j**comparison["quadrant_rotation"])
    z = recovered["symbols_raw"]*np.exp(-2j*np.pi*true_cfo_hz*np.arange(count)/symbol_rate_hz)
    design = np.column_stack((d,np.ones(count,complex)))
    coefficients,_,rank,_ = np.linalg.lstsq(design,z,rcond=None)
    if rank != 2 or abs(coefficients[0]) == 0:
        raise ValueError("data-aided reference is singular")
    a,c = coefficients
    y = (z-c)/a
    denominator = np.sum(d.real*d.real+d.imag*d.imag)
    def evm(values):
        e = values-d
        return float(100*np.sqrt(np.sum(e.real*e.real+e.imag*e.imag)/denominator))
    a0 = np.sum(np.conj(d)*z)/denominator
    estimated_cfo = recovered.get("cfo_hz")
    estimated_z = recovered["symbols_raw"] if estimated_cfo is None else recovered["symbols_raw"]*np.exp(
        -2j*np.pi*estimated_cfo*np.arange(count)/symbol_rate_hz)
    estimated_a,estimated_c = np.linalg.lstsq(design,estimated_z,rcond=None)[0]
    return dict(comparison=comparison, evm_pct_rms=evm(y),
                zero_dc_scalar_evm_pct_rms=evm(z/a0), forward_gain=a,
                dc=c, complex_gain=1/a,
                at_estimated_cfo_evm_pct=evm((estimated_z-estimated_c)/estimated_a),
                at_estimated_cfo_dc=estimated_c, at_estimated_cfo_gain=1/estimated_a)
