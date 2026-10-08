// qamcheck is a developer stage-comparison adapter. Full intermediate arrays
// belong in ignored temporary files, never production CLI JSON or Golden.
package main

import (
	"encoding/json"
	"fmt"
	"github.com/xulu199705/psdana/go/qam"
	"os"
)

type complexArray struct {
	Real []float64 `json:"real"`
	Imag []float64 `json:"imag"`
}

func array(x []complex128) complexArray {
	r := complexArray{make([]float64, len(x)), make([]float64, len(x))}
	for k, z := range x {
		r.Real[k] = real(z)
		r.Imag[k] = imag(z)
	}
	return r
}
func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
func run() error {
	var req struct {
		Samples     complexArray  `json:"samples"`
		Config      qam.QAMConfig `json:"config"`
		DCMode      string        `json:"dc_mode"`
		Taps        []float64     `json:"taps"`
		StagesOnly  bool          `json:"stages_only"`
		SummaryOnly bool          `json:"summary_only"`
	}
	req.Config = qam.DefaultQAMConfig()
	if err := json.NewDecoder(os.Stdin).Decode(&req); err != nil {
		return err
	}
	req.Config.DCMode = req.DCMode
	if len(req.Samples.Real) != len(req.Samples.Imag) {
		return fmt.Errorf("IQ length mismatch")
	}
	if req.SummaryOnly {
		original := make([]complex128, len(req.Samples.Real))
		for k := range original {
			original[k] = complex(req.Samples.Real[k], req.Samples.Imag[k])
		}
		recovered, err := qam.RecoverSymbols(original, req.Config)
		if err != nil {
			d := map[string]any{"status": "unreliable"}
			if recovery, ok := err.(*qam.RecoveryError); ok {
				d = recovery.Diagnostics
			}
			return json.NewEncoder(os.Stdout).Encode(map[string]any{"accepted": false, "diagnostics": d, "error": err.Error(), "rejected_search": map[string]any{"timing_phase_up": recovered.Timing.PhaseUp, "timing_curve": recovered.Timing.CurveEVMPct, "raw_symbols": array(recovered.Timing.SymbolsRaw), "coarse_hz": recovered.CFO.CoarseHz, "coarse_scores": recovered.CFO.CoarseEVMPct, "fine_hz": recovered.CFO.FineHz, "fine_scores": recovered.CFO.FineEVMPct}})
		}
		r, err := qam.BuildQAMResult(recovered, len(original), req.Config)
		if err != nil {
			return err
		}
		return json.NewEncoder(os.Stdout).Encode(map[string]any{"accepted": true, "result": r})
	}
	x := make([]complex128, len(req.Samples.Real))
	for k := range x {
		x[k] = complex(req.Samples.Real[k], float64(req.Config.QSign)*req.Samples.Imag[k])
	}
	taps := req.Taps
	var err error
	if taps == nil {
		taps, err = qam.GenerateRRCTaps(req.Config.RRCBeta, req.Config.RRCSpanSymbols, req.Config.SamplesPerSymbol())
		if err != nil {
			return err
		}
	}
	matched, err := qam.MatchedFilter(x, taps)
	if err != nil {
		return err
	}
	up, err := qam.Interpolate(matched, req.Config.TimingInterp, req.Config.TimingKaiserBeta)
	if err != nil {
		return err
	}
	ih, err := qam.InterpolationTaps(req.Config.TimingInterp, req.Config.TimingKaiserBeta)
	if err != nil {
		return err
	}
	out := map[string]any{"taps": taps, "interpolation_taps": ih, "matched": array(matched), "interpolated": array(up)}
	if !req.StagesOnly {
		initial, err := qam.SearchTimingPhases(up, req.Config, nil)
		if err != nil {
			return err
		}
		out["initial_timing_curve"] = initial.CurveEVMPct
		original := make([]complex128, len(x))
		for k := range original {
			original[k] = complex(req.Samples.Real[k], req.Samples.Imag[k])
		}
		recovery, err := qam.RecoverSymbols(original, req.Config)
		if err != nil {
			return err
		}
		result, err := qam.BuildQAMResult(recovery, len(x), req.Config)
		if err != nil {
			return err
		}
		out["raw_symbols"] = array(recovery.Timing.SymbolsRaw)
		out["scalar"] = recovery.CFO.ScalarResult
		out["result"] = result
		c := recovery.CFO
		out["cfo_coarse_hz"] = c.CoarseHz
		out["cfo_coarse_scores"] = c.CoarseEVMPct
		out["cfo_fine_hz"] = c.FineHz
		out["cfo_fine_scores"] = c.FineEVMPct
	}
	return json.NewEncoder(os.Stdout).Encode(out)
}
