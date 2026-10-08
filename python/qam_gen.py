"""Deterministic periodic QAM fixtures, independent of receiver synchronization."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import signal

from psd.qam import qam_constellation, rrc_taps
from psd.qam.config import positive_int, finite_real
from psd.qam.constellation import complex_vector

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/generated/qam"


def generate_signal(symbol_count=2048, seed=12345, sps=8, symbol_rate_hz=20e6,
                    beta=0.25, span=10, order=64, power=0.06, noise_evm_pct=0,
                    cfo_hz=0, phase_deg=0, gain=1, dc=0j, iq_imbalance=0,
                    timing_offset_samples=0):
    """Return waveform, unmodified TX truth and exact injection metadata.

    Timing offset is a periodic delay: positive delay requires a later RX phase.
    AWGN variance is noise_evm_pct^2/10000 times clean waveform mean power.
    Unit-energy matched filtering makes this an approximate symbol EVM target,
    not an assertion that finite-filter blind EVM equals the injection exactly.
    """
    positive_int(symbol_count,"symbol_count",32)
    positive_int(sps,"sps",2)
    for name,value in (("gain",gain),("power",power),("symbol_rate_hz",symbol_rate_hz)):
        finite_real(value,name,strict=True)
    finite_real(noise_evm_pct,"noise_evm_pct")
    if not all(np.isfinite(v) for v in (cfo_hz,phase_deg,dc,iq_imbalance,timing_offset_samples)):
        raise ValueError("all injected impairments must be finite")
    rng = np.random.default_rng(seed)
    points = qam_constellation(order)
    truth = points[rng.integers(0, order, symbol_count)]
    taps = rrc_taps(beta, span, sps)
    up = np.zeros(3*symbol_count*sps, dtype=complex)
    up[::sps] = np.tile(truth, 3)
    shaped = signal.convolve(up, taps, mode="full", method="direct")
    start = symbol_count*sps+(len(taps)-1)//2
    x = shaped[start:start+symbol_count*sps].copy()
    x *= np.sqrt(power/np.mean(abs(x)**2))
    if timing_offset_samples:
        freq = np.fft.fftfreq(len(x))
        x = np.fft.ifft(np.fft.fft(x)*np.exp(-2j*np.pi*freq*timing_offset_samples))
    x *= gain*np.exp(1j*np.deg2rad(phase_deg))
    x = x.real*(1+iq_imbalance)+1j*x.imag*(1-iq_imbalance)
    x *= np.exp(2j*np.pi*cfo_hz*np.arange(len(x))/(sps*symbol_rate_hz))
    noise_power = np.mean(abs(x)**2)*(noise_evm_pct/100)**2
    x += np.sqrt(noise_power/2)*(rng.standard_normal(len(x))+1j*rng.standard_normal(len(x)))
    x += dc
    if not np.all(np.isfinite(x)):
        raise ValueError("generated signal exceeds supported numeric range")
    meta = dict(seed=seed, symbol_count=symbol_count, sample_count=len(x),
                sample_rate_hz=sps*symbol_rate_hz, symbol_rate_hz=symbol_rate_hz,
                samples_per_symbol=sps, qam_order=order, rrc_beta=beta,
                rrc_span_symbols=span, target_clean_sample_power=power,
                noise_evm_pct=noise_evm_pct, noise_power=noise_power,
                cfo_hz=cfo_hz, phase_deg=phase_deg, gain=gain,
                dc_offset=dict(real=float(np.real(dc)), imag=float(np.imag(dc))),
                iq_gain_imbalance=iq_imbalance, timing_offset_samples=timing_offset_samples,
                float_sample_power=float(np.mean(abs(x)**2)),
                boundary_rule="three periods; center period after TX group-delay compensation")
    return x, truth, meta


def quantize_q15(samples, full_scale=32767):
    """Legacy generator factor 32767; receiver always divides by 32768."""
    samples = complex_vector(samples)
    finite_real(full_scale,"full_scale",strict=True)
    components = np.column_stack((samples.real, samples.imag))
    rounded = np.rint(components*full_scale)
    clipped = int(np.count_nonzero((rounded < -32768)|(rounded > 32767)))
    values = np.clip(rounded, -32768, 32767).astype(np.int16)
    decoded = values[:, 0].astype(float)/32768+1j*values[:, 1].astype(float)/32768
    return values, dict(quantizer_multiplier=full_scale, decoder_divisor=32768,
                        clipped_component_count=clipped,
                        quantized_sample_power=float(np.mean(abs(decoded)**2)))


def write_packed64(path, values):
    """One 64-bit HEX row: older I/Q in low word, newer I/Q in high word."""
    values = np.asarray(values)
    if (values.ndim != 2 or values.shape[1] != 2 or not len(values)
            or values.dtype.kind not in "iu" or np.any(values < -32768) or np.any(values > 32767)):
        raise ValueError("packed64 requires a nonempty N-by-2 signed int16 value array")
    if len(values)%2:
        raise ValueError("packed64 output requires an even sample count; no padding")
    words = values.astype(np.uint16).astype(np.uint64)
    iq = words[:, 0] | (words[:, 1] << np.uint64(16))
    packed = iq[::2] | (iq[1::2] << np.uint64(32))
    Path(path).write_text("packed_iq\n"+"".join(f"{int(v):016X}\n" for v in packed), encoding="utf-8")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def generate_all(output=OUTPUT):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    cases = [
        ("Q01", "ideal", {}), ("Q02", "awgn", dict(noise_evm_pct=2.5)),
        ("Q03", "positive_cfo", dict(cfo_hz=1000)),
        ("Q04", "negative_cfo", dict(cfo_hz=-3000)),
        ("Q05", "fixed_phase", dict(phase_deg=31)),
        ("Q06", "gain", dict(gain=0.65)),
        ("Q07", "iq_imbalance", dict(iq_imbalance=0.04)),
        ("Q08", "dc", dict(dc=0.015-0.012j)),
        ("Q09", "combined", dict(noise_evm_pct=2, cfo_hz=1000, phase_deg=23,
                                  gain=0.8, dc=0.01+0.005j, timing_offset_samples=0.5)),
        ("Q10", "q15", {}),
        ("Q11", "sps2", dict(sps=2, symbol_rate_hz=80e6, symbol_count=3072)),
        ("Q12", "sps8_timing", dict(timing_offset_samples=1.5, symbol_count=3072)),
    ]
    vectors = []
    for index, (identity, name, options) in enumerate(cases):
        x, truth, meta = generate_signal(seed=12345+index, **options)
        csv_path = output/f"{identity}_{name}.csv"
        truth_path = output/f"{identity}_symbols.csv"
        fmt = "q15" if identity == "Q10" else "float"
        values = np.column_stack((x.real,x.imag))
        if fmt == "q15":
            values, quantization = quantize_q15(x)
            meta.update(quantization)
            packed_path = output/f"{identity}_packed64.csv"
            write_packed64(packed_path, values)
            meta.update(packed_file=packed_path.name, packed_sha256=sha256(packed_path))
        np.savetxt(csv_path, values, delimiter=",", header="i,q", comments="",
                   fmt="%d" if fmt == "q15" else "%.17g")
        np.savetxt(truth_path, np.column_stack((truth.real,truth.imag)), delimiter=",",
                   header="i,q", comments="", fmt="%.17g")
        vectors.append(dict(id=identity, input_file=csv_path.name,
                            input_sha256=sha256(csv_path), sample_format=fmt,
                            truth_file=truth_path.name, truth_sha256=sha256(truth_path), **meta))
    manifest = dict(schema_version="1.0.0", generator_version="qam-periodic-1",
                    vector_count=len(vectors), vectors=vectors)
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    manifest = generate_all(parser.parse_args().output)
    print(f"Generated {manifest['vector_count']} QAM cases")
