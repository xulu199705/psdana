package qam

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"github.com/xulu199705/psdana/go/csvio"
	"math"
	"math/cmplx"
	"math/rand"
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestReceiverGolden(t *testing.T) {
	for _, folder := range []string{"../../data/golden/qam", "../../data/golden/qam/v2", "../../data/golden/qam/v2.1.2"} {
		var index struct {
			Vectors []struct{ File, SHA256 string }
		}
		b, err := os.ReadFile(filepath.Join(folder, "index.json"))
		if err != nil {
			t.Fatal(err)
		}
		if err = json.Unmarshal(b, &index); err != nil {
			t.Fatal(err)
		}
		for _, entry := range index.Vectors {
			t.Run(filepath.Base(folder)+"/"+entry.File, func(t *testing.T) {
				var v struct {
					InputFile string `json:"input_file"`
					InputSHA  string `json:"input_sha256"`
					Format    string `json:"sample_format"`
					DCMode    string `json:"dc_mode"`
					CSV       struct {
						Format string `json:"sample_format"`
					} `json:"csv_config"`
					Config     QAMConfig          `json:"qam_config"`
					Expected   map[string]any     `json:"expected"`
					Tolerances map[string]float64 `json:"tolerances"`
				}
				path := filepath.Join(folder, entry.File)
				b, err := os.ReadFile(path)
				if err != nil {
					t.Fatal(err)
				}
				if fmt.Sprintf("%x", sha256.Sum256(b)) != entry.SHA256 {
					t.Fatal("Golden hash mismatch")
				}
				v.Config = DefaultQAMConfig()
				if err = json.Unmarshal(b, &v); err != nil {
					t.Fatal(err)
				}
				if v.DCMode != "" {
					v.Config.DCMode = v.DCMode
				}
				if v.Format == "" {
					v.Format = v.CSV.Format
				}
				source := filepath.Join(folder, filepath.FromSlash(v.InputFile))
				b, err = os.ReadFile(source)
				if err != nil {
					t.Fatal(err)
				}
				if fmt.Sprintf("%x", sha256.Sum256(b)) != v.InputSHA {
					t.Fatal("input hash mismatch")
				}
				cc := csvio.DefaultConfig()
				cc.SampleFormat = v.Format
				cc.IColumn = csvio.ParseColumn("i")
				cc.QColumn = csvio.ParseColumn("q")
				data, err := csvio.ReadCSV(source, cc)
				if err != nil {
					t.Fatal(err)
				}
				before := append([]complex128(nil), data.Complex...)
				result, err := AnalyzeQAM(data.Complex, v.Config)
				if err != nil {
					t.Fatal(err)
				}
				if !reflect.DeepEqual(before, data.Complex) {
					t.Fatal("modified input")
				}
				b, err = json.Marshal(result)
				if err != nil {
					t.Fatal(err)
				}
				var got map[string]any
				json.Unmarshal(b, &got)
				var compare func(any, any, string)
				compare = func(a, b any, field string) {
					t.Helper()
					switch e := b.(type) {
					case map[string]any:
						g, ok := a.(map[string]any)
						if !ok {
							t.Fatalf("%s type", field)
						}
						for k, v := range e {
							compare(g[k], v, k)
						}
					case []any:
						g, ok := a.([]any)
						if !ok || len(g) != len(e) {
							t.Fatalf("%s length", field)
						}
						for k, v := range e {
							compare(g[k], v, field)
						}
					case float64:
						g, ok := a.(float64)
						if !ok {
							t.Fatalf("%s type %T", field, a)
						}
						tol := 1e-10 + 1e-9*math.Abs(e)
						switch field {
						case "frequency_error_hz":
							tol = v.Tolerances["cfo_atol_hz"]
						case "sample_rate_hz", "symbol_rate_hz":
							tol = 0
						case "timing_offset_symbols", "timing_initial_offset_symbols":
							tol = v.Tolerances["timing_atol_symbols"]
						case "evm_pct_rms", "amplitude_error_pct_rms", "phase_error_pct_rms", "phase_error_deg_rms":
							tol = v.Tolerances["metric_atol"]
						case "constellation_i", "constellation_q", "ideal_i", "ideal_q", "timing_curve_evm_pct":
							tol = v.Tolerances["array_atol"] + v.Tolerances["array_rtol"]*math.Abs(e)
						}
						if g != e && math.Abs(g-e) > tol {
							t.Fatalf("%s got %.17g expected %.17g tol %.3g", field, g, e, tol)
						}
					default:
						if !reflect.DeepEqual(a, b) {
							t.Fatalf("%s got %v expected %v", field, a, b)
						}
					}
				}
				compare(got, v.Expected, "")
				closeTo(t, result.EVMPctRMS*result.EVMPctRMS, result.AmplitudeErrorPctRMS*result.AmplitudeErrorPctRMS+result.PhaseErrorPctRMS*result.PhaseErrorPctRMS, 1e-10)
			})
		}
	}
}

