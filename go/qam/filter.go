package qam

import "fmt"

// MatchedFilter implements scipy fftconvolve(samples,taps,mode="same")
// via direct convolution. The output length equals the first input length,
// including even tap lengths and zero extension at both edges.
func MatchedFilter(samples []complex128, taps []float64) ([]complex128, error) {
	if err := validateSamples(samples, 1); err != nil {
		return nil, err
	}
	if len(taps) == 0 {
		return nil, fmt.Errorf("empty FIR")
	}
	for _, v := range taps {
		if !finite(v) {
			return nil, fmt.Errorf("nonfinite FIR")
		}
	}
	out := make([]complex128, len(samples))
	offset := (len(taps) - 1) / 2
	for k := range out {
		var z complex128
		for j, h := range taps {
			i := k + offset - j
			if i >= 0 && i < len(samples) {
				z += samples[i] * complex(h, 0)
			}
		}
		if !finiteComplex(z) {
			return nil, fmt.Errorf("filter exceeds float64 range")
		}
		out[k] = z
	}
	return out, nil
}
