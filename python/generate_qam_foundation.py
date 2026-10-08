"""Portable primitive vectors, separate from both receiver Golden indexes."""

import json
from pathlib import Path
import numpy as np
from psd.qam import qam_constellation, qam_slicer, rrc_taps, scalar_qam_fit, qam_error_metrics
from qam_gen import ROOT, sha256


def split(z):
    values = np.asarray(z)
    if values.ndim == 0:
        return dict(real=float(values.real),imag=float(values.imag))
    return dict(real=values.real.tolist(),imag=values.imag.tolist())


def generate(output=ROOT/"data/golden/qam/v2/foundation"):
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    entries = []
    def save(identity,kind,args,expected):
        vector = dict(schema_version="1.0.0",id=identity,kind=kind,
            complex_encoding="real_imag_parallel_arrays_or_scalar_fields",arguments=args,expected=expected,
            tolerances=dict(atol=1e-10,rtol=1e-10,metric_atol=1e-8))
        path = output/f"{identity}.json"
        path.write_text(json.dumps(vector,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        entries.append(dict(id=identity,file=path.name,sha256=sha256(path)))
    for order in (16,64,256):
        points = qam_constellation(order)
        save(f"constellation_{order}","constellation",dict(order=order),split(points))
        inputs = np.concatenate((points,points+.002+.003j,points[::3]*1j))
        decisions,indices = qam_slicer(inputs,order)
        save(f"slicer_{order}","slicer",dict(order=order,samples=split(inputs)),
            dict(decisions=split(decisions),indices=indices.tolist()))
        save(f"metrics_{order}","metrics",dict(samples=split(points*(1.03+.04j)),decisions=split(points)),
            qam_error_metrics(points*(1.03+.04j),points))
        rng = np.random.default_rng(421+order)
        d = points[rng.integers(0,order,512)]
        for label,z in (("ideal",d),("dc_gain",.7*np.exp(.3j)*d+.02-.015j),
                        ("awgn",d+.01*(rng.normal(size=512)+1j*rng.normal(size=512)))):
            for mode in ("legacy_mean","decision_directed_joint"):
                fit = scalar_qam_fit(z,order,5,dc_mode=mode)
                expected = {k:split(v) if k in ("eq","decisions","dc","complex_gain","forward_gain")
                            else v.tolist() if isinstance(v,np.ndarray) else v for k,v in fit.items()}
                save(f"scalar_{order}_{label}_{mode}","scalar",
                    dict(order=order,iterations=5,dc_mode=mode,samples=split(z)),expected)
    for beta in (0,.25,1):
        for span,sps in ((10,2),(10,8),(3,3)):
            save(f"rrc_{beta}_{span}_{sps}","rrc",dict(beta=beta,span_symbols=span,sps=sps),
                dict(taps=rrc_taps(beta,span,sps).tolist()))
    index = dict(schema_version="1.0.0",vector_count=len(entries),vectors=entries,
        comparison_rules="No extra LS fit; scalar coordinates compared directly, modulo-90 alignment only if explicitly required. Zero/disabled values never become NaN/Infinity.")
    (output/"index.json").write_text(json.dumps(index,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return index


if __name__ == "__main__":
    print(f"Generated {generate()['vector_count']} QAM foundation vectors")
