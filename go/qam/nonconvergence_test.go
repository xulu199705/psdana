package qam

import (
	"math"
	"math/cmplx"
	"reflect"
	"testing"
)

// V2.1.1 contract: last LS gain/DC fit the previous decisions. Returned final
// decisions are the new slice of that LS output; no hidden extra refit occurs.
func TestJointIterationLimitContract(t *testing.T) {
	z := make([]complex128, 512)
	for k := range z {
		n := float64(k)
		z[k] = complex(math.Sin(n*.37)+.3*math.Cos(n*.19), math.Cos(n*.23)+.2*math.Sin(n*.43))
	}
	cfg := ScalarConfig{64, 1, LegacyMean}
	initial, err := ScalarQAMFit(z, cfg)
	if err != nil {
		t.Fatal(err)
	}
	cfg.DCMode = DecisionDirectedJoint
	fit, err := ScalarQAMFit(z, cfg)
	if err != nil {
		t.Fatal(err)
	}
	if fit.JointConverged || fit.JointIterations != 1 {
		t.Fatal("fixture must update final decisions")
	}
	zm, dm := mean(z), mean(initial.Decisions)
	var numerator complex128
	var denominator float64
	for k, v := range initial.Decisions {
		d := v - dm
		numerator += cmplx.Conj(d) * (z[k] - zm)
		a := cmplx.Abs(d)
		denominator += a * a
	}
	expected := numerator / complex(denominator, 0)
	closeTo(t, cmplx.Abs(fit.ForwardGain-expected), 0, 1e-14)
	closeTo(t, cmplx.Abs(fit.DC-(zm-expected*dm)), 0, 1e-14)
	decisions, _, err := SliceQAM(fit.Equalized, 64)
	if err != nil || !reflect.DeepEqual(decisions, fit.Decisions) {
		t.Fatal("final decisions do not slice final output")
	}
	for k, v := range z {
		closeTo(t, cmplx.Abs(fit.Equalized[k]-(v-fit.DC)/fit.ForwardGain), 0, 1e-14)
	}
}
