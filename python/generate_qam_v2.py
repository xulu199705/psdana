"""New receiver Golden version only; existing captures/vectors remain frozen."""

from dataclasses import asdict
import json
import os
from pathlib import Path

import numpy as np

from psd.csvio import CSVConfig,read_csv
from psd.qam import QAMConfig,analyze_qam
from psd.qam.receiver import JOINT_ALGORITHM_VERSION
from qam_gen import ROOT,OUTPUT,generate_signal,sha256

INPUTS = ROOT/"data/generated/qam/v2"
GOLDEN = ROOT/"data/golden/qam/v2"


def generate_v2():
    INPUTS.mkdir(parents=True,exist_ok=True)
    GOLDEN.mkdir(parents=True,exist_ok=True)
    manifest = json.loads((OUTPUT/"manifest.json").read_text(encoding="utf-8"))
    cases = [(v["id"],OUTPUT/v["input_file"],v["sample_format"],v["symbol_rate_hz"])
             for v in manifest["vectors"]]
    new_inputs = []
    for length in (256,512,1024,4096,16384):
        x,d,metadata = generate_signal(symbol_count=length,seed=12345)
        source = INPUTS/f"ideal_{length}.csv"
        truth = INPUTS/f"symbols_{length}.csv"
        for path,values in ((source,x),(truth,d)):
            np.savetxt(path,np.column_stack((values.real,values.imag)),delimiter=",",
                       header="i,q",comments="",fmt="%.17g")
        new_inputs.append(dict(input_file=source.name,input_sha256=sha256(source),
                               truth_file=truth.name,truth_sha256=sha256(truth),**metadata))
        cases.append((f"IDEAL_{length}",source,"float",20e6))
    (INPUTS/"manifest.json").write_text(json.dumps(dict(schema_version="1.0.0",vectors=new_inputs),indent=2,allow_nan=False)+"\n",encoding="utf-8")
    cases.append(("REAL64",ROOT/"data/qam64_20MSymPS_160MSPS_RRC0p25.csv","hex_q15",20e6))
    entries = []
    for identity,source,fmt,rate in cases:
        cfg = QAMConfig(symbol_rate_hz=rate,constellation_points=128)
        csv_cfg = CSVConfig(sample_format=fmt,i_column="i",q_column="q")
        x = read_csv(source,csv_cfg).samples
        result = analyze_qam(x,cfg,dc_mode="decision_directed_joint")
        vector = dict(schema_version="2.0.0",algorithm_version=JOINT_ALGORITHM_VERSION,
            id=identity,dc_mode="decision_directed_joint",qam_config=asdict(cfg),
            input_file=Path(os.path.relpath(source,GOLDEN)).as_posix(),input_sha256=sha256(source),
            sample_count=len(x),csv_config=asdict(csv_cfg),expected=result.to_dict(),
            tolerances=dict(metric_atol=1e-7,array_atol=1e-9,array_rtol=1e-9,
                            cfo_atol_hz=1e-9,timing_atol_symbols=1e-15,
                            scalar_atol=1e-10,scalar_rtol=1e-9))
        target = GOLDEN/f"{identity}.json"
        target.write_text(json.dumps(vector,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        entries.append(dict(id=identity,file=target.name,sha256=sha256(target)))
    index = dict(schema_version="2.0.0",algorithm_version=JOINT_ALGORITHM_VERSION,
                 vector_count=len(entries),input_path_base="vector_directory",vectors=entries)
    (GOLDEN/"index.json").write_text(json.dumps(index,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return index


if __name__ == "__main__":
    print(f"Generated {generate_v2()['vector_count']} Joint-fit receiver vectors")
