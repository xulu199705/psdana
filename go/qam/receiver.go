package qam

const AlgorithmVersion = "qam-blind-scalar-1"
const JointAlgorithmVersion = "qam-blind-scalar-2"

func occupied(indices []int) int {
	m := map[int]bool{}
	for _, v := range indices {
		m[v] = true
	}
	return len(m)
}

// RecoverSymbols returns full accepted symbols and bounded search evidence.
// Input IQ is never modified; no external process is invoked.
func RecoverSymbols(samples []complex128, c QAMConfig) (RecoveryResult, error) {
	if err := c.Validate(); err != nil {
		return RecoveryResult{}, err
	}
	if err := validateSamples(samples, 1); err != nil {
		return RecoveryResult{}, err
	}
	x := make([]complex128, len(samples))
	for k, z := range samples {
		x[k] = complex(real(z), float64(c.QSign)*imag(z))
	}
	taps, err := GenerateRRCTaps(c.RRCBeta, c.RRCSpanSymbols, c.SamplesPerSymbol())
	if err != nil {
		return RecoveryResult{}, err
	}
	matched, err := MatchedFilter(x, taps)
	if err != nil {
		return RecoveryResult{}, err
	}
	up, err := Interpolate(matched, c.TimingInterp, c.TimingKaiserBeta)
	if err != nil {
		return RecoveryResult{}, err
	}
	timing, err := SearchTimingPhases(up, c, nil)
	if err != nil {
		return RecoveryResult{}, err
	}
	fit, err := SearchResidualCFO(timing.SymbolsRaw, c)
	if err != nil {
		return RecoveryResult{}, err
	}
	r := RecoveryResult{Timing: timing, CFO: fit, InitialPhaseUp: timing.PhaseUp, InitialEVMPct: timing.EVMPct, RRCTapCount: len(taps)}
	if c.EnableCFOCorrection {
		r.CFOSearchEvaluations = c.CFOCoarseSteps + c.CFOFineSteps
	}
	if c.DCMode == DecisionDirectedJoint && c.EnableCFOCorrection {
		timing, err = SearchTimingPhases(up, c, fit.FrequencyHz)
		if err != nil {
			return RecoveryResult{}, err
		}
		r.Timing = timing
		if timing.PhaseUp != r.InitialPhaseUp {
			fit, err = SearchResidualCFO(timing.SymbolsRaw, c)
			if err != nil {
				return RecoveryResult{}, err
			}
			r.CFO = fit
			r.CFOSearchEvaluations *= 2
		}
	}
	if fit.EVMPct > c.MaxDecisionEVMPct || occupied(fit.Indices) < 8 {
		return r, &RecoveryError{map[string]any{"status": "unreliable", "evm_pct_rms": fit.EVMPct, "occupied_decision_points": occupied(fit.Indices), "frequency_error_hz": fit.FrequencyHz, "timing_offset_symbols": float64(r.Timing.PhaseUp) / float64(c.SamplesPerSymbol()*c.TimingInterp), "dc_estimation_mode": c.DCMode, "cfo_search_boundary_hit": fit.BoundaryHit}}
	}
	return r, nil
}

// AnalyzeQAM independently performs matched RRC, fractional timing, residual
// CFO and scalar fitting. Blind candidate/warning does not certify TX lock.
func AnalyzeQAM(samples []complex128, c QAMConfig) (QAMResult, error) {
	r, err := RecoverSymbols(samples, c)
	if err != nil {
		return QAMResult{}, err
	}
	return BuildQAMResult(r, len(samples), c)
}

