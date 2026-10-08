package bench

import (
	"bufio"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"runtime"
	"sync"
	"testing"

	"github.com/xulu199705/psdana/go/csvio"
	"github.com/xulu199705/psdana/go/psd"
)

type benchmarkCase struct {
	Name   string        `json:"name"`
	CSV    string        `json:"csv"`
	Config psd.PSDConfig `json:"config"`
	Data   csvio.CSVData `json:"-"`
}

var catalog []benchmarkCase
var catalogErr error
var once sync.Once
var resultSink psd.PSDResult
var dataSink csvio.CSVData

func compute(d csvio.CSVData, c psd.PSDConfig) (psd.PSDResult, error) {
	if d.InputType == "complex" {
		return psd.ComputeComplexPSD(d.Complex, c)
	}
	return psd.ComputeRealPSD(d.Real, c)
}

func defaultFixtures(dir string) ([]benchmarkCase, error) {
	if err := os.MkdirAll(dir, 0755); err != nil {
		return nil, err
	}
	var cases []benchmarkCase
	for _, n := range []int{999, 333, 1024, 8192, 65536, 1048576} {
		path := filepath.Join(dir, fmt.Sprintf("complex_%d.csv", n))
		f, err := os.Create(path)
		if err != nil {
			return nil, err
		}
		w := bufio.NewWriter(f)
		fmt.Fprintln(w, "i,q")
		for j := 0; j < n; j++ {
			fmt.Fprintf(w, "%.17g,%.17g\n", 0.7*math.Cos(float64(j)*0.47)+0.1*math.Sin(float64(j)*0.11), 0.7*math.Sin(float64(j)*0.47))
		}
		if err := w.Flush(); err != nil {
			f.Close()
			return nil, err
		}
		if err := f.Close(); err != nil {
			return nil, err
		}
		c := psd.DefaultConfig()
		cases = append(cases, benchmarkCase{Name: fmt.Sprintf("complex_%d_all", n), CSV: path, Config: c})
		if n > 1024 {
			c.FFTPoints = psd.FFTPoints{N: 1024}
			cases = append(cases, benchmarkCase{Name: fmt.Sprintf("complex_%d_welch1024", n), CSV: path, Config: c})
		}
	}
	return cases, nil
}

func loadCatalog() {
	_, file, _, _ := runtime.Caller(0)
	root := filepath.Clean(filepath.Join(filepath.Dir(file), "../.."))
	dir := os.Getenv("PSD_BENCH_DIR")
	if dir == "" {
		dir = filepath.Join(root, ".cache", "bench")
	}
	raw, err := os.ReadFile(filepath.Join(dir, "manifest.json"))
	if err == nil {
		var manifest struct {
			Cases []benchmarkCase `json:"cases"`
		}
		catalogErr = json.Unmarshal(raw, &manifest)
		catalog = manifest.Cases
	} else if os.Getenv("PSD_BENCH_DIR") != "" {
		catalogErr = err
	} else {
		catalog, catalogErr = defaultFixtures(dir)
	}
	if catalogErr != nil {
		return
	}
	loaded := map[string]csvio.CSVData{}
	for j := range catalog {
		path := catalog[j].CSV
		if !filepath.IsAbs(path) {
			path = filepath.Join(dir, path)
		}
		catalog[j].CSV = path
		if d, ok := loaded[path]; ok {
			catalog[j].Data = d
			continue
		}
		data, err := csvio.ReadCSV(path, csvio.DefaultConfig())
		if err != nil {
			catalogErr = err
			return
		}
		loaded[path] = data
		catalog[j].Data = data
	}
	if len(catalog) == 0 {
		catalogErr = fmt.Errorf("empty benchmark manifest")
	}
}

// BenchmarkPSD measures core, CSV-only, and file-decode+core without process,
// compilation, plotting, JSON, or input generation time. FFT setup is in core.
func BenchmarkPSD(b *testing.B) {
	once.Do(loadCatalog)
	if catalogErr != nil {
		b.Fatal(catalogErr)
	}
	csvMeasured := map[string]bool{}
	for _, entry := range catalog {
		b.Run("Core/"+entry.Name, func(b *testing.B) {
			if _, err := compute(entry.Data, entry.Config); err != nil {
				b.Fatal(err)
			} // warm up, untimed
			b.ReportAllocs()
			b.ResetTimer()
			for j := 0; j < b.N; j++ {
				r, err := compute(entry.Data, entry.Config)
				if err != nil {
					b.Fatal(err)
				}
				resultSink = r
			}
		})
		if !csvMeasured[entry.CSV] {
			csvMeasured[entry.CSV] = true
			b.Run("CSV/"+entry.Name, func(b *testing.B) {
				if _, err := csvio.ReadCSV(entry.CSV, csvio.DefaultConfig()); err != nil {
					b.Fatal(err)
				}
				b.ReportAllocs()
				b.ResetTimer()
				for j := 0; j < b.N; j++ {
					d, err := csvio.ReadCSV(entry.CSV, csvio.DefaultConfig())
					if err != nil {
						b.Fatal(err)
					}
					dataSink = d
				}
			})
		}
		b.Run("E2E/"+entry.Name, func(b *testing.B) {
			d, err := csvio.ReadCSV(entry.CSV, csvio.DefaultConfig())
			if err != nil {
				b.Fatal(err)
			}
			if _, err := compute(d, entry.Config); err != nil {
				b.Fatal(err)
			}
			b.ReportAllocs()
			b.ResetTimer()
			for j := 0; j < b.N; j++ {
				d, err := csvio.ReadCSV(entry.CSV, csvio.DefaultConfig())
				if err != nil {
					b.Fatal(err)
				}
				r, err := compute(d, entry.Config)
				if err != nil {
					b.Fatal(err)
				}
				resultSink = r
			}
		})
	}
}
