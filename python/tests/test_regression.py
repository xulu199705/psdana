import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from generate_test_data import generate
from psd import PSDConfig, compute_psd
from psd.csvio import CSVConfig, read_csv

ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "data" / "generated"
ORIGINAL = ROOT / "data" / "sine_+40MHz_160MSPS.csv"
ORIGINAL_SHA256 = "ee2623352aefad86b4c28872d45d7e5b25f1ba0358ca08eb8945f9aec61b4f79"


def manifest():
    return json.loads((GENERATED / "manifest.json").read_text(encoding="utf-8"))


def case(case_id):
    record = next(c for c in manifest()["cases"] if c["id"] == case_id)
    data = read_csv(GENERATED / record["csv"], CSVConfig(sample_format=record["sample_format"]))
    return record, data.samples


@pytest.mark.parametrize("case_id", [f"T{j:02d}" for j in range(1, 11)])
def test_generated_end_to_end(case_id):
    record, samples = case(case_id)
    assert len(samples) == record["sample_count"]
    assert hashlib.sha256((GENERATED / record["csv"]).read_bytes()).hexdigest() == record["sha256"]
    assert np.mean(np.abs(samples)**2) == pytest.approx(record["realized_mean_power"], rel=1e-14, abs=1e-20)
    result = compute_psd(samples)
    assert np.all(np.isfinite(result.psd_linear)) and np.all(result.psd_linear >= 0)
    if case_id == "T05":
        assert result.integrated_power == pytest.approx(record["expected_power"], rel=0.04)
    elif case_id == "T09":
        assert result.integrated_power == pytest.approx(record["expected_power"], rel=5e-5)
    else:
        assert result.integrated_power == pytest.approx(record["expected_power"], rel=1e-12, abs=1e-15)
    if len(record["signal_frequency_hz"]) == 1:
        peak = np.argmax(result.psd_linear)
        assert abs(result.frequency_hz[peak] - record["signal_frequency_hz"][0]) <= result.frequency_resolution_hz / 2 + 1e-8


def test_original_capture_format_frequency_and_amplitude():
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() == ORIGINAL_SHA256
    data = read_csv(ORIGINAL, CSVConfig(sample_format="hex_q15"))
    assert data.header == ("q", "i") and data.columns == (1, 0)
    assert data.sample_count == 8192 and data.delimiter == ","
    result = compute_psd(data.samples)
    peak = np.argmax(result.psd_linear)
    assert result.frequency_hz[peak] == pytest.approx(40e6, abs=1e-8)
    # Independent known four-sample cycle from the raw words, not a saved Golden spectrum.
    cycle = np.array([-814 - 11481j, 11481 - 814j, 814 + 11481j, -11481 + 814j]) / 32768
    expected_power = float(np.mean(abs(cycle)**2))
    assert result.integrated_power == pytest.approx(expected_power, rel=1e-14)
    assert result.rbw_power_dbfs[peak] == pytest.approx(10 * np.log10(expected_power), abs=1e-11)
    assert result.enbw_hz == pytest.approx(29296.875)


def test_two_tone_relative_power():
    record, samples = case("T04")
    result = compute_psd(samples)
    for frequency, amplitude in zip(record["signal_frequency_hz"], record["signal_amplitude"]):
        j = np.argmin(abs(result.frequency_hz - frequency))
        assert result.rbw_power_dbfs[j] == pytest.approx(20 * np.log10(amplitude), abs=1e-10)


def test_noise_welch_normalization():
    _, samples = case("T05")
    for window in ("rectangle", "hann"):
        result = compute_psd(samples, PSDConfig(window=window, fft_points=256))
        assert result.segment_count == 63
        assert result.integrated_power == pytest.approx(0.04, rel=0.035)
        # Complex white noise two-sided expected density is variance / fs.
        assert np.mean(result.psd_linear) == pytest.approx(0.04 / 160e6, rel=0.035)


def test_noncoherent_window_sidelobes_and_scalloping():
    record, samples = case("T06")
    hann = compute_psd(samples)
    rectangle = compute_psd(samples, PSDConfig(window="rectangle"))
    ideal_db = 20 * np.log10(record["signal_amplitude"][0])
    assert ideal_db - np.max(hann.rbw_power_dbfs) == pytest.approx(1.4236228, abs=1e-6)
    assert ideal_db - np.max(rectangle.rbw_power_dbfs) == pytest.approx(3.9223941, abs=1e-6)
    distant = abs(hann.frequency_hz - record["signal_frequency_hz"][0]) > 5 * hann.frequency_resolution_hz
    assert np.sum(hann.psd_linear[distant]) < np.sum(rectangle.psd_linear[distant]) * 0.001


def test_dc_removal():
    _, samples = case("T08")
    kept = compute_psd(samples, PSDConfig(fft_points=256))
    removed = compute_psd(samples, PSDConfig(fft_points=256, detrend="mean"))
    assert kept.integrated_power == pytest.approx(0.328125, rel=1e-13)
    assert removed.integrated_power == pytest.approx(0.25, rel=1e-13)
    assert removed.psd_linear[np.argmin(abs(removed.frequency_hz))] < 1e-30


