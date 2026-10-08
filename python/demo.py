"""CLI PSD example; defaults to the original hexadecimal Q/I capture."""

import argparse
from pathlib import Path

import numpy as np

from psd import PSDConfig
from psd.csvio import CSVConfig, read_csv
from psd.analysis import analyze_iq

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
    parser.add_argument("--freq-left", type=float, help="band left boundary in Hz; requires --freq-right")
    parser.add_argument("--freq-right", type=float, help="band right boundary in Hz; requires --freq-left")
    parser.add_argument("--sample-format", choices=["float", "q15", "hex_q15"])
    parser.add_argument("--input-type", choices=["auto", "real", "iq"], default="auto")
    parser.add_argument("--header", choices=["auto", "yes", "no"], default="auto")
    parser.add_argument("--delimiter")
    parser.add_argument("--real-column", type=column)
    parser.add_argument("--i-column", type=column)
    parser.add_argument("--q-column", type=column)
    parser.add_argument("--qam", action="store_true", help="enable Python-only blind QAM receiver")
    parser.add_argument("--qam-order", type=int, default=64)
    parser.add_argument("--symbol-rate", type=float, default=20e6)
    parser.add_argument("--rrc-beta", type=float, default=0.25)
    parser.add_argument("--rrc-span", type=int, default=10)
    parser.add_argument("--timing-interp", type=int, default=16)
    parser.add_argument("--max-cfo", type=float, default=5000)
    parser.add_argument("--max-analysis-symbols", type=int, default=30000)
    parser.add_argument("--constellation-points", type=int, default=5000)
    parser.add_argument("--no-cfo-correction", action="store_true")
    parser.add_argument("--q-sign", type=int, choices=[-1,1], default=1)
    args = parser.parse_args(argv)
    if (args.freq_left is None) != (args.freq_right is None):
        parser.error("freq-left and freq-right must be provided together")
    # Relative paths are relative to the project root, independent of process cwd.
    path = args.input if args.input.is_absolute() else ROOT / args.input
    sample_format = args.sample_format or ("hex_q15" if path.resolve() == DEFAULT_INPUT else "float")
    try:
        capture = read_csv(path, CSVConfig(
            sample_format=sample_format, input_type=args.input_type, header=args.header,
            delimiter=args.delimiter, real_column=args.real_column,
            i_column=args.i_column, q_column=args.q_column,
        ))
        qam_config = None
        if args.qam:
            from psd.qam import QAMConfig
            qam_config = QAMConfig(sample_rate_hz=args.fs, symbol_rate_hz=args.symbol_rate,
                qam_order=args.qam_order, rrc_beta=args.rrc_beta, rrc_span_symbols=args.rrc_span,
                timing_interp=args.timing_interp, max_residual_cfo_hz=args.max_cfo,
                max_analysis_symbols=args.max_analysis_symbols, constellation_points=args.constellation_points,
                enable_cfo_correction=not args.no_cfo_correction, q_sign=args.q_sign)
        analysis = analyze_iq(capture.samples,
            PSDConfig(args.fs, args.window, args.fft_points, args.overlap, args.detrend),
            qam_config, (args.freq_left,args.freq_right) if args.freq_left is not None else None)
        result, metrics = analysis.psd, analysis.power_metrics
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    peak = int(np.argmax(result.psd_linear))
    print(f"Input: {capture.path}\nSamples: {capture.sample_count}; format: {capture.sample_format}; "
          f"columns: {capture.columns}; type: {result.input_type}")
    print(f"Method: {result.method}; FFT: {result.fft_size}; window: {result.window}; "
          f"segments: {result.segment_count}; overlap samples: {result.overlap_samples}; hop: {result.hop_size}")
    print(f"df: {result.frequency_resolution_hz:.9g} Hz; ENBW: {result.enbw_hz:.9g} Hz; "
          f"coherent gain: {result.coherent_gain:.9g}; tail discarded: {result.discarded_tail_samples}")
    frequency = f"{result.frequency_hz[peak]:.9g} Hz" if result.psd_linear[peak] > 0 else "N/A"
    print(f"Peak: {frequency}; {result.rbw_power_dbfs[peak]:.9f} dBFS; "
          f"{result.psd_dbfs_per_hz[peak]:.9f} dBFS/Hz")
    print(f"Integrated power: {result.integrated_power:.12g}; P_FS: {result.reference_power}")
    if metrics is not None:
        frequency = f"{metrics.peak_frequency_hz:.9g} Hz" if metrics.peak_frequency_hz is not None else "N/A"
        end = "]" if metrics.is_point else ")"
        print(f"Frequency Range: [{metrics.freq_left_hz:.9g}, {metrics.freq_right_hz:.9g}{end} Hz; point={metrics.is_point}")
        print(f"Band Peak Frequency: {frequency}; Peak Power (dBFS): {metrics.peak_power_dbfs:.9f}; "
              f"Average Power (dBFS): {metrics.average_power_dbfs:.9f}")
    from psd.plotting import plot_psd
    if analysis.qam_metrics is None:
        plot_psd(result, display=args.display, show=not args.no_show)
    else:
        qam = analysis.qam_metrics
        cfo = "not estimated" if qam.frequency_error_hz is None else f"{qam.frequency_error_hz:.9g} Hz"
        print(f"QAM: {qam.qam_order}; EVM: {qam.evm_pct_rms:.9f}% RMS; "
              f"Amplitude Error: {qam.amplitude_error_pct_rms:.9f}% RMS; "
              f"Phase Error: {qam.phase_error_pct_rms:.9f}% RMS; "
              f"Phase angle: {qam.phase_error_deg_rms:.9f} deg RMS")
        print(f"Frequency Error: {cfo}; timing: {qam.timing_offset_symbols:.9g} symbol; "
              f"valid symbols: {qam.recovered_symbol_count}; status: {qam.diagnostics['status']}")
        for warning in qam.diagnostics["warnings"]:
            print(f"QAM warning: {warning}")
        from psd.qam.plotting import plot_constellation
        plot_psd(result, display=args.display, show=False)
        plot_constellation(qam, show=False)
        if not args.no_show:
            import matplotlib.pyplot as plt
            plt.show()
    return result


if __name__ == "__main__":
    main()
