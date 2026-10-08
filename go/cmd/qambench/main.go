// qambench measures prepared identical IQ buffers, excluding process/I/O/JSON.
package main

import (
	"encoding/json"
	"fmt"
	"github.com/xulu199705/psdana/go/psd"
	"github.com/xulu199705/psdana/go/qam"
	"os"
	"runtime"
	"sort"
	"time"
)

type request struct {
	Real, Imag         []float64
	Config             qam.QAMConfig
	DCMode             string
	Repeats, FFTPoints int
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
func percentile(x []float64, p float64) float64 {
	index := float64(len(x)-1) * p
	i := int(index)
	if i == len(x)-1 {
		return x[i]
	}
	return x[i] + (x[i+1]-x[i])*(index-float64(i))
}
func run() error {
	var req request
	if err := json.NewDecoder(os.Stdin).Decode(&req); err != nil {
		return err
	}
	if req.Repeats < 3 || len(req.Real) != len(req.Imag) {
		return fmt.Errorf("invalid benchmark request")
	}
	req.Config.DCMode = req.DCMode
	c := req.Config
	x := make([]complex128, len(req.Real))
	for k := range x {
		x[k] = complex(req.Real[k], req.Imag[k])
	}
	req.Real = nil
	req.Imag = nil
	r, err := qam.RecoverSymbols(x, c)
	if err != nil {
		return err
	}
	h, err := qam.GenerateRRCTaps(c.RRCBeta, c.RRCSpanSymbols, c.SamplesPerSymbol())
	if err != nil {
		return err
	}
	matched, err := qam.MatchedFilter(x, h)
	if err != nil {
		return err
	}
	up, err := qam.Interpolate(matched, c.TimingInterp, c.TimingKaiserBeta)
	if err != nil {
		return err
	}
	pc := psd.DefaultConfig()
	pc.FS = c.SampleRateHz
	pc.FFTPoints = psd.FFTPoints{N: req.FFTPoints}
	rows := []map[string]any{}
	record := func(stage string, op func() error) error {
		// Windows wall-clock granularity can quantize a short pilot to zero.
		// Calibrate batches to >=50ms instead of inferring from one short call.
		batch := 1
		for {
			pilot := time.Now()
			for j := 0; j < batch; j++ {
				if err := op(); err != nil {
					return err
				}
			}
			if time.Since(pilot) >= 50*time.Millisecond {
				break
			}
			if batch >= 65536 {
				return fmt.Errorf("timer calibration failed for %s", stage)
			}
			batch *= 2
		}
		times := []float64{}
		var bytes, allocs float64
		for i := 0; i < req.Repeats; i++ {
			var before, after runtime.MemStats
			runtime.ReadMemStats(&before)
			start := time.Now()
			var err error
			for j := 0; j < batch; j++ {
				if err = op(); err != nil {
					break
				}
			}
			elapsed := time.Since(start).Seconds() / float64(batch)
			runtime.ReadMemStats(&after)
			if err != nil {
				return err
			}
			times = append(times, elapsed*1000)
			bytes += float64(after.TotalAlloc-before.TotalAlloc) / float64(batch)
			allocs += float64(after.Mallocs-before.Mallocs) / float64(batch)
		}
		sort.Float64s(times)
		median := percentile(times, .5)
		if median <= 0 {
			return fmt.Errorf("timer resolution insufficient for %s", stage)
		}
		rows = append(rows, map[string]any{"stage": stage, "median_ms": median, "p90_ms": percentile(times, .9), "repeats": req.Repeats, "operations_per_repeat": batch, "samples_per_second": float64(len(x)) / (median / 1000), "symbols_per_second": float64(len(r.CFO.Equalized)) / (median / 1000), "bytes_per_op": float64(bytes) / float64(req.Repeats), "allocations_per_op": float64(allocs) / float64(req.Repeats)})
		return nil
	}
	ops := []struct {
		name string
		op   func() error
	}{
		{"psd_core", func() error { _, e := psd.ComputeComplexPSD(x, pc); return e }},
		{"rrc_taps", func() error { _, e := qam.GenerateRRCTaps(c.RRCBeta, c.RRCSpanSymbols, c.SamplesPerSymbol()); return e }},
		{"matched_rrc", func() error { _, e := qam.MatchedFilter(x, h); return e }},
		{"fractional_interpolation", func() error { _, e := qam.Interpolate(matched, c.TimingInterp, c.TimingKaiserBeta); return e }},
		{"timing_search", func() error {
			_, e := qam.SearchTimingPhases(up, c, nil)
			if e == nil && c.DCMode == qam.DecisionDirectedJoint && c.EnableCFOCorrection {
				_, e = qam.SearchTimingPhases(up, c, r.CFO.FrequencyHz)
			}
			return e
		}},
		{"cfo_search", func() error { _, e := qam.SearchResidualCFO(r.Timing.SymbolsRaw, c); return e }},
		{"scalar_fit", func() error {
			_, e := qam.ScalarQAMFit(r.CFO.Equalized, qam.ScalarConfig{Order: c.QAMOrder, Iterations: c.ScalarFitIterations, DCMode: c.DCMode})
			return e
		}},
		{"error_metrics", func() error { _, e := qam.ComputeQAMMetrics(r.CFO.Equalized, r.CFO.Decisions); return e }},
		{"receiver_total", func() error { _, e := qam.AnalyzeQAM(x, c); return e }},
		{"psd_qam_total", func() error {
			_, e := psd.ComputeComplexPSD(x, pc)
			if e == nil {
				_, e = qam.AnalyzeQAM(x, c)
			}
			return e
		}},
	}
	for _, op := range ops {
		if err := record(op.name, op.op); err != nil {
			return err
		}
	}
	return json.NewEncoder(os.Stdout).Encode(map[string]any{"language": "go", "go_version": runtime.Version(), "input_samples": len(x), "fft_points": req.FFTPoints, "mode": c.DCMode, "analysis_symbols": len(r.CFO.Equalized), "rows": rows, "worker_peak_working_set_bytes": nil, "memory_scope": "B/op and allocations/op use per-operation runtime total-allocation deltas; process peak not measured"})
}
