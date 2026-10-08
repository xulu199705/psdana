package qam

import (
	"encoding/json"
	"fmt"
	"math"
	"math/cmplx"
)

// ScalarResult contains full corrected symbols and final decisions. DC is in
// the supplied symbol domain, ComplexGain is the correcting scalar, and Joint
// ForwardGain is a in z=a*d+c. Phase is identifiable only modulo 90 degrees.
type ScalarResult struct {
	Equalized, Decisions         []complex128
	Indices                      []int
	EVMPct                       float64
	DC, ComplexGain, ForwardGain complex128
	CoarsePhaseDeg               float64
	DCMode                       string
	JointIterations              int
	JointConverged               bool
}

// MarshalJSON encodes complex numbers as real/imag fields or parallel arrays,
// using Python primitive field names. Nonfinite values return an encoding error.
func (r ScalarResult) MarshalJSON() ([]byte, error) {
	split := func(z complex128) map[string]float64 { return map[string]float64{"real": real(z), "imag": imag(z)} }
	array := func(z []complex128) map[string][]float64 {
		a, b := make([]float64, len(z)), make([]float64, len(z))
		for k, v := range z {
			a[k], b[k] = real(v), imag(v)
		}
		return map[string][]float64{"real": a, "imag": b}
	}
	out := map[string]any{"eq": array(r.Equalized), "decisions": array(r.Decisions), "indices": r.Indices,
		"evm_pct": r.EVMPct, "dc": split(r.DC), "complex_gain": split(r.ComplexGain), "coarse_phase_deg": r.CoarsePhaseDeg}
	if r.DCMode == DecisionDirectedJoint {
		out["forward_gain"], out["joint_fit_iterations"], out["joint_fit_converged"] = split(r.ForwardGain), r.JointIterations, r.JointConverged
	}
	return json.Marshal(out)
}

func mean(z []complex128) complex128 {
	var s complex128
	for _, v := range z {
		s += v
	}
	return s / complex(float64(len(z)), 0)
}
func norm2(z []complex128) float64 {
	var s float64
	for _, v := range z {
		a := cmplx.Abs(v)
		s += a * a
	}
	return s
}
func dot(x, y []complex128) complex128 {
	var s complex128
	for k, v := range x {
		s += cmplx.Conj(v) * y[k]
	}
	return s
}

// Search scoring needs only EVM, not radial/tangential/angle metrics. Keep
// identical magnitude accumulation; full metrics are computed for final output.
func decisionEVM(y, d []complex128) (float64, error) {
	var energy, total float64
	for k, v := range y {
		a, b := cmplx.Abs(d[k]), cmplx.Abs(v-d[k])
		energy += a * a
		total += b * b
	}
	if !finite(energy) || energy <= 0 || !finite(total) {
		return 0, fmt.Errorf("EVM exceeds supported numeric range")
	}
	evm := 100 * math.Sqrt(total/energy)
	if !finite(evm) {
		return 0, fmt.Errorf("nonfinite EVM")
	}
	return evm, nil
}

// ScalarQAMFit performs bounded blind scalar fitting; it never modifies samples.
// There is no timing/CFO search or quality-lock claim in this primitive API.
func ScalarQAMFit(samples []complex128, config ScalarConfig) (ScalarResult, error) {
	if err := config.validate(); err != nil {
		return ScalarResult{}, err
	}
	if err := validateSamples(samples, 32); err != nil {
		return ScalarResult{}, err
	}
	legacy, err := legacyFit(samples, config)
	if err != nil || config.DCMode == LegacyMean {
		return legacy, err
	}
	zMean := mean(samples)
	z := make([]complex128, len(samples))
	for k, v := range samples {
		z[k] = v - zMean
	}
	d := legacy.Decisions
	result := ScalarResult{CoarsePhaseDeg: legacy.CoarsePhaseDeg, DCMode: DecisionDirectedJoint}
	for used := 1; used <= config.Iterations; used++ {
		dMean := mean(d)
		centered := make([]complex128, len(d))
		for k, v := range d {
			centered[k] = v - dMean
		}
		energy := norm2(centered)
		if !finite(energy) || energy <= 0 {
			return ScalarResult{}, fmt.Errorf("zero or invalid centered decision energy")
		}
		a := dot(centered, z) / complex(energy, 0)
		c := zMean - a*dMean
		if !finiteComplex(a) || cmplx.Abs(a) == 0 || !finiteComplex(c) {
			return ScalarResult{}, fmt.Errorf("joint fit gain/DC is zero or nonfinite")
		}
		y := make([]complex128, len(samples))
		for k, v := range samples {
			y[k] = (v - c) / a
		}
		updated, indices, err := SliceQAM(y, config.Order)
		if err != nil {
			return ScalarResult{}, err
		}
		stable := true
		for k, v := range d {
			if v != updated[k] {
				stable = false
				break
			}
		}
		result.Equalized, result.Decisions, result.Indices = y, updated, indices
		result.DC, result.ComplexGain, result.ForwardGain = c, 1/a, a
		result.JointIterations, result.JointConverged = used, stable
		d = updated
		if stable {
			break
		}
	}
	evm, err := decisionEVM(result.Equalized, result.Decisions)
	if err != nil || !finiteComplex(result.ComplexGain) {
		return ScalarResult{}, fmt.Errorf("joint fit exceeds numeric range: %v", err)
	}
	result.EVMPct = evm
	return result, nil
}

func legacyFit(samples []complex128, config ScalarConfig) (ScalarResult, error) {
	dc := mean(samples)
	y := make([]complex128, len(samples))
	for k, v := range samples {
		y[k] = v - dc
	}
	rms := math.Sqrt(norm2(y) / float64(len(y)))
	if !finite(rms) || rms <= 0 || !finiteComplex(dc) {
		return ScalarResult{}, fmt.Errorf("zero or invalid QAM power")
	}
	var moment complex128
	for k := range y {
		y[k] /= complex(rms, 0)
		square := y[k] * y[k]
		moment += square * square
	}
	moment /= complex(float64(len(y)), 0)
	phase := 0.0
	if cmplx.Abs(moment) > 1e-15 {
		phase = cmplx.Phase(-moment) / 4
	}
	gain := cmplx.Exp(complex(0, -phase)) / complex(rms, 0)
	for k := range y {
		y[k] *= cmplx.Exp(complex(0, -phase))
	}
	for used := 0; used < config.Iterations; used++ {
		d, _, err := SliceQAM(y, config.Order)
		if err != nil {
			return ScalarResult{}, err
		}
		denominator := dot(y, y)
		if !finiteComplex(denominator) || cmplx.Abs(denominator) <= 1e-30 {
			return ScalarResult{}, fmt.Errorf("invalid scalar fit energy")
		}
		g := dot(y, d) / denominator
		for k := range y {
			y[k] *= g
		}
		gain *= g
	}
	d, indices, err := SliceQAM(y, config.Order)
	if err != nil {
		return ScalarResult{}, err
	}
	evm, err := decisionEVM(y, d)
	if err != nil || !finiteComplex(gain) || cmplx.Abs(gain) == 0 {
		return ScalarResult{}, fmt.Errorf("scalar fit exceeds numeric range: %v", err)
	}
	return ScalarResult{Equalized: y, Decisions: d, Indices: indices, EVMPct: evm,
		DC: dc, ComplexGain: gain, CoarsePhaseDeg: phase * 180 / math.Pi, DCMode: LegacyMean}, nil
}
