package tests

import (
	"encoding/json"
	"github.com/xulu199705/psdana/go/csvio"
	"github.com/xulu199705/psdana/go/psd"
	"math"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestQAM32768CLICompatibility(t *testing.T) {
	binary := filepath.Join(t.TempDir(), "psdana.exe")
	build := exec.Command("go", "build", "-o", binary, "./cmd/psdana")
	build.Dir = filepath.Join(repoRoot(), "go")
	if out, err := build.CombinedOutput(); err != nil {
		t.Fatal(err, string(out))
	}
	base := []string{"--input", "data/generated/qam/Q13_32768_q15.csv", "--sample-format", "q15", "--fs", "160000000", "--fft-points", "32768", "--json"}
	call := func(args []string) map[string]json.RawMessage {
		t.Helper()
		cmd := exec.Command(binary, args...)
		cmd.Dir = repoRoot()
		raw, err := cmd.Output()
		if err != nil {
			t.Fatal(err)
		}
		var fields map[string]json.RawMessage
		if err = json.Unmarshal(raw, &fields); err != nil {
			t.Fatal(err, string(raw))
		}
		return fields
	}
	plain := call(base)
	for _, mode := range []string{"legacy_mean", "decision_directed_joint"} {
		args := append(append([]string{}, base...), "--qam", "--qam-dc-mode", mode, "--freq-left", "-80000000", "--freq-right", "80000000", "--constellation-points", "128")
		fields := call(args)
		if len(fields) != len(plain)+2 {
			t.Fatal("JSON structure")
		}
		for k, v := range plain {
			if string(v) != string(fields[k]) {
				t.Fatal("PSD changed", k)
			}
		}
		var q struct {
			Count       int            `json:"recovered_symbol_count"`
			CFO         *float64       `json:"frequency_error_hz"`
			Diagnostics map[string]any `json:"diagnostics"`
		}
		if err := json.Unmarshal(fields["qam_metrics"], &q); err != nil || q.Count != 4074 || q.CFO == nil || q.Diagnostics["input_sample_count"] != float64(32768) {
			t.Fatal("QAM contract", q, err)
		}
	}
	fields := call([]string{"--input", "data/generated/qam/Q01_ideal.csv", "--sample-format", "float", "--json", "--qam", "--no-cfo-correction", "--qam-dc-mode", "decision_directed_joint"})
	var q map[string]any
	json.Unmarshal(fields["qam_metrics"], &q)
	if q["frequency_error_hz"] != nil {
		t.Fatal("CFO must be null")
	}
	for _, extra := range [][]string{{"--qam", "--qam-order", "32"}, {"--qam", "--q-sign", "0"}, {"--qam", "--qam-dc-mode", "invalid"}, {"--qam", "--symbol-rate", "21000000"}, {"--qam", "--timing-interp", "0"}, {"--fft-points", "65536"}} {
		cmd := exec.Command(binary, append(append([]string{}, base...), extra...)...)
		cmd.Dir = repoRoot()
		out, err := cmd.Output()
		if err == nil || len(out) > 0 {
			t.Fatal("invalid input stdout", extra, err)
		}
		failure, ok := err.(*exec.ExitError)
		if !ok || len(failure.Stderr) == 0 {
			t.Fatal("missing stderr")
		}
	}
}

func TestQAM32768CSVPSDAndFFTLengths(t *testing.T) {
	cc := csvio.DefaultConfig()
	cc.SampleFormat = "q15"
	cc.IColumn = csvio.ParseColumn("i")
	cc.QColumn = csvio.ParseColumn("q")
	data, err := csvio.ReadCSV(filepath.Join(repoRoot(), "data/generated/qam/Q13_32768_q15.csv"), cc)
	if err != nil || data.SampleCount() != 32768 {
		t.Fatal(err)
	}
	for _, z := range data.Complex {
		if real(z)*32768 != math.Trunc(real(z)*32768) || imag(z)*32768 != math.Trunc(imag(z)*32768) {
			t.Fatal("Q15 decode")
		}
	}
	c := psd.DefaultConfig()
	c.FFTPoints = psd.FFTPoints{N: 32768}
	r, err := psd.ComputeComplexPSD(data.Complex, c)
	if err != nil || r.Method != "periodogram" || r.ReferencePower != 1 || r.FrequencyResolutionHz != 160e6/32768 || math.Abs(r.ENBWHZ-1.5*r.FrequencyResolutionHz) > 1e-10 {
		t.Fatal("PSD contract", err)
	}
	p, err := psd.AnalyzeBandPower(r, -80e6, 80e6)
	if err != nil || math.Abs(p.BandPowerLinear-r.IntegratedPower) > 1e-13 {
		t.Fatal("power contract", err)
	}
	twice := append(append([]complex128{}, data.Complex...), data.Complex...)
	welch, err := psd.ComputeComplexPSD(twice, c)
	if err != nil || welch.Method != "welch" || welch.InputSampleCount != 65536 {
		t.Fatal("Welch contract", err)
	}
	if _, err := psd.ComputeComplexPSD(data.Complex[:16384], c); err == nil {
		t.Fatal("implicit padding")
	}
	all, err := psd.ComputeComplexPSD(twice, psd.DefaultConfig())
	if err != nil || all.FFTSize != 65536 {
		t.Fatal("all semantics", err)
	}
}
