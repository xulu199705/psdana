package qam

import (
	"fmt"
	"math"
)

// GenerateRRCTaps returns symmetric unit-energy RRC taps. The odd-length
// convention is span*sps+1, increased by one if even, as in Python. Group delay
// is (len(taps)-1)/2 samples. Allocation is limited to 1,048,576 taps.
func GenerateRRCTaps(beta float64, spanSymbols, sps int) ([]float64, error) {
	const limit = 1 << 20
	if !finite(beta) || beta < 0 || beta > 1 || spanSymbols < 1 || sps < 1 {
		return nil, fmt.Errorf("beta must be finite in [0,1]; span and sps must be positive")
	}
	if spanSymbols > (limit-2)/sps {
		return nil, fmt.Errorf("RRC exceeds supported tap allocation")
	}
	n := spanSymbols*sps + 1
	if n%2 == 0 {
		n++
	}
	h := make([]float64, n)
	energy := 0.0
	for k := range h {
		t := float64(k-n/2) / float64(sps)
		var value float64
		switch {
		case beta == 0:
			if t == 0 {
				value = 1
			} else {
				value = math.Sin(math.Pi*t) / (math.Pi * t)
			}
		case t == 0:
			value = 1 + beta*(4/math.Pi-1)
		case math.Abs(math.Abs(t)-1/(4*beta)) <= 8*0x1p-52*math.Max(1, math.Abs(t)):
			value = beta / math.Sqrt2 * ((1+2/math.Pi)*math.Sin(math.Pi/(4*beta)) + (1-2/math.Pi)*math.Cos(math.Pi/(4*beta)))
		default:
			value = (math.Sin(math.Pi*t*(1-beta)) + 4*beta*t*math.Cos(math.Pi*t*(1+beta))) / (math.Pi * t * (1 - math.Pow(4*beta*t, 2)))
		}
		h[k] = value
		energy += value * value
	}
	if !finite(energy) || energy <= 0 {
		return nil, fmt.Errorf("RRC normalization is nonfinite or zero")
	}
	scale := math.Sqrt(energy)
	for k := range h {
		h[k] /= scale
	}
	return h, nil
}
