"""Unmodified TX truth, QAM Golden hashes, real capture and CLI regressions."""

from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from psd import PSDConfig, analyze_iq
from psd.csvio import CSVConfig, read_csv
from psd.qam import QAMConfig, analyze_qam, recover_symbols
from qam_gen import generate_signal, generate_all, quantize_q15, OUTPUT, sha256
from qam_reference import data_aided_check

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT/"data/golden/qam"
ACTUAL = ROOT/"data/qam64_20MSymPS_160MSPS_RRC0p25.csv"
METRICS = ("evm_pct_rms","amplitude_error_pct_rms","phase_error_pct_rms","phase_error_deg_rms")


@pytest.fixture(scope="module")
def manifest():
    return json.loads((OUTPUT/"manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("identity",[f"Q{i:02d}" for i in range(1,13)])
def test_synthetic_with_independent_transmit_truth(manifest,identity):
    v = next(v for v in manifest["vectors"] if v["id"] == identity)
    assert sha256(OUTPUT/v["input_file"]) == v["input_sha256"]
    assert sha256(OUTPUT/v["truth_file"]) == v["truth_sha256"]
    x = read_csv(OUTPUT/v["input_file"],CSVConfig(sample_format=v["sample_format"])).samples
    d = read_csv(OUTPUT/v["truth_file"]).samples
    cfg = QAMConfig(symbol_rate_hz=v["symbol_rate_hz"])
    recovered = recover_symbols(x,cfg)
    da = data_aided_check(recovered,d)
    blind = analyze_qam(x,cfg)
    assert da["decision_mismatch_count"] == 0
    for name in METRICS:
        assert getattr(blind,name) == pytest.approx(da[name],abs=1e-10)
    assert blind.evm_pct_rms**2 == pytest.approx(
        blind.amplitude_error_pct_rms**2+blind.phase_error_pct_rms**2,abs=1e-11)
    assert abs(blind.frequency_error_hz-v["cfo_hz"]) <= 2*blind.diagnostics["cfo_grid_resolution_hz"]
    assert blind.diagnostics["trim_symbols_per_edge"] == 11


def test_generator_determinism_and_packed_equivalence(tmp_path,manifest):
    from psd.iqio import read_packed64
    regenerated = generate_all(tmp_path)
    assert regenerated == manifest
    for v in manifest["vectors"]:
        assert sha256(tmp_path/v["input_file"]) == v["input_sha256"]
    q10 = next(v for v in manifest["vectors"] if v["id"] == "Q10")
    csv = read_csv(OUTPUT/q10["input_file"],CSVConfig(sample_format="q15")).samples
    np.testing.assert_array_equal(csv,read_packed64(OUTPUT/q10["packed_file"]))
    assert q10["clipped_component_count"] == 0


def test_known_impairments_same_truth_are_not_fitted_away():
    clean,d,_ = generate_signal(symbol_count=4096,seed=22)
    noisy,other,_ = generate_signal(symbol_count=4096,seed=22,noise_evm_pct=5)
    distorted,_,_ = generate_signal(symbol_count=4096,seed=22,iq_imbalance=.08)
    gain_phase,_,_ = generate_signal(symbol_count=4096,seed=22,gain=.6,phase_deg=31)
    np.testing.assert_array_equal(d,other)
    a,b,c,g = [analyze_qam(x) for x in (clean,noisy,distorted,gain_phase)]
    assert b.evm_pct_rms > a.evm_pct_rms
    assert c.evm_pct_rms > a.evm_pct_rms+3
    assert g.evm_pct_rms == pytest.approx(a.evm_pct_rms,abs=1e-10)
    integers,_ = quantize_q15(clean)
    q = integers[:,0].astype(float)/32768+1j*integers[:,1].astype(float)/32768
    assert abs(analyze_qam(q).evm_pct_rms-a.evm_pct_rms) < .01


@pytest.mark.parametrize("identity", [f"Q{i:02d}" for i in range(1,13)]+["REAL64"])
def test_qam_golden(identity):
    index = json.loads((GOLDEN/"index.json").read_text(encoding="utf-8"))
    entries = {v["id"]:v for v in index["vectors"]}
    assert index["vector_count"] == len(entries)
    if identity not in entries:
        pytest.skip("BLOCKED: real capture Golden unavailable")
    entry = entries[identity]
    path = GOLDEN/entry["file"]
    assert sha256(path) == entry["sha256"]
    v = json.loads(path.read_text(encoding="utf-8"))
    source = path.parent/v["input_file"]
    if not source.exists() and identity == "REAL64":
        pytest.skip("BLOCKED: real capture not supplied")
    assert sha256(source) == v["input_sha256"]
    x = read_csv(source,CSVConfig(**v["csv_config"])).samples
    assert len(x) == v["sample_count"]
    cfg = QAMConfig(**v["qam_config"])
    r = analyze_qam(x,cfg).to_dict()
    expected,tol = v["expected"],v["tolerances"]
    for name in METRICS:
        assert r[name] == pytest.approx(expected[name],abs=tol["metric_atol"],rel=0)
    assert r["frequency_error_hz"] == pytest.approx(expected["frequency_error_hz"],abs=tol["cfo_atol_hz"],rel=0)
    assert r["timing_offset_symbols"] == pytest.approx(expected["timing_offset_symbols"],abs=tol["timing_atol_symbols"],rel=0)
    for name in ("constellation_i","constellation_q","ideal_i","ideal_q"):
        np.testing.assert_allclose(r[name],expected[name],atol=tol["array_atol"],rtol=tol["array_rtol"])
    for name in ("qam_order","samples_per_symbol","sample_rate_hz","symbol_rate_hz","recovered_symbol_count"):
        assert r[name] == expected[name]
    assert r["diagnostics"]["config"] == v["qam_config"] == asdict(cfg)
    assert r["diagnostics"].keys() == expected["diagnostics"].keys()
    for name,actual in r["diagnostics"].items():
        target = expected["diagnostics"][name]
        if name == "timing_curve_evm_pct":
            np.testing.assert_allclose(actual,target,atol=tol["metric_atol"],rtol=0)
        elif name in ("complex_gain","dc_offset"):
            for component in ("real","imag"):
                assert actual[component] == pytest.approx(target[component],abs=tol["array_atol"],rel=tol["array_rtol"])
        elif isinstance(actual,float):
            assert actual == pytest.approx(target,abs=tol["metric_atol"],rel=0)
        else:
            assert actual == target
    json.dumps(r,allow_nan=False)


def test_real_capture_shared_psd_and_qam():
    if not ACTUAL.exists():
        pytest.skip("BLOCKED: real capture not supplied")
    assert sha256(ACTUAL) == "5f59fc3f1a3698cf44d52e9e49bc59db6493d1471efac64bdad5b1ce62640b70"
    x = read_csv(ACTUAL,CSVConfig(sample_format="hex_q15")).samples
    r = analyze_iq(x,PSDConfig(),QAMConfig(),(-80e6,80e6))
    assert r.qam_metrics.samples_per_symbol == 8
    assert 2 < r.qam_metrics.evm_pct_rms < 3
    assert r.qam_metrics.recovered_symbol_count == 2026
    assert r.qam_metrics.timing_offset_symbols == .0625
    assert not r.qam_metrics.diagnostics["cfo_search_boundary_hit"]
    assert r.psd.fft_size == 16384
    assert r.power_metrics.band_power_linear == pytest.approx(r.psd.integrated_power)


def test_constellation_style_and_single_show(monkeypatch):
    import matplotlib
    matplotlib.use("Agg",force=True)
    import matplotlib.pyplot as plt
    from matplotlib.colors import to_rgba
    from psd.qam.plotting import plot_constellation
    from demo import main
    x,_,_ = generate_signal()
    result = analyze_qam(x)
    called = []
    monkeypatch.setattr(plt,"show",lambda: called.append(True))
    monkeypatch.setattr(plt.Figure,"savefig",lambda *a,**k: pytest.fail("must not save images"))
    fig,axes = plot_constellation(result,show=False)
    assert not called
    assert axes.get_aspect() == 1
    yellow,red = axes.collections
    assert yellow.get_alpha() == .4
    np.testing.assert_allclose(yellow.get_facecolors()[0],to_rgba("#FFE45C",alpha=.4))
    np.testing.assert_allclose(red.get_edgecolors()[0],to_rgba("#FF3B30"))
    assert len(red.get_offsets()) == 64
    assert red.get_facecolors().size == 0
    plt.close(fig)
    main(["--input","data/generated/qam/Q01_ideal.csv","--qam"])
    assert len(called) == 1
    assert len(plt.get_fignums()) == 2
    plt.close("all")
    main(["--input","data/generated/qam/Q01_ideal.csv","--qam","--no-show"])
    assert len(called) == 1
    plt.close("all")


def test_import_does_not_load_plotting():
    code = "import sys; import psd; import psd.qam; assert 'matplotlib' not in sys.modules"
    subprocess.run([sys.executable,"-c",code],cwd=ROOT/"python",check=True,capture_output=True)


def test_qam_real_cli_rejects_real(capsys):
    from demo import main
    with pytest.raises(SystemExit) as exc:
        main(["--input","data/generated/T03_real_full_scale_sine.csv","--qam","--no-show"])
    assert exc.value.code == 2
    assert "complex sequence" in capsys.readouterr().err


def test_golden_generation_deterministic(tmp_path):
    from generate_qam_golden import generate_golden
    index = generate_golden(tmp_path)
    frozen = json.loads((GOLDEN/"index.json").read_text(encoding="utf-8"))
    # Output locations affect input_file paths, but not results or tolerances.
    for entry in index["vectors"]:
        fresh = json.loads((tmp_path/entry["file"]).read_text(encoding="utf-8"))
        expected = json.loads((GOLDEN/entry["file"]).read_text(encoding="utf-8"))
        fresh.pop("input_file")
        expected.pop("input_file")
        assert fresh == expected
    before = {entry["file"]:entry["sha256"] for entry in index["vectors"]}
    assert before == {entry["file"]:entry["sha256"] for entry in generate_golden(tmp_path)["vectors"]}
    assert frozen["vector_count"] == len(index["vectors"])
