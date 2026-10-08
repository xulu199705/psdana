package qam

import "fmt"

type QAMResult struct {
	QAMOrder         int     `json:"qam_order"`
	SampleRateHz     float64 `json:"sample_rate_hz"`
	SymbolRateHz     float64 `json:"symbol_rate_hz"`
	SamplesPerSymbol int     `json:"samples_per_symbol"`
	Metrics
	FrequencyErrorHz     *float64       `json:"frequency_error_hz"`
	TimingOffsetSymbols  float64        `json:"timing_offset_symbols"`
	RecoveredSymbolCount int            `json:"recovered_symbol_count"`
	ConstellationI       []float64      `json:"constellation_i"`
	ConstellationQ       []float64      `json:"constellation_q"`
	IdealI               []float64      `json:"ideal_i"`
	IdealQ               []float64      `json:"ideal_q"`
	Diagnostics          map[string]any `json:"diagnostics"`
}

// RecoveryError carries unreliable evidence, never an accepted result.
type RecoveryError struct{ Diagnostics map[string]any }

func (e *RecoveryError) Error() string {
	return fmt.Sprintf("QAM decisions unreliable: EVM/constellation occupancy failed; no equalizer applied (%v)", e.Diagnostics)
}

type RecoveryResult struct {
	Timing               TimingResult
	CFO                  CFOResult
	InitialPhaseUp       int
	InitialEVMPct        float64
	CFOSearchEvaluations int
	RRCTapCount          int
}
