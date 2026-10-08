package psd

import (
	"fmt"
	"math"
	"math/cmplx"
	"reflect"
	"sync"
	"testing"
)

func closeValue(t *testing.T, actual, expected, tolerance float64) {
	t.Helper()
	if math.IsNaN(actual) || math.Abs(actual-expected) > tolerance {
		t.Fatalf("actual=%.17g expected=%.17g tolerance=%g", actual, expected, tolerance)
	}
}
func tone(n, k int, amplitude float64) []complex128 {
	x := make([]complex128, n)
	for j := range x {
		x[j] = complex(amplitude, 0) * cmplx.Exp(complex(0, 2*math.Pi*float64(k*j)/float64(n)))
	}
	return x
}
func peak(r PSDResult) int {
	j := 0
	for k, p := range r.PSDLinear {
		if p > r.PSDLinear[j] {
			j = k
		}
	}
	return j
}

func TestWindowAndParsevalIndependent(t *testing.T) {
	for _, n := range []int{1, 2, 3, 255, 256, 333, 999, 1024} {
		for _, window := range []string{"hann", "rectangle"} {
			for _, kind := range []string{"real", "complex"} {
				t.Run(fmt.Sprintf("%s/%s/%d", kind, window, n), func(t *testing.T) {
					c := DefaultConfig()
					c.Window = window
					x := make([]complex128, n)
					xr := make([]float64, n)
					for j := range x {
						xr[j] = 0.2 + math.Sin(float64(j)*0.47)
						x[j] = complex(xr[j], 0.3*math.Cos(float64(j)*0.23))
					}
					var r PSDResult
					var err error
					if kind == "real" {
						r, err = ComputeRealPSD(xr, c)
					} else {
						r, err = ComputeComplexPSD(x, c)
					}
					if n == 1 && window == "hann" {
						if err == nil {
							t.Fatal("Hann N=1 accepted")
						}
						return
					}
					if err != nil {
						t.Fatal(err)
					}
					energy, weighted, sum := 0.0, 0.0, 0.0
					for j := 0; j < n; j++ {
						w := 1.0
						if window == "hann" {
							w = 0.5 - 0.5*math.Cos(2*math.Pi*float64(j)/float64(n))
						}
						v := xr[j] * xr[j]
						if kind == "complex" {
							v += imag(x[j]) * imag(x[j])
						}
						energy += w * w
						sum += w
						weighted += v * w * w
					}
					closeValue(t, r.IntegratedPower, weighted/energy, 2e-13)
					closeValue(t, r.WindowPowerSum, energy, 2e-12)
					closeValue(t, r.CoherentGain, sum/float64(n), 1e-14)
					bins := 1.0
					if window == "hann" {
						bins = 1.5
						if n == 2 {
							bins = 2
						}
					}
					closeValue(t, r.ENBWHZ, c.FS/float64(n)*bins, 1e-6)
				})
			}
		}
	}
}

func TestFullScaleAndTwoTones(t *testing.T) {
	for _, window := range []string{"hann", "rectangle"} {
		for _, k := range []int{-256, 256} {
			t.Run(fmt.Sprintf("%s/%d", window, k), func(t *testing.T) {
				c := DefaultConfig()
				c.Window = window
				r, err := ComputeComplexPSD(tone(1024, k, 1), c)
				if err != nil {
					t.Fatal(err)
				}
				j := peak(r)
				closeValue(t, r.FrequencyHz[j], float64(k)*c.FS/1024, 1e-8)
				closeValue(t, r.RBWPowerDBFS[j], 0, 1e-10)
				closeValue(t, r.IntegratedPower, 1, 1e-13)
			})
		}
		t.Run("real/"+window, func(t *testing.T) {
			c := DefaultConfig()
			c.Window = window
			x := tone(1024, 256, 1)
			xr := make([]float64, len(x))
			for j, v := range x {
				xr[j] = real(v)
			}
			r, err := ComputeRealPSD(xr, c)
			if err != nil {
				t.Fatal(err)
			}
			closeValue(t, r.RBWPowerDBFS[peak(r)], 0, 1e-10)
			closeValue(t, r.IntegratedPower, 0.5, 1e-13)
		})
		t.Run("two-tones/"+window, func(t *testing.T) {
			c := DefaultConfig()
			c.Window = window
			x, y := tone(1024, 128, 0.75), tone(1024, -64, 0.25)
			for j := range x {
				x[j] += y[j]
			}
			r, err := ComputeComplexPSD(x, c)
			if err != nil {
				t.Fatal(err)
			}
			closeValue(t, r.IntegratedPower, 0.625, 1e-13)
			closeValue(t, r.RBWPowerDBFS[128+512], 20*math.Log10(0.75), 1e-10)
			closeValue(t, r.RBWPowerDBFS[-64+512], 20*math.Log10(0.25), 1e-10)
		})
	}
}

