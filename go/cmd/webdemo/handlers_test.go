package main

import (
	"bytes"
	"encoding/json"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func request(t *testing.T, csv string, changes map[string]string) *http.Request {
	t.Helper()
	fields := map[string]string{"sample_rate_hz": "160000000", "symbol_rate_hz": "20000000", "power_band_left_hz": "-20000000", "power_band_right_hz": "20000000", "rrc_beta": "0.25"}
	for k, v := range changes {
		fields[k] = v
	}
	var body bytes.Buffer
	form := multipart.NewWriter(&body)
	for k, v := range fields {
		if v != "OMIT" {
			if err := form.WriteField(k, v); err != nil {
				t.Fatal(err)
			}
		}
	}
	if csv != "OMIT" {
		file, err := form.CreateFormFile("file", "capture.csv")
		if err != nil {
			t.Fatal(err)
		}
		if _, err = io.WriteString(file, csv); err != nil {
			t.Fatal(err)
		}
	}
	if err := form.Close(); err != nil {
		t.Fatal(err)
	}
	r := httptest.NewRequest("POST", "http://127.0.0.1:8080/api/analyze", &body)
	r.Header.Set("Content-Type", form.FormDataContentType())
	return r
}
func response(t *testing.T, h http.Handler, r *http.Request, code int) map[string]any {
	t.Helper()
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != code {
		t.Fatalf("status %d, want %d: %s", w.Code, code, w.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	return result
}
func TestValidation(t *testing.T) {
	valid := "i,q\n0000,0000\n0001,0001\n0002,0002\n"
	cases := []struct {
		name, csv string
		fields    map[string]string
		code      int
	}{
		{"empty", "", nil, 400}, {"missing file", "OMIT", nil, 400}, {"float", "i,q\n0.5,0.2\n", nil, 400},
		{"decimal negative", "i,q\n-123,20\n", nil, 400}, {"packed", "i,q\n00000001,0001\n", nil, 400},
		{"bad hex", "i,q\nZZZZ,0001\n", nil, 400}, {"short PSD", "i,q\n0000,0000\n", nil, 422},
		{"nan", valid, map[string]string{"sample_rate_hz": "NaN"}, 400}, {"inf", valid, map[string]string{"rrc_beta": "Inf"}, 400},
		{"zero rate", valid, map[string]string{"sample_rate_hz": "0"}, 400}, {"zero symbols", valid, map[string]string{"symbol_rate_hz": "0"}, 400},
		{"fractional SPS", valid, map[string]string{"symbol_rate_hz": "21000000"}, 400},
		{"SPS one", valid, map[string]string{"symbol_rate_hz": "160000000"}, 400},
		{"beta low", valid, map[string]string{"rrc_beta": "-0.1"}, 400}, {"beta high", valid, map[string]string{"rrc_beta": "1.1"}, 400},
		{"reversed band", valid, map[string]string{"power_band_left_hz": "20000001"}, 400},
		{"outside nyquist", valid, map[string]string{"power_band_right_hz": "80000001"}, 400},
		{"missing parameter", valid, map[string]string{"rrc_beta": "OMIT"}, 400},
		{"format override", valid, map[string]string{"sample_format": "float"}, 400},
		{"short IQ partial", valid, nil, 200}, {"real partial", "real\n0000\n1234\n0000\nf000\n", nil, 200},
		{"beta zero boundary", valid, map[string]string{"rrc_beta": "0"}, 200}, {"beta one boundary", valid, map[string]string{"rrc_beta": "1"}, 200},
		{"nyquist endpoints", valid, map[string]string{"power_band_left_hz": "-80000000", "power_band_right_hz": "80000000"}, 200},
	}
	h := newHandler(maxRequestBytes)
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			r := response(t, h, request(t, tc.csv, tc.fields), tc.code)
			if tc.code == 200 && (r["status"] != "PARTIAL" || r["qam_metrics"] != nil || r["qam_error"] == nil || r["power_metrics"] == nil) {
				t.Fatalf("partial contract: %v", r)
			}
		})
	}
}
func TestLimitsAndMethods(t *testing.T) {
	for _, chunked := range []bool{false, true} {
		r := request(t, "i,q\n"+strings.Repeat("0000,0000\n", 200), nil)
		if chunked {
			r.ContentLength = -1
		}
		response(t, newHandler(1024), r, 413)
	}
	h := newHandler(maxRequestBytes)
	r := request(t, "i,q\n0000,0000\n0001,0001\n", nil)
	r.Header.Set("Origin", "https://example.org")
	response(t, h, r, 403)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest("GET", "/api/analyze", nil))
	if w.Code != 404 {
		t.Fatalf("GET analyze: %d", w.Code)
	}
	r = httptest.NewRequest("GET", "/api/health", nil)
	if response(t, h, r, 200)["version"] != "2.2.0" {
		t.Fatal("version")
	}
	w = httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest("GET", "/", nil))
	if w.Code != 200 || !strings.Contains(w.Body.String(), "ANALYZE") {
		t.Fatal("embedded UI")
	}
	a := &analyzer{limit: maxRequestBytes, slots: make(chan struct{}, 1)}
	a.slots <- struct{}{}
	response(t, http.HandlerFunc(a.analyze), request(t, "", nil), 503)
}
func TestZeroNulls(t *testing.T) {
	r := response(t, newHandler(maxRequestBytes), request(t, "i,q\n0000,0000\n0000,0000\n0000,0000\n0000,0000\n", nil), 200)
	for _, v := range r["psd_dbfs_per_hz"].([]any) {
		if v != nil {
			t.Fatal("zero PSD must encode null")
		}
	}
	p := r["power_metrics"].(map[string]any)
	if p["average_power_dbfs"] != nil || p["peak_frequency_hz"] != nil {
		t.Fatal("zero power must encode null")
	}
}

