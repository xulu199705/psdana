package qam

import (
	"fmt"
	"math"
)

func besselI0(x float64) float64 {
	sum, term := 1.0, 1.0
	for k := 1; k < 10000; k++ {
		term *= x * x / (4 * float64(k) * float64(k))
		sum += term
		if term <= sum*1e-16 {
			break
		}
	}
	return sum
}

// InterpolationTaps reproduces firwin(20*up+1,1/up,kaiser(beta))*up.
func InterpolationTaps(up int, beta float64) ([]float64, error) {
	if up < 1 || up > 4096 || !finite(beta) || beta < 0 || beta > 700 {
		return nil, fmt.Errorf("invalid interpolation parameters")
	}
	if up == 1 {
		return []float64{1}, nil
	}
	half := 10 * up
	h := make([]float64, 2*half+1)
	sum := 0.0
	den := besselI0(beta)
	for k := range h {
		m := float64(k - half)
		a := m / float64(up)
		s := 1.0
		if a != 0 {
			s = math.Sin(math.Pi*a) / (math.Pi * a)
		}
		r := m / float64(half)
		h[k] = s / float64(up) * besselI0(beta*math.Sqrt(math.Max(0, 1-r*r))) / den
		sum += h[k]
	}
	for k := range h {
		h[k] *= float64(up) / sum
	}
	return h, nil
}

// Interpolate matches resample_poly(x,up,1,window=(kaiser,beta),
// padtype=constant). Delay compensation cancels the one pre-padding tap:
// out[k] = sum_i x[i]*h[k+10*up-i*up]. No zero-stuffed array is allocated.
func Interpolate(samples []complex128, up int, beta float64) ([]complex128, error) {
	if err := validateSamples(samples, 1); err != nil {
		return nil, err
	}
	h, err := InterpolationTaps(up, beta)
	if err != nil {
		return nil, err
	}
	if len(samples) > int(^uint(0)>>1)/up {
		return nil, fmt.Errorf("interpolated length overflows")
	}
	if up == 1 {
		return append([]complex128(nil), samples...), nil
	}
	out := make([]complex128, len(samples)*up)
	half := 10 * up
	for k := range out {
		center := k + half
		lo := (center - (len(h) - 1) + up - 1) / up
		if center < len(h)-1 {
			lo = 0
		}
		hi := center / up
		if hi >= len(samples) {
			hi = len(samples) - 1
		}
		var z complex128
		for i := lo; i <= hi; i++ {
			z += samples[i] * complex(h[center-i*up], 0)
		}
		if !finiteComplex(z) {
			return nil, fmt.Errorf("interpolation exceeds float64 range")
		}
		out[k] = z
	}
	return out, nil
}