func TestRealEndpoints(t *testing.T) {
	for _, n := range []int{1, 2, 3, 31, 32, 255, 256} {
		c := DefaultConfig()
		c.Window = "rectangle"
		x := make([]float64, n)
		for j := range x {
			x[j] = 1
		}
		dc, err := ComputeRealPSD(x, c)
		if err != nil {
			t.Fatal(err)
		}
		closeValue(t, dc.PSDLinear[0], float64(n)/c.FS, 1e-20)
		closeValue(t, dc.IntegratedPower, 1, 1e-13)
		for j := range x {
			x[j] = math.Cos(2 * math.Pi * float64((n/2)*j) / float64(n))
		}
		r, err := ComputeRealPSD(x, c)
		if err != nil {
			t.Fatal(err)
		}
		power := 0.5
		if n%2 == 0 || n == 1 {
			power = 1
		}
		closeValue(t, r.IntegratedPower, power, 1e-13)
		closeValue(t, r.PSDLinear[len(r.PSDLinear)-1], float64(n)*power/c.FS, 1e-18)
	}
}

func TestWelchLinearMeanAndTail(t *testing.T) {
	c := DefaultConfig()
	c.Window = "rectangle"
	c.FFTPoints = FFTPoints{N: 32}
	c.Overlap = 0
	x := append(tone(32, 8, 1), tone(32, 8, 0.1)...)
	r, err := ComputeComplexPSD(x, c)
	if err != nil {
		t.Fatal(err)
	}
	closeValue(t, r.IntegratedPower, 0.505, 1e-13)
	closeValue(t, r.RBWPowerDBFS[peak(r)], 10*math.Log10(0.505), 1e-11)
	c = DefaultConfig()
	c.FFTPoints = FFTPoints{N: 5}
	r, err = ComputeRealPSD(make([]float64, 15), c)
	if err != nil {
		t.Fatal(err)
	}
	if r.OverlapSamples != 2 || r.HopSize != 3 || r.SegmentCount != 4 || r.UsedSampleCount != 14 || r.DiscardedTailSamples != 1 {
		t.Fatal(r)
	}
	c.FFTPoints = FFTPoints{N: 15}
	r, err = ComputeRealPSD(make([]float64, 15), c)
	if err != nil || r.Method != "periodogram" {
		t.Fatal("N=M must be Periodogram", err)
	}
}

func TestZeroDCDetrendAndNoClipping(t *testing.T) {
	c := DefaultConfig()
	x := make([]complex128, 64)
	r, err := ComputeComplexPSD(x, c)
	if err != nil {
		t.Fatal(err)
	}
	for j, p := range r.PSDLinear {
		if p != 0 || !math.IsInf(r.RBWPowerDBFS[j], -1) {
			t.Fatal("zero PSD must be exact")
		}
	}
	for j := range x {
		x[j] = 2 + 1i
	}
	c.Detrend = "mean"
	c.FFTPoints = FFTPoints{N: 32}
	r, err = ComputeComplexPSD(x, c)
	if err != nil || r.IntegratedPower != 0 {
		t.Fatal("mean removal failed", err)
	}
	c = DefaultConfig()
	r, err = ComputeComplexPSD(tone(64, 16, 2), c)
	if err != nil {
		t.Fatal(err)
	}
	closeValue(t, r.RBWPowerDBFS[peak(r)], 10*math.Log10(4), 1e-11)
	// Complex dtype with zero imag remains two-sided and P_FS=1.
	r, err = ComputeComplexPSD([]complex128{1, 1}, c)
	if err != nil || r.InputType != "complex" || r.ReferencePower != 1 || len(r.PSDLinear) != 2 {
		t.Fatal("input type inferred from imag", err)
	}
}

