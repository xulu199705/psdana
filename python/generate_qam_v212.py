"""Add only the versioned V2.1.2 Q1.15 fixture and Python Golden."""
from dataclasses import asdict
import json
import numpy as np
from qam_gen import ROOT, OUTPUT, generate_signal, quantize_q15, sha256
from psd.qam import QAMConfig, analyze_qam

def generate():
    x, truth, meta = generate_signal(symbol_count=4096, seed=21232768,
        cfo_hz=1000, noise_evm_pct=2, timing_offset_samples=0.5,
        phase_deg=23, dc=0.01+0.005j)
    values, quant = quantize_q15(x, full_scale=32768)
    source, tx = OUTPUT/'Q13_32768_q15.csv', OUTPUT/'Q13_32768_symbols.csv'
    OUTPUT.mkdir(parents=True, exist_ok=True)
    np.savetxt(source, values, delimiter=',', header='i,q', comments='', fmt='%d')
    np.savetxt(tx, np.column_stack((truth.real,truth.imag)), delimiter=',',
               header='i,q', comments='', fmt='%.17g')
    meta.update(quant, id='Q13_32768', input_file=source.name,
        sample_format='q15', input_sha256=sha256(source), truth_file=tx.name,
        truth_sha256=sha256(tx), provenance='synthetic qam_gen; never hardware capture')
    (OUTPUT/'manifest_v2.1.2.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf-8')
    decoded = values[:,0].astype(float)/32768+1j*values[:,1].astype(float)/32768
    dest=ROOT/'data/golden/qam/v2.1.2';dest.mkdir(parents=True,exist_ok=True)
    entries=[]
    for mode in ('legacy_mean','decision_directed_joint'):
        config=QAMConfig(constellation_points=128)
        v=dict(schema_version='2.1.2',id='Q13_32768_'+mode,dc_mode=mode,
            input_file='../../../generated/qam/'+source.name,input_sha256=sha256(source),
            sample_format='q15',sample_count=len(decoded),qam_config=asdict(config),
            expected=analyze_qam(decoded,config,dc_mode=mode).to_dict(),
            tolerances=dict(metric_atol=1e-7,array_atol=1e-9,array_rtol=1e-9,
                            cfo_atol_hz=1e-9,timing_atol_symbols=1e-15))
        target=dest/(mode+'.json');target.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        entries.append(dict(id=v['id'],file=target.name,sha256=sha256(target)))
    (dest/'index.json').write_text(json.dumps(dict(schema_version='2.1.2',vector_count=2,vectors=entries),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(meta,indent=2))

if __name__=='__main__': generate()