// BuildQAMResult formats an accepted recovery without rerunning the receiver.
func BuildQAMResult(r RecoveryResult, inputCount int, c QAMConfig) (QAMResult, error) {
	if err := c.Validate(); err != nil {
		return QAMResult{}, err
	}
	f, t := r.CFO, r.Timing
	metrics, err := ComputeQAMMetrics(f.Equalized, f.Decisions)
	if err != nil {
		return QAMResult{}, err
	}
	count := len(f.Equalized)
	n := count
	if n > c.ConstellationPoints {
		n = c.ConstellationPoints
	}
	ci, cq := make([]float64, n), make([]float64, n)
	selectionStep := 0.0
	if n > 1 {
		selectionStep = float64(count-1) / float64(n-1)
	}
	for k := 0; k < n; k++ {
		index := 0
		if n > 1 {
			index = int(float64(k) * selectionStep)
		}
		if k == n-1 && n > 1 {
			index = count - 1
		} // np.linspace sets the endpoint exactly.
		ci[k] = real(f.Equalized[index])
		cq[k] = imag(f.Equalized[index])
	}
	ideal, _ := GenerateConstellation(c.QAMOrder)
	ii, iq := make([]float64, len(ideal)), make([]float64, len(ideal))
	for k, z := range ideal {
		ii[k] = real(z)
		iq[k] = imag(z)
	}
	warnings := []string{}
	if f.BoundaryHit {
		warnings = append(warnings, "CFO estimate is near search boundary; out-of-range recovery is not guaranteed")
	}
	split := func(z complex128) map[string]float64 { return map[string]float64{"real": real(z), "imag": imag(z)} }
	phase, period := float64(t.PhaseUp), float64(c.SamplesPerSymbol()*c.TimingInterp)
	d := map[string]any{"algorithm_version": AlgorithmVersion, "config": c, "metric_reference": "decision_directed", "phase_ambiguity_degrees": 90, "status": "candidate", "warnings": warnings,
		"complex_gain": split(f.ComplexGain), "dc_offset": split(f.DC), "coarse_phase_deg": f.CoarsePhaseDeg, "timing_offset_samples": phase / float64(c.TimingInterp), "timing_evm_pct": t.EVMPct, "timing_candidates": int(period), "timing_phase_up": t.PhaseUp, "timing_curve_evm_pct": t.CurveEVMPct,
		"trim_symbols_per_edge": t.TrimSymbols, "analysis_first_symbol_index": t.FirstSymbolIndex, "valid_symbol_count": count, "input_sample_count": inputCount, "rrc_tap_count": r.RRCTapCount, "rrc_group_delay_samples": (r.RRCTapCount - 1) / 2,
		"cfo_correction_enabled": c.EnableCFOCorrection, "cfo_search_boundary_hit": f.BoundaryHit, "cfo_estimate_hz": f.FrequencyHz, "cfo_search_range_hz": []float64{-c.MaxResidualCFOHz, c.MaxResidualCFOHz}, "cfo_search_symbol_count": f.SearchSymbols, "cfo_grid_resolution_hz": f.GridResolutionHz,
		"observation_seconds": float64(count-1) / c.SymbolRateHz, "occupied_decision_points": occupied(f.Indices), "constellation_selection": "uniform_indices_inclusive_endpoints", "dc_estimation_mode": c.DCMode}
	if c.DCMode == DecisionDirectedJoint {
		if !f.JointConverged {
			warnings = append(warnings, "Joint decisions did not stabilize within the iteration limit")
		}
		d["algorithm_version"] = JointAlgorithmVersion
		d["forward_gain"] = split(f.ForwardGain)
		d["joint_fit_iterations"] = f.JointIterations
		d["joint_fit_converged"] = f.JointConverged
		d["dc_reference"] = "symbol_domain_after_CFO_derotation_before_scalar"
		d["cfo_estimation_uncertainty_hz"] = nil
		d["cfo_estimation_error_hz"] = nil
		d["cfo_search_evaluations"] = r.CFOSearchEvaluations
		d["timing_initial_offset_symbols"] = float64(r.InitialPhaseUp) / period
		d["timing_initial_evm_pct"] = r.InitialEVMPct
		d["timing_cfo_refinement_enabled"] = c.EnableCFOCorrection
		d["timing_search_sweeps"] = 1
		if c.EnableCFOCorrection {
			d["timing_search_sweeps"] = 2
		}
		d["timing_fit_mode"] = c.DCMode
		d["cfo_fit_mode"] = c.DCMode
	}
	d["warnings"] = warnings
	if len(warnings) > 0 {
		d["status"] = "warning"
	}
	return QAMResult{c.QAMOrder, c.SampleRateHz, c.SymbolRateHz, c.SamplesPerSymbol(), metrics, f.FrequencyHz, phase / period, count, ci, cq, ii, iq, d}, nil
}
