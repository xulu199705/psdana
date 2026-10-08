package psd

import (
	"fmt"
	"math"
)

func validateNumericScale(fs float64, n int, denominator, enbw float64) error {
	if !finite(denominator) || denominator <= 0 || !finite(enbw) || enbw <= 0 || fs/float64(n) == 0 || fs/2 == 0 {
		return fmt.Errorf("sample rate/window normalization exceeds supported float64 range")
	}
	return nil
}

func makeWindow(n int, c PSDConfig) ([]float64, float64, float64, float64) {
	w := make([]float64, n)
	sum, energy := 0.0, 0.0
	for j := range w {
		v := 1.0
		if c.Window == "hann" {
			v = 0.5 - 0.5*math.Cos(2*math.Pi*float64(j)/float64(n))
		}
		w[j] = v
		sum += v
		energy += v * v
	}
	return w, energy, sum / float64(n), c.FS * energy / (sum * sum)
}
