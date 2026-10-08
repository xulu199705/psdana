// Package qam provides a blind scalar QAM receiver and mathematical primitives.
package qam

import (
	"fmt"
	"math"
)

const (
	// LegacyMean preserves the Python V2.1.0 mean-removal scalar fit.
	LegacyMean = "legacy_mean"
	// DecisionDirectedJoint fits a complex scalar and symbol-domain DC jointly.
	DecisionDirectedJoint = "decision_directed_joint"
)

// ScalarConfig configures only scalar fitting, without timing or CFO recovery.
// Its zero value is invalid; use DefaultScalarConfig.
type ScalarConfig struct {
	Order      int
	Iterations int
	DCMode     string
}

// DefaultScalarConfig returns 64QAM, five iterations, and LegacyMean.
func DefaultScalarConfig() ScalarConfig {
	return ScalarConfig{Order: 64, Iterations: 5, DCMode: LegacyMean}
}

func (c ScalarConfig) validate() error {
	if !validOrder(c.Order) {
		return fmt.Errorf("order must be 16, 64 or 256")
	}
	if c.Iterations < 1 {
		return fmt.Errorf("iterations must be positive")
	}
	if c.DCMode != LegacyMean && c.DCMode != DecisionDirectedJoint {
		return fmt.Errorf("dc_mode must be legacy_mean or decision_directed_joint")
	}
	return nil
}

func validOrder(order int) bool       { return order == 16 || order == 64 || order == 256 }
func finite(x float64) bool           { return !math.IsNaN(x) && !math.IsInf(x, 0) }
func finiteComplex(z complex128) bool { return finite(real(z)) && finite(imag(z)) }
func validateSamples(z []complex128, minimum int) error {
	if len(z) < minimum {
		return fmt.Errorf("need at least %d complex samples", minimum)
	}
	for i, v := range z {
		if !finiteComplex(v) {
			return fmt.Errorf("sample %d contains NaN/Inf", i)
		}
	}
	return nil
}