func TestMatchedFilterImpulse(t *testing.T) {
	for _, n := range []int{5, 32, 101} {
		for _, h := range [][]float64{{1}, {1, 2}, {1, 2, 3}, {1, 2, 3, 4, 5, 6, 7}} {
			x := make([]complex128, n)
			x[n/2] = 1 + 2i
			out, err := MatchedFilter(x, h)
			if err != nil {
				t.Fatal(err)
			}
			for k, z := range out {
				j := k + (len(h)-1)/2 - n/2
				want := complex(0, 0)
				if j >= 0 && j < len(h) {
					want = (1 + 2i) * complex(h[j], 0)
				}
				if z != want {
					t.Fatal(n, h, k, z, want)
				}
			}
		}
	}
}
func TestCarrierSignAndBoundary(t *testing.T) {
	d, _ := GenerateConstellation(64)
	rng := rand.New(rand.NewSource(18))
	symbols := make([]complex128, 4096)
	for k := range symbols {
		symbols[k] = d[rng.Intn(len(d))]
	}
	for _, mode := range []string{LegacyMean, DecisionDirectedJoint} {
		for _, hz := range []float64{0, 100, -100, 1000, -1000, 3000, -3000, 4995, -4995, 6000, -6000} {
			c := DefaultQAMConfig()
			c.DCMode = mode
			y := derotate(symbols, -hz, c.SymbolRateHz)
			r, err := SearchResidualCFO(y, c)
			if err != nil {
				t.Fatal(err)
			}
			if math.Abs(hz) <= 5000 && math.Abs(*r.FrequencyHz-hz) > 12.5 {
				t.Fatal(mode, hz, *r.FrequencyHz)
			}
			if math.Abs(hz) == 4995 && !r.BoundaryHit {
				t.Fatal("missing boundary warning")
			}
			if math.Abs(hz) > 5000 && math.Abs(*r.FrequencyHz-hz) < 500 {
				t.Fatal("out of range")
			}
		}
	}
}
func TestReceiverLimits(t *testing.T) {
	c := DefaultQAMConfig()
	for _, x := range [][]complex128{nil, make([]complex128, 100), make([]complex128, 3000), {complex(math.NaN(), 0)}} {
		if _, err := AnalyzeQAM(x, c); err == nil {
			t.Fatal("invalid input accepted")
		}
	}
	if _, err := AnalyzeQAM(make([]complex128, 3000), QAMConfig{}); err == nil {
		t.Fatal("zero config")
	}
	rng := rand.New(rand.NewSource(88))
	x := make([]complex128, 4096)
	for k := range x {
		x[k] = complex(rng.NormFloat64(), rng.NormFloat64())
	}
	for _, mode := range []string{LegacyMean, DecisionDirectedJoint} {
		c.DCMode = mode
		if _, err := AnalyzeQAM(x, c); err == nil {
			t.Fatal("noise accepted")
		}
	}
}
func TestDisabledCFOAndPolarity(t *testing.T) {
	cc := csvio.DefaultConfig()
	cc.SampleFormat = "float"
	data, err := csvio.ReadCSV("../../data/generated/qam/Q01_ideal.csv", cc)
	if err != nil {
		t.Fatal(err)
	}
	c := DefaultQAMConfig()
	c.EnableCFOCorrection = false
	c.MaxAnalysisSymbols = 1000
	c.ConstellationPoints = 1
	a, err := AnalyzeQAM(data.Complex, c)
	if err != nil {
		t.Fatal(err)
	}
	if a.FrequencyErrorHz != nil || a.RecoveredSymbolCount != 1000 || len(a.ConstellationI) != 1 {
		t.Fatal("disabled/capped")
	}
	y := make([]complex128, len(data.Complex))
	for k, z := range data.Complex {
		y[k] = cmplx.Conj(z)
	}
	c.QSign = -1
	b, err := AnalyzeQAM(y, c)
	if err != nil {
		t.Fatal(err)
	}
	if a.Metrics != b.Metrics || !reflect.DeepEqual(a.ConstellationI, b.ConstellationI) || !reflect.DeepEqual(a.ConstellationQ, b.ConstellationQ) {
		t.Fatal("polarity")
	}
}
