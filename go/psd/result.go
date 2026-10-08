package psd

import (
	"encoding/json"
	"fmt"
	"math"
)

// DBValues encodes negative infinity as JSON null. NaN/+Inf are rejected.
type DBValues []float64

func (v DBValues) MarshalJSON() ([]byte, error) {
	values := make([]*float64, len(v))
	for i, x := range v {
		if math.IsInf(x, -1) {
			continue
		}
		if !finite(x) {
			return nil, fmt.Errorf("nonfinite dB value at bin %d", i)
		}
		y := x
		values[i] = &y
	}
	return json.Marshal(values)
}
func (v *DBValues) UnmarshalJSON(raw []byte) error {
	var values []*float64
	if err := json.Unmarshal(raw, &values); err != nil {
		return err
	}
	out := make(DBValues, len(values))
	for i, x := range values {
		if x == nil {
			out[i] = math.Inf(-1)
		} else {
			out[i] = *x
		}
	}
	*v = out
	return nil
}

// PSDResult preserves the complete Python Golden result and absolute power units.
type PSDResult struct {
	FrequencyHz           []float64 `json:"frequency_hz"`
	PSDLinear             []float64 `json:"psd_linear"`
	PSDDBFSPerHz          DBValues  `json:"psd_dbfs_per_hz"`
	RBWPowerDBFS          DBValues  `json:"rbw_power_dbfs"`
	FFTSize               int       `json:"fft_size"`
	FSHz                  float64   `json:"fs_hz"`
	FrequencyResolutionHz float64   `json:"frequency_resolution_hz"`
	ENBWHZ                float64   `json:"enbw_hz"`
	CoherentGain          float64   `json:"coherent_gain"`
	WindowPowerSum        float64   `json:"window_power_sum"`
	SegmentCount          int       `json:"segment_count"`
	Window                string    `json:"window"`
	InputType             string    `json:"input_type"`
	ReferencePower        float64   `json:"reference_power"`
	Method                string    `json:"method"`
	OverlapSamples        int       `json:"overlap_samples"`
	HopSize               int       `json:"hop_size"`
	InputSampleCount      int       `json:"input_sample_count"`
	UsedSampleCount       int       `json:"used_sample_count"`
	DiscardedTailSamples  int       `json:"discarded_tail_samples"`
	Detrend               string    `json:"detrend"`
	IntegratedPower       float64   `json:"integrated_power"`
}
