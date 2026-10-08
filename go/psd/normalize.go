package psd

import "math"

func dbPower(v, reference float64) float64 {
	if v == 0 {
		return math.Inf(-1)
	}
	return 10 * math.Log10(v/reference)
}

func reverse(values []float64) {
	for i, j := 0, len(values)-1; i < j; i, j = i+1, j-1 {
		values[i], values[j] = values[j], values[i]
	}
}

func finish(density []float64, n, m int, c PSDConfig, energy, gain, enbw float64, isComplex bool) PSDResult {
	// Rotate right by floor(N/2) once per call, then normalize in place.
	// This preserves NumPy odd/even fftshift without per-segment reordering.
	if isComplex {
		reverse(density)
		reverse(density[:n/2])
		reverse(density[n/2:])
	}
	overlap := 0
	method := "periodogram"
	reference := 0.5
	kind := "real"
	if n < m {
		overlap = int(math.Floor(float64(n) * c.Overlap))
		method = "welch"
	}
	hop := n - overlap
	count := 1 + (m-n)/hop
	used := (count-1)*hop + n
	if isComplex {
		reference = 1
		kind = "complex"
	}
	size := len(density)
	r := PSDResult{FrequencyHz: make([]float64, size), PSDLinear: density, PSDDBFSPerHz: make(DBValues, size), RBWPowerDBFS: make(DBValues, size),
		FFTSize: n, FSHz: c.FS, FrequencyResolutionHz: c.FS / float64(n), ENBWHZ: enbw, CoherentGain: gain, WindowPowerSum: energy, SegmentCount: count,
		Window: c.Window, InputType: kind, ReferencePower: reference, Method: method, OverlapSamples: overlap, HopSize: hop, InputSampleCount: m, UsedSampleCount: used, DiscardedTailSamples: m - used, Detrend: c.Detrend}
	for j := range density {
		bin := j
		if isComplex {
			bin = j - n/2
		}
		p := density[j] / float64(count)
		if !isComplex && j > 0 && !(n%2 == 0 && j == n/2) {
			p *= 2
		}
		r.PSDLinear[j] = p
		r.FrequencyHz[j] = float64(bin) * r.FrequencyResolutionHz
		r.PSDDBFSPerHz[j] = dbPower(p, reference)
		r.RBWPowerDBFS[j] = dbPower(p*enbw, reference)
		r.IntegratedPower += p
	}
	r.IntegratedPower *= r.FrequencyResolutionHz
	return r
}
