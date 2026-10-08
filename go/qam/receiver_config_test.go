package qam

import (
	"math"
	"testing"
)

func TestInvalidReceiverConfiguration(t *testing.T) {
	changes := []func(*QAMConfig){
		func(c *QAMConfig) { c.SampleRateHz = 0 }, func(c *QAMConfig) { c.SymbolRateHz = math.Inf(1) }, func(c *QAMConfig) { c.SymbolRateHz = 21e6 }, func(c *QAMConfig) { c.SymbolRateHz = 160e6 }, func(c *QAMConfig) { c.QAMOrder = 32 }, func(c *QAMConfig) { c.RRCBeta = -1 }, func(c *QAMConfig) { c.RRCBeta = 1.1 }, func(c *QAMConfig) { c.RRCSpanSymbols = 0 }, func(c *QAMConfig) { c.TimingInterp = 0 }, func(c *QAMConfig) { c.ExtraEdgeTrimSymbols = -1 }, func(c *QAMConfig) { c.CFOCoarseSteps = 4 }, func(c *QAMConfig) { c.CFOFineSteps = 1 }, func(c *QAMConfig) { c.MaxResidualCFOHz = math.NaN() }, func(c *QAMConfig) { c.MaxResidualCFOHz = 0 }, func(c *QAMConfig) { c.MaxAnalysisSymbols = 10 }, func(c *QAMConfig) { c.QSign = 0 }, func(c *QAMConfig) { c.ConstellationPoints = 0 }, func(c *QAMConfig) { c.ScalarFitIterations = 0 }, func(c *QAMConfig) { c.MinAnalysisSymbols = 1 }, func(c *QAMConfig) { c.MinAnalysisSymbols = int(^uint(0) >> 1) }, func(c *QAMConfig) { c.CFOCoarseSteps = int(^uint(0) >> 1) }, func(c *QAMConfig) { c.TimingKaiserBeta = math.Inf(1) }, func(c *QAMConfig) { c.DCMode = "invalid" },
	}
	for k, change := range changes {
		c := DefaultQAMConfig()
		change(&c)
		if c.Validate() == nil {
			t.Fatal("invalid config accepted", k)
		}
	}
	c := DefaultQAMConfig()
	if c.Validate() != nil {
		t.Fatal("defaults invalid")
	}
	for _, up := range []int{1, 2, 16} {
		x := []complex128{1 + 2i, 3 - 4i}
		out, err := Interpolate(x, up, 8)
		if err != nil || len(out) != len(x)*up {
			t.Fatal("interpolator length", up, err)
		}
	}
}