func TestInvalidConfigAndSamples(t *testing.T) {
	cases := []PSDConfig{{}}
	for _, change := range []func(*PSDConfig){func(c *PSDConfig) { c.FS = 0 }, func(c *PSDConfig) { c.FS = math.Inf(1) }, func(c *PSDConfig) { c.FS = math.NaN() }, func(c *PSDConfig) { c.Window = "symmetric_hann" }, func(c *PSDConfig) { c.Detrend = "linear" }, func(c *PSDConfig) { c.Overlap = 1 }, func(c *PSDConfig) { c.Overlap = -0.1 }, func(c *PSDConfig) { c.Overlap = math.NaN() }, func(c *PSDConfig) { c.FFTPoints = FFTPoints{N: 17} }, func(c *PSDConfig) { c.FFTPoints = FFTPoints{N: -1} }, func(c *PSDConfig) { c.FFTPoints = FFTPoints{All: true, N: 3} }} {
		c := DefaultConfig()
		change(&c)
		cases = append(cases, c)
	}
	for j, c := range cases {
		t.Run(fmt.Sprint(j), func(t *testing.T) {
			if _, err := ComputeRealPSD(make([]float64, 16), c); err == nil {
				t.Fatal("invalid config accepted")
			}
			if _, err := ComputeComplexPSD(make([]complex128, 16), c); err == nil {
				t.Fatal("invalid config accepted")
			}
		})
	}
	for _, x := range [][]float64{nil, {math.NaN()}, {math.Inf(-1)}} {
		if _, err := ComputeRealPSD(x, DefaultConfig()); err == nil {
			t.Fatal("invalid sample accepted")
		}
	}
	if _, err := ComputeComplexPSD([]complex128{complex(0, math.Inf(1))}, DefaultConfig()); err == nil {
		t.Fatal("invalid imag accepted")
	}
}

func TestLargePrimeFactorRealAccuracy(t *testing.T) {
	for _, n := range []int{127, 257, 509, 1009, 8193, 5462} {
		t.Run(fmt.Sprint(n), func(t *testing.T) {
			c := DefaultConfig()
			c.Detrend = "mean"
			x := make([]float64, n)
			mean := 0.0
			for j := range x {
				x[j] = 0.2 + math.Sin(float64(j)*0.47) + 0.3*math.Cos(float64(j)*0.123)
				mean += x[j]
			}
			mean /= float64(n)
			weighted, energy := 0.0, 0.0
			for j, v := range x {
				w := 0.5 - 0.5*math.Cos(2*math.Pi*float64(j)/float64(n))
				weighted += (v - mean) * (v - mean) * w * w
				energy += w * w
			}
			r, err := ComputeRealPSD(x, c)
			if err != nil {
				t.Fatal(err)
			}
			closeValue(t, r.IntegratedPower, weighted/energy, 2e-13)
			if !realNeedsComplex(n) {
				t.Fatal("large-prime fallback not selected")
			}
		})
	}
}

func TestInputOwnershipAndConcurrentCalls(t *testing.T) {
	x := tone(333, 17, 0.7)
	before := append([]complex128(nil), x...)
	c := DefaultConfig()
	c.FFTPoints = FFTPoints{N: 255}
	c.Detrend = "mean"
	reference, err := ComputeComplexPSD(x, c)
	if err != nil {
		t.Fatal(err)
	}
	var wg sync.WaitGroup
	for j := 0; j < 8; j++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			r, err := ComputeComplexPSD(x, c)
			if err != nil || !reflect.DeepEqual(reference, r) {
				t.Error("concurrent result mismatch", err)
			}
		}()
	}
	wg.Wait()
	if !reflect.DeepEqual(x, before) {
		t.Fatal("caller input was modified")
	}
}