def test_data_generation_is_reproducible(tmp_path):
    recreated = generate(tmp_path)
    assert recreated == manifest()
    generate(tmp_path)
    for record in recreated["cases"]:
        assert (tmp_path / record["csv"]).read_bytes() == (GENERATED / record["csv"]).read_bytes()


@pytest.mark.parametrize("display,label", [("dbfs", "dBFS)"), ("dbfs_per_hz", "dBFS/Hz)")])
def test_plotting_show_units_no_fft_or_save(monkeypatch, display, label):
    import matplotlib.pyplot as plt
    from psd.plotting import plot_psd
    result = compute_psd(np.zeros(32, dtype=np.complex128))
    original_values = result.rbw_power_dbfs.copy()
    shown = []
    monkeypatch.setattr(plt, "show", lambda: shown.append(True))

    def forbidden(*args, **kwargs):
        pytest.fail("plotting must not calculate FFT or save figures")

    monkeypatch.setattr(np.fft, "fft", forbidden)
    monkeypatch.setattr(plt, "savefig", forbidden)
    monkeypatch.setattr(plt.Figure, "savefig", forbidden)
    for show in (True, False):
        figure, axes = plot_psd(result, display=display, show=show)
        assert label in axes.get_ylabel() and "MHz" in axes.get_xlabel()
        assert len(axes.lines) == 1
        assert np.all(np.isfinite(axes.lines[0].get_ydata()))
        plt.close(figure)
    assert shown == [True]
    np.testing.assert_array_equal(result.rbw_power_dbfs, original_values)


def test_cli_from_another_directory(tmp_path):
    completed = subprocess.run([sys.executable, str(ROOT / "python" / "demo.py"), "--input",
                                "data/sine_+40MHz_160MSPS.csv", "--no-show"],
                               cwd=tmp_path, check=True, capture_output=True, text=True)
    assert "Peak: 40000000 Hz" in completed.stdout
    assert "FFT: 8192" in completed.stdout


GOLDEN_INDEX = json.loads((ROOT / "data" / "golden" / "index.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("entry", GOLDEN_INDEX["vectors"], ids=lambda entry: entry["id"])
def test_golden_vectors_and_independent_scipy(entry):
    from scipy import signal

    def invalid_json_constant(value):
        raise ValueError(f"Nonstandard JSON constant: {value}")

    path = ROOT / "data" / "golden" / entry["file"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
    vector = json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid_json_constant)
    source = path.parent / vector["input"]["csv_relative_to_vector"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == vector["input"]["sha256"]
    samples = read_csv(source, CSVConfig(**vector["input"]["csv_config"])).samples
    config = PSDConfig(**vector["psd_config"])
    result = compute_psd(samples, config)
    expected = vector["expected"]
    tolerance = vector["tolerances"]
    np.testing.assert_allclose(result.frequency_hz, expected["frequency_hz"], **tolerance["frequency_hz"])
    np.testing.assert_allclose(result.psd_linear, expected["psd_linear"], **tolerance["psd_linear"])
    for key in ("fft_size", "segment_count", "window", "input_type", "method", "overlap_samples", "hop_size",
                "input_sample_count", "used_sample_count", "discarded_tail_samples", "detrend"):
        assert getattr(result, key) == expected[key]
    for key in ("fs_hz", "frequency_resolution_hz", "enbw_hz", "coherent_gain", "window_power_sum", "reference_power"):
        np.testing.assert_allclose(getattr(result, key), expected[key], **tolerance["scalar_metadata"])
    significant = np.array(expected["psd_linear"]) > tolerance["db_values"]["compare_only_when_expected_psd_linear_gt"]
    for key in ("psd_dbfs_per_hz", "rbw_power_dbfs"):
        decoded = np.array([-np.inf if v is None else v for v in expected[key]])
        np.testing.assert_allclose(getattr(result, key)[significant], decoded[significant],
                                   rtol=0, atol=tolerance["db_values"]["atol_db"])
        assert np.all(np.isneginf(getattr(result, key)[np.isneginf(decoded)]))
    w = signal.get_window("hann" if config.window == "hann" else "boxcar", result.fft_size, fftbins=True)
    kwargs = dict(fs=config.fs, window=w, detrend="constant" if config.detrend == "mean" else False,
                  return_onesided=result.input_type == "real", scaling="density")
    if result.method == "welch":
        _, independent = signal.welch(samples, nperseg=result.fft_size, noverlap=result.overlap_samples, **kwargs)
    else:
        _, independent = signal.periodogram(samples, **kwargs)
    if result.input_type == "complex":
        independent = np.fft.fftshift(independent)
    np.testing.assert_allclose(independent, expected["psd_linear"], **tolerance["psd_linear"])
    assert result.integrated_power == pytest.approx(expected["integrated_power"], rel=2e-12, abs=1e-15)


def test_golden_index_completeness():
    directory = ROOT / "data" / "golden"
    assert GOLDEN_INDEX["vector_count"] == len(GOLDEN_INDEX["vectors"]) == 17
    assert {v["file"] for v in GOLDEN_INDEX["vectors"]} == {p.name for p in directory.glob("T*.json")}
    assert {v["id"].split("_")[0] for v in GOLDEN_INDEX["vectors"]} == {f"T{j:02d}" for j in range(1, 11)}
