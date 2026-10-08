"""Explicit QAM Golden generation; never modifies PSD Golden or capture input."""

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path

from psd.csvio import CSVConfig, read_csv
from psd.qam import QAMConfig, analyze_qam
from psd.qam.receiver import ALGORITHM_VERSION
from qam_gen import ROOT, OUTPUT, sha256

GOLDEN = ROOT/"data/golden/qam"
ACTUAL = ROOT/"data/qam64_20MSymPS_160MSPS_RRC0p25.csv"


def generate_golden(output=GOLDEN, include_real=True):
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    manifest = json.loads((OUTPUT/"manifest.json").read_text(encoding="utf-8"))
    cases = [(v["id"], OUTPUT/v["input_file"],v["sample_format"],v["symbol_rate_hz"],v)
             for v in manifest["vectors"]]
    if include_real and ACTUAL.exists():
        cases.append(("REAL64",ACTUAL,"hex_q15",20e6,None))
    entries = []
    for identity,path,fmt,rate,injection in cases:
        cfg = QAMConfig(symbol_rate_hz=rate,constellation_points=128)
        x = read_csv(path,CSVConfig(sample_format=fmt,i_column="i",q_column="q")).samples
        result = analyze_qam(x,cfg)
        vector = dict(schema_version="1.0.0",algorithm_version=ALGORITHM_VERSION,id=identity,
            input_file=Path(os.path.relpath(path,output)).as_posix(),input_sha256=sha256(path),
            sample_format=fmt,sample_count=len(x),csv_config=dict(sample_format=fmt,i_column="i",q_column="q"),
            qam_config=asdict(cfg),expected=result.to_dict(),
            tolerances=dict(metric_atol=1e-7,array_atol=1e-10,array_rtol=1e-10,
                            cfo_atol_hz=1e-9,timing_atol_symbols=1e-15),
            injection=injection)
        target = output/f"{identity}.json"
        target.write_text(json.dumps(vector,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        entries.append(dict(id=identity,file=target.name,sha256=sha256(target)))
    index = dict(schema_version="1.0.0",algorithm_version=ALGORITHM_VERSION,vector_count=len(entries),
                 input_path_base="vector_directory",nonfinite_policy="reject; unestimated CFO uses null",vectors=entries)
    (output/"index.json").write_text(json.dumps(index,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return index


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=GOLDEN)
    parser.add_argument("--synthetic-only",action="store_true")
    args = parser.parse_args()
    index = generate_golden(args.output, not args.synthetic_only)
    print(f"Generated {index['vector_count']} QAM Golden vectors")
