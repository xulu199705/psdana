package psd

import (
	"fmt"
	"math"
)

// ComputeComplexPSD computes shifted two-sided PSD for explicitly complex samples.
// Each call owns its FFT plan and buffers; simultaneous calls do not share state.
func ComputeComplexPSD(samples []complex128, c PSDConfig) (PSDResult, error) {
	for j, v := range samples {
		if !finite(real(v)) || !finite(imag(v)) {
			return PSDResult{}, fmt.Errorf("sample %d contains NaN/Inf", j)
		}
	}
	n, err := c.validate(len(samples))
	if err != nil {
		return PSDResult{}, err
	}
	w, energy, gain, enbw := makeWindow(n, c)
	denominator := c.FS * energy
	plan := complexPlan(n)
	buffer := make([]complex128, n)
	density := make([]float64, n)
	hop := n
	if n < len(samples) {
		hop = n - int(math.Floor(float64(n)*c.Overlap))
	}
	for start := 0; start <= len(samples)-n; start += hop {
		mean := complex(0, 0)
		if c.Detrend == "mean" {
			for _, v := range samples[start : start+n] {
				mean += v
			}
			mean /= complex(float64(n), 0)
		}
		for j := range buffer {
			buffer[j] = (samples[start+j] - mean) * complex(w[j], 0)
		}
		spectrum := plan.Coefficients(buffer, buffer)
		for j, v := range spectrum {
			density[j] += (real(v)*real(v) + imag(v)*imag(v)) / denominator
		}
	}
	return finish(density, n, len(samples), c, energy, gain, enbw, true), nil
}

// ComputeRealPSD computes one-sided PSD; DC/even Nyquist retain their power.
func ComputeRealPSD(samples []float64, c PSDConfig) (PSDResult, error) {
	for j, v := range samples {
		if !finite(v) {
			return PSDResult{}, fmt.Errorf("sample %d contains NaN/Inf", j)
		}
	}
	n, err := c.validate(len(samples))
	if err != nil {
		return PSDResult{}, err
	}
	w, energy, gain, enbw := makeWindow(n, c)
	denominator := c.FS * energy
	var transform func([]complex128, []float64)
	if realNeedsComplex(n) {
		plan := complexPlan(n)
		complexBuffer := make([]complex128, n)
		transform = func(dst []complex128, src []float64) {
			for j, v := range src {
				complexBuffer[j] = complex(v, 0)
			}
			plan.Coefficients(complexBuffer, complexBuffer)
			copy(dst, complexBuffer[:len(dst)])
		}
	} else {
		plan := realPlan(n)
		transform = func(dst []complex128, src []float64) { plan.Coefficients(dst, src) }
	}
	buffer := make([]float64, n)
	spectrum := make([]complex128, n/2+1)
	density := make([]float64, len(spectrum))
	hop := n
	if n < len(samples) {
		hop = n - int(math.Floor(float64(n)*c.Overlap))
	}
	for start := 0; start <= len(samples)-n; start += hop {
		mean := 0.0
		if c.Detrend == "mean" {
			for _, v := range samples[start : start+n] {
				mean += v
			}
			mean /= float64(n)
		}
		for j := range buffer {
			buffer[j] = (samples[start+j] - mean) * w[j]
		}
		transform(spectrum, buffer)
		for j, v := range spectrum {
			density[j] += (real(v)*real(v) + imag(v)*imag(v)) / denominator
		}
	}
	return finish(density, n, len(samples), c, energy, gain, enbw, false), nil
}
