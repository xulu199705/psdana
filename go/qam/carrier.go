package qam

import "math"

type CFOResult struct {
	ScalarResult
	FrequencyHz                                *float64
	BoundaryHit                                bool
	SearchSymbols                              int
	GridResolutionHz                           *float64
	CoarseHz, CoarseEVMPct, FineHz, FineEVMPct []float64
}

func linspace(a, b float64, n int) []float64 {
	x := make([]float64, n)
	step := (b - a) / float64(n-1)
	for k := range x {
		x[k] = a + float64(k)*step
	}
	x[n-1] = b
	return x
}

// SearchResidualCFO estimates positive input phase slope as positive CFO.
func SearchResidualCFO(symbols []complex128, c QAMConfig) (CFOResult, error) {
	if err := c.Validate(); err != nil {
		return CFOResult{}, err
	}
	if err := validateSamples(symbols, c.MinAnalysisSymbols); err != nil {
		return CFOResult{}, err
	}
	if !c.EnableCFOCorrection {
		fit, err := ScalarQAMFit(symbols, c.scalarConfig())
		return CFOResult{ScalarResult: fit}, err
	}
	length := len(symbols)
	if length > c.CFOSearchMaxSymbols {
		length = c.CFOSearchMaxSymbols
	}
	start := (len(symbols) - length) / 2
	subset := symbols[start : start+length]
	score := func(grid []float64) ([]float64, int, error) {
		scores := make([]float64, len(grid))
		best := 0
		for k, f := range grid {
			fit, err := ScalarQAMFit(derotate(subset, f, c.SymbolRateHz), c.scalarConfig())
			if err != nil {
				return nil, 0, err
			}
			scores[k] = fit.EVMPct
			if scores[k] < scores[best] {
				best = k
			}
		}
		return scores, best, nil
	}
	coarse := linspace(-c.MaxResidualCFOHz, c.MaxResidualCFOHz, c.CFOCoarseSteps)
	scores, best, err := score(coarse)
	if err != nil {
		return CFOResult{}, err
	}
	step := coarse[1] - coarse[0]
	fine := linspace(math.Max(-c.MaxResidualCFOHz, coarse[best]-step), math.Min(c.MaxResidualCFOHz, coarse[best]+step), c.CFOFineSteps)
	fineScores, best, err := score(fine)
	if err != nil {
		return CFOResult{}, err
	}
	frequency := fine[best]
	resolution := fine[1] - fine[0]
	fit, err := ScalarQAMFit(derotate(symbols, frequency, c.SymbolRateHz), c.scalarConfig())
	if err != nil {
		return CFOResult{}, err
	}
	return CFOResult{fit, &frequency, math.Abs(frequency) >= c.MaxResidualCFOHz-step, length, &resolution, coarse, scores, fine, fineScores}, nil
}
