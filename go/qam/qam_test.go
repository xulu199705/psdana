package qam

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"math/cmplx"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func closeTo(t *testing.T, actual, expected, tolerance float64) {
	t.Helper()
	if !finite(actual) || math.Abs(actual-expected) > tolerance {
		t.Fatalf("actual %.17g expected %.17g tolerance %.3g", actual, expected, tolerance)
	}
}

func TestConstellationAndSlicer(t *testing.T) {
	for _, order := range []int{16, 64, 256} {
		d, err := GenerateConstellation(order)
		if err != nil || len(d) != order {
			t.Fatal(order, err)
		}
		closeTo(t, norm2(d)/float64(order), 1, 1e-14)
		got, indices, err := SliceQAM(d, order)
		if err != nil || !reflect.DeepEqual(got, d) {
			t.Fatal("slicer identity", err)
		}
		for k, i := range indices {
			if k != i {
				t.Fatal("index order", k, i)
			}
		}
		rot := make([]complex128, len(d))
		for k, v := range d {
			rot[k] = 1i * v
		}
		got, _, err = SliceQAM(rot, order)
		if err != nil || !reflect.DeepEqual(got, rot) {
			t.Fatal("quadrant invariance", err)
		}
	}
	points, _ := GenerateConstellation(64)
	got, indices, err := SliceQAM([]complex128{0, complex(math.MaxFloat64, -math.MaxFloat64)}, 64)
	if err != nil || indices[0] != 27 || indices[1] != 56 || got[1] != points[56] {
		t.Fatal("tie/saturation", indices, err)
	}
}

func TestRRCAnalytic(t *testing.T) {
	for _, beta := range []float64{0, .25, 1} {
		for _, sps := range []int{1, 2, 3, 8} {
			h, err := GenerateRRCTaps(beta, 10, sps)
			if err != nil {
				t.Fatal(err)
			}
			if len(h) != 10*sps+1 {
				t.Fatal("length")
			}
			energy := 0.0
			for k, v := range h {
				closeTo(t, v, h[len(h)-1-k], 1e-15)
				energy += v * v
			}
			closeTo(t, energy, 1, 1e-14)
		}
	}
	impulse, _ := GenerateRRCTaps(0, 10, 1)
	for k, v := range impulse {
		want := 0.0
		if k == 5 {
			want = 1
		}
		closeTo(t, v, want, 1e-15)
	}
	h, _ := GenerateRRCTaps(.25, 10, 8)
	// Unit normalization cancels from the ratio at t=1 (removable singularity).
	singular := .25 / math.Sqrt2 * ((1+2/math.Pi)*math.Sin(math.Pi) + (1-2/math.Pi)*math.Cos(math.Pi))
	closeTo(t, h[48]/h[40], singular/(1+.25*(4/math.Pi-1)), 1e-14)
	odd, _ := GenerateRRCTaps(.25, 3, 3)
	if len(odd) != 11 {
		t.Fatal("odd tap convention")
	}
}

func TestMetricsAnalytic(t *testing.T) {
	for _, order := range []int{16, 64, 256} {
		d, _ := GenerateConstellation(order)
		y := make([]complex128, len(d))
		for k, v := range d {
			y[k] = v * (1.03 + .04i)
		}
		m, err := ComputeQAMMetrics(y, d)
		if err != nil {
			t.Fatal(err)
		}
		closeTo(t, m.EVMPctRMS, 5, 1e-12)
		closeTo(t, m.AmplitudeErrorPctRMS, 3, 1e-12)
		closeTo(t, m.PhaseErrorPctRMS, 4, 1e-12)
		closeTo(t, m.PhaseErrorDegRMS, math.Atan2(.04, 1.03)*180/math.Pi, 1e-12)
		closeTo(t, m.EVMPctRMS*m.EVMPctRMS, m.AmplitudeErrorPctRMS*m.AmplitudeErrorPctRMS+m.PhaseErrorPctRMS*m.PhaseErrorPctRMS, 1e-12)
	}
}

func TestScalarAnalyticAndImmutable(t *testing.T) {
	for _, order := range []int{16, 64, 256} {
		points, _ := GenerateConstellation(order)
		d := append(append(append([]complex128{}, points...), points...), points[0])
		a, c := cmplx.Rect(.7, .3), complex(.02, -.015)
		z := make([]complex128, len(d))
		for k, v := range d {
			z[k] = a*v + c
		}
		before := append([]complex128{}, z...)
		cfg := DefaultScalarConfig()
		cfg.Order, cfg.DCMode = order, DecisionDirectedJoint
		r, err := ScalarQAMFit(z, cfg)
		if err != nil {
			t.Fatal(order, err)
		}
		if !reflect.DeepEqual(before, z) {
			t.Fatal("modified input")
		}
		closeTo(t, r.EVMPct, 0, 1e-10)
		closeTo(t, cmplx.Abs(r.DC-c), 0, 1e-13)
		closeTo(t, cmplx.Abs(r.ComplexGain-1/a), 0, 1e-12)
		if !r.JointConverged || r.JointIterations > cfg.Iterations {
			t.Fatal("bounded convergence")
		}
		if _, err = json.Marshal(r); err != nil {
			t.Fatal(err)
		}
		cfg.DCMode = LegacyMean
		legacy, err := ScalarQAMFit(z, cfg)
		if err != nil {
			t.Fatal(err)
		}
		closeTo(t, cmplx.Abs(legacy.DC-mean(z)), 0, 1e-14)
	}
}

