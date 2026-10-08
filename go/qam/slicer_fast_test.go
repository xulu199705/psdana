package qam

import (
	"math"
	"math/rand"
	"testing"
)

func TestFastSlicerAgainstBrute(t *testing.T) {
	rng := rand.New(rand.NewSource(212))
	for _, order := range []int{16, 64, 256} {
		points, _ := GenerateConstellation(order)
		root := int(math.Sqrt(float64(order)))
		levels := make([]float64, root)
		for k := range levels {
			levels[k] = real(points[k*root])
		}
		values := []float64{0, -math.MaxFloat64, math.MaxFloat64}
		values = append(values, levels...)
		for k := 0; k < root-1; k++ {
			mid := (levels[k] + levels[k+1]) / 2
			values = append(values, mid, math.Nextafter(mid, math.Inf(-1)), math.Nextafter(mid, math.Inf(1)))
		}
		for k := 0; k < 100000; k++ {
			values = append(values, 8*rng.Float64()-4)
		}
		for _, v := range values {
			best := 0
			for k := 1; k < root; k++ {
				if math.Abs(v-levels[k]) < math.Abs(v-levels[best]) {
					best = k
				}
			}
			if v <= levels[0] {
				best = 0
			}
			if v >= levels[root-1] {
				best = root - 1
			}
			if got := nearestLevel(v, levels); got != best {
				t.Fatal(order, v, got, best)
			}
		}
	}
}
