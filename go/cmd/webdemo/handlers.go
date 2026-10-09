package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"net/http"
	"net/url"
	"strconv"
	"strings"

	"github.com/xulu199705/psdana/go/csvio"
	"github.com/xulu199705/psdana/go/psd"
	"github.com/xulu199705/psdana/go/qam"
)

const maxRequestBytes int64 = 16 << 20

type analyzer struct {
	limit int64
	slots chan struct{}
}
type analysisResponse struct {
	psd.PSDResult
	PowerMetrics psd.PowerResult `json:"power_metrics"`
	QAMMetrics   *qam.QAMResult  `json:"qam_metrics,omitempty"`
	QAMError     string          `json:"qam_error,omitempty"`
	RRCBeta      float64         `json:"rrc_beta"`
	Status       string          `json:"status"`
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	b, err := json.Marshal(value)
	if err != nil {
		status = http.StatusInternalServerError
		b = []byte(`{"status":"ERROR","error":"JSON encoding failed"}`)
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_, _ = w.Write(b)
}
func fail(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]string{"status": "ERROR", "error": message})
}

func (a *analyzer) analyze(w http.ResponseWriter, r *http.Request) {
	defer r.Body.Close()
	// A local browser must use this service's own origin; CLI clients need no Origin.
	if origin := r.Header.Get("Origin"); origin != "" {
		u, err := url.Parse(origin)
		if err != nil || u.Scheme != "http" || u.Host != r.Host {
			fail(w, http.StatusForbidden, "cross-origin uploads are not allowed")
			return
		}
	}
	select {
	case a.slots <- struct{}{}:
		defer func() { <-a.slots }()
	default:
		fail(w, http.StatusServiceUnavailable, "analyzer busy; retry after the current analysis")
		return
	}
	if r.ContentLength > a.limit {
		fail(w, 413, "request exceeds 16 MiB limit")
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, a.limit)
	// Small captures remain in memory; net/http cleans spilled multipart files below.
	err := r.ParseMultipartForm(1 << 20)
	if r.MultipartForm != nil {
		defer r.MultipartForm.RemoveAll()
	}
	if err != nil {
		var tooLarge *http.MaxBytesError
		if errors.As(err, &tooLarge) {
			fail(w, 413, "request exceeds 16 MiB limit")
		} else {
			fail(w, 400, "invalid multipart/form-data: "+err.Error())
		}
		return
	}
	fields := []string{"sample_rate_hz", "power_band_left_hz", "power_band_right_hz", "symbol_rate_hz", "rrc_beta"}
	values := make(map[string]float64, len(fields))
	for _, key := range fields {
		v := r.MultipartForm.Value[key]
		if len(v) != 1 {
			fail(w, 400, "exactly one "+key+" is required")
			return
		}
		n, err := strconv.ParseFloat(strings.TrimSpace(v[0]), 64)
		if err != nil || math.IsNaN(n) || math.IsInf(n, 0) {
			fail(w, 400, key+" must be a finite number")
			return
		}
		values[key] = n
	}
	if len(r.MultipartForm.Value) != len(fields) {
		fail(w, 400, "unsupported form field; input format is fixed to hex_q15")
		return
	}
	qc := qam.DefaultQAMConfig()
	qc.SampleRateHz, qc.SymbolRateHz, qc.RRCBeta = values[fields[0]], values[fields[3]], values[fields[4]]
	if err := qc.Validate(); err != nil {
		fail(w, 400, "invalid analysis parameters: "+err.Error())
		return
	}
	left, right := values[fields[1]], values[fields[2]]
	if left > right || left < -qc.SampleRateHz/2 || right > qc.SampleRateHz/2 {
		fail(w, 400, "power band must satisfy -Fs/2 <= lower <= upper <= Fs/2 (equal bounds measure one frequency)")
		return
	}
	files := r.MultipartForm.File["file"]
	if len(files) != 1 || len(r.MultipartForm.File) != 1 {
		fail(w, 400, "exactly one CSV file is required")
		return
	}
	f, err := files[0].Open()
	if err != nil {
		fail(w, 400, "cannot read upload")
		return
	}
	defer f.Close()
	csvConfig := csvio.DefaultConfig()
	csvConfig.SampleFormat = "hex_q15"
	data, err := csvio.Read(f, csvConfig)
	if err != nil {
		fail(w, 400, "hex_q15 CSV format/parse error: "+err.Error())
		return
	}
	if r.Context().Err() != nil {
		return
	}
	pc := psd.DefaultConfig()
	pc.FS = qc.SampleRateHz
	var spectrum psd.PSDResult
	if data.InputType == "complex" {
		spectrum, err = psd.ComputeComplexPSD(data.Complex, pc)
	} else {
		spectrum, err = psd.ComputeRealPSD(data.Real, pc)
	}
	if err != nil {
		fail(w, 422, "PSD analysis failed: "+err.Error())
		return
	}
	power, err := psd.AnalyzeBandPower(spectrum, left, right)
	if err != nil {
		fail(w, 422, "power analysis failed: "+err.Error())
		return
	}
	if r.Context().Err() != nil {
		return
	}
	result := analysisResponse{PSDResult: spectrum, PowerMetrics: power, RRCBeta: qc.RRCBeta, Status: "COMPLETE"}
	if data.InputType != "complex" {
		result.QAMError = "QAM requires complex IQ input"
	} else {
		qr, err := qam.AnalyzeQAM(data.Complex, qc)
		if err != nil {
			var rejected *qam.RecoveryError
			if errors.As(err, &rejected) {
				result.QAMError = "QAM decisions unreliable: EVM/constellation occupancy failed; no equalizer applied"
			} else {
				result.QAMError = fmt.Sprint(err)
			}
		} else {
			result.QAMMetrics = &qr
		}
	}
	if result.QAMError != "" {
		result.Status = "PARTIAL"
	}
	if r.Context().Err() == nil {
		writeJSON(w, 200, result)
	}
}
