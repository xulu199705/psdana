package psd

import (
	"fmt"
	"math"
	"math/cmplx"
	"testing"
)

func directDFT(x []complex128) []complex128 {
	out := make([]complex128, len(x))
	for k := range out {
		for j, v := range x {
			out[k] += v * cmplx.Exp(complex(0, -2*math.Pi*float64(k*j)/float64(len(x))))
		}
	}
	return out
}

func TestFFTContract(t *testing.T) {
	for _, n := range []int{1, 2, 3, 15, 31, 255, 256, 333, 999, 1024} {
		for _, kind := range []string{"impulse", "constant", "positive", "negative"} {
			t.Run(fmt.Sprintf("%s/%d", kind, n), func(t *testing.T) {
				x := make([]complex128, n)
				for j := range x {
					switch kind {
					case "impulse":
						if j == 0 {
							x[j] = 1
						}
					case "constant":
						x[j] = 1
					case "positive":
						x[j] = cmplx.Exp(complex(0, 2*math.Pi*float64(j)/float64(n)))
					case "negative":
						x[j] = cmplx.Exp(complex(0, -2*math.Pi*float64(j)/float64(n)))
					}
				}
				actual := complexPlan(n).Coefficients(nil, x)
				expected := make([]complex128, n)
				k := 0
				switch kind {
				case "impulse":
					for j := range expected {
						expected[j] = 1
					}
				case "constant":
					expected[0] = complex(float64(n), 0)
				case "positive":
					k = 1 % n
					expected[k] = complex(float64(n), 0)
				case "negative":
					k = (n - 1) % n
					expected[k] = complex(float64(n), 0)
				}
				for j := range expected {
					if cmplx.Abs(actual[j]-expected[j]) > 2e-10*float64(n) {
						t.Fatalf("bin=%d actual=%v expected=%v", j, actual[j], expected[j])
					}
				}
			})
		}
		t.Run(fmt.Sprintf("real-vs-independent-dft/%d", n), func(t *testing.T) {
			x := make([]float64, n)
			c := make([]complex128, n)
			for j := range x {
				x[j] = math.Sin(float64(j)*0.31) + 0.2*math.Cos(float64(j)*0.17)
				c[j] = complex(x[j], 0)
			}
			expected := directDFT(c)
			actual := realPlan(n).Coefficients(nil, x)
			if len(actual) != n/2+1 {
				t.Fatal("wrong real FFT length")
			}
			for j, v := range actual {
				if cmplx.Abs(v-expected[j]) > 2e-10*float64(n) {
					t.Fatalf("bin=%d actual=%v expected=%v", j, v, expected[j])
				}
			}
		})
	}
}
