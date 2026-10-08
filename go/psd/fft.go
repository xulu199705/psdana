package psd

import "gonum.org/v1/gonum/dsp/fourier"

// Plans own mutable workspaces. A computation reuses its plan across segments,
// but plans are never shared between calls or goroutines.
func complexPlan(n int) *fourier.CmplxFFT { return fourier.NewCmplxFFT(n) }
func realPlan(n int) *fourier.FFT         { return fourier.NewFFT(n) }

// The v0.17 FFTPACK real general-radix path loses the Golden precision at
// N=8193 (3*2731). Conservatively route factors >31 through CmplxFFT, whose
// forward transform passes that regression. This never changes the FFT size.
func realNeedsComplex(n int) bool {
	for factor := 2; factor <= n/factor; factor++ {
		for n%factor == 0 {
			if factor > 31 {
				return true
			}
			n /= factor
		}
	}
	return n > 31
}
