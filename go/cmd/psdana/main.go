// Command psdana computes PSD summaries or machine-only JSON; it never plots.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"strconv"

	"github.com/xulu199705/psdana/go/csvio"
	"github.com/xulu199705/psdana/go/psd"
)

func projectRoot() (string, error) {
	cwd, _ := os.Getwd()
	executable, _ := os.Executable()
	for _, start := range []string{cwd, filepath.Dir(executable)} {
		for dir := start; ; dir = filepath.Dir(dir) {
			if _, err := os.Stat(filepath.Join(dir, "data", "sine_+40MHz_160MSPS.csv")); err == nil {
				return dir, nil
			}
			if filepath.Dir(dir) == dir {
				break
			}
		}
	}
	return "", fmt.Errorf("cannot find project root; run from repository/module directory or use absolute --input")
}
func run(args []string) error {
	flags := flag.NewFlagSet("psdana", flag.ContinueOnError)
	flags.SetOutput(os.Stderr)
	c := psd.DefaultConfig()
	readerConfig := csvio.DefaultConfig()
	input := flags.String("input", "data/sine_+40MHz_160MSPS.csv", "absolute path or path relative to project root")
	flags.Float64Var(&c.FS, "fs", c.FS, "sample rate Hz")
	flags.StringVar(&c.Window, "window", c.Window, "hann or rectangle")
	points := flags.String("fft-points", "all", "all or a positive integer")
	flags.Float64Var(&c.Overlap, "overlap", c.Overlap, "Welch overlap ratio [0,1)")
	flags.StringVar(&c.Detrend, "detrend", c.Detrend, "none or mean")
	format := flags.String("sample-format", "auto", "float, q15, hex_q15; auto uses hex_q15 only for original capture")
	flags.StringVar(&readerConfig.InputType, "input-type", "auto", "auto, real or iq")
	flags.StringVar(&readerConfig.Header, "header", "auto", "auto, yes or no")
	separator := flags.String("delimiter", "", "comma, semicolon, tab or a literal character; empty=auto")
	realColumn := flags.String("real-column", "", "name or zero-based index")
	iColumn := flags.String("i-column", "", "I name or zero-based index")
	qColumn := flags.String("q-column", "", "Q name or zero-based index")
	jsonOutput := flags.Bool("json", false, "stdout contains only complete PSDResult JSON")
	left := flags.Float64("freq-left", 0, "band left boundary in Hz; requires --freq-right")
	right := flags.Float64("freq-right", 0, "band right boundary in Hz; requires --freq-left")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if flags.NArg() != 0 {
		return fmt.Errorf("unexpected positional arguments")
	}
	hasLeft, hasRight := false, false
	flags.Visit(func(f *flag.Flag) {
		if f.Name == "freq-left" {
			hasLeft = true
		}
		if f.Name == "freq-right" {
			hasRight = true
		}
	})
	if hasLeft != hasRight {
		return fmt.Errorf("freq-left and freq-right must be provided together")
	}
	if *points != "all" {
		n, err := strconv.Atoi(*points)
		if err != nil || n <= 0 {
			return fmt.Errorf("fft-points must be all or a positive integer")
		}
		c.FFTPoints = psd.FFTPoints{N: n}
	}
	root, rootErr := projectRoot()
	path := *input
	if !filepath.IsAbs(path) {
		if rootErr != nil {
			return rootErr
		}
		path = filepath.Join(root, path)
	}
	if *format == "auto" {
		readerConfig.SampleFormat = "float"
		if rootErr == nil && filepath.Clean(path) == filepath.Join(root, "data", "sine_+40MHz_160MSPS.csv") {
			readerConfig.SampleFormat = "hex_q15"
		}
	} else {
		readerConfig.SampleFormat = *format
	}
	if *separator != "" {
		sep := *separator
		switch sep {
		case "comma":
			sep = ","
		case "semicolon":
			sep = ";"
		case "tab":
			sep = "\t"
		}
		readerConfig.Delimiter = &sep
	}
	if *realColumn != "" {
		readerConfig.RealColumn = csvio.ParseColumn(*realColumn)
	}
	if *iColumn != "" {
		readerConfig.IColumn = csvio.ParseColumn(*iColumn)
	}
	if *qColumn != "" {
		readerConfig.QColumn = csvio.ParseColumn(*qColumn)
	}
	data, err := csvio.ReadCSV(path, readerConfig)
	if err != nil {
		return err
	}
	var r psd.PSDResult
	if data.InputType == "complex" {
		r, err = psd.ComputeComplexPSD(data.Complex, c)
	} else {
		r, err = psd.ComputeRealPSD(data.Real, c)
	}
	if err != nil {
		return err
	}
	var metrics *psd.PowerResult
	if hasLeft {
		p, err := psd.AnalyzeBandPower(r, *left, *right)
		if err != nil {
			return err
		}
		metrics = &p
	}
	if *jsonOutput {
		if metrics != nil {
			return json.NewEncoder(os.Stdout).Encode(struct {
				psd.PSDResult
				PowerMetrics *psd.PowerResult `json:"power_metrics"`
			}{r, metrics})
		}
		return json.NewEncoder(os.Stdout).Encode(r)
	}
	peak := -1
	for j, p := range r.PSDLinear {
		if p > 0 && (peak < 0 || p > r.PSDLinear[peak]) {
			peak = j
		}
	}
	peakFrequency, rbw, density := "N/A", math.Inf(-1), math.Inf(-1)
	if peak >= 0 {
		peakFrequency = fmt.Sprintf("%.12g Hz", r.FrequencyHz[peak])
		rbw, density = r.RBWPowerDBFS[peak], r.PSDDBFSPerHz[peak]
	}
	fmt.Printf("Samples: %d\nInput Type: %s\nFFT Size: %d\nMethod: %s\nWindow: %s\nSegment Count: %d\nPeak Frequency: %s\nPeak RBW Power: %.9f dBFS\nPeak PSD: %.9f dBFS/Hz\nFrequency Resolution: %.12g Hz\nENBW: %.12g Hz\nIntegrated Power: %.12g\n",
		r.InputSampleCount, r.InputType, r.FFTSize, r.Method, r.Window, r.SegmentCount, peakFrequency, rbw, density, r.FrequencyResolutionHz, r.ENBWHZ, r.IntegratedPower)
	if metrics != nil {
		f := "N/A"
		if metrics.PeakFrequencyHz != nil {
			f = fmt.Sprintf("%.12g Hz", *metrics.PeakFrequencyHz)
		}
		end := ")"
		if metrics.IsPoint {
			end = "]"
		}
		fmt.Printf("Frequency Range: [%.12g, %.12g%s Hz; point=%t\nBand Peak Frequency: %s\nPeak Power (dBFS): %.9f\nAverage Power (dBFS): %.9f\n", metrics.FreqLeftHz, metrics.FreqRightHz, end, metrics.IsPoint, f, metrics.PeakPowerDBFS, metrics.AveragePowerDBFS)
	}
	return nil
}
func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, "psdana:", err)
		os.Exit(1)
	}
}
