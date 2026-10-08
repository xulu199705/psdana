package qam

import (
	"fmt"
	"math"
)

// GenerateConstellation returns unit-average-power I-major/Q-minor points.
func GenerateConstellation(order int) ([]complex128, error) {
	if !validOrder(order) {
		return nil, fmt.Errorf("order must be 16, 64 or 256")
	}
	root := int(math.Sqrt(float64(order)))
	scale := math.Sqrt(2 * float64(order-1) / 3)
	points := make([]complex128, order)
	for i := 0; i < root; i++ {
		for q := 0; q < root; q++ {
			points[i*root+q] = complex(float64(2*i-root+1)/scale, float64(2*q-root+1)/scale)
		}
	}
	return points, nil
}

// SliceQAM returns nearest points and indices. Exact distance ties choose the
// lower coordinate. Finite coordinates outside the constellation saturate.
func SliceQAM(samples []complex128, order int) ([]complex128, []int, error) {
	if err := validateSamples(samples, 1); err != nil {
		return nil, nil, err
	}
	points, err := GenerateConstellation(order)
	if err != nil {
		return nil, nil, err
	}
	root := int(math.Sqrt(float64(order)))
	levels := make([]float64, root)
	for i := range levels {
		levels[i] = real(points[i*root])
	}
	d, indices := make([]complex128, len(samples)), make([]int, len(samples))
	for k, z := range samples {
		indices[k] = nearestLevel(real(z), levels)*root + nearestLevel(imag(z), levels)
		d[k] = points[indices[k]]
	}
	return d, indices, nil
}
