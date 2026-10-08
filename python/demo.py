"""CLI PSD example; defaults to the original hexadecimal Q/I capture."""

import argparse
from pathlib import Path

import numpy as np

from psd import PSDConfig, compute_psd
from psd.csvio import CSVConfig, read_csv

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "sine_+40MHz_160MSPS.csv"


def fft_points(value):
    if value == "all":
        return value
    try:
        points = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("fft-points must be all or a positive integer") from exc
    if points < 1:
        raise argparse.ArgumentTypeError("fft-points must be positive")
    return points


def column(value):
    return int(value) if value.isdecimal() else value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--fs", type=float, default=160e6)
    parser.add_argument("--window", choices=["hann", "rectangle"], default="hann")
    parser.add_argument("--fft-points", type=fft_points, default="all")
    parser.add_argument("--overlap", type=float, default=0.5)
    parser.add_argument("--detrend", choices=["none", "mean"], default="none")
    parser.add_argument("--display", choices=["dbfs", "dbfs_per_hz"], default="dbfs")
    parser.add_argument("--no-show", action="store_true")
    parser.add_argument("--sample-format", choices=["float", "q15", "hex_q15"])
    parser.add_argument("--input-type", choices=["auto", "real", "iq"], default="auto")
    parser.add_argument("--header", choices=["auto", "yes", "no"], default="auto")
    parser.add_argument("--delimiter")
    parser.add_argument("--real-column", type=column)
    parser.add_argument("--i-column", type=column)
    parser.add_argument("--q-column", type=column)
    args = parser.parse_args(argv)
    # Relative paths are relative to the project root, independent of process cwd.
    path = args.input if args.input.is_absolute() else ROOT / args.input
    sample_format = args.sample_format or ("hex_q15" if path.resolve() == DEFAULT_INPUT else "float")
    try:
        capture = read_csv(path, CSVConfig(
            sample_format=sample_format, input_type=args.input_type, header=args.header,
            delimiter=args.delimiter, real_column=args.real_column,
            i_column=args.i_column, q_column=args.q_column,
        ))
        result = compute_psd(capture.samples, PSDConfig(args.fs, args.window, args.fft_points, args.overlap, args.detrend))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    peak = int(np.argmax(result.psd_linear))
    print(f"Input: {capture.path}\nSamples: {capture.sample_count}; format: {capture.sample_format}; "
          f"columns: {capture.columns}; type: {result.input_type}")
    print(f"Method: {result.method}; FFT: {result.fft_size}; window: {result.window}; "
          f"segments: {result.segment_count}; overlap samples: {result.overlap_samples}; hop: {result.hop_size}")
    print(f"df: {result.frequency_resolution_hz:.9g} Hz; ENBW: {result.enbw_hz:.9g} Hz; "
          f"coherent gain: {result.coherent_gain:.9g}; tail discarded: {result.discarded_tail_samples}")
    print(f"Peak: {result.frequency_hz[peak]:.9g} Hz; {result.rbw_power_dbfs[peak]:.9f} dBFS; "
          f"{result.psd_dbfs_per_hz[peak]:.9f} dBFS/Hz")
    print(f"Integrated power: {result.integrated_power:.12g}; P_FS: {result.reference_power}")
    from psd.plotting import plot_psd
    plot_psd(result, display=args.display, show=not args.no_show)
    return result


if __name__ == "__main__":
    main()
