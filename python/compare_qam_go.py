"""Full-array stage comparison with bounded persistent statistics.

Build qamcheck once; subprocess/JSON are validation transport, never benchmark.
No existing Golden is regenerated. Temporary full arrays remain in memory.
"""
from dataclasses import asdict
import argparse
import json
from pathlib import Path
import subprocess
import numpy as np
import scipy
from scipy import signal
from psd.csvio import CSVConfig, read_csv
from psd.qam import QAMConfig, rrc_taps, analyze_qam
from psd.qam.constellation import scalar_qam_fit
from psd.qam.receiver import _synchronize
from psd.qam.timing import search_timing_phases
from qam_gen import ROOT, generate_signal, sha256

def pack(x): return dict(real=x.real.tolist(),imag=x.imag.tolist())
def unpack(x): return np.asarray(x['real'])+1j*np.asarray(x['imag'])

def invoke(executable,x,cfg,mode,taps=None,stages_only=False):
    request=dict(samples=pack(x),config=asdict(cfg),dc_mode=mode,stages_only=stages_only)
    if taps is not None: request['taps']=np.asarray(taps).tolist()
    p=subprocess.run([str(executable)],input=json.dumps(request,allow_nan=False),
                     text=True,capture_output=True,check=True)
    return json.loads(p.stdout)

def compare_array(a,b,name,atol=1e-9,rtol=1e-9):
    a,b=np.asarray(a),np.asarray(b)
    assert a.shape==b.shape,(name,a.shape,b.shape)
    delta=np.abs(a-b)
    assert np.all(delta<=atol+rtol*np.abs(b)),(name,float(delta.max()))
    keep=np.abs(b)>=1e-12
    indexes=np.unique(np.r_[np.arange(min(4,len(b))),np.linspace(0,len(b)-1,min(5,len(b)),dtype=int),np.arange(max(0,len(b)-4),len(b))])
    return dict(stage=name,output_length=len(b),max_absolute_error=float(delta.max(initial=0)),
        max_relative_error=float((delta[keep]/np.abs(b[keep])).max(initial=0)),
        rms_power=float(np.mean(abs(b)**2)) if len(b) else 0,
        selected_indices=indexes.tolist(),expected_selected=pack(b[indexes].astype(complex)))

def compare_tree(a,b,field=''):
    if field=='config' or field in ('sample_rate_hz','symbol_rate_hz','fs_hz'):
        assert a==b,(field,a,b)
    elif isinstance(b,dict):
        for key,v in b.items(): compare_tree(a[key],v,key)
    elif isinstance(b,list):
        assert len(a)==len(b),(field,len(a),len(b))
        for aa,bb in zip(a,b): compare_tree(aa,bb,field)
    elif isinstance(b,bool) or b is None or isinstance(b,str) or isinstance(b,int):
        assert a==b,(field,a,b)
    elif field in ('frequency_error_hz','timing_offset_symbols','timing_initial_offset_symbols'):
        assert abs(a-b)<=1e-9 if field=='frequency_error_hz' else a==b,(field,a,b)
    else: assert abs(a-b)<=1e-9+1e-9*abs(b),(field,a,b)

def cfo_grids(raw,cfg,mode):
    if not cfg.enable_cfo_correction: return [],[],[],[]
    length=min(len(raw),cfg.cfo_search_max_symbols);start=(len(raw)-length)//2
    y=raw[start:start+length];n=np.arange(length)/cfg.symbol_rate_hz
    def scores(grid):return np.array([scalar_qam_fit(y*np.exp(-2j*np.pi*f*n),cfg.qam_order,cfg.scalar_fit_iterations,dc_mode=mode)['evm_pct'] for f in grid])
    coarse=np.linspace(-cfg.max_residual_cfo_hz,cfg.max_residual_cfo_hz,cfg.cfo_coarse_steps)
    s=scores(coarse);best=coarse[np.argmin(s)];step=coarse[1]-coarse[0]
    fine=np.linspace(max(-cfg.max_residual_cfo_hz,best-step),min(cfg.max_residual_cfo_hz,best+step),cfg.cfo_fine_steps)
    return coarse,s,fine,scores(fine)

