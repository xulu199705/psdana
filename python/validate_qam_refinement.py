"""Reproducible DC/CFO/false-candidate matrices; input generation is in memory."""

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from psd.csvio import read_csv, CSVConfig
from psd.qam import QAMConfig, scalar_qam_fit, analyze_qam, QAMRecoveryError
from psd.qam.receiver import _synchronize
from qam_gen import generate_signal, ROOT
from qam_joint_reference import data_aided_scalar_reference

MODES = ("legacy_mean","decision_directed_joint")


def inspect_signal(x,d,config,true_cfo=0,true_delay=0):
    rows = []
    for mode in MODES:
        r = _synchronize(x,config,mode)
        ref = data_aided_scalar_reference(r,d,config.symbol_rate_hz,true_cfo)
        error = abs(r["cfo_hz"]-true_cfo) if r["cfo_hz"] is not None else None
        phase = r["timing_phase_up"]/(config.samples_per_symbol*config.timing_interp)
        phase_error = abs((phase-true_delay/config.samples_per_symbol+.5)%1-.5)
        before = scalar_qam_fit(r["symbols_raw"],config.qam_order,config.scalar_fit_iterations,dc_mode=mode)
        row = dict(mode=mode,evm_pct=r["evm_pct"],data_aided_evm_pct=ref["evm_pct_rms"],
            same_output_data_aided_evm_pct=ref["comparison"]["evm_pct_rms"],
            zero_dc_reference_evm_pct=ref["zero_dc_scalar_evm_pct_rms"],
            blind_truth_metric_error_pct=abs(r["evm_pct"]-ref["comparison"]["evm_pct_rms"]),
            decision_errors=ref["comparison"]["decision_mismatch_count"],
            dc_abs_error_to_reference=float(abs(r["dc"]-ref["dc"])),
            gain_relative_error_to_reference=float(abs(r["complex_gain"]/ref["complex_gain"]-1)),
            gain_phase_error_deg=float(np.degrees(np.angle(r["complex_gain"]/ref["complex_gain"]))),
            dc_real=float(r["dc"].real),dc_imag=float(r["dc"].imag),
            estimated_cfo_hz=r["cfo_hz"],cfo_error_hz=error,
            cfo_grid_resolution_hz=r["cfo_grid_resolution_hz"],cfo_uncertainty_hz=None,
            boundary_hit=bool(r["cfo_boundary_hit"]),evm_before_cfo_pct=before["evm_pct"],
            timing_offset_symbols=phase,timing_error_symbols=phase_error,
            joint_converged=r.get("joint_fit_converged"),valid_symbols=len(r["eq"]),
            accepted_by_default_gate=bool(r["evm_pct"]<=config.max_decision_evm_pct and np.unique(r["indices"]).size>=8))
        rows.append(row)
    return rows


def write_rows(path,rows):
    with Path(path).open("w",encoding="utf-8",newline="") as stream:
        writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_validation(output):
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    cases = [("ideal",{}),("dc",dict(dc=.02-.015j)),
        ("complex_gain",dict(gain=.65,phase_deg=31)),("awgn",dict(noise_evm_pct=4)),
        ("cfo",dict(cfo_hz=1000)),("iq_imbalance",dict(iq_imbalance=.04)),
        ("combined",dict(noise_evm_pct=4,cfo_hz=1000,gain=.8,phase_deg=23,dc=.01+.005j,timing_offset_samples=.5))]
    dc_rows = []
    for length in (256,512,1024,2048,4096,16384):
        for label,options in cases:
            x,d,_ = generate_signal(symbol_count=length,seed=12345,**options)
            for row in inspect_signal(x,d,QAMConfig(),options.get("cfo_hz",0),options.get("timing_offset_samples",0)):
                dc_rows.append(dict(symbol_count=length,input=label,**row))
        print(f"DC matrix {length} symbols completed",flush=True)
    write_rows(output/"v2.1.1_dc_matrix.csv",dc_rows)
    cfo_rows = []
    for length in (256,2048,16384):
        for noise in (0,4):
            for f in (0,-100,100,-1000,1000,-3000,3000,-4995,4995,-6000,6000):
                x,d,_ = generate_signal(symbol_count=length,seed=12345,cfo_hz=f,noise_evm_pct=noise)
                for row in inspect_signal(x,d,QAMConfig(),f):
                    cfo_rows.append(dict(symbol_count=length,noise_evm_pct=noise,true_cfo_hz=f,**row))
            print(f"CFO matrix {length} symbols / noise {noise}% completed",flush=True)
    write_rows(output/"v2.1.1_cfo_matrix.csv",cfo_rows)
    rng = np.random.default_rng(4242)
    count = 16384
    tone = np.exp(2j*np.pi*np.arange(count)/8)
    qam,_,_ = generate_signal(seed=12345)
    random_phase = np.exp(1j*rng.uniform(-np.pi,np.pi,count))
    negatives = [("pure_awgn",rng.normal(size=count)+1j*rng.normal(size=count),QAMConfig()),
        ("single_tone",tone,QAMConfig()),("two_tones",tone+.4*tone.conj(),QAMConfig()),
        ("random_phase",random_phase,QAMConfig()),("wrong_rate",qam,QAMConfig(symbol_rate_hz=40e6)),
        ("wrong_rrc",qam,QAMConfig(rrc_beta=1)),
        ("low_snr",generate_signal(noise_evm_pct=70)[0],QAMConfig()),
        ("sample_order",qam.reshape(-1,2)[:,::-1].ravel(),QAMConfig()),
        ("swapped_iq",qam.imag+1j*qam.real,QAMConfig()),
        ("wrong_q_polarity",qam,QAMConfig(q_sign=-1)),
        ("out_of_range_cfo",generate_signal(cfo_hz=6000)[0],QAMConfig())]
    negative_rows = []
    for label,x,cfg in negatives:
        for mode in MODES:
            try:
                r = analyze_qam(x,cfg,dc_mode=mode)
                row = dict(input=label,mode=mode,accepted=True,status=r.diagnostics["status"],
                    evm_pct=r.evm_pct_rms,cfo_hz=r.frequency_error_hz,timing=r.timing_offset_symbols,
                    explanation="candidate is not a proof of correct modulation/polarity")
            except ValueError as exc:
                diagnostics = getattr(exc,"diagnostics",{})
                row = dict(input=label,mode=mode,accepted=False,status="unreliable",
                    evm_pct=diagnostics.get("evm_pct_rms"),cfo_hz=diagnostics.get("frequency_error_hz"),
                    timing=diagnostics.get("timing_offset_symbols"),explanation=str(exc))
            negative_rows.append(row)
    write_rows(output/"v2.1.1_reliability_matrix.csv",negative_rows)
    real = read_csv(ROOT/"data/qam64_20MSymPS_160MSPS_RRC0p25.csv",CSVConfig(sample_format="hex_q15")).samples
    actual = {mode:analyze_qam(real,dc_mode=mode).to_dict() for mode in MODES}
    summary = dict(dc_rows=len(dc_rows),cfo_rows=len(cfo_rows),reliability_rows=len(negative_rows),real=actual,
        diagnostic_policy="failed fits kept by private bounded synchronization only; acceptance uses unchanged default gate")
    (output/"v2.1.1_measurements.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"python/reports")
    run_validation(parser.parse_args().output)
