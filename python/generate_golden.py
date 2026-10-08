"""Export bounded, standard JSON vectors from already-generated CSV fixtures."""

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from psd import PSDConfig, compute_psd
from psd.csvio import CSVConfig, read_csv

ROOT = Path(__file__).resolve().parents[1]
TOLERANCES = {
    "frequency_hz": {"rtol": 1e-12, "atol": 1e-7},
    "psd_linear": {"rtol": 2e-11, "atol": 1e-20},
    "db_values": {"atol_db": 1e-7, "compare_only_when_expected_psd_linear_gt": 1e-20},
    "scalar_metadata": {"rtol": 2e-12, "atol": 1e-12},
    "integer_and_string_metadata": "exact",
}


def json_array(values):
    """The only permitted nonfinite output is -inf dB, encoded as JSON null."""
    if np.any(np.isnan(values)) or np.any(np.isposinf(values)):
        raise ValueError("NaN/+Inf cannot be exported in a Golden vector")
    return [float(v) if np.isfinite(v) else None for v in values]


def generate(output_dir=None):
    destination = Path(output_dir) if output_dir is not None else ROOT / "data" / "golden"
    destination.mkdir(parents=True, exist_ok=True)
    fixtures = ROOT / "data" / "generated"
    manifest_path = fixtures / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Run generate_test_data.py before generate_golden.py")
    records = {r["id"]: r for r in json.loads(manifest_path.read_text(encoding="utf-8"))["cases"]}
    configurations = [
        ("T01", "hann_all", PSDConfig()),
        ("T01", "rectangle_all", PSDConfig(window="rectangle")),
        ("T02", "hann_all", PSDConfig()),
        ("T03", "hann_all", PSDConfig()),
        ("T03", "rectangle_all", PSDConfig(window="rectangle")),
        ("T03", "hann_welch255", PSDConfig(fft_points=255)),
        ("T04", "hann_welch256", PSDConfig(fft_points=256)),
        ("T05", "hann_welch255", PSDConfig(fft_points=255)),
        ("T05", "rectangle_welch256", PSDConfig(window="rectangle", fft_points=256)),
        ("T06", "hann_all", PSDConfig()),
        ("T06", "rectangle_all", PSDConfig(window="rectangle")),
        ("T07", "rectangle_all", PSDConfig(window="rectangle")),
        ("T08", "hann_welch256", PSDConfig(fft_points=256)),
        ("T08", "hann_welch256_mean", PSDConfig(fft_points=256, detrend="mean")),
        ("T09", "hann_welch256", PSDConfig(fft_points=256)),
        ("T10", "hann_all", PSDConfig()),
        ("T10", "hann_welch333", PSDConfig(fft_points=333)),
    ]
    vectors = []
    for case_id, suffix, config in configurations:
        record = records[case_id]
        source = fixtures / record["csv"]
        csv_config = CSVConfig(sample_format=record["sample_format"])
        result = compute_psd(read_csv(source, csv_config).samples, config)
        expected = {}
        for key, value in asdict(result).items():
            expected[key] = json_array(value) if isinstance(value, np.ndarray) else value
        expected["integrated_power"] = result.integrated_power
        payload = {
            "schema_version": 1, "algorithm_version": "psd-python-phase1-v1",
            "id": f"{case_id}_{suffix}",
            "input": {
                "csv_relative_to_vector": Path(os.path.relpath(source, destination)).as_posix(),
                "sha256": record["sha256"], "csv_config": asdict(csv_config),
                "sample_count": record["sample_count"],
                "complex_encoding": "CSV columns i=real, q=imag; x=i+j*q" if record["input_type"] == "complex" else None,
                "description": record,
            },
            "psd_config": asdict(config),
            "full_scale": {
                "complex": "unit-magnitude complex tone, P_FS=1",
                "real": "unit-peak real sinusoid, P_FS=0.5",
                "reference_power": result.reference_power,
                "q15_conversion": "signed int16 / 32768; never normalize by input peak",
            },
            "algorithm": {
                "fft": "unnormalized forward FFT, exp(-j*2*pi*k*n/N)",
                "window": "hann: 0.5-0.5*cos(2*pi*n/N); rectangle: 1",
                "density": "abs(FFT(x*w))^2 / (fs*sum(w^2)); detrend before window",
                "welch": "overlap_samples=floor(N*overlap); linear arithmetic mean; discard incomplete tail",
                "sidedness": "complex: fftshift two-sided; real: one-sided, double interior bins only",
                "integration": "sum(psd_linear)*fs/N, NOT sum(ENBW-calibrated bins)",
            },
            "units": {"frequency_hz": "Hz", "psd_linear": "normalized input-unit squared/Hz (absolute)",
                      "psd_dbfs_per_hz": "dBFS/Hz", "rbw_power_dbfs": "dBFS", "enbw_hz": "Hz"},
            "nonfinite_policy": "null in dB arrays means negative infinity (zero PSD). Linear PSD/frequency are finite. NaN/+Inf forbidden.",
            "tolerances": TOLERANCES, "expected": expected,
        }
        path = destination / f"{payload['id']}.json"
        path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        vectors.append({"id": payload["id"], "file": path.name,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    index = {"schema_version": 1, "vector_count": len(vectors), "vectors": vectors}
    (destination / "index.json").write_text(json.dumps(index, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return index


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "golden")
    args = parser.parse_args()
    index = generate(args.output_dir)
    print(f"Exported {index['vector_count']} Golden vectors and index in {args.output_dir.resolve()}")