func TestPointBandBoundaries(t *testing.T) {
	for _, frequency := range []string{"-80000000", "0", "80000000"} {
		t.Run(frequency, func(t *testing.T) {
			r := response(t, newHandler(maxRequestBytes), request(t, "i,q\n0000,0000\n0000,0000\n0000,0000\n0000,0000\n", map[string]string{
				"power_band_left_hz": frequency, "power_band_right_hz": frequency,
			}), 200)
			p := r["power_metrics"].(map[string]any)
			if p["is_point"] != true || p["contributing_bins"] != float64(1) || p["average_power_dbfs"] != nil || p["peak_power_dbfs"] != nil {
				t.Fatalf("point power contract: %v", p)
			}
		})
	}
}

// Compare every existing JSON field with the unchanged CLI, not copied equations.
// Only this test launches a CLI; the HTTP implementation invokes Go APIs directly.
func TestRealCapturesMatchCLI(t *testing.T) {
	for _, tc := range []struct {
		name, file, left, right string
		qam                     bool
	}{
		{"qam", "qam64_20MSymPS_160MSPS_RRC0p25.csv", "-20000000", "20000000", true},
		{"sine", "sine_+40MHz_160MSPS.csv", "39000000", "41000000", false},
		{"sine point", "sine_+40MHz_160MSPS.csv", "40000000", "40000000", false},
		{"sine nearest bin", "sine_+40MHz_160MSPS.csv", "40005000", "40005000", false},
		{"sine Nyquist point", "sine_+40MHz_160MSPS.csv", "80000000", "80000000", false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			path, err := filepath.Abs("../../../data/" + tc.file)
			if err != nil {
				t.Fatal(err)
			}
			csv, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			actual := response(t, newHandler(maxRequestBytes), request(t, string(csv), map[string]string{"power_band_left_hz": tc.left, "power_band_right_hz": tc.right}), 200)
			args := []string{"run", "../psdana", "--input", path, "--sample-format", "hex_q15", "--fs", "160000000", "--fft-points", "all", "--freq-left", tc.left, "--freq-right", tc.right, "--json"}
			if tc.qam {
				args = append(args, "--qam", "--symbol-rate", "20000000", "--rrc-beta", "0.25")
			}
			output, err := exec.Command("go", args...).Output()
			if err != nil {
				t.Fatal(err)
			}
			var expected map[string]any
			if err := json.Unmarshal(output, &expected); err != nil {
				t.Fatal(err)
			}
			for k, v := range expected {
				if !reflect.DeepEqual(v, actual[k]) {
					t.Fatalf("HTTP/CLI mismatch in %s", k)
				}
			}
			if tc.qam && actual["status"] != "COMPLETE" {
				t.Fatalf("QAM failed: %v", actual["qam_error"])
			}
			if !tc.qam && actual["status"] != "PARTIAL" {
				t.Fatal("sine must not be accepted as 64QAM")
			}
			if tc.left == tc.right {
				p := actual["power_metrics"].(map[string]any)
				if p["is_point"] != true || p["contributing_bins"] != float64(1) || p["average_power_dbfs"] != p["peak_power_dbfs"] {
					t.Fatalf("single-bin RBW power contract: %v", p)
				}
			}
			t.Logf("all %d CLI fields exactly equal; status=%v; power=%v", len(expected), actual["status"], actual["power_metrics"])
			if tc.qam {
				q := actual["qam_metrics"].(map[string]any)
				t.Logf("EVM=%v phase_pct=%v amp_pct=%v CFO=%v", q["evm_pct_rms"], q["phase_error_pct_rms"], q["amplitude_error_pct_rms"], q["frequency_error_hz"])
			}
		})
	}
}
