"""Independent RRC limits, FIR equivalence and constellation geometry."""

import numpy as np
import pytest
from scipy import signal

from psd.qam import rrc_taps, qam_constellation, qam_slicer, scalar_qam_fit


@pytest.mark.parametrize("beta", [0,0.25,1])
@pytest.mark.parametrize("sps", [2,3,8])
def test_rrc_energy_symmetry(beta,sps):
    h = rrc_taps(beta,10,sps)
    assert len(h) == 10*sps+1
    np.testing.assert_allclose(h,h[::-1],atol=1e-15)
    assert np.dot(h,h) == pytest.approx(1,abs=3e-15)
    assert np.all(np.isfinite(h))
    # Independent continuous-time expression evaluated away from singularities.
    t = np.arange(-5*sps,5*sps+1)/sps
    safe = (t != 0)&(abs(1-(4*beta*t)**2)>1e-12)
    expected = np.sinc(t[safe]) if beta == 0 else (
        np.sin(np.pi*t[safe]*(1-beta))+4*beta*t[safe]*np.cos(np.pi*t[safe]*(1+beta))
        )/(np.pi*t[safe]*(1-(4*beta*t[safe])**2))
    center = 1+beta*(4/np.pi-1)
    np.testing.assert_allclose(h[safe]/h[len(h)//2],expected/center,atol=2e-15)


def test_rrc_singular_and_odd_length():
    h = rrc_taps(.25,10,8)
    singular = .25/np.sqrt(2)*((1+2/np.pi)*np.sin(np.pi)+(1-2/np.pi)*np.cos(np.pi))
    assert h[48]/h[40] == pytest.approx(singular/(1+.25*(4/np.pi-1)))
    assert len(rrc_taps(.25,3,3)) == 11
    rng = np.random.default_rng(5)
    x = rng.normal(size=203)+1j*rng.normal(size=203)
    np.testing.assert_allclose(signal.fftconvolve(x,h,mode="same"),
                               np.convolve(x,h,mode="same"),atol=2e-15)


@pytest.mark.parametrize("order", [16,64,256])
def test_constellation_geometry_and_rotation(order):
    d = qam_constellation(order)
    assert len(d) == len(np.unique(d)) == order
    root = int(np.sqrt(order))
    levels = np.arange(-root+1,root,2)/np.sqrt(2*(order-1)/3)
    np.testing.assert_array_equal(np.unique(d.real),levels)
    assert np.mean(abs(d)**2) == pytest.approx(1)
    decisions,indices = qam_slicer(d,order)
    np.testing.assert_array_equal(indices,np.arange(order))
    np.testing.assert_array_equal(decisions,d)
    rotated,_ = qam_slicer(d*1j,order)
    np.testing.assert_allclose(rotated,d*1j,atol=1e-15)
    # Complete equally weighted cycles have exact zero mean, so scalar fitting
    # removes a known gain/phase/DC without finite-record mean bias.
    y = np.tile(d,8)*.63*np.exp(.31j)+(.02-.03j)
    fit = scalar_qam_fit(y,order)
    assert fit["evm_pct"] < 1e-11
    assert fit["dc"] == pytest.approx(.02-.03j,abs=1e-15)


@pytest.mark.parametrize("args", [(-.1,10,8),(1.1,10,8),(np.nan,10,8),(.25,0,8),(.25,10,0)])
def test_invalid_rrc(args):
    with pytest.raises(ValueError):
        rrc_taps(*args)
