package tests

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"

	"github.com/xulu199705/psdana/go/csvio"
	"github.com/xulu199705/psdana/go/psd"
)

type bound struct {
	RTol float64 `json:"rtol"`
	ATol float64 `json:"atol"`
}
type tolerances struct {
	Frequency bound `json:"frequency_hz"`
	Linear    bound `json:"psd_linear"`
	Scalar    bound `json:"scalar_metadata"`
	DB        struct {
		ATol      float64 `json:"atol_db"`
		Threshold float64 `json:"compare_only_when_expected_psd_linear_gt"`
	} `json:"db_values"`
}
type vector struct {
	ID    string `json:"id"`
	Input struct {
		CSV    string          `json:"csv_relative_to_vector"`
		SHA256 string          `json:"sha256"`
		Config csvio.CSVConfig `json:"csv_config"`
	} `json:"input"`
	Config     psd.PSDConfig `json:"psd_config"`
	Expected   psd.PSDResult `json:"expected"`
	Tolerances tolerances    `json:"tolerances"`
}
type fieldStats struct {
	Field             string  `json:"field"`
	MaxAbs            float64 `json:"max_absolute_error"`
	MaxRel            float64 `json:"max_relative_error_nonzero_expected"`
	MaxSignificantRel float64 `json:"max_relative_error_significant_psd_bins"`
	Bin               int     `json:"max_abs_bin"`
	FrequencyHz       float64 `json:"frequency_hz"`
	Actual            float64 `json:"actual_at_max_abs"`
	Expected          float64 `json:"expected_at_max_abs"`
	RTol              float64 `json:"rtol"`
	ATol              float64 `json:"atol"`
	Passed            bool    `json:"passed"`
}
type vectorStats struct {
	ID     string       `json:"id"`
	Passed bool         `json:"passed"`
	Fields []fieldStats `json:"fields"`
}

func repoRoot() string {
	_, file, _, _ := runtime.Caller(0)
	return filepath.Clean(filepath.Join(filepath.Dir(file), "../.."))
}
func checkedRead(t *testing.T, path, expectedHash string) []byte {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	hash := sha256.Sum256(raw)
	if hex.EncodeToString(hash[:]) != expectedHash {
		t.Fatalf("SHA256 mismatch: %s", path)
	}
	return raw
}
func calculate(data csvio.CSVData, c psd.PSDConfig) (psd.PSDResult, error) {
	if data.InputType == "complex" {
		return psd.ComputeComplexPSD(data.Complex, c)
	}
	return psd.ComputeRealPSD(data.Real, c)
}

func compareResult(t *testing.T, v vector, actual psd.PSDResult) vectorStats {
	t.Helper()
	out := vectorStats{ID: v.ID, Passed: true}
	av, ev := reflect.ValueOf(actual), reflect.ValueOf(v.Expected)
	typ := av.Type()
	for j := 0; j < av.NumField(); j++ {
		name := typ.Field(j).Tag.Get("json")
		a, e := av.Field(j), ev.Field(j)
		if a.Kind() == reflect.Int || a.Kind() == reflect.String {
			if !reflect.DeepEqual(a.Interface(), e.Interface()) {
				t.Errorf("%s field=%s actual=%v expected=%v exact FAIL", v.ID, name, a.Interface(), e.Interface())
				out.Passed = false
			}
			continue
		}
		bounds := v.Tolerances.Scalar
		if name == "frequency_hz" {
			bounds = v.Tolerances.Frequency
		}
		if name == "psd_linear" {
			bounds = v.Tolerances.Linear
		}
		if name == "integrated_power" {
			bounds = bound{2e-12, 1e-15}
		}
		isDB := name == "psd_dbfs_per_hz" || name == "rbw_power_dbfs"
		if isDB {
			bounds = bound{ATol: v.Tolerances.DB.ATol}
		}
		stats := fieldStats{Field: name, Bin: -1, RTol: bounds.RTol, ATol: bounds.ATol, Passed: true}
		count := 1
		if a.Kind() == reflect.Slice {
			count = a.Len()
			if count != e.Len() {
				t.Errorf("%s %s length actual=%d expected=%d", v.ID, name, count, e.Len())
				out.Passed = false
				continue
			}
		}
		for k := 0; k < count; k++ {
			aa, ee := 0.0, 0.0
			if a.Kind() == reflect.Slice {
				aa = a.Index(k).Float()
				ee = e.Index(k).Float()
			} else {
				aa = a.Float()
				ee = e.Float()
			}
			if isDB && v.Expected.PSDLinear[k] <= v.Tolerances.DB.Threshold {
				continue
			}
			delta := math.Abs(aa - ee)
			if math.IsNaN(delta) || math.IsInf(delta, 0) {
				stats.Passed = false
				t.Errorf("%s %s bin=%d nonfinite actual=%g expected=%g", v.ID, name, k, aa, ee)
				continue
			}
			if delta >= stats.MaxAbs {
				stats.MaxAbs = delta
				stats.Actual = aa
				stats.Expected = ee
				if a.Kind() == reflect.Slice {
					stats.Bin = k
					stats.FrequencyHz = v.Expected.FrequencyHz[k]
				}
			}
			if ee != 0 {
				rel := delta / math.Abs(ee)
				stats.MaxRel = math.Max(stats.MaxRel, rel)
				if a.Kind() == reflect.Slice && v.Expected.PSDLinear[k] > v.Tolerances.DB.Threshold {
					stats.MaxSignificantRel = math.Max(stats.MaxSignificantRel, rel)
				}
			}
			if delta > bounds.ATol+bounds.RTol*math.Abs(ee) {
				stats.Passed = false
				t.Errorf("%s field=%s bin=%d frequency=%g actual=%.17g expected=%.17g abs=%g rtol=%g atol=%g FAIL", v.ID, name, k, v.Expected.FrequencyHz[min(k, len(v.Expected.FrequencyHz)-1)], aa, ee, delta, bounds.RTol, bounds.ATol)
			}
		}
		t.Logf("%s field=%s max_abs=%g max_rel=%g bin=%d frequency=%g actual=%g expected=%g rtol=%g atol=%g PASS=%t", v.ID, name, stats.MaxAbs, stats.MaxRel, stats.Bin, stats.FrequencyHz, stats.Actual, stats.Expected, stats.RTol, stats.ATol, stats.Passed)
		out.Fields = append(out.Fields, stats)
		out.Passed = out.Passed && stats.Passed
	}
	if v.ID == "T07_rectangle_all" {
		for j, p := range actual.PSDLinear {
			if p != 0 || !math.IsInf(actual.PSDDBFSPerHz[j], -1) || !math.IsInf(actual.RBWPowerDBFS[j], -1) {
				t.Errorf("true zero must be exact at bin %d", j)
				out.Passed = false
			}
		}
	}
	return out
}

