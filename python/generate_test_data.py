"""Generate deterministic T01--T10 CSV fixtures (no network or plotting)."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FS = 160e6
SEED = 20261008


def generate(output_dir=None):
    destination = Path(output_dir) if output_dir is not None else ROOT / "data" / "generated"
    destination.mkdir(parents=True, exist_ok=True)
    n = np.arange(1024)

    def tone(frequency, amplitude=1.0, count=1024):
        return amplitude * np.exp(2j * np.pi * frequency * np.arange(count) / FS)

    rng = np.random.Generator(np.random.PCG64(SEED))
    noise = np.sqrt(0.04 / 2) * (rng.standard_normal(8192) + 1j * rng.standard_normal(8192))
    cases = [
        ("T01", "complex_positive_tone", tone(40e6), [40e6], [1.0], 1.0),
        ("T02", "complex_negative_tone", tone(-40e6), [-40e6], [1.0], 1.0),
        ("T03", "real_full_scale_sine", np.cos(2 * np.pi * 40e6 * n / FS), [40e6], [1.0], 0.5),
        ("T04", "complex_two_tones", tone(40e6, 0.75) + tone(-25e6, 0.25), [40e6, -25e6], [0.75, 0.25], 0.625),
        ("T05", "complex_white_noise", noise, [], [], 0.04),
        ("T06", "noncoherent_tone", tone(40e6 + FS / 1024 / 2, 0.8), [40e6 + FS / 1024 / 2], [0.8], 0.64),
        ("T07", "zero_iq", np.zeros(512, dtype=np.complex128), [], [], 0.0),
        ("T08", "iq_with_dc", tone(20e6, 0.5) + (0.25 + 0.125j), [0.0, 20e6], [float(abs(0.25 + 0.125j)), 0.5], 0.328125),
        ("T09", "q15_iq", tone(40e6, 0.8), [40e6], [0.8], 0.64),
        ("T10", "odd_non_power_two", tone(FS * 137 / 999, 0.6, 999), [FS * 137 / 999], [0.6], 0.36),
    ]
    records = []
    for case_id, description, samples, frequencies, amplitudes, theoretical_power in cases:
        is_iq = np.iscomplexobj(samples)
        values = np.column_stack((samples.real, samples.imag)) if is_iq else samples[:, None]
        sample_format = "float"
        if case_id == "T09":
            values = np.clip(np.rint(values * 32768), -32768, 32767).astype(np.int16)
            recovered = values[:, 0] / 32768.0 + 1j * values[:, 1] / 32768.0
            sample_format = "q15"
        else:
            recovered = samples
        path = destination / f"{case_id}_{description}.csv"
        np.savetxt(path, values, delimiter=",", header="i,q" if is_iq else "sample", comments="",
                   fmt="%d" if sample_format == "q15" else "%.17g")
        records.append({
            "id": case_id, "description": description, "csv": path.name,
            "sample_rate_hz": FS, "sample_count": len(samples), "sample_format": sample_format,
            "input_type": "complex" if is_iq else "real",
            "columns": ["i", "q"] if is_iq else ["sample"],
            "signal_frequency_hz": frequencies, "signal_amplitude": amplitudes,
            "expected_power": theoretical_power,
            "expected_power_kind": "ensemble mean" if case_id == "T05" else "analytic before quantization",
            "realized_mean_power": float(np.mean(np.abs(recovered)**2)),
            "random_seed": SEED if case_id == "T05" else None,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    manifest = {"schema_version": 1, "random_generator": "NumPy PCG64", "cases": records}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "generated")
    args = parser.parse_args()
    manifest = generate(args.output_dir)
    print(f"Generated {len(manifest['cases'])} CSV files and manifest in {args.output_dir.resolve()}")
