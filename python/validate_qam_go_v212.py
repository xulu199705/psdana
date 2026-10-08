"""Reliability/CLI comparison; preserve known blind false candidates."""
from dataclasses import asdict
import json
import subprocess
import numpy as np
from psd import PSDConfig,compute_psd,analyze_band_power
from psd.csvio import CSVConfig,read_csv
from psd.qam import QAMConfig,analyze_qam,qam_constellation,scalar_qam_fit
from qam_gen import ROOT,generate_signal
from compare_qam_go import pack,unpack,compare_tree,compare_array
from scipy import signal
from psd.qam import rrc_taps
from psd.qam.receiver import _synchronize

def rejected_tie_evidence(x,c,mode,go,expected):
    """Audit actual competing scores; only rejected near-ties may differ."""
    assert expected['status']==go['diagnostics']['status']=='unreliable'
    r=_synchronize(x,c,mode);debug=go['rejected_search']
    period=c.samples_per_symbol*c.timing_interp;phase=debug['timing_phase_up']
    xx=x.real+1j*c.q_sign*x.imag
    h=rrc_taps(c.rrc_beta,c.rrc_span_symbols,c.samples_per_symbol)
    up=signal.resample_poly(signal.fftconvolve(xx,h,mode='same'),c.timing_interp,1,window=('kaiser',c.timing_kaiser_beta))
    trim=c.rrc_span_symbols//2+c.extra_edge_trim_symbols
    raw=up[trim*period+phase:len(up)-trim*period:period];start=max(0,(len(raw)-c.max_analysis_symbols)//2);raw=raw[start:start+c.max_analysis_symbols]
    length=min(len(raw),c.cfo_search_max_symbols);start=(len(raw)-length)//2;subset=raw[start:start+length];n=np.arange(length)/c.symbol_rate_hz
    def score(f):return scalar_qam_fit(subset*np.exp(-2j*np.pi*f*n),c.qam_order,c.scalar_fit_iterations,dc_mode=mode)['evm_pct']
    raw_comparison=compare_array(unpack(debug['raw_symbols']),raw,'rejected_raw_symbols',1e-12,1e-12)
    arrays=[]
    for label in ('coarse','fine'):
        frequencies=debug[label+'_hz'];scores=np.array([score(f) for f in frequencies])
        actual=np.asarray(debug[label+'_scores']);assert actual.shape==scores.shape
        best=int(np.argmin(actual))
        assert abs(actual[best]-scores[best])<=1e-9
        assert scores[best]-scores.min()<=1e-9
        # Non-QAM decision branches can amplify roundoff for nonwinning
        # candidates. Record the full finite curves, never declare equivalence.
        arrays.append(dict(stage=label+'_scores',max_absolute_error=float(abs(actual-scores).max()),
            go_best_index=best,python_best_index=int(np.argmin(scores)),
            go_selected_score_gap_to_python_min_pct=float(scores[best]-scores.min()),
            python_scores=scores.tolist(),go_scores=actual.tolist(),frequencies_hz=frequencies))
    go_hz=go['diagnostics']['frequency_error_hz'];py_hz=expected['frequency_error_hz']
    competing_gap=abs(score(go_hz)-score(py_hz))
    assert competing_gap<=1e-9,(go_hz,py_hz,competing_gap)
    # Timing and CFO ambiguity must not change acceptance or EVM/occupancy.
    for key in ('status','occupied_decision_points','evm_pct_rms','dc_estimation_mode','cfo_search_boundary_hit'):
        compare_tree(go['diagnostics'][key],expected[key],key)
    timing_comparison=compare_array(debug['timing_curve'],r['timing_curve_evm_pct'],'rejected_final_timing_curve',1e-9,1e-9)
    timing_gap=float(r['timing_curve_evm_pct'][phase]-r['timing_evm_pct'])
    assert abs(timing_gap)<=1e-9,'unexplained timing disagreement'
    return dict(qualification='rejected non-QAM signal; winning CFO candidates numerically tied; some nonwinning scalar branches differ, not claimed equivalent; strict Golden tolerances unchanged',python_cfo_hz=py_hz,go_cfo_hz=go_hz,
        raw_centered_power_ratio=float(np.mean(abs(raw-raw.mean())**2)/np.mean(abs(raw)**2)),
        competing_score_gap_pct=float(competing_gap),raw_symbols_comparison=raw_comparison,scoring_comparisons=arrays,
        python_timing_phase_up=int(r['timing_phase_up']),go_timing_phase_up=phase,timing_selected_gap_pct=timing_gap,timing_curve_comparison=timing_comparison,
        python_coarse_hz=debug['coarse_hz'],python_coarse_scores=[score(f) for f in debug['coarse_hz']],go_coarse_scores=debug['coarse_scores'])

def run():
    cfg=QAMConfig();rng=np.random.default_rng(4242);n=16384
    qam,_,_=generate_signal(seed=12345);tone=np.exp(2j*np.pi*np.arange(n)/8)
    cases=[('pure_awgn',rng.normal(size=n)+1j*rng.normal(size=n),cfg),
        ('single_tone',tone,cfg),('two_tones',tone+.4*tone.conj(),cfg),
        ('random_phase',np.exp(1j*rng.uniform(-np.pi,np.pi,n)),cfg),
        ('wrong_rate',qam,QAMConfig(symbol_rate_hz=40e6)),('wrong_rrc',qam,QAMConfig(rrc_beta=1)),
        ('low_snr',generate_signal(noise_evm_pct=70)[0],cfg),
        ('sample_order',qam.reshape(-1,2)[:,::-1].ravel(),cfg),
        ('swapped_iq',qam.imag+1j*qam.real,cfg),('wrong_q_polarity',qam,QAMConfig(q_sign=-1)),
        ('out_of_range_cfo',generate_signal(cfo_hz=6000)[0],cfg),
        ('zero_input',np.zeros(3000,complex),cfg),('short_capture',np.ones(100,complex),cfg)]
    rows=[];exe=ROOT/'.cache/v212/qamcheck.exe'
    def check(name,x,c,mode):
        request=dict(samples=pack(x),config=asdict(c),dc_mode=mode,summary_only=True)
        p=subprocess.run([str(exe)],input=json.dumps(request),capture_output=True,text=True,check=True)
        go=json.loads(p.stdout)
        try:
            py=analyze_qam(x,c,dc_mode=mode).to_dict();accepted=True;compare_tree(go['result'],py)
            row=dict(status=py['diagnostics']['status'],evm_pct_rms=py['evm_pct_rms'],frequency_error_hz=py['frequency_error_hz'],timing_offset_symbols=py['timing_offset_symbols'])
        except ValueError as exc:
            accepted=False;d=getattr(exc,'diagnostics',{'status':'unreliable'});row=dict(d)
            try:compare_tree(go['diagnostics'],d)
            except AssertionError:row['near_tie_evidence']=rejected_tie_evidence(x,c,mode,go,d)
        assert go['accepted']==accepted,(name,mode)
        rows.append(dict(id=name,mode=mode,accepted=accepted,**row))
    for name,x,c in cases:
        for mode in ('legacy_mean','decision_directed_joint'):check(name,x,c,mode)
        print(name,'PASS',flush=True)
    for hz in (0,-100,100,-1000,1000,-3000,3000,-4995,4995,-6000,6000):
        x,_,_=generate_signal(symbol_count=2048,seed=12345,cfo_hz=hz)
        for mode in ('legacy_mean','decision_directed_joint'):check('CFO_'+str(hz),x,cfg,mode)
        print('CFO',hz,'PASS',flush=True)
    cli=[];binary=ROOT/'.cache/v212/psdana.exe'
    for name,path,fmt,fft in [('REAL64','data/qam64_20MSymPS_160MSPS_RRC0p25.csv','hex_q15',16384),('Q13_32768','data/generated/qam/Q13_32768_q15.csv','q15',32768)]:
        x=read_csv(ROOT/path,CSVConfig(sample_format=fmt,i_column='i',q_column='q')).samples
        spectrum=compute_psd(x,PSDConfig(fft_points=fft));power=analyze_band_power(spectrum,-80e6,80e6).to_dict()
        for mode in ('legacy_mean','decision_directed_joint'):
            command=[str(binary),'--input',path,'--sample-format',fmt,'--fft-points',str(fft),'--qam','--qam-dc-mode',mode,'--constellation-points','128','--freq-left','-80000000','--freq-right','80000000','--json']
            go=json.loads(subprocess.run(command,cwd=ROOT,capture_output=True,text=True,check=True).stdout);stats=[]
            for field in ('frequency_hz','psd_linear','psd_dbfs_per_hz','rbw_power_dbfs'):
                if field=='frequency_hz':np.testing.assert_array_equal(go[field],spectrum.frequency_hz)
                stats.append(compare_array(go[field],getattr(spectrum,field),field,1e-9,1e-9))
            for field in asdict(spectrum):
                value=getattr(spectrum,field)
                if not isinstance(value,np.ndarray):compare_tree(go[field],value,field)
            compare_tree(go['power_metrics'],power);compare_tree(go['qam_metrics'],analyze_qam(x,QAMConfig(constellation_points=128),dc_mode=mode).to_dict())
            cli.append(dict(id=name,mode=mode,status='PASS',stages=stats,integrated_power=spectrum.integrated_power,df_hz=spectrum.frequency_resolution_hz,enbw_hz=spectrum.enbw_hz))
    points=qam_constellation(256);truth=np.r_[points,points,points[:128]];z=.7*np.exp(.3j)*truth+.02-.015j
    fit=scalar_qam_fit(z,256,dc_mode='decision_directed_joint')
    assert fit['joint_fit_converged'] and np.count_nonzero(fit['decisions']!=truth)==608
    report=dict(status='PASS',reliability=rows,cli=cli,skewed_256qam=dict(symbols=640,wrong_decisions=608,evm_pct=fit['evm_pct'],joint_fit_converged=True,qualification='Foundation regression in both languages; not an absolute lock'))
    target=ROOT/'go/reports/v2.1.2_reliability_validation.json';target.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')

if __name__=='__main__':run()
