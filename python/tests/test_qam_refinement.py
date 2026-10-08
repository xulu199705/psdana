"""Joint DC LS, CFO-aware timing and backward-compatible receiver behavior."""

from pathlib import Path
import json

import numpy as np
import pytest

from psd import analyze_iq
from psd.qam import QAMConfig, QAMRecoveryError, analyze_qam, recover_symbols, scalar_qam_fit, qam_constellation
from psd.qam.metrics import qam_error_metrics
from qam_gen import generate_signal
from qam_joint_reference import data_aided_scalar_reference

JOINT = "decision_directed_joint"
ROOT = Path(__file__).resolve().parents[2]


def test_skewed_256qam_convergence_does_not_prove_truth():
    points = qam_constellation(256)
    d = np.concatenate((points,points,points[:128]))
    z = .7*np.exp(.3j)*d+.02-.015j
    fit = scalar_qam_fit(z,256,dc_mode=JOINT)
    assert fit["joint_fit_converged"]
    assert np.count_nonzero(fit["decisions"]!=d) == 608
    assert fit["evm_pct"] > 3
    # Independent TX-aided affine fit is exact for this noiseless model.
    a,c = np.linalg.lstsq(np.column_stack((d,np.ones(len(d)))),z,rcond=None)[0]
    assert np.max(abs((z-c)/a-d)) < 1e-12


@pytest.mark.parametrize("order",[16,64,256])
@pytest.mark.parametrize("phase",[.3,.3+np.pi/2,.3+np.pi])
def test_affine_known_model(order,phase):
    rng = np.random.default_rng(42)
    d = qam_constellation(order)[rng.integers(0,order,2048)]
    a = .63*np.exp(1j*phase)
    c = .015-.01j
    z = a*d+c
    original = z.copy()
    fit = scalar_qam_fit(z,order,dc_mode=JOINT)
    assert fit["joint_fit_converged"]
    assert fit["joint_fit_iterations"] <= 5
    assert fit["evm_pct"] < 1e-10
    assert fit["dc"] == pytest.approx(c,abs=1e-13)
    # Gain phase is defined only modulo 90 degrees, magnitude is unambiguous.
    assert abs(fit["complex_gain"]) == pytest.approx(1/abs(a),abs=1e-12)
    np.testing.assert_array_equal(z,original)
    expected = np.linalg.lstsq(np.column_stack((fit["decisions"],np.ones(len(z)))),z,rcond=None)[0]
    assert fit["forward_gain"] == pytest.approx(expected[0],abs=1e-13)
    assert fit["dc"] == pytest.approx(expected[1],abs=1e-13)


@pytest.mark.parametrize("length",[256,512,1024,2048,4096,16384])
@pytest.mark.parametrize("damage",[{},dict(dc=.02-.015j),dict(noise_evm_pct=4)])
def test_short_record_truth_not_sample_mean(length,damage):
    x,d,_ = generate_signal(symbol_count=length,seed=12345,**damage)
    cfg = QAMConfig()
    legacy = recover_symbols(x,cfg)
    joint = recover_symbols(x,cfg,dc_mode=JOINT)
    reference = data_aided_scalar_reference(joint,d,cfg.symbol_rate_hz)
    assert reference["comparison"]["decision_mismatch_count"] == 0
    # Exact LS equivalence uses the same CFO. The known-true-CFO oracle is a
    # different estimator: noisy blind CFO can optimize a small noise slope.
    assert joint["evm_pct"] == pytest.approx(reference["at_estimated_cfo_evm_pct"],abs=1e-10)
    assert abs(joint["dc"]-reference["at_estimated_cfo_dc"]) < 1e-12
    assert abs(joint["complex_gain"]-reference["at_estimated_cfo_gain"]) < 1e-12
    assert joint["joint_fit_converged"]
    # Improvement is checked against independent TX truth, not only blind EVM.
    legacy_ref = data_aided_scalar_reference(legacy,d,cfg.symbol_rate_hz)
    assert reference["comparison"]["evm_pct_rms"] <= legacy_ref["comparison"]["evm_pct_rms"]


@pytest.mark.parametrize("frequency",[-4995,-3000,-1000,-100,0,100,1000,3000,4995])
def test_cfo_and_timing_refinement(frequency):
    x,d,_ = generate_signal(symbol_count=2048,seed=12345,cfo_hz=frequency)
    cfg = QAMConfig()
    r = recover_symbols(x,cfg,dc_mode=JOINT)
    assert abs(r["cfo_hz"]-frequency) <= 12.5
    assert min(r["timing_phase_up"],128-r["timing_phase_up"]) <= 1
    assert r["timing_cfo_refinement_enabled"]
    reference = data_aided_scalar_reference(r,d,cfg.symbol_rate_hz,frequency)
    assert reference["comparison"]["decision_mismatch_count"] == 0
    assert r["evm_pct"] < 1.1