func TestSkewed256QAMIsNotLockProof(t *testing.T) {
	points, _ := GenerateConstellation(256)
	d := append(append(append([]complex128{}, points...), points...), points[:128]...)
	z := make([]complex128, len(d))
	for k, v := range d {
		z[k] = cmplx.Rect(.7, .3)*v + complex(.02, -.015)
	}
	cfg := DefaultScalarConfig()
	cfg.Order, cfg.DCMode = 256, DecisionDirectedJoint
	r, err := ScalarQAMFit(z, cfg)
	if err != nil {
		t.Fatal(err)
	}
	wrong := 0
	for k, v := range d {
		if r.Decisions[k] != v {
			wrong++
		}
	}
	if !r.JointConverged || wrong != 608 || r.EVMPct < 3 {
		t.Fatal("skewed 256QAM false-candidate regression", wrong, r.EVMPct)
	}
}

func TestErrorsAndNumericalBoundaries(t *testing.T) {
	for _, order := range []int{0, 4, 32, 65} {
		if _, err := GenerateConstellation(order); err == nil {
			t.Fatal("bad order")
		}
	}
	for _, params := range []struct {
		beta      float64
		span, sps int
	}{{-.1, 10, 8}, {1.1, 10, 8}, {math.NaN(), 10, 8}, {math.Inf(1), 10, 8}, {.25, 0, 8}, {.25, 10, 0}, {.25, int(^uint(0) >> 1), 8}} {
		if _, err := GenerateRRCTaps(params.beta, params.span, params.sps); err == nil {
			t.Fatal("bad RRC")
		}
	}
	for _, z := range [][]complex128{nil, {complex(math.NaN(), 0)}, {complex(0, math.Inf(1))}} {
		if _, _, err := SliceQAM(z, 64); err == nil {
			t.Fatal("bad samples")
		}
	}
	for _, pair := range []struct{ y, d []complex128 }{{nil, nil}, {[]complex128{1}, nil}, {[]complex128{1}, []complex128{0}}, {[]complex128{1e308}, []complex128{1e308}}, {[]complex128{complex(math.NaN(), 0)}, []complex128{1}}} {
		if _, err := ComputeQAMMetrics(pair.y, pair.d); err == nil {
			t.Fatal("bad metric")
		}
	}
	points, _ := GenerateConstellation(64)
	for _, cfg := range []ScalarConfig{{}, {64, 0, LegacyMean}, {64, 5, "bad"}} {
		if _, err := ScalarQAMFit(points, cfg); err == nil {
			t.Fatal("bad config")
		}
	}
	for _, mode := range []string{LegacyMean, DecisionDirectedJoint} {
		cfg := DefaultScalarConfig()
		cfg.DCMode = mode
		for _, z := range [][]complex128{nil, make([]complex128, 64), {1, 2, 3}, bytesToHugeSamples()} {
			if _, err := ScalarQAMFit(z, cfg); err == nil {
				t.Fatal("bad scalar samples", mode)
			}
		}
	}
	bad := ScalarResult{EVMPct: math.Inf(1)}
	if _, err := json.Marshal(bad); err == nil {
		t.Fatal("nonstandard JSON")
	}
}

func bytesToHugeSamples() []complex128 {
	z := make([]complex128, 64)
	for k := range z {
		z[k] = complex(1e308, float64(k%2)*1e308)
	}
	return z
}

type complexJSON struct{ Real, Imag []float64 }

func (z complexJSON) values() []complex128 {
	out := make([]complex128, len(z.Real))
	for k := range out {
		out[k] = complex(z.Real[k], z.Imag[k])
	}
	return out
}

