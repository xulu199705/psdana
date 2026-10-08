package psd

import (
	"encoding/json"
	"fmt"
	"math"
)

// PowerResult contains absolute band power and Full Scale referenced dB powers.
// In point mode BandPowerLinear is the selected bin's RBW power.
type PowerResult struct {
	FreqLeftHz       float64  `json:"freq_left_hz"`
	FreqRightHz      float64  `json:"freq_right_hz"`
	IsPoint          bool     `json:"is_point"`
	PeakFrequencyHz  *float64 `json:"peak_frequency_hz"`
	PeakPowerDBFS    float64  `json:"peak_power_dbfs"`
	AveragePowerDBFS float64  `json:"average_power_dbfs"`
	BandPowerLinear  float64  `json:"band_power_linear"`
	ContributingBins int      `json:"contributing_bins"`
}

// MarshalJSON encodes -Inf dB and an absent peak frequency as null.
func (p PowerResult) MarshalJSON() ([]byte, error) {
	var peak, average *float64
	if !math.IsInf(p.PeakPowerDBFS, -1) {
		peak = &p.PeakPowerDBFS
	}
	if !math.IsInf(p.AveragePowerDBFS, -1) {
		average = &p.AveragePowerDBFS
	}
	return json.Marshal(struct {
		FreqLeftHz       float64  `json:"freq_left_hz"`
		FreqRightHz      float64  `json:"freq_right_hz"`
		IsPoint          bool     `json:"is_point"`
		PeakFrequencyHz  *float64 `json:"peak_frequency_hz"`
		PeakPowerDBFS    *float64 `json:"peak_power_dbfs"`
		AveragePowerDBFS *float64 `json:"average_power_dbfs"`
		BandPowerLinear  float64  `json:"band_power_linear"`
		ContributingBins int      `json:"contributing_bins"`
	}{p.FreqLeftHz, p.FreqRightHz, p.IsPoint, p.PeakFrequencyHz, peak, average, p.BandPowerLinear, p.ContributingBins})
}

func validatePowerSpectrum(r PSDResult) error {
	if r.FFTSize < 1 || !finite(r.FSHz) || r.FSHz <= 0 || r.FSHz/2 == 0 ||
		!finite(r.FrequencyResolutionHz) || r.FrequencyResolutionHz <= 0 ||
		!finite(r.ENBWHZ) || r.ENBWHZ <= 0 {
		return fmt.Errorf("PSDResult FFT size, fs, df and ENBW must be finite and positive")
	}
	const eps = 2.220446049250313e-16
	df := r.FSHz / float64(r.FFTSize)
	if df == 0 || math.Abs(r.FrequencyResolutionHz-df) > 16*eps*df {
		return fmt.Errorf("PSDResult frequency resolution is inconsistent or unrepresentable")
	}
	length, reference := r.FFTSize, 1.0
	if r.InputType == "real" {
		length, reference = r.FFTSize/2+1, 0.5
	} else if r.InputType != "complex" {
		return fmt.Errorf("PSDResult input_type must be real or complex")
	}
	if r.ReferencePower != reference {
		return fmt.Errorf("PSDResult Full Scale reference is inconsistent with input_type")
	}
	if len(r.PSDLinear) != length || len(r.FrequencyHz) != length {
		return fmt.Errorf("PSDResult frequency/PSD arrays have invalid dimensions")
	}
	for j, p := range r.PSDLinear {
		bin := j
		if r.InputType == "complex" {
			bin -= r.FFTSize / 2
		}
		expected := float64(bin) * r.FrequencyResolutionHz
		if !finite(p) || p < 0 || !finite(r.FrequencyHz[j]) || math.Abs(r.FrequencyHz[j]-expected) > 16*eps*r.FSHz {
			return fmt.Errorf("PSDResult invalid power or frequency axis at bin %d", j)
		}
	}
	return nil
}

// signedBin unfolds a real single-sided bin without duplicating DC or Nyquist.
func signedBin(r PSDResult, j int) (float64, float64) {
	if r.InputType == "complex" {
		return r.FrequencyHz[j], r.PSDLinear[j]
	}
	k := j - r.FFTSize/2
	index, sign := k, 1.0
	if k < 0 {
		index, sign = -k, -1
	}
	p := r.PSDLinear[index]
	if k != 0 && !(r.FFTSize%2 == 0 && k == -r.FFTSize/2) {
		p *= 0.5
	}
	return sign * r.FrequencyHz[index], p
}

func intervalWidth(left, right, lo, hi float64) float64 {
	return math.Max(0, math.Min(right, hi)-math.Max(left, lo))
}
func cellOverlap(center, df, fs, left, right float64) float64 {
	half := fs / 2
	lo, hi := center-df/2, center+df/2
	width := intervalWidth(left, right, math.Max(lo, -half), math.Min(hi, half))
	if lo < -half {
		width += intervalWidth(left, right, half-(-half-lo), half)
	}
	if hi > half {
		width += intervalWidth(left, right, -half, -half+(hi-half))
	}
	return width
}

// AnalyzeBandPower integrates centered periodic bin cells, or selects the nearest
// signed bin for a point. Ties select the lower frequency; zero power has no peak.
// It never computes an FFT, reads samples, or modifies the input result.
func AnalyzeBandPower(r PSDResult, left, right float64) (PowerResult, error) {
	if err := validatePowerSpectrum(r); err != nil {
		return PowerResult{}, err
	}
	half := r.FSHz / 2
	if !finite(left) || !finite(right) || left < -half || right > half || left > right {
		return PowerResult{}, fmt.Errorf("frequency boundaries require finite -fs/2 <= left <= right <= fs/2")
	}
	p := PowerResult{FreqLeftHz: left, FreqRightHz: right, IsPoint: left == right}
	peakDensity, peakFrequency := 0.0, 0.0
	if p.IsPoint {
		index, distance := 0, math.Inf(1)
		for j := 0; j < r.FFTSize; j++ {
			f := float64(j-r.FFTSize/2) * r.FrequencyResolutionHz
			if d := math.Abs(f - left); d < distance {
				index, distance = j, d
			}
		}
		if left == half {
			index = r.FFTSize - 1
		}
		peakFrequency, peakDensity = signedBin(r, index)
		p.ContributingBins = 1
		p.BandPowerLinear = peakDensity * r.ENBWHZ
	} else {
		for j := 0; j < r.FFTSize; j++ {
			f, density := signedBin(r, j)
			width := r.FrequencyResolutionHz
			if left != -half || right != half {
				width = cellOverlap(float64(j-r.FFTSize/2)*r.FrequencyResolutionHz, width, r.FSHz, left, right)
			}
			if width <= 0 {
				continue
			}
			p.ContributingBins++
			p.BandPowerLinear += density * width
			if density > peakDensity {
				peakDensity, peakFrequency = density, f
			}
		}
	}
	peakPower := peakDensity * r.ENBWHZ
	if !finite(peakPower) || !finite(p.BandPowerLinear) {
		return PowerResult{}, fmt.Errorf("band/RBW power exceeds supported float64 range")
	}
	if peakPower > 0 {
		p.PeakFrequencyHz = &peakFrequency
	}
	p.PeakPowerDBFS = dbPower(peakPower, r.ReferencePower)
	p.AveragePowerDBFS = dbPower(p.BandPowerLinear, r.ReferencePower)
	return p, nil
}
