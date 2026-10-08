"""Analytic CFO, timing, scalar and input limits independent of fixtures."""

import numpy as np
import pytest

from psd.qam import QAMConfig, analyze_qam, recover_symbols, search_residual_cfo, qam_constellation
from psd import analyze_iq, PSDConfig
from qam_gen import generate_signal


@pytest.mark.parametrize("frequency", [0,1000,-3000,4995,6000])
def test_cfo_sign_resolution_and_boundary(frequency):
    rng = np.random.default_rng(18)
    d = np.concatenate([rng.permutation(qam_constellation()) for _ in range(64)])
    y = d*np.exp(2j*np.pi*frequency*np.arange(len(d))/20e6)
    fit = search_residual_cfo(y,QAMConfig())
    if abs(frequency) <= 5000:
        assert abs(fit["cfo_hz"]-frequency) <= 2*fit["cfo_grid_resolution_hz"]
        assert fit["evm_pct"] < 2
    if frequency == 4995:
        assert fit["cfo_boundary_hit"]
    if frequency == 6000:
        assert abs(fit["cfo_hz"]-frequency) > 500
    if frequency in (1000,-3000):
        off = search_residual_cfo(y,QAMConfig(enable_cfo_correction=False))
        assert off["cfo_hz"] is None
        assert fit["evm_pct"] < off["evm_pct"]


@pytest.mark.parametrize("sps,offset", [(8,0),(8,2),(8,.5),(8,1.5),(2,.5)])
def test_timing_and_data_not_mutated(sps,offset):
    x,_,_ = generate_signal(symbol_count=3072,sps=sps,symbol_rate_hz=160e6/sps,
                             timing_offset_samples=offset)
    before = x.copy()
    r = analyze_qam(x,QAMConfig(symbol_rate_hz=160e6/sps,constellation_points=123))
    # Circular phase difference handles a near-one-symbol phase representation.
    error = abs((r.timing_offset_symbols-offset/sps+.5)%1-.5)
    assert error <= 1/(sps*16)
    assert r.recovered_symbol_count == 3050
    assert len(r.constellation_i) == 123
    assert len(r.ideal_i) == 64
    np.testing.assert_array_equal(x,before)


def test_analysis_limit_disabled_cfo_and_composition():
    x,_,_ = generate_signal(symbol_count=4096)
    cfg = QAMConfig(max_analysis_symbols=1000,cfo_search_max_symbols=500,
                    enable_cfo_correction=False)
    result = analyze_iq(x,PSDConfig(),cfg,(-80e6,80e6))
    assert result.qam_metrics.frequency_error_hz is None
    assert result.qam_metrics.recovered_symbol_count == 1000
    assert result.power_metrics.band_power_linear == pytest.approx(result.psd.integrated_power)
    assert result.qam_metrics.diagnostics["cfo_search_symbol_count"] == 0
    assert analyze_iq(x).qam_metrics is None
    with pytest.raises(ValueError,match="rates"):
        analyze_iq(x,PSDConfig(fs=80e6),cfg)
    with pytest.raises(ValueError):
        analyze_iq(x.real,PSDConfig(),cfg)


@pytest.mark.parametrize("change", [dict(sample_rate_hz=0),dict(symbol_rate_hz=np.inf),
    dict(symbol_rate_hz=21e6),dict(symbol_rate_hz=160e6),dict(qam_order=32),
    dict(rrc_beta=-1),dict(rrc_beta=1.1),dict(rrc_span_symbols=0),
    dict(timing_interp=0),dict(timing_interp=True),dict(extra_edge_trim_symbols=-1),
    dict(cfo_coarse_steps=4),dict(cfo_fine_steps=1),dict(max_residual_cfo_hz=np.nan),
    dict(max_residual_cfo_hz=0),dict(max_analysis_symbols=10),dict(q_sign=0),
    dict(q_sign=True),dict(constellation_points=0),dict(scalar_fit_iterations=0),
    dict(enable_cfo_correction=1),dict(min_analysis_symbols=1)])
def test_invalid_config(change):
    with pytest.raises(ValueError):
        QAMConfig(**change)


@pytest.mark.parametrize("x", [np.array([],complex),np.zeros(3000,complex),
    np.ones(3000,complex),np.ones(3000),np.ones((2,3000),complex),
    np.full(3000,np.nan+1j),np.full(3000,np.inf+1j),np.ones(100,complex),
    np.full(3000,1e308+1e308j)])
def test_invalid_or_short_input(x):
    with pytest.raises(ValueError):
        analyze_qam(x)


def test_noise_is_not_claimed_as_lock():
    rng = np.random.default_rng(88)
    x = rng.normal(size=4096)+1j*rng.normal(size=4096)
    with pytest.raises(ValueError,match="unreliable"):
        analyze_qam(x)


def test_q_polarity_explicit():
    x,_,_ = generate_signal()
    a = analyze_qam(x)
    b = analyze_qam(x.conj(),QAMConfig(q_sign=-1))
    assert a.evm_pct_rms == b.evm_pct_rms
    np.testing.assert_array_equal(a.constellation_i,b.constellation_i)


def test_filter_once_and_cfo_subset(monkeypatch):
    from psd.qam import timing
    calls = []
    original = timing.signal.fftconvolve
    def counted(*args,**kwargs):
        calls.append(1)
        return original(*args,**kwargs)
    monkeypatch.setattr(timing.signal,"fftconvolve",counted)
    x,_,_ = generate_signal(symbol_count=4096,cfo_hz=1000)
    r = analyze_qam(x,QAMConfig(max_analysis_symbols=1000,cfo_search_max_symbols=500))
    assert len(calls) == 1
    assert r.recovered_symbol_count == 1000
    assert r.diagnostics["cfo_search_symbol_count"] == 500
    assert abs(r.frequency_error_hz-1000) <= 2*r.diagnostics["cfo_grid_resolution_hz"]
