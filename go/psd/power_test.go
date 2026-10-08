package psd

import (
	"encoding/json"
	"fmt"
	"math"
	"reflect"
	"testing"
)

func syntheticPower(t *testing.T, n int, isReal bool) PSDResult {
	t.Helper()
	c := DefaultConfig()
	c.FS = float64(2 * n)
	c.Window = "rectangle"
	var r PSDResult
	var err error
	if isReal {
		r, err = ComputeRealPSD(make([]float64, n), c)
	} else {
		r, err = ComputeComplexPSD(make([]complex128, n), c)
	}
	if err != nil {
		t.Fatal(err)
	}
	for j := range r.PSDLinear {
		r.PSDLinear[j] = float64(j + 2)
		r.IntegratedPower += r.PSDLinear[j] * r.FrequencyResolutionHz
	}
	return r
}
func band(t *testing.T, r PSDResult, left, right float64) PowerResult {
	t.Helper()
	p, err := AnalyzeBandPower(r, left, right)
	if err != nil {
		t.Fatal(err)
	}
	return p
}
func TestBandFullAndPoints(t *testing.T) {
	for _, n := range []int{1, 2, 3, 4, 5, 255, 256, 333, 999} {
		for _, realInput := range []bool{false, true} {
			t.Run(fmt.Sprintf("%d/real=%t", n, realInput), func(t *testing.T) {
				r := syntheticPower(t, n, realInput)
				before, _ := json.Marshal(r)
				p := band(t, r, -r.FSHz/2, r.FSHz/2)
				closeValue(t, p.BandPowerLinear, r.IntegratedPower, 2e-14*r.IntegratedPower)
				if p.ContributingBins != n || p.IsPoint {
					t.Fatal("full band dimensions")
				}
				for _, f := range []float64{-r.FSHz / 2, 0, r.FSHz / 2} {
					p = band(t, r, f, f)
					if !p.IsPoint || p.ContributingBins != 1 || p.PeakPowerDBFS != p.AveragePowerDBFS {
						t.Fatal("point rule")
					}
				}
				closeValue(t, *p.PeakFrequencyHz, float64(n-1-n/2)*r.FrequencyResolutionHz, 0)
				after, _ := json.Marshal(r)
				if !reflect.DeepEqual(before, after) {
					t.Fatal("modified input result")
				}
			})
		}
	}
}
func TestBandFractionalNyquistAndTies(t *testing.T) {
	r := syntheticPower(t, 4, false)
	for _, v := range []struct {
		left, right, power, freq float64
		bins                     int
	}{
		{-4, -3.5, 1, -4, 1}, {3.5, 4, 1, -4, 1}, {-4, 4, 28, 2, 4},
		{-2.25, -1.75, 1.5, -2, 1}, {-3, -1, 6, -2, 1}, {-3.5, -2.5, 2.5, -2, 2}, {1.25, 1.75, 2.5, 2, 1},
	} {
		p := band(t, r, v.left, v.right)
		closeValue(t, p.BandPowerLinear, v.power, 2e-15)
		if *p.PeakFrequencyHz != v.freq || p.ContributingBins != v.bins {
			t.Fatal(v, p)
		}
	}
	for j := range r.PSDLinear {
		r.PSDLinear[j] = 1
	}
	if *band(t, r, -4, 4).PeakFrequencyHz != -4 || *band(t, r, -1, -1).PeakFrequencyHz != -2 {
		t.Fatal("lower frequency tie rule")
	}
	// Odd-length cells tile the interval without a Nyquist-centered bin.
	r = syntheticPower(t, 5, false)
	closeValue(t, band(t, r, -5, -4.5).BandPowerLinear, 1, 0)
	closeValue(t, band(t, r, 4.5, 5).BandPowerLinear, 3, 0)
}
func TestBandTonesWindowsAndWelch(t *testing.T) {
	for _, window := range []string{"hann", "rectangle"} {
		for _, points := range []FFTPoints{{All: true}, {N: 256}} {
			t.Run(fmt.Sprintf("%s/%v", window, points), func(t *testing.T) {
				c := DefaultConfig()
				c.Window = window
				c.FFTPoints = points
				r, err := ComputeComplexPSD(tone(1024, 256, 1), c)
				if err != nil {
					t.Fatal(err)
				}
				f, df := 40e6, r.FrequencyResolutionHz
				p := band(t, r, f, f)
				closeValue(t, p.PeakPowerDBFS, 0, 1e-11)
				closeValue(t, p.AveragePowerDBFS, 0, 1e-11)
				closeValue(t, band(t, r, -80e6, 80e6).AveragePowerDBFS, 0, 1e-11)
				closeValue(t, band(t, r, f-1.5*df, f+1.5*df).BandPowerLinear, 1, 2e-13)
				one := 1.0
				if window == "hann" {
					one = 2.0 / 3
				}
				closeValue(t, band(t, r, f-df/2, f+df/2).BandPowerLinear, one, 2e-13)
			})
		}
	}
	for _, window := range []string{"hann", "rectangle"} {
		c := DefaultConfig()
		c.Window = window
		x := tone(1024, 256, .8)
		second := tone(1024, -128, .3)
		for j := range x {
			x[j] += second[j]
		}
		r, err := ComputeComplexPSD(x, c)
		if err != nil {
			t.Fatal(err)
		}
		p := band(t, r, -25e6, 45e6)
		closeValue(t, p.BandPowerLinear, .73, 2e-13)
		closeValue(t, p.PeakPowerDBFS, 20*math.Log10(.8), 1e-11)
		if *p.PeakFrequencyHz != 40e6 {
			t.Fatal("two tone peak")
		}
		closeValue(t, band(t, r, -21e6, -19e6).BandPowerLinear, .09, 2e-13)
	}
}
func TestBandRealMirrorsDCAndNyquist(t *testing.T) {
	for _, n := range []int{255, 256, 333, 999} {
		for _, window := range []string{"hann", "rectangle"} {
			t.Run(fmt.Sprintf("%d/%s", n, window), func(t *testing.T) {
				c := DefaultConfig()
				c.FS = float64(n)
				c.Window = window
				x := make([]float64, n)
				for j := range x {
					x[j] = math.Cos(2 * math.Pi * 20 * float64(j) / float64(n))
				}
				r, err := ComputeRealPSD(x, c)
				if err != nil {
					t.Fatal(err)
				}
				positive, negative := band(t, r, 18.5, 21.5), band(t, r, -21.5, -18.5)
				closeValue(t, positive.BandPowerLinear, .25, 2e-14)
				closeValue(t, positive.BandPowerLinear, negative.BandPowerLinear, 2e-14)
				closeValue(t, positive.PeakPowerDBFS, -10*math.Log10(2), 1e-11)
				closeValue(t, band(t, r, -c.FS/2, c.FS/2).BandPowerLinear, .5, 2e-14)
				if *positive.PeakFrequencyHz != 20 || *negative.PeakFrequencyHz != -20 {
					t.Fatal("signed real peak")
				}
			})
		}
	}
	for _, n := range []int{1, 2, 3, 256} {
		c := DefaultConfig()
		c.FS = float64(n)
		c.Window = "rectangle"
		x := make([]float64, n)
		for j := range x {
			x[j] = 1
		}
		r, err := ComputeRealPSD(x, c)
		if err != nil {
			t.Fatal(err)
		}
		closeValue(t, band(t, r, -c.FS/2, c.FS/2).BandPowerLinear, 1, 1e-14)
		closeValue(t, band(t, r, 0, 0).AveragePowerDBFS, 10*math.Log10(2), 1e-12)
		if n%2 == 0 {
			for j := range x {
				if j%2 == 1 {
					x[j] = -1
				}
			}
			r, err = ComputeRealPSD(x, c)
			if err != nil {
				t.Fatal(err)
			}
			closeValue(t, band(t, r, -c.FS/2, c.FS/2).BandPowerLinear, 1, 1e-14)
			closeValue(t, band(t, r, -c.FS/2, -c.FS/2).BandPowerLinear, 1, 1e-14)
			closeValue(t, band(t, r, c.FS/2-.5, c.FS/2).BandPowerLinear, .5, 1e-14)
		}
	}
}
func TestBandZeroAndJSON(t *testing.T) {
	r := syntheticPower(t, 4, false)
	r.PSDLinear = []float64{0, 0, 1, 0}
	for _, bounds := range [][2]float64{{-3, -1}, {-2, -2}, {4, 4}} {
		p := band(t, r, bounds[0], bounds[1])
		if p.PeakFrequencyHz != nil || !math.IsInf(p.PeakPowerDBFS, -1) || !math.IsInf(p.AveragePowerDBFS, -1) {
			t.Fatal("false zero peak")
		}
		raw, err := json.Marshal(p)
		if err != nil {
			t.Fatal(err)
		}
		var values map[string]any
		if err = json.Unmarshal(raw, &values); err != nil {
			t.Fatal(err)
		}
		for _, key := range []string{"peak_frequency_hz", "peak_power_dbfs", "average_power_dbfs"} {
			if values[key] != nil {
				t.Fatal("expected JSON null", key)
			}
		}
	}
	for j := range r.PSDLinear {
		r.PSDLinear[j] = 0
	}
	p := band(t, r, -4, 4)
	if p.BandPowerLinear != 0 || p.PeakFrequencyHz != nil {
		t.Fatal("zero full band")
	}
	p.PeakPowerDBFS = math.Inf(1)
	if _, err := json.Marshal(p); err == nil {
		t.Fatal("nonfinite JSON accepted")
	}
}
func TestBandInvalidArgumentsAndResults(t *testing.T) {
	r := syntheticPower(t, 4, false)
	for _, v := range [][2]float64{{-5, 0}, {0, 5}, {2, -2}, {math.NaN(), 0}, {0, math.Inf(1)}, {math.Inf(-1), 0}} {
		if _, err := AnalyzeBandPower(r, v[0], v[1]); err == nil {
			t.Fatal("bad boundaries", v)
		}
	}
	for _, mutate := range []func(*PSDResult){
		func(r *PSDResult) { r.FFTSize = 0 }, func(r *PSDResult) { r.FSHz = 0 }, func(r *PSDResult) { r.ENBWHZ = math.Inf(1) },
		func(r *PSDResult) { r.FrequencyResolutionHz = 3 }, func(r *PSDResult) { r.ReferencePower = 0 }, func(r *PSDResult) { r.InputType = "iq" },
		func(r *PSDResult) { r.PSDLinear = nil }, func(r *PSDResult) { r.PSDLinear = []float64{0, -1, 0, 0} }, func(r *PSDResult) { r.PSDLinear = []float64{0, math.NaN(), 0, 0} },
		func(r *PSDResult) { r.FrequencyHz = []float64{0, 1, 2, 3} },
	} {
		bad := r
		mutate(&bad)
		if _, err := AnalyzeBandPower(bad, 0, 0); err == nil {
			t.Fatal("malformed result accepted")
		}
	}
	c := DefaultConfig()
	c.FS = 1e-9
	c.Window = "rectangle"
	r, err := ComputeComplexPSD([]complex128{1, 1, 1, 1}, c)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := AnalyzeBandPower(r, 0, math.Nextafter(c.FS/2, math.Inf(1))); err == nil {
		t.Fatal("one ULP outside fs accepted")
	}
}
func TestNumericRangeGuards(t *testing.T) {
	for _, kind := range []string{"real", "complex"} {
		for _, scenario := range []string{"samples", "mean", "fs_high", "fs_low"} {
			t.Run(kind+"/"+scenario, func(t *testing.T) {
				c := DefaultConfig()
				c.Window = "rectangle"
				value := 1.0
				switch scenario {
				case "samples":
					value = math.MaxFloat64
				case "mean":
					value = math.MaxFloat64
					c.Detrend = "mean"
				case "fs_high":
					c.FS = math.MaxFloat64
				case "fs_low":
					c.FS = math.SmallestNonzeroFloat64
				}
				var err error
				if kind == "real" {
					_, err = ComputeRealPSD([]float64{value, value, value, value}, c)
				} else {
					_, err = ComputeComplexPSD([]complex128{complex(value, 0), complex(value, 0), complex(value, 0), complex(value, 0)}, c)
				}
				if err == nil {
					t.Fatal("unrepresentable intermediates accepted")
				}
			})
		}
	}
	c := DefaultConfig()
	c.Window = "rectangle"
	r, err := ComputeComplexPSD([]complex128{1e100, 1e100, 1e100, 1e100}, c)
	if err != nil {
		t.Fatal(err)
	}
	closeValue(t, r.IntegratedPower/1e200, 1, 2e-14)
	closeValue(t, band(t, r, 0, 0).AveragePowerDBFS, 2000, 1e-11)
	if !finite(dbPower(math.MaxFloat64, .5)) {
		t.Fatal("finite power/reference produced infinite dB")
	}
	r = syntheticPower(t, 4, false)
	r.PSDLinear[0] = math.MaxFloat64
	if _, err := AnalyzeBandPower(r, -4, 4); err == nil {
		t.Fatal("band overflow accepted")
	}
}

func TestTinySampleRateAxis(t *testing.T) {
	for _, fs := range []float64{1e-308, 1e-310} {
		for _, isReal := range []bool{false, true} {
			c := DefaultConfig()
			c.FS = fs
			c.Window = "rectangle"
			var r PSDResult
			var err error
			if isReal {
				r, err = ComputeRealPSD(make([]float64, 4), c)
			} else {
				r, err = ComputeComplexPSD(make([]complex128, 4), c)
			}
			if err != nil {
				t.Fatal(err)
			}
			for j, f := range r.FrequencyHz {
				k := j
				if !isReal {
					k -= 2
				}
				if f != float64(k)*(fs/4) {
					t.Fatal("tiny fs axis")
				}
			}
			p := band(t, r, -fs/2, fs/2)
			if p.BandPowerLinear != 0 || p.PeakFrequencyHz != nil {
				t.Fatal("tiny fs zero power")
			}
		}
	}
}
