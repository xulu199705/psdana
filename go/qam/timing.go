package qam

import (
	"fmt"
	"math"
	"math/cmplx"
)

type TimingResult struct {
	SymbolsRaw                    []complex128
	PhaseUp                       int
	EVMPct                        float64
	CurveEVMPct                   []float64
	TrimSymbols, FirstSymbolIndex int
}

func derotate(x []complex128, hz, rate float64) []complex128 {
	y := make([]complex128, len(x))
	for k, v := range x {
		y[k] = v * cmplx.Exp(complex(0, -2*math.Pi*hz*float64(k)/rate))
	}
	return y
}

// SearchTimingPhases scores every phase, with first-minimum tie selection.
// A non-nil CFO applies the bounded Joint refinement scoring convention.
func SearchTimingPhases(up []complex128, c QAMConfig, cfo *float64) (TimingResult, error) {
	if err := c.Validate(); err != nil {
		return TimingResult{}, err
	}
	if err := validateSamples(up, 1); err != nil {
		return TimingResult{}, err
	}
	if cfo != nil && !finite(*cfo) {
		return TimingResult{}, fmt.Errorf("nonfinite CFO")
	}
	period := c.SamplesPerSymbol() * c.TimingInterp
	trim := c.RRCSpanSymbols/2 + c.ExtraEdgeTrimSymbols
	if len(up)/period < 2*trim+c.MinAnalysisSymbols+1 {
		return TimingResult{}, fmt.Errorf("capture too short after matched-filter edge trimming")
	}
	best := TimingResult{EVMPct: math.Inf(1), CurveEVMPct: make([]float64, period), TrimSymbols: trim}
	for phase := 0; phase < period; phase++ {
		begin, end := trim*period+phase, len(up)-trim*period
		count := (end - begin + period - 1) / period
		start := 0
		if count > c.MaxAnalysisSymbols {
			start = (count - c.MaxAnalysisSymbols) / 2
			count = c.MaxAnalysisSymbols
		}
		syms := make([]complex128, count)
		for k := range syms {
			syms[k] = up[begin+(start+k)*period]
		}
		scored := syms
		if cfo != nil {
			scored = derotate(syms, *cfo, c.SymbolRateHz)
		}
		fit, err := ScalarQAMFit(scored, c.scalarConfig())
		if err != nil {
			return TimingResult{}, err
		}
		best.CurveEVMPct[phase] = fit.EVMPct
		if fit.EVMPct < best.EVMPct {
			best.SymbolsRaw = syms
			best.PhaseUp = phase
			best.EVMPct = fit.EVMPct
			best.FirstSymbolIndex = trim + start
		}
	}
	return best, nil
}