def test_joint_diagnostics_disabled_cfo_and_cli(monkeypatch):
    import matplotlib.pyplot as plt
    from demo import main
    x,_,_ = generate_signal()
    cfg = QAMConfig(enable_cfo_correction=False)
    r = analyze_iq(x,qam_config=cfg,dc_mode=JOINT).qam_metrics
    assert r.frequency_error_hz is None
    assert r.diagnostics["cfo_estimation_uncertainty_hz"] is None
    assert r.diagnostics["cfo_estimation_error_hz"] is None
    assert r.diagnostics["timing_fit_mode"] == r.diagnostics["cfo_fit_mode"] == JOINT
    assert r.diagnostics["joint_fit_converged"]
    assert r.diagnostics["algorithm_version"] == "qam-blind-scalar-2"
    assert not r.diagnostics["timing_cfo_refinement_enabled"]
    json.dumps(r.to_dict(),allow_nan=False)
    main(["--input","data/generated/qam/Q01_ideal.csv","--qam","--qam-dc-mode",JOINT,"--no-show"])
    plt.close("all")


@pytest.mark.parametrize("mode",["invalid",None,""])
def test_invalid_mode(mode):
    x,_,_ = generate_signal()
    with pytest.raises(ValueError,match="dc_mode"):
        analyze_qam(x,dc_mode=mode)


def test_unreliable_is_error_with_evidence():
    rng = np.random.default_rng(4242)
    noise = rng.normal(size=16384)+1j*rng.normal(size=16384)
    with pytest.raises(QAMRecoveryError) as exc:
        analyze_qam(noise,dc_mode=JOINT)
    assert exc.value.diagnostics["status"] == "unreliable"


@pytest.mark.parametrize("order",[16,64,256])
def test_metrics_decomposition_all_orders(order):
    d = qam_constellation(order)
    metrics = qam_error_metrics(d*(1.03+.04j),d)
    assert metrics["evm_pct_rms"] == pytest.approx(5)
    assert metrics["evm_pct_rms"]**2 == pytest.approx(
        metrics["amplitude_error_pct_rms"]**2+metrics["phase_error_pct_rms"]**2)


@pytest.mark.parametrize("values",[np.array([],complex),np.ones(64,complex),
    np.full(64,complex(np.nan,0)),np.full(64,1e308+1e308j)])
def test_joint_numeric_boundaries(values):
    with pytest.raises(ValueError):
        scalar_qam_fit(values,dc_mode=JOINT)


@pytest.mark.parametrize("identity",[f"Q{i:02d}" for i in range(1,13)]+[f"IDEAL_{n}" for n in (256,512,1024,4096,16384)]+["REAL64"])
def test_v2_receiver_golden(identity):
    from qam_gen import sha256
    from psd.csvio import CSVConfig,read_csv
    folder = ROOT/"data/golden/qam/v2"
    index = json.loads((folder/"index.json").read_text(encoding="utf-8"))
    assert index["vector_count"] == 18 == len(index["vectors"])
    entry = next(e for e in index["vectors"] if e["id"] == identity)
    path = folder/entry["file"]
    assert sha256(path) == entry["sha256"]
    vector = json.loads(path.read_text(encoding="utf-8"))
    source = folder/vector["input_file"]
    assert sha256(source) == vector["input_sha256"]
    x = read_csv(source,CSVConfig(**vector["csv_config"])).samples
    assert len(x) == vector["sample_count"]
    actual = analyze_qam(x,QAMConfig(**vector["qam_config"]),dc_mode=vector["dc_mode"]).to_dict()
    tol = vector["tolerances"]
    def compare(a,b,field=""):
        if isinstance(a,dict):
            assert a.keys() == b.keys()
            for key in a:
                compare(a[key],b[key],key)
        elif isinstance(a,list):
            assert len(a) == len(b)
            for aa,bb in zip(a,b):
                compare(aa,bb,field)
        elif isinstance(a,float):
            if field in ("constellation_i","constellation_q","ideal_i","ideal_q","timing_curve_evm_pct"):
                atol,rtol = tol["array_atol"],tol["array_rtol"]
            elif field == "frequency_error_hz":
                atol,rtol = tol["cfo_atol_hz"],0
            elif field.endswith("offset_symbols"):
                atol,rtol = tol["timing_atol_symbols"],0
            elif field.endswith("pct_rms") or field.endswith("deg_rms"):
                atol,rtol = tol["metric_atol"],0
            else:
                atol,rtol = tol["scalar_atol"],tol["scalar_rtol"]
            assert abs(a-b) <= atol+rtol*abs(b), (field,a,b,atol,rtol)
        else:
            assert a == b
    compare(actual,vector["expected"])