def receiver_case(executable,name,x,cfg,mode):
    go=invoke(executable,x,cfg,mode)
    xx=x.real+1j*cfg.q_sign*x.imag
    h=rrc_taps(cfg.rrc_beta,cfg.rrc_span_symbols,cfg.samples_per_symbol)
    matched=signal.fftconvolve(xx,h,mode='same')
    up=signal.resample_poly(matched,cfg.timing_interp,1,window=('kaiser',cfg.timing_kaiser_beta),padtype='constant')
    ih=(signal.firwin(20*cfg.timing_interp+1,1/cfg.timing_interp,window=('kaiser',cfg.timing_kaiser_beta))*cfg.timing_interp if cfg.timing_interp>1 else [1])
    stats=[compare_array(go['taps'],h,'rrc',1e-14,1e-13),compare_array(go['interpolation_taps'],ih,'interpolation_taps',1e-14,1e-13),
        compare_array(unpack(go['matched']),matched,'matched',1e-12,1e-12),
        compare_array(unpack(go['interpolated']),up,'interpolated',1e-12,1e-12)]
    initial=search_timing_phases(up,cfg,dc_mode=mode)
    stats.append(compare_array(go['initial_timing_curve'],initial['timing_curve_evm_pct'],'initial_timing_curve'))
    r=_synchronize(x,cfg,mode)
    stats.append(compare_array(unpack(go['raw_symbols']),r['symbols_raw'],'raw_symbols',1e-12,1e-12))
    for key in ('eq','decisions'):
        stats.append(compare_array(unpack(go['scalar'][key]),r[key],key,1e-10,1e-10))
    assert go['scalar']['indices']==r['indices'].tolist(),'decision index mismatch'
    for key in ('complex_gain','dc','forward_gain'):
        if key in r: compare_tree(go['scalar'][key],dict(real=float(r[key].real),imag=float(r[key].imag)),key)
    grids=cfo_grids(r['symbols_raw'],cfg,mode)
    for key,value in zip(('cfo_coarse_hz','cfo_coarse_scores','cfo_fine_hz','cfo_fine_scores'),grids):
        stats.append(compare_array(go[key] or [],value,key,1e-9,1e-9))
    py=analyze_qam(x,cfg,dc_mode=mode).to_dict();compare_tree(go['result'],py)
    curve=np.sort(initial['timing_curve_evm_pct'])
    return dict(id=name,mode=mode,input_samples=len(x),stages=stats,python=py,go=go['result'],
        timing_best_runnerup_gap_pct=float(curve[1]-curve[0]),
        metric_differences={k:abs(go['result'][k]-py[k]) for k in ('evm_pct_rms','amplitude_error_pct_rms','phase_error_pct_rms','phase_error_deg_rms')})

def run(executable,output):
    rows=[]
    for name,path,fmt in [('REAL64',ROOT/'data/qam64_20MSymPS_160MSPS_RRC0p25.csv','hex_q15'),
                         ('Q13_32768',ROOT/'data/generated/qam/Q13_32768_q15.csv','q15')]:
        x=read_csv(path,CSVConfig(sample_format=fmt,i_column='i',q_column='q')).samples
        for mode in ('legacy_mean','decision_directed_joint'):
            row=receiver_case(executable,name,x,QAMConfig(constellation_points=128),mode)
            row['input_sha256']=sha256(path);rows.append(row);print(name,mode,'PASS',flush=True)
    for sps in (2,8):
        x,_,_=generate_signal(symbol_count=512,sps=sps,symbol_rate_hz=160e6/sps,timing_offset_samples=.5)
        for mode in ('legacy_mean','decision_directed_joint'):
            rows.append(receiver_case(executable,f'SPS{sps}_fractional',x,QAMConfig(symbol_rate_hz=160e6/sps,constellation_points=128),mode))
    x,_,_=generate_signal(symbol_count=600,seed=21232768)
    for n in (4093,4099):
        for mode in ('legacy_mean','decision_directed_joint'):
            rows.append(receiver_case(executable,f'NONALIGNED_{n}',x[:n],QAMConfig(constellation_points=128),mode))
    x,_,_=generate_signal(symbol_count=533,seed=21232768)
    for mode in ('legacy_mean','decision_directed_joint'):
        rows.append(receiver_case(executable,'CONSTELLATION_255',x,QAMConfig(constellation_points=255),mode))
        rows.append(receiver_case(executable,'CFO_DISABLED_QSIGN',x.conj(),QAMConfig(q_sign=-1,enable_cfo_correction=False,constellation_points=128),mode))
        rows.append(receiver_case(executable,'INTERP_IDENTITY',x,QAMConfig(timing_interp=1,constellation_points=128),mode))
    rng=np.random.default_rng(212)
    filters=[]
    for n in (31,127,1023,32768):
        for kind in ('impulse','tone','random'):
            x=np.zeros(n,complex)
            if kind=='impulse': x[n//2]=1+2j
            elif kind=='tone':x=np.exp(2j*np.pi*.031*np.arange(n))
            else:x=rng.normal(size=n)+1j*rng.normal(size=n)
            for length in (1,2,7,16,81):
                h=rng.normal(size=length);go=invoke(executable,x,QAMConfig(), 'legacy_mean',h,True)
                m=signal.fftconvolve(x,h,mode='same');up=signal.resample_poly(m,16,1,window=('kaiser',8))
                filters.append(dict(n=n,kind=kind,taps=length,matched=compare_array(unpack(go['matched']),m,'matched',1e-11,1e-12),interpolated=compare_array(unpack(go['interpolated']),up,'interpolated',1e-11,1e-12)))
        print('Filter full-array matrix',n,'PASS',flush=True)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(dict(status='PASS',scipy=scipy.__version__,receiver_cases=rows,filter_cases=filters),indent=2,allow_nan=False)+'\n',encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--executable',type=Path,default=ROOT/'.cache/v212/qamcheck.exe')
    p.add_argument('--output',type=Path,default=ROOT/'go/reports/v2.1.2_stage_validation.json')
    a=p.parse_args();run(a.executable,a.output)
