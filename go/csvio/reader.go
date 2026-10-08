// Package csvio decodes explicit floating-point and Q1.15 CSV inputs.
package csvio

import (
	"bufio"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"os"
	"strconv"
	"strings"
	"unicode/utf8"
)

// Column selects a case-insensitive header name or a zero-based index.
type Column struct {
	Name    string
	Index   int
	ByIndex bool
}

func (c *Column) UnmarshalJSON(raw []byte) error {
	var index int
	if err := json.Unmarshal(raw, &index); err == nil && string(raw) != "null" {
		*c = Column{Index: index, ByIndex: true}
		return nil
	}
	var name string
	if err := json.Unmarshal(raw, &name); err != nil || name == "" {
		return fmt.Errorf("column must be a name or integer index")
	}
	*c = Column{Name: name}
	return nil
}
func (c Column) MarshalJSON() ([]byte, error) {
	if c.ByIndex {
		return json.Marshal(c.Index)
	}
	return json.Marshal(c.Name)
}

// ParseColumn interprets CLI decimal indices; other tokens are column names.
func ParseColumn(value string) *Column {
	if j, err := strconv.Atoi(value); err == nil {
		return &Column{Index: j, ByIndex: true}
	}
	return &Column{Name: value}
}

// CSVConfig matches the Phase 1 input adapter. Use DefaultConfig for defaults.
type CSVConfig struct {
	SampleFormat string  `json:"sample_format"`
	InputType    string  `json:"input_type"`
	Header       string  `json:"header"`
	Delimiter    *string `json:"delimiter"`
	RealColumn   *Column `json:"real_column"`
	IColumn      *Column `json:"i_column"`
	QColumn      *Column `json:"q_column"`
}

// DefaultConfig returns normalized float, auto header/columns/delimiter.
func DefaultConfig() CSVConfig {
	return CSVConfig{SampleFormat: "float", InputType: "auto", Header: "auto"}
}

// CSVData preserves the explicitly selected real or IQ representation.
type CSVData struct {
	Real      []float64
	Complex   []complex128
	InputType string
	Header    []string
	Columns   []int
	Delimiter rune
}

// SampleCount returns the decoded sample count.
func (d CSVData) SampleCount() int {
	if d.InputType == "complex" {
		return len(d.Complex)
	}
	return len(d.Real)
}

func number(token, format string) (float64, error) {
	token = strings.TrimSpace(token)
	var value float64
	switch format {
	case "float":
		v, err := strconv.ParseFloat(token, 64)
		if err != nil {
			return 0, err
		}
		value = v
	case "q15":
		for _, c := range token {
			if !(c >= '0' && c <= '9') && c != '+' && c != '-' {
				return 0, fmt.Errorf("Q1.15 requires decimal signed int16")
			}
		}
		v, err := strconv.ParseInt(token, 10, 16)
		if err != nil {
			return 0, fmt.Errorf("invalid signed int16: %w", err)
		}
		value = float64(v) / 32768
	case "hex_q15":
		digits := token
		if strings.HasPrefix(strings.ToLower(digits), "0x") {
			digits = digits[2:]
		}
		if len(digits) < 1 || len(digits) > 4 {
			return 0, fmt.Errorf("hex_q15 requires 1-4 hex digits")
		}
		for _, c := range digits {
			if !strings.ContainsRune("0123456789abcdefABCDEF", c) {
				return 0, fmt.Errorf("invalid hexadecimal word")
			}
		}
		v, err := strconv.ParseUint(digits, 16, 16)
		if err != nil {
			return 0, err
		}
		value = float64(int16(uint16(v))) / 32768
	}
	if math.IsNaN(value) || math.IsInf(value, 0) {
		return 0, fmt.Errorf("sample contains NaN/Inf")
	}
	return value, nil
}

func delimiter(preview string) (rune, error) {
	selected := rune(',')
	found := false
	for _, candidate := range []rune{',', ';', '\t'} {
		reader := csv.NewReader(strings.NewReader(preview))
		reader.Comma = candidate
		row, err := reader.Read()
		if err == nil && len(row) > 1 {
			if found {
				return 0, fmt.Errorf("ambiguous delimiter; specify explicitly")
			}
			selected = candidate
			found = true
		}
	}
	return selected, nil
}

// ReadCSV reads a file and returns errors instead of silently inventing samples.
func ReadCSV(path string, c CSVConfig) (CSVData, error) {
	stream, err := os.Open(path)
	if err != nil {
		return CSVData{}, err
	}
	defer stream.Close()
	return Read(stream, c)
}

