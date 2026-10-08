"""Analytic error vectors are independent expected values, not Golden outputs."""

import numpy as np
import pytest

from psd.qam import qam_error_metrics, qam_constellation


def test_radial_tangential_decomposition():
    d = np.array([1+1j,-3+1j,1-3j,-3-3j])/np.sqrt(10)
    radial, tangential = .03, .04
    y = d*(1+radial+1j*tangential)
    metrics = qam_error_metrics(y,d)
    assert metrics["evm_pct_rms"] == pytest.approx(5)
    assert metrics["amplitude_error_pct_rms"] == pytest.approx(3)
    assert metrics["phase_error_pct_rms"] == pytest.approx(4)
    assert metrics["phase_error_deg_rms"] == pytest.approx(np.degrees(np.arctan2(.04,1.03)))
    assert metrics["evm_pct_rms"]**2 == pytest.approx(
        metrics["amplitude_error_pct_rms"]**2+metrics["phase_error_pct_rms"]**2,abs=1e-12)


def test_angle_and_error_vector_are_different():
    d = qam_constellation()
    angle = .06
    m = qam_error_metrics(d*np.exp(1j*angle),d)
    assert m["evm_pct_rms"] == pytest.approx(200*np.sin(angle/2))
    assert m["amplitude_error_pct_rms"] == pytest.approx(100*(1-np.cos(angle)))
    assert m["phase_error_pct_rms"] == pytest.approx(100*np.sin(angle))
    assert m["phase_error_deg_rms"] == pytest.approx(np.degrees(angle))


@pytest.mark.parametrize("y,d", [(np.array([],complex),np.array([],complex)),
    (np.ones(3,complex),np.ones(2,complex)),(np.ones(3),np.ones(3,complex)),
    (np.ones(3,complex),np.zeros(3,complex)),(np.array([np.nan+1j]),np.ones(1,complex)),
    (np.array([1e308+1j]),np.ones(1,complex))])
def test_invalid_metrics(y,d):
    with pytest.raises(ValueError):
        qam_error_metrics(y,d)
