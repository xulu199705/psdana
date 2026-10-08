"""Versioned Q1.15 contract and independent slicer equivalence."""
from dataclasses import asdict
import json
import numpy as np
import pytest
from qam_gen import ROOT,sha256
from psd import PSDConfig,compute_psd,analyze_band_power
from psd.csvio import CSVConfig,read_csv
from psd.qam import QAMConfig,analyze_qam,qam_constellation,scalar_qam_fit,qam_slicer
from psd.qam._slicer import nearest_level_indices

@pytest.mark.parametrize('order',[16,64,256])
def test_threshold_slicer_vs_brute(order):
    root=int(np.sqrt(order));levels=qam_constellation(order)[::root].real
    mid=(levels[1:]+levels[:-1])/2
    rng=np.random.default_rng(212)
    values=np.r_[rng.uniform(-4,4,100000),levels,mid,np.nextafter(mid,-np.inf),np.nextafter(mid,np.inf),0,-np.finfo(float).max,np.finfo(float).max]
    expected=np.argmin(abs(values[:,None]-levels),axis=1)
    np.testing.assert_array_equal(nearest_level_indices(values,levels),expected)

def test_joint_iteration_limit_contract():
    n=np.arange(512,dtype=float)
    z=np.sin(n*.37)+.3*np.cos(n*.19)+1j*(np.cos(n*.23)+.2*np.sin(n*.43))
    initial=scalar_qam_fit(z,64,1)
    fit=scalar_qam_fit(z,64,1,dc_mode='decision_directed_joint')
    assert not fit['joint_fit_converged'] and fit['joint_fit_iterations']==1
    d=initial['decisions'];centered=d-d.mean()
    gain=np.vdot(centered,z-z.mean())/np.sum(abs(centered)**2)
    np.testing.assert_allclose(fit['forward_gain'],gain,atol=1e-14)
    np.testing.assert_allclose(fit['dc'],z.mean()-gain*d.mean(),atol=1e-14)
    np.testing.assert_allclose(fit['eq'],(z-fit['dc'])/fit['forward_gain'],atol=1e-14)
    np.testing.assert_array_equal(fit['decisions'],qam_slicer(fit['eq'],64)[0])

def test_q15_32768_psd_contract():
    path=ROOT/'data/generated/qam/Q13_32768_q15.csv'
    meta=json.loads((path.parent/'manifest_v2.1.2.json').read_text())
    assert sha256(path)==meta['input_sha256']
    assert sha256(path.parent/meta['truth_file'])==meta['truth_sha256']
    truth=np.loadtxt(path.parent/meta['truth_file'],delimiter=',',skiprows=1)
    assert len(truth)==4096 and meta['clipped_component_count']==0
    x=read_csv(path,CSVConfig(sample_format='q15',i_column='i',q_column='q')).samples
    ints=np.loadtxt(path,delimiter=',',skiprows=1)
    assert len(x)==32768
    np.testing.assert_array_equal(x,ints[:,0]/32768+1j*ints[:,1]/32768)
    r=compute_psd(x,PSDConfig(fft_points=32768))
    assert r.method=='periodogram' and r.reference_power==1
    assert r.frequency_resolution_hz==160e6/32768
    assert r.enbw_hz==pytest.approx(1.5*r.frequency_resolution_hz)
    p=analyze_band_power(r,-80e6,80e6)
    assert p.band_power_linear==pytest.approx(r.integrated_power)
    assert compute_psd(np.tile(x,2),PSDConfig(fft_points=32768)).method=='welch'
    assert compute_psd(x,PSDConfig()).fft_size==len(x)
    with pytest.raises(ValueError):compute_psd(x[:16384],PSDConfig(fft_points=32768))

@pytest.mark.parametrize('mode',['legacy_mean','decision_directed_joint'])
def test_q15_32768_golden(mode):
    folder=ROOT/'data/golden/qam/v2.1.2'
    index=json.loads((folder/'index.json').read_text());entry=next(v for v in index['vectors'] if v['file']==mode+'.json')
    path=folder/entry['file'];assert sha256(path)==entry['sha256']
    v=json.loads(path.read_text());source=folder/v['input_file'];assert sha256(source)==v['input_sha256']
    x=read_csv(source,CSVConfig(sample_format='q15',i_column='i',q_column='q')).samples
    r=analyze_qam(x,QAMConfig(**v['qam_config']),dc_mode=mode).to_dict()
    assert r['recovered_symbol_count']==4074
    assert r['timing_offset_symbols']==v['expected']['timing_offset_symbols']
    assert r['frequency_error_hz']==v['expected']['frequency_error_hz']
    for field in ('evm_pct_rms','amplitude_error_pct_rms','phase_error_pct_rms','phase_error_deg_rms'):
        assert abs(r[field]-v['expected'][field])<=v['tolerances']['metric_atol']
    for field in ('constellation_i','constellation_q','ideal_i','ideal_q'):
        np.testing.assert_allclose(r[field],v['expected'][field],atol=1e-9,rtol=1e-9)
