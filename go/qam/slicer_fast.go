package qam

import "math"

// nearestLevel checks actual stored distances around the square-grid interval.
// Clamping before arithmetic prevents overflow and preserves lower-index ties.
func nearestLevel(v float64, levels []float64) int {
	n := len(levels)
	if v <= levels[0] {
		return 0
	}
	if v >= levels[n-1] {
		return n - 1
	}
	lo := int(math.Floor((v - levels[0]) / (levels[1] - levels[0])))
	if lo < 0 {
		lo = 0
	}
	if lo > n-2 {
		lo = n - 2
	}
	if math.Abs(v-levels[lo+1]) < math.Abs(v-levels[lo]) {
		return lo + 1
	}
	return lo
}
