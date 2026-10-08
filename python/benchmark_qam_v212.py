"""Identical-buffer Python/Go stage benchmark with isolated workers."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import numpy as np
import scipy
from scipy import signal
from psd import PSDConfig, compute_psd
from psd.qam import QAMConfig, analyze_qam, rrc_taps, scalar_qam_fit, qam_error_metrics
from psd.qam.receiver import _synchronize
from psd.qam.timing import search_timing_phases
from psd.qam.carrier import search_residual_cfo
from psd.csvio import CSVConfig,read_csv
from benchmark_qam import measure,peak_working_set
from qam_gen import ROOT,generate_signal,sha256

def python_worker(request):
    c=QAMConfig(**request['Config']);mode=request['DCMode']
    x=np.asarray(request['Real'])+1j*np.asarray(request['Imag']);request['Real']=request['Imag']=None
    r=_synchronize(x,c,mode);h=rrc_taps(c.rrc_beta,c.rrc_span_symbols,c.samples_per_symbol)
    matched=signal.fftconvolve(x,h,mode='same');up=signal.resample_poly(matched,c.timing_interp,1,window=('kaiser',c.timing_kaiser_beta))
    pc=PSDConfig(fs=c.sample_rate_hz,fft_points=request['FFTPoints']);rows=[]
    def timing():
        search_timing_phases(up,c,dc_mode=mode)
        if mode=='decision_directed_joint': search_timing_phases(up,c,dc_mode=mode,cfo_hz=r['cfo_hz'])
    operations=[('psd_core',lambda:compute_psd(x,pc)),('rrc_taps',lambda:rrc_taps(c.rrc_beta,c.rrc_span_symbols,c.samples_per_symbol)),
        ('matched_rrc',lambda:signal.fftconvolve(x,h,mode='same')),
        ('fractional_interpolation',lambda:signal.resample_poly(matched,c.timing_interp,1,window=('kaiser',c.timing_kaiser_beta))),
        ('timing_search',timing),('cfo_search',lambda:search_residual_cfo(r['symbols_raw'],c,dc_mode=mode)),
        ('scalar_fit',lambda:scalar_qam_fit(r['eq'],c.qam_order,c.scalar_fit_iterations,dc_mode=mode)),
        ('error_metrics',lambda:qam_error_metrics(r['eq'],r['decisions'])),
        ('receiver_total',lambda:analyze_qam(x,c,dc_mode=mode)),
        ('psd_qam_total',lambda:(compute_psd(x,pc),analyze_qam(x,c,dc_mode=mode)))]
    for stage,op in operations:
        stats=measure(op,request['Repeats']);stats.update(stage=stage,samples_per_second=len(x)/(stats['median_ms']/1000),symbols_per_second=len(r['eq'])/(stats['median_ms']/1000));rows.append(stats)
    return dict(language='python',input_samples=len(x),fft_points=request['FFTPoints'],mode=mode,analysis_symbols=len(r['eq']),rows=rows,worker_peak_working_set_bytes=peak_working_set(),memory_scope='worker lifetime peak including imports, prepared buffers, warmup and all stages')

def run(executable,output,repeats,sizes,modes,real_capture=False):
    env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',OMP_NUM_THREADS='1')
    results=[]
    for n in sizes:
        if real_capture:
            x=read_csv(ROOT/'data/qam64_20MSymPS_160MSPS_RRC0p25.csv',CSVConfig(sample_format='hex_q15',i_column='i',q_column='q')).samples
            assert n==len(x)==16384
        elif n==32768:
            values=np.loadtxt(ROOT/'data/generated/qam/Q13_32768_q15.csv',delimiter=',',skiprows=1)
            x=values[:,0]/32768+1j*values[:,1]/32768
        else: x,_,_=generate_signal(symbol_count=n//8,seed=21232768)
        for fft in ([32768,65536] if n==65536 else [n if n<=32768 else 32768]):
            for mode in modes:
                request=dict(Real=x.real.tolist(),Imag=x.imag.tolist(),Config=asdict(QAMConfig()),DCMode=mode,Repeats=repeats,FFTPoints=fft)
                payload=json.dumps(request,allow_nan=False)
                for language,command in [('python',[sys.executable,str(Path(__file__).resolve()),'--worker']),('go',[str(executable)])]:
                    p=subprocess.run(command,input=payload,text=True,capture_output=True,env=env)
                    if p.returncode: raise RuntimeError(f'{language} benchmark failed: {p.stderr}')
                    result=json.loads(p.stdout);result['input_complex128_sha256']=__import__('hashlib').sha256(x.astype('<c16').tobytes()).hexdigest();results.append(result)
                    output.parent.mkdir(parents=True,exist_ok=True)
                    report=dict(environment=dict(os=platform.platform(),python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,cpu=platform.processor(),logical_cpus=os.cpu_count()),repeats=repeats,seed=None if real_capture else 21232768,input_policy='unchanged 16384 real hex_q15 capture' if real_capture else 'synthetic qam_gen for length trends; 32768 uses decoded Q13 Q1.15 fixture',thread_environment=dict(OPENBLAS_NUM_THREADS=1,MKL_NUM_THREADS=1,OMP_NUM_THREADS=1),policy='Python one warmup; Go untimed batch calibration >=50ms, operations_per_repeat records batch size; p90 for Go short stages is per-batch average; startup, generation, CSV and JSON excluded; stage buffers prepared; Joint timing includes two sweeps; CFO one search; max 30000 analysis/12000 CFO symbols',measurements=results)
                    output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8');print(n,fft,mode,language,'complete',flush=True)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--worker',action='store_true');p.add_argument('--real-capture',action='store_true');p.add_argument('--repeats',type=int,default=3);p.add_argument('--sizes',type=int,nargs='+',default=[8192,16384,32768,65536,262144,1048576]);p.add_argument('--modes',nargs='+',default=['legacy_mean','decision_directed_joint']);p.add_argument('--executable',type=Path,default=ROOT/'.cache/v212/qambench.exe');p.add_argument('--output',type=Path,default=ROOT/'go/reports/v2.1.2_qam_benchmark.json');a=p.parse_args()
    if a.worker: print(json.dumps(python_worker(json.load(sys.stdin)),allow_nan=False))
    else:
        if a.repeats<3: p.error('repeats must be >=3')
        if a.real_capture:
            a.sizes=[16384]
            if a.output==ROOT/'go/reports/v2.1.2_qam_benchmark.json':a.output=ROOT/'go/reports/v2.1.2_real_benchmark.json'
        run(a.executable,a.output,a.repeats,a.sizes,a.modes,a.real_capture)
