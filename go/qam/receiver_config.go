package qam

import (
	"fmt"
	"math"
)

// QAMConfig is explicit; the zero value is invalid. Use DefaultQAMConfig.
type QAMConfig struct {
	SampleRateHz         float64 `json:"sample_rate_hz"`
	SymbolRateHz         float64 `json:"symbol_rate_hz"`
	QAMOrder             int     `json:"qam_order"`
	RRCBeta              float64 `json:"rrc_beta"`
	RRCSpanSymbols       int     `json:"rrc_span_symbols"`
	TimingInterp         int     `json:"timing_interp"`
	TimingKaiserBeta     float64 `json:"timing_kaiser_beta"`
	ExtraEdgeTrimSymbols int     `json:"extra_edge_trim_symbols"`
	EnableCFOCorrection  bool    `json:"enable_cfo_correction"`
	MaxResidualCFOHz     float64 `json:"max_residual_cfo_hz"`
	CFOCoarseSteps       int     `json:"cfo_coarse_steps"`
	CFOFineSteps         int     `json:"cfo_fine_steps"`
	CFOSearchMaxSymbols  int     `json:"cfo_search_max_symbols"`
	MaxAnalysisSymbols   int     `json:"max_analysis_symbols"`
	ConstellationPoints  int     `json:"constellation_points"`
	QSign                int     `json:"q_sign"`
	ScalarFitIterations  int     `json:"scalar_fit_iterations"`
	MinAnalysisSymbols   int     `json:"min_analysis_symbols"`
	MaxDecisionEVMPct    float64 `json:"max_decision_evm_pct"`
	DCMode               string  `json:"-"` // Python selects this separately from its config.
}

func DefaultQAMConfig() QAMConfig {
	return QAMConfig{160e6, 20e6, 64, .25, 10, 16, 8, 6, true, 5000, 81, 41, 12000, 30000, 5000, 1, 5, 200, 12, LegacyMean}
}
func (c QAMConfig) SamplesPerSymbol() int { return int(math.Round(c.SampleRateHz / c.SymbolRateHz)) }
func (c QAMConfig) scalarConfig() ScalarConfig {
	return ScalarConfig{c.QAMOrder, c.ScalarFitIterations, c.DCMode}
}
func (c QAMConfig) Validate() error {
	if !finite(c.SampleRateHz) || c.SampleRateHz <= 0 || !finite(c.SymbolRateHz) || c.SymbolRateHz <= 0 {
		return fmt.Errorf("rates must be finite and positive")
	}
	ratio := c.SampleRateHz / c.SymbolRateHz
	if !finite(ratio) || ratio < 2 || ratio > 1e6 || math.Abs(ratio-math.Round(ratio)) > 8*(math.Nextafter(1, 2)-1)*ratio {
		return fmt.Errorf("integer SPS >=2 required (implementation limit 1000000)")
	}
	if err := c.scalarConfig().validate(); err != nil {
		return err
	}
	if !finite(c.RRCBeta) || c.RRCBeta < 0 || c.RRCBeta > 1 || c.RRCSpanSymbols < 1 || c.RRCSpanSymbols > 1000000/c.SamplesPerSymbol() {
		return fmt.Errorf("invalid RRC parameters")
	}
	if c.TimingInterp < 1 || c.TimingInterp > 4096 || !finite(c.TimingKaiserBeta) || c.TimingKaiserBeta < 0 || c.TimingKaiserBeta > 700 || c.ExtraEdgeTrimSymbols < 0 || c.ExtraEdgeTrimSymbols > 1000000 {
		return fmt.Errorf("invalid timing parameters")
	}
	if !finite(c.MaxResidualCFOHz) || c.MaxResidualCFOHz < 0 || c.MaxResidualCFOHz >= c.SymbolRateHz/2 || (c.EnableCFOCorrection && c.MaxResidualCFOHz == 0) {
		return fmt.Errorf("invalid CFO range")
	}
	if c.CFOCoarseSteps < 3 || c.CFOFineSteps < 3 || c.CFOCoarseSteps > 1000001 || c.CFOFineSteps > 1000001 || c.CFOCoarseSteps%2 == 0 || c.CFOFineSteps%2 == 0 {
		return fmt.Errorf("CFO grids must have odd counts >=3")
	}
	if c.MinAnalysisSymbols < 32 || c.MinAnalysisSymbols > 1000000000 || c.ScalarFitIterations > 1000000 || c.CFOSearchMaxSymbols < c.MinAnalysisSymbols || c.MaxAnalysisSymbols < c.MinAnalysisSymbols || c.ConstellationPoints < 1 || (c.QSign != 1 && c.QSign != -1) || !finite(c.MaxDecisionEVMPct) || c.MaxDecisionEVMPct <= 0 {
		return fmt.Errorf("invalid analysis parameters")
	}
	return nil
}
