package tests

import (
	"encoding/json"
	"math"
	"os/exec"
	"path/filepath"
	"runtime"
	"testing"

	"github.com/xulu199705/psdana/go/csvio"
	"github.com/xulu199705/psdana/go/psd"
)

func TestOriginalSamplesAndPSD(t *testing.T) {
	c := csvio.DefaultConfig()
	c.SampleFormat = "hex_q15"
	data, err := csvio.ReadCSV(filepath.Join(repoRoot(), "data", "sine_+40MHz_160MSPS.csv"), c)
	if err != nil {
		t.Fatal(err)
	}
	if data.SampleCount() != 8192 || data.Columns[0] != 1 || data.Columns[1] != 0 {
		t.Fatal("original capture interpretation")
	}
	cycle := []complex128{complex(-814, -11481), complex(11481, -814), complex(814, 11481), complex(-11481, 814)}
	for j, v := range data.Complex {
		if v != cycle[j%4]/32768 {
			t.Fatalf("wrong decoded sample %d: %v", j, v)
		}
	}
	r, err := calculate(data, psd.DefaultConfig())
	if err != nil {
		t.Fatal(err)
	}
	peak := 0
	for j, p := range r.PSDLinear {
		if p > r.PSDLinear[peak] {
			peak = j
		}
	}
	expectedPower := (814.0*814 + 11481.0*11481) / (32768 * 32768)
	if r.FrequencyHz[peak] != 40e6 || math.Abs(r.RBWPowerDBFS[peak]-10*math.Log10(expectedPower)) > 1e-10 || math.Abs(r.IntegratedPower-expectedPower) > 1e-13 {
		t.Fatal("original PSD analytic mismatch")
	}
}

func TestCLIJSONAndPathResolution(t *testing.T) {
	goExecutable := filepath.Join(runtime.GOROOT(), "bin", "go")
	suffix := ""
	if runtime.GOOS == "windows" {
		goExecutable += ".exe"
		suffix = ".exe"
	}
	binary := filepath.Join(t.TempDir(), "psdana"+suffix)
	build := exec.Command(goExecutable, "build", "-o", binary, "./cmd/psdana")
	build.Dir = filepath.Join(repoRoot(), "go")
	if raw, err := build.CombinedOutput(); err != nil {
		t.Fatalf("build: %v %s", err, raw)
	}
	for _, cwd := range []string{repoRoot(), filepath.Join(repoRoot(), "go")} {
		t.Run(filepath.Base(cwd), func(t *testing.T) {
			command := exec.Command(binary, "--json")
			command.Dir = cwd
			raw, err := command.Output()
			if err != nil {
				t.Fatal(err)
			}
			var r psd.PSDResult
			if err := json.Unmarshal(raw, &r); err != nil {
				t.Fatal("non-JSON stdout", err)
			}
			if r.InputSampleCount != 8192 || len(r.PSDLinear) != 8192 {
				t.Fatal("incomplete JSON result")
			}
		})
	}
	zero := exec.Command(binary, "--input", "data/generated/T07_zero_iq.csv", "--json")
	zero.Dir = repoRoot()
	raw, err := zero.Output()
	if err != nil {
		t.Fatal(err)
	}
	var r psd.PSDResult
	if err := json.Unmarshal(raw, &r); err != nil || !math.IsInf(r.PSDDBFSPerHz[0], -1) {
		t.Fatal("zero JSON null handling", err)
	}
	bad := exec.Command(binary, "--input", "definitely_missing.csv", "--json")
	bad.Dir = repoRoot()
	raw, err = bad.Output()
	if err == nil || len(raw) != 0 {
		t.Fatal("invalid input must fail with empty stdout")
	}
	failure, ok := err.(*exec.ExitError)
	if !ok || len(failure.Stderr) == 0 {
		t.Fatal("error must be on stderr")
	}
}
