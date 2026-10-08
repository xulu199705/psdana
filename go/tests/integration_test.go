package tests

import (
	"encoding/json"
	"math"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
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
	for _, bounds := range [][2]float64{{40e6, 40e6}, {39e6, 41e6}, {-80e6, 80e6}} {
		p, err := psd.AnalyzeBandPower(r, bounds[0], bounds[1])
		if err != nil || math.Abs(p.BandPowerLinear-expectedPower) > 2e-15 || p.PeakFrequencyHz == nil || *p.PeakFrequencyHz != 40e6 {
			t.Fatal("capture band power", p, err)
		}
	}
	quiet, err := psd.AnalyzeBandPower(r, -10e6, 10e6)
	if err != nil || quiet.BandPowerLinear > 1e-28 {
		t.Fatal("quiet band", quiet, err)
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
			var fields map[string]json.RawMessage
			if err := json.Unmarshal(raw, &fields); err != nil || len(fields) != 22 || fields["power_metrics"] != nil {
				t.Fatal("original JSON structure changed", len(fields), err)
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
	for _, args := range [][]string{
		{"--freq-left", "0"}, {"--freq-right", "0"}, {"--freq-left", "1", "--freq-right", "0"},
		{"--freq-left", "NaN", "--freq-right", "0"}, {"--freq-left", "0", "--freq-right", "Inf"},
		{"--freq-left", "-80000001", "--freq-right", "0"}, {"--freq-left", "0", "--freq-right", "80000001"},
		{"--fs", "1e308", "--window", "rectangle"},
	} {
		command := exec.Command(binary, append(args, "--json")...)
		command.Dir = repoRoot()
		raw, err := command.Output()
		if err == nil || len(raw) != 0 {
			t.Fatal("CLI must fail without stdout", args)
		}
	}
	for _, v := range []struct {
		input, left, right string
		zero               bool
	}{
		{"data/generated/T07_zero_iq.csv", "0", "0", true},
		{"data/generated/T07_zero_iq.csv", "-80000000", "80000000", true},
		{"data/sine_+40MHz_160MSPS.csv", "40000000", "40000000", false},
	} {
		command := exec.Command(binary, "--input", v.input, "--freq-left", v.left, "--freq-right", v.right, "--json")
		command.Dir = repoRoot()
		raw, err := command.Output()
		if err != nil {
			t.Fatal(err)
		}
		var fields map[string]json.RawMessage
		if err = json.Unmarshal(raw, &fields); err != nil || len(fields) != 23 {
			t.Fatal("band JSON structure", err, len(fields))
		}
		var p map[string]any
		if err = json.Unmarshal(fields["power_metrics"], &p); err != nil {
			t.Fatal(err)
		}
		if v.zero {
			for _, key := range []string{"peak_frequency_hz", "peak_power_dbfs", "average_power_dbfs"} {
				if p[key] != nil {
					t.Fatal("zero JSON must be null", key)
				}
			}
		} else if p["peak_frequency_hz"] != 40e6 {
			t.Fatal("point peak", p)
		}
	}
	zeroText := exec.Command(binary, "--input", "data/generated/T07_zero_iq.csv")
	zeroText.Dir = repoRoot()
	raw, err = zeroText.Output()
	if err != nil || !strings.Contains(string(raw), "Peak Frequency: N/A") {
		t.Fatal("zero text false frequency", err, string(raw))
	}
	bandText := exec.Command(binary, "--freq-left", "39000000", "--freq-right", "41000000")
	bandText.Dir = repoRoot()
	raw, err = bandText.Output()
	if err != nil || !strings.Contains(string(raw), "Frequency Range: [39000000, 41000000) Hz") {
		t.Fatal("half-open text range", err, string(raw))
	}
}
