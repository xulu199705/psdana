package qam

import (
	"fmt"
	"math"
	"math/cmplx"
)

// Metrics uses RMS percentage errors and principal-angle RMS degrees.
type Metrics struct {
	EVMPctRMS            float64 `json:"evm_pct_rms"`
	AmplitudeErrorPctRMS float64 `json:"amplitude_error_pct_rms"`
	PhaseErrorPctRMS     float64 `json:"phase_error_pct_rms"`
	PhaseErrorDegRMS     float64 `json:"phase_error_deg_rms"`
}

// ComputeQAMMetrics compares corresponding symbols without fitting or slicing.
// PhaseErrorPctRMS is tangential error, not a percentage of a phase angle.
func ComputeQAMMetrics(samples, decisions []complex128) (Metrics, error) {
	if err := validateSamples(samples, 1); err != nil {
		return Metrics{}, err
	}
	if err := validateSamples(decisions, 1); err != nil {
		return Metrics{}, err
	}
	if len(samples) != len(decisions) {
		return Metrics{}, fmt.Errorf("metric arrays must have equal lengths")
	}
	var energy, total, radial, tangent, angles float64
	for k, y := range samples {
		d := decisions[k]
		m := cmplx.Abs(d)
		if m == 0 {
			return Metrics{}, fmt.Errorf("reference %d has zero magnitude", k)
		}
		e := y - d
		projected := e * cmplx.Conj(d)
		product := y * cmplx.Conj(d)
		if !finiteComplex(projected) || !finiteComplex(product) {
			return Metrics{}, fmt.Errorf("metric product exceeds float64 range")
		}
		r, t := real(projected)/m, imag(projected)/m
		angle := cmplx.Phase(product) * 180 / math.Pi
		energy += m * m
		mag := cmplx.Abs(e)
		total += mag * mag
		radial += r * r
		tangent += t * t
		angles += angle * angle
	}
	if !finite(energy) || energy <= 0 || !finite(total) || !finite(radial) || !finite(tangent) || !finite(angles) {
		return Metrics{}, fmt.Errorf("metric accumulation exceeds supported numeric range")
	}
	out := Metrics{100 * math.Sqrt(total/energy), 100 * math.Sqrt(radial/energy), 100 * math.Sqrt(tangent/energy), math.Sqrt(angles / float64(len(samples)))}
	if !finite(out.EVMPctRMS) || !finite(out.AmplitudeErrorPctRMS) || !finite(out.PhaseErrorPctRMS) || !finite(out.PhaseErrorDegRMS) {
		return Metrics{}, fmt.Errorf("metrics are nonfinite")
	}
	return out, nil
}
