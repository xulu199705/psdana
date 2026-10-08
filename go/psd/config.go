// Package psd implements the Phase 1 PSD mathematical contract using Gonum FFT.
package psd

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math"
)

// FFTPoints explicitly distinguishes all input samples from an integer FFT size.
// Its zero value is invalid. JSON accepts only "all" or a positive integer.
type FFTPoints struct {
	All bool
	N   int
}

func (p FFTPoints) MarshalJSON() ([]byte, error) {
	if p.All && p.N == 0 {
		return []byte(`"all"`), nil
	}
	if !p.All && p.N > 0 {
		return json.Marshal(p.N)
	}
	return nil, fmt.Errorf("invalid FFTPoints")
}
func (p *FFTPoints) UnmarshalJSON(raw []byte) error {
	raw = bytes.TrimSpace(raw)
	if bytes.Equal(raw, []byte(`"all"`)) {
		*p = FFTPoints{All: true}
		return nil
	}
	var n int
	if err := json.Unmarshal(raw, &n); err != nil || n <= 0 {
		return fmt.Errorf("fft_points must be 'all' or a positive JSON integer")
	}
	*p = FFTPoints{N: n}
	return nil
}

// PSDConfig contains explicit algorithm settings; use DefaultConfig, not its zero value.
type PSDConfig struct {
	FS        float64   `json:"fs"`
	Window    string    `json:"window"`
	FFTPoints FFTPoints `json:"fft_points"`
	Overlap   float64   `json:"overlap"`
	Detrend   string    `json:"detrend"`
}

// DefaultConfig returns the Phase 1 defaults.
func DefaultConfig() PSDConfig { return PSDConfig{160e6, "hann", FFTPoints{All: true}, 0.5, "none"} }
func finite(v float64) bool    { return !math.IsNaN(v) && !math.IsInf(v, 0) }
func (c PSDConfig) validate(m int) (int, error) {
	if m == 0 {
		return 0, fmt.Errorf("samples must be nonempty")
	}
	if !finite(c.FS) || c.FS <= 0 {
		return 0, fmt.Errorf("fs must be finite and positive")
	}
	if c.Window != "hann" && c.Window != "rectangle" {
		return 0, fmt.Errorf("window must be hann or rectangle")
	}
	if c.Detrend != "none" && c.Detrend != "mean" {
		return 0, fmt.Errorf("detrend must be none or mean")
	}
	if !finite(c.Overlap) || c.Overlap < 0 || c.Overlap >= 1 {
		return 0, fmt.Errorf("overlap must be in [0,1)")
	}
	n := c.FFTPoints.N
	if c.FFTPoints.All {
		if n != 0 {
			return 0, fmt.Errorf("FFTPoints All conflicts with N")
		}
		n = m
	}
	if n <= 0 {
		return 0, fmt.Errorf("FFT size must be positive; use DefaultConfig for defaults")
	}
	if n > m {
		return 0, fmt.Errorf("FFT size exceeds input; implicit zero padding is disabled")
	}
	if n == 1 && c.Window == "hann" {
		return 0, fmt.Errorf("Periodic Hann N=1 has zero window energy")
	}
	return n, nil
}