func TestGoldenVectors(t *testing.T) {
	directory := filepath.Join(repoRoot(), "data", "golden")
	raw, err := os.ReadFile(filepath.Join(directory, "index.json"))
	if err != nil {
		t.Fatal(err)
	}
	var index struct {
		Count   int `json:"vector_count"`
		Vectors []struct {
			ID     string `json:"id"`
			File   string `json:"file"`
			SHA256 string `json:"sha256"`
		} `json:"vectors"`
	}
	if err := json.Unmarshal(raw, &index); err != nil {
		t.Fatal(err)
	}
	if index.Count != 17 || len(index.Vectors) != index.Count {
		t.Fatal("expected all 17 Golden vectors")
	}
	stats := make([]vectorStats, 0, index.Count)
	for _, entry := range index.Vectors {
		t.Run(entry.ID, func(t *testing.T) {
			var v vector
			if err := json.Unmarshal(checkedRead(t, filepath.Join(directory, entry.File), entry.SHA256), &v); err != nil {
				t.Fatal(err)
			}
			if v.ID != entry.ID {
				t.Fatal("vector ID mismatch")
			}
			source := filepath.Join(directory, filepath.FromSlash(v.Input.CSV))
			checkedRead(t, source, v.Input.SHA256)
			data, err := csvio.ReadCSV(source, v.Input.Config)
			if err != nil {
				t.Fatal(err)
			}
			result, err := calculate(data, v.Config)
			if err != nil {
				t.Fatal(err)
			}
			stats = append(stats, compareResult(t, v, result))
		})
	}
	if reportDir := os.Getenv("PSD_REPORT_DIR"); reportDir != "" {
		if err := os.MkdirAll(reportDir, 0755); err != nil {
			t.Fatal(err)
		}
		report := struct {
			Count   int           `json:"vector_count"`
			Vectors []vectorStats `json:"vectors"`
		}{len(stats), stats}
		encoded, err := json.MarshalIndent(report, "", "  ")
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(reportDir, "golden_statistics.json"), append(encoded, '\n'), 0644); err != nil {
			t.Fatal(err)
		}
	}
}

func TestJSONConfigTypes(t *testing.T) {
	for _, token := range []string{`"all"`, `1`, `255`} {
		var points psd.FFTPoints
		if err := json.Unmarshal([]byte(token), &points); err != nil {
			t.Fatal(err)
		}
	}
	for _, token := range []string{`0`, `-1`, `255.0`, `"255"`, `true`, `null`, `1e3`} {
		t.Run(token, func(t *testing.T) {
			var points psd.FFTPoints
			if err := json.Unmarshal([]byte(token), &points); err == nil {
				t.Fatalf("accepted invalid FFT points %s", token)
			}
		})
	}
	values := psd.DBValues{math.Inf(-1), -3, 0}
	raw, err := json.Marshal(values)
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) != "[null,-3,0]" {
		t.Fatal(string(raw))
	}
	var decoded psd.DBValues
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatal(err)
	}
	if !math.IsInf(decoded[0], -1) || decoded[1] != -3 {
		t.Fatal("null decoded incorrectly")
	}
	for _, invalid := range []float64{math.NaN(), math.Inf(1)} {
		if _, err := json.Marshal(psd.DBValues{invalid}); err == nil {
			t.Fatal(fmt.Sprintf("accepted %g", invalid))
		}
	}
}