// Read decodes CSV from a reader, without peak normalization or FFT computation.
func Read(stream io.Reader, c CSVConfig) (CSVData, error) {
	if c.SampleFormat != "float" && c.SampleFormat != "q15" && c.SampleFormat != "hex_q15" {
		return CSVData{}, fmt.Errorf("invalid sample_format")
	}
	if c.InputType != "auto" && c.InputType != "real" && c.InputType != "iq" {
		return CSVData{}, fmt.Errorf("invalid input_type")
	}
	if c.Header != "auto" && c.Header != "yes" && c.Header != "no" {
		return CSVData{}, fmt.Errorf("invalid header setting")
	}
	buffered := bufio.NewReaderSize(stream, 8192)
	if prefix, _ := buffered.Peek(3); string(prefix) == "\xef\xbb\xbf" {
		_, _ = buffered.Discard(3)
	}
	sep := rune(',')
	if c.Delimiter != nil {
		if utf8.RuneCountInString(*c.Delimiter) != 1 {
			return CSVData{}, fmt.Errorf("delimiter must be one character")
		}
		sep, _ = utf8.DecodeRuneInString(*c.Delimiter)
		if sep == '\r' || sep == '\n' || sep == '"' || sep == 0 || sep == utf8.RuneError {
			return CSVData{}, fmt.Errorf("invalid delimiter")
		}
	} else {
		preview, _ := buffered.Peek(8192)
		var err error
		sep, err = delimiter(string(preview))
		if err != nil {
			return CSVData{}, err
		}
	}
	reader := csv.NewReader(buffered)
	reader.Comma = sep
	first, err := reader.Read()
	if err != nil {
		return CSVData{}, fmt.Errorf("CSV first row: %w", err)
	}
	for j := range first {
		first[j] = strings.TrimSpace(first[j])
	}
	width := len(first)
	header := c.Header == "yes"
	if c.Header == "auto" {
		numeric := 0
		for _, s := range first {
			if _, err := number(s, c.SampleFormat); err == nil {
				numeric++
			}
		}
		if numeric == width {
			header = false
		} else if numeric > 0 {
			return CSVData{}, fmt.Errorf("ambiguous first row; specify header=yes/no")
		} else {
			for _, s := range first {
				if _, err := strconv.ParseFloat(s, 64); err == nil {
					return CSVData{}, fmt.Errorf("invalid numeric first row; specify format/header")
				}
			}
			header = true
		}
	}
	data := CSVData{Delimiter: sep}
	if header {
		data.Header = first
		seen := map[string]bool{}
		for _, s := range first {
			key := strings.ToLower(s)
			if key == "" || seen[key] {
				return CSVData{}, fmt.Errorf("header names must be nonempty and unique")
			}
			seen[key] = true
		}
	}
	index := func(column *Column) (int, error) {
		if column.ByIndex {
			if column.Index < 0 || column.Index >= width {
				return 0, fmt.Errorf("column index %d outside [0,%d)", column.Index, width)
			}
			return column.Index, nil
		}
		for j, name := range data.Header {
			if strings.EqualFold(name, column.Name) {
				return j, nil
			}
		}
		return 0, fmt.Errorf("column %q not found; names require header", column.Name)
	}
	hasIQ := c.IColumn != nil || c.QColumn != nil
	if hasIQ && (c.IColumn == nil || c.QColumn == nil) {
		return CSVData{}, fmt.Errorf("specify both I and Q columns")
	}
	if c.RealColumn != nil && (hasIQ || c.InputType == "iq") {
		return CSVData{}, fmt.Errorf("real column conflicts with IQ")
	}
	if hasIQ && c.InputType == "real" {
		return CSVData{}, fmt.Errorf("IQ columns conflict with real input")
	}
	var selected []*Column
	iIndex, iErr := index(&Column{Name: "i"})
	qIndex, qErr := index(&Column{Name: "q"})
	switch {
	case hasIQ:
		selected = []*Column{c.IColumn, c.QColumn}
	case c.RealColumn != nil:
		selected = []*Column{c.RealColumn}
	case c.InputType != "real" && header && iErr == nil && qErr == nil:
		selected = []*Column{{Index: iIndex, ByIndex: true}, {Index: qIndex, ByIndex: true}}
	case width == 1 && c.InputType != "iq":
		selected = []*Column{{Index: 0, ByIndex: true}}
	case width == 2 && c.InputType == "iq" && !header:
		selected = []*Column{{Index: 0, ByIndex: true}, {Index: 1, ByIndex: true}}
	default:
		return CSVData{}, fmt.Errorf("ambiguous columns; specify real_column or i_column/q_column")
	}
	for _, column := range selected {
		j, err := index(column)
		if err != nil {
			return CSVData{}, err
		}
		data.Columns = append(data.Columns, j)
	}
	if len(data.Columns) == 2 && data.Columns[0] == data.Columns[1] {
		return CSVData{}, fmt.Errorf("I and Q columns must differ")
	}
	data.InputType = "real"
	if len(data.Columns) == 2 {
		data.InputType = "complex"
	}
	appendRow := func(row []string, line int) error {
		values := [2]float64{}
		for j, k := range data.Columns {
			v, err := number(row[k], c.SampleFormat)
			if err != nil {
				return fmt.Errorf("CSV row %d column %d: %w", line, k, err)
			}
			values[j] = v
		}
		if data.InputType == "complex" {
			data.Complex = append(data.Complex, complex(values[0], values[1]))
		} else {
			data.Real = append(data.Real, values[0])
		}
		return nil
	}
	if !header {
		if err := appendRow(first, 1); err != nil {
			return CSVData{}, err
		}
	}
	reader.ReuseRecord = true
	for {
		row, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			return CSVData{}, fmt.Errorf("CSV: %w", err)
		}
		line, _ := reader.FieldPos(0)
		if err := appendRow(row, line); err != nil {
			return CSVData{}, err
		}
	}
	if data.SampleCount() == 0 {
		return CSVData{}, fmt.Errorf("CSV contains no samples")
	}
	return data, nil
}