func TestPythonFoundationGolden(t *testing.T) {
	folder := filepath.Join("..", "..", "data", "golden", "qam", "v2", "foundation")
	content, err := os.ReadFile(filepath.Join(folder, "index.json"))
	if err != nil {
		t.Fatal(err)
	}
	var index struct {
		VectorCount int `json:"vector_count"`
		Vectors     []struct{ ID, File, SHA256 string }
	}
	if err := json.Unmarshal(content, &index); err != nil {
		t.Fatal(err)
	}
	if index.VectorCount != 36 || len(index.Vectors) != index.VectorCount {
		t.Fatal("vector count")
	}
	globalAbs, globalRel, globalMetric := 0.0, 0.0, 0.0
	for _, entry := range index.Vectors {
		t.Run(entry.ID, func(t *testing.T) {
			content, err := os.ReadFile(filepath.Join(folder, entry.File))
			if err != nil {
				t.Fatal(err)
			}
			hash := sha256.Sum256(content)
			if hex.EncodeToString(hash[:]) != entry.SHA256 {
				t.Fatal("SHA256 mismatch")
			}
			var vector struct {
				Kind      string
				Arguments struct {
					Order, Iterations  int
					DCMode             string `json:"dc_mode"`
					Beta               float64
					Span               int `json:"span_symbols"`
					SPS                int
					Samples, Decisions complexJSON
				}
				Expected   any
				Tolerances struct {
					Atol, Rtol float64
					MetricAtol float64 `json:"metric_atol"`
				}
			}
			if err := json.Unmarshal(content, &vector); err != nil {
				t.Fatal(err)
			}
			a := vector.Arguments
			var actual any
			split := func(z []complex128) map[string][]float64 {
				r, i := make([]float64, len(z)), make([]float64, len(z))
				for k, v := range z {
					r[k], i[k] = real(v), imag(v)
				}
				return map[string][]float64{"real": r, "imag": i}
			}
			switch vector.Kind {
			case "constellation":
				d, err := GenerateConstellation(a.Order)
				if err != nil {
					t.Fatal(err)
				}
				actual = split(d)
			case "slicer":
				d, i, err := SliceQAM(a.Samples.values(), a.Order)
				if err != nil {
					t.Fatal(err)
				}
				actual = map[string]any{"decisions": split(d), "indices": i}
			case "rrc":
				h, err := GenerateRRCTaps(a.Beta, a.Span, a.SPS)
				if err != nil {
					t.Fatal(err)
				}
				actual = map[string]any{"taps": h}
			case "metrics":
				m, err := ComputeQAMMetrics(a.Samples.values(), a.Decisions.values())
				if err != nil {
					t.Fatal(err)
				}
				actual = m
			case "scalar":
				r, err := ScalarQAMFit(a.Samples.values(), ScalarConfig{a.Order, a.Iterations, a.DCMode})
				if err != nil {
					t.Fatal(err)
				}
				actual = r
			default:
				t.Fatal("unknown vector kind")
			}
			serialized, err := json.Marshal(actual)
			if err != nil {
				t.Fatal(err)
			}
			decoder := json.NewDecoder(bytes.NewReader(serialized))
			var normalized any
			if err := decoder.Decode(&normalized); err != nil {
				t.Fatal(err)
			}
			maxAbs, maxRel, maxMetric := 0.0, 0.0, 0.0
			var compare func(any, any, string)
			compare = func(actual, expected any, path string) {
				switch e := expected.(type) {
				case map[string]any:
					a, ok := actual.(map[string]any)
					if !ok || len(a) != len(e) {
						t.Fatalf("%s map dimensions", path)
					}
					for k, v := range e {
						compare(a[k], v, path+"."+k)
					}
				case []any:
					a, ok := actual.([]any)
					if !ok || len(a) != len(e) {
						t.Fatalf("%s array dimensions", path)
					}
					for k, v := range e {
						compare(a[k], v, fmt.Sprintf("%s[%d]", path, k))
					}
				case float64:
					a, ok := actual.(float64)
					if !ok || !finite(a) {
						t.Fatalf("%s nonfinite/type", path)
					}
					difference := math.Abs(a - e)
					atol := vector.Tolerances.Atol
					metric := strings.Contains(path, "evm_pct") || strings.Contains(path, "_rms")
					if metric {
						atol = vector.Tolerances.MetricAtol
						maxMetric = math.Max(maxMetric, difference)
					}
					maxAbs = math.Max(maxAbs, difference)
					if math.Abs(e) >= 1e-12 {
						maxRel = math.Max(maxRel, difference/math.Abs(e))
					}
					if strings.Contains(path, "indices[") || strings.HasSuffix(path, "joint_fit_iterations") {
						if a != e {
							t.Fatalf("%s integer mismatch", path)
						}
					} else if difference > atol+vector.Tolerances.Rtol*math.Abs(e) {
						t.Fatalf("%s actual=%.17g expected=%.17g abs=%.3g relative=%.3g atol=%.3g rtol=%.3g", path, a, e, difference, difference/math.Max(math.Abs(e), 1e-300), atol, vector.Tolerances.Rtol)
					}
				default:
					if !reflect.DeepEqual(actual, expected) {
						t.Fatalf("%s metadata mismatch", path)
					}
				}
			}
			compare(normalized, vector.Expected, entry.ID)
			globalAbs, globalRel, globalMetric = math.Max(globalAbs, maxAbs), math.Max(globalRel, maxRel), math.Max(globalMetric, maxMetric)
			t.Logf("PASS max_abs=%.12g max_relative(|expected|>=1e-12)=%.12g max_metric=%.12g", maxAbs, maxRel, maxMetric)
		})
	}
	t.Logf("36 vectors: max_abs=%.12g max_relative(|expected|>=1e-12)=%.12g max_metric=%.12g", globalAbs, globalRel, globalMetric)
}
